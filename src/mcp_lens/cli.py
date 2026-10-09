"""Command-Line Interface for MCP Lens.

Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
100% Python Standard Library — Zero External Dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import List, Optional

from .analyzer import MCPTrafficAnalyzer, SchemaMinifier
from .proxy import GLOBAL_TRAFFIC, StdioProxy
from .server import MCPLensServer


BANNER = r"""
 __  __  ____ ____    _     _____ _   _ ____  
|  \/  |/ ___|  _ \  | |   | ____| \ | / ___| 
| |\/| | |   | |_) | | |   |  _| |  \| \___ \ 
| |  | | |___|  __/  | |___| |___| |\  |___) |
|_|  |_|\____|_|     |_____|_____|_| \_|____/ 
   Zero-Dependency Model Context Protocol Traffic Sniffer
   Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform
"""


def cmd_serve(args: argparse.Namespace) -> int:
    """Run the standalone Web Cockpit & Telemetry Server."""
    print(BANNER)
    server = MCPLensServer(host=args.host, port=args.port)
    print(f"● Launching MCP Lens Web Cockpit on http://{args.host}:{args.port}")
    print("● Real-time SSE waterfall feed active on /api/events/stream")
    print("● Press Ctrl+C to terminate.")
    try:
        server.start(block=True)
    except KeyboardInterrupt:
        print("\n● MCP Lens gracefully shut down.")
    return 0


def cmd_proxy(args: argparse.Namespace, child_cmd: List[str]) -> int:
    """Run the transparent Stdio proxy wrapping a target MCP server."""
    if not child_cmd:
        sys.stderr.write("Error: No command specified to proxy.\n")
        sys.stderr.write("Usage: mcp-lens proxy [options] -- <command> [args...]\n")
        return 1

    server: Optional[MCPLensServer] = None
    if not args.no_server:
        # Start server in background thread so cockpit is immediately accessible
        server = MCPLensServer(host=args.host, port=args.port)
        server.start(block=False)
        sys.stderr.write(f"[mcp-lens] Web Cockpit active at http://{args.host}:{args.port}\n")
        sys.stderr.flush()

    sys.stderr.write(f"[mcp-lens] Proxying stdio for: {' '.join(child_cmd)}\n")
    sys.stderr.flush()

    proxy = StdioProxy(
        command=child_cmd,
        traffic_store=GLOBAL_TRAFFIC,
        remote_collector_url=f"http://127.0.0.1:{args.port}/api/frame" if not args.no_server else None,
    )
    code = proxy.start()

    if server:
        server.stop()
    return code


def cmd_status(args: argparse.Namespace) -> int:
    """Query and display live health and telemetry stats from running MCP Lens server."""
    url = f"http://{args.host}:{args.port}/api/stats"
    health_url = f"http://{args.host}:{args.port}/api/health"

    try:
        with urllib.request.urlopen(health_url, timeout=2.0) as resp:
            health = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error: Could not connect to MCP Lens server at http://{args.host}:{args.port} ({e})")
        return 1

    try:
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            stats = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error: Failed to fetch telemetry statistics ({e})")
        return 1

    print(BANNER)
    print(f"Service Status:       ONLINE ({health.get('status')})")
    print(f"Server Port:          {args.port}")
    print(f"Engine Uptime:        {health.get('uptime_seconds')}s")
    print("-" * 55)
    print(f"Total Tapped Frames:  {stats.get('total_frames', 0):,}")
    print(f"Total Bytes Streamed: {stats.get('total_bytes', 0):,} B")
    print(f"Discovered Tools:     {len(stats.get('tools', []))}")
    print(f"Cumulative Tokens:    {stats.get('total_tokens', 0):,}")
    print(f"Token Overhead (Raw): {stats.get('token_overhead', 0):,} tokens")
    print(f"Minified Potential:   {stats.get('potential_savings_tokens', 0):,} tokens saved ({stats.get('savings_percent', 0)}% reduction)")
    print("-" * 55)
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """Run internal self-tests for token calculations, minifier, and parser."""
    print("● Running MCP Lens internal diagnostics...")

    # Test 1: Parser
    sample_rpc = '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'
    parsed = MCPTrafficAnalyzer.parse_frame(sample_rpc)
    assert parsed is not None, "Failed to parse valid JSON-RPC frame"
    assert parsed.get("method") == "tools/list", "Method mismatch"
    print("  ✓ JSON-RPC 2.0 framing parser verified")

    # Test 2: BPE Token Estimator
    text = "SELECT * FROM users WHERE active = 1;"
    tokens = MCPTrafficAnalyzer.estimate_tokens(text)
    assert tokens > 0, "Token count must be positive"
    print(f"  ✓ BPE Token Heuristic verified ({len(text)} chars -> ~{tokens} tokens)")

    # Test 3: Minifier
    tool = {
        "name": "read_file",
        "description": "Reads entire file contents and returns markdown text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The exact absolute path on filesystem.",
                    "examples": ["/var/log/syslog"]
                }
            },
            "required": ["path"]
        }
    }
    raw_tokens = MCPTrafficAnalyzer.estimate_tokens(tool)
    minified = SchemaMinifier.minify_tool_schema(tool)
    min_tokens = MCPTrafficAnalyzer.estimate_tokens(minified)
    assert min_tokens <= raw_tokens, "Minified tokens must be <= raw tokens"
    saved = raw_tokens - min_tokens
    print(f"  ✓ Schema Minification verified (Raw: {raw_tokens} tokens -> Minified: {min_tokens} tokens, Saved: {saved})")

    print("\nAll MCP Lens internal diagnostics passed successfully.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for mcp-lens CLI."""
    if argv is None:
        argv = sys.argv[1:]

    # Handle direct proxy shorthand: mcp-lens -- <command> ...
    if "--" in argv:
        split_idx = argv.index("--")
        pre_args = argv[:split_idx]
        post_args = argv[split_idx + 1 :]

        parser = argparse.ArgumentParser(description="MCP Lens - Zero-Dependency Model Context Protocol Traffic Sniffer")
        parser.add_argument("--port", type=int, default=8109, help="Web Cockpit port (default: 8109)")
        parser.add_argument("--host", default="0.0.0.0", help="Web Cockpit host (default: 0.0.0.0)")
        parser.add_argument("--no-server", action="store_true", help="Disable embedded Web Cockpit HTTP server")
        parsed = parser.parse_args(pre_args)
        return cmd_proxy(parsed, post_args)

    parser = argparse.ArgumentParser(
        prog="mcp-lens",
        description="MCP Lens - Zero-Dependency Model Context Protocol Traffic Sniffer & Schema Auditor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mcp-lens serve --port 8109
  mcp-lens proxy -- python my_mcp_server.py
  mcp-lens -- npx -y @modelcontextprotocol/server-filesystem /tmp
  mcp-lens status --port 8109
  mcp-lens test
        """
    )
    parser.add_argument("-v", "--version", action="version", version="mcp-lens 1.0.0")

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # serve
    p_serve = subparsers.add_parser("serve", help="Run the Web Cockpit and Telemetry server")
    p_serve.add_argument("--port", type=int, default=8109, help="Port to bind (default: 8109)")
    p_serve.add_argument("--host", default="0.0.0.0", help="Host interface (default: 0.0.0.0)")

    # proxy
    p_proxy = subparsers.add_parser("proxy", help="Transparently proxy stdio for a child MCP server")
    p_proxy.add_argument("--port", type=int, default=8109, help="Web Cockpit port (default: 8109)")
    p_proxy.add_argument("--host", default="0.0.0.0", help="Web Cockpit host (default: 0.0.0.0)")
    p_proxy.add_argument("--no-server", action="store_true", help="Disable embedded Web Cockpit HTTP server")
    p_proxy.add_argument("cmd", nargs=argparse.REMAINDER, help="Child MCP server command and arguments")

    # status
    p_status = subparsers.add_parser("status", help="Inspect status and metrics of running MCP Lens")
    p_status.add_argument("--port", type=int, default=8109, help="Server port (default: 8109)")
    p_status.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")

    # test
    p_test = subparsers.add_parser("test", help="Execute internal diagnostics and schema self-tests")

    args = parser.parse_args(argv)

    if args.subcommand == "serve":
        return cmd_serve(args)
    elif args.subcommand == "proxy":
        child_cmd = args.cmd
        if child_cmd and child_cmd[0] == "--":
            child_cmd = child_cmd[1:]
        return cmd_proxy(args, child_cmd)
    elif args.subcommand == "status":
        return cmd_status(args)
    elif args.subcommand == "test":
        return cmd_test(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
