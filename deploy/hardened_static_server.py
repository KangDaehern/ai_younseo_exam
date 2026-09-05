"""Minimal allow-listed HTTP server for the Yunseo study pages."""

from __future__ import annotations

import argparse
import html
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class StudyHandler(BaseHTTPRequestHandler):
    server_version = "StudyServer"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802
        if self._state_route() is not None:
            self._get_state()
        else:
            self._serve(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._serve(send_body=False)

    def do_POST(self) -> None:  # noqa: N802
        if self._state_route() is None:
            self.send_error(404, "Not found")
            return
        self._save_state()

    def _state_route(self) -> tuple[str, str] | None:
        request_path = unquote(urlsplit(self.path).path)
        prefix = f"/{self.server.access_token}/api/state/"  # type: ignore[attr-defined]
        if not request_path.startswith(prefix):
            return None
        parts = request_path[len(prefix) :].strip("/").split("/")
        if len(parts) != 2 or not re.fullmatch(r"(?:0[1-9]|[12][0-9]|30)", parts[0]) or parts[1] not in {"test", "yunseo"}:
            return None
        return parts[0], parts[1]

    def _state_file(self) -> Path:
        passage, profile = self._state_route() or ("", "")
        return self.server.state_dir / f"{passage}-{profile}.json"  # type: ignore[attr-defined]

    def _get_state(self) -> None:
        state_file = self._state_file()
        with self.server.state_lock:  # type: ignore[attr-defined]
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {"version": 1, "known": {}, "unknown": {}, "quiz": {}, "hiddenSentences": {}, "readingMode": "easy"}
        self._send_json(200, data)

    def _save_state(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid content length")
            return
        if length < 2 or length > 100_000:
            self.send_error(413, "Invalid state size")
            return
        try:
            incoming = json.loads(self.rfile.read(length).decode("utf-8"))
            data = self._sanitize_state(incoming)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            self.send_error(400, "Invalid state")
            return

        state_file = self._state_file()
        temporary = state_file.with_suffix(".tmp")
        with self.server.state_lock:  # type: ignore[attr-defined]
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(state_file)
        self._send_json(200, {"saved": True})

    @staticmethod
    def _sanitize_state(incoming: object) -> dict[str, object]:
        if not isinstance(incoming, dict):
            raise ValueError("State must be an object")

        def boolean_map(name: str, max_items: int) -> dict[str, bool]:
            value = incoming.get(name, {})
            if not isinstance(value, dict) or len(value) > max_items:
                raise ValueError(f"Invalid {name}")
            return {str(key)[:100]: bool(item) for key, item in value.items() if bool(item)}

        quiz_value = incoming.get("quiz", {})
        if not isinstance(quiz_value, dict) or len(quiz_value) > 50:
            raise ValueError("Invalid quiz")
        quiz: dict[str, dict[str, object]] = {}
        for key, item in quiz_value.items():
            if not isinstance(item, dict):
                continue
            selected = item.get("selected")
            quiz[str(key)[:10]] = {
                "selected": selected if isinstance(selected, int) and 0 <= selected <= 4 else None,
                "checked": bool(item.get("checked")),
                "wrong": bool(item.get("wrong")),
                "hidden": bool(item.get("hidden")),
            }
        return {
            "version": 1,
            "known": boolean_map("known", 200),
            "unknown": boolean_map("unknown", 200),
            "quiz": quiz,
            "hiddenSentences": boolean_map("hiddenSentences", 100),
            "readingMode": "hard" if incoming.get("readingMode") == "hard" else "easy",
        }

    def _send_json(self, status: int, data: object) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

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
            filename = "study.html"
        elif relative_path in {"study.html", "data/passages.json"}:
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
        content_type = "application/json; charset=utf-8" if filename.endswith(".json") else "text/html; charset=utf-8"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'unsafe-inline'; "
            "style-src 'unsafe-inline'; img-src data:; connect-src 'self'; "
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
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()

    token = args.token_file.read_text(encoding="ascii").strip()
    if len(token) != 32 or any(character not in "0123456789abcdef" for character in token):
        raise ValueError("Access token must be exactly 32 lowercase hexadecimal characters")

    server = ThreadingHTTPServer(("0.0.0.0", args.port), StudyHandler)
    server.web_root = args.web_root.resolve()
    server.access_token = token
    server.state_dir = args.state_dir.resolve()
    server.state_dir.mkdir(parents=True, exist_ok=True)
    server.state_lock = threading.Lock()
    server.serve_forever()


if __name__ == "__main__":
    main()
