"""Command-Line Interface for MCP Lens.

Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
100% Python Standard Library — Zero External Dependencies.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from typing import List, Optional

from . import __version__
from .analyzer import MCPTrafficAnalyzer, SchemaMinifier
from .mcp_server import run_mcp_stdio_server
from .proxy import GLOBAL_TRAFFIC, StdioProxy
from .server import MCPLensServer


def _default_bind_host() -> str:
    """Bind address: localhost unless explicitly opted in via $ZOTH_BIND_HOST or
    $HOST (IP literal only; zsh sets HOST to the hostname) or --host."""
    for var in ("ZOTH_BIND_HOST", "HOST"):
        val = os.environ.get(var, "").strip()
        if val == "localhost":
            return "127.0.0.1"
        if val:
            try:
                ipaddress.ip_address(val)
                return val
            except ValueError:
                pass
    return "127.0.0.1"


BANNER = f"""
 __  __  ____ ____    _     _____ _   _ ____
|  \\/  |/ ___|  _ \\  | |   | ____| \\ | / ___|
| |\\/| | |   | |_) | | |   |  _| |  \\| \\___ \\
| |  | | |___|  __/  | |___| |___| |\\  |___) |
|_|  |_|\\____|_|     |_____|_____|_| \\_|____/
   Zero-Dependency Model Context Protocol Traffic Sniffer (v{__version__})
   Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform
