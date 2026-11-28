"""Real Stdio JSON-RPC 2.0 Model Context Protocol (MCP) Server for MCP Lens.

Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
100% Python Standard Library — Zero External Dependencies.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any, Dict, List, Optional, TextIO, Tuple

from . import __version__
from .analyzer import MCPTrafficAnalyzer, SchemaMinifier
from .proxy import GLOBAL_TRAFFIC, TrafficStore
from .server import SAMPLE_MCP_TOOLS, seed_sample_traffic

PROTOCOL_VERSION = "2024-11-05"

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "mcp_audit_schema_tokens",
        "description": "Audit one or more MCP tool schemas for raw vs minified BPE token weights and savings percentage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "schema": {"type": "object", "description": "Single MCP tool definition object"},
                "tools": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Optional array of MCP tool definitions to batch audit",
                },
            },
        },
    },
    {
        "name": "mcp_minify_schema",
        "description": "Minify an MCP tool JSON schema while preserving parameter types, required keys, and enums.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool": {"type": "object", "description": "Raw MCP tool definition object"},
            },
            "required": ["tool"],
        },
    },
    {
        "name": "mcp_parse_frame",
        "description": "Parse and categorize a raw JSON-RPC 2.0 frame string with byte size and BPE token estimate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "raw_line": {"type": "string", "description": "Raw JSON-RPC 2.0 JSON line"},
            },
            "required": ["raw_line"],
        },
    },
    {
        "name": "mcp_get_traffic",
        "description": "Return recent captured MCP JSON-RPC 2.0 frames from live :8109 daemon or local store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max frames to return (1-1000)", "default": 25},
                "topic": {"type": "string", "description": "Optional method/topic filter (e.g. tools/call)"},
                "port": {"type": "integer", "description": "Local MCP Lens HTTP port (default 8109)", "default": 8109},
            },
        },
    },
    {
        "name": "mcp_replay_tool",
        "description": "Replay or simulate a JSON-RPC 2.0 tools/call payload via live :8109 or deterministic in-process simulator.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Target MCP tool name"},
                "arguments": {"type": "object", "description": "Tool arguments object"},
                "port": {"type": "integer", "description": "Local MCP Lens HTTP port (default 8109)", "default": 8109},
            },
            "required": ["tool_name"],
        },
    },
    {
        "name": "mcp_diagnostics",
        "description": "Return MCP Lens version, engine self-checks, and live loopback :8109 daemon reachability.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "description": "Local MCP Lens HTTP port (default 8109)", "default": 8109},
            },
        },
    },
]


def _try_http_json(url: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
    try:
        if payload is not None:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        else:
            req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


class MCPLensMCPServer:
    """Zero-dependency stdio JSON-RPC 2.0 MCP server."""

    def __init__(self, traffic_store: Optional[TrafficStore] = None):
        self.traffic = traffic_store or GLOBAL_TRAFFIC
        seed_sample_traffic(self.traffic)

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        if name == "mcp_audit_schema_tokens":
            tools = arguments.get("tools")
            single = arguments.get("schema") or arguments.get("tool")
            if isinstance(tools, list) and tools:
                return MCPTrafficAnalyzer.audit_tools_list(tools), False
            if isinstance(single, dict) and single:
                w = MCPTrafficAnalyzer.audit_tool(single)
                return {
                    "name": w.name,
                    "raw_tokens": w.total_tokens,
                    "minified_tokens": w.minified_tokens,
                    "tokens_saved": w.tokens_saved,
                    "savings_percent": w.savings_percent,
                    "minified_schema": w.minified_schema,
                }, False
            return MCPTrafficAnalyzer.audit_tools_list(SAMPLE_MCP_TOOLS), False

        if name == "mcp_minify_schema":
            tool = arguments.get("tool") or arguments.get("schema")
            if not isinstance(tool, dict):
                return {"error": "Missing or invalid 'tool' object"}, True
            minified, orig_tok, min_tok = SchemaMinifier.minify_schema(tool)
            saved = max(0, orig_tok - min_tok)
            pct = round((saved / orig_tok) * 100.0, 1) if orig_tok > 0 else 0.0
            return {
                "original_tokens": orig_tok,
                "minified_tokens": min_tok,
                "tokens_saved": saved,
                "savings_percent": pct,
                "minified_schema": minified,
            }, False

        if name == "mcp_parse_frame":
            raw_line = arguments.get("raw_line", "")
            if not isinstance(raw_line, str) or not raw_line.strip():
                return {"error": "Missing non-empty 'raw_line' string"}, True
            parsed = MCPTrafficAnalyzer.parse_frame(raw_line)
            if parsed is None:
                return {"valid": False, "error": "Input is not a valid JSON object"}, False
            meta = MCPTrafficAnalyzer.categorize_frame(parsed)
            return {"valid": True, "parsed": parsed, "meta": meta}, False

        if name == "mcp_get_traffic":
            limit = max(1, min(int(arguments.get("limit", 25)), 1000))
            topic = arguments.get("topic")
            port = int(arguments.get("port", 8109))
            query = f"?limit={limit}" + (f"&topic={topic}" if topic else "")
            live = _try_http_json(f"http://127.0.0.1:{port}/api/traffic{query}")
            if live is not None:
                live["source"] = f"http://127.0.0.1:{port}"
                return live, False
            frames = self.traffic.get_recent(limit=limit, method_filter=topic)
            return {"source": "in-process", "count": len(frames), "frames": frames}, False

        if name == "mcp_replay_tool":
            tool_name = str(arguments.get("tool_name") or "").strip()
            if not tool_name:
                return {"error": "Missing required 'tool_name'"}, True
            tool_args = arguments.get("arguments", {})
            if not isinstance(tool_args, dict):
                return {"error": "'arguments' must be an object"}, True
            port = int(arguments.get("port", 8109))
            live = _try_http_json(
                f"http://127.0.0.1:{port}/api/replay",
                payload={"tool_name": tool_name, "arguments": tool_args},
            )
            if live is not None:
                live["source"] = f"http://127.0.0.1:{port}"
                return live, False
            rpc = {
                "jsonrpc": "2.0",
                "id": "mcp_replay_local",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": tool_args},
            }
            self.traffic.record_frame("inbound", json.dumps(rpc))
            return {
                "source": "in-process",
                "success": True,
                "tool": tool_name,
                "arguments": tool_args,
                "request_tokens": MCPTrafficAnalyzer.estimate_tokens(rpc),
            }, False

        if name == "mcp_diagnostics":
            port = int(arguments.get("port", 8109))
            health = _try_http_json(f"http://127.0.0.1:{port}/api/health")
            return {
                "service": "mcp-lens",
                "version": __version__,
                "protocolVersion": PROTOCOL_VERSION,
                "tool_count": len(MCP_TOOLS),
                "tools": [t["name"] for t in MCP_TOOLS],
                "daemon_online": health is not None,
                "daemon_health": health,
                "author": "Neal Frazier Tech (@1nc0gn30) • NullAI Platform",
            }, False

        return {"error": f"Unknown tool: {name}"}, True

    def handle_request(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        req_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}

        # Notifications have no id and require no response
        if req_id is None and method and method.startswith("notifications/"):
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": "mcp-lens",
                        "version": __version__,
                    },
                },
            }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": MCP_TOOLS},
            }

        if method == "tools/call":
            if not isinstance(params, dict) or not params.get("name"):
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Invalid params: 'name' is required"},
                }
            tool_name = str(params["name"])
            tool_args = params.get("arguments") or {}
            if not isinstance(tool_args, dict):
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Invalid params: 'arguments' must be an object"},
                }
            result_obj, is_error = self.call_tool(tool_name, tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result_obj, indent=2)}],
                    "isError": is_error,
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def serve_stdio(self, stdin: Optional[TextIO] = None, stdout: Optional[TextIO] = None) -> int:
        in_stream = stdin if stdin is not None else sys.stdin
        out_stream = stdout if stdout is not None else sys.stdout

        for raw_line in in_stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception as exc:
                err = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                }
                out_stream.write(json.dumps(err) + "\n")
                out_stream.flush()
                continue

            if not isinstance(msg, dict):
                err = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Invalid Request"},
                }
                out_stream.write(json.dumps(err) + "\n")
                out_stream.flush()
                continue

            resp = self.handle_request(msg)
            if resp is not None:
                out_stream.write(json.dumps(resp) + "\n")
                out_stream.flush()

        return 0


def run_mcp_stdio_server() -> int:
    server = MCPLensMCPServer()
    return server.serve_stdio()
