import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("reports", Path(__file__).parents[1] / "scripts/publish-daily-reports.py")
reports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reports)


class ReportsTest(unittest.TestCase):
    def test_midnight_and_new_year_use_shanghai_previous_day(self):
        now = datetime(2026, 12, 31, 16, 0, tzinfo=timezone.utc)
        self.assertEqual(str(reports.report_date("daily", now)), "2026-12-31")
        self.assertEqual(str(reports.report_date("sleep", now)), "2027-01-01")

    def test_sleep_uses_gmt_not_misleading_local_timestamp(self):
        start = datetime(2026, 10, 14, 15, 30, tzinfo=timezone.utc).timestamp() * 1000
        end = datetime(2026, 10, 14, 23, 30, tzinfo=timezone.utc).timestamp() * 1000
        payload = {"dailySleepDTO": {
            "calendarDate": "2026-10-15", "sleepStartTimestampGMT": start,
            "sleepEndTimestampGMT": end, "sleepStartTimestampLocal": start + 16 * 3600000,
            "sleepTimeSeconds": 27000, "sleepScores": {"overall": {"value": 0}},
        }}
        _, body = reports.sleep_report("2026-10-15", payload)
        self.assertIn("入眠时间：2026-10-14 23:30", body)
        self.assertIn("起床时间：2026-10-15 07:30", body)
        self.assertIn("7 小时 30 分钟", body)
        self.assertIn("睡眠评分：0", body)
        with self.assertRaises(reports.ReportError):
            reports.sleep_report("2026-10-16", payload)
        with self.assertRaises(reports.ReportError):
            reports.sleep_report("2026-10-15", {})

    def test_daily_reads_requested_date_and_completed_enrichment_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "daily.sqlite"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE bookmarks (raindrop_id TEXT, url TEXT, domain TEXT, category TEXT, classification_status TEXT, title TEXT, excerpt TEXT, enriched_title TEXT, enriched_description TEXT, enrichment_status TEXT, saved_date TEXT, created_at TEXT)")
                for identifier, status, day in [("1", "completed", "2026-10-15"), ("2", "failed", "2026-10-15"), ("3", "completed", "2026-10-16")]:
                    db.execute("INSERT INTO bookmarks VALUES (?, 'https://example.com/a(b)', 'example.com', 'ai', 'pending', '原始标题', '原始摘要', '增强标题', '增强摘要', ?, ?, ?)", (identifier, status, day, identifier))
            rows = reports.read_daily("2026-10-15", path)
            self.assertEqual(len(rows), 2)
            self.assertEqual([r["title"] for r in rows], ["增强标题", "原始标题"])
            _, body = reports.daily_report("2026-10-15", rows)
            self.assertIn("## 待分类", body)
            self.assertIn("a%28b%29", body)
            with self.assertRaises(sqlite3.OperationalError):
                reports.read_daily("2026-10-15", Path(directory) / "missing.sqlite")

    def test_telegram_length_handles_emoji(self):
        text = reports.telegram_text("日报", "😀" * 5000, "https://github.com/KazooTTT/issues-blog/issues/1")
        self.assertLessEqual(len(text.encode("utf-16-le")) // 2, 4096)
        self.assertIn("完整报告", text)

    def test_d1_failure_is_not_a_false_empty_report(self):
        with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "account", "CLOUDFLARE_API_TOKEN": "secret"}), patch.object(reports, "api", return_value={"success": False}):
            with self.assertRaises(reports.ReportError):
                reports.read_daily("2026-10-15")

    def test_rerun_deduplicates_issue_and_telegram_and_preserves_edits(self):
        calls, issues = [], []
        def fake_api(url, **kwargs):
            calls.append((url, kwargs))
            data = kwargs.get("data")
            if url.endswith("/user"):
                return {"login": "KazooTTT"}
            if "/issues?" in url:
                return issues
            if "/labels/" in url:
                return {}
            if url.endswith("/issues"):
                item = {**data, "number": 7, "html_url": "https://github.com/KazooTTT/issues-blog/issues/7"}
                issues.append(item)
                return item
            if url.endswith("/sendMessage"):
                return {"ok": True, "result": {"message_id": 1}}
            if url.endswith("/issues/7"):
                issues[0].update(data)
                return issues[0]
            raise AssertionError(url)
        env = {"REPORT_GITHUB_TOKEN": "owner-token", "TELEGRAM_BOT_TOKEN": "bot-token", "TELEGRAM_CHAT_ID": "123"}
        with patch.dict(os.environ, env), patch.object(reports, "api", side_effect=fake_api):
            reports.publish("daily", "2026-10-15", "日报", "首版")
            issues[0]["body"] += "\n人工修订"
            reports.publish("daily", "2026-10-15", "日报", "修改后的输入")
        self.assertEqual(len(issues), 1)
        self.assertEqual(sum(url.endswith("/sendMessage") for url, _ in calls), 1)
        self.assertIn("人工修订", issues[0]["body"])
        self.assertIn("blog:publish", issues[0]["labels"])

    def test_telegram_failure_retries_existing_issue(self):
        issue = {"number": 3, "title": "日报", "body": "正文\n<!-- automated-report:daily:2026-10-15 -->", "html_url": "https://example.com/issue/3"}
        def fake_api(url, **kwargs):
            if url.endswith("/user"):
                return {"login": "KazooTTT"}
            if "/issues?" in url:
                return [issue]
            if url.endswith("/sendMessage"):
                raise reports.ReportError("Telegram failed")
            raise AssertionError("Unexpected write: " + url)
        with patch.dict(os.environ, {"REPORT_GITHUB_TOKEN": "token", "TELEGRAM_BOT_TOKEN": "bot", "TELEGRAM_CHAT_ID": "123"}), patch.object(reports, "api", side_effect=fake_api):
            with self.assertRaises(reports.ReportError):
                reports.publish("daily", "2026-10-15", "日报", "正文")
        self.assertNotIn("report-telegram-sent", issue["body"])

    def test_bot_owner_mismatch_blocks_writes(self):
        with patch.dict(os.environ, {"REPORT_GITHUB_TOKEN": "token"}), patch.object(reports, "api", return_value={"login": "github-actions[bot]"}) as api:
            with self.assertRaises(reports.ReportError):
                reports.publish("daily", "2026-10-15", "日报", "正文", telegram=False)
            self.assertEqual(api.call_count, 1)


if __name__ == "__main__":
    unittest.main()
