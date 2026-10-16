from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import telegram_memos

SHANGHAI = ZoneInfo("Asia/Shanghai")
WAKE_MATCH_WINDOW_MS = 5 * 60 * 1000
DEFAULT_STATE_PATH = Path("data/telegram/sleep-sent.json")
MAX_SENT_DATES = 60
MIN_COMPLETE_SLEEP_SECONDS = 3 * 60 * 60

# garminconnect 0.3.6 get_sleep_data returns the raw wellness payload.
# dailySleepDTO.sleepTimeSeconds is the canonical total (seconds). The other
# names are defensive fallbacks seen on partial or newer payloads.
DURATION_KEYS = (
    "sleepTimeSeconds",
    "sleepTimeInSeconds",
    "totalSleepSeconds",
    "sleepDurationInSeconds",
    "actualSleepSeconds",
)
STAGE_KEYS = {
    "deep": ("deepSleepSeconds", "deepSleepTimeInSeconds", "deepSleep"),
    "light": ("lightSleepSeconds", "lightSleepTimeInSeconds", "lightSleep"),
    "rem": ("remSleepSeconds", "remSleepTimeInSeconds", "remSleep"),
    "awake": ("awakeSleepSeconds", "awakeSleepTimeInSeconds", "awakeSleep"),
}
LEVEL_BY_ACTIVITY = {0: "deep", 1: "light", 2: "rem", 3: "awake"}
START_GMT_KEYS = (
    "sleepStartTimestampGMT",
    "autoSleepStartTimestampGMT",
    "sleepStartTimeGMT",
)
START_LOCAL_KEYS = (
    "sleepStartTimestampLocal",
    "autoSleepStartTimestampLocal",
    "sleepStartTimeLocal",
)
END_GMT_KEYS = (
    "sleepEndTimestampGMT",
    "autoSleepEndTimestampGMT",
    "sleepEndTimeGMT",
)
END_LOCAL_KEYS = (
    "sleepEndTimestampLocal",
    "autoSleepEndTimestampLocal",
    "sleepEndTimeLocal",
)
NIGHT_HEART_RATE_KEYS = (
    "averageSleepHeartRate",
    "avgSleepHeartRate",
    "avgHeartRate",
    "averageHeartRate",
    "sleepHeartRate",
    "averageOvernightHeartRate",
    "nightlyAverageHeartRate",
)
HRV_KEYS = (
    "avgSleepHRV",
    "avgOvernightHrv",
    "averageHrv",
    "overnightHrv",
    "averageOvernightHrv",
)
BODY_BATTERY_CHANGE_KEYS = (
    "bodyBatteryChange",
    "bodyBatteryDelta",
    "bodyBatteryDifference",
)
QUALIFIER_LABELS = {
    "EXCELLENT": "优秀",
    "GOOD": "良好",
    "FAIR": "一般",
    "POOR": "较差",
}
PII_KEY_PARTS = (
    "userprofile",
    "userid",
    "displayname",
    "fullname",
    "firstname",
    "lastname",
    "email",
    "deviceid",
    "devicename",
    "password",
    "token",
    "profileimage",
    "ownerid",
)
DEBUG_SKIP_KEYS = {
    "sleepLevels",
    "sleepLevelsMap",
    "sleepMovement",
    "sleepRestlessMoments",
    "restlessMoments",
    "wellnessEpochSPO2DataDTOList",
    "wellnessEpochRespirationDataDTOList",
    "sleepStress",
}


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
    if any(key in payload for key in DURATION_KEYS + START_GMT_KEYS + END_GMT_KEYS):
        return payload
    return {}


def mapping_sources(*items: Any) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict) and all(item is not existing for existing in sources):
            sources.append(item)
    return sources


def duration_value(value: Any) -> int | None:
    """Read a duration in seconds. 0.3.6 types this as an int; accept dicts too."""
    if isinstance(value, dict):
        for key in ("seconds", "value", "total", "sleepTimeSeconds", "duration"):
            if key in value:
                found = duration_value(value.get(key))
                if found is not None:
                    return found
        return None
    return rounded_non_negative(value)


