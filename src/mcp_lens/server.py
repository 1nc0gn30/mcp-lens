"""Multi-Threaded HTTP Server, REST API & Server-Sent Events (SSE) for MCP Lens.

Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
100% Python Standard Library — Zero External Dependencies.
"""

from __future__ import annotations

import collections
import io
import json
import mimetypes
import os
import queue
import socket
import sys
import threading
import time
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Any, Dict, List, Optional

from .analyzer import MCPTrafficAnalyzer, SchemaMinifier
from .proxy import GLOBAL_TRAFFIC, TrafficStore, TappedFrame


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# Pre-seed realistic sample tools to provide rich initial data
SAMPLE_MCP_TOOLS = [
    {
        "name": "sqlite_query_records",
        "description": "Executes a read-only SQL query against the connected SQLite database. This tool automatically sanitizes queries and returns formatted tabular rows with column headers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database_path": {
                    "type": "string",
                    "description": "Absolute filesystem path to the target SQLite file on disk.",
                    "examples": ["/data/production.db"]
                },
                "query": {
                    "type": "string",
                    "description": "The exact SQL SELECT statement to execute against the target tables.",
                    "examples": ["SELECT id, name, balance FROM accounts LIMIT 10;"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to return in the result set.",
                    "default": 100
                }
            },
            "required": ["database_path", "query"]
        }
    },
    {
        "name": "filesystem_read_file",
        "description": "Reads the entire text content of a file from the workspace filesystem. Supports UTF-8 encoding and partial byte slicing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute or workspace-relative path to the file to read."
                },
                "offset": {
                    "type": "integer",
                    "description": "Optional zero-indexed line offset for reading file chunks."
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum number of lines to return from the specified offset."
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "github_create_pull_request",
        "description": "Opens a new pull request in a GitHub repository using the GitHub REST API v3. Enforces branch comparison and base target validation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_owner": {"type": "string", "description": "The GitHub account username or organization."},
                "repo_name": {"type": "string", "description": "The name of the target repository."},
                "title": {"type": "string", "description": "Descriptive title for the proposed pull request."},
                "head": {"type": "string", "description": "The name of the feature branch where your changes are implemented."},
                "base": {"type": "string", "description": "The branch you want the changes pulled into.", "default": "main"},
                "body": {"type": "string", "description": "Full Markdown body content describing the changes."}
            },
            "required": ["repo_owner", "repo_name", "title", "head"]
        }
    },
    {
        "name": "web_search_duckduckgo",
        "description": "Performs a live web search using DuckDuckGo search index and returns ranked titles, snippets, and source URLs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query string to look up."},
                "max_results": {"type": "integer", "description": "Maximum number of search results to return.", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "execute_sandboxed_bash",
        "description": "Spawns an isolated bash process to execute system maintenance commands with resource quotas and strict timeout enforcement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The exact shell command line string to run."},
                "timeout_seconds": {"type": "integer", "description": "Maximum allowed execution time before SIGKILL.", "default": 30}
            },
            "required": ["command"]
        }
    }
]


def seed_sample_traffic(traffic: TrafficStore) -> None:
    """Pre-populate store with sample MCP handshake and tool traffic."""
    if len(traffic.buffer) > 0:
        return

    # Seed tools
    for t in SAMPLE_MCP_TOOLS:
        traffic.discovered_tools[t["name"]] = t

    # 1. Initialize Request & Response
    traffic.record_frame(
        "inbound",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
                "clientInfo": {"name": "Antigravity/Claude-Code", "version": "2.1.0"}
            }
        })
    )
    traffic.record_frame(
        "outbound",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": True}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": "NullAI-Sovereign-Server", "version": "1.0.0"}
            }
        })
    )

    # 2. Tools List Request & Response
    traffic.record_frame(
        "inbound",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        })
    )
    traffic.record_frame(
        "outbound",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "tools": SAMPLE_MCP_TOOLS
            }
        })
    )

    # 3. Sample Tool Call
    traffic.record_frame(
        "inbound",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "sqlite_query_records",
                "arguments": {
                    "database_path": "/home/zoth/data/sovereign.db",
                    "query": "SELECT id, product_name, price FROM items ORDER BY id ASC LIMIT 3;"
                }
            }
        })
    )
    traffic.record_frame(
        "outbound",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "[{\"id\": 1, \"product_name\": \"Grandma's Garden Crewneck\", \"price\": 34.99}, {\"id\": 2, \"product_name\": \"Songbird 15oz Ceramic Mug\", \"price\": 21.99}, {\"id\": 3, \"product_name\": \"Vintage French Seed Tote\", \"price\": 24.99}]"
                    }
                ],
                "isError": False
            }
        })
    )


