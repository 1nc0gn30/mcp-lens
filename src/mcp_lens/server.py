"""Multi-Threaded HTTP Server, REST API & Server-Sent Events (SSE) for MCP Lens.

Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
100% Python Standard Library — Zero External Dependencies.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Any, Dict, List, Optional, Tuple

from . import __version__
from .analyzer import MCPTrafficAnalyzer, SchemaMinifier
from .proxy import GLOBAL_TRAFFIC, IN_PROCESS_COLLECTORS, TrafficStore, TappedFrame

MAX_BODY_BYTES = 1_048_576  # 1 MiB strict cap
DEFAULT_PORT = 8109
STUDIO_PORT = 3000

CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self' http://127.0.0.1:* http://localhost:*; "
    "font-src 'self' data:; "
    "frame-ancestors 'self' http://127.0.0.1:3000 http://localhost:3000; "
    "object-src 'none'; "
    "base-uri 'self'"
)


class _PayloadTooLargeError(Exception):
    pass


class _BadRequestError(Exception):
    pass


def _is_valid_host(host_header: Optional[str], active_port: int) -> bool:
    """Strict loopback Host validation (blocks DNS rebinding & mismatched ports)."""
    if not host_header:
        return False
    raw = host_header.strip().lower()
    if not raw:
        return False

    hostname = ""
    port: Optional[int] = None

    if raw.startswith("["):
        end_bracket = raw.find("]")
        if end_bracket == -1:
            return False
        hostname = raw[1:end_bracket]
        rest = raw[end_bracket + 1 :]
        if rest:
            if not rest.startswith(":"):
                return False
            try:
                port = int(rest[1:])
            except ValueError:
                return False
    else:
        if raw.count(":") > 1:
            return False
        if ":" in raw:
            hostname, port_str = raw.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                return False
        else:
            hostname = raw

    if hostname not in ("127.0.0.1", "localhost", "::1"):
        return False
    if port is not None and port != active_port:
        return False
    return True


def _is_local_origin(origin: Optional[str], active_port: int = DEFAULT_PORT) -> bool:
    """Exact-port browser Origin allowlist.

    No Origin header = non-browser client (CLI/agent): allowed.
    Browser Origin must match http://(127.0.0.1|localhost|[::1]):(<active_port>|3000).
    """
    if not origin:
        return True
    try:
        u = urllib.parse.urlparse(origin)
        origin_port = u.port
    except ValueError:
        return False
    if u.scheme != "http":
        return False
    if u.hostname not in ("127.0.0.1", "localhost", "::1"):
        return False
    if u.username is not None or u.password is not None:
        return False
    if u.path not in ("", "/") or u.query or u.fragment:
        return False
    allowed_ports = {active_port, STUDIO_PORT}
    return origin_port in allowed_ports


def _cors_origin(handler: "MCPLensRequestHandler") -> str:
    origin = handler.headers.get("Origin")
    active_port = handler._active_port()
    if origin and _is_local_origin(origin, active_port=active_port):
        return origin
    return f"http://127.0.0.1:{active_port}"


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
                    "examples": ["/data/production.db"],
                },
                "query": {
                    "type": "string",
                    "description": "The exact SQL SELECT statement to execute against the target tables.",
                    "examples": ["SELECT id, name, balance FROM accounts LIMIT 10;"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to return in the result set.",
                    "default": 100,
                },
            },
            "required": ["database_path", "query"],
        },
    },
    {
        "name": "filesystem_read_file",
        "description": "Reads the entire text content of a file from the workspace filesystem. Supports UTF-8 encoding and partial byte slicing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute or workspace-relative path to the file to read.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Optional zero-indexed line offset for reading file chunks.",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum number of lines to return from the specified offset.",
                },
            },
            "required": ["file_path"],
        },
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
                "body": {"type": "string", "description": "Full Markdown body content describing the changes."},
            },
            "required": ["repo_owner", "repo_name", "title", "head"],
        },
    },
    {
        "name": "web_search_duckduckgo",
        "description": "Performs a live web search using DuckDuckGo search index and returns ranked titles, snippets, and source URLs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query string to look up."},
                "max_results": {"type": "integer", "description": "Maximum number of search results to return.", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "execute_sandboxed_bash",
        "description": "Spawns an isolated bash process to execute system maintenance commands with resource quotas and strict timeout enforcement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The exact shell command line string to run."},
                "timeout_seconds": {"type": "integer", "description": "Maximum allowed execution time before SIGKILL.", "default": 30},
            },
            "required": ["command"],
        },
    },
]


def seed_sample_traffic(traffic: TrafficStore) -> None:
    """Pre-populate store with sample MCP handshake and tool traffic."""
    if len(traffic.buffer) > 0:
        return

    for t in SAMPLE_MCP_TOOLS:
        traffic.discovered_tools[t["name"]] = t

    traffic.record_frame(
        "inbound",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
                "clientInfo": {"name": "Antigravity/Claude-Code", "version": "2.6.0"},
            },
        }),
    )
    traffic.record_frame(
        "outbound",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": True}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": "NullAI-Sovereign-Server", "version": __version__},
            },
        }),
    )
    traffic.record_frame(
        "inbound",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }),
    )
    traffic.record_frame(
        "outbound",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"tools": SAMPLE_MCP_TOOLS},
        }),
    )
    traffic.record_frame(
        "inbound",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "sqlite_query_records",
                "arguments": {
                    "database_path": "~/data/sovereign.db",
                    "query": "SELECT id, product_name, price FROM items ORDER BY id ASC LIMIT 3;",
                },
            },
        }),
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
                        "text": '[{"id": 1, "product_name": "Grandma\'s Garden Crewneck", "price": 34.99}, {"id": 2, "product_name": "Songbird 15oz Ceramic Mug", "price": 21.99}, {"id": 3, "product_name": "Vintage French Seed Tote", "price": 24.99}]',
                    }
                ],
                "isError": False,
            },
        }),
    )


class MCPLensRequestHandler(SimpleHTTPRequestHandler):
    """Hardened HTTP request handler supporting REST API endpoints and SSE."""

    server_version = "MCPLens/2.6"
    sys_version = ""

    def __init__(self, *args, directory=None, traffic_store=None, **kwargs):
        self.traffic = traffic_store or GLOBAL_TRAFFIC
        if directory is None:
            cur_dir = os.path.dirname(os.path.abspath(__file__))
            pkg_root = os.path.dirname(os.path.dirname(cur_dir))
            directory = os.path.join(pkg_root, "public")
        super().__init__(*args, directory=directory, **kwargs)

    def version_string(self) -> str:
        """Strip Python interpreter version from Server header."""
        return self.server_version

    def _active_port(self) -> int:
        try:
            return int(self.server.server_address[1])
        except Exception:
            return DEFAULT_PORT

    def end_headers(self) -> None:
        """Inject all 4 security headers on every HTTP response."""
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Content-Security-Policy", CSP_POLICY)
        super().end_headers()

    def list_directory(self, path):
        """Disable directory listing completely (returns 404)."""
        self._send_json(404, {"error": "Not found"})
        return None

    def _check_security_gates(self) -> bool:
        """Enforce strict loopback Host and exact-port Origin allowlist."""
        active_port = self._active_port()
        host_header = self.headers.get("Host")
        if host_header is not None:
            if not _is_valid_host(host_header, active_port):
                self._send_json(403, {"error": "Forbidden host header"})
                return False
        elif getattr(self, "request_version", "HTTP/1.1") != "HTTP/1.0":
            self._send_json(403, {"error": "Missing host header"})
            return False

        origin = self.headers.get("Origin")
        if origin and not _is_local_origin(origin, active_port=active_port):
            self._send_json(403, {"error": "Cross-origin request blocked"})
            return False

        return True

    def _send_json(self, status_code: int, data: Any, head_only: bool = False) -> None:
        raw = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Vary", "Origin")
        origin = self.headers.get("Origin")
        if origin and _is_local_origin(origin, active_port=self._active_port()):
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{self._active_port()}")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        if not head_only:
            self.wfile.write(raw)

    def _read_raw_body(self) -> bytes:
        transfer_encoding = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in transfer_encoding:
            chunks: List[bytes] = []
            total = 0
            while True:
                size_line = self.rfile.readline(65536)
                if not size_line:
                    raise _BadRequestError("Incomplete chunked request body")
                size_token = size_line.split(b";", 1)[0].strip()
                try:
                    chunk_size = int(size_token, 16)
                except ValueError:
                    raise _BadRequestError("Invalid chunk size header")
                if chunk_size < 0:
                    raise _BadRequestError("Negative chunk size")
                if chunk_size == 0:
                    # Drain trailer lines until blank line
                    while True:
                        trailer = self.rfile.readline(65536)
                        if not trailer or trailer in (b"\r\n", b"\n"):
                            break
                    break
                total += chunk_size
                if total > MAX_BODY_BYTES:
                    raise _PayloadTooLargeError("Payload exceeds 1 MiB limit")
                chunk_data = self.rfile.read(chunk_size)
                if len(chunk_data) != chunk_size:
                    raise _BadRequestError("Truncated chunk payload")
                chunks.append(chunk_data)
                crlf = self.rfile.read(2)
                if crlf != b"\r\n":
                    # Tolerate lone LF
                    if not crlf.startswith(b"\n"):
                        raise _BadRequestError("Malformed chunk terminator")
            return b"".join(chunks)

        raw_cl = self.headers.get("Content-Length")
        if raw_cl is None:
            return b""
        try:
            content_len = int(raw_cl.strip())
        except ValueError:
            raise _BadRequestError("Invalid Content-Length header")
        if content_len < 0:
            raise _BadRequestError("Negative Content-Length header")
        if content_len > MAX_BODY_BYTES:
            raise _PayloadTooLargeError("Payload exceeds 1 MiB limit")
        if content_len == 0:
            return b""
        return self.rfile.read(content_len)

    def _read_json_body(self) -> Dict[str, Any]:
        raw = self._read_raw_body()
        if not raw.strip():
            return {}
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except Exception:
            raise _BadRequestError("Malformed JSON request body")
        if not isinstance(decoded, dict):
            raise _BadRequestError("JSON request body must be an object")
        return decoded

    def _health_payload(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "service": "mcp-lens",
            "port": self._active_port(),
            "version": __version__,
            "engine": "mcp-traffic-sniffer",
            "uptime_seconds": round(time.time() - self.traffic.start_time, 1),
        }

    def _stats_payload(self) -> Dict[str, Any]:
        stats = self.traffic.get_stats()
        tools_audit = MCPTrafficAnalyzer.audit_tools_list(list(self.traffic.discovered_tools.values()))
        stats["token_overhead"] = tools_audit["total_tokens_raw"]
        stats["potential_savings_tokens"] = tools_audit["total_tokens_saved"]
        stats["savings_percent"] = tools_audit["overall_savings_percent"]
        stats["version"] = __version__
        stats["port"] = self._active_port()
        return stats

    def _parse_limit(self, qs: Dict[str, List[str]]) -> Tuple[Optional[int], Optional[str]]:
        if "limit" not in qs:
            return 100, None
        raw_val = qs["limit"][0]
        try:
            limit = int(raw_val)
        except (ValueError, TypeError):
            return None, "Invalid limit parameter; expected integer between 1 and 1000"
        if limit < 1:
            return None, "Invalid limit parameter; must be >= 1"
        return min(limit, 1000), None

    def _handle_api_get(self, path: str, qs: Dict[str, List[str]], head_only: bool = False) -> bool:
        if path in ("/api/health", "/health"):
            self._send_json(200, self._health_payload(), head_only=head_only)
            return True

        if path == "/api/stats":
            self._send_json(200, self._stats_payload(), head_only=head_only)
            return True

        if path == "/api/traffic":
            limit, err = self._parse_limit(qs)
            if err is not None:
                self._send_json(400, {"error": err}, head_only=head_only)
                return True
            topic = qs.get("topic", [None])[0]
            frames = self.traffic.get_recent(limit=limit or 100, method_filter=topic)
            self._send_json(200, {"count": len(frames), "frames": frames}, head_only=head_only)
            return True

        if path == "/api/tools":
            tools_list = list(self.traffic.discovered_tools.values())
            audit = MCPTrafficAnalyzer.audit_tools_list(tools_list)
            self._send_json(200, audit, head_only=head_only)
            return True

        if path == "/api/events/stream":
            if head_only:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", _cors_origin(self))
                self.end_headers()
            else:
                self._handle_sse_stream()
            return True

        if path.startswith("/api/"):
            self._send_json(404, {"error": "Endpoint not found", "path": path}, head_only=head_only)
            return True

        return False

    def do_OPTIONS(self) -> None:
        if not self._check_security_gates():
            return
        self.send_response(204)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Origin", _cors_origin(self))
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_HEAD(self) -> None:
        if not self._check_security_gates():
            return
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if self._handle_api_get(parsed.path, qs, head_only=True):
            return
        super().do_HEAD()

    def do_GET(self) -> None:
        if not self._check_security_gates():
            return
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if self._handle_api_get(parsed.path, qs, head_only=False):
            return
        super().do_GET()

    def do_POST(self) -> None:
        if not self._check_security_gates():
            return
        path = urllib.parse.urlparse(self.path).path

        try:
            payload = self._read_json_body()
        except _PayloadTooLargeError as exc:
            self.close_connection = True
            self._send_json(413, {"error": str(exc), "max_bytes": MAX_BODY_BYTES})
            return
        except _BadRequestError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        if path == "/api/minify":
            raw_tool = payload.get("tool", payload)
            if not isinstance(raw_tool, dict) or not raw_tool:
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

        if path == "/api/replay":
            tool_name = str(payload.get("tool_name") or payload.get("name") or "sqlite_query_records")
            arguments = payload.get("arguments", payload.get("args", {}))
            if not isinstance(arguments, dict):
                self._send_json(400, {"error": "arguments must be a JSON object"})
                return

            t0 = time.perf_counter()
            req_id = f"replay_{int(time.time() * 1000)}"
            request_rpc = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
            req_tokens = MCPTrafficAnalyzer.estimate_tokens(request_rpc)
            elapsed_ms = round(max(0.2, (time.perf_counter() - t0) * 1000.0), 2)

            simulated_response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"[MCP Replay] Executed tool '{tool_name}' with args {json.dumps(arguments, sort_keys=True)}.",
                        }
                    ],
                    "isError": False,
                    "execution_ms": elapsed_ms,
                    "request_tokens": req_tokens,
                },
            }

            self.traffic.record_frame("inbound", json.dumps(request_rpc))
            self.traffic.record_frame("outbound", json.dumps(simulated_response))

            self._send_json(200, {
                "success": True,
                "id": req_id,
                "tool": tool_name,
                "arguments": arguments,
                "response": simulated_response["result"],
            })
            return

        if path == "/api/frame":
            direction = str(payload.get("direction", "inbound"))
            if direction not in ("inbound", "outbound"):
                direction = "inbound"
            raw_line = (
                payload.get("raw_line")
                or payload.get("raw_payload")
                or (json.dumps(payload.get("data")) if payload.get("data") is not None else None)
                or (json.dumps(payload.get("json_data")) if payload.get("json_data") is not None else None)
                or ""
            )
            frame = self.traffic.record_frame(direction, str(raw_line))
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
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Origin", _cors_origin(self))
        self.end_headers()

        q = self.traffic.add_subscriber()
        try:
            welcome = json.dumps({"type": "connected", "time": time.time(), "message": "MCP Lens live stream active"})
            self.wfile.write(f"data: {welcome}\n\n".encode("utf-8"))
            self.wfile.flush()

            while True:
                try:
                    frame: TappedFrame = q.get(timeout=10.0)
                    event_data = json.dumps({"type": "frame", "frame": frame.to_dict()})
                    self.wfile.write(f"data: {event_data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    ping = json.dumps({"type": "ping", "time": time.time()})
                    self.wfile.write(f"data: {ping}\n\n".encode("utf-8"))
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.traffic.remove_subscriber(q)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy per-request stderr logs unless explicitly enabled
        if os.environ.get("MCP_LENS_ACCESS_LOG") == "1":
            super().log_message(format, *args)


class MCPLensServer:
    """Manages the lifecycle of the MCP Lens Web Cockpit HTTP Server."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        public_dir: Optional[str] = None,
        traffic_store: Optional[TrafficStore] = None,
    ):
        self.host = host
        self.port = port
        self.public_dir = public_dir
        self.traffic = traffic_store or GLOBAL_TRAFFIC
        seed_sample_traffic(self.traffic)
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self, block: bool = True) -> None:
        handler = lambda *args, **kwargs: MCPLensRequestHandler(
            *args, directory=self.public_dir, traffic_store=self.traffic, **kwargs
        )
        self.server = ThreadingHTTPServer((self.host, self.port), handler)
        bound_port = int(self.server.server_address[1])
        self.port = bound_port
        IN_PROCESS_COLLECTORS[bound_port] = self.traffic
        print(f"● MCP Lens Server v{__version__} listening on http://{self.host}:{bound_port}")

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
            IN_PROCESS_COLLECTORS.pop(self.port, None)
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            print("● MCP Lens Server stopped.")
