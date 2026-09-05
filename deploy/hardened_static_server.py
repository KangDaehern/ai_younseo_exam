"""Minimal allow-listed HTTP server for the Yunseo study pages."""

from __future__ import annotations

import argparse
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class StudyHandler(BaseHTTPRequestHandler):
    server_version = "StudyServer"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802
        self._serve(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._serve(send_body=False)

    def do_POST(self) -> None:  # noqa: N802
        self.send_error(405, "Method not allowed")

    def _serve(self, *, send_body: bool) -> None:
        request_path = unquote(urlsplit(self.path).path)
        prefix = f"/{self.server.access_token}/"  # type: ignore[attr-defined]
        if not request_path.startswith(prefix):
            self.send_error(404, "Not found")
            return

        relative_path = request_path[len(prefix) :]
        if relative_path in ("", "index.html"):
            filename = "index.html"
        elif relative_path == "01_fallacy-of-composition.html":
            filename = relative_path
        else:
            self.send_error(404, "Not found")
            return

        web_root: Path = self.server.web_root  # type: ignore[attr-defined]
        file_path = web_root / filename
        try:
            payload = file_path.read_bytes()
        except OSError:
            self.send_error(404, "Not found")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'unsafe-inline'; "
            "style-src 'unsafe-inline'; img-src data:; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        if send_body:
            self.wfile.write(payload)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        safe_message = html.escape(message or "Error")
        payload = f"<!doctype html><title>{code}</title><h1>{code} {safe_message}</h1>".encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        # Keep normal access logs but never print the token-bearing request path.
        print(f'{self.address_string()} - {self.command} - {args[1]}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--web-root", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    args = parser.parse_args()

    token = args.token_file.read_text(encoding="ascii").strip()
    if len(token) != 32 or any(character not in "0123456789abcdef" for character in token):
        raise ValueError("Access token must be exactly 32 lowercase hexadecimal characters")

    server = ThreadingHTTPServer(("0.0.0.0", args.port), StudyHandler)
    server.web_root = args.web_root.resolve()
    server.access_token = token
    server.serve_forever()


if __name__ == "__main__":
    main()
