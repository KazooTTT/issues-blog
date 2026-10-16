from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable

BOT_TOKEN_PATTERN = re.compile(r"bot\d+:[A-Za-z0-9_-]+")
BOT_SIGNATURE = "🤖 佳明日报 BOT 自动发送"


def sign_message(text: str) -> str:
    """Put the shared bot signature on its own line above the message body."""
    body = text.strip()
    if not body:
        return BOT_SIGNATURE
    signed = f"{BOT_SIGNATURE}\n\n{body}"
    if body == BOT_SIGNATURE or body.startswith(f"{BOT_SIGNATURE}\n"):
        return body
    return signed


def redact(text: str) -> str:
    redacted = text
    for name in ("TELEGRAM_MEMOS_BOT_TOKEN", "GARMIN_PASSWORD", "OPENROUTER_API_KEY"):
        secret = os.environ.get(name)
        if secret:
            redacted = redacted.replace(secret, "***")
    return BOT_TOKEN_PATTERN.sub("bot***", redacted)


def send_message(
    text: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> None:
    """Post text to the memos channel. The bot token is never logged."""
    token = os.environ.get("TELEGRAM_MEMOS_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_MEMOS_CHAT_ID", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_MEMOS_BOT_TOKEN is required")
    if not chat_id:
        raise SystemExit(
            "TELEGRAM_MEMOS_CHAT_ID is required "
            "(secret or variable; @kazootttmemos or a numeric chat id)"
        )
    if not text.strip():
        raise SystemExit("Refusing to send an empty Telegram message")
    text = sign_message(text)

    payload = json.dumps(
        {"chat_id": chat_id, "text": text},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    print(f"Sending Telegram message to {chat_id}")
    try:
        with opener(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(
            f"Telegram send failed: HTTP {error.code} {redact(detail)}"
        ) from None
    except urllib.error.URLError as error:
        raise SystemExit(
            f"Telegram send failed: {redact(str(error.reason))}"
        ) from None
    except Exception as error:
        raise SystemExit(f"Telegram send failed: {redact(str(error))}") from None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SystemExit("Telegram send failed: response was not JSON") from error
    if not isinstance(parsed, dict) or not parsed.get("ok"):
        description = "unknown error"
        if isinstance(parsed, dict) and parsed.get("description"):
            description = str(parsed["description"])
        raise SystemExit(f"Telegram send failed: {redact(description)}")
    print("Telegram message sent")
