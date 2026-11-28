"""Transparent Non-Blocking Stdio/SSE Proxy & Frame Sniffer for MCP.

Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
Transparently proxies stdio between host AI agent and child MCP server process,
tapping JSON-RPC 2.0 frames into memory and optionally dispatching to a remote Web Cockpit.
100% Python Standard Library — Zero External Dependencies.
"""

from __future__ import annotations

import collections
import json
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Deque, Dict, List, Optional

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
            return None

        meta = MCPTrafficAnalyzer.categorize_frame(parsed)

        with self.lock:
            f_id = f"f_{int(time.time() * 1000)}_{self.total_frames + 1}"
            frame = TappedFrame(
                frame_id=f_id,
                direction=direction,
                timestamp=time.time(),
                raw_payload=raw_line.strip(),
                json_data=parsed,
                meta=meta,
            )
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

# Tracks in-process bound HTTP server ports mapped to their TrafficStore
# so StdioProxy never double-records by POSTing back into the same store.
IN_PROCESS_COLLECTORS: Dict[int, TrafficStore] = {}


class StdioProxy:
    """Bidirectional non-blocking stdio proxy with real-time JSON-RPC line tapping."""

    def __init__(
        self,
        command: List[str],
        traffic_store: Optional[TrafficStore] = None,
        remote_collector_url: Optional[str] = None,
        stdin_stream: Optional[Any] = None,
        stdout_stream: Optional[Any] = None,
        queue_maxsize: int = 256,
    ):
        self.command = command
        self._has_local_store = traffic_store is not None
        self.traffic = traffic_store if traffic_store is not None else GLOBAL_TRAFFIC
        self.remote_url = remote_collector_url
        self.stdin_stream = stdin_stream if stdin_stream is not None else sys.stdin
        self.stdout_stream = stdout_stream if stdout_stream is not None else sys.stdout
        self.child: Optional[subprocess.Popen] = None
        self.running = False
        self.threads: List[threading.Thread] = []
        self._post_queue: queue.Queue[Optional[Dict[str, Any]]] = queue.Queue(maxsize=max(1, queue_maxsize))
        self._dispatcher_thread: Optional[threading.Thread] = None
        self._dispatcher_lock = threading.Lock()

    def _should_post_remote(self) -> bool:
        """Never POST back into the same process's TrafficStore (prevents double-recording)."""
        if not self.remote_url:
            return False
        if self._has_local_store:
            return False
        try:
            u = urllib.parse.urlparse(self.remote_url)
            if u.hostname in ("127.0.0.1", "localhost", "::1") and u.port is not None:
                bound_store = IN_PROCESS_COLLECTORS.get(u.port)
                if bound_store is self.traffic:
                    return False
        except ValueError:
            return False
        return True

    def _ensure_dispatcher(self) -> None:
        with self._dispatcher_lock:
            if self._dispatcher_thread is not None and self._dispatcher_thread.is_alive():
                return
            self._dispatcher_thread = threading.Thread(
                target=self._remote_dispatch_loop,
                name="mcp-lens-remote-dispatcher",
                daemon=True,
            )
            self._dispatcher_thread.start()

    def _remote_dispatch_loop(self) -> None:
        """Single bounded-queue background worker that posts tapped frames to a remote collector."""
        while True:
            item = self._post_queue.get()
            try:
                if item is None:
                    return
                if not self.remote_url:
                    continue
                payload = json.dumps(item).encode("utf-8")
                req = urllib.request.Request(
                    self.remote_url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=0.25):
                    pass
            except Exception:
                pass  # Non-blocking: never impede stdio flow
            finally:
                self._post_queue.task_done()

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
                bufsize=1,
            )
        except Exception as e:
            sys.stderr.write(f"[mcp-lens] Failed to execute command {' '.join(self.command)}: {e}\n")
            sys.stderr.flush()
            self.running = False
            return 1

        if self._should_post_remote():
            self._ensure_dispatcher()

        t_in = threading.Thread(target=self._pump_stdin_to_child, daemon=True)
        t_out = threading.Thread(target=self._pump_child_stdout_to_host, daemon=True)
        t_err = threading.Thread(target=self._pump_child_stderr_to_host, daemon=True)

        self.threads = [t_in, t_out, t_err]
        for t in self.threads:
            t.start()

        try:
            return_code = self.child.wait()
        except KeyboardInterrupt:
            self.stop()
            return 0

        for t in self.threads:
            t.join(timeout=0.5)

        self.running = False
        self._shutdown_dispatcher()
        return return_code

    def _shutdown_dispatcher(self) -> None:
        if self._dispatcher_thread is not None and self._dispatcher_thread.is_alive():
            try:
                self._post_queue.put_nowait(None)
            except queue.Full:
                pass
            self._dispatcher_thread.join(timeout=0.5)

    def stop(self) -> None:
        """Terminate child process and dispatcher cleanly."""
        self.running = False
        if self.child and self.child.poll() is None:
            try:
                self.child.terminate()
                self.child.wait(timeout=2.0)
            except Exception:
                self.child.kill()
        self._shutdown_dispatcher()

    def _pump_stdin_to_child(self) -> None:
        """Stream host stdin directly to child stdin and record inbound frames."""
        try:
            for line in self.stdin_stream:
                if not self.running or self.child is None or self.child.stdin is None:
                    break

                self._dispatch_tapped_frame("inbound", line)

                try:
                    self.child.stdin.write(line)
                    self.child.stdin.flush()
                except (BrokenPipeError, OSError):
                    break
        except Exception:
            pass
        finally:
            try:
                if self.child and self.child.stdin:
                    self.child.stdin.close()
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

                self._dispatch_tapped_frame("outbound", line)

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
        """Record into in-memory store and enqueue for remote collector only when external."""
        frame = self.traffic.record_frame(direction, raw_line)
        if frame and self._should_post_remote():
            self._ensure_dispatcher()
            try:
                self._post_queue.put_nowait(frame.to_dict())
            except queue.Full:
                pass  # Bounded queue drops telemetry rather than blocking stdio
