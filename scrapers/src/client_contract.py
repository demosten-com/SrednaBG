# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Publish-time gate: never serve data a published client cannot consume.

The apps in the stores cannot be fixed retroactively. A client-side tolerance
shipped today reaches only future installs, so **the wire format is the sole
protection for the existing fleet** — which makes this module, not the client
code, the thing that keeps it alive.

The rules live in `contracts/*.json` rather than in Python because they are a
transcription of somebody else's parser (the released Kotlin and Swift models)
and must be checkable against it. `contracts/README.md` describes the fixture
corpus that proves the transcription is faithful; the short version is that
every constraint here has a payload which violates exactly that rule, and a
test which decodes that payload with the *released* client models to confirm it
really does break them. A rule nothing can demonstrate is a guess.

Enforcement runs on Namecheap shared hosting — Python 3.11, no JVM, no Swift —
so this module is stdlib-only and does no I/O beyond reading the contracts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONTRACTS_DIR = Path(__file__).parent.parent / "contracts"

# Every published client is enforced at ERROR: a fix that ships in an app cannot
# reach installs that already exist, so "old enough to break" is not a thing a
# release date can decide. A version may be retired to WARN by adding an explicit
# `severity` to its manifest entry — deliberately, not as a side effect of
# shipping something newer. See contracts/manifest.json.
SEVERITY_FOR_STATUS = {"live": "error", "published": "error"}

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


class ContractError(Exception):
    """The contract files themselves are missing or malformed."""


def load_manifest(contracts_dir: Path | None = None) -> list[dict[str, Any]]:
    """Published clients whose contracts must hold, newest first."""
    root = contracts_dir or CONTRACTS_DIR
    path = root / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # Never fall through to "no contracts, therefore no violations" — that
        # would silently disable the fleet's only protection.
        raise ContractError(f"cannot read {path}: {exc}") from exc

    clients = manifest.get("clients")
    if not clients:
        raise ContractError(f"{path} lists no clients — nothing would be enforced")

    for client in clients:
        contract_path = root / client["contract"]
        try:
            client["_contract"] = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ContractError(f"cannot read {contract_path}: {exc}") from exc
    return clients


def contract_violations(
    payload: dict[str, Any], contracts_dir: Path | None = None
) -> list[str]:
    """Reasons ``payload`` must not be published, or [] if it may be.

    ``payload`` is the serialized `/api/zones` body — the wire form, **not** the
    `ZoneDatabase` model, because the wire is what clients see and
    `exclude_none=True` means a null field is absent rather than null.

    Distinct clients sharing one contract are checked once and reported against
    every version that shares it, so the message names who breaks.
    """
    clients = load_manifest(contracts_dir)
    errors: list[str] = []
    seen: dict[str, list[str]] = {}

    for client in clients:
        if SEVERITY_FOR_STATUS.get(client.get("status"), "error") != "error":
            continue
        seen.setdefault(client["contract"], []).append(client["version"])

    for contract_file, versions in seen.items():
        contract = next(
            c["_contract"] for c in clients if c["contract"] == contract_file
        )
        who = ", ".join(sorted(versions))
        for problem in _check(payload, contract):
            errors.append(f"breaks published client(s) {who}: {problem}")
    return errors


def _check(payload: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    out: list[str] = []

    for key, kind in contract["response"]["required"].items():
        if key not in payload:
            out.append(f"response is missing required key '{key}'")
        elif not _TYPE_CHECKS[kind](payload[key]):
            out.append(f"response key '{key}' must be {kind}")
    if not isinstance(payload.get("zones"), list):
        return out  # nothing further is checkable

    for index, zone in enumerate(payload["zones"]):
        zid = zone.get("id") if isinstance(zone, dict) else None
        label = f"zone {zid!r}" if zid else f"zones[{index}]"
        if not isinstance(zone, dict):
            out.append(f"{label} is not an object")
            continue
        out.extend(_check_zone(zone, label, contract))
    return out


def _check_zone(zone: dict, label: str, contract: dict) -> list[str]:
    out: list[str] = []

    for key, kind in contract["zone"]["required"].items():
        if key not in zone:
            out.append(f"{label} is missing required key '{key}'")
        elif not _TYPE_CHECKS[kind](zone[key]):
            out.append(f"{label} key '{key}' must be {kind}")

    for end in ("start", "end"):
        endpoint = zone.get(end)
        if isinstance(endpoint, dict):
            for key, kind in contract["endpoint"]["required"].items():
                if key not in endpoint:
                    out.append(f"{label} {end} is missing required key '{key}'")
                elif not _TYPE_CHECKS[kind](endpoint[key]):
                    out.append(f"{label} {end} key '{key}' must be {kind}")

    limits = zone.get("speed_limits")
    if isinstance(limits, dict):
        for key, kind in contract["speed_limits"]["required"].items():
            if key not in limits:
                out.append(
                    f"{label} speed_limits is missing required key '{key}' — the "
                    f"key is omitted on the wire, which fails the whole "
                    f"/api/zones decode on iOS 1.x"
                )
            elif not _TYPE_CHECKS[kind](limits[key]):
                out.append(f"{label} speed_limits key '{key}' must be {kind}")

    out.extend(_check_constraints(zone, label, contract))
    return out


def _check_constraints(zone: dict, label: str, contract: dict) -> list[str]:
    out: list[str] = []
    for rule in contract.get("constraints", []):
        kind = rule["rule"]
        breaks = "/".join(rule.get("breaks", []))
        suffix = f" [{rule['id']}, breaks {breaks}]"

        if kind == "centerline_min_points":
            cl = zone.get("centerline")
            if isinstance(cl, list) and len(cl) < rule["value"]:
                out.append(
                    f"{label} centerline has {len(cl)} point(s), needs "
                    f"{rule['value']}{suffix}"
                )
        elif kind == "centerline_point_arity":
            cl = zone.get("centerline")
            if isinstance(cl, list):
                bad = [
                    i
                    for i, p in enumerate(cl)
                    if not isinstance(p, list) or len(p) < rule["value"]
                ]
                if bad:
                    out.append(
                        f"{label} centerline point(s) {bad[:3]} have fewer than "
                        f"{rule['value']} coordinates{suffix}"
                    )
        elif kind == "endpoints_non_zero":
            for end in ("start", "end"):
                ep = zone.get(end)
                if isinstance(ep, dict) and ep.get("lat") == 0 and ep.get("lng") == 0:
                    out.append(
                        f"{label} {end} is the (0, 0) placeholder — it likely "
                        f"failed to merge with a coordinate-bearing source; check "
                        f"roads.ROAD_AXIS / ROAD_DIRECTIONS covers "
                        f"{zone.get('road')!r}{suffix}"
                    )
        elif kind == "positive_integer":
            value = zone.get(rule["field"])
            if isinstance(value, int) and value <= 0:
                out.append(f"{label} {rule['field']} is {value}{suffix}")
        elif kind == "positive_limits":
            limits = zone.get("speed_limits") or {}
            for field in rule["fields"]:
                value = limits.get(field)
                if isinstance(value, int) and value <= 0:
                    out.append(
                        f"{label} speed_limits.{field} is {value}{suffix}"
                    )
        else:
            # An unknown rule must never be silently skipped: the contract would
            # look enforced while doing nothing.
            out.append(
                f"contract error: unknown constraint rule {kind!r} "
                f"({rule.get('id')}) — cannot verify {label}"
            )
    return out