def first_duration(mapping: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        if key not in mapping:
            continue
        value = duration_value(mapping.get(key))
        if value is not None:
            return value
    return None


def optional_signed_int(value: Any) -> int | None:
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    magnitude = abs(float(value))
    rounded = math.floor(magnitude + 0.5)
    if value < 0:
        return -rounded
    return rounded


def optional_hrv(value: Any) -> int | None:
    number = rounded_non_negative(value)
    if number is None or number <= 0 or number > 300:
        return None
    return number


def level_name(activity: Any) -> str | None:
    if isinstance(activity, str):
        name = activity.strip().lower()
        if name in {"deep", "light", "rem", "awake"}:
            return name
        return None
    number = rounded_non_negative(activity)
    if number is None:
        return None
    return LEVEL_BY_ACTIVITY.get(number)


def interval_seconds(item: dict[str, Any]) -> int | None:
    pairs = (
        ("startGMT", "endGMT"),
        ("startTimeGMT", "endTimeGMT"),
        ("startTimeInSeconds", "endTimeInSeconds"),
        ("start", "end"),
    )
    for start_key, end_key in pairs:
        if start_key not in item or end_key not in item:
            continue
        start = parse_timestamp(item.get(start_key), local_wall=False)
        end = parse_timestamp(item.get(end_key), local_wall=False)
        if start is not None and end is not None:
            delta = (end - start).total_seconds()
            if delta > 0:
                return rounded_non_negative(delta)
    return None


def accumulate_stage_seconds(levels: Any, totals: dict[str, int]) -> None:
    if isinstance(levels, list):
        for item in levels:
            if not isinstance(item, dict):
                continue
            name = level_name(item.get("activityLevel", item.get("level")))
            seconds = interval_seconds(item)
            if name and seconds:
                totals[name] = totals.get(name, 0) + seconds
        return
    if not isinstance(levels, dict):
        return
    for raw_name, intervals in levels.items():
        name = level_name(raw_name)
        if name is None or not isinstance(intervals, list):
            continue
        for item in intervals:
            if not isinstance(item, dict):
                continue
            seconds = interval_seconds(item)
            if seconds:
                totals[name] = totals.get(name, 0) + seconds


def stage_seconds_from_levels(
    dto: dict[str, Any],
    root: dict[str, Any],
) -> dict[str, int]:
    for source in mapping_sources(dto, root):
        totals: dict[str, int] = {}
        found = False
        for key in ("sleepLevels", "sleepLevelsMap"):
            levels = source.get(key)
            if not levels:
                continue
            accumulate_stage_seconds(levels, totals)
            found = True
        if found:
            return totals
    return {}


def resolve_stage_seconds(
    dto: dict[str, Any],
    root: dict[str, Any],
) -> dict[str, int | None]:
    from_levels = stage_seconds_from_levels(dto, root)
    resolved: dict[str, int | None] = {}
    for stage, keys in STAGE_KEYS.items():
        value = first_duration(dto, keys)
        if value is None and root is not dto:
            value = first_duration(root, keys)
        if value is None and stage in from_levels:
            value = from_levels[stage]
        resolved[stage] = value
    return resolved


def resolve_total_sleep_seconds(
    dto: dict[str, Any],
    root: dict[str, Any],
    stages: dict[str, int | None],
) -> int | None:
    """Prefer a full night over a short fragment stored in sleepTimeSeconds.

    0.3.6's canonical field is dailySleepDTO.sleepTimeSeconds. A finished night
    already lives there (for example 28860 seconds renders as 8小时1分). When
    that field is only a short window, later candidates — alternate names, then
    deep+light+REM — can still hold the night the China site shows.
    """
    candidates: list[int] = []
    for source in mapping_sources(dto, root):
        for key in DURATION_KEYS:
            if key not in source:
                continue
            value = duration_value(source.get(key))
            if value is not None and value > 0:
                candidates.append(value)
    stage_values = [stages.get(stage) for stage in ("deep", "light", "rem")]
    if any(value is not None for value in stage_values):
        stage_sum = sum(value or 0 for value in stage_values)
        if stage_sum > 0:
            candidates.append(stage_sum)
    for value in candidates:
        if value >= MIN_COMPLETE_SLEEP_SECONDS:
            return value
    return candidates[0] if candidates else None


def first_timestamp(
    mapping: dict[str, Any],
    keys: tuple[str, ...],
    *,
    local_wall: bool,
) -> datetime | None:
    for key in keys:
        if key not in mapping:
            continue
        parsed = parse_timestamp(mapping.get(key), local_wall=local_wall)
        if parsed is not None:
            return parsed
    return None


def extract_sleep_score_detail(
    *sources: dict[str, Any],
) -> tuple[int | None, str | None]:
    for dto in sources:
        scores = dto.get("sleepScores")
        if isinstance(scores, dict):
            overall = scores.get("overall")
            if isinstance(overall, dict):
                score = optional_score(overall.get("value"))
                if score is not None:
                    qualifier = overall.get("qualifierKey")
                    if not isinstance(qualifier, str):
                        qualifier = None
                    return score, qualifier
            elif overall is not None:
                score = optional_score(overall)
                if score is not None:
                    return score, None
            for key in ("overallScore", "totalScore", "sleepScore"):
                if key in scores:
                    score = optional_score(scores.get(key))
                    if score is not None:
                        return score, None
        for key in ("sleepScore", "overallSleepScore"):
            if key in dto:
                score = optional_score(dto.get(key))
                if score is not None:
                    return score, None
    return None, None


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
    root: dict[str, Any] | None = None,
) -> int | None:
    for source in mapping_sources(dto, root, stats if isinstance(stats, dict) else None):
        if "restingHeartRate" not in source:
            continue
        value = optional_heart_rate(source.get("restingHeartRate"))
        if value is not None:
            return value
    return resting_heart_rate_from_metrics(rhr_payload)


