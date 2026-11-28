"""Only exact-port loopback pages may call this server from a browser (CSRF / cross-site read guard)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from mcp_lens.server import _is_local_origin, _is_valid_host


class TestOriginGuard(unittest.TestCase):
    def test_allowed_origins(self):
        for o in (
            None,
            "",
            "http://127.0.0.1:8109",
            "http://localhost:8109",
            "http://[::1]:8109",
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ):
            self.assertTrue(_is_local_origin(o, active_port=8109), o)

    def test_blocked_origins(self):
        for o in (
            "https://evil.example.invalid",
            "http://127.0.0.1:81090",
            "http://localhost:9999",
            "http://127.0.0.1:8000",
            "null",
            "http://127.0.0.1.evil.com",
            "file://",
            "chrome-extension://abc",
        ):
            self.assertFalse(_is_local_origin(o, active_port=8109), o)

    def test_host_validation(self):
        for h in ("127.0.0.1:8109", "localhost:8109", "[::1]:8109", "127.0.0.1", "localhost"):
            self.assertTrue(_is_valid_host(h, 8109), h)
        for h in ("evil.example.invalid", "127.0.0.1:9999", "localhost:81090", "", None):
            self.assertFalse(_is_valid_host(h, 8109), str(h))


if __name__ == "__main__":
    unittest.main()