class MCPLensRequestHandler(SimpleHTTPRequestHandler):
    """HTTP request handler supporting REST API endpoints and Server-Sent Events (SSE)."""

    server_version = "MCPLens/1.0.0"

    def __init__(self, *args, directory=None, traffic_store=None, **kwargs):
        self.traffic = traffic_store or GLOBAL_TRAFFIC
        if directory is None:
            cur_dir = os.path.dirname(os.path.abspath(__file__))
            pkg_root = os.path.dirname(os.path.dirname(cur_dir))
            directory = os.path.join(pkg_root, "public")
        super().__init__(*args, directory=directory, **kwargs)

    def _send_json(self, status_code: int, data: Any) -> None:
        raw = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> Dict[str, Any]:
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len <= 0:
            return {}
        body = self.rfile.read(content_len).decode("utf-8")
        try:
            return json.loads(body)
        except Exception:
            return {}

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # 1. Health Probe
        if path in ("/api/health", "/health"):
            self._send_json(200, {
                "status": "healthy",
                "service": "mcp-lens",
                "port": 8109,
                "version": "1.0.0",
                "engine": "mcp-traffic-sniffer",
                "uptime_seconds": round(time.time() - self.traffic.start_time, 1),
            })
            return

        # 2. Operational Statistics
        if path == "/api/stats":
            stats = self.traffic.get_stats()
            # Calculate total token weights for discovered tools
            tools_audit = MCPTrafficAnalyzer.audit_tools_list(list(self.traffic.discovered_tools.values()))
            stats["token_overhead"] = tools_audit["total_tokens_raw"]
            stats["potential_savings_tokens"] = tools_audit["total_tokens_saved"]
            stats["savings_percent"] = tools_audit["overall_savings_percent"]
            self._send_json(200, stats)
            return

        # 3. Traffic Waterfall Frames
        if path == "/api/traffic":
            limit = int(qs.get("limit", [100])[0])
            topic = qs.get("topic", [None])[0]
            frames = self.traffic.get_recent(limit=limit, method_filter=topic)
            self._send_json(200, {
                "count": len(frames),
                "frames": frames,
            })
            return

        # 4. Discovered Tool Schemas & Token Weight Audit
        if path == "/api/tools":
            tools_list = list(self.traffic.discovered_tools.values())
            audit = MCPTrafficAnalyzer.audit_tools_list(tools_list)
            self._send_json(200, audit)
            return

        # 5. Live Server-Sent Events (SSE) Stream
        if path == "/api/events/stream":
            self._handle_sse_stream()
            return

        # Fallback to static file server (public/ directory)
        super().do_GET()

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        payload = self._read_json_body()

        # 1. Minify Schema Endpoint
        if path == "/api/minify":
            raw_tool = payload.get("tool", payload)
            if not isinstance(raw_tool, dict):
                self._send_json(400, {"error": "Invalid tool schema JSON"})
                return

            minified, orig_tok, min_tok = SchemaMinifier.minify_schema(raw_tool)
            saved = max(0, orig_tok - min_tok)
            pct = round((saved / orig_tok) * 100.0, 1) if orig_tok > 0 else 0.0

            self._send_json(200, {
                "success": True,
                "original_tokens": orig_tok,
                "minified_tokens": min_tok,
                "tokens_saved": saved,
                "savings_percent": pct,
                "minified_schema": minified,
            })
            return

        # 2. Replay / Test Tool Execution Endpoint
        if path == "/api/replay":
            tool_name = payload.get("tool_name", payload.get("name", "sqlite_query_records"))
            arguments = payload.get("arguments", payload.get("args", {}))

            # Simulate realistic MCP execution response
            simulated_response = {
                "jsonrpc": "2.0",
                "id": f"replay_{int(time.time()*1000)}",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"✓ [MCP Replay Simulator] Executed tool '{tool_name}' with args {json.dumps(arguments)}."
                        }
                    ],
                    "isError": False,
                    "execution_ms": 14.2
                }
            }

            # Record into live traffic waterfall
            self.traffic.record_frame("inbound", json.dumps({
                "jsonrpc": "2.0",
                "id": simulated_response["id"],
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments}
            }))
            self.traffic.record_frame("outbound", json.dumps(simulated_response))

            self._send_json(200, {
                "success": True,
                "tool": tool_name,
                "arguments": arguments,
                "response": simulated_response["result"]
            })
            return

        # 3. External Frame Ingestion (from proxy or client)
        if path == "/api/frame":
            direction = payload.get("direction", "inbound")
            raw_line = (
                payload.get("raw_line")
                or payload.get("raw_payload")
                or json.dumps(payload.get("data") or payload.get("json_data") or {})
            )
            frame = self.traffic.record_frame(direction, raw_line)
            if frame:
                self._send_json(200, {"success": True, "status": "recorded", "frame_id": frame.frame_id})
            else:
                self._send_json(400, {"error": "Invalid frame"})
            return

        self._send_json(404, {"error": "Endpoint not found", "path": path})

    def _handle_sse_stream(self) -> None:
        """Stream real-time frame events to web clients via Server-Sent Events."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = self.traffic.add_subscriber()
        try:
            # Send initial connection confirmation
            welcome = json.dumps({"type": "connected", "time": time.time(), "message": "MCP Lens live stream active"})
            self.wfile.write(f"data: {welcome}\n\n".encode("utf-8"))
            self.wfile.flush()

            while True:
                try:
                    frame: TappedFrame = q.get(timeout=10.0)
                    event_data = json.dumps({
                        "type": "frame",
                        "frame": frame.to_dict(),
                    })
                    self.wfile.write(f"data: {event_data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    # Heartbeat ping
                    ping = json.dumps({"type": "ping", "time": time.time()})
                    self.wfile.write(f"data: {ping}\n\n".encode("utf-8"))
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.traffic.remove_subscriber(q)


class MCPLensServer:
    """Manages the lifecycle of the MCP Lens Web Cockpit HTTP Server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8109, public_dir: Optional[str] = None):
        self.host = host
        self.port = port
        self.public_dir = public_dir
        self.traffic = GLOBAL_TRAFFIC
        seed_sample_traffic(self.traffic)
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self, block: bool = True) -> None:
        handler = lambda *args, **kwargs: MCPLensRequestHandler(
            *args, directory=self.public_dir, traffic_store=self.traffic, **kwargs
        )
        self.server = ThreadingHTTPServer((self.host, self.port), handler)
        print(f"● MCP Lens Server listening on http://{self.host}:{self.port}")

        if block:
            try:
                self.server.serve_forever()
            except KeyboardInterrupt:
                self.stop()
        else:
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            print("● MCP Lens Server stopped.")
