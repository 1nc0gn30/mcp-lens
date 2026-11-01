"""Transparent Non-Blocking Stdio/SSE Proxy & Frame Sniffer for MCP.

Engineered by 1nc0gn30 (@1nc0gn30) • NullAI Platform.
Transparently proxies stdio between host AI agent and child MCP server process,
tapping JSON-RPC 2.0 frames into memory and dispatching to the live Web Cockpit.
100% Python Standard Library — Zero External Dependencies.
"""

from __future__ import annotations

import collections
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

from .analyzer import MCPTrafficAnalyzer


@dataclass
class TappedFrame:
    frame_id: str
    direction: str          # "inbound" (host -> child) or "outbound" (child -> host)
    timestamp: float
    raw_payload: str
    json_data: Optional[Dict[str, Any]]
    meta: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TrafficStore:
    """Thread-safe ring buffer and subscriber hub for tapped MCP traffic."""

    def __init__(self, maxlen: int = 1000):
        self.lock = threading.Lock()
        self.buffer: Deque[TappedFrame] = collections.deque(maxlen=maxlen)
        self.discovered_tools: Dict[str, Dict[str, Any]] = {}
        self.subscribers: List[queue.Queue] = []
        self.total_frames = 0
        self.total_bytes = 0
        self.total_tokens = 0
        self.start_time = time.time()

    def record_frame(self, direction: str, raw_line: str) -> Optional[TappedFrame]:
        """Parse, classify, store, and publish a tapped JSON-RPC frame."""
        parsed = MCPTrafficAnalyzer.parse_frame(raw_line)
        if not parsed:
            # Ignore non-JSON diagnostic noise or ping
            return None

        meta = MCPTrafficAnalyzer.categorize_frame(parsed)
        f_id = f"f_{int(time.time() * 1000)}_{self.total_frames + 1}"

        frame = TappedFrame(
            frame_id=f_id,
            direction=direction,
            timestamp=time.time(),
            raw_payload=raw_line.strip(),
            json_data=parsed,
            meta=meta,
        )

        with self.lock:
            self.buffer.append(frame)
            self.total_frames += 1
            self.total_bytes += meta["byte_size"]
            self.total_tokens += meta["estimated_tokens"]

            # Inspect tools/list responses to discover schemas
            if direction == "outbound" and isinstance(parsed.get("result"), dict):
                res = parsed["result"]
                if "tools" in res and isinstance(res["tools"], list):
                    for t in res["tools"]:
                        if isinstance(t, dict) and "name" in t:
                            self.discovered_tools[t["name"]] = t

            # Notify active SSE subscribers
            dead_subs = []
            for q in self.subscribers:
                try:
                    q.put_nowait(frame)
                except Exception:
                    dead_subs.append(q)
            for d in dead_subs:
                self.subscribers.remove(d)

        return frame

    def add_subscriber(self) -> queue.Queue:
        """Register a new queue for Server-Sent Events (SSE) streaming."""
        q: queue.Queue = queue.Queue(maxsize=200)
        with self.lock:
            self.subscribers.append(q)
        return q

    def remove_subscriber(self, q: queue.Queue) -> None:
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def get_recent(self, limit: int = 50, method_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            frames = list(self.buffer)
        if method_filter:
            frames = [f for f in frames if f.meta.get("primary_topic") == method_filter]
        return [f.to_dict() for f in frames[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            uptime = round(time.time() - self.start_time, 1)
            return {
                "total_frames": self.total_frames,
                "total_bytes": self.total_bytes,
                "total_tokens": self.total_tokens,
                "discovered_tools_count": len(self.discovered_tools),
                "active_subscribers": len(self.subscribers),
                "uptime_seconds": uptime,
                "buffer_size": len(self.buffer),
            }


GLOBAL_TRAFFIC = TrafficStore()


class StdioProxy:
    """Bidirectional non-blocking stdio proxy with real-time JSON-RPC line tapping."""

    def __init__(
        self,
        command: List[str],
        traffic_store: Optional[TrafficStore] = None,
        remote_collector_url: Optional[str] = "http://127.0.0.1:8109/api/frame",
        stdin_stream: Optional[Any] = None,
        stdout_stream: Optional[Any] = None,
    ):
        self.command = command
        self.traffic = traffic_store or GLOBAL_TRAFFIC
        self.remote_url = remote_collector_url
        self.stdin_stream = stdin_stream if stdin_stream is not None else sys.stdin
        self.stdout_stream = stdout_stream if stdout_stream is not None else sys.stdout
        self.child: Optional[subprocess.Popen] = None
        self.running = False
        self.threads: List[threading.Thread] = []

    def start(self) -> int:
        """Spawn child MCP server process and launch tapping threads."""
        self.running = True
        try:
            self.child = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
            )
        except Exception as e:
            sys.stderr.write(f"[mcp-lens] Failed to execute command {' '.join(self.command)}: {e}\n")
            sys.stderr.flush()
            return 1

        # Thread 1: Host stdin -> Child stdin (Inbound)
        t_in = threading.Thread(target=self._pump_stdin_to_child, daemon=True)
        # Thread 2: Child stdout -> Host stdout (Outbound)
        t_out = threading.Thread(target=self._pump_child_stdout_to_host, daemon=True)
        # Thread 3: Child stderr -> Host stderr (Passthrough)
        t_err = threading.Thread(target=self._pump_child_stderr_to_host, daemon=True)

        self.threads = [t_in, t_out, t_err]
        for t in self.threads:
            t.start()

        # Wait for child completion
        try:
            return_code = self.child.wait()
        except KeyboardInterrupt:
            self.stop()
            return 0

        self.running = False
        return return_code

    def stop(self) -> None:
        """Terminate child process cleanly."""
        self.running = False
        if self.child and self.child.poll() is None:
            try:
                self.child.terminate()
                self.child.wait(timeout=2.0)
            except Exception:
                self.child.kill()

    def _pump_stdin_to_child(self) -> None:
        """Stream host stdin directly to child stdin and record inbound frames."""
        try:
            for line in self.stdin_stream:
                if not self.running or self.child is None or self.child.stdin is None:
                    break

                # Tap frame
                self._dispatch_tapped_frame("inbound", line)

                # Forward without delay
                try:
                    self.child.stdin.write(line)
                    self.child.stdin.flush()
                except (BrokenPipeError, OSError):
                    break
        except Exception:
            pass

    def _pump_child_stdout_to_host(self) -> None:
        """Stream child stdout directly to host stdout and record outbound frames."""
        try:
            if not self.child or not self.child.stdout:
                return

            for line in self.child.stdout:
                if not self.running:
                    break

                # Tap frame
                self._dispatch_tapped_frame("outbound", line)

                # Forward without delay
                try:
                    self.stdout_stream.write(line)
                    self.stdout_stream.flush()
                except (BrokenPipeError, OSError):
                    break
        except Exception:
            pass

    def _pump_child_stderr_to_host(self) -> None:
        """Pass child diagnostics directly to stderr."""
        try:
            if not self.child or not self.child.stderr:
                return

            for line in self.child.stderr:
                if not self.running:
                    break
                try:
                    sys.stderr.write(line)
                    sys.stderr.flush()
                except (BrokenPipeError, OSError):
                    break
        except Exception:
            pass

    def _dispatch_tapped_frame(self, direction: str, raw_line: str) -> None:
        """Record into in-memory store and notify collector."""
        frame = self.traffic.record_frame(direction, raw_line)
        if frame and self.remote_url:
            # Asynchronous background post to server on port 8109 if running
            def _post():
                try:
                    payload = json.dumps(frame.to_dict()).encode("utf-8")
                    req = urllib.request.Request(
                        self.remote_url,
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=0.2):
                        pass
                except Exception:
                    pass  # Non-blocking, never impede stdio flow
            threading.Thread(target=_post, daemon=True).start()
