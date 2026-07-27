from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from garminconnect import Garmin


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch recent Garmin activities.")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.days < 1:
        parser.error("--days must be at least 1")

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        raise SystemExit("GARMIN_EMAIL and GARMIN_PASSWORD are required")

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    start = today - timedelta(days=args.days - 1)
    client = Garmin(
        email,
        password,
        is_cn=env_bool("GARMIN_IS_CN", default=True),
    )
    client.login()
    activities = client.get_activities_by_date(start.isoformat(), today.isoformat())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"activities": activities}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Fetched {len(activities)} Garmin activities from {start} to {today}")


if __name__ == "__main__":
    main()
