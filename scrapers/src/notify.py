# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Telegram bot notifications for the scraper cron run.

Reads ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` from the environment;
silently no-ops when they're absent so local dev runs don't try to ping a bot.

Invoked from ``run_cron.sh`` as:
    python -m src.notify <rc> <duration_s> <new_hash> <prev_hash> <log_path>
"""

import html
import os
import sys
from collections import deque
from pathlib import Path

import requests

TELEGRAM_API = "https://api.telegram.org"
MAX_TELEGRAM_LEN = 4000  # Telegram caps at 4096; leave headroom for safety.
TAIL_LINES = 30
HOST = "srednabg.com"


def send_telegram(text: str, *, parse_mode: str = "HTML") -> bool:
    """POST a message to Telegram. Returns True on HTTP 2xx, else False."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            f"{TELEGRAM_API}/bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text[:MAX_TELEGRAM_LEN],
                "parse_mode": parse_mode,
                "disable_web_page_preview": "true",
            },
            timeout=10,
        )
        return r.ok
    except requests.RequestException:
        return False


def _tail(path: Path, lines: int) -> str:
    """Return the last ``lines`` lines of ``path``, or empty if unreadable."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return "".join(deque(fh, maxlen=lines))
    except OSError:
        return ""


def _short_hash(h: str) -> str:
    """Trim 'sha256:abcdef…' to 14 hex chars for compact display."""
    if not h or h == "-":
        return "(none)"
    if h.startswith("sha256:"):
        return f"sha256:{h[7:21]}…"
    return h[:20]


def format_success(zone_count: int, new_hash: str, prev_hash: str, duration_s: int) -> str:
    changed = "no" if new_hash and prev_hash and new_hash == prev_hash else "yes"
    return (
        "✅ <b>SrednaBG scraper OK</b>\n"
        f"zones: <b>{zone_count}</b>\n"
        f"hash: <code>{html.escape(_short_hash(new_hash))}</code>\n"
        f"changed: <b>{changed}</b>\n"
        f"duration: {duration_s}s\n"
        f"host: {HOST}"
    )


def format_failure(rc: int, duration_s: int, log_tail: str) -> str:
    tail = html.escape(log_tail.rstrip()) if log_tail else "(no log content)"
    return (
        f"❌ <b>SrednaBG scraper FAILED</b>  rc={rc}\n"
        f"duration: {duration_s}s\n"
        f"host: {HOST}\n"
        f"<pre>--- last {TAIL_LINES} lines of cron.log ---\n"
        f"{tail}</pre>"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print(
            "usage: python -m src.notify <rc> <duration_s> <new_hash> "
            "<prev_hash> <log_path>",
            file=sys.stderr,
        )
        return 2
    rc_str, dur_str, new_hash, prev_hash, log_path_str = argv
    try:
        rc = int(rc_str)
        duration_s = int(dur_str)
    except ValueError:
        print("rc and duration must be integers", file=sys.stderr)
        return 2

    log_path = Path(log_path_str)

    if rc == 0:
        text = format_success(
            zone_count=_count_from_state(log_path),
            new_hash=new_hash,
            prev_hash=prev_hash,
            duration_s=duration_s,
        )
    else:
        text = format_failure(
            rc=rc,
            duration_s=duration_s,
            log_tail=_tail(log_path, TAIL_LINES),
        )

    sent = send_telegram(text)
    if not sent:
        # Don't fail the cron just because notification failed; log and exit 0.
        print("notify: send_telegram returned False", file=sys.stderr)
    return 0


def _count_from_state(log_path: Path) -> int:
    """Best-effort: parse the latest RESULT line from the log."""
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            tail = list(deque(fh, maxlen=200))
    except OSError:
        return 0
    for line in reversed(tail):
        if line.startswith("RESULT "):
            for tok in line.split():
                if tok.startswith("zone_count="):
                    try:
                        return int(tok.split("=", 1)[1])
                    except ValueError:
                        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
