"""Comprehensive Unit, Security, HTTP Hardening, CLI & MCP Test Suite for MCP Lens v2.6.0.

Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
100% Python Standard Library + pytest. Zero external pip runtime dependencies.
"""

from __future__ import annotations

import http.client
import io
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from mcp_lens import __version__
from mcp_lens.analyzer import MCPTrafficAnalyzer, SchemaMinifier, estimate_tokens
from mcp_lens.cli import main as cli_main
from mcp_lens.mcp_server import MCPLensMCPServer
from mcp_lens.proxy import StdioProxy, TrafficStore
from mcp_lens.server import MAX_BODY_BYTES, MCPLensServer

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def live_server():
    port = _free_port()
    store = TrafficStore(maxlen=500)
    srv = MCPLensServer(host="127.0.0.1", port=port, public_dir=str(REPO_ROOT / "public"), traffic_store=store)
    srv.start(block=False)
    time.sleep(0.2)
    yield srv, port, f"http://127.0.0.1:{port}"
    srv.stop()


def _raw_http(port: int, method: str, path: str, headers=None, body: bytes = b""):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    hdrs = dict(headers or {})
    if "Host" not in hdrs:
        hdrs["Host"] = f"127.0.0.1:{port}"
    conn.request(method, path, body=body, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    resp_headers = {k.lower(): v for k, v in resp.getheaders()}
    status = resp.status
    conn.close()
    return status, resp_headers, data


# ---------------------------------------------------------------------------
# 1. Core Analyzer, Minifier & Store Tests
# ---------------------------------------------------------------------------

def test_version_unified():
    assert __version__ == "2.6.0"


def test_token_estimator():
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0
    assert 2 <= estimate_tokens("hello world") <= 4
    assert estimate_tokens({"query": "SELECT * FROM users;", "limit": 100}) >= 10
    assert MCPTrafficAnalyzer.estimate_tokens("test string") > 0


def test_json_rpc_parser():
    line = '{"jsonrpc": "2.0", "id": 42, "method": "tools/call", "params": {"name": "test"}}'
    parsed = MCPTrafficAnalyzer.parse_frame(line)
    assert parsed is not None and parsed["method"] == "tools/call"
    meta = MCPTrafficAnalyzer.categorize_frame(parsed)
    assert meta["is_valid_rpc"] is True
    assert meta["frame_type"] == "request"
    assert meta["primary_topic"] == "tools/call"

    err_parsed = MCPTrafficAnalyzer.parse_frame('{"jsonrpc": "2.0", "id": 43, "error": {"code": -32601, "message": "Method not found"}}')
    err_meta = MCPTrafficAnalyzer.categorize_frame(err_parsed)
    assert err_meta["has_error"] is True and err_meta["error_message"] == "Method not found"
    assert MCPTrafficAnalyzer.parse_frame("not json") is None


def test_schema_minifier():
    bloated_tool = {
        "name": "enterprise_db_exec",
        "description": "Executes SQL transactions against PostgreSQL.\nVerbose second paragraph with redundant details.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql_query": {
                    "type": "string",
                    "description": "The SQL statement with placeholders.",
                    "examples": ["SELECT id, email FROM production_users LIMIT 50;"],
                },
                "timeout_ms": {"type": "integer", "description": "Timeout in ms.", "default": 5000},
            },
            "required": ["sql_query"],
        },
    }
    minified, orig_tokens, min_tokens = SchemaMinifier.minify_schema(bloated_tool)
    assert min_tokens < orig_tokens
    assert minified["inputSchema"]["properties"]["sql_query"]["type"] == "string"
    assert minified["inputSchema"]["required"] == ["sql_query"]


def test_tool_token_audit():
    tool = {
        "name": "read_logs",
        "description": "Reads application logs from disk.",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string", "description": "Absolute path."}},
            "required": ["filepath"],
        },
    }
    weight = MCPTrafficAnalyzer.audit_tool(tool)
    assert weight.total_tokens >= weight.minified_tokens
    batch = MCPTrafficAnalyzer.audit_tools_list([tool])
    assert batch["total_tools"] == 1


