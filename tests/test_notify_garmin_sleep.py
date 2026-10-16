from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from http.client import HTTPMessage
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "notify-garmin-sleep.py"
SPEC = importlib.util.spec_from_file_location("notify_garmin_sleep", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def run_script(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("OPENROUTER_API_KEY", None)
    kwargs.setdefault("env", env)
    return subprocess.run(*args, **kwargs)  # type: ignore[arg-type]


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
            "昨晚 23:18 睡，07:42 起，一共 7 小时 24 分，评分 82（良好）。"
            "深睡 1小时30分，浅睡 4小时，REM 1小时54分。静息心率 51。",
        )
        self.assertNotIn("\n", MODULE.format_sleep_message(summary))

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
        self.assertIn("23:18 睡，07:42 起", message)
        self.assertIn("一共 7 小时 24 分", message)
        self.assertNotIn("静息心率", message)
        self.assertNotIn("身体电量", message)
        self.assertNotIn("评分", message)
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
        self.assertNotIn("身体电量", message)
        self.assertNotIn("\n", message)

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

    def test_complete_sleep_has_ended_with_a_positive_duration(self) -> None:
        woke = datetime(2026, 10, 16, 7, 42, tzinfo=SHANGHAI)
        bundle = {
            "sleep": {
                "dailySleepDTO": {
                    "calendarDate": "2026-10-16",
                    "sleepTimeSeconds": 26640,
                    "sleepStartTimestampGMT": epoch_ms(
                        datetime(2026, 10, 15, 23, 18, tzinfo=SHANGHAI),
                    ),
                    "sleepEndTimestampGMT": epoch_ms(woke),
                    "sleepScores": {"overall": {"value": 82}},
                }
            }
        }
        now = datetime(2026, 10, 16, 8, 0, tzinfo=SHANGHAI)
        assessment = MODULE.assess_sleep(bundle, now=now, fallback_date="2026-10-16")
        self.assertTrue(assessment.complete)
        self.assertEqual(assessment.summary["woke_at"], woke)
        ended_at_now = MODULE.assess_sleep(bundle, now=woke, fallback_date="2026-10-16")
        self.assertTrue(ended_at_now.complete)
        self.assertEqual(
            MODULE.plan_sleep_notification(assessment, [], force=False),
            "send",
        )
        self.assertEqual(
            MODULE.plan_sleep_notification(assessment, ["2026-10-16"], force=False),
            "skip-already-sent",
        )
        self.assertEqual(
            MODULE.plan_sleep_notification(assessment, ["2026-10-16"], force=True),
            "send",
        )

    def test_incomplete_sleep_is_skipped_until_it_has_ended(self) -> None:
        now = datetime(2026, 10, 16, 8, 0, tzinfo=SHANGHAI)
        missing = MODULE.assess_sleep({}, now=now, fallback_date="2026-10-16")
        self.assertFalse(missing.complete)
        self.assertIn("dailySleepDTO", missing.reason)

        zero = MODULE.assess_sleep(
            {
                "sleep": {
                    "dailySleepDTO": {
                        "calendarDate": "2026-10-16",
                        "sleepTimeSeconds": 0,
                        "sleepEndTimestampGMT": epoch_ms(now),
                    }
                }
            },
            now=now,
            fallback_date="2026-10-16",
        )
        self.assertFalse(zero.complete)
        self.assertIn("sleepTimeSeconds", zero.reason)

        no_wake = MODULE.assess_sleep(
            {
                "sleep": {
                    "dailySleepDTO": {
                        "calendarDate": "2026-10-16",
                        "sleepTimeSeconds": 3600,
                    }
                }
            },
            now=now,
            fallback_date="2026-10-16",
        )
        self.assertFalse(no_wake.complete)
        self.assertEqual(no_wake.reason, "wake time is missing")

        still_asleep = MODULE.assess_sleep(
            {
                "sleep": {
                    "dailySleepDTO": {
                        "calendarDate": "2026-10-16",
                        "sleepTimeSeconds": 3600,
                        "sleepEndTimestampGMT": epoch_ms(
                            datetime(2026, 10, 16, 9, 0, tzinfo=SHANGHAI),
                        ),
                    }
                }
            },
            now=now,
            fallback_date="2026-10-16",
        )
        self.assertFalse(still_asleep.complete)
        self.assertEqual(still_asleep.reason, "sleep has not ended yet")
        self.assertEqual(
            MODULE.plan_sleep_notification(still_asleep, [], force=True),
            "skip-incomplete",
        )

        short_night = MODULE.assess_sleep(
            {
                "sleep": {
                    "dailySleepDTO": {
                        "calendarDate": "2026-10-16",
                        "sleepTimeSeconds": 3600,
                        "sleepEndTimestampGMT": epoch_ms(
                            datetime(2026, 10, 16, 7, 30, tzinfo=SHANGHAI),
                        ),
                        "sleepScores": {"overall": {"value": 91}},
                    }
                }
            },
            now=now,
            fallback_date="2026-10-16",
        )
        self.assertFalse(short_night.complete)
        self.assertEqual(short_night.reason, "total sleep is under 3 hours")
        self.assertEqual(
            MODULE.plan_sleep_notification(short_night, [], force=True),
            "skip-incomplete",
        )

        unscored = MODULE.assess_sleep(
            {
                "sleep": {
                    "dailySleepDTO": {
                        "calendarDate": "2026-10-16",
                        "sleepTimeSeconds": 28860,
                        "sleepEndTimestampGMT": epoch_ms(
                            datetime(2026, 10, 16, 7, 30, tzinfo=SHANGHAI),
                        ),
                    }
                }
            },
            now=now,
            fallback_date="2026-10-16",
        )
        self.assertFalse(unscored.complete)
        self.assertEqual(unscored.reason, "sleep score is missing")

    def test_sent_dates_keep_the_newest_entries(self) -> None:
        self.assertEqual(
            MODULE.remember_sent_date(["2026-10-14", "2026-10-15"], "2026-10-16", limit=2),
            ["2026-10-15", "2026-10-16"],
        )

    def test_cli_dry_run_prints_message_without_telegram(self) -> None:
        with self.subTest("fixture"):
            with tempfile.TemporaryDirectory() as directory:
                bundle = Path(directory) / "sleep.json"
                state = Path(directory) / "sleep-sent.json"
                bundle.write_text(
                    json.dumps(
                        {
                            "sleep": {
                                "dailySleepDTO": {
                                    "calendarDate": "2026-10-16",
                                    "sleepTimeSeconds": 10800,
                                    "sleepEndTimestampGMT": epoch_ms(
                                        datetime(2026, 10, 16, 7, 30, tzinfo=SHANGHAI),
                                    ),
                                    "sleepScores": {"overall": {"value": 80}},
                                }
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                result = run_script(
                    [
                        sys.executable,
                        str(SCRIPT_PATH),
                        "--input",
                        str(bundle),
                        "--state",
                        str(state),
                        "--now",
                        "2026-10-16T08:00:00+08:00",
                        "--dry-run",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("一共 3 小时", result.stdout)
                self.assertIn("评分 80", result.stdout)
                self.assertIn("文案来源: 固定模板", result.stdout)
                self.assertIn("Dry run; Telegram message not sent", result.stdout)
                self.assertNotIn("TELEGRAM_MEMOS_BOT_TOKEN", result.stdout + result.stderr)
                self.assertFalse(state.exists())

        result = run_script(
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
            missing = run_script(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(empty),
                    "--now",
                    "2026-10-16T08:00:00+08:00",
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(missing.returncode, 0, missing.stderr)
            self.assertIn("Skipping sleep notification", missing.stdout)
            self.assertIn("sleepTimeSeconds", missing.stdout)
            self.assertNotIn("总睡眠", missing.stdout)

    def test_cli_skips_a_date_already_sent_unless_forced(self) -> None:
        woke = epoch_ms(datetime(2026, 10, 16, 7, 30, tzinfo=SHANGHAI))
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "sleep.json"
            state = Path(directory) / "sleep-sent.json"
            bundle.write_text(
                json.dumps(
                    {
                        "sleep": {
                            "dailySleepDTO": {
                                "calendarDate": "2026-10-16",
                                "sleepTimeSeconds": 10800,
                                "sleepEndTimestampGMT": woke,
                                "sleepScores": {"overall": {"value": 80}},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            state.write_text(
                json.dumps({"sentDates": ["2026-10-16"]}, indent=2) + "\n",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(SCRIPT_PATH),
                "--input",
                str(bundle),
                "--state",
                str(state),
                "--now",
                "2026-10-16T10:00:00+08:00",
                "--dry-run",
            ]
            skipped = run_script(command, check=False, capture_output=True, text=True)
            self.assertEqual(skipped.returncode, 0, skipped.stderr)
            self.assertIn("already sent", skipped.stdout)
            self.assertNotIn("总睡眠", skipped.stdout)

            forced = run_script(
                [*command, "--force"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertIn("一共 3 小时", forced.stdout)
            self.assertIn("Dry run; Telegram message not sent", forced.stdout)
            self.assertEqual(
                json.loads(state.read_text(encoding="utf-8"))["sentDates"],
                ["2026-10-16"],
            )

    def test_records_the_date_after_a_successful_send(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "sleep.json"
            state = Path(directory) / "sleep-sent.json"
            bundle.write_text(
                json.dumps(
                    {
                        "sleep": {
                            "dailySleepDTO": {
                                "calendarDate": "2026-10-16",
                                "sleepTimeSeconds": 10800,
                                "sleepEndTimestampGMT": epoch_ms(
                                    datetime(2026, 10, 16, 7, 30, tzinfo=SHANGHAI),
                                ),
                                "sleepScores": {"overall": {"value": 80}},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            original = MODULE.telegram_memos.send_message
            argv = sys.argv
            previous_key = os.environ.pop("OPENROUTER_API_KEY", None)
            MODULE.telegram_memos.send_message = lambda message: None
            try:
                sys.argv = [
                    "notify-garmin-sleep.py",
                    "--input",
                    str(bundle),
                    "--state",
                    str(state),
                    "--now",
                    "2026-10-16T08:00:00+08:00",
                ]
                MODULE.main()
            finally:
                sys.argv = argv
                MODULE.telegram_memos.send_message = original
                if previous_key is None:
                    os.environ.pop("OPENROUTER_API_KEY", None)
                else:
                    os.environ["OPENROUTER_API_KEY"] = previous_key
            self.assertEqual(
                json.loads(state.read_text(encoding="utf-8"))["sentDates"],
                ["2026-10-16"],
            )


REAL_SLEEP_SECONDS = 8 * 3600 + 60
REAL_DEEP_SECONDS = 55 * 60
REAL_LIGHT_SECONDS = 5 * 3600 + 35 * 60
REAL_REM_SECONDS = 1 * 3600 + 32 * 60
REAL_AWAKE_SECONDS = 3 * 60


def real_night_dto(**overrides: object) -> dict:
    woke = datetime(2026, 10, 16, 7, 30, tzinfo=SHANGHAI)
    fell_asleep = datetime(2026, 10, 15, 23, 26, tzinfo=SHANGHAI)
    dto = {
        "calendarDate": "2026-10-16",
        "sleepTimeSeconds": REAL_SLEEP_SECONDS,
        "deepSleepSeconds": REAL_DEEP_SECONDS,
        "lightSleepSeconds": REAL_LIGHT_SECONDS,
        "remSleepSeconds": REAL_REM_SECONDS,
        "awakeSleepSeconds": REAL_AWAKE_SECONDS,
        "sleepStartTimestampGMT": epoch_ms(fell_asleep),
        "sleepEndTimestampGMT": epoch_ms(woke),
        "sleepScores": {"overall": {"value": 91, "qualifierKey": "EXCELLENT"}},
        "restingHeartRate": 56,
        "averageSleepHeartRate": 61,
        "bodyBatteryChange": 48,
        "avgSleepHRV": 65,
    }
    dto.update(overrides)
    return dto


class GarminSleepFieldFallbackTest(unittest.TestCase):
    def test_formats_the_china_export_for_2026_10_16(self) -> None:
        summary = MODULE.summarize_sleep(
            {"sleep": {"dailySleepDTO": real_night_dto()}},
            fallback_date="2026-10-16",
        )
        now = datetime(2026, 10, 16, 8, 0, tzinfo=SHANGHAI)
        assessment = MODULE.assess_sleep(
            {"sleep": {"dailySleepDTO": real_night_dto()}},
            now=now,
            fallback_date="2026-10-16",
        )

        self.assertTrue(assessment.complete)
        self.assertEqual(summary["total_sleep_seconds"], REAL_SLEEP_SECONDS)
        self.assertEqual(
            MODULE.format_sleep_message(summary),
            "昨晚 23:26 睡，07:30 起，一共 8 小时 1 分，评分 91（优秀）。"
            "深睡 55分，浅睡 5小时35分，REM 1小时32分，清醒 3分。"
            "静息心率 56，身体电量 +48，HRV 65ms。",
        )
        self.assertNotIn("\n", MODULE.format_sleep_message(summary))

    def test_prefers_a_full_night_when_sleep_time_seconds_is_a_fragment(self) -> None:
        woke = datetime(2026, 10, 16, 7, 30, tzinfo=SHANGHAI)
        summary = MODULE.summarize_sleep(
            {
                "sleep": {
                    "dailySleepDTO": {
                        "calendarDate": "2026-10-16",
                        "sleepTimeSeconds": 3600,
                        "sleepTimeInSeconds": REAL_SLEEP_SECONDS,
                        "deepSleepSeconds": REAL_DEEP_SECONDS,
                        "lightSleepSeconds": REAL_LIGHT_SECONDS,
                        "remSleepSeconds": REAL_REM_SECONDS,
                        "awakeSleepSeconds": REAL_AWAKE_SECONDS,
                        "sleepEndTimestampGMT": epoch_ms(woke),
                        "sleepScores": {
                            "overall": {"value": 91, "qualifierKey": "EXCELLENT"},
                        },
                    }
                }
            }
        )

        self.assertEqual(summary["total_sleep_seconds"], REAL_SLEEP_SECONDS)
        message = MODULE.format_sleep_message(summary)
        self.assertIn("一共 8 小时 1 分", message)
        self.assertNotIn("一共 1 小时", message)
        self.assertIn("23:26 睡", message)

    def test_reads_root_fields_and_sleep_levels_when_the_dto_is_a_fragment(self) -> None:
        woke = datetime(2026, 10, 16, 7, 30, tzinfo=SHANGHAI)
        base = 1_700_000_000
        cursor = base
        levels = []
        for activity, seconds in (
            (0, REAL_DEEP_SECONDS),
            (1, REAL_LIGHT_SECONDS),
            (2, REAL_REM_SECONDS),
            (3, REAL_AWAKE_SECONDS),
        ):
            levels.append(
                {
                    "activityLevel": activity,
                    "startTimeInSeconds": cursor,
                    "endTimeInSeconds": cursor + seconds,
                }
            )
            cursor += seconds
        bundle = {
            "sleep": {
                "dailySleepDTO": {
                    "calendarDate": "2026-10-16",
                    "userProfilePK": 424242,
                    "sleepTimeSeconds": 3600,
                    "sleepEndTimestampGMT": epoch_ms(woke),
                },
                "sleepTimeSeconds": REAL_SLEEP_SECONDS,
                "deepSleepSeconds": REAL_DEEP_SECONDS,
                "lightSleepSeconds": REAL_LIGHT_SECONDS,
                "remSleepSeconds": REAL_REM_SECONDS,
                "awakeSleepSeconds": REAL_AWAKE_SECONDS,
                "sleepLevels": levels,
                "sleepScores": {"overall": {"value": 91, "qualifierKey": "EXCELLENT"}},
                "restingHeartRate": 56,
                "avgHeartRate": 61,
                "bodyBatteryChange": 48,
                "avgOvernightHrv": 65,
            },
            "hrv": {"hrvSummary": {"lastNightAvg": 40}},
        }
        summary = MODULE.summarize_sleep(bundle)
        assessment = MODULE.assess_sleep(
            bundle,
            now=datetime(2026, 10, 16, 8, 0, tzinfo=SHANGHAI),
            fallback_date="2026-10-16",
        )

        self.assertTrue(assessment.complete)
        self.assertEqual(summary["total_sleep_seconds"], REAL_SLEEP_SECONDS)
        self.assertEqual(summary["deep_sleep_seconds"], REAL_DEEP_SECONDS)
        self.assertEqual(summary["average_hrv"], 65)
        self.assertEqual(summary["night_heart_rate"], 61)
        message = MODULE.format_sleep_message(summary)
        self.assertIn("一共 8 小时 1 分", message)
        self.assertIn("深睡 55分", message)
        self.assertIn("评分 91（优秀）", message)
        self.assertNotIn("424242", message)

    def test_sums_sleep_levels_when_stage_fields_are_missing(self) -> None:
        base = 1_700_000_000
        cursor = base
        levels = []
        for activity, seconds in (
            (0.0, REAL_DEEP_SECONDS),
            (1.0, REAL_LIGHT_SECONDS),
            (2.0, REAL_REM_SECONDS),
            (3.0, REAL_AWAKE_SECONDS),
        ):
            levels.append(
                {
                    "activityLevel": activity,
                    "startGMT": datetime.fromtimestamp(cursor, timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%S.0",
                    ),
                    "endGMT": datetime.fromtimestamp(
                        cursor + seconds,
                        timezone.utc,
                    ).strftime("%Y-%m-%dT%H:%M:%S.0"),
                }
            )
            cursor += seconds
        summary = MODULE.summarize_sleep(
            {
                "sleep": {
                    "dailySleepDTO": {
                        "calendarDate": "2026-10-16",
                        "sleepTimeSeconds": 3600,
                        "sleepEndTimestampGMT": epoch_ms(
                            datetime(2026, 10, 16, 7, 30, tzinfo=SHANGHAI),
                        ),
                        "sleepScores": {"overall": {"value": 91}},
                    },
                    "sleepLevels": levels,
                }
            }
        )

        self.assertEqual(
            summary["total_sleep_seconds"],
            REAL_DEEP_SECONDS + REAL_LIGHT_SECONDS + REAL_REM_SECONDS,
        )
        self.assertEqual(summary["rem_sleep_seconds"], REAL_REM_SECONDS)
        self.assertEqual(summary["awake_sleep_seconds"], REAL_AWAKE_SECONDS)
        self.assertIn("一共 8 小时 2 分", MODULE.format_sleep_message(summary))

    def test_reads_a_nested_sleep_time_seconds_object(self) -> None:
        summary = MODULE.summarize_sleep(
            {
                "sleep": {
                    "dailySleepDTO": real_night_dto(
                        sleepTimeSeconds={"seconds": REAL_SLEEP_SECONDS},
                    ),
                }
            }
        )
        self.assertEqual(summary["total_sleep_seconds"], REAL_SLEEP_SECONDS)

    def test_hrv_falls_back_to_get_hrv_data_summary(self) -> None:
        summary = MODULE.summarize_sleep(
            {
                "sleep": {"dailySleepDTO": real_night_dto(avgSleepHRV=None)},
                "hrv": {"hrvSummary": {"lastNightAvg": 65}},
            }
        )
        self.assertEqual(summary["average_hrv"], 65)

    def test_debug_snapshot_keeps_metrics_and_drops_identifiers(self) -> None:
        lines = MODULE.debug_sleep_lines(
            {
                "dailySleepDTO": {
                    "userProfilePK": 12345,
                    "displayName": "someone@example.com",
                    "calendarDate": "2026-10-16",
                    "sleepTimeSeconds": 3600,
                    "sleepScores": {
                        "overall": {"value": 91, "qualifierKey": "EXCELLENT"},
                    },
                    "sleepMovement": [{"start": 1}] * 20,
                },
                "avgOvernightHrv": 65,
                "restingHeartRate": 56,
            }
        )
        text = "\n".join(lines)
        self.assertIn("sleepTimeSeconds=3600", text)
        self.assertIn("91", text)
        self.assertIn("root.avgOvernightHrv=65", text)
        self.assertIn("root.restingHeartRate=56", text)
        self.assertNotIn("12345", text)
        self.assertNotIn("someone@example.com", text)
        self.assertNotIn("userProfilePK", text)
        self.assertNotIn("sleepMovement", text)

    def test_cli_skips_the_one_hour_fragment_seen_in_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "sleep.json"
            bundle.write_text(
                json.dumps(
                    {
                        "sleep": {
                            "dailySleepDTO": {
                                "calendarDate": "2026-10-16",
                                "userProfilePK": 8675309,
                                "displayName": "person@example.com",
                                "sleepTimeSeconds": 3600,
                                "sleepEndTimestampGMT": epoch_ms(
                                    datetime(2026, 10, 16, 7, 30, tzinfo=SHANGHAI),
                                ),
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            result = run_script(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(bundle),
                    "--now",
                    "2026-10-16T08:00:00+08:00",
                    "--dry-run",
                    "--force",
                    "--debug",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("total sleep is under 3 hours", result.stdout)
        self.assertIn("sleepTimeSeconds=3600", result.stdout)
        self.assertNotIn("总睡眠 1小时", result.stdout)
        self.assertNotIn("8675309", result.stdout)
        self.assertNotIn("person@example.com", result.stdout)
        self.assertNotIn("Dry run; Telegram message not sent", result.stdout)


AI_NARRATIVE = (
    "昨晚睡得踏实，一共 8 小时，评分 91。"
    "跳舞和力量训练之后这样够恢复，今天力量可以照常安排，不要再额外加量。"
)


def llm_summary() -> dict:
    return {
        "date": "2026-10-16",
        "fell_asleep_at": datetime(2026, 10, 15, 23, 26, tzinfo=SHANGHAI),
        "woke_at": datetime(2026, 10, 16, 7, 30, tzinfo=SHANGHAI),
        "total_sleep_seconds": 8 * 3600 + 60,
        "deep_sleep_seconds": 55 * 60,
        "light_sleep_seconds": 5 * 3600 + 35 * 60,
        "rem_sleep_seconds": 92 * 60,
        "awake_sleep_seconds": 3 * 60,
        "sleep_score": 91,
        "sleep_score_qualifier": "EXCELLENT",
        "resting_heart_rate": 56,
        "night_heart_rate": 61,
        "body_battery": 80,
        "body_battery_change": 48,
        "average_hrv": 65,
    }


class Response:
    def __init__(self, payload: dict) -> None:
        self.raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read(self) -> bytes:
        return self.raw

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def chat_response(content: object, reasoning: str | None = None) -> Response:
    message: dict[str, object] = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return Response({"choices": [{"message": message}]})


class ScriptedOpener:
    def __init__(self, steps: list[object]) -> None:
        self.steps = list(steps)
        self.calls: list[object] = []
        self.timeouts: list[int] = []

    def __call__(self, request: object, timeout: int = 45) -> Response:
        self.timeouts.append(timeout)
        self.calls.append(request)
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step  # type: ignore[return-value]


class SleepCopyGenerationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.previous = os.environ.get("OPENROUTER_API_KEY")
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test-secret"

    def tearDown(self) -> None:
        if self.previous is None:
            os.environ.pop("OPENROUTER_API_KEY", None)
        else:
            os.environ["OPENROUTER_API_KEY"] = self.previous

    def compose(self, opener: ScriptedOpener) -> tuple[object, str]:
        stdout = io.StringIO()
        with _redirect(stdout):
            copy = MODULE.compose_sleep_message(llm_summary(), opener=opener)
        return copy, stdout.getvalue()

    def test_llm_success_keeps_script_data_as_the_second_paragraph(self) -> None:
        opener = ScriptedOpener(
            [chat_response(f"<think>先看时长</think>{AI_NARRATIVE}")]
        )
        copy, logs = self.compose(opener)
        summary = llm_summary()
        data = MODULE.format_sleep_data(summary)
        self.assertEqual(copy.source, "llm")
        self.assertEqual(copy.attempt, 1)
        self.assertEqual(copy.text, f"{AI_NARRATIVE}\n\n{data}")
        self.assertTrue(copy.text.startswith(AI_NARRATIVE))
        self.assertIn("深睡 55分 · 浅睡 5小时35分 · REM 1小时32分 · 清醒 3分", copy.text)
        self.assertIn("静息心率 56 · 身体电量 +48 · HRV 65ms", copy.text)
        self.assertNotIn("夜间平均心率", copy.text)
        self.assertNotIn("身体电量 80", copy.text)
        self.assertNotIn("<think>", copy.text)
        self.assertNotIn("sk-or-test-secret", logs)
        self.assertEqual(MODULE.describe_sleep_copy(copy), "文案来源: AI（第 1 次尝试）")
        request = opener.calls[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "openrouter/free")
        self.assertEqual(body["temperature"], 0.3)
        self.assertEqual(body["max_tokens"], 512)
        self.assertIn("跳舞", body["messages"][0]["content"])
        self.assertIn("力量训练", body["messages"][0]["content"])
        self.assertIn("示例一", body["messages"][0]["content"])
        self.assertIn("不要罗列指标", body["messages"][1]["content"])
        self.assertIn("不要写日期", body["messages"][1]["content"])
        self.assertEqual(opener.timeouts, [60])
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-or-test-secret")

    def test_uses_reasoning_content_when_content_is_empty(self) -> None:
        opener = ScriptedOpener([chat_response(None, AI_NARRATIVE)])
        copy, _logs = self.compose(opener)
        self.assertEqual(copy.source, "llm")
        self.assertTrue(copy.text.startswith(AI_NARRATIVE))

    def test_third_attempt_succeeds_after_two_failures(self) -> None:
        opener = ScriptedOpener(
            [
                urllib.error.URLError("timed out"),
                urllib.error.HTTPError(
                    MODULE.OPENROUTER_URL,
                    500,
                    "error",
                    HTTPMessage(),
                    io.BytesIO(b"upstream failed"),
                ),
                chat_response(AI_NARRATIVE),
            ]
        )
        copy, logs = self.compose(opener)
        self.assertEqual(copy.source, "llm")
        self.assertEqual(copy.attempt, 3)
        self.assertIn(AI_NARRATIVE, copy.text)
        self.assertIn("\n\n", copy.text)
        self.assertIn("OpenRouter 第 1 次失败", logs)
        self.assertIn("OpenRouter 第 2 次失败", logs)
        self.assertIn("HTTP 500", logs)
        self.assertNotIn("sk-or-test-secret", logs)
        self.assertEqual(len(opener.calls), 3)
        self.assertEqual(MODULE.describe_sleep_copy(copy), "文案来源: AI（第 3 次尝试）")

    def test_three_failures_use_the_single_paragraph_template(self) -> None:
        opener = ScriptedOpener(
            [
                urllib.error.URLError("timed out"),
                urllib.error.HTTPError(
                    MODULE.OPENROUTER_URL,
                    429,
                    "error",
                    HTTPMessage(),
                    io.BytesIO(b"slow down"),
                ),
                chat_response(""),
            ]
        )
        copy, logs = self.compose(opener)
        summary = llm_summary()
        self.assertEqual(copy.source, "fallback")
        self.assertIsNone(copy.attempt)
        self.assertEqual(copy.text, MODULE.format_sleep_message(summary))
        self.assertNotIn("\n", copy.text)
        self.assertIn("昨晚 23:26 睡，07:30 起", copy.text)
        self.assertIn("一共 8 小时 1 分", copy.text)
        self.assertIn("评分 91（优秀）", copy.text)
        self.assertIn("OpenRouter 3 次都失败，改用固定模板。", logs)
        self.assertNotIn("sk-or-test-secret", logs)
        self.assertEqual(MODULE.describe_sleep_copy(copy), "文案来源: 固定模板")

    def test_listing_style_output_counts_as_a_failed_attempt(self) -> None:
        listing = (
            "2026-10-16 睡8小时2分，评分91，深睡55分，浅睡5小时35分，"
            "REM1小时32分，清醒3分，静息56，夜间61，电量+48，HRV65，"
            "恢复良好，建议排练后适度伸展、补水。"
        )
        opener = ScriptedOpener([chat_response(listing), chat_response(AI_NARRATIVE)])
        copy, logs = self.compose(opener)
        self.assertEqual(copy.source, "llm")
        self.assertEqual(copy.attempt, 2)
        self.assertTrue(copy.text.startswith(AI_NARRATIVE))
        self.assertIn("output starts with a date", logs)
        self.assertEqual(len(opener.calls), 2)

    def test_rejects_a_date_a_metric_list_and_a_run_on_line(self) -> None:
        summary = llm_summary()
        with self.assertRaises(MODULE.SleepCopyError) as started:
            MODULE.validate_narrative(
                "2026-10-16 昨晚睡得踏实。跳舞和力量训练之后这样够恢复，今天可以照常安排，别再额外加量。",
                summary,
            )
        self.assertIn("date", str(started.exception))

        with self.assertRaises(MODULE.SleepCopyError) as listed:
            MODULE.validate_narrative(
                "昨晚睡了 8 小时，评分 91，深睡 55 分，心率 56。今天排练之后可以照常做力量训练，别再加量。",
                summary,
            )
        self.assertIn("too many numbers", str(listed.exception))

        with self.assertRaises(MODULE.SleepCopyError) as unpunctuated:
            MODULE.validate_narrative(
                "昨晚睡得踏实一共八小时评分也不错跳舞和力量训练之后恢复够用今天可以照常安排别再加量就好",
                summary,
            )
        self.assertIn("enough sentences", str(unpunctuated.exception))

        with self.assertRaises(MODULE.SleepCopyError) as too_long:
            MODULE.validate_narrative("昨晚睡得还行。" * 40, summary)
        self.assertIn("length", str(too_long.exception))

    def test_invalid_numbers_fall_back_to_the_template(self) -> None:
        opener = ScriptedOpener([chat_response(f"{AI_NARRATIVE}再补 12 小时。")] * 3)
        copy, logs = self.compose(opener)
        self.assertEqual(copy.source, "fallback")
        self.assertEqual(copy.text, MODULE.format_sleep_message(llm_summary()))
        self.assertNotIn("\n\n", copy.text)
        self.assertIn("numbers that were not provided: 12", logs)
        self.assertEqual(len(opener.calls), 3)

    def test_missing_key_uses_the_template_without_calling_the_network(self) -> None:
        os.environ.pop("OPENROUTER_API_KEY", None)
        opener = ScriptedOpener([])
        copy, logs = self.compose(opener)
        self.assertEqual(copy.source, "fallback")
        self.assertEqual(copy.text, MODULE.format_sleep_message(llm_summary()))
        self.assertEqual(opener.calls, [])
        self.assertIn("未设置 OPENROUTER_API_KEY", logs)


def _redirect(stdout: io.StringIO):
    import contextlib

    return contextlib.redirect_stdout(stdout)
