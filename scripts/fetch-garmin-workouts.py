from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ACTIVITY_TYPE_NAMES = {
    "cardio": "有氧运动",
    "dance": "舞蹈健身",
    "hiit": "HIIT",
    "strength_training": "力量训练",
    "treadmill_running": "跑步机",
    "walking": "步行",
}


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def rounded_non_negative(
    value: Any,
    field: str,
    default: float | None = None,
    *,
    coerce: bool = False,
) -> int:
    if value is None and default is not None:
        value = default
    if coerce and isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            pass
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return math.floor(value + 0.5)


def normalized_name(activity: dict[str, Any]) -> str:
    name = activity.get("activityName")
    if isinstance(name, str) and name.strip():
        return name.strip()

    activity_type = activity.get("activityType")
    type_key = (
        activity_type.get("typeKey", "")
        if isinstance(activity_type, dict)
        else ""
    )
    if not isinstance(type_key, str):
        type_key = ""
    return ACTIVITY_TYPE_NAMES.get(
        type_key,
        type_key.replace("_", " ").strip() or "Garmin 活动",
    )


def normalize_garmin_activities(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("activities", payload.get("payload"))
    if not isinstance(payload, list):
        raise ValueError("Garmin payload must contain an activity list")

    workouts = []
    for activity in payload:
        if not isinstance(activity, dict):
            raise ValueError("Each Garmin activity must be an object")
        activity_id = activity.get("activityId")
        start_time = activity.get("startTimeLocal")
        if (
            isinstance(activity_id, bool)
            or not isinstance(activity_id, str | int)
            or not str(activity_id).strip()
        ):
            raise ValueError("activityId must be a non-empty string or number")
        if not isinstance(start_time, str) or len(start_time) < 10:
            raise ValueError("startTimeLocal must include a date")

        external_id = str(activity_id).strip()
        workouts.append(
            {
                "externalId": external_id,
                "name": normalized_name(activity),
                "activityDate": start_time[:10],
                "durationSeconds": rounded_non_negative(
                    activity.get("duration"),
                    "duration",
                    coerce=True,
                ),
                "caloriesKcal": rounded_non_negative(
                    activity.get("calories"),
                    "calories",
                    default=0,
                    coerce=True,
                ),
            }
        )
    return normalize_workouts(workouts)


def normalize_workouts(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("workouts")
    if not isinstance(payload, list):
        raise ValueError("Workout snapshot must be a list")

    unique: dict[str, dict[str, Any]] = {}
    for workout in payload:
        if not isinstance(workout, dict):
            raise ValueError("Each workout must be an object")
        external_id = workout.get("externalId")
        name = workout.get("name")
        activity_date = workout.get("activityDate")
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("externalId must be a non-empty string")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if (
            not isinstance(activity_date, str)
            or len(activity_date) != 10
            or activity_date[4] != "-"
            or activity_date[7] != "-"
        ):
            raise ValueError("activityDate must use YYYY-MM-DD")
        normalized_external_id = external_id.strip()
        unique[normalized_external_id] = {
            "externalId": normalized_external_id,
            "name": name.strip(),
            "activityDate": activity_date,
            "durationSeconds": rounded_non_negative(
                workout.get("durationSeconds"),
                "durationSeconds",
            ),
            "caloriesKcal": rounded_non_negative(
                workout.get("caloriesKcal"),
                "caloriesKcal",
            ),
        }

    return sorted(
        unique.values(),
        key=lambda workout: (workout["activityDate"], workout["externalId"]),
        reverse=True,
    )


def merge_workouts(
    current: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return normalize_workouts([*current, *incoming])


def fetch_activities(start: str, end: str) -> list[dict[str, Any]]:
    from garminconnect import Garmin

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        raise SystemExit("GARMIN_EMAIL and GARMIN_PASSWORD are required")

    client = Garmin(
        email,
        password,
        is_cn=env_bool("GARMIN_IS_CN", default=True),
    )
    client.login()
    return client.get_activities_by_date(start, end)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and merge recent Garmin activities.",
    )
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument(
        "--input",
        help="Import workout JSON from a file, or use - for stdin instead of Garmin.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("src/data/workouts.json"),
    )
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()

    if args.days < 1:
        parser.error("--days must be at least 1")

    if args.input:
        source = (
            sys.stdin.read()
            if args.input == "-"
            else Path(args.input).read_text(encoding="utf-8")
        )
        incoming = normalize_workouts(json.loads(source))
        source_summary = f"Imported {len(incoming)} workouts"
    else:
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        start = today - timedelta(days=args.days - 1)
        activities = fetch_activities(start.isoformat(), today.isoformat())
        incoming = normalize_garmin_activities(activities)
        source_summary = (
            f"Fetched {len(activities)} Garmin activities from {start} to {today}"
        )
    workouts = incoming
    if args.merge and args.output.exists():
        current = normalize_workouts(
            json.loads(args.output.read_text(encoding="utf-8")),
        )
        workouts = merge_workouts(current, incoming)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f"{json.dumps(workouts, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )
    print(
        f"{source_summary}; synced {len(workouts)} workouts to {args.output}"
    )


if __name__ == "__main__":
    main()