def extract_named_number(
    sources: list[dict[str, Any]],
    keys: tuple[str, ...],
    reader: Any,
) -> int | None:
    for source in sources:
        for key in keys:
            if key not in source:
                continue
            value = reader(source.get(key))
            if value is not None:
                return value
    return None


def extract_hrv(sources: list[dict[str, Any]], hrv_payload: Any) -> int | None:
    value = extract_named_number(sources, HRV_KEYS, optional_hrv)
    if value is not None:
        return value
    if isinstance(hrv_payload, dict):
        summary = hrv_payload.get("hrvSummary")
        if isinstance(summary, dict):
            return optional_hrv(summary.get("lastNightAvg"))
    return None


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


def sleep_bounds(
    dto: dict[str, Any],
    root: dict[str, Any] | None = None,
) -> tuple[datetime | None, datetime | None]:
    sources = mapping_sources(dto, root)
    start = None
    end = None
    for source in sources:
        if start is None:
            start = first_timestamp(source, START_GMT_KEYS, local_wall=False)
        if end is None:
            end = first_timestamp(source, END_GMT_KEYS, local_wall=False)
    for source in sources:
        if start is None:
            start = first_timestamp(source, START_LOCAL_KEYS, local_wall=True)
        if end is None:
            end = first_timestamp(source, END_LOCAL_KEYS, local_wall=True)
    return start, end