def test_traffic_store_ring_buffer():
    store = TrafficStore(maxlen=5)
    for i in range(10):
        store.record_frame("inbound", json.dumps({"jsonrpc": "2.0", "id": i, "method": f"test/m_{i}", "params": {}}))
    assert store.total_frames == 10
    recent = store.get_recent(limit=10)
    assert len(recent) == 5
    assert recent[-1]["meta"]["method"] == "test/m_9"


# ---------------------------------------------------------------------------
# 2. StdioProxy Single-Recording & Bounded Queue Tests
# ---------------------------------------------------------------------------

def test_stdio_proxy_single_recording_with_local_store(live_server):
    srv, port, _ = live_server
    store = TrafficStore(maxlen=50)
    child_script = (
        "import sys, json; "
        "line = sys.stdin.readline(); "
        "data = json.loads(line); "
        "sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': data['id'], 'result': 'pong'}) + '\\n'); "
        "sys.stdout.flush()"
    )
    req = json.dumps({"jsonrpc": "2.0", "id": 99, "method": "ping", "params": {}}) + "\n"
    stdout_mock = io.StringIO()
    proxy = StdioProxy(
        command=[sys.executable, "-c", child_script],
        traffic_store=store,
        remote_collector_url=f"http://127.0.0.1:{port}/api/frame",
        stdin_stream=io.StringIO(req),
        stdout_stream=stdout_mock,
    )
    assert proxy._should_post_remote() is False
    assert proxy.start() == 0
    assert "pong" in stdout_mock.getvalue()
    # Exactly 2 frames (1 inbound + 1 outbound), never 4 (no double-recording!)
    assert store.total_frames == 2


# ---------------------------------------------------------------------------
# 3. HTTP Hardening, Security Headers, Host/Origin/413/400/HEAD/Chunked Tests
# ---------------------------------------------------------------------------

def test_security_headers_and_stripped_server_header(live_server):
    _, port, _ = live_server
    for path in ("/", "/health", "/api/stats", "/assets/"):
        status, hdrs, _ = _raw_http(port, "GET", path)
        assert hdrs.get("x-frame-options") == "SAMEORIGIN", path
        assert hdrs.get("x-content-type-options") == "nosniff", path
        assert hdrs.get("referrer-policy") == "strict-origin-when-cross-origin", path
        assert "default-src 'self'" in hdrs.get("content-security-policy", ""), path
        assert "Python" not in hdrs.get("server", ""), hdrs.get("server")
        assert hdrs.get("server") == "MCPLens/2.6"


def test_host_dns_rebinding_rejected_403(live_server):
    _, port, _ = live_server
    for method, path in (("GET", "/health"), ("POST", "/api/minify"), ("OPTIONS", "/api/minify")):
        status, _, body = _raw_http(port, method, path, headers={"Host": "evil.example.invalid"})
        assert status == 403
        assert "error" in json.loads(body.decode("utf-8"))

    # Mismatched port in Host header must also return 403
    status, _, _ = _raw_http(port, "GET", "/health", headers={"Host": f"127.0.0.1:{port + 1}"})
    assert status == 403


def test_origin_exact_port_and_methods_403(live_server):
    _, port, _ = live_server
    bad_origins = [
        "https://evil.example.invalid",
        f"http://127.0.0.1:{port}0",
        "http://localhost:9999",
    ]
    for origin in bad_origins:
        for method, path in (("GET", "/api/stats"), ("POST", "/api/minify"), ("OPTIONS", "/api/minify")):
            status, _, body = _raw_http(port, method, path, headers={"Origin": origin})
            assert status == 403, f"{method} {path} Origin={origin} got {status}"
            assert "error" in json.loads(body.decode("utf-8"))

    # Allowed exact-port origin & Studio :3000 origin succeed
    for origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}", "http://127.0.0.1:3000"):
        status, hdrs, _ = _raw_http(port, "OPTIONS", "/api/minify", headers={"Origin": origin})
        assert status == 204
        assert hdrs.get("access-control-allow-origin") == origin


def test_head_endpoints_return_200_empty_body(live_server):
    _, port, _ = live_server
    for path in ("/", "/health", "/api/health", "/api/stats", "/api/traffic?limit=5", "/api/tools"):
        status, hdrs, body = _raw_http(port, "HEAD", path)
        assert status == 200, path
        assert body == b""
        assert hdrs.get("x-content-type-options") == "nosniff"


