#!/usr/bin/env python3
"""
Zerodha Kite Connect login script.

Opens the Kite login page, captures the request_token via a local callback
server (or manual paste), exchanges it for a daily access_token, and saves
the session for later API use.

Prerequisites:
  1. Create an app at https://developers.kite.trade/
  2. Set the app redirect URL to http://127.0.0.1:8765/callback
  3. Copy .env.example to .env and fill in KITE_API_KEY / KITE_API_SECRET

Usage:
  python scripts/zerodha_login.py
  python scripts/zerodha_login.py --manual          # paste redirect URL yourself
  python scripts/zerodha_login.py --port 8765
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from kiteconnect import KiteConnect
except ImportError:
    print("Missing dependency. Install with: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
SESSION_FILE = ROOT / ".kite_session.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def load_dotenv(path: Path = ENV_FILE) -> None:
    """Load KEY=VALUE pairs from .env into os.environ (no override)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def require_credentials() -> tuple[str, str]:
    api_key = os.environ.get("KITE_API_KEY", "").strip()
    api_secret = os.environ.get("KITE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        print(
            "Set KITE_API_KEY and KITE_API_SECRET in .env or the environment.\n"
            f"See {ROOT / '.env.example'}",
            file=sys.stderr,
        )
        sys.exit(1)
    return api_key, api_secret


def extract_request_token(url_or_token: str) -> str:
    """Accept a full redirect URL or a bare request_token string."""
    value = url_or_token.strip()
    if "request_token=" in value or value.startswith("http"):
        query = parse_qs(urlparse(value).query)
        token = (query.get("request_token") or [None])[0]
        status = (query.get("status") or [None])[0]
        if status and status.lower() not in ("success",):
            raise ValueError(f"Login failed or was cancelled (status={status})")
        if not token:
            raise ValueError("No request_token found in the provided URL")
        return token
    return value


class CallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures request_token from the redirect."""

    server: "CallbackServer"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") != "/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found. Use /callback as the redirect path.")
            return

        query = parse_qs(parsed.query)
        token = (query.get("request_token") or [None])[0]
        status = (query.get("status") or ["unknown"])[0]

        if token and status.lower() == "success":
            self.server.request_token = token
            body = (
                b"<html><body><h2>Login successful</h2>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
            self.send_response(200)
        else:
            self.server.error = f"Login failed (status={status})"
            body = (
                b"<html><body><h2>Login failed</h2>"
                b"<p>Check the terminal for details.</p>"
                b"</body></html>"
            )
            self.send_response(400)

        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

        # Unblock serve_forever after the response is written.
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        # Keep the terminal quiet during the OAuth redirect.
        return


class CallbackServer(HTTPServer):
    def __init__(self, host: str, port: int) -> None:
        super().__init__((host, port), CallbackHandler)
        self.request_token: str | None = None
        self.error: str | None = None


def capture_token_via_callback(login_url: str, host: str, port: int) -> str:
    redirect = f"http://{host}:{port}/callback"
    print(f"Redirect URL expected by Kite app settings: {redirect}")
    print(f"Opening browser:\n  {login_url}\n")

    server = CallbackServer(host, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    opened = webbrowser.open(login_url)
    if not opened:
        print("Could not open a browser automatically. Open the URL above manually.")

    print("Waiting for Zerodha login + 2FA redirect...")
    thread.join()
    server.server_close()

    if server.error:
        raise RuntimeError(server.error)
    if not server.request_token:
        raise RuntimeError("No request_token received from callback")
    return server.request_token


def capture_token_manually(login_url: str) -> str:
    print(f"Open this URL in your browser:\n  {login_url}\n")
    print(
        "After login, Zerodha redirects to your registered URL with ?request_token=...\n"
        "Paste the full redirect URL (or just the request_token) below.\n"
    )
    raw = input("Redirect URL / request_token: ").strip()
    if not raw:
        raise ValueError("Empty input")
    return extract_request_token(raw)


def save_session(session: dict, path: Path = SESSION_FILE) -> None:
    # Persist only what is needed for later API calls; never store api_secret.
    payload = {
        "user_id": session.get("user_id"),
        "user_name": session.get("user_name"),
        "email": session.get("email"),
        "access_token": session.get("access_token"),
        "login_time": session.get("login_time"),
        "api_key": os.environ.get("KITE_API_KEY", ""),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def login(manual: bool, host: str, port: int) -> dict:
    load_dotenv()
    api_key, api_secret = require_credentials()

    kite = KiteConnect(api_key=api_key)
    login_url = kite.login_url()

    if manual:
        request_token = capture_token_manually(login_url)
    else:
        request_token = capture_token_via_callback(login_url, host, port)

    print("Exchanging request_token for access_token...")
    session = kite.generate_session(request_token, api_secret=api_secret)
    kite.set_access_token(session["access_token"])

    save_session(session)
    profile = kite.profile()

    print("\nLogin successful")
    print(f"  User     : {profile.get('user_name')} ({profile.get('user_id')})")
    print(f"  Email    : {profile.get('email')}")
    print(f"  Session  : {SESSION_FILE}")
    print("  Note     : access_token is valid until ~06:00 IST next trading day")
    return session


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log in to Zerodha via Kite Connect")
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Paste the redirect URL instead of running a local callback server",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Callback bind host")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Callback port (default {DEFAULT_PORT})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        login(manual=args.manual, host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 — surface API/user errors cleanly
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
