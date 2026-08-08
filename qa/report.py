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

import time
from pathlib import Path
from xml.sax.saxutils import escape

from .runner import ScenarioResult


def write_reports(suite_name: str, report_dir: Path, results: list[ScenarioResult],
                  *, interrupted: bool = False) -> tuple[Path, Path]:
    junit = report_dir / "junit.xml"
    md = report_dir / "summary.md"
    junit.write_text(_render_junit(suite_name, results, interrupted=interrupted), encoding="utf-8")
    md.write_text(_render_markdown(suite_name, results, interrupted=interrupted), encoding="utf-8")
    return junit, md


def _render_junit(suite_name: str, results: list[ScenarioResult], *, interrupted: bool = False) -> str:
    errors = sum(1 for r in results if r.errored)
    failures = sum(1 for r in results if not r.passed and not r.errored)
    total_time = sum(r.duration_s for r in results)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuite name="{escape(suite_name)}" tests="{len(results)}" '
        f'failures="{failures}" errors="{errors}" time="{total_time:.2f}"'
        + (' interrupted="true">' if interrupted else '>'),
    ]
    for r in results:
        parts.append(
            f'  <testcase name="{escape(r.name)}" time="{r.duration_s:.2f}"'
            + (' />' if r.passed else '>')
        )
        if not r.passed:
            tag = "error" if r.errored else "failure"
            body = _cdata(
                f'{r.failure_message}\n\n--- recent logs ---\n'
                + "\n".join(r.recent_logs[-50:])
            )
            parts.append(
                f'    <{tag} message="{escape(_one_line(r.failure_message))}">'
                f'{body}</{tag}>'
            )
            parts.append('  </testcase>')
    parts.append('</testsuite>')
    return "\n".join(parts) + "\n"


def _cdata(s: str) -> str:
    """Wrap `s` in a CDATA section, neutralizing any embedded `]]>` (which would
    otherwise terminate the section early and break XML well-formedness) by
    splitting it across two CDATA blocks."""
    return "<![CDATA[" + s.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _render_markdown(suite_name: str, results: list[ScenarioResult], *, interrupted: bool = False) -> str:
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    total_time = sum(r.duration_s for r in results)
    status = "INTERRUPTED" if interrupted else ("PASS" if failed == 0 else "FAIL")
    lines = [
        f"# {suite_name} — {status}",
        "",
    ]
    if interrupted:
        lines.append("> ⚠️ **Partial run** — the suite was interrupted (Ctrl-C / "
                     "SIGTERM) before all scenarios ran. The scenarios below are "
                     "only those that completed.")
        lines.append("")
    lines += [
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
