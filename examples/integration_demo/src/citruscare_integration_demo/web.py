"""Loopback-only web playground for the synthetic consumer integration demo."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from typing import Any

from citruscare_integration_demo.demo import run_demo

_CONTENT_TYPES = {
    "/": ("static/index.html", "text/html; charset=utf-8"),
    "/assets/app.css": ("static/app.css", "text/css; charset=utf-8"),
    "/assets/app.js": ("static/app.js", "text/javascript; charset=utf-8"),
}
_MAX_REQUEST_BYTES = 1024
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'self'; script-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _require_loopback(host: str) -> None:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("host must be a loopback IP address") from exc
    if not address.is_loopback:
        raise ValueError("the demo web server may only bind to a loopback address")


def create_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Create a local-only server instance, suitable for CLI use and tests."""
    _require_loopback(host)
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")

    class PlaygroundHandler(BaseHTTPRequestHandler):
        server_version = "CitrusCarePlayground/0.1"
        sys_version = ""

        def send_error(
            self,
            code: int,
            message: str | None = None,
            explain: str | None = None,
        ) -> None:
            del message, explain
            try:
                status = HTTPStatus(code)
            except ValueError:
                status = HTTPStatus.INTERNAL_SERVER_ERROR
            self._send_json(status, {"error": status.phrase})

        def do_GET(self) -> None:
            if self.path in _CONTENT_TYPES:
                resource_name, content_type = _CONTENT_TYPES[self.path]
                body = (
                    files("citruscare_integration_demo")
                    .joinpath(*resource_name.split("/"))
                    .read_bytes()
                )
                self._send(HTTPStatus.OK, content_type, body)
                return
            if self.path == "/api/health":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "mode": "synthetic_local_demo",
                        "sdk_version": self._sdk_version(),
                    },
                )
                return
            self._send_json(
                HTTPStatus.NOT_FOUND, {"error": "No playground route at this path"}
            )

        def do_POST(self) -> None:
            if self.path != "/api/demo":
                self._send_json(
                    HTTPStatus.NOT_FOUND, {"error": "No playground route at this path"}
                )
                return
            content_length = self.headers.get("Content-Length", "0")
            try:
                request_bytes = int(content_length)
            except ValueError:
                self._send_json(
                    HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length"}
                )
                return
            if request_bytes < 0 or request_bytes > _MAX_REQUEST_BYTES:
                self._send_json(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"error": "Request body is too large"},
                )
                return
            if request_bytes:
                self.rfile.read(request_bytes)
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "error": (
                            "This synthetic demo accepts no user-provided data. "
                            "Send an empty POST request."
                        )
                    },
                )
                return
            try:
                self._send_json(HTTPStatus.OK, run_demo())
            except Exception as exc:
                print(
                    f"Playground demo failed ({type(exc).__name__}): {exc}",
                    file=sys.stderr,
                )
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {
                        "error": "The synthetic demo failed; check the server output.",
                        "error_type": type(exc).__name__,
                    },
                )

        def do_HEAD(self) -> None:
            self._send(HTTPStatus.METHOD_NOT_ALLOWED, "text/plain; charset=utf-8", b"")

        def _send_json(self, status: HTTPStatus, value: dict[str, Any]) -> None:
            self._send(
                status,
                "application/json; charset=utf-8",
                json.dumps(value, separators=(",", ":")).encode("utf-8"),
            )

        def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for name, value in _SECURITY_HEADERS.items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        @staticmethod
        def _sdk_version() -> str:
            try:
                return version("citruscare-sdk")
            except PackageNotFoundError:
                return "unknown"

        def log_message(self, format: str, *args: Any) -> None:
            del format, args

    return ThreadingHTTPServer((host, port), PlaygroundHandler)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = create_server(host, port)
    print(f"CitrusCare SDK playground: http://{host}:{server.server_port}/")
    print("Loopback only; synthetic data only; no AI model or patient data.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping CitrusCare SDK playground.")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="loopback IP to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="TCP port to bind (default: 8765; use 0 for an ephemeral port)",
    )
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