"""


def _resolve_project_root() -> str:
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(pkg_dir))


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
        server = MCPLensServer(host=args.host, port=args.port)
        server.start(block=False)
        sys.stderr.write(f"[mcp-lens] Web Cockpit active at http://{args.host}:{args.port}\n")
        sys.stderr.flush()

    sys.stderr.write(f"[mcp-lens] Proxying stdio for: {' '.join(child_cmd)}\n")
    sys.stderr.flush()

    # When running embedded server, GLOBAL_TRAFFIC is shared in-process; do not
    # double-record by POSTing back to the same process's /api/frame endpoint.
    proxy = StdioProxy(
        command=child_cmd,
        traffic_store=GLOBAL_TRAFFIC if not args.no_server else None,
        remote_collector_url=f"http://127.0.0.1:{args.port}/api/frame" if args.no_server else None,
    )
    code = proxy.start()

    if server:
        server.stop()
    return code


def cmd_status(args: argparse.Namespace) -> int:
    """Query and display live health and telemetry stats from running MCP Lens server."""
    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8109)
    url = f"http://{host}:{port}/api/stats"
    health_url = f"http://{host}:{port}/api/health"

    health = {}
    stats = {}
    online = True

    try:
        with urllib.request.urlopen(health_url, timeout=2.0) as resp:
            health = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        online = False
        health = {"status": "offline", "error": str(e)}

    if online:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                stats = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            stats = {"error": str(e)}

    if getattr(args, "json", False):
        print(json.dumps({
            "service": "mcp-lens",
            "version": __version__,
            "online": online,
            "port": port,
            "host": host,
            "health": health,
            "stats": stats,
            "license": "100% Free & Open Access (Zero Paywalls)",
            "author": "Neal Frazier Tech (@1nc0gn30) • NullAI Platform",
            "support": {
                "stripe": "https://buy.stripe.com/3cIfZg27PdKo2D64Ocfw40X",
                "solana": "GG2eQbVh8ut1BK6j1A2tz7pSySdLpD38BgyEhGcxdXoK",
            },
        }, indent=2))
        return 0

    if not online:
        print(f"Error: Could not connect to MCP Lens server at http://{host}:{port} ({health.get('error')})")
        return 1

    print(BANNER)
    print(f"Service Status:       ONLINE ({health.get('status')})")
    print(f"Server Port:          {port}")
    print(f"Engine Version:       {health.get('version', __version__)}")
    print(f"Engine Uptime:        {health.get('uptime_seconds')}s")
    print("-" * 55)
    print(f"Total Tapped Frames:  {stats.get('total_frames', 0):,}")
    print(f"Total Bytes Streamed: {stats.get('total_bytes', 0):,} B")
    print(f"Discovered Tools:     {stats.get('discovered_tools_count', 0)}")
    print(f"Cumulative Tokens:    {stats.get('total_tokens', 0):,}")
    print(f"Token Overhead (Raw): {stats.get('token_overhead', 0):,} tokens")
    print(f"Minified Potential:   {stats.get('potential_savings_tokens', 0):,} tokens saved ({stats.get('savings_percent', 0)}% reduction)")
    print("-" * 55)
    return 0


def cmd_desktop(args: argparse.Namespace) -> int:
    """Launch MCP Lens desktop workstation (Electron wrapper or local browser)."""
    root = _resolve_project_root()
    electron_main = os.path.join(root, "electron", "main.cjs")
    electron_bin = shutil.which("electron")
    url = f"http://{args.host}:{args.port}"

    if getattr(args, "dry_run", False):
        mode = "electron" if (electron_bin and os.path.isfile(electron_main)) else "browser"
        print(json.dumps({
            "service": "mcp-lens",
            "version": __version__,
            "mode": mode,
            "url": url,
            "electron_available": bool(electron_bin and os.path.isfile(electron_main)),
        }, indent=2))
        return 0

    if electron_bin and os.path.isfile(electron_main) and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        env = os.environ.copy()
        env["PORT"] = str(args.port)
        return subprocess.call([electron_bin, electron_main], cwd=root, env=env)

    # Headless or no Electron binary: ensure server is reachable or start it
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=0.8):
            online = True
    except Exception:
        online = False

    if not online:
        server = MCPLensServer(host=args.host, port=args.port)
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            server.start(block=False)
            opener = shutil.which("xdg-open")
            if opener:
                subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                server.thread.join()  # type: ignore[union-attr]
            except KeyboardInterrupt:
                server.stop()
            return 0
        server.start(block=True)
        return 0

    opener = shutil.which("xdg-open")
    if opener and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print(f"● MCP Lens Web Cockpit ready at {url}")
    return 0


def cmd_mcp(_args: argparse.Namespace) -> int:
    """Run the real stdio JSON-RPC 2.0 MCP server (6 tools)."""
    return run_mcp_stdio_server()


def cmd_test(_args: argparse.Namespace) -> int:
    """Run internal self-tests for token calculations, minifier, and parser."""
    print(f"● Running MCP Lens v{__version__} internal diagnostics...")

    sample_rpc = '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'
    parsed = MCPTrafficAnalyzer.parse_frame(sample_rpc)
    assert parsed is not None, "Failed to parse valid JSON-RPC frame"
    assert parsed.get("method") == "tools/list", "Method mismatch"
    print("  ✓ JSON-RPC 2.0 framing parser verified")

    text = "SELECT * FROM users WHERE active = 1;"
    tokens = MCPTrafficAnalyzer.estimate_tokens(text)
    assert tokens > 0, "Token count must be positive"
    print(f"  ✓ BPE Token Heuristic verified ({len(text)} chars -> ~{tokens} tokens)")

    tool = {
        "name": "read_file",
        "description": "Reads entire file contents and returns markdown text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The exact absolute path on filesystem.",
                    "examples": ["/var/log/syslog"],
                }
            },
            "required": ["path"],
        },
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

        # If subcommand is explicitly 'proxy', strip it from pre_args
        if pre_args and pre_args[0] == "proxy":
            pre_args = pre_args[1:]

        parser = argparse.ArgumentParser(description="MCP Lens - Zero-Dependency Model Context Protocol Traffic Sniffer")
        parser.add_argument("--port", type=int, default=8109, help="Web Cockpit port (default: 8109)")
        parser.add_argument("--host", default=_default_bind_host(), help="Host interface (default: 127.0.0.1 or $ZOTH_BIND_HOST)")
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
  mcp-lens proxy -- python3 my_mcp_server.py
  mcp-lens -- npx -y @modelcontextprotocol/server-filesystem /tmp
  mcp-lens mcp
  mcp-lens desktop
  mcp-lens status --port 8109 --json
  mcp-lens test
        """,
    )
    parser.add_argument("-v", "--version", action="version", version=f"mcp-lens {__version__}")
    parser.add_argument("--status", action="store_true", help="Query status of local MCP Lens instance")
    parser.add_argument("--json", action="store_true", help="Output status/telemetry in structured JSON")
    parser.add_argument("--port", type=int, default=8109, help="Server port (default: 8109)")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    p_serve = subparsers.add_parser("serve", help="Run the Web Cockpit and Telemetry server")
    p_serve.add_argument("--port", type=int, default=8109, help="Port to bind (default: 8109)")
    p_serve.add_argument("--host", default=_default_bind_host(), help="Host interface (default: 127.0.0.1 or $ZOTH_BIND_HOST)")

    p_proxy = subparsers.add_parser("proxy", help="Transparently proxy stdio for a child MCP server")
    p_proxy.add_argument("--port", type=int, default=8109, help="Web Cockpit port (default: 8109)")
    p_proxy.add_argument("--host", default=_default_bind_host(), help="Host interface (default: 127.0.0.1 or $ZOTH_BIND_HOST)")
    p_proxy.add_argument("--no-server", action="store_true", help="Disable embedded Web Cockpit HTTP server")
    p_proxy.add_argument("cmd", nargs=argparse.REMAINDER, help="Child MCP server command and arguments")

    p_status = subparsers.add_parser("status", help="Inspect status and metrics of running MCP Lens")
    p_status.add_argument("--port", type=int, default=8109, help="Server port (default: 8109)")
    p_status.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    p_status.add_argument("--json", action="store_true", help="Output status in structured JSON format")

    subparsers.add_parser("mcp", help="Run stdio JSON-RPC 2.0 MCP server (6 tools)")

    p_desktop = subparsers.add_parser("desktop", help="Launch MCP Lens desktop workstation")
    p_desktop.add_argument("--port", type=int, default=8109, help="Server port (default: 8109)")
    p_desktop.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    p_desktop.add_argument("--dry-run", action="store_true", help="Print resolved launch mode JSON and exit")

    subparsers.add_parser("test", help="Execute internal diagnostics and schema self-tests")

    args = parser.parse_args(argv)

    if (getattr(args, "status", False) or getattr(args, "json", False)) and not args.subcommand:
        return cmd_status(args)

    if args.subcommand == "serve":
        return cmd_serve(args)
    if args.subcommand == "proxy":
        child_cmd = args.cmd
        if child_cmd and child_cmd[0] == "--":
            child_cmd = child_cmd[1:]
        return cmd_proxy(args, child_cmd)
    if args.subcommand == "status":
        return cmd_status(args)
    if args.subcommand == "mcp":
        return cmd_mcp(args)
    if args.subcommand == "desktop":
        return cmd_desktop(args)
    if args.subcommand == "test":
        return cmd_test(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
