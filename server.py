#!/usr/bin/env python3
"""MCP Lens - Standalone Web Cockpit & Telemetry Server.

Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
100% Python Standard Library — Zero External Dependencies.
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure src/ is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(SCRIPT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from mcp_lens.server import MCPLensServer


def main():
    parser = argparse.ArgumentParser(description="MCP Lens Web Cockpit & Telemetry Server")
    parser.add_argument("--port", type=int, default=8109, help="Port to listen on (default: 8109)")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    args = parser.parse_args()

    public_dir = os.path.join(SCRIPT_DIR, "public")
    server = MCPLensServer(host=args.host, port=args.port, public_dir=public_dir)
    print(f"● MCP Lens Server listening on http://{args.host}:{args.port}")
    try:
        server.start(block=True)
    except KeyboardInterrupt:
        server.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
