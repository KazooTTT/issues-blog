from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import telegram_memos

SHANGHAI = ZoneInfo("Asia/Shanghai")
WAKE_MATCH_WINDOW_MS = 5 * 60 * 1000
DEFAULT_STATE_PATH = Path("data/telegram/sleep-sent.json")
MAX_SENT_DATES = 60


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def rounded_non_negative(value: Any) -> int | None:
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if value < 0:
        return None
    return math.floor(value + 0.5)


def optional_score(value: Any) -> int | None:
    number = rounded_non_negative(value)
    if number is None or number > 100:
        return None
    return number


def optional_heart_rate(value: Any) -> int | None:
    number = rounded_non_negative(value)
    if number is None or number <= 0 or number > 250:
        return None
    return number


def epoch_ms(value: Any) -> int | None:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if value <= 0:
        return None
    if value < 10**11:
        return int(value * 1000)
    return int(value)


def parse_timestamp(value: Any, *, local_wall: bool) -> datetime | None:
    """Parse a Garmin sleep timestamp.

    GMT fields are absolute instants. China-region local fields can be shifted
    by the timezone twice, so a missing GMT value is read as a wall clock in
    Asia/Shanghai instead of being converted again.
    """
    if isinstance(value, str):
        text = value.strip()
        if text and not text.replace(".", "", 1).isdigit():
            normalized = text.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=SHANGHAI if local_wall else timezone.utc,
                )
            return parsed
    millis = epoch_ms(value)
    if millis is None:
        return None
    moment = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
    if local_wall:
        return moment.replace(tzinfo=SHANGHAI)
    return moment


