"""Comprehensive Unit and Integration Test Suite for MCP Lens.

Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
100% Python Standard Library + pytest. Zero external pip runtime dependencies.
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import pytest

from mcp_lens.analyzer import (
    MCPTrafficAnalyzer,
    SchemaMinifier,
    estimate_tokens,
)
from mcp_lens.proxy import GLOBAL_TRAFFIC, StdioProxy, TrafficStore
from mcp_lens.server import MCPLensServer


def test_token_estimator():
    """Verify BPE token weight heuristic accurately calculates tokens."""
    # Empty string
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0

    # Short phrase
    t1 = estimate_tokens("hello world")
    assert 2 <= t1 <= 4

    # Structured JSON
    sample_json = {"query": "SELECT * FROM users;", "limit": 100}
    t2 = estimate_tokens(sample_json)
    assert t2 >= 10

    # Class method alias
    assert MCPTrafficAnalyzer.estimate_tokens("test string") > 0


def test_json_rpc_parser():
    """Verify JSON-RPC 2.0 framing parser correctly classifies frames."""
    # Valid Request
    line = '{"jsonrpc": "2.0", "id": 42, "method": "tools/call", "params": {"name": "test"}}'
    parsed = MCPTrafficAnalyzer.parse_frame(line)
    assert parsed is not None
    assert parsed["jsonrpc"] == "2.0"
    assert parsed["id"] == 42
    assert parsed["method"] == "tools/call"

    # Categorization
    meta = MCPTrafficAnalyzer.categorize_frame(parsed)
    assert meta["is_valid_rpc"] is True
    assert meta["frame_type"] == "request"
    assert meta["primary_topic"] == "tools/call"
    assert meta["has_error"] is False
    assert meta["estimated_tokens"] > 0

    # Valid Response
    resp_line = '{"jsonrpc": "2.0", "id": 42, "result": {"content": [{"type": "text", "text": "ok"}]}}'
    resp_parsed = MCPTrafficAnalyzer.parse_frame(resp_line)
    resp_meta = MCPTrafficAnalyzer.categorize_frame(resp_parsed)
    assert resp_meta["frame_type"] == "response"
    assert resp_meta["primary_topic"] == "response"

    # Valid Error
    err_line = '{"jsonrpc": "2.0", "id": 43, "error": {"code": -32601, "message": "Method not found"}}'
    err_parsed = MCPTrafficAnalyzer.parse_frame(err_line)
    err_meta = MCPTrafficAnalyzer.categorize_frame(err_parsed)
    assert err_meta["frame_type"] == "error"
    assert err_meta["has_error"] is True
    assert err_meta["error_message"] == "Method not found"

    # Malformed lines
    assert MCPTrafficAnalyzer.parse_frame("not a json") is None
    assert MCPTrafficAnalyzer.parse_frame("{incomplete json") is None
    assert MCPTrafficAnalyzer.parse_frame("") is None


def test_schema_minifier():
    """Verify AST schema minifier strips redundant bloat while preserving typing."""
    bloated_tool = {
        "name": "enterprise_db_exec",
        "description": "Executes high-performance SQL transactions against PostgreSQL cluster.\n"
                       "This is an extensive multi-paragraph docstring detailing security best practices,\n"
                       "connection pooling, and failover replicas that burns context window tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql_query": {
                    "type": "string",
                    "description": "The target SQL statement with comprehensive parameter placeholders.",
                    "examples": ["SELECT id, email, created_at FROM production_users WHERE active = true LIMIT 50;"]
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "Connection timeout in milliseconds.",
                    "default": 5000
                }
            },
            "required": ["sql_query"]
        }
    }

    minified, orig_tokens, min_tokens = SchemaMinifier.minify_schema(bloated_tool)
    assert min_tokens < orig_tokens
    assert minified["name"] == "enterprise_db_exec"
    # Ensure types and required properties are intact
    props = minified["inputSchema"]["properties"]
    assert "sql_query" in props
    assert props["sql_query"]["type"] == "string"
    assert "timeout_ms" in props
    assert props["timeout_ms"]["type"] == "integer"
    assert minified["inputSchema"]["required"] == ["sql_query"]

    # Also test minify_tool_schema single return
    single_min = SchemaMinifier.minify_tool_schema(bloated_tool)
    assert single_min["name"] == bloated_tool["name"]


def test_tool_token_audit():
    """Verify audit_tool calculates savings and percentages properly."""
    tool = {
        "name": "read_logs",
        "description": "Reads application logs from disk.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Absolute path to log file."
                }
            },
            "required": ["filepath"]
        }
    }
    weight = MCPTrafficAnalyzer.audit_tool(tool)
    assert weight.name == "read_logs"
    assert weight.total_tokens >= weight.minified_tokens
    assert weight.tokens_saved >= 0

    batch = MCPTrafficAnalyzer.audit_tools_list([tool])
    assert batch["total_tools"] == 1
    assert batch["total_tokens_raw"] >= batch["total_tokens_minified"]


def test_traffic_store_ring_buffer():
    """Verify thread-safe ring buffer and subscriber queues in TrafficStore."""
    store = TrafficStore(maxlen=5)

    # Record 10 frames
    for i in range(10):
        raw = json.dumps({"jsonrpc": "2.0", "id": i, "method": f"test/method_{i}", "params": {}})
        store.record_frame("inbound", raw)

    assert store.total_frames == 10
    # Store bounded to maxlen=5
    recent = store.get_recent(limit=10)
    assert len(recent) == 5
    assert recent[-1]["meta"]["method"] == "test/method_9"

    # Subscriber queue
    q = store.add_subscriber()
    raw = json.dumps({"jsonrpc": "2.0", "id": 11, "method": "tools/list", "params": {}})
    store.record_frame("outbound", raw)
    frame = q.get(timeout=1.0)
    assert frame.meta["method"] == "tools/list"
    assert frame.direction == "outbound"
    store.remove_subscriber(q)


def test_stdio_proxy_passthrough():
    """Verify StdioProxy spawns child, taps frames, and forwards stdio cleanly."""
    import io
    store = TrafficStore(maxlen=50)

    # Python one-liner child process that reads one line and echoes JSON-RPC response
    child_script = (
        "import sys, json; "
        "line = sys.stdin.readline(); "
        "data = json.loads(line); "
        "sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': data['id'], 'result': 'pong'}) + '\\n'); "
        "sys.stdout.flush()"
    )

    req = json.dumps({"jsonrpc": "2.0", "id": 99, "method": "ping", "params": {}}) + "\n"
    stdin_mock = io.StringIO(req)
    stdout_mock = io.StringIO()

    proxy = StdioProxy(
        command=[sys.executable, "-c", child_script],
        traffic_store=store,
        remote_collector_url=None,
        stdin_stream=stdin_mock,
        stdout_stream=stdout_mock,
    )

    # Run proxy synchronously to completion
    code = proxy.start()
    assert code == 0

    # Verify frame was recorded in traffic store
    frames = store.get_recent(limit=10)
    assert len(frames) >= 1
    methods = [f["meta"].get("method") for f in frames if f.get("meta") and f["meta"].get("method")]
    assert "ping" in methods
    # Verify child stdout was written
    assert "pong" in stdout_mock.getvalue()


def test_http_rest_api():
    """Verify HTTP Server REST endpoints (/api/health, /api/stats, /api/traffic, /api/tools, /api/replay, /api/minify)."""
    # Start ephemeral server on high unassigned test port (e.g. 18109)
    test_port = 18109
    server = MCPLensServer(host="127.0.0.1", port=test_port)
    server.start(block=False)
    time.sleep(0.3)

    base = f"http://127.0.0.1:{test_port}"

    try:
        # 1. Health
        with urllib.request.urlopen(f"{base}/api/health", timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "healthy"
            assert data["service"] == "mcp-lens"

        # 2. Stats
        with urllib.request.urlopen(f"{base}/api/stats", timeout=2.0) as resp:
            assert resp.status == 200
            stats = json.loads(resp.read().decode("utf-8"))
            assert "total_frames" in stats
            assert "total_tokens" in stats
            assert stats["total_frames"] > 0

        # 3. Traffic
        with urllib.request.urlopen(f"{base}/api/traffic?limit=10", timeout=2.0) as resp:
            assert resp.status == 200
            traffic = json.loads(resp.read().decode("utf-8"))
            assert "frames" in traffic
            assert len(traffic["frames"]) > 0

        # 4. Tools
        with urllib.request.urlopen(f"{base}/api/tools", timeout=2.0) as resp:
            assert resp.status == 200
            tools = json.loads(resp.read().decode("utf-8"))
            assert "tools" in tools
            assert len(tools["tools"]) > 0

        # 5. POST /api/minify
        sample_tool = {
            "name": "sample_compress_tool",
            "description": "Long redundant docstring for compression test.",
            "inputSchema": {"type": "object", "properties": {"arg": {"type": "string"}}}
        }
        req = urllib.request.Request(
            f"{base}/api/minify",
            data=json.dumps({"tool": sample_tool}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            assert resp.status == 200
            min_resp = json.loads(resp.read().decode("utf-8"))
            assert "minified_schema" in min_resp

        # 6. POST /api/replay
        replay_req = urllib.request.Request(
            f"{base}/api/replay",
            data=json.dumps({"tool_name": "sqlite_query_records", "arguments": {"database_path": "/tmp/test.db", "query": "SELECT 1;"}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(replay_req, timeout=2.0) as resp:
            assert resp.status == 200
            rep_resp = json.loads(resp.read().decode("utf-8"))
            assert rep_resp["success"] is True
            assert "response" in rep_resp

        # 7. POST /api/frame
        custom_frame = {
            "direction": "inbound",
            "raw_payload": json.dumps({"jsonrpc": "2.0", "id": 777, "method": "test/external_tap"})
        }
        frame_req = urllib.request.Request(
            f"{base}/api/frame",
            data=json.dumps(custom_frame).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(frame_req, timeout=2.0) as resp:
            assert resp.status == 200
            f_resp = json.loads(resp.read().decode("utf-8"))
            assert f_resp["status"] == "recorded"
    finally:
        server.stop()
