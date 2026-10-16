from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))

import telegram_memos

DEFAULT_FEED_URL = "https://blog.kazoottt.top/rss.xml"
DEFAULT_STATE_PATH = Path("data/telegram/rss-seen.json")
MAX_SEEN = 500


class RssStateMissing(Exception):
    """The current feed has not been seeded, so nothing may be posted."""


@dataclass(frozen=True)
class RssItem:
    id: str
    title: str
    link: str


@dataclass(frozen=True)
class RssPlan:
    messages: list[str]
    new_items: list[RssItem]
    seen: list[str]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_rss_items(xml_text: str, feed_url: str) -> list[RssItem]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as error:
        raise ValueError(f"RSS XML is invalid: {error}") from error

    items: list[RssItem] = []
    seen_ids: set[str] = set()
    for element in root.iter():
        if local_name(element.tag) not in {"item", "entry"}:
            continue
        title = ""
        link = ""
        guid = ""
        for child in list(element):
            name = local_name(child.tag)
            if name == "title" and not title:
                title = "".join(child.itertext()).strip()
            elif name == "link" and not link:
                rel = child.attrib.get("rel", "alternate")
                if rel not in {"alternate", ""}:
                    continue
                text = "".join(child.itertext()).strip()
                href = child.attrib.get("href", "").strip()
                link = text or href
            elif name in {"guid", "id"} and not guid:
                guid = "".join(child.itertext()).strip()
        if not link and guid.startswith(("http://", "https://")):
            link = guid
        if not link:
            continue
        absolute = urljoin(feed_url, link)
        item_id = guid or absolute
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        items.append(RssItem(id=item_id, title=title, link=absolute))
    return items


def format_rss_message(item: RssItem) -> str:
    title = " ".join(item.title.split()) or "未命名文章"
    return f"新文章：{title}\n{item.link}"


def merge_seen(
    seen: list[str],
    extra: list[str],
    *,
    limit: int = MAX_SEEN,
) -> list[str]:
    merged = list(dict.fromkeys([*seen, *extra]))
    if len(merged) > limit:
        return merged[-limit:]
    return merged


def plan_rss_notifications(
    items: list[RssItem],
    seen: list[str] | None,
    *,
    seed: bool,
) -> RssPlan:
    if seed:
        return RssPlan(
            messages=[],
            new_items=[],
            seen=merge_seen(seen or [], [item.id for item in items]),
        )
    if seen is None:
        raise RssStateMissing(
            "RSS state is missing. Refusing to post existing articles. "
            "Run once with --seed to record the current feed without sending."
        )
    seen_ids = set(seen)
    chronological = list(reversed([item for item in items if item.id not in seen_ids]))
    return RssPlan(
        messages=[format_rss_message(item) for item in chronological],
        new_items=chronological,
        seen=merge_seen(seen, [item.id for item in chronological]),
    )


def send_planned_messages(
    plan: RssPlan,
    send: Callable[[str], None],
) -> tuple[list[str], BaseException | None]:
    sent: list[str] = []
    try:
        for item, message in zip(plan.new_items, plan.messages, strict=True):
            send(message)
            sent.append(item.id)
    except (Exception, SystemExit) as error:
        return sent, error
    return sent, None


def load_seen(path: Path) -> list[str] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"RSS state file is not valid JSON: {path}: {error}") from None
    if not isinstance(data, dict) or not isinstance(data.get("seen"), list):
        raise SystemExit(f"RSS state file must be an object with a seen list: {path}")
    seen: list[str] = []
    for item in data["seen"]:
        if not isinstance(item, str) or not item.strip():
            raise SystemExit(f"RSS state file has an invalid seen id: {path}")
        seen.append(item.strip())
    return seen


def save_seen(path: Path, seen: list[str], feed: str) -> bool:
    text = json.dumps({"feed": feed, "seen": seen}, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def fetch_feed(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "issues-blog-rss-notify"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as error:
        raise SystemExit(f"RSS fetch failed: HTTP {error.code} for {url}") from None
    except urllib.error.URLError as error:
        raise SystemExit(f"RSS fetch failed for {url}: {error.reason}") from None


def load_feed_xml(feed: str, input_path: str | None) -> str:
    if not input_path:
        return fetch_feed(feed)
    if input_path == "-":
        return sys.stdin.read()
    return Path(input_path).read_text(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send new blog RSS items to Telegram.",
    )
    parser.add_argument("--feed", default=DEFAULT_FEED_URL)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument(
        "--input",
        help="Read RSS XML from a file, or - for stdin, instead of the feed URL.",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Record the current feed as already sent without posting.",
    )
    parser.add_argument(
        "--resend-latest",
        action="store_true",
        help="Send the newest feed item again without changing state.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print messages without calling Telegram or writing state.",
    )
    args = parser.parse_args()
    if args.seed and args.resend_latest:
        parser.error("--seed and --resend-latest cannot be used together")
    return args


def main() -> None:
    args = parse_args()
    xml_text = load_feed_xml(args.feed, args.input)
    try:
        items = parse_rss_items(xml_text, args.feed)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    source = args.input or args.feed
    print(f"Parsed {len(items)} RSS items from {source}")

    if args.resend_latest:
        if not items:
            raise SystemExit("RSS feed has no items to send")
        message = format_rss_message(items[0])
        print(message)
        if args.dry_run:
            print("Dry run; Telegram message not sent")
            return
        telegram_memos.send_message(message)
        print("Latest item resent; RSS state was not changed")
        return

    seen = load_seen(args.state)
    try:
        plan = plan_rss_notifications(items, seen, seed=args.seed)
    except RssStateMissing as error:
        raise SystemExit(str(error)) from None

    if args.seed:
        added = len(set(plan.seen) - set(seen or []))
        print(f"Seeded {len(plan.seen)} RSS items ({added} newly marked); nothing sent")
        if args.dry_run:
            print("Dry run; RSS state not updated")
            return
        if save_seen(args.state, plan.seen, args.feed):
            print(f"Wrote RSS state to {args.state}")
        else:
            print("RSS state already up to date")
        return

    if not plan.messages:
        print("No new RSS items")
        return

    print(f"{len(plan.messages)} new RSS item(s)")
    if args.dry_run:
        for message in plan.messages:
            print(message)
            print("---")
        print("Dry run; Telegram messages not sent and RSS state not updated")
        return

    def send_and_log(message: str) -> None:
        print(message)
        print("---")
        telegram_memos.send_message(message)

    sent_ids, failure = send_planned_messages(plan, send_and_log)
    if sent_ids:
        updated = merge_seen(seen or [], sent_ids)
        if save_seen(args.state, updated, args.feed):
            print(f"Recorded {len(sent_ids)} sent RSS items in {args.state}")
    if failure is not None:
        if isinstance(failure, SystemExit):
            raise failure from None
        raise SystemExit(telegram_memos.redact(str(failure))) from None


if __name__ == "__main__":
    main()
