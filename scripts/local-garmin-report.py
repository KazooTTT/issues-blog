#!/usr/bin/env python3
"""Local Garmin → Magpie → Telegram. Preview by default; never writes GitHub."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
from html.parser import HTMLParser
import re
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location("reports", Path(__file__).with_name("publish-daily-reports.py"))
reports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reports)
DEFAULT_MODEL = "workbuddy-ai/deepseek-v4.1-flash"
DEFAULT_STATE = Path.home() / "Library/Application Support/local-garmin-reports"
FITNESS_API = os.environ.get("FITNESS_API", "https://fitness-dashboard-9qn.pages.dev/api/metrics?days=7")


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


def interpret(title, body, with_exercise=True):
    base = os.environ.get("MAGPIE_BASE_URL", "http://127.0.0.1:3425/v1").rstrip("/")
    if urlparse(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise reports.ReportError("MAGPIE_BASE_URL must point to the local gateway")
    token = os.environ.get("MAGPIE_API_KEY")
    if not token:
        config = Path.home() / ".config/opencode/opencode.json"
        if config.exists():
            options = json.loads(config.read_text()).get("provider", {}).get("magpie", {}).get("options", {})
            if options.get("baseURL", "").rstrip("/") == base:
                token = options.get("apiKey")
    system = (
        "你是个人早报编辑。只依据提供的佳明数据，输出一个合法JSON对象，不要代码围栏或额外文字。"
        "字段：conclusion（不超过30字，只说今天的首要安排，不摘要复述后面各节）；"
        "sleep（不超过100字，仅睡眠时长、评分、作息和一个观察，不罗列分期）；"
        "hrv（不超过180字，必须写全四件事：昨夜HRV、7日均值、个人基线；然后写出状态名，并紧跟一句用来说明这个状态是怎么判定的，形如「BALANCED 指7日均值落在个人基线内」，不能只写状态名或只写身体感受；若单晚与7日均值相对基线的位置不同，再说明两者不矛盾）；"
        "佳明HRV状态的含义：BALANCED指7日均值落在个人基线内，说明身体能消化当前负荷；UNBALANCED指7日均值略超出基线，偏高偏低都算，负荷突增时偏高同样代表身体在加班恢复；LOW指7日均值明显跌破基线，通常来自压力或负荷持续堆积；POOR指低于同龄健康下限，与个人基线无关。判断依据是7日均值相对基线的位置，不是单晚数值；"
    )
    if with_exercise:
        system += "exercise（不超过160字，昨日运动类型、时长、平均心率、训练效果或负荷择要，然后一句与恢复有关的谨慎判断，不写行动建议）；"
    system += (
        "fitness（不超过150字，不罗列任何数值，不要出现CTL、ATL、TSB这类术语；用日常语言解释这段数据意味着什么：长期底子处在什么水平、最近一周的疲劳从哪里来、现在恢复余量够不够用，最后一句与恢复有关的判断，不写行动建议）；"
        "actions（2到3个字符串，每条不超过55字，分别说明今天如何运动、今晚如何作息、需要留意什么）。"
    )
    system += (
        "整篇250到400字，字段内容是无标题的纯文本。每项事实只能在一个字段出现，建议不再复述指标。"
        if with_exercise else
        "整篇200到330字，字段内容是无标题的纯文本。每项事实只能在一个字段出现，建议不再复述指标。"
    )
    system += (
        "不得重复套话、附数据表、写总结段或免责声明。不描述未提供的个人体感，例如不解乏、疲劳或精神不好；建议可以用如果感到疲劳这样的条件句。只在影响判断的地方说明缺失，不罗列所有未知字段。"
        "负荷取整，HRV带ms，心率带bpm；舞蹈等非距离运动不提0公里。"
        "区分事实和推测，不编造个人趋势、正常范围或最大心率，不断言昨日运动造成HRV变化，不做医学诊断。"
    )
    system += (
        "佳明HRV状态与单晚相对基线位置不同；没有运动记录不等于没有运动，接口失败不能写零运动。"
        if with_exercise else
        "佳明HRV状态与单晚相对基线位置不同；昨天没有运动数据，不要提及运动记录、训练量或训练负荷，也不要因为缺失写任何说明。"
    )
    result = reports.api(base + "/chat/completions", token=token, method="POST", data={
        "model": os.environ.get("MAGPIE_MODEL", DEFAULT_MODEL),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": title + "\n\n" + body},
        ],
        "max_tokens": 3000,
        "stream": False,
    })
    try:
        text = result["choices"][0]["message"]["content"].strip()
        finished = result["choices"][0].get("finish_reason")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise reports.ReportError("Magpie returned no usable interpretation") from None
    if not text or finished == "length":
        raise reports.ReportError("Magpie interpretation empty or truncated; retry generation")
    return render_brief(text, with_exercise)


def render_brief(text, with_exercise=True):
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        raise reports.ReportError("Magpie returned invalid brief JSON; retry generation") from None
    limits = {"conclusion": 60, "sleep": 130, "hrv": 190, "fitness": 180}
    if with_exercise:
        limits["exercise"] = 190
    if not isinstance(data, dict) or any(not isinstance(data.get(key), str) or not data[key].strip()
                                        or len(data[key]) > limit for key, limit in limits.items()):
        raise reports.ReportError("Magpie brief does not match the concise report structure")
    actions = data.get("actions")
    if not isinstance(actions, list) or not 2 <= len(actions) <= 3 or any(
            not isinstance(item, str) or not item.strip() or len(item) > 70 for item in actions):
        raise reports.ReportError("Magpie brief must provide two or three short actions")
    values = {key: reports.clean(data[key]) for key in limits}
    lines = [values['conclusion'], "", "## 睡眠与恢复", "",
             "- 睡眠：" + values['sleep'], "- HRV：" + values['hrv'], ""]
    if with_exercise:
        lines.extend(["## 昨日运动", "", values['exercise'], ""])
    lines.extend(["## 体能与疲劳", "", values['fitness'], "", "## 今天安排", ""])
    lines.extend(f"- {reports.clean(item)}" for item in actions)
    return "\n".join(lines)


D1_SLEEP_API = os.environ.get("D1_SLEEP_API", "https://fitness-dashboard-9qn.pages.dev/api/sleep")


def d1_sleep(day):
    """Read the day's sleep from the unified D1 store, shaped like Garmin's payload.

    Used only when a direct Garmin query fails; D1 may lag, so freshness is the
    caller's problem and the source line says where the numbers came from.
    """
    url = f"{D1_SLEEP_API}?date={quote(day)}"
    try:
        token = os.environ.get("D1_SLEEP_TOKEN")
        headers = {"User-Agent": "issues-blog-reports", "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with urlopen(Request(url, headers=headers), timeout=15) as response:
            row = json.load(response)
    except Exception:
        return None
    if not isinstance(row, dict) or row.get("date") != day or not row.get("total_seconds"):
        return None
    dto = {
        "calendarDate": row["date"],
        "sleepTimeSeconds": row.get("total_seconds"),
        "deepSleepSeconds": row.get("deep_seconds"),
        "lightSleepSeconds": row.get("light_seconds"),
        "remSleepSeconds": row.get("rem_seconds"),
        "awakeSleepSeconds": row.get("awake_seconds"),
        "sleepScores": {"overall": {"value": row.get("sleep_score")}},
    }
    hrv = {"calendarDate": row["date"], "lastNightAvg": row.get("hrv_last_night"),
           "weeklyAvg": row.get("hrv_weekly_avg"), "status": row.get("hrv_status"),
           "baseline": {"balancedLow": row.get("hrv_baseline_low"),
                        "balancedUpper": row.get("hrv_baseline_high")}}
    return {"dailySleepDTO": dto, "restingHeartRate": row.get("resting_hr"),
            "hrvSummary": hrv, "_d1_fallback": True}


def fetch_payload(day):
    from garminconnect import Garmin
    client = Garmin(os.environ.get("GARMIN_EMAIL"), os.environ.get("GARMIN_PASSWORD"),
                    is_cn=os.environ.get("GARMIN_IS_CN", "true").lower() in {"true", "1", "yes"})
    try:
        client.login(os.environ.get("GARMIN_TOKEN_STORE"))
        payload = client.get_sleep_data(day)
    except Exception:
        fallback = d1_sleep(day)
        if fallback is None:
            raise reports.ReportError("Garmin login or sleep query failed; check credentials / session / watch sync") from None
        return {**fallback, "localContext": {"activity_date": (date.fromisoformat(day) - timedelta(days=1)).isoformat()}}
    yesterday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    context = {"activity_date": yesterday}
    for key, query in (("hrv", lambda: client.get_hrv_data(day)),
                       ("activities", lambda: client.get_activities_by_date(yesterday, yesterday))):
        try:
            context[key] = query()
        except Exception:
            context[key + "_error"] = True
    return {**payload, "localContext": context}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


HRV_STATUS = {
    "BALANCED": "BALANCED（7日均值处于个人基线内，恢复跟得上负荷）",
    "UNBALANCED": "UNBALANCED（7日均值略超出个人基线，偏高或偏低都算）",
    "LOW": "LOW（7日均值明显低于个人基线，多为压力或负荷堆积）",
    "POOR": "POOR（低于同龄健康下限，与个人基线无关）",
}


def hrv_status_text(status):
    key = str(status or "").strip().upper()
    return HRV_STATUS.get(key) or (reports.clean(status) if status else "未提供")


def activity_state(day, payload):
    """Classify yesterday's records as ok / empty / error.

    Empty means Garmin returned no record for the day, which is not evidence of
    zero training. Callers omit the exercise section instead of writing filler.
    """
    context = payload.get("localContext") or {}
    if context.get("activities_error"):
        return "error", []
    if not isinstance(context.get("activities"), list):
        return "empty", []
    yesterday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    selected, seen = [], set()
    for activity in context["activities"]:
        if not isinstance(activity, dict):
            continue
        try:
            if activity.get("startTimeGMT"):
                start = datetime.fromisoformat(activity["startTimeGMT"].replace("Z", "+00:00"))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                activity_day = start.astimezone(reports.TZ).date().isoformat()
            else:
                activity_day = activity.get("startTimeLocal", "")[:10]
        except (TypeError, ValueError):
            continue
        if activity_day != yesterday:
            continue
        identity = activity.get("activityId")
        if identity is not None:
            if str(identity) in seen:
                continue
            seen.add(str(identity))
        selected.append(activity)
    return ("ok" if selected else "empty"), selected


def recovery_source(day, payload):
    context = payload.get("localContext") or {}
    hrv = (context.get("hrv") or {}).get("hrvSummary") or {}
    if hrv.get("calendarDate") and hrv["calendarDate"] != day:
        hrv = {}
    baseline = hrv.get("baseline") or {}
    low, high = number(baseline.get("balancedLow")), number(baseline.get("balancedUpper"))
    valid = low is not None and high is not None and 0 < low <= high
    def ms(value):
        value = number(value)
        return f"{value:g} ms" if value is not None and value > 0 else "未提供"
    lines = ["## HRV 个人基线与恢复", ""]
    if context.get("hrv_error"):
        lines.append("HRV 接口读取失败，个人基线及7日均值未知。")
    else:
        lines.extend([f"- 昨夜平均 HRV：{ms(hrv.get('lastNightAvg'))}",
                      f"- HRV 7日均值：{ms(hrv.get('weeklyAvg'))}",
                      f"- 佳明个人基线：{f'{low:g}–{high:g} ms' if valid else '未提供（不能推算个人正常范围）'}",
                      f"- 佳明 HRV 状态：{hrv_status_text(hrv.get('status'))}"])
        for label, key in (("昨夜值", "lastNightAvg"), ("7日均值", "weeklyAvg")):
            value = number(hrv.get(key))
            if valid and value is not None and value > 0:
                position = "低于" if value < low else ("高于" if value > high else "处于")
                lines.append(f"- {label}相对个人基线：{position}基线范围")
        lines.append("单晚相对基线的位置不等于佳明的HRV状态；不依据单晚数据推断疾病或训练因果。")
    state, selected = activity_state(day, payload)
    if state == "error":
        # A failed query means unknown load, not zero load; keep that visible.
        lines.extend(["", "## 昨日运动", "", "运动接口读取失败，昨日运动量未知。"])
    elif state == "ok":
        yesterday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
        lines.extend(["", f"## 昨日运动 · {yesterday}（北京时间）", ""])
        durations = [number(a.get("duration")) for a in selected]
        total = sum(v for v in durations if v is not None)
        lines.append(f"共 {len(selected)} 次，已知运动时长合计 {reports.duration(total)}" +
                     ("（部分记录缺少时长）" if None in durations else "") + "。")
        names = {"running": "跑步", "walking": "步行", "cycling": "骑行", "strength_training": "力量训练",
                 "dance": "舞蹈", "fitness_equipment": "健身", "swimming": "游泳", "hiking": "徒步", "hiit": "HIIT"}
        for index, activity in enumerate(selected, 1):
            kind = (activity.get("activityType") or {}).get("typeKey", "未知类型")
            lines.extend(["", f"### 运动 {index} · {reports.clean(names.get(kind, kind))}",
                          f"- 时长：{reports.duration(number(activity.get('duration')))}"])
            for label, key, unit in (("平均心率", "averageHR", "bpm"), ("最高心率", "maxHR", "bpm"),
                                     ("有氧训练效果", "aerobicTrainingEffect", ""),
                                     ("无氧训练效果", "anaerobicTrainingEffect", ""),
                                     ("训练负荷", "activityTrainingLoad", "")):
                value = number(activity.get(key))
                lines.append(f"- {label}：{f'{value:g} {unit}'.strip() if value is not None else '未提供'}")
            distance = number(activity.get("distance"))
            if distance is not None:
                lines.append(f"- 距离：{distance / 1000:.2f} km")
    return "\n".join(lines)


def telegram_html(markdown):
    """Render the report's Markdown subset using only Telegram-supported tags."""
    inline_pattern = re.compile(
        r"\\([\\`*_{}\[\]<>#|!~])|`([^`\n]+)`|"
        r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)|"
        r"\*\*(.+?)\*\*|__(.+?)__|~~(.+?)~~|"
        r"(?<!\*)\*([^*\n]+)\*(?!\*)|(?<![\w_])_([^_\n]+)_(?![\w_])"
    )

    def inline(text):
        parts, end = [], 0
        for match in inline_pattern.finditer(text):
            parts.append(html.escape(text[end:match.start()], quote=False))
            escaped, code, label, url, bold, bold2, strike, italic, italic2 = match.groups()
            if escaped is not None:
                parts.append(html.escape(escaped, quote=False))
            elif code is not None:
                parts.append('<code>' + html.escape(code, quote=False) + '</code>')
            elif url is not None:
                parts.append('<a href="' + html.escape(url, quote=True) + '">' + html.escape(label, quote=False) + '</a>')
            else:
                tag = 'b' if bold is not None or bold2 is not None else ('s' if strike is not None else 'i')
                content = next(v for v in (bold, bold2, strike, italic, italic2) if v is not None)
                parts.append('<' + tag + '>' + inline(content) + '</' + tag + '>')
            end = match.end()
        parts.append(html.escape(text[end:], quote=False))
        return ''.join(parts)

    lines, code_lines, fence = [], [], None
    for line in markdown.splitlines():
        if line.lstrip().startswith('```'):
            if fence is None:
                fence = True
            else:
                lines.append('<pre>' + html.escape('\n'.join(code_lines), quote=False) + '</pre>')
                fence, code_lines = None, []
            continue
        if fence:
            code_lines.append(line)
            continue
        heading = re.match(r'^\s{0,3}#{1,6}\s+(.+?)(?:\s+#+)?$', line)
        if heading:
            lines.append('<b>' + inline(heading[1]) + '</b>')
        elif re.fullmatch(r'\s*(?:-{3,}|\*{3,}|_{3,})\s*', line):
            lines.append('────────')
        else:
            line = re.sub(r'^(\s*)[-*+]\s+', r'\1• ', line)
            lines.append(inline(line))
    if fence:
        lines.append('<pre>' + html.escape('\n'.join(code_lines), quote=False) + '</pre>')
    return '\n'.join(lines)


