from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "notify-rss.py"
SPEC = importlib.util.spec_from_file_location("notify_rss", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

FEED = "https://blog.kazoottt.top/rss.xml"


def feed_xml(items: list[tuple[str, str, str]]) -> str:
    rendered = []
    for title, link, guid in items:
        rendered.append(
            "<item>"
            f"<title>{title}</title>"
            f"<link>{link}</link>"
            f'<guid isPermaLink="false">{guid}</guid>'
            "<content:encoded>https://example.invalid/not-the-link</content:encoded>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">'
        "<channel>"
        "<title>KazooTTT</title>"
        f"{''.join(rendered)}"
        "</channel></rss>"
    )


class RssNotificationTest(unittest.TestCase):
    def test_detects_new_items_in_chronological_order(self) -> None:
        items = MODULE.parse_rss_items(
            feed_xml(
                [
                    ("最新文章", "https://blog.kazoottt.top/posts/3/", "issue-3"),
                    ("中间 &amp; 文章", "/posts/2/", "issue-2"),
                    ("更旧的文章", "https://blog.kazoottt.top/posts/1/", "issue-1"),
                ]
            ),
            FEED,
        )

        self.assertEqual(
            [(item.id, item.title, item.link) for item in items],
            [
                ("issue-3", "最新文章", "https://blog.kazoottt.top/posts/3/"),
                ("issue-2", "中间 & 文章", "https://blog.kazoottt.top/posts/2/"),
                ("issue-1", "更旧的文章", "https://blog.kazoottt.top/posts/1/"),
            ],
        )
        plan = MODULE.plan_rss_notifications(items, ["issue-1"], seed=False)
        self.assertEqual(
            plan.messages,
            [
                "新文章：中间 & 文章\nhttps://blog.kazoottt.top/posts/2/",
                "新文章：最新文章\nhttps://blog.kazoottt.top/posts/3/",
            ],
        )
        self.assertEqual(plan.seen, ["issue-1", "issue-2", "issue-3"])

        unchanged = MODULE.plan_rss_notifications(items, plan.seen, seed=False)
        self.assertEqual(unchanged.messages, [])
        self.assertEqual(unchanged.seen, plan.seen)

    def test_seed_records_current_items_without_messages(self) -> None:
        items = MODULE.parse_rss_items(
            feed_xml(
                [
                    ("最新文章", "https://blog.kazoottt.top/posts/3/", "issue-3"),
                    ("更旧的文章", "https://blog.kazoottt.top/posts/1/", "issue-1"),
                ]
            ),
            FEED,
        )
        with self.assertRaises(MODULE.RssStateMissing) as caught:
            MODULE.plan_rss_notifications(items, None, seed=False)
        self.assertIn("seed", str(caught.exception))

        plan = MODULE.plan_rss_notifications(items, None, seed=True)
        self.assertEqual(plan.messages, [])
        self.assertEqual(plan.new_items, [])
        self.assertEqual(plan.seen, ["issue-3", "issue-1"])

    def test_formats_blank_titles_and_atom_entries(self) -> None:
        items = MODULE.parse_rss_items(
            """<?xml version="1.0" encoding="UTF-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry>
                <title>  跨行
                标题 </title>
                <link rel="self" href="https://blog.kazoottt.top/rss.xml"/>
                <link rel="alternate" href="https://blog.kazoottt.top/posts/9/"/>
                <id>issue-9</id>
              </entry>
              <entry>
                <title></title>
                <id>https://blog.kazoottt.top/posts/8/</id>
              </entry>
              <entry>
                <title>重复</title>
                <id>issue-9</id>
                <link href="https://blog.kazoottt.top/posts/9/"/>
              </entry>
            </feed>
            """,
            FEED,
        )
        self.assertEqual(
            [MODULE.format_rss_message(item) for item in items],
            [
                "新文章：跨行 标题\nhttps://blog.kazoottt.top/posts/9/",
                "新文章：未命名文章\nhttps://blog.kazoottt.top/posts/8/",
            ],
        )

    def test_seen_list_drops_oldest_ids_past_the_limit(self) -> None:
        self.assertEqual(
            MODULE.merge_seen(["a", "b", "c"], ["d"], limit=3),
            ["b", "c", "d"],
        )

    def test_failed_send_records_delivered_ids_and_redacts_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            feed = Path(directory) / "rss.xml"
            state = Path(directory) / "rss-seen.json"
            feed.write_text(
                feed_xml(
                    [
                        ("第二篇", "https://blog.kazoottt.top/posts/2/", "issue-2"),
                        ("第一篇", "https://blog.kazoottt.top/posts/1/", "issue-1"),
                    ]
                ),
                encoding="utf-8",
            )
            state.write_text(
                json.dumps({"feed": FEED, "seen": []}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            token = "123456:ABCDEF_secret-token"

            def send(message: str) -> None:
                if "第二篇" in message:
                    raise RuntimeError(
                        f"down https://api.telegram.org/bot{token}/sendMessage"
                    )

            original = MODULE.telegram_memos.send_message
            argv = sys.argv
            MODULE.telegram_memos.send_message = send
            try:
                sys.argv = [
                    "notify-rss.py",
                    "--input",
                    str(feed),
                    "--state",
                    str(state),
                ]
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as caught:
                        MODULE.main()
            finally:
                sys.argv = argv
                MODULE.telegram_memos.send_message = original

            self.assertNotIn(token, str(caught.exception))
            self.assertIn("bot***", str(caught.exception))
            self.assertEqual(
                json.loads(state.read_text(encoding="utf-8"))["seen"],
                ["issue-1"],
            )

    def test_partial_send_keeps_only_delivered_ids(self) -> None:
        items = MODULE.parse_rss_items(
            feed_xml(
                [
                    ("第二篇", "https://blog.kazoottt.top/posts/2/", "issue-2"),
                    ("第一篇", "https://blog.kazoottt.top/posts/1/", "issue-1"),
                ]
            ),
            FEED,
        )
        plan = MODULE.plan_rss_notifications(items, [], seed=False)

        def send(message: str) -> None:
            if "第二篇" in message:
                raise RuntimeError("telegram down bot123:secret")

        sent, failure = MODULE.send_planned_messages(plan, send)
        self.assertEqual(sent, ["issue-1"])
        self.assertIsInstance(failure, RuntimeError)
        self.assertEqual(
            MODULE.merge_seen([], sent),
            ["issue-1"],
        )

    def test_cli_refuses_to_post_without_state_and_seeds_without_sending(self) -> None:
        xml = feed_xml(
            [
                ("最新文章", "https://blog.kazoottt.top/posts/3/", "issue-3"),
                ("更旧的文章", "https://blog.kazoottt.top/posts/1/", "issue-1"),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            feed = Path(directory) / "rss.xml"
            state = Path(directory) / "rss-seen.json"
            feed.write_text(xml, encoding="utf-8")

            missing = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(feed),
                    "--state",
                    str(state),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("--seed", missing.stderr)
            self.assertFalse(state.exists())

            dry_seed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(feed),
                    "--state",
                    str(state),
                    "--seed",
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(dry_seed.returncode, 0, dry_seed.stderr)
            self.assertIn("nothing sent", dry_seed.stdout)
            self.assertFalse(state.exists())

            seeded = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(feed),
                    "--state",
                    str(state),
                    "--seed",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(seeded.returncode, 0, seeded.stderr)
            self.assertIn("nothing sent", seeded.stdout)
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["seen"], ["issue-3", "issue-1"])
            self.assertEqual(saved["feed"], FEED)

            quiet = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(feed),
                    "--state",
                    str(state),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(quiet.returncode, 0, quiet.stderr)
            self.assertIn("No new RSS items", quiet.stdout)
            self.assertEqual(state.read_text(encoding="utf-8"), json.dumps(saved, ensure_ascii=False, indent=2) + "\n")

            updated = feed_xml(
                [
                    ("刚发布", "https://blog.kazoottt.top/posts/4/", "issue-4"),
                    ("最新文章", "https://blog.kazoottt.top/posts/3/", "issue-3"),
                    ("更旧的文章", "https://blog.kazoottt.top/posts/1/", "issue-1"),
                ]
            )
            feed.write_text(updated, encoding="utf-8")
            preview = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(feed),
                    "--state",
                    str(state),
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertIn("新文章：刚发布\nhttps://blog.kazoottt.top/posts/4/", preview.stdout)
            self.assertIn("RSS state not updated", preview.stdout)
            self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["seen"], ["issue-3", "issue-1"])

            conflict = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(feed),
                    "--seed",
                    "--resend-latest",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(conflict.returncode, 0)


if __name__ == "__main__":
    unittest.main()
