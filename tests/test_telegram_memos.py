from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import unittest
import urllib.error
from http.client import HTTPMessage
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "telegram_memos.py"
SPEC = importlib.util.spec_from_file_location("telegram_memos", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

TOKEN = "123456:ABCDEF_secret-token"


class Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def read(self) -> bytes:
        return self.payload


class TelegramMemosTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous = {
            name: os.environ.get(name)
            for name in ("TELEGRAM_MEMOS_BOT_TOKEN", "TELEGRAM_MEMOS_CHAT_ID", "GARMIN_PASSWORD")
        }
        os.environ["TELEGRAM_MEMOS_BOT_TOKEN"] = TOKEN
        os.environ["TELEGRAM_MEMOS_CHAT_ID"] = "@kazootttmemos"
        os.environ["GARMIN_PASSWORD"] = "garmin-password"

    def tearDown(self) -> None:
        for name, value in self.previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_redacts_secrets_and_bot_token_urls(self) -> None:
        text = MODULE.redact(
            f"password=garmin-password url=https://api.telegram.org/bot{TOKEN}/sendMessage"
        )
        self.assertNotIn(TOKEN, text)
        self.assertNotIn("garmin-password", text)
        self.assertIn("bot***", text)

    def test_http_error_does_not_log_the_bot_token(self) -> None:
        def opener(request: object, timeout: int) -> Response:
            del timeout
            raise urllib.error.HTTPError(
                getattr(request, "full_url"),
                403,
                "Forbidden",
                HTTPMessage(),
                io.BytesIO(b'{"ok":false,"description":"Forbidden"}'),
            )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                MODULE.send_message("睡眠 10月16日", opener=opener)
        combined = f"{caught.exception}{stdout.getvalue()}{stderr.getvalue()}"
        self.assertNotIn(TOKEN, combined)
        self.assertNotIn("garmin-password", combined)
        self.assertIn("HTTP 403", str(caught.exception))
        self.assertIn("@kazootttmemos", stdout.getvalue())

    def test_success_response_does_not_log_the_bot_token(self) -> None:
        seen: list[str] = []

        def opener(request: object, timeout: int) -> Response:
            del timeout
            seen.append(json.loads(getattr(request, "data")))
            return Response(b'{"ok":true,"result":{"message_id":1}}')

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            MODULE.send_message("新文章：标题\nhttps://blog.kazoottt.top/posts/1/", opener=opener)
        self.assertNotIn(TOKEN, stdout.getvalue())
        self.assertIn("Telegram message sent", stdout.getvalue())
        self.assertEqual(seen[0]["chat_id"], "@kazootttmemos")
        self.assertEqual(
            seen[0]["text"],
            f"{MODULE.BOT_SIGNATURE}\n\n新文章：标题\nhttps://blog.kazoottt.top/posts/1/",
        )

    def test_sign_message_adds_one_signature_line(self) -> None:
        body = "新文章：标题\nhttps://blog.kazoottt.top/posts/1/"
        signed = MODULE.sign_message(body)
        self.assertEqual(signed, f"{MODULE.BOT_SIGNATURE}\n\n{body}")
        self.assertEqual(MODULE.sign_message(signed), signed)


if __name__ == "__main__":
    unittest.main()
