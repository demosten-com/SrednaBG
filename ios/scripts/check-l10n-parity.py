#!/usr/bin/env python3
"""Pin the strings the Live Activity and the in-app UI must word identically.

The Lock Screen / Dynamic Island widget keeps its own string catalogue
(`SrednaBGWidgets/Localizable.xcstrings`) because it is a separate target from
`SrednaBGUI` (`Resources/{en,bg}.lproj/Localizable.strings`). Both are
hand-maintained, so a wording change on one side can silently leave the two
surfaces disagreeing about the *same* state — the driver glances at the Lock
Screen and the app and reads two different words for one condition.

Only a few keys actually have to agree, and this file names them. Most of the
widget catalogue is deliberately *not* a mirror: the Live Activity is a compact
surface with its own register ("avg" / "left" against the app's "Average speed" /
"Remaining"), so a blanket key diff would be almost all false positives. Add a
pair below only when the two surfaces genuinely describe the same thing.

Usage:  python3 ios/scripts/check-l10n-parity.py
Exits 1 and prints every mismatch when the surfaces have drifted.
"""

import json
import re
import sys
from pathlib import Path

IOS = Path(__file__).resolve().parent.parent

WIDGET_CATALOG = IOS / "SrednaBGWidgets" / "Localizable.xcstrings"
UI_STRINGS = IOS / "Packages/SrednaBGUI/Sources/SrednaBGUI/Resources/{lang}.lproj/Localizable.strings"

LANGUAGES = ("en", "bg")

# (widget key, SrednaBGUI key, why they must match)
PAIRS = [
    (
        "liveActivityUnmeasured",
        "statusUnmeasured",
        "The one state whose whole point is an honest disclaimer — the Lock "
        "Screen and the app must decline to measure in the same words.",
    ),
]


def widget_strings():
    data = json.loads(WIDGET_CATALOG.read_text(encoding="utf-8"))
    out = {}
    for key, entry in data.get("strings", {}).items():
        for lang, loc in entry.get("localizations", {}).items():
            value = loc.get("stringUnit", {}).get("value")
            if value is not None:
                out[(key, lang)] = value
    return out


def ui_strings(lang):
    text = UI_STRINGS.as_posix().format(lang=lang)
    body = Path(text).read_text(encoding="utf-8")
    # "key" = "value";  — the .strings format, one entry per line.
    return dict(re.findall(r'^\s*"([^"]+)"\s*=\s*"(.*)"\s*;', body, re.MULTILINE))


def main():
    widget = widget_strings()
    ui = {lang: ui_strings(lang) for lang in LANGUAGES}

    problems = []
    for widget_key, ui_key, why in PAIRS:
        for lang in LANGUAGES:
            left = widget.get((widget_key, lang))
            right = ui[lang].get(ui_key)
            if left is None:
                problems.append(f"[{lang}] widget catalogue has no {widget_key!r}")
            elif right is None:
                problems.append(f"[{lang}] SrednaBGUI has no {ui_key!r}")
            elif left != right:
                problems.append(
                    f"[{lang}] {widget_key!r} = {left!r} but {ui_key!r} = {right!r}\n"
                    f"        {why}"
                )

    if problems:
        print("Live Activity / in-app wording has drifted:\n", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    checked = len(PAIRS) * len(LANGUAGES)
    print(f"l10n parity OK — {checked} paired strings match across {', '.join(LANGUAGES)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
