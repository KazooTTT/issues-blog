from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "notify-garmin-sleep.py"
SPEC = importlib.util.spec_from_file_location("notify_garmin_sleep", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def epoch_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def wall_clock_labeled_utc(moment: datetime) -> int:
    """Garmin CN local fields can store the Shanghai clock as if it were UTC."""
    local = moment.astimezone(SHANGHAI).replace(tzinfo=timezone.utc)
    return epoch_ms(local)


class GarminSleepMessageTest(unittest.TestCase):
    def test_formats_sleep_message_from_gmt_timestamps(self) -> None:
        fell_asleep = datetime(2026, 10, 15, 23, 18, tzinfo=SHANGHAI)
        woke = datetime(2026, 10, 16, 7, 42, tzinfo=SHANGHAI)
        summary = MODULE.summarize_sleep(
            {
                "sleep": {
                    "dailySleepDTO": {
                        "calendarDate": "2026-10-16",
                        "sleepTimeSeconds": 26640,
                        "deepSleepSeconds": 5400,
                        "lightSleepSeconds": 14400,
                        "remSleepSeconds": 6840,
                        "sleepStartTimestampGMT": epoch_ms(fell_asleep),
                        "sleepEndTimestampGMT": epoch_ms(woke),
                        "sleepStartTimestampLocal": epoch_ms(
                            datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc),
                        ),
                        "sleepEndTimestampLocal": epoch_ms(
                            datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc),
                        ),
                        "sleepScores": {"overall": {"value": 82, "qualifierKey": "GOOD"}},
                        "restingHeartRate": 51,
                    }
                },
                "stats": {
                    "restingHeartRate": 60,
                    "bodyBatteryMostRecentValue": 10,
                },
                "body_battery": [
                    {
                        "bodyBatteryValuesArray": [
                            [epoch_ms(datetime(2026, 10, 16, 7, 0, tzinfo=SHANGHAI)), 40],
                            [epoch_ms(datetime(2026, 10, 16, 7, 40, tzinfo=SHANGHAI)), 68],
                            [epoch_ms(datetime(2026, 10, 16, 10, 0, tzinfo=SHANGHAI)), 90],
                            [epoch_ms(datetime(2026, 10, 16, 7, 50, tzinfo=SHANGHAI)), None],
                        ]
                    }
                ],
            }
        )

        self.assertEqual(summary["woke_at"], woke)
        self.assertEqual(summary["fell_asleep_at"], fell_asleep)
        self.assertEqual(summary["resting_heart_rate"], 51)
        self.assertEqual(summary["body_battery"], 68)
        self.assertEqual(
            MODULE.format_sleep_message(summary),
            "\n".join(
                [
                    "睡眠 10月16日",
                    "起床 07:42",
                    "入眠 10月15日 23:18",
                    "总睡眠 7小时24分",
                    "深睡 1小时30分 · 浅睡 4小时 · REM 1小时54分",
                    "睡眠评分 82",
                    "静息心率 51",
                    "身体电量 68",
                ]
            ),
        )

    def test_local_timestamps_keep_shanghai_wall_clock_when_gmt_is_missing(self) -> None:
        fell_asleep = datetime(2026, 10, 15, 23, 18, tzinfo=SHANGHAI)
        woke = datetime(2026, 10, 16, 7, 42, tzinfo=SHANGHAI)
        summary = MODULE.summarize_sleep(
            {
                "sleep": {
                    "dailySleepDTO": {
                        "calendarDate": "2026-10-16",
                        "sleepTimeSeconds": 26640,
                        "sleepStartTimestampLocal": wall_clock_labeled_utc(fell_asleep),
                        "sleepEndTimestampLocal": wall_clock_labeled_utc(woke),
                    }
                }
            }
        )

        self.assertEqual(summary["fell_asleep_at"].timestamp(), fell_asleep.timestamp())
        self.assertEqual(summary["woke_at"].timestamp(), woke.timestamp())
        message = MODULE.format_sleep_message(summary)
        self.assertIn("起床 07:42", message)
        self.assertIn("入眠 10月15日 23:18", message)
        self.assertNotIn("静息心率", message)
        self.assertNotIn("身体电量", message)
        self.assertNotIn("睡眠评分", message)
        self.assertNotIn("深睡", message)

    def test_omits_missing_stages_and_reads_optional_fallbacks(self) -> None:
        summary = MODULE.summarize_sleep(
            {
                "sleep": {
                    "calendarDate": "2026-10-16",
                    "sleepTimeSeconds": "3600",
                    "deepSleepSeconds": 0,
                    "sleepScore": 70,
                },
                "rhr": {
                    "allMetrics": {
                        "metricsMap": {
                            "WELLNESS_RESTING_HEART_RATE": [
                                {"calendarDate": "2026-10-16", "value": 48}
                            ]
                        }
                    }
                },
                "stats": {"bodyBatteryMostRecentValue": 77},
            }
        )

        self.assertEqual(summary["sleep_score"], 70)
        self.assertEqual(summary["resting_heart_rate"], 48)
        self.assertEqual(summary["body_battery"], 77)
        message = MODULE.format_sleep_message(summary)
        self.assertIn("深睡 0分", message)
        self.assertNotIn("浅睡", message)
        self.assertNotIn("REM", message)
        self.assertIn("静息心率 48", message)
        self.assertIn("身体电量 77", message)

    def test_rejects_empty_sleep(self) -> None:
        with self.assertRaises(ValueError) as caught:
            MODULE.summarize_sleep(
                {
                    "sleep": {
                        "dailySleepDTO": {
                            "calendarDate": "2026-10-16",
                            "sleepTimeSeconds": 0,
                        }
                    }
                }
            )
        self.assertIn("sleepTimeSeconds", str(caught.exception))

    def test_cli_dry_run_prints_message_without_telegram(self) -> None:
        with self.subTest("fixture"):
            with tempfile.TemporaryDirectory() as directory:
                bundle = Path(directory) / "sleep.json"
                bundle.write_text(
                    json.dumps(
                        {
                            "sleep": {
                                "dailySleepDTO": {
                                    "calendarDate": "2026-10-16",
                                    "sleepTimeSeconds": 3600,
                                    "sleepScores": {"overall": {"value": 80}},
                                }
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT_PATH),
                        "--input",
                        str(bundle),
                        "--dry-run",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("总睡眠 1小时", result.stdout)
                self.assertIn("睡眠评分 80", result.stdout)
                self.assertIn("Dry run; Telegram message not sent", result.stdout)
                self.assertNotIn("TELEGRAM_MEMOS_BOT_TOKEN", result.stdout + result.stderr)

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--date", "16-10-2026", "--dry-run"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("YYYY-MM-DD", result.stderr)

        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty.json"
            empty.write_text(
                json.dumps(
                    {
                        "sleep": {
                            "dailySleepDTO": {
                                "calendarDate": "2026-10-16",
                                "sleepTimeSeconds": 0,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            missing = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--input", str(empty), "--dry-run"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("sleepTimeSeconds", missing.stderr)
            self.assertIn("re-run", missing.stderr)


if __name__ == "__main__":
    unittest.main()
