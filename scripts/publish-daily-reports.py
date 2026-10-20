#!/usr/bin/env python3
"""Generate reports read-only by default; --publish writes Issues and Telegram."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
D1_ID = "4da564b6-3fc1-4d42-89a1-f96af4ad9f58"
CATEGORIES = {
    "ai": "AI", "product_design": "产品与设计", "development": "开发与工具",
    "visual": "影像与审美", "indie_business": "独立开发与营销",
    "reading_thinking": "阅读与思考", "other": "待分类",
}
DAILY_SQL = """
SELECT raindrop_id, url, domain, category, classification_status,
 CASE WHEN enrichment_status = 'completed' THEN COALESCE(NULLIF(enriched_title, ''), title) ELSE title END AS title,
 CASE WHEN enrichment_status = 'completed' THEN COALESCE(NULLIF(enriched_description, ''), excerpt) ELSE excerpt END AS excerpt
FROM bookmarks WHERE saved_date = ? ORDER BY created_at, raindrop_id
"""


class ReportError(Exception):
    pass


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ReportError(f"Missing environment variable: {name}")
    return value


def api(url, *, token=None, method="GET", data=None):
    headers = {"User-Agent": "issues-blog-reports", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, headers=headers, method=method,
                      data=json.dumps(data).encode() if data is not None else None)
    try:
        with urlopen(request, timeout=60) as response:
            return json.load(response)
    except HTTPError as error:
        # URLs can contain Telegram's bot token. Never log URLs, bodies or raw exceptions.
        raise ReportError(f"{urlparse(url).hostname}: HTTP {error.code}") from None
    except (URLError, TimeoutError, ValueError):
        raise ReportError(f"{urlparse(url).hostname}: request failed") from None


def report_date(kind, now=None):
    today = (now or datetime.now(timezone.utc)).astimezone(TZ).date()
    return today - timedelta(days=1) if kind == "daily" else today


def clean(value):
    # External titles/descriptions are text, not trusted Markdown/HTML.
    text = re.sub(r"<[^>]*>", "", str(value if value is not None else ""))
    text = " ".join(text.split())
    return re.sub(r"([\\`*_{}\[\]<>#|!])", r"\\\1", text)


def safe_url(value):
    value = str(value if value is not None else "")
    if urlparse(value).scheme not in {"http", "https"}:
        raise ReportError("Bookmark URL must use http or https")
    return quote(value, safe=":/?&=%#@+;,~!$'*-._")


def read_daily(day, database=None):
    if database:
        with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(DAILY_SQL, (day,))]
    account = required("CLOUDFLARE_ACCOUNT_ID")
    database_id = os.environ.get("DAILY_D1_DATABASE_ID", D1_ID)
    result = api(f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{database_id}/query",
                 token=required("CLOUDFLARE_API_TOKEN"), method="POST",
                 data={"sql": DAILY_SQL, "params": [day]})
    if not result.get("success") or not result.get("result") or not all(r.get("success") for r in result["result"]):
        raise ReportError("D1 query failed")
    return [row for batch in result["result"] for row in batch["results"]]


def daily_report(day, rows):
    title = f"每日收集 · {day}"
    lines = [f"共收集 {len(rows)} 条内容。", ""]
    grouped = {}
    for row in rows:
        category = "other" if row.get("classification_status") == "pending" else row.get("category")
        grouped.setdefault(CATEGORIES.get(category, "待分类"), []).append(row)
    for category, entries in grouped.items():
        lines.extend([f"## {category}", ""])
        for row in entries:
            lines.append(f"### [{clean(row['title']) or '未命名收藏'}]({safe_url(row['url'])})")
            lines.extend(["", clean(row.get("excerpt")) or "暂无摘要。", ""])
    if not rows:
        lines.extend(["这一天没有新增收藏。", ""])
    lines.append(f"[查看 daily 当日页面](https://daily.kazoottt.top/d/{day}/)")
    return title, "\n".join(lines)


def duration(value):
    if value is None:
        return "未提供"
    minutes = max(0, int(value) // 60)
    return f"{minutes // 60} 小时 {minutes % 60} 分钟"


def sleep_report(day, payload):
    dto = payload.get("dailySleepDTO") or {}
    start, end = dto.get("sleepStartTimestampGMT"), dto.get("sleepEndTimestampGMT")
    if not start or not end:
        raise ReportError("Sleep data not synced yet; retry after watch synchronization")
    start_time = datetime.fromtimestamp(start / 1000, timezone.utc).astimezone(TZ)
    end_time = datetime.fromtimestamp(end / 1000, timezone.utc).astimezone(TZ)
    if end_time.date().isoformat() != day or start_time >= end_time:
        raise ReportError("Sleep window does not match requested wake date")
    if dto.get("calendarDate") and dto["calendarDate"] != day:
        raise ReportError("Garmin returned a different sleep date")
    score = ((dto.get("sleepScores") or {}).get("overall") or {}).get("value")
    fields = [
        ("入眠时间", start_time.strftime("%Y-%m-%d %H:%M")),
        ("起床时间", end_time.strftime("%Y-%m-%d %H:%M")),
        ("睡眠时长", duration(dto.get("sleepTimeSeconds"))),
        ("睡眠评分", score),
        ("深睡", duration(dto.get("deepSleepSeconds"))),
        ("浅睡", duration(dto.get("lightSleepSeconds"))),
        ("REM", duration(dto.get("remSleepSeconds"))),
        ("清醒", duration(dto.get("awakeSleepSeconds"))),
        ("静息心率", payload.get("restingHeartRate")),
        ("夜间平均 HRV", payload.get("avgOvernightHrv")),
        ("身体电量变化", payload.get("bodyBatteryChange")),
    ]
    body = "\n".join(f"- {label}：{clean(value) if value is not None else '未提供'}" for label, value in fields)
    body += "\n\n时间为北京时间，起床时间采用佳明检测的睡眠结束时间。\n来源：Garmin Connect。"
    return f"佳明早报 · {day}", body


def fetch_sleep(day):
    from garminconnect import Garmin
    is_cn = os.environ.get("GARMIN_IS_CN", "true").lower() in {"1", "true", "yes"}
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    store = os.environ.get("GARMIN_TOKEN_STORE")
    if not store and (not email or not password):
        raise ReportError("Configure GARMIN_TOKEN_STORE or GARMIN_EMAIL / GARMIN_PASSWORD")
    client = Garmin(email, password, is_cn=is_cn)
    try:
        if store:
            client.login(store)
        else:
            client.login()
        return client.get_sleep_data(day)
    except Exception:
        raise ReportError("Garmin login or sleep query failed; check credentials / session / watch sync") from None


def telegram_text(title, body, issue_url):
    # One message avoids partial multi-message delivery. Full Markdown lives in the Issue.
    text = f"{title}\n\n{body}"
    suffix = f"\n\n完整报告：{issue_url}"
    # Telegram counts UTF-16 units. 3800 leaves headroom below the 4096 limit.
    budget = 3800 - len(suffix.encode("utf-16-le")) // 2
    encoded = text.encode("utf-16-le")
    if len(encoded) // 2 > budget:
        text = encoded[:(budget - 2) * 2].decode("utf-16-le", errors="ignore") + "…"
    return text + suffix


def publish(kind, day, title, body, *, telegram=True, blog=True):
    repo = os.environ.get("REPORT_REPOSITORY", "KazooTTT/issues-blog")
    token = required("REPORT_GITHUB_TOKEN")
    base = f"https://api.github.com/repos/{repo}"
    owner = repo.split("/")[0]
    user = api("https://api.github.com/user", token=token)
    if user["login"].lower() != owner.lower():
        raise ReportError("REPORT_GITHUB_TOKEN must belong to the repository owner")
    if telegram:
        bot = required("TELEGRAM_BOT_TOKEN")
        chat = required("TELEGRAM_CHAT_ID")
        destination = hashlib.sha256(chat.encode()).hexdigest()[:16]
        sent = f"<!-- report-telegram-sent:{destination} -->"
    marker = f"<!-- automated-report:{kind}:{day} -->"
    issue = None
    page = 1
    # Issue listing is immediately consistent; search indexing can lag after creation.
    while True:
        items = api(base + "/issues?" + urlencode({"state": "all", "creator": owner, "per_page": 100, "page": page}), token=token)
        for item in items:
            if "pull_request" not in item and marker in (item.get("body") or ""):
                issue = item
                break
        if issue or len(items) < 100:
            break
        page += 1
    if issue is None:
        if len(body) > 65000:
            raise ReportError("Report exceeds GitHub Issue body limit; shorten source summaries before publishing")
        labels = ["总结", "AI 写作为主"]
        if blog:
            labels.append("blog:publish")
        # Ensure all publishing labels exist before creating the article.
        colors = {"总结": "0e8a16", "AI 写作为主": "c5def5", "blog:publish": "1d76db"}
        for label in labels:
            try:
                api(base + "/labels/" + quote(label, safe=""), token=token)
            except ReportError as error:
                if not str(error).endswith("HTTP 404"):
                    raise
                api(base + "/labels", token=token, method="POST", data={"name": label, "color": colors[label]})
        issue = api(base + "/issues", token=token, method="POST",
                    data={"title": title, "body": f"{body}\n\n{marker}", "labels": labels})
    # Preserve the first published snapshot and any subsequent manual edits on reruns.
    if telegram and sent not in (issue.get("body") or ""):
        message_body = re.sub(r"<!--.*?-->", "", issue["body"], flags=re.S).strip()
        result = api(f"https://api.telegram.org/bot{bot}/sendMessage", method="POST",
                     data={"chat_id": chat, "text": telegram_text(issue["title"], message_body, issue["html_url"]),
                           "link_preview_options": {"is_disabled": True}})
        if not result.get("ok"):
            raise ReportError("Telegram rejected the message")
        api(base + f"/issues/{issue['number']}", token=token, method="PATCH",
            data={"body": issue["body"] + f"\n{sent}"})
    return issue["html_url"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["sleep", "daily"])
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--database", help="Read daily's local SQLite read-only (preview/testing)")
    parser.add_argument("--input", type=Path, help="Read saved Garmin JSON instead of logging in")
    parser.add_argument("--output", type=Path, help="Write a local Markdown preview")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--no-telegram", action="store_true")
    parser.add_argument("--draft", action="store_true", help="Create a tracking Issue without blog:publish")
    args = parser.parse_args()
    day = (args.date or report_date(args.kind)).isoformat()
    if args.kind == "sleep":
        payload = json.loads(args.input.read_text()) if args.input else fetch_sleep(day)
        title, body = sleep_report(day, payload)
    else:
        title, body = daily_report(day, read_daily(day, args.database))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.output.write_text(f"# {title}\n\n{body}\n")
        args.output.chmod(0o600)
    if args.publish:
        print(publish(args.kind, day, title, body, telegram=not args.no_telegram, blog=not args.draft))
    elif not args.output:
        print(f"# {title}\n\n{body}")
    else:
        print(f"Preview saved to {args.output}")


if __name__ == "__main__":
    try:
        main()
    except ReportError as error:
        print(f"Report failed: {error}", file=sys.stderr)
        sys.exit(1)
