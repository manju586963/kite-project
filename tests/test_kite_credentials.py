#!/usr/bin/env python3
"""Unit tests for kite_credentials (no network)."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

import kite_credentials as kc


class CredentialLoadTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = {
            k: os.environ[k]
            for k in list(os.environ)
            if k.startswith("KITE_")
        }
        for k in list(os.environ):
            if k.startswith("KITE_"):
                del os.environ[k]

    def tearDown(self) -> None:
        for k in list(os.environ):
            if k.startswith("KITE_"):
                del os.environ[k]
        os.environ.update(self._env)

    def test_access_token_from_env(self) -> None:
        os.environ["KITE_ACCESS_TOKEN"] = "env-token-123"
        with mock.patch.object(kc, "ACCESS_TOKEN_FILE", Path("/no/such/file")):
            with mock.patch.object(kc, "SESSION_FILE", Path("/no/such/session")):
                with mock.patch.object(kc, "_load_dotenv", lambda: None):
                    self.assertEqual(kc.load_access_token(), "env-token-123")

    def test_access_token_from_file(self) -> None:
        token_file = Path(self.id().replace(".", "_") + "_token.txt")
        try:
            token_file.write_text("file-token-456\n", encoding="utf-8")
            with mock.patch.object(kc, "ACCESS_TOKEN_FILE", token_file):
                with mock.patch.object(kc, "_load_dotenv", lambda: None):
                    self.assertEqual(kc.load_access_token(), "file-token-456")
        finally:
            token_file.unlink(missing_ok=True)

    def test_api_key_from_session(self) -> None:
        session = Path(self.id().replace(".", "_") + "_session.json")
        try:
            session.write_text(
                json.dumps({"api_key": "session-key", "access_token": "t"}),
                encoding="utf-8",
            )
            with mock.patch.object(kc, "SESSION_FILE", session):
                with mock.patch.object(kc, "_load_dotenv", lambda: None):
                    self.assertEqual(kc.load_api_key(), "session-key")
        finally:
            session.unlink(missing_ok=True)

    def test_missing_token_message(self) -> None:
        with mock.patch.object(kc, "ACCESS_TOKEN_FILE", Path("/no/such/file")):
            with mock.patch.object(kc, "SESSION_FILE", Path("/no/such/session")):
                with mock.patch.object(kc, "_load_dotenv", lambda: None):
                    with self.assertRaises(RuntimeError) as ctx:
                        kc.load_access_token()
        self.assertIn("KITE_ACCESS_TOKEN", str(ctx.exception))
        self.assertIn("Cloud/CI", str(ctx.exception))

    def test_credential_status(self) -> None:
        os.environ["KITE_API_KEY"] = "k"
        os.environ["KITE_ACCESS_TOKEN"] = "t"
        with mock.patch.object(kc, "_load_dotenv", lambda: None):
            status = kc.credential_status()
        self.assertTrue(status["api_key"])
        self.assertTrue(status["access_token"])
        self.assertFalse(status["api_secret"])


if __name__ == "__main__":
    unittest.main()