def daily_sleep_dto(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    dto = payload.get("dailySleepDTO")
    if isinstance(dto, dict):
        return dto
    if any(
        key in payload
        for key in (
            "sleepTimeSeconds",
            "sleepStartTimestampGMT",
            "sleepEndTimestampGMT",
        )
    ):
        return payload
    return {}


def extract_sleep_score(dto: dict[str, Any]) -> int | None:
    scores = dto.get("sleepScores")
    if isinstance(scores, dict):
        overall = scores.get("overall")
        if isinstance(overall, dict):
            score = optional_score(overall.get("value"))
            if score is not None:
                return score
        elif overall is not None:
            score = optional_score(overall)
            if score is not None:
                return score
        for key in ("overallScore", "totalScore", "sleepScore"):
            if key in scores:
                score = optional_score(scores.get(key))
                if score is not None:
                    return score
    for key in ("sleepScore", "overallSleepScore"):
        if key in dto:
            score = optional_score(dto.get(key))
            if score is not None:
                return score
    return None


def resting_heart_rate_from_metrics(payload: Any) -> int | None:
    entries: list[Any]
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        metrics_map = payload.get("allMetrics")
        if isinstance(metrics_map, dict):
            metrics_map = metrics_map.get("metricsMap")
        series = None
        if isinstance(metrics_map, dict):
            series = metrics_map.get("WELLNESS_RESTING_HEART_RATE")
        entries = series if isinstance(series, list) else [payload]
    else:
        return None
    for item in entries:
        if not isinstance(item, dict):
            continue
        for key in ("restingHeartRate", "restingHR", "value"):
            value = optional_heart_rate(item.get(key))
            if value is not None:
                return value
    return None


def extract_resting_heart_rate(
    dto: dict[str, Any],
    stats: Any,
    rhr_payload: Any,
) -> int | None:
    candidates = [dto.get("restingHeartRate")]
    if isinstance(stats, dict):
        candidates.append(stats.get("restingHeartRate"))
    for candidate in candidates:
        value = optional_heart_rate(candidate)
        if value is not None:
            return value
    return resting_heart_rate_from_metrics(rhr_payload)


def body_battery_samples(payload: Any) -> list[tuple[int, int]]:
    days: list[Any]
    if isinstance(payload, list):
        days = payload
    elif isinstance(payload, dict) and isinstance(
        payload.get("bodyBatteryValuesArray"),
        list,
    ):
        days = [payload]
    elif isinstance(payload, dict) and isinstance(payload.get("bodyBattery"), list):
        days = payload["bodyBattery"]
    else:
        return []
    samples: list[tuple[int, int]] = []
    for day in days:
        if not isinstance(day, dict):
            continue
        array = day.get("bodyBatteryValuesArray")
        if not isinstance(array, list):
            continue
        for point in array:
            if not isinstance(point, list | tuple) or len(point) < 2:
                continue
            timestamp = epoch_ms(point[0])
            level = optional_score(point[1])
            if timestamp is None or level is None:
                continue
            samples.append((timestamp, level))
    samples.sort(key=lambda sample: sample[0])
    return samples


def extract_body_battery(
    stats: Any,
    payload: Any,
    woke_at: datetime | None,
) -> int | None:
    samples = body_battery_samples(payload)
    if samples:
        if woke_at is None:
            return samples[-1][1]
        wake_ms = int(woke_at.timestamp() * 1000)
        window = [
            sample
            for sample in samples
            if sample[0] <= wake_ms + WAKE_MATCH_WINDOW_MS
        ]
        pool = window or samples
        return min(pool, key=lambda sample: abs(sample[0] - wake_ms))[1]
    if isinstance(stats, dict):
        for key in ("bodyBatteryAtWakeTime", "bodyBatteryMostRecentValue"):
            value = optional_score(stats.get(key))
            if value is not None:
                return value
    return None


def sleep_bounds(dto: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    start = parse_timestamp(dto.get("sleepStartTimestampGMT"), local_wall=False)
    end = parse_timestamp(dto.get("sleepEndTimestampGMT"), local_wall=False)
    if start is None:
        start = parse_timestamp(dto.get("sleepStartTimestampLocal"), local_wall=True)
    if end is None:
        end = parse_timestamp(dto.get("sleepEndTimestampLocal"), local_wall=True)
    return start, end


def summarize_sleep(
    bundle: dict[str, Any],
    *,
    fallback_date: str | None = None,
) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        raise ValueError("sleep bundle must be an object")
    dto = daily_sleep_dto(bundle.get("sleep"))
    if not dto:
        raise ValueError("Garmin response has no dailySleepDTO")
    calendar_date = dto.get("calendarDate")
    if not isinstance(calendar_date, str) or len(calendar_date) != 10:
        calendar_date = fallback_date
    if not isinstance(calendar_date, str):
        raise ValueError("calendarDate is missing")
    try:
        datetime.strptime(calendar_date, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError("calendarDate must use YYYY-MM-DD") from error

    total = rounded_non_negative(dto.get("sleepTimeSeconds"))
    if total is None or total <= 0:
        raise ValueError("sleepTimeSeconds is missing")
    fell_asleep_at, woke_at = sleep_bounds(dto)
    return {
        "date": calendar_date,
        "fell_asleep_at": fell_asleep_at,
        "woke_at": woke_at,
        "total_sleep_seconds": total,
        "deep_sleep_seconds": rounded_non_negative(dto.get("deepSleepSeconds")),
        "light_sleep_seconds": rounded_non_negative(dto.get("lightSleepSeconds")),
        "rem_sleep_seconds": rounded_non_negative(dto.get("remSleepSeconds")),
        "sleep_score": extract_sleep_score(dto),
        "resting_heart_rate": extract_resting_heart_rate(
            dto,
            bundle.get("stats"),
            bundle.get("rhr"),
        ),
        "body_battery": extract_body_battery(
            bundle.get("stats"),
            bundle.get("body_battery"),
            woke_at,
        ),
    }


class SleepAssessment:
    def __init__(
        self,
        complete: bool,
        reason: str,
        summary: dict[str, Any] | None,
    ) -> None:
        self.complete = complete
        self.reason = reason
        self.summary = summary


def assess_sleep(
    bundle: dict[str, Any],
    *,
    now: datetime,
    fallback_date: str | None = None,
) -> SleepAssessment:
    """A night is complete only when it has already finished.

    That means total sleep is greater than zero, a wake time (sleep end
    timestamp) is present, and that wake time is at or before ``now``.
    A missing record, a zero duration, a missing wake time, or an end time
    still in the future is treated as not synced or still in progress.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=SHANGHAI)
    try:
        summary = summarize_sleep(bundle, fallback_date=fallback_date)
    except ValueError as error:
        return SleepAssessment(False, str(error), None)
    if fallback_date and summary["date"] != fallback_date:
        return SleepAssessment(
            False,
            "sleep calendar date does not match the requested date",
            None,
        )
    woke_at = summary.get("woke_at")
    if woke_at is None:
        return SleepAssessment(False, "wake time is missing", None)
    if woke_at.tzinfo is None:
        woke_at = woke_at.replace(tzinfo=SHANGHAI)
    if woke_at > now:
        return SleepAssessment(False, "sleep has not ended yet", None)
    return SleepAssessment(True, "", summary)


def plan_sleep_notification(
    assessment: SleepAssessment,
    sent_dates: list[str],
    *,
    force: bool,
) -> str:
    if not assessment.complete:
        return "skip-incomplete"
    sleep_date = assessment.summary["date"] if assessment.summary else ""
    if sleep_date in sent_dates and not force:
        return "skip-already-sent"
    return "send"


def load_sent_dates(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"Sleep state file is not valid JSON: {path}: {error}") from None
    if not isinstance(data, dict) or not isinstance(data.get("sentDates"), list):
        raise SystemExit(
            f"Sleep state file must be an object with a sentDates list: {path}"
        )
    sent: list[str] = []
    for item in data["sentDates"]:
        if not isinstance(item, str):
            raise SystemExit(f"Sleep state file has an invalid date: {path}")
        try:
            datetime.strptime(item, "%Y-%m-%d")
        except ValueError:
            raise SystemExit(f"Sleep state file has an invalid date: {path}") from None
        sent.append(item)
    return sent


def remember_sent_date(
    sent_dates: list[str],
    sleep_date: str,
    *,
    limit: int = MAX_SENT_DATES,
) -> list[str]:
    merged = [item for item in sent_dates if item != sleep_date]
    merged.append(sleep_date)
    return merged[-limit:]


def save_sent_dates(path: Path, sent_dates: list[str]) -> bool:
    text = json.dumps({"sentDates": sent_dates}, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def format_duration(seconds: int) -> str:
    minutes_total = (seconds + 30) // 60
    hours, minutes = divmod(minutes_total, 60)
    if hours and minutes:
        return f"{hours}小时{minutes}分"
    if hours:
        return f"{hours}小时"
    return f"{minutes}分"


def format_moment(moment: datetime, report_date: date) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=SHANGHAI)
    local = moment.astimezone(SHANGHAI)
    clock = local.strftime("%H:%M")
    if local.date() == report_date:
        return clock
    return f"{local.month}月{local.day}日 {clock}"


def format_sleep_message(summary: dict[str, Any]) -> str:
    report_date = datetime.strptime(summary["date"], "%Y-%m-%d").date()
    lines = [f"睡眠 {report_date.month}月{report_date.day}日"]
    if summary.get("woke_at") is not None:
        lines.append(f"起床 {format_moment(summary['woke_at'], report_date)}")
    if summary.get("fell_asleep_at") is not None:
        lines.append(f"入眠 {format_moment(summary['fell_asleep_at'], report_date)}")
    lines.append(f"总睡眠 {format_duration(summary['total_sleep_seconds'])}")
    stages = []
    if summary.get("deep_sleep_seconds") is not None:
        stages.append(f"深睡 {format_duration(summary['deep_sleep_seconds'])}")
    if summary.get("light_sleep_seconds") is not None:
        stages.append(f"浅睡 {format_duration(summary['light_sleep_seconds'])}")
    if summary.get("rem_sleep_seconds") is not None:
        stages.append(f"REM {format_duration(summary['rem_sleep_seconds'])}")
    if stages:
        lines.append(" · ".join(stages))
    if summary.get("sleep_score") is not None:
        lines.append(f"睡眠评分 {summary['sleep_score']}")
    if summary.get("resting_heart_rate") is not None:
        lines.append(f"静息心率 {summary['resting_heart_rate']}")
    if summary.get("body_battery") is not None:
        lines.append(f"身体电量 {summary['body_battery']}")
    return "\n".join(lines)


def optional_garmin_call(client: Any, method_name: str, *args: Any, label: str) -> Any:
    method = getattr(client, method_name, None)
    if method is None:
        print(
            f"Garmin client has no {method_name}; skipping {label}",
            file=sys.stderr,
        )
        return None
    try:
        return method(*args)
    except Exception as error:
        print(
            f"Skipping Garmin {label}: {telegram_memos.redact(str(error))}",
            file=sys.stderr,
        )
        return None


def prompt_mfa() -> str:
    raise SystemExit(
        "Garmin login requires MFA, and this workflow cannot enter a code. "
        "Nothing was sent."
    )


def fetch_sleep_bundle(sleep_date: str) -> dict[str, Any]:
    try:
        from garminconnect import Garmin
    except ImportError:
        raise SystemExit(
            "garminconnect is not installed. Install garminconnect==0.3.6."
        ) from None

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        raise SystemExit("GARMIN_EMAIL and GARMIN_PASSWORD are required")

    is_cn = env_bool("GARMIN_IS_CN", default=True)
    client = Garmin(email, password, is_cn=is_cn, prompt_mfa=prompt_mfa)
    try:
        client.login()
    except SystemExit:
        raise
    except Exception as error:
        raise SystemExit(
            f"Garmin login failed: {telegram_memos.redact(str(error))}"
        ) from None
    print(f"Garmin login succeeded ({'CN' if is_cn else 'global'} account)")
    try:
        sleep = client.get_sleep_data(sleep_date)
    except Exception as error:
        raise SystemExit(
            f"Garmin sleep request failed for {sleep_date}: "
            f"{telegram_memos.redact(str(error))}"
        ) from None
    return {
        "sleep": sleep,
        "stats": optional_garmin_call(
            client,
            "get_stats",
            sleep_date,
            label="daily stats",
        ),
        "rhr": optional_garmin_call(
            client,
            "get_rhr_day",
            sleep_date,
            label="resting heart rate",
        ),
        "body_battery": optional_garmin_call(
            client,
            "get_body_battery",
            sleep_date,
            label="body battery",
        ),
    }


def load_bundle(path: str) -> dict[str, Any]:
    source = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(source)
    except json.JSONDecodeError as error:
        raise SystemExit(f"Sleep input is not valid JSON: {error}") from None
    if not isinstance(payload, dict):
        raise SystemExit("Sleep input must be a JSON object")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a short Garmin sleep summary to Telegram.",
    )
    parser.add_argument(
        "--date",
        help="Sleep date YYYY-MM-DD. Defaults to today in Asia/Shanghai.",
    )
    parser.add_argument(
        "--input",
        help="Read a sleep JSON bundle from a file, or - for stdin, instead of Garmin.",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help="JSON file of sleep dates already sent.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Send again even if this sleep date was already sent.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the message without calling Telegram or recording state.",
    )
    parser.add_argument(
        "--now",
        help="Override the current time as an ISO-8601 timestamp. For tests.",
    )
    args = parser.parse_args()
    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            parser.error("--date must use YYYY-MM-DD")
    if args.now:
        try:
            parsed_now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        except ValueError:
            parser.error("--now must be an ISO-8601 timestamp")
        if parsed_now.tzinfo is None:
            parser.error("--now must include a timezone offset")
    return args


def current_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(SHANGHAI)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=SHANGHAI)
    return parsed


def main() -> None:
    args = parse_args()
    now = current_time(args.now)
    sleep_date = args.date or now.astimezone(SHANGHAI).date().isoformat()
    print(f"Preparing Garmin sleep summary for {sleep_date} (Asia/Shanghai)")
    bundle = load_bundle(args.input) if args.input else fetch_sleep_bundle(sleep_date)
    assessment = assess_sleep(bundle, now=now, fallback_date=sleep_date)
    sent_dates = load_sent_dates(args.state)
    decision = plan_sleep_notification(assessment, sent_dates, force=args.force)
    if decision == "skip-incomplete":
        print(
            f"Skipping sleep notification for {sleep_date}: {assessment.reason}. "
            "The next scheduled run will try again."
        )
        return
    if decision == "skip-already-sent":
        print(f"Sleep summary for {sleep_date} was already sent; skipping")
        return
    if assessment.summary is None:
        raise SystemExit(f"Sleep summary for {sleep_date} is missing")
    message = format_sleep_message(assessment.summary)
    print(message)
    if args.dry_run:
        print("Dry run; Telegram message not sent")
        return
    telegram_memos.send_message(message)
    updated = remember_sent_date(sent_dates, assessment.summary["date"])
    if save_sent_dates(args.state, updated):
        print(f"Recorded sent sleep date {assessment.summary['date']} in {args.state}")


if __name__ == "__main__":
    main()
