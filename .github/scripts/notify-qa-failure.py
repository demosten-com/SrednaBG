#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — CI

"""Tell the Telegram bot that the nightly QA job failed.

Failure-only by design: the workflow calls this under `if: failure()`, so a
green night is silent. Same bot and chat as the scraper cron
(`scrapers/src/notify.py`), but the credentials are a separate copy — the cron
reads `~/.config/srednabg/scraper.env` on the web host, this reads the
`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` repository secrets.

The message names what failed rather than just that something did: the failing
scenarios per platform from each `junit.xml`, or — when a platform produced no
report at all — that the job died before its suite ran (build, emulator boot,
Xcode licence), which is a different problem with a different fix.

Stdlib only: it has to work when the venv step is the thing that failed.

    python3 .github/scripts/notify-qa-failure.py            # send
    python3 .github/scripts/notify-qa-failure.py --dry-run  # print the message
"""

from __future__ import annotations

import html
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS = REPO_ROOT / "qa" / "reports"
PLATFORMS = ("android", "ios")
TELEGRAM_API = "https://api.telegram.org"
MAX_TELEGRAM_LEN = 4000  # Telegram caps at 4096; leave headroom for safety.
MAX_SCENARIOS = 12  # per platform — past that the list is noise, the link isn't
MAX_REASON_LEN = 160


def _latest_junit(platform: str) -> Path | None:
    found = sorted((REPORTS / platform).glob("*/junit.xml"), key=lambda p: p.stat().st_mtime)
    return found[-1] if found else None


def _failed_cases(junit: Path) -> tuple[int, list[tuple[str, str]]]:
    """(total scenarios, [(name, first line of the reason)]) for one report."""
    suite = ET.parse(junit).getroot()
    cases = list(suite.iter("testcase"))
    failed: list[tuple[str, str]] = []
    for case in cases:
        verdict = case.find("failure")
        if verdict is None:
            verdict = case.find("error")
        if verdict is None:
            continue
        reason = (verdict.get("message") or "").strip().splitlines()
        failed.append((case.get("name", "?"), reason[0][:MAX_REASON_LEN] if reason else ""))
    return len(cases), failed


def _zones_line(platform: str) -> str:
    """The catalog the run drove, as the harness printed it into its log."""
    try:
        log = (REPO_ROOT / f"qa-{platform}.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in log.splitlines():
        if "Zones under test:" in line:
            return line.split("Zones under test:", 1)[1].strip()
    return ""


def _platform_section(platform: str) -> str:
    try:
        junit = _latest_junit(platform)
        if junit is None:
            return (f"<b>{platform}</b>: no report — the job failed before this "
                    "platform's suite ran (build / device boot / setup)")
        total, failed = _failed_cases(junit)
        skipped = len(list(ET.parse(junit).getroot().iter("skipped")))
    except (ET.ParseError, OSError) as e:
        # A broken report must not prevent the other platform's summary or
        # the run link from reaching Telegram.
        print(f"notify: could not read {platform} QA report ({type(e).__name__})",
              file=sys.stderr)
        return (f"<b>{platform}</b>: report unavailable or invalid — "
                "see the run logs and artifacts")
    if not failed:
        return (f"<b>{platform}</b>: {total - skipped}/{total} passed"
                + (f", {skipped} skipped (see coverage report)" if skipped else ""))
    lines = [f"<b>{platform}</b>: {len(failed)} of {total} failed"
             + (f", {skipped} skipped" if skipped else "")]
    for name, reason in failed[:MAX_SCENARIOS]:
        lines.append(f"• <code>{html.escape(name)}</code> — {html.escape(reason)}")
    if len(failed) > MAX_SCENARIOS:
        lines.append(f"… and {len(failed) - MAX_SCENARIOS} more")
    return "\n".join(lines)


def build_message() -> str:
    platforms = os.environ.get("PLATFORMS", "both")
    ran = [p for p in PLATFORMS if platforms in ("both", p)]
    parts = [f"❌ <b>SrednaBG QA FAILED</b>  suite={html.escape(os.environ.get('SUITE', 'nightly'))}"]
    zones = next((z for z in map(_zones_line, ran) if z), "")
    if zones:
        parts.append(f"zones: {html.escape(zones)}")
    parts.extend(_platform_section(p) for p in ran)
    sha = os.environ.get("GITHUB_SHA", "")[:7]
    if sha:
        parts.append(f"commit: <code>{sha}</code>")
    if os.environ.get("RUN_URL"):
        parts.append(html.escape(os.environ["RUN_URL"]))
    return "\n".join(parts)


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("notify: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set, nothing sent. "
              "Add them as repository secrets:\n"
              "    gh secret set TELEGRAM_BOT_TOKEN\n"
              "    gh secret set TELEGRAM_CHAT_ID", file=sys.stderr)
        return False
    body = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text[:MAX_TELEGRAM_LEN],
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(
                f"{TELEGRAM_API}/bot{token}/sendMessage", data=body, timeout=10) as resp:
            return 200 <= resp.status < 300
    except OSError as e:
        # Never echo the URL — it carries the bot token.
        print(f"notify: Telegram request failed ({type(e).__name__})", file=sys.stderr)
        return False


def main(argv: list[str]) -> int:
    text = build_message()
    if "--dry-run" in argv:
        print(text)
        return 0
    if not send_telegram(text):
        print("notify: no Telegram message was sent", file=sys.stderr)
    # The job is already red; a notification problem must not change why.
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
