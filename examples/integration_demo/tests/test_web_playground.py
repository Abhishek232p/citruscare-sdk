from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from citruscare_integration_demo.web import create_server


class PlaygroundServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = create_server(port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_serves_ui_assets_and_security_headers(self) -> None:
        with urlopen(f"{self.base_url}/", timeout=5) as response:
            html = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("CitrusCare SDK Playground", html)
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
            self.assertIn(
                "default-src 'self'",
                response.headers["Content-Security-Policy"],
            )
        with urlopen(f"{self.base_url}/assets/app.js", timeout=5) as response:
            self.assertIn("Run the integration demo", response.read().decode("utf-8"))

    def test_health_route_reports_installed_sdk_and_local_only_mode(self) -> None:
        with urlopen(f"{self.base_url}/api/health", timeout=5) as response:
            health = json.loads(response.read())
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["mode"], "synthetic_local_demo")
        self.assertNotEqual(health["sdk_version"], "unknown")

    def test_demo_route_executes_full_sdk_flow(self) -> None:
        request = Request(f"{self.base_url}/api/demo", method="POST")
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read())
        self.assertEqual(
            result["agent"]["content"], "Reference DEMO-REF-001 is active."
        )
        self.assertFalse(result["http_adapter"]["ai_generated"])
        self.assertEqual(
            result["handled_errors"]["provider_http_error"],
            "Provider returned HTTP 503",
        )

    def test_demo_rejects_user_supplied_request_data(self) -> None:
        request = Request(
            f"{self.base_url}/api/demo",
            data=b'{"prompt":"synthetic"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 400)
        error = json.loads(raised.exception.read())
        self.assertIn("accepts no user-provided data", error["error"])

    def test_unknown_route_and_method_return_errors(self) -> None:
        with self.assertRaises(HTTPError) as missing:
            urlopen(f"{self.base_url}/missing", timeout=5)
        self.assertEqual(missing.exception.code, 404)

        request = Request(f"{self.base_url}/api/demo", method="HEAD")
        with self.assertRaises(HTTPError) as method:
            urlopen(request, timeout=5)
        self.assertEqual(method.exception.code, 405)

        request = Request(
            f"{self.base_url}/api/demo",
            data=b"",
            method="PUT",
        )
        with self.assertRaises(HTTPError) as unsupported:
            urlopen(request, timeout=5)
        self.assertEqual(unsupported.exception.code, 501)
        self.assertIn(
            "X-Content-Type-Options",
            unsupported.exception.headers,
        )

    def test_server_refuses_to_bind_to_non_loopback_addresses(self) -> None:
        with self.assertRaisesRegex(ValueError, "loopback"):
            create_server(host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
