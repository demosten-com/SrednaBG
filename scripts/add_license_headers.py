#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scripts

"""Insert SPDX license headers into first-party SrednaBG source files.

Walks an explicit allow-list of source roots under the repo and inserts a
4-line SPDX header block at the top of every `.kt`, `.swift`, `.py`, and `.sh`
file that does not already carry one. Idempotent: re-running is a no-op.

Usage:
    python3 scripts/add_license_headers.py            # write changes in place
    python3 scripts/add_license_headers.py --dry-run  # list files; write nothing
    python3 scripts/add_license_headers.py --check    # exit 1 if any are missing
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

COPYRIGHT_LINE = "SPDX-FileCopyrightText: 2026 SrednaBG Contributors"
LICENSE_LINE = "SPDX-License-Identifier: MIT"
PROJECT_NAME = "SrednaBG"

CODING_RE = re.compile(rb"coding[:=]\s*[-\w.]+")


@dataclass(frozen=True)
class Root:
    """A source-tree root to scan."""

    path: str  # repo-relative
    label: str  # subproject label rendered into the header
    extensions: tuple[str, ...]  # e.g. (".kt",), (".swift",), (".py",)


# Order matters: longest-prefix wins. Specific paths first, broad ones last.
ROOTS: tuple[Root, ...] = (
    # Android
    Root("android/core/src", "android / core", (".kt",)),
    Root("android/app/src", "android / app", (".kt",)),
    # iOS — main app shell + tests
    Root("ios/SrednaBG", "ios / SrednaBG", (".swift",)),
    Root("ios/SrednaBGTests", "ios / SrednaBG", (".swift",)),
    Root("ios/SrednaBGUITests", "ios / SrednaBG", (".swift",)),
    # iOS — SPM packages
    Root("ios/Packages/SrednaBGCore", "ios / SrednaBGCore", (".swift",)),
    Root("ios/Packages/SrednaBGData", "ios / SrednaBGData", (".swift",)),
    Root("ios/Packages/SrednaBGTracking", "ios / SrednaBGTracking", (".swift",)),
    Root("ios/Packages/SrednaBGMapCore", "ios / SrednaBGMapCore", (".swift",)),
    Root("ios/Packages/SrednaBGUI", "ios / SrednaBGUI", (".swift",)),
    Root("ios/Packages/SrednaBGCarPlay", "ios / SrednaBGCarPlay", (".swift",)),
    # Python + shell — most specific first so backend/scripts wins over a backend root
    Root("backend/scripts", "backend / scripts", (".py", ".sh")),
    Root("scrapers", "scrapers", (".py", ".sh")),
    Root("qa", "qa", (".py", ".sh")),
    Root("scripts", "scripts", (".py", ".sh")),
    # Shell — web tooling (specific web/fdroid/scripts root before the broad web root)
    Root("web/fdroid/scripts", "web / fdroid", (".sh",)),
    Root("web", "web", (".sh",)),
)

# Defense-in-depth: even if a Root path includes one of these, skip.
SKIP_DIR_NAMES = frozenset(
    {
        "build",
        ".gradle",
        ".build",
        "DerivedData",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".pytest_cache",
        "node_modules",
        ".idea",
        ".git",
        "OfflineMap",  # gitignored map bundle under ios/SrednaBG/App/Resources/
    }
)
# Skip these subtrees by relative path (prefix match).
SKIP_PREFIXES = (
    "scrapers/data",  # input/output data, not source
    "ios/.build/checkouts",  # fetched SPM deps
)


def header_block(label: str, comment: str) -> list[str]:
    """Return the 4-line SPDX header (without trailing blank line)."""
    return [
        f"{comment} {LICENSE_LINE}",
        f"{comment} {COPYRIGHT_LINE}",
        f"{comment}",
        f"{comment} {PROJECT_NAME} — {label}",
    ]


def comment_marker_for(ext: str) -> str:
    if ext in (".kt", ".swift"):
        return "//"
    if ext in (".py", ".sh"):
        return "#"
    raise ValueError(f"unsupported extension: {ext}")


def already_has_header(content_bytes: bytes) -> bool:
    """True if the SPDX license tag appears in the first 5 lines."""
    head = content_bytes.split(b"\n", 5)[:5]
    return any(LICENSE_LINE.encode() in line for line in head)


def detect_line_ending(content_bytes: bytes) -> bytes:
    """Return b'\\r\\n' if the file uses CRLF, else b'\\n'."""
    # First 4KB is plenty to detect.
    sample = content_bytes[:4096]
    if b"\r\n" in sample:
        return b"\r\n"
    return b"\n"


def split_script_prologue(lines: list[bytes], ext: str) -> tuple[list[bytes], list[bytes]]:
    """Pull off the shebang (and, for Python, a PEP 263 coding declaration).

    Applies to `#`-comment scripts (`.py`, `.sh`) so the SPDX block lands just
    below any `#!...` line rather than displacing it.

    Returns (prologue_lines, remaining_lines).
    """
    prologue: list[bytes] = []
    rest = list(lines)
    if rest and rest[0].startswith(b"#!"):
        prologue.append(rest.pop(0))
    # PEP 263: coding declaration must be in line 1 or 2. If we already took a
    # shebang from line 1, the coding line (if any) is now rest[0]. Python only.
    if ext == ".py" and rest and rest[0].startswith(b"#") and CODING_RE.search(rest[0]):
        prologue.append(rest.pop(0))
    return prologue, rest


def insert_header(path: Path, label: str) -> bool:
    """Insert the SPDX header into `path`. Returns True if the file was modified."""
    ext = path.suffix
    comment = comment_marker_for(ext)
    raw = path.read_bytes()

    if already_has_header(raw):
        return False

    eol = detect_line_ending(raw)
    had_trailing_newline = raw.endswith(eol) if raw else True

    # Split into lines without the trailing newline so we can re-join cleanly.
    if raw:
        if had_trailing_newline:
            body_text = raw[: -len(eol)]
        else:
            body_text = raw
        lines = body_text.split(eol)
    else:
        lines = []

    header_lines = [s.encode() for s in header_block(label, comment)]
    blank = b""

    if ext in (".py", ".sh"):
        prologue, remaining = split_script_prologue(lines, ext)
        if remaining and remaining[0] == b"":
            # Avoid double-blank between header and remaining content.
            remaining = remaining[1:]
        new_lines = prologue + header_lines + [blank] + remaining
    else:
        if lines and lines[0] == b"":
            lines = lines[1:]
        new_lines = header_lines + [blank] + lines

    new_bytes = eol.join(new_lines)
    if had_trailing_newline or raw == b"":
        new_bytes += eol

    path.write_bytes(new_bytes)
    return True


def is_skipped(rel: Path) -> bool:
    parts = rel.parts
    if any(p in SKIP_DIR_NAMES for p in parts):
        return True
    rel_str = rel.as_posix()
    return any(rel_str.startswith(prefix) for prefix in SKIP_PREFIXES)


def iter_target_files(roots: tuple[Root, ...]) -> list[tuple[Path, str]]:
    """Yield (absolute_path, label) for every source file under `roots`."""
    seen: set[Path] = set()
    out: list[tuple[Path, str]] = []
    for root in roots:
        base = REPO_ROOT / root.path
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix not in root.extensions:
                continue
            rel = path.relative_to(REPO_ROOT)
            if is_skipped(rel):
                continue
            if path in seen:
                continue
            seen.add(path)
            out.append((path, root.label))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="list files; write nothing")
    group.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any first-party source file is missing the SPDX header",
    )
    args = parser.parse_args()

    targets = iter_target_files(ROOTS)
    if not targets:
        print("No target files found. Did the repo layout change?", file=sys.stderr)
        return 1

    modified: list[Path] = []
    missing: list[Path] = []
    skipped = 0

    for path, label in targets:
        rel = path.relative_to(REPO_ROOT)
        raw = path.read_bytes()
        if already_has_header(raw):
            skipped += 1
            continue

        if args.check:
            missing.append(rel)
            continue

        if args.dry_run:
            print(rel)
            modified.append(rel)
            continue

        if insert_header(path, label):
            print(rel)
            modified.append(rel)
        else:
            skipped += 1

    total = len(targets)
    if args.check:
        if missing:
            print(f"Missing SPDX header in {len(missing)} file(s):", file=sys.stderr)
            for rel in missing:
                print(f"  {rel}", file=sys.stderr)
            return 1
        print(f"OK: all {total} files carry the SPDX header.")
        return 0

    suffix = " (dry run)" if args.dry_run else ""
    print(
        f"Modified {len(modified)} files (skipped {skipped} already-headered, scanned {total} total){suffix}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
