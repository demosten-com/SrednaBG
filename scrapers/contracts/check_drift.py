# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Detect the contract drifting away from the clients it claims to describe.

`wire-v1.json` is a transcription of the Kotlin and Swift models listed in its
`derived_from`. Transcriptions rot silently: someone adds a non-optional field
to `Zone`, every published client starts requiring it, and the publish gate goes
on cheerfully approving payloads without it.

So the contract records a fingerprint of the **decode surface** it was written
against — just the field declarations, not the whole file — and
`tests/test_client_contract.py` recomputes it. Doc comments, helper methods and
formatting do not move the fingerprint; adding, removing, renaming or
re-nullabling a field does.

When it fires, the fix is to review the contract (and its fixtures) against the
changed model, then re-record with:

    python scrapers/contracts/check_drift.py --update
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CONTRACTS = Path(__file__).resolve().parent

# Kotlin `val name: Type = default,` inside a data class body.
_KT_FIELD = re.compile(r"^\s*val\s+(\w+)\s*:\s*([^=,]+?)\s*(?:=.*)?,?\s*$")
# Swift `public let name: Type`.
_SW_FIELD = re.compile(r"^\s*public let\s+(\w+)\s*:\s*(.+?)\s*$")

# Only these declarations touch the wire. Anything else in the file (engine
# types, helpers, docs) is deliberately out of scope.
_KT_TYPES = ("ZoneEndpoint", "SpeedLimits", "Zone", "ZonesResponse", "VersionResponse")
_SW_TYPES = ("ZoneEndpoint", "SpeedLimits", "Zone", "ZonesResponse", "VersionResponse")


def _kotlin_surface(text: str) -> list[str]:
    out: list[str] = []
    current: str | None = None
    for line in text.splitlines():
        m = re.match(r"^data class (\w+)\s*\(", line)
        if m:
            current = m.group(1) if m.group(1) in _KT_TYPES else None
            continue
        if current and line.startswith(")"):
            current = None
            continue
        if current:
            f = _KT_FIELD.match(line)
            if f:
                out.append(f"{current}.{f.group(1)}:{f.group(2).strip()}")
    return out


def _swift_surface(text: str) -> list[str]:
    out: list[str] = []
    current: str | None = None
    for line in text.splitlines():
        m = re.match(r"^public struct (\w+)\s*[:{]", line)
        if m:
            current = m.group(1) if m.group(1) in _SW_TYPES else None
            continue
        if current and line.startswith("}"):
            current = None
            continue
        if current:
            f = _SW_FIELD.match(line)
            if f:
                out.append(f"{current}.{f.group(1)}:{f.group(2).strip()}")
    return out


def surface_for(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return _kotlin_surface(text) if path.suffix == ".kt" else _swift_surface(text)


def compute_fingerprints(contract: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for paths in contract["derived_from"]["decode_surface"].values():
        for rel in paths:
            path = REPO / rel
            if not path.exists():
                out[rel] = "MISSING"
                continue
            fields = surface_for(path)
            if not fields:
                # An extractor that silently matches nothing would pin every
                # file to the same empty hash and detect no drift at all.
                out[rel] = "NO-FIELDS-EXTRACTED"
                continue
            blob = "\n".join(fields).encode("utf-8")
            out[rel] = hashlib.sha256(blob).hexdigest()[:16]
    return out


def drift(contract_name: str = "wire-v1.json") -> list[str]:
    """Files whose decode surface no longer matches the recorded fingerprint."""
    contract = json.loads((CONTRACTS / contract_name).read_text(encoding="utf-8"))
    recorded = contract.get("surface_fingerprint", {})
    current = compute_fingerprints(contract)

    problems: list[str] = []
    for rel, digest in current.items():
        if digest in ("MISSING", "NO-FIELDS-EXTRACTED"):
            problems.append(f"{rel}: {digest} — the extractor needs updating")
        elif rel not in recorded:
            problems.append(f"{rel}: no fingerprint recorded")
        elif recorded[rel] != digest:
            problems.append(
                f"{rel}: decode surface changed ({recorded[rel]} -> {digest})"
            )
    for rel in recorded.keys() - current.keys():
        problems.append(f"{rel}: fingerprinted but no longer in derived_from")
    return problems


def main() -> int:
    name = "wire-v1.json"
    if "--update" in sys.argv:
        path = CONTRACTS / name
        contract = json.loads(path.read_text(encoding="utf-8"))
        contract["surface_fingerprint"] = compute_fingerprints(contract)
        path.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"recorded {len(contract['surface_fingerprint'])} fingerprints in {name}")
        return 0

    problems = drift(name)
    if problems:
        print("Client decode surface has drifted from the contract:")
        for p in problems:
            print(f"  - {p}")
        print(
            "\nReview contracts/wire-v1.json and contracts/fixtures/ against the "
            "changed model, then re-record:\n"
            "  python scrapers/contracts/check_drift.py --update"
        )
        return 1
    print("Contract matches the current client decode surface.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
