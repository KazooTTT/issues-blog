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
GARMIN_OPTIONAL_FIELDS = {
    "startTimeLocal": ("startTimeLocal", "string"),
    "startTimeGmt": ("startTimeGMT", "string"),
    "activityType": ("activityType.typeKey", "string"),
    "movingDurationSeconds": ("movingDuration", "number"),
    "elapsedDurationSeconds": ("elapsedDuration", "number"),
    "distanceMeters": ("distance", "number"),
    "elevationGainMeters": ("elevationGain", "number"),
    "elevationLossMeters": ("elevationLoss", "number"),
    "averageSpeedMps": ("averageSpeed", "number"),
    "maxSpeedMps": ("maxSpeed", "number"),
    "averageHeartRateBpm": ("averageHR", "number"),
    "maxHeartRateBpm": ("maxHR", "number"),
    "bmrCaloriesKcal": ("bmrCalories", "number"),
    "averagePowerWatts": ("avgPower", "number"),
    "maxPowerWatts": ("maxPower", "number"),
    "normalizedPowerWatts": ("normPower", "number"),
    "aerobicTrainingEffect": ("aerobicTrainingEffect", "number"),
    "anaerobicTrainingEffect": ("anaerobicTrainingEffect", "number"),
    "trainingLoad": ("activityTrainingLoad", "number"),
    "trainingEffectLabel": ("trainingEffectLabel", "string"),
    "averageRunningCadenceSpm": (
        "averageRunningCadenceInStepsPerMinute",
        "number",
    ),
    "maxRunningCadenceSpm": (
        "maxRunningCadenceInStepsPerMinute",
        "number",
    ),
    "totalSets": ("totalSets", "integer"),
    "activeSets": ("activeSets", "integer"),
    "totalReps": ("totalReps", "integer"),
    "totalVolume": ("totalVolume", "number"),
}
SNAPSHOT_OPTIONAL_FIELD_TYPES = {
    field: field_type for field, (_, field_type) in GARMIN_OPTIONAL_FIELDS.items()
}
TRAINING_DETAIL_METHODS = {
    "heartRateZones": "get_activity_hr_in_timezones",
    "powerZones": "get_activity_power_in_timezones",
    "splits": "get_activity_splits",
    "typedSplits": "get_activity_typed_splits",
    "splitSummaries": "get_activity_split_summaries",
    "exerciseSets": "get_activity_exercise_sets",
}
PRIVATE_LOCATION_KEY_PARTS = (
    "latitude",
    "longitude",
    "polyline",
    "geolocation",
    "location",
    "coordinate",
    "gps",
    "position",
    "point",
    "address",
    "place",
    "weather",
    "device",
    "gear",
    "equipment",
)
PRIVATE_LOCATION_KEYS = {
    "lat",
    "lon",
    "lng",
    "startlat",
    "startlon",
    "startlng",
    "endlat",
    "endlon",
    "endlng",
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


def non_negative_number(
    value: Any,
    field: str,
    *,
    coerce: bool = False,
) -> float:
    if coerce and isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            pass
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return value


def nested_value(activity: dict[str, Any], path: str) -> Any:
    value: Any = activity
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def optional_garmin_details(activity: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    for output_field, (source_path, field_type) in GARMIN_OPTIONAL_FIELDS.items():
        value = nested_value(activity, source_path)
        if value is None:
            continue
        if field_type == "string":
            if isinstance(value, str) and value.strip():
                details[output_field] = value.strip()
            continue
        if field_type == "integer":
            try:
                details[output_field] = rounded_non_negative(
                    value,
                    source_path,
                    coerce=True,
                )
            except ValueError as error:
                print(f"Skipping optional Garmin field {source_path}: {error}", file=sys.stderr)
            continue
        try:
            details[output_field] = non_negative_number(
                value,
                source_path,
                coerce=True,
            )
        except ValueError as error:
            print(f"Skipping optional Garmin field {source_path}: {error}", file=sys.stderr)
    return details


def scrub_location_data(value: Any) -> Any:
    if isinstance(value, list):
        return [scrub_location_data(item) for item in value]
    if not isinstance(value, dict):
        return value

    scrubbed = {}
    for key, item in value.items():
        normalized_key = "".join(character for character in key.lower() if character.isalnum())
        if normalized_key in PRIVATE_LOCATION_KEYS or any(
            part in normalized_key for part in PRIVATE_LOCATION_KEY_PARTS
        ):
            continue
        scrubbed[key] = scrub_location_data(item)
    return scrubbed


def optional_snapshot_details(workout: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    for field, field_type in SNAPSHOT_OPTIONAL_FIELD_TYPES.items():
        value = workout.get(field)
        if value is None:
            continue
        if field_type == "string":
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")
            details[field] = value.strip()
            continue
        if field_type == "integer":
            details[field] = rounded_non_negative(value, field)
            continue
        details[field] = non_negative_number(value, field)
    training_details = workout.get("trainingDetails")
    if training_details is not None:
        if not isinstance(training_details, dict):
            raise ValueError("trainingDetails must be an object")
        details["trainingDetails"] = scrub_location_data(training_details)
    return details


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
                **optional_garmin_details(activity),
                **(
                    {
                        "trainingDetails": scrub_location_data(
                            activity["trainingDetails"],
                        )
                    }
                    if isinstance(activity.get("trainingDetails"), dict)
                    else {}
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
            **optional_snapshot_details(workout),
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


def fetch_training_details(
    client: Any,
    activity_id: str | int,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    training_details = dict(previous or {})
    unavailable = []
    training_details.pop("_sync", None)
    for detail_key, method_name in TRAINING_DETAIL_METHODS.items():
        try:
            detail = getattr(client, method_name)(activity_id)
        except Exception as error:
            unavailable.append(detail_key)
            print(
                f"Keeping previous {detail_key} for activity {activity_id}: {error}",
                file=sys.stderr,
            )
            continue
        if detail:
            training_details[detail_key] = scrub_location_data(detail)
        else:
            training_details.pop(detail_key, None)
    if unavailable:
        training_details["_sync"] = {"unavailable": unavailable}
    return training_details


def fetch_activities(
    start: str,
    end: str,
    previous_training_details: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
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
    activities = client.get_activities_by_date(start, end)
    for activity in activities:
        activity_id = activity.get("activityId")
        if not activity_id:
            continue
        previous = (previous_training_details or {}).get(str(activity_id))
        training_details = fetch_training_details(client, activity_id, previous)
        if training_details:
            activity["trainingDetails"] = training_details
    return activities


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
        current = (
            normalize_workouts(
                json.loads(args.output.read_text(encoding="utf-8")),
            )
            if args.merge and args.output.exists()
            else []
        )
        previous_training_details = {
            workout["externalId"]: workout["trainingDetails"]
            for workout in current
            if isinstance(workout.get("trainingDetails"), dict)
        }
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        start = today - timedelta(days=args.days - 1)
        activities = fetch_activities(
            start.isoformat(),
            today.isoformat(),
            previous_training_details,
        )
        incoming = normalize_garmin_activities(activities)
        source_summary = (
            f"Fetched {len(activities)} Garmin activities from {start} to {today}"
        )
    workouts = incoming
    if args.merge and args.output.exists():
        current = normalize_workouts(json.loads(args.output.read_text(encoding="utf-8")))
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
