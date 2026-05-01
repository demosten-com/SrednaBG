# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Report writers — JUnit XML for CI consumption + Markdown for humans/Claude.

Both formats are emitted side-by-side in `qa/reports/<suite>-<ts>/`.
The Markdown summary is what /qa-app reads when it summarizes a run
back to the user.
"""

from __future__ import annotations

import html
import time
from pathlib import Path
from xml.sax.saxutils import escape

from .runner import ScenarioResult


def write_reports(suite_name: str, report_dir: Path, results: list[ScenarioResult]) -> tuple[Path, Path]:
    junit = report_dir / "junit.xml"
    md = report_dir / "summary.md"
    junit.write_text(_render_junit(suite_name, results), encoding="utf-8")
    md.write_text(_render_markdown(suite_name, results), encoding="utf-8")
    return junit, md


def _render_junit(suite_name: str, results: list[ScenarioResult]) -> str:
    failures = sum(1 for r in results if not r.passed)
    total_time = sum(r.duration_s for r in results)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuite name="{escape(suite_name)}" tests="{len(results)}" '
        f'failures="{failures}" errors="0" time="{total_time:.2f}">',
    ]
    for r in results:
        parts.append(
            f'  <testcase name="{escape(r.name)}" time="{r.duration_s:.2f}"'
            + (' />' if r.passed else '>')
        )
        if not r.passed:
            parts.append(
                f'    <failure message="{escape(_one_line(r.failure_message))}">'
                f'<![CDATA[{r.failure_message}\n\n--- recent logs ---\n'
                + "\n".join(r.recent_logs[-50:]) +
                ']]></failure>'
            )
            parts.append('  </testcase>')
    parts.append('</testsuite>')
    return "\n".join(parts) + "\n"


def _render_markdown(suite_name: str, results: list[ScenarioResult]) -> str:
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    total_time = sum(r.duration_s for r in results)
    status = "PASS" if failed == 0 else "FAIL"
    lines = [
        f"# {suite_name} — {status}",
        "",
        f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Total: **{len(results)}** scenarios — **{passed} passed** / **{failed} failed**",
        f"- Wall time: {total_time:.1f}s ({total_time/60:.1f}m)",
        "",
        "## Results",
        "",
        "| Scenario | Status | Duration | Notes |",
        "|----------|--------|----------|-------|",
    ]
    for r in results:
        status_cell = "✅" if r.passed else "❌"
        notes = ""
        if not r.passed:
            notes = _one_line(r.failure_message)[:120]
        lines.append(f"| `{r.name}` | {status_cell} | {r.duration_s:.1f}s | {notes} |")

    if failed:
        lines.append("")
        lines.append("## Failures")
        lines.append("")
        for r in results:
            if r.passed:
                continue
            lines.append(f"### `{r.name}`")
            lines.append("")
            lines.append("```")
            lines.append(r.failure_message)
            lines.append("```")
            lines.append("")
            lines.append("Recent log lines:")
            lines.append("")
            lines.append("```")
            for ln in r.recent_logs[-30:]:
                lines.append(ln)
            lines.append("```")
            lines.append("")
    return "\n".join(lines) + "\n"


def _one_line(s: str) -> str:
    return " ".join(s.split())