def summarize_sleep(
    bundle: dict[str, Any],
    *,
    fallback_date: str | None = None,
) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        raise ValueError("sleep bundle must be an object")
    root = bundle.get("sleep") if isinstance(bundle.get("sleep"), dict) else {}
    dto = daily_sleep_dto(root)
    if not dto:
        raise ValueError("Garmin response has no dailySleepDTO")
    calendar_date = dto.get("calendarDate")
    if not isinstance(calendar_date, str) or len(calendar_date) != 10:
        calendar_date = root.get("calendarDate") if root is not dto else None
    if not isinstance(calendar_date, str) or len(calendar_date) != 10:
        calendar_date = fallback_date
    if not isinstance(calendar_date, str):
        raise ValueError("calendarDate is missing")
    try:
        datetime.strptime(calendar_date, "%Y-%m-%d")
    except ValueError as error:
        raise ValueError("calendarDate must use YYYY-MM-DD") from error

    stages = resolve_stage_seconds(dto, root)
    total = resolve_total_sleep_seconds(dto, root, stages)
    if total is None or total <= 0:
        raise ValueError("sleepTimeSeconds is missing")
    fell_asleep_at, woke_at = sleep_bounds(dto, root)
    awake = stages.get("awake") or 0
    unmeasurable = first_duration(dto, ("unmeasurableSleepSeconds",))
    if unmeasurable is None and root is not dto:
        unmeasurable = first_duration(root, ("unmeasurableSleepSeconds",))
    if fell_asleep_at is None and woke_at is not None:
        window = total + awake + (unmeasurable or 0)
        fell_asleep_at = woke_at - timedelta(seconds=window)
    sources = mapping_sources(dto, root)
    score, qualifier = extract_sleep_score_detail(*sources)
    return {
        "date": calendar_date,
        "fell_asleep_at": fell_asleep_at,
        "woke_at": woke_at,
        "total_sleep_seconds": total,
        "deep_sleep_seconds": stages.get("deep"),
        "light_sleep_seconds": stages.get("light"),
        "rem_sleep_seconds": stages.get("rem"),
        "awake_sleep_seconds": stages.get("awake"),
        "sleep_score": score,
        "sleep_score_qualifier": qualifier,
        "resting_heart_rate": extract_resting_heart_rate(
            dto,
            bundle.get("stats"),
            bundle.get("rhr"),
            root,
        ),
        "night_heart_rate": extract_named_number(
            sources,
            NIGHT_HEART_RATE_KEYS,
            optional_heart_rate,
        ),
        "body_battery": extract_body_battery(
            bundle.get("stats"),
            bundle.get("body_battery"),
            woke_at,
        ),
        "body_battery_change": extract_named_number(
            sources,
            BODY_BATTERY_CHANGE_KEYS,
            optional_signed_int,
        ),
        "average_hrv": extract_hrv(sources, bundle.get("hrv")),
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
    """A night is complete only when the finished summary is worth sending.

    The wake time has to be present and at or before ``now``. Total sleep also
    has to reach 3 hours, and a sleep score has to be present. A ~1 hour window
    with a wake timestamp and no score is a fragment (often the start of the
    night) and must not be sent.
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
    if summary["total_sleep_seconds"] < MIN_COMPLETE_SLEEP_SECONDS:
        return SleepAssessment(False, "total sleep is under 3 hours", None)
    if summary.get("sleep_score") is None:
        return SleepAssessment(False, "sleep score is missing", None)
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


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openrouter/free"
LLM_ATTEMPTS = 3
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 200
LLM_TIMEOUT_SECONDS = 60
NARRATIVE_MIN_CHARS = 40
NARRATIVE_MAX_CHARS = 200
MAX_NARRATIVE_NUMBERS = 3
THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
THINK_OPEN = re.compile(r"<think\b[^>]*>.*", re.IGNORECASE | re.DOTALL)
DATE_START = re.compile(
    r"^\s*\d{4}\s*[-/.年]\s*\d{1,2}(?:\s*[-/.月]\s*\d{1,2})?"
)
SENTENCE_END = re.compile(r"[。！？]")
REASONING_LINE = re.compile(
    r"^(?:思考|分析|草稿|推理|推理过程|思考过程|分析过程|draft|reasoning|thoughts?|"
    r"let me|okay|ok|首先|让我|我先|我需要|用户希望|用户要求|下面是|以下是)"
    r"(?:[:：\s]|$)",
    re.IGNORECASE,
)
REASONING_LABEL_ONLY = re.compile(
    r"^(?:思考|分析|草稿|推理|推理过程|思考过程|分析过程|draft|reasoning|thoughts?)"
    r"\s*[:：]?\s*$",
    re.IGNORECASE,
)
REASONING_LABEL_BODY = re.compile(
    r"^(?:思考|分析|草稿|推理|推理过程|思考过程|分析过程|draft|reasoning|thoughts?)"
    r"\s*[:：]\s*(.+)$",
    re.IGNORECASE,
)
SECTION_LABEL_ONLY = re.compile(r"(?:正文|最终|输出)\s*[:：]?", re.IGNORECASE)

SYSTEM_PROMPT = (
    "你是睡眠晨报的第一段作者。用户会跳舞，也做力量训练，恢复建议要考虑排练和训练。"
    "只输出 2 句话，总共不超过 100 个汉字，不要任何其他内容。"
    "不要标题，不要列表，不要日期，不要思考、分析或 Draft。"
    "最多引用总时长和评分里的 1 个或 2 个数字。其他指标只用于判断，不要写出来。"
    "语气温和，不要夸张，不要医疗诊断。示例不要照抄数字。\n"
    "示例一：昨晚睡得踏实，一共 8 小时，评分 91。跳舞和力量训练之后这样够恢复，今天力量可以照常安排。\n"
    "示例二：昨晚睡得短了些，一共 5 小时。排练和训练先放轻一点，今晚早点休息。"
)


def format_duration_spaced(seconds: int) -> str:
    minutes_total = (seconds + 30) // 60
    hours, minutes = divmod(minutes_total, 60)
    if hours and minutes:
        return f"{hours} 小时 {minutes} 分"
    if hours:
        return f"{hours} 小时"
    return f"{minutes} 分"


def format_clock(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=SHANGHAI)
    return moment.astimezone(SHANGHAI).strftime("%H:%M")


def format_score_text(summary: dict[str, Any]) -> str | None:
    score = summary.get("sleep_score")
    if score is None:
        return None
    qualifier = QUALIFIER_LABELS.get(summary.get("sleep_score_qualifier") or "")
    if qualifier:
        return f"{score}（{qualifier}）"
    return str(score)


def stage_bits(summary: dict[str, Any]) -> list[str]:
    bits = []
    if summary.get("deep_sleep_seconds") is not None:
        bits.append(f"深睡 {format_duration(summary['deep_sleep_seconds'])}")
    if summary.get("light_sleep_seconds") is not None:
        bits.append(f"浅睡 {format_duration(summary['light_sleep_seconds'])}")
    if summary.get("rem_sleep_seconds") is not None:
        bits.append(f"REM {format_duration(summary['rem_sleep_seconds'])}")
    if summary.get("awake_sleep_seconds") is not None:
        bits.append(f"清醒 {format_duration(summary['awake_sleep_seconds'])}")
    return bits


def metric_bits(summary: dict[str, Any]) -> list[str]:
    bits = []
    if summary.get("resting_heart_rate") is not None:
        bits.append(f"静息心率 {summary['resting_heart_rate']}")
    change = summary.get("body_battery_change")
    if change is not None:
        sign = "+" if change > 0 else ""
        bits.append(f"身体电量 {sign}{change}")
    if summary.get("average_hrv") is not None:
        bits.append(f"HRV {summary['average_hrv']}ms")
    return bits


def format_sleep_data(summary: dict[str, Any]) -> str:
    """Core numbers shown under an AI paragraph. Empty when nothing is present."""
    lines = []
    stages = stage_bits(summary)
    metrics = metric_bits(summary)
    if stages:
        lines.append(" · ".join(stages))
    if metrics:
        lines.append(" · ".join(metrics))
    return "\n".join(lines)


def format_sleep_message(summary: dict[str, Any]) -> str:
    """Fixed one-paragraph template used when the model does not return copy."""
    bits = []
    fell_asleep_at = summary.get("fell_asleep_at")
    woke_at = summary.get("woke_at")
    if fell_asleep_at is not None and woke_at is not None:
        bits.append(f"{format_clock(fell_asleep_at)} 睡，{format_clock(woke_at)} 起")
    elif woke_at is not None:
        bits.append(f"{format_clock(woke_at)} 起")
    elif fell_asleep_at is not None:
        bits.append(f"{format_clock(fell_asleep_at)} 睡")
    bits.append(f"一共 {format_duration_spaced(summary['total_sleep_seconds'])}")
    score_text = format_score_text(summary)
    if score_text is not None:
        bits.append(f"评分 {score_text}")
    lead = "，".join(bits)
    if fell_asleep_at is not None or woke_at is not None:
        lead = f"昨晚 {lead}"
    sentences = [f"{lead}。"]
    stages = stage_bits(summary)
    metrics = metric_bits(summary)
    if stages:
        sentences.append(f"{'，'.join(stages)}。")
    if metrics:
        sentences.append(f"{'，'.join(metrics)}。")
    return "".join(sentences)


def sleep_fact_lines(summary: dict[str, Any]) -> list[str]:
    lines = [f"日期: {summary['date']}"]
    fell_asleep_at = summary.get("fell_asleep_at")
    woke_at = summary.get("woke_at")
    if fell_asleep_at is not None:
        lines.append(f"入睡: {format_clock(fell_asleep_at)}")
    if woke_at is not None:
        lines.append(f"起床: {format_clock(woke_at)}")
    lines.append(f"总睡眠: {format_duration_spaced(summary['total_sleep_seconds'])}")
    score_text = format_score_text(summary)
    if score_text is not None:
        lines.append(f"评分: {score_text}")
    for label, key in (
        ("深睡", "deep_sleep_seconds"),
        ("浅睡", "light_sleep_seconds"),
        ("REM", "rem_sleep_seconds"),
        ("清醒", "awake_sleep_seconds"),
    ):
        if summary.get(key) is not None:
            lines.append(f"{label}: {format_duration(summary[key])}")
    if summary.get("resting_heart_rate") is not None:
        lines.append(f"静息心率: {summary['resting_heart_rate']}")
    if summary.get("night_heart_rate") is not None:
        lines.append(f"夜间平均心率: {summary['night_heart_rate']}")
    change = summary.get("body_battery_change")
    if change is not None:
        sign = "+" if change > 0 else ""
        lines.append(f"身体电量变化: {sign}{change}")
    if summary.get("average_hrv") is not None:
        lines.append(f"平均HRV: {summary['average_hrv']}ms")
    return lines


def allowed_numbers(summary: dict[str, Any]) -> set[str]:
    allowed = set(re.findall(r"\d+", "\n".join(sleep_fact_lines(summary))))
    allowed.update(token.lstrip("0") or "0" for token in list(allowed))
    return allowed


def strip_think_tags(text: str) -> str:
    cleaned = THINK_BLOCK.sub("", text)
    cleaned = THINK_OPEN.sub("", cleaned)
    return cleaned.strip()


def coerce_model_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text", item.get("content", ""))
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def paragraph_reading(paragraph: str) -> str:
    """Drop a leading 思考/分析/Draft label and keep the reading after it."""
    kept: list[str] = []
    for raw_line in paragraph.splitlines():
        stripped = raw_line.strip().lstrip("#").strip()
        if kept:
            kept.append(raw_line.strip())
            continue
        if not stripped or REASONING_LABEL_ONLY.match(stripped):
            continue
        if SECTION_LABEL_ONLY.fullmatch(stripped):
            continue
        labeled = REASONING_LABEL_BODY.match(stripped)
        if labeled:
            kept.append(labeled.group(1).strip())
            continue
        if REASONING_LINE.match(stripped):
            continue
        kept.append(raw_line.strip())
    return "\n".join(kept).strip()


def closing_sentences(text: str) -> str:
    sentences = re.findall(r"[^。！？\n]+[。！？]", text)
    if len(sentences) >= 2:
        return "".join(sentences[-2:]).strip()
    if sentences:
        return sentences[-1].strip()
    return ""


def final_interpretation(text: str) -> str:
    """Drop think tags and reasoning paragraphs, then keep the closing reading."""
    text = strip_think_tags(text)
    for marker in ("最终解读：", "最终解读:", "正文：", "正文:", "输出：", "输出:"):
        if marker in text:
            text = text.split(marker)[-1]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    kept = [paragraph_reading(paragraph) for paragraph in paragraphs]
    kept = [paragraph for paragraph in kept if paragraph]
    candidate = kept[-1].strip() if kept else ""
    if not candidate:
        return ""
    compact_length = len(re.sub(r"\s+", "", candidate))
    if compact_length > NARRATIVE_MAX_CHARS:
        shortened = closing_sentences(candidate)
        if shortened:
            candidate = shortened
    return candidate.strip()


def narrative_from_message(message: Any) -> tuple[str, str, str]:
    """Return the reading, the raw field it came from, and that field's name."""
    if not isinstance(message, dict):
        return "", "", ""
    candidates: list[tuple[str, str, str]] = []
    for key in ("content", "reasoning_content", "reasoning"):
        raw = coerce_model_text(message.get(key))
        if not raw.strip():
            continue
        candidates.append((key, final_interpretation(raw), raw))
    for key, extracted, raw in candidates:
        length = len(re.sub(r"\s+", "", extracted))
        if NARRATIVE_MIN_CHARS <= length <= NARRATIVE_MAX_CHARS:
            return extracted, raw, key
    if candidates:
        key, extracted, raw = candidates[0]
        return extracted or raw, raw, key
    return "", "", ""


class ModelReply:
    def __init__(
        self,
        text: str,
        model: str,
        fields: list[str],
        raw: str,
        used: str,
    ) -> None:
        self.text = text
        self.model = model
        self.fields = fields
        self.raw = raw
        self.used = used


class SleepCopyError(Exception):
    pass


def validate_narrative(text: str, summary: dict[str, Any]) -> str:
    if re.search(r"<\s*think\b", text, re.IGNORECASE):
        raise SleepCopyError("output still contains a think tag")
    compact = re.sub(r"\s+", "", text)
    if not compact:
        raise SleepCopyError("output is empty")
    length = len(compact)
    if length < NARRATIVE_MIN_CHARS or length > NARRATIVE_MAX_CHARS:
        raise SleepCopyError(f"output length {length} is outside 40-200")
    if DATE_START.match(text):
        raise SleepCopyError("output starts with a date")
    if len(SENTENCE_END.findall(text)) < 2:
        raise SleepCopyError("output does not contain enough sentences")
    numbers = re.findall(r"\d+", text)
    if len(numbers) > MAX_NARRATIVE_NUMBERS:
        raise SleepCopyError(f"output lists too many numbers ({len(numbers)})")
    allowed = allowed_numbers(summary)
    unexpected = [token for token in numbers if token not in allowed]
    if unexpected:
        shown = ", ".join(unexpected[:6])
        raise SleepCopyError(f"output contains numbers that were not provided: {shown}")
    return text


def message_fields(message: Any) -> list[str]:
    if not isinstance(message, dict):
        return []
    fields = []
    for key in ("content", "reasoning", "reasoning_content"):
        if coerce_model_text(message.get(key)).strip():
            fields.append(key)
    return fields


def parse_openrouter_payload(raw: bytes) -> ModelReply:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise SleepCopyError("response was not JSON") from error
    if not isinstance(payload, dict):
        raise SleepCopyError("response was not an object")
    error = payload.get("error")
    if error:
        detail = error.get("message") if isinstance(error, dict) else str(error)
        raise SleepCopyError(f"API error: {detail}")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise SleepCopyError("response has no choices")
    message = choices[0].get("message")
    text, raw_text, used = narrative_from_message(message)
    model = payload.get("model")
    return ModelReply(
        text,
        model if isinstance(model, str) else "",
        message_fields(message),
        raw_text,
        used,
    )


def request_openrouter_narrative(
    summary: dict[str, Any],
    *,
    opener: Any,
    api_key: str,
) -> ModelReply:
    body = json.dumps(
        {
            "model": OPENROUTER_MODEL,
            "temperature": LLM_TEMPERATURE,
            "max_tokens": LLM_MAX_TOKENS,
            "reasoning": {"effort": "low"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "只输出 2 句话，总共不超过 100 个汉字，不要任何其他内容。\n"
                        "不要罗列指标，不要写日期，不要解释判断过程。\n"
                        "最多提总时长和评分。下面的数据只供判断：\n"
                        + "\n".join(sleep_fact_lines(summary))
                    ),
                },
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://blog.kazoottt.top",
            "X-Title": "issues-blog sleep",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=LLM_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:180]
        raise SleepCopyError(f"HTTP {error.code} {detail}") from None
    except urllib.error.URLError as error:
        raise SleepCopyError(f"network error: {error.reason}") from None
    except TimeoutError as error:
        raise SleepCopyError(f"network error: {error}") from None
    return parse_openrouter_payload(raw)


class SleepCopy:
    def __init__(self, text: str, source: str, attempt: int | None) -> None:
        self.text = text
        self.source = source
        self.attempt = attempt


def describe_sleep_copy(copy: SleepCopy) -> str:
    if copy.source == "llm" and copy.attempt is not None:
        return f"文案来源: AI（第 {copy.attempt} 次尝试）"
    return "文案来源: 固定模板"


def failure_detail(error: SleepCopyError, reply: ModelReply | None) -> str:
    detail = telegram_memos.redact(str(error))
    if reply is None:
        return detail
    preview = telegram_memos.redact(re.sub(r"\s+", " ", reply.raw).strip())[:300]
    fields = ", ".join(reply.fields) if reply.fields else "none"
    model = reply.model or "unknown"
    used = reply.used or "none"
    return (
        f"{detail}\n  model: {model}\n  fields: {fields}\n  used: {used}\n  raw: {preview}"
    )


def compose_sleep_message(
    summary: dict[str, Any],
    *,
    opener: Any = urllib.request.urlopen,
    attempts: int = LLM_ATTEMPTS,
) -> SleepCopy:
    fallback = format_sleep_message(summary)
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("未设置 OPENROUTER_API_KEY，改用固定模板。")
        return SleepCopy(fallback, "fallback", None)
    for attempt in range(1, attempts + 1):
        reply: ModelReply | None = None
        try:
            reply = request_openrouter_narrative(summary, opener=opener, api_key=api_key)
            narrative = validate_narrative(reply.text, summary)
        except SleepCopyError as error:
            print(f"OpenRouter 第 {attempt} 次失败: {failure_detail(error, reply)}")
            continue
        data = format_sleep_data(summary)
        text = narrative if not data else f"{narrative}\n\n{data}"
        return SleepCopy(text, "llm", attempt)
    print(f"OpenRouter {attempts} 次都失败，改用固定模板。")
    return SleepCopy(fallback, "fallback", None)


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
        "hrv": optional_garmin_call(
            client,
            "get_hrv_data",
            sleep_date,
            label="overnight HRV",
        ),
    }