def test_directory_listing_blocked_404(live_server):
    _, port, _ = live_server
    status, hdrs, body = _raw_http(port, "GET", "/assets/")
    assert status == 404
    assert b"Directory listing" not in body


def test_health_reports_dynamic_port_and_v260(live_server):
    _, port, _ = live_server
    status, _, body = _raw_http(port, "GET", "/api/health")
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["port"] == port
    assert data["version"] == "2.6.0"
    assert data["status"] == "healthy"


def test_payload_413_over_1mib(live_server):
    _, port, _ = live_server
    oversized = b'{"tool":{"name":"big","description":"' + (b"x" * (MAX_BODY_BYTES + 256)) + b'"}}'
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.putrequest("POST", "/api/minify")
        conn.putheader("Host", f"127.0.0.1:{port}")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(len(oversized)))
        conn.endheaders()
        try:
            conn.send(oversized)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Server legitimately rejected oversized Content-Length early
        resp = conn.getresponse()
        body = resp.read()
        assert resp.status == 413
        assert "max_bytes" in json.loads(body.decode("utf-8"))
    finally:
        conn.close()


def test_malformed_json_returns_400(live_server):
    _, port, _ = live_server
    status, _, body = _raw_http(
        port, "POST", "/api/minify", headers={"Content-Type": "application/json"}, body=b"{bad json"
    )
    assert status == 400
    assert "error" in json.loads(body.decode("utf-8"))


def test_invalid_limit_returns_400_and_valid_clamped(live_server):
    _, port, _ = live_server
    for bad in ("notanint", "-5", "0"):
        status, _, body = _raw_http(port, "GET", f"/api/traffic?limit={bad}")
        assert status == 400, bad
        assert "error" in json.loads(body.decode("utf-8"))

    status, _, body = _raw_http(port, "GET", "/api/traffic?limit=999999")
    assert status == 200
    assert "frames" in json.loads(body.decode("utf-8"))


def test_unknown_api_routes_return_json_404(live_server):
    _, port, _ = live_server
    for method in ("GET", "POST"):
        status, hdrs, body = _raw_http(port, method, "/api/nonexistent")
        assert status == 404
        assert "application/json" in hdrs.get("content-type", "")
        assert "error" in json.loads(body.decode("utf-8"))


def test_chunked_post_body_supported(live_server):
    _, port, _ = live_server
    payload = json.dumps({
        "tool": {
            "name": "chunked_tool",
            "description": "Long description for chunked HTTP/1.1 test.\nExtra line.",
            "inputSchema": {"type": "object", "properties": {"x": {"type": "string", "examples": ["a"]}}},
        }
    }).encode("utf-8")
    chunked_wire = f"{len(payload):x}\r\n".encode("ascii") + payload + b"\r\n0\r\n\r\n"

    with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
        req = (
            f"POST /api/minify HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            f"Content-Type: application/json\r\n"
            f"Transfer-Encoding: chunked\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii") + chunked_wire
        sock.sendall(req)
        raw = b""
        while True:
            buf = sock.recv(4096)
            if not buf:
                break
            raw += buf

    head, _, body = raw.partition(b"\r\n\r\n")
    assert b"200 OK" in head
    data = json.loads(body.decode("utf-8"))
    assert data["success"] is True
    assert data["minified_schema"]["name"] == "chunked_tool"


def test_rest_replay_and_frame_endpoints(live_server):
    _, port, _ = live_server
    body = json.dumps({"tool_name": "sqlite_query_records", "arguments": {"query": "SELECT 1;"}}).encode("utf-8")
    status, _, resp = _raw_http(port, "POST", "/api/replay", {"Content-Type": "application/json"}, body)
    assert status == 200
    data = json.loads(resp.decode("utf-8"))
    assert data["success"] is True and data["tool"] == "sqlite_query_records"

    frame_body = json.dumps({
        "direction": "inbound",
        "raw_payload": json.dumps({"jsonrpc": "2.0", "id": 777, "method": "test/tap"}),
    }).encode("utf-8")
    status, _, resp = _raw_http(port, "POST", "/api/frame", {"Content-Type": "application/json"}, frame_body)
    assert status == 200
    assert json.loads(resp.decode("utf-8"))["status"] == "recorded"


