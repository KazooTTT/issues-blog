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
                    "睡眠评分 82（良好）",
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
                result = subprocess.run(
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
                self.assertIn("总睡眠 3小时", result.stdout)
                self.assertIn("睡眠评分 80", result.stdout)
                self.assertIn("Dry run; Telegram message not sent", result.stdout)
                self.assertNotIn("TELEGRAM_MEMOS_BOT_TOKEN", result.stdout + result.stderr)
                self.assertFalse(state.exists())

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
            skipped = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(skipped.returncode, 0, skipped.stderr)
            self.assertIn("already sent", skipped.stdout)
            self.assertNotIn("总睡眠", skipped.stdout)

            forced = subprocess.run(
                [*command, "--force"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertIn("总睡眠 3小时", forced.stdout)
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
            "\n".join(
                [
                    "睡眠 10月16日",
                    "起床 07:30",
                    "入眠 10月15日 23:26",
                    "总睡眠 8小时1分",
                    "深睡 55分 · 浅睡 5小时35分 · REM 1小时32分",
                    "清醒 3分",
                    "睡眠评分 91（优秀）",
                    "静息心率 56",
                    "夜间平均心率 61",
                    "身体电量变化 +48",
                    "平均 HRV 65ms",
                ]
            ),
        )

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
        self.assertIn("总睡眠 8小时1分", message)
        self.assertNotIn("总睡眠 1小时", message)
        self.assertIn("入眠 10月15日 23:26", message)

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
        self.assertIn("总睡眠 8小时1分", message)
        self.assertIn("深睡 55分", message)
        self.assertIn("睡眠评分 91（优秀）", message)
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
        self.assertIn("总睡眠 8小时2分", MODULE.format_sleep_message(summary))

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
            result = subprocess.run(
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