def is_pii_key(key: str) -> bool:
    compact = "".join(character for character in key.lower() if character.isalnum())
    return any(part in compact for part in PII_KEY_PARTS)


def debug_value(value: Any) -> str:
    if isinstance(value, str) and "@" in value:
        return json.dumps("***", ensure_ascii=False)
    if isinstance(value, dict):
        cleaned = {
            str(key): item
            for key, item in value.items()
            if not is_pii_key(str(key))
        }
        if any(isinstance(item, list) and len(item) > 8 for item in cleaned.values()):
            return "{...}"
        return json.dumps(cleaned, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(value, list):
        return f"[{len(value)} items]"
    return json.dumps(value, ensure_ascii=False, default=str)


def debug_sleep_lines(payload: Any) -> list[str]:
    """Key/value snapshot of dailySleepDTO, without profile or device identifiers."""
    if not isinstance(payload, dict):
        return ["dailySleepDTO debug: missing"]
    dto = daily_sleep_dto(payload)
    lines = ["dailySleepDTO debug:"]
    if not dto:
        lines.append("  (no dailySleepDTO)")
    else:
        printed = False
        for key in sorted(dto):
            if key in DEBUG_SKIP_KEYS or is_pii_key(key):
                continue
            value = dto.get(key)
            if isinstance(value, list):
                continue
            lines.append(f"  {key}={debug_value(value)}")
            printed = True
        if not printed:
            lines.append("  (no relevant fields)")
    if payload is not dto:
        for key in sorted(payload):
            if key in DEBUG_SKIP_KEYS or is_pii_key(key) or key in dto:
                continue
            value = payload.get(key)
            if isinstance(value, list):
                continue
            lines.append(f"  root.{key}={debug_value(value)}")
    levels = stage_seconds_from_levels(dto, payload)
    if levels:
        summary = " ".join(
            f"{name}={levels[name]}"
            for name in ("deep", "light", "rem", "awake")
            if name in levels
        )
        lines.append(f"  sleepLevelsSeconds: {summary}")
    return lines


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
        "--debug",
        action="store_true",
        help="Print dailySleepDTO field names and values, without personal identifiers.",
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
    if args.debug:
        sleep_payload = bundle.get("sleep") if isinstance(bundle, dict) else None
        print(telegram_memos.redact("\n".join(debug_sleep_lines(sleep_payload))))
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
    copy = compose_sleep_message(assessment.summary)
    print(describe_sleep_copy(copy))
    print(copy.text)
    if args.dry_run:
        print("Dry run; Telegram message not sent")
        return
    telegram_memos.send_message(copy.text)
    updated = remember_sent_date(sent_dates, assessment.summary["date"])
    if save_sent_dates(args.state, updated):
        print(f"Recorded sent sleep date {assessment.summary['date']} in {args.state}")


if __name__ == "__main__":
    main()
