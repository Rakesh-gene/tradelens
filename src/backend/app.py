"""Small dependency-free HTTP API for the TradeLens application."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

HOST = "127.0.0.1"
PORT = 9004


class ApiHandler(BaseHTTPRequestHandler):
    """Serve the application's JSON API."""

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", maxsplit=1)[0].rstrip("/") or "/"
        if path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {"status": "ok", "service": "tradelens-backend"},
            )
            return
        if path == "/":
            self._send_json(
                HTTPStatus.OK,
                {"message": "TradeLens backend", "health": "/api/health"},
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def create_server(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    """Create the backend server, allowing tests to use an ephemeral port."""
    return ThreadingHTTPServer((host, port), ApiHandler)


def main() -> None:
    server = create_server()
    print(f"TradeLens backend listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping backend")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