def telegram_chunks(rendered, limit=3300, numbered=True):
    """Split at paragraph/sentence boundaries, closing/reopening formatting tags."""
    class Splitter(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack, self.parts, self.chunks = [], [], []
            self.units = 0

        def flush(self):
            if not self.units:
                return
            self.chunks.append(''.join(self.parts) + ''.join(f'</{tag}>' for tag, opening in reversed(self.stack)))
            self.parts = [opening for tag, opening in self.stack]
            self.units = 0

        def handle_starttag(self, tag, attrs):
            opening = self.get_starttag_text()
            self.parts.append(opening)
            self.stack.append((tag, opening))

        def handle_endtag(self, tag):
            self.parts.append(f'</{tag}>')
            self.stack.pop()

        def handle_data(self, text):
            for piece in re.split(r'(\n\n+|\n|(?<=[。！？；])|[ \t]+)', text):
                if not piece:
                    continue
                if piece.startswith('\n') and self.units >= min(1800, limit // 2):
                    self.flush()
                    continue
                units = len(piece.encode('utf-16-le')) // 2
                if self.units and self.units + units > limit:
                    self.flush()
                # Very long paragraphs/code without punctuation may need a hard boundary.
                while units > limit:
                    size, index = 0, 0
                    for char in piece:
                        char_size = len(char.encode('utf-16-le')) // 2
                        if size + char_size > limit:
                            break
                        size += char_size
                        index += 1
                    self.parts.append(html.escape(piece[:index], quote=False))
                    self.units += size
                    self.flush()
                    piece = piece[index:]
                    units = len(piece.encode('utf-16-le')) // 2
                self.parts.append(html.escape(piece, quote=False))
                self.units += units
    parser = Splitter()
    parser.feed(rendered)
    parser.close()
    parser.flush()
    chunks = parser.chunks
    if numbered and len(chunks) > 1:
        chunks = [f'<b>早报 · {i}/{len(chunks)}</b>\n\n{chunk}' for i, chunk in enumerate(chunks, 1)]
    return chunks


def report_chunks(state):
    # Detailed metrics remain available locally; the notification is the edited brief only.
    return telegram_chunks(telegram_html(f"# {state['title']}\n\n{state['interpretation']}"))


def fitness_source():
    """Read the fitness dashboard API for load / fatigue / form."""
    try:
        with urlopen(Request(FITNESS_API, headers={"User-Agent": "issues-blog-reports",
                                                 "Accept": "application/json"}), timeout=15) as response:
            data = json.load(response)
        summary = data["summary"]
        ctl, atl, tsb = float(summary["ctl"]), float(summary["atl"]), float(summary["tsb"])
    except Exception:
        return "## 体能与疲劳\n\n体能接口读取失败，今天的负荷与恢复状态未知。"
    ratio = atl / ctl if ctl else 0
    week_load = summary.get("week_load")
    prev_week = summary.get("prev_week_load")
    delta = summary.get("ctl_delta")
    lines = [f"## 体能与疲劳（截至 {data.get('today', '')}）", "",
             f"- 体能 CTL：{ctl:g}（42天负荷移动平均）",
             f"- 疲劳 ATL：{atl:g}（7天负荷移动平均）",
             f"- 状态 TSB：{tsb:g}（{summary.get('label', '未知')}）",
             f"- 疲劳比 ATL/CTL：{ratio:.2f}"]
    if week_load is not None and prev_week is not None:
        lines.append(f"- 近7天负荷：{week_load:g}，前7天：{prev_week:g}")
    if delta is not None:
        lines.append(f"- 近7天体能变化：{delta:+.1f}")
    advice = summary.get("advice")
    if advice:
        lines.extend(["", reports.clean(advice)])
    lines.append("")
    lines.append("TSB 为当天开始前的体能减疲劳，负数越大表示疲劳压得越重。")
    return "\n".join(lines)


def run(args):
    day = (args.date or reports.report_date("sleep")).isoformat()
    state_dir = args.state_dir.expanduser()
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_dir.chmod(0o700)
    # Serialize manual and scheduled runs before reading delivery state.
    with (state_dir / "report.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = state_dir / (day + ".json")
        state = json.loads(path.read_text()) if path.exists() else {}
        chat = reports.required("TELEGRAM_CHAT_ID") if args.send else None
        destination = hashlib.sha256(chat.encode()).hexdigest() if chat else None
        status = state.get("deliveries", {}).get(destination)
        if args.send and status == "sent" and not getattr(args, "resend", False):
            print("Already delivered; skipped")
            return
        if args.send and status == "sending":
            raise reports.ReportError("Previous send has uncertain outcome; inspect Telegram and local state before retrying")
        if getattr(args, "refresh", False) and any(v in {"sending", "pending"} for v in state.get("deliveries", {}).values()):
            raise reports.ReportError("Cannot refresh a report with an unfinished delivery; inspect local delivery state first")
        if not state or getattr(args, "refresh", False):
            payload = json.loads(args.input.read_text()) if args.input else fetch_payload(day)
            title, body = reports.sleep_report(day, payload)
            # Save the validated source before contacting the model.
            source = body + "\n\n" + recovery_source(day, payload) + "\n\n" + fitness_source()
            state = {"title": title, "source": source,
                     "deliveries": state.get("deliveries", {}), "schema_version": 3,
                     "message_ids": state.get("message_ids", {}),
                     "delivery_progress": state.get("delivery_progress", {})}
            save(path, state)
        if not state.get("interpretation") or getattr(args, "rewrite", False):
            if any(v in {"sending", "pending"} for v in state.get("deliveries", {}).values()):
                raise reports.ReportError("Cannot rewrite a report with unfinished delivery")
            # The exercise section is omitted entirely when Garmin has no record.
            with_exercise = "## 昨日运动" in state["source"]
            state["interpretation"] = interpret(state["title"], state["source"], with_exercise)
            state["brief_version"] = 7
            state["model"] = os.environ.get("MAGPIE_MODEL", DEFAULT_MODEL)
            save(path, state)
        text = f"# {state['title']}\n\n{state['interpretation']}\n\n## 原始指标\n{state['source']}"
        if args.send:
            bot = reports.required("TELEGRAM_BOT_TOKEN")
            chunks = report_chunks(state)
            digest = hashlib.sha256(json.dumps(chunks, ensure_ascii=False).encode()).hexdigest()
            progress = state.setdefault("delivery_progress", {}).get(destination)
            if status == "sent" or progress is None:
                progress = {"digest": digest, "message_ids": []}
                state["delivery_progress"][destination] = progress
            elif progress["digest"] != digest:
                raise reports.ReportError("Report changed during partial delivery; inspect local delivery state before retrying")
            for chunk in chunks[len(progress["message_ids"]):]:
                state["deliveries"][destination] = "sending"
                save(path, state)
                # Persist each receipt; an uncertain chunk is never automatically retried.
                result = reports.api(f"https://api.telegram.org/bot{bot}/sendMessage", method="POST",
                                     data={"chat_id": chat, "text": chunk, "parse_mode": "HTML",
                                           "link_preview_options": {"is_disabled": True}})
                if not result.get("ok"):
                    state["deliveries"][destination] = "pending"
                    save(path, state)
                    raise reports.ReportError("Telegram rejected report")
                progress["message_ids"].append(result.get("result", {}).get("message_id"))
                state["deliveries"][destination] = "pending"
                save(path, state)
            state["message_ids"] = state.get("message_ids", {})
            state["message_ids"][destination] = progress["message_ids"]
            state["deliveries"][destination] = "sent"
            save(path, state)
            print(f"Report delivered ({len(chunks)} messages)")
        else:
            output = state_dir / (day + ".md")
            output.write_text(text + "\n")
            output.chmod(0o600)
            print(f"Preview saved to {output}")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--input", type=Path, help="Saved Garmin JSON for preview/testing")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--send", action="store_true", help="Send to configured Telegram destination")
    parser.add_argument("--rewrite", action="store_true", help="Rewrite the saved source without fetching Garmin again")
    parser.add_argument("--refresh", action="store_true", help="Refresh source and regenerate interpretation")
    parser.add_argument("--resend", action="store_true", help="Explicitly resend a successfully delivered report")
    parser.add_argument("--config", type=Path, help="Private JSON mapping of environment variables")
    args = parser.parse_args()
    if args.config:
        config = json.loads(args.config.expanduser().read_text())
        if not isinstance(config, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in config.items()):
            raise reports.ReportError("Config must map environment names to string values")
        os.environ.update(config)
    run(args)


if __name__ == "__main__":
    try:
        main()
    except (reports.ReportError, OSError, ValueError) as error:
        # Do not print raw network errors, credentials or health data in scheduler logs.
        print(str(error) if isinstance(error, reports.ReportError) else "Local report failed; check local configuration/state", file=sys.stderr)
        sys.exit(1)
