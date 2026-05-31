#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — backend / scripts

"""Compute a deterministic content hash for the offline map bundle.

The result becomes ``map_hash`` in the bundle's ``version.json`` and gates client
re-downloads, so it MUST be stable across rebuilds whenever the actual map
*content* is unchanged. Hashing raw file bytes fails that: Planetiler stamps
build timestamps into the mbtiles ``metadata`` table, and SQLite page layout /
gzip mtime vary run-to-run. So we hash canonical content instead:

  - the static style + glyph files, by bytes, sorted by relative path;
  - the mbtiles tile rows, by DECOMPRESSED tile payload, ordered by z/x/y.
    The ``metadata`` table is excluded entirely (it carries the volatile
    timestamps / planetiler version).

Mirrors the repo convention that content hashes exclude volatile fields (the
zones ``hash`` excludes per-zone ``last_verified``). This is distinct from the
per-release zip checksum in web/fdroid/scripts/publish-map-bundle.sh, which is an
integrity pin of the exact download and legitimately differs every build.

Prints ``sha256:<hex>``.
"""
from __future__ import annotations

import gzip
import hashlib
import sqlite3
import sys
from pathlib import Path

MBTILES_NAME = "bulgaria.mbtiles"
STATIC_TOP = ("style-light.json", "style-dark.json")


def _decompressed(blob: bytes) -> bytes:
    """mbtiles MVT payloads are gzip-compressed; decompress so a varying gzip
    mtime/level can't perturb the hash. Fall back to raw for anything not
    gzip-framed."""
    if blob[:2] == b"\x1f\x8b":
        return gzip.decompress(blob)
    return blob


def compute(bundle_dir: Path) -> str:
    h = hashlib.sha256()

    # 1) Static files: the two style JSONs + every glyph PBF, sorted by
    #    relative path so ordering is stable across filesystems.
    static = [bundle_dir / name for name in STATIC_TOP]
    static = [p for p in static if p.is_file()]
    fonts_dir = bundle_dir / "fonts"
    if fonts_dir.is_dir():
        static.extend(p for p in fonts_dir.rglob("*") if p.is_file())
    for p in sorted(static, key=lambda x: x.relative_to(bundle_dir).as_posix()):
        rel = p.relative_to(bundle_dir).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())

    # 2) Tiles: decompressed payload ordered by z/x/y. The metadata table is
    #    intentionally NOT read.
    mbtiles = bundle_dir / MBTILES_NAME
    if not mbtiles.is_file():
        raise SystemExit(f"error: {mbtiles} not found")
    conn = sqlite3.connect(f"file:{mbtiles}?mode=ro", uri=True)
    try:
        cur = conn.execute(
            "SELECT zoom_level, tile_column, tile_row, tile_data "
            "FROM tiles ORDER BY zoom_level, tile_column, tile_row"
        )
        for z, x, y, blob in cur:
            h.update(f"{z}/{x}/{y}".encode("utf-8"))
            h.update(b"\0")
            h.update(hashlib.sha256(_decompressed(bytes(blob))).digest())
    finally:
        conn.close()

    return "sha256:" + h.hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: compute-map-hash.py <bundle-dir>", file=sys.stderr)
        return 2
    print(compute(Path(argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
