from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "fetch-garmin-workouts.py"
SPEC = importlib.util.spec_from_file_location("fetch_garmin_workouts", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GarminWorkoutSynchronizationTest(unittest.TestCase):
    def test_normalizes_garmin_activities(self) -> None:
        self.assertEqual(
            MODULE.normalize_garmin_activities(
                [
                    {
                        "activityId": 101,
                        "activityName": "Easy Run",
                        "activityType": {"typeKey": "running"},
                        "startTimeLocal": "2026-07-08 07:30:00",
                        "duration": 1800.4,
                        "calories": 359.6,
                    }
                ]
            ),
            [
                {
                    "externalId": "101",
                    "name": "Easy Run",
                    "activityDate": "2026-07-08",
                    "durationSeconds": 1800,
                    "caloriesKcal": 360,
                }
            ],
        )

    def test_coerces_garmin_numbers_and_trims_external_id(self) -> None:
        workout = MODULE.normalize_garmin_activities(
            [
                {
                    "activityId": " 101 ",
                    "activityName": "Easy Run",
                    "startTimeLocal": "2026-07-08 07:30:00",
                    "duration": "1800.4",
                    "calories": "359.6",
                }
            ]
        )[0]
        self.assertEqual(workout["externalId"], "101")
        self.assertEqual(workout["durationSeconds"], 1800)
        self.assertEqual(workout["caloriesKcal"], 360)

    def test_uses_readable_activity_type_when_name_is_missing(self) -> None:
        workout = MODULE.normalize_garmin_activities(
            [
                {
                    "activityId": "102",
                    "activityType": {"typeKey": "strength_training"},
                    "startTimeLocal": "2026-07-09 18:00:00",
                    "duration": 1200,
                    "calories": 180,
                }
            ]
        )[0]
        self.assertEqual(workout["name"], "力量训练")

    def test_accepts_archived_payload_wrappers(self) -> None:
        workout = MODULE.normalize_garmin_activities(
            {
                "payload": [
                    {
                        "activityId": "103",
                        "activityName": "舞蹈健身",
                        "startTimeLocal": "2026-07-10 20:00:00",
                        "duration": 2400,
                        "calories": 260,
                    }
                ]
            }
        )[0]
        self.assertEqual(workout["externalId"], "103")

    def test_updates_matching_activities_and_preserves_history(self) -> None:
        merged = MODULE.merge_workouts(
            [
                {
                    "externalId": "100",
                    "name": "旧活动",
                    "activityDate": "2026-07-01",
                    "durationSeconds": 600,
                    "caloriesKcal": 100,
                },
                {
                    "externalId": "101",
                    "name": "Before edit",
                    "activityDate": "2026-07-08",
                    "durationSeconds": 1800,
                    "caloriesKcal": 300,
                },
            ],
            [
                {
                    "externalId": "101",
                    "name": "After edit",
                    "activityDate": "2026-07-08",
                    "durationSeconds": 1810,
                    "caloriesKcal": 360,
                }
            ],
        )
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["name"], "After edit")
        self.assertEqual(merged[1]["externalId"], "100")

    def test_cli_imports_and_merges_snapshot_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "workouts.json"
            output.write_text(
                json.dumps(
                    [
                        {
                            "externalId": "100",
                            "name": "历史活动",
                            "activityDate": "2026-07-01",
                            "durationSeconds": 600,
                            "caloriesKcal": 100,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            incoming = Path(directory) / "incoming.json"
            incoming.write_text(
                json.dumps(
                    [
                        {
                            "externalId": "101",
                            "name": "新活动",
                            "activityDate": "2026-07-08",
                            "durationSeconds": 1200,
                            "caloriesKcal": 200,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--merge",
                    "--input",
                    str(incoming),
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            workouts = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual([workout["externalId"] for workout in workouts], ["101", "100"])


if __name__ == "__main__":
    unittest.main()
