#!/usr/bin/env python3
"""Convert srednabg QA track-format GPX into Xcode "Simulate Location" GPX.

Our QA fixtures (qa/fixtures/gpx/*.gpx) use the GPX *track* form
``<trk><trkseg><trkpt .../></trkseg></trk>`` — valid GPX 1.1 and what
``simctl``/the harness parsers consume. Xcode's location simulation, however,
reads **only** ``<wpt>`` waypoint elements (Apple's own GPX template is all
``<wpt>``); it silently ignores ``<trkpt>``, so a track-form file imports but
plays nothing. This converts each ``<trkpt>`` into an equivalent root-level
``<wpt>`` (same lat/lon/time). Xcode uses the per-waypoint ``<time>`` deltas to
pace playback (~1 Hz) and derive speed.

Usage:
    python qa/fixtures/gpx_to_xcode.py qa/fixtures/gpx/trakiya-01-east_160.gpx
    python qa/fixtures/gpx_to_xcode.py <in.gpx> <out.gpx>

With one argument the output lands in qa/fixtures/gpx-xcode/<same-name>.gpx so
the harness's track-form fixtures stay untouched.
"""
import re
import sys
from pathlib import Path

TRKPT_RE = re.compile(
    r'<trkpt\s+lat="(?P<lat>[^"]+)"\s+lon="(?P<lon>[^"]+)"\s*>'
    r'(?:\s*<time>(?P<time>[^<]+)</time>\s*)?'
    r'</trkpt>',
    re.IGNORECASE,
)


def convert(text: str) -> str:
    points = list(TRKPT_RE.finditer(text))
    if not points:
        raise SystemExit("no <trkpt> elements found — is this a track-form GPX?")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="srednabg-gpx-to-xcode" '
        'xmlns="http://www.topografix.com/GPX/1/1">',
    ]
    for m in points:
        lat, lon, time = m.group("lat"), m.group("lon"), m.group("time")
        if time:
            lines.append(f'  <wpt lat="{lat}" lon="{lon}"><time>{time}</time></wpt>')
        else:
            lines.append(f'  <wpt lat="{lat}" lon="{lon}"></wpt>')
    lines.append("</gpx>")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    if not 2 <= len(argv) <= 3:
        raise SystemExit(__doc__)
    src = Path(argv[1])
    if len(argv) == 3:
        dst = Path(argv[2])
    else:
        dst = src.parent.parent / "gpx-xcode" / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    out = convert(src.read_text(encoding="utf-8"))
    dst.write_text(out, encoding="utf-8")
    n = out.count("<wpt ")
    print(f"wrote {n} waypoints -> {dst}")


if __name__ == "__main__":
    main(sys.argv)