def test_discovery_manifests_served(live_server):
    _, port, _ = live_server
    s1, _, b1 = _raw_http(port, "GET", "/llms.txt")
    assert s1 == 200 and b"mcp-lens mcp" in b1
    s2, _, b2 = _raw_http(port, "GET", "/.well-known/mcp.json")
    assert s2 == 200
    m = json.loads(b2.decode("utf-8"))
    assert m["version"] == "2.6.0" and m["toolCount"] == 6


# ---------------------------------------------------------------------------
# 4. CLI Status, Desktop, Server Entrypoint & Real Stdio MCP Server Tests
# ---------------------------------------------------------------------------

def test_cli_status_reads_discovered_tools_count(live_server, capsys):
    _, port, _ = live_server
    rc = cli_main(["status", "--port", str(port)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Discovered Tools:     5" in out


def test_cli_desktop_dry_run(capsys):
    rc = cli_main(["desktop", "--dry-run"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["service"] == "mcp-lens" and data["version"] == "2.6.0"


def test_server_py_accepts_optional_serve_arg():
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "server.py"), "serve", "--version"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert proc.returncode == 0
    assert "2.6.0" in (proc.stdout + proc.stderr)


def test_mcp_stdio_server_initialize_list_and_call():
    srv = MCPLensMCPServer(traffic_store=TrafficStore(maxlen=50))
    req_lines = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
        json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "mcp_audit_schema_tokens",
                "arguments": {
                    "schema": {
                        "name": "sample",
                        "description": "First line.\nSecond verbose line.",
                        "inputSchema": {"type": "object", "properties": {"a": {"type": "string", "examples": ["x"]}}},
                    }
                },
            },
        }),
        json.dumps({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "mcp_parse_frame", "arguments": {"raw_line": '{"jsonrpc":"2.0","id":7,"method":"ping"}'}},
        }),
        json.dumps({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "mcp_diagnostics", "arguments": {"port": 1}},
        }),
    ]) + "\n"

    out_buf = io.StringIO()
    rc = srv.serve_stdio(stdin=io.StringIO(req_lines), stdout=out_buf)
    assert rc == 0
    responses = [json.loads(line) for line in out_buf.getvalue().strip().splitlines()]
    assert len(responses) == 5

    assert responses[0]["result"]["serverInfo"]["name"] == "mcp-lens"
    assert responses[0]["result"]["serverInfo"]["version"] == "2.6.0"

    tool_names = [t["name"] for t in responses[1]["result"]["tools"]]
    assert len(tool_names) == 6
    assert "mcp_audit_schema_tokens" in tool_names
    assert "mcp_minify_schema" in tool_names
    assert "mcp_diagnostics" in tool_names

    audit_res = json.loads(responses[2]["result"]["content"][0]["text"])
    assert audit_res["raw_tokens"] >= audit_res["minified_tokens"]

    parse_res = json.loads(responses[3]["result"]["content"][0]["text"])
    assert parse_res["valid"] is True and parse_res["meta"]["method"] == "ping"

    diag_res = json.loads(responses[4]["result"]["content"][0]["text"])
    assert diag_res["version"] == "2.6.0" and diag_res["tool_count"] == 6


# ---------------------------------------------------------------------------
# 5. Frontend Static Security & Hygiene Invariants (Zero XSS / Zero CDN)
# ---------------------------------------------------------------------------

def test_frontend_zero_innerhtml_and_zero_cdn():
    engine_js = (REPO_ROOT / "public" / "lens_engine.js").read_text(encoding="utf-8")
    assert ".innerHTML" not in engine_js, "lens_engine.js must not use innerHTML sinks"
    assert "closePaywallModal" not in engine_js
    assert "Math.random" not in engine_js

    index_html = (REPO_ROOT / "public" / "index.html").read_text(encoding="utf-8")
    assert "cdn.tailwindcss.com" not in index_html
    assert "fonts.googleapis.com" not in index_html
    assert "fonts.gstatic.com" not in index_html
    assert 'id="hero-aperture-canvas"' in index_html
    assert 'aria-label="Search traffic waterfall' in index_html
    assert "onclick=" not in index_html
