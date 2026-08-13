# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""The publish gate that keeps /api/zones consumable by the shipped 1.x apps.

The fixture-driven cases are the load-bearing ones: they assert that each rule
in `contracts/wire-v1.json` actually rejects a payload violating it, and that a
compliant payload passes. A gate nobody has watched reject anything is a gate
you are trusting on faith — and the fleet has no second line of defence.
"""

import json
from pathlib import Path

import pytest

from contracts.check_drift import compute_fingerprints, drift
from src.client_contract import (
    ContractError,
    contract_violations,
    load_manifest,
)

FIXTURES = Path(__file__).parent.parent / "contracts" / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class TestManifest:
    def test_only_published_versions_are_enforced(self):
        """v1.0.1-v1.0.3 are tags that never reached a store, so they impose no
        obligation. Listing them would block publishes to protect nobody."""
        versions = {c["version"] for c in load_manifest()}
        assert versions == {"1.0.4", "1.1.0"}

    def test_every_client_resolves_a_contract(self):
        for client in load_manifest():
            assert client["_contract"]["name"], client["version"]

    def test_a_missing_manifest_fails_loudly(self, tmp_path):
        """Never 'no contracts loaded, therefore no violations'."""
        with pytest.raises(ContractError):
            load_manifest(tmp_path)


class TestCompliantPayload:
    def test_a_good_payload_has_no_violations(self):
        assert contract_violations(_fixture("compliant")) == []

    def test_the_shipped_data_satisfies_every_published_client(self):
        data = json.loads(
            (Path(__file__).parent.parent / "data" / "zones.json").read_text("utf-8")
        )
        assert contract_violations(data) == []


class TestEveryRuleIsProved:
    """One case per constraint in wire-v1.json. If you add a rule, add a case —
    an unproved rule is indistinguishable from a typo."""

    @pytest.mark.parametrize(
        "fixture,expected",
        [
            ("violation-missing-limits", "speed_limits is missing required key"),
            ("violation-empty-centerline", "centerline has 0 point(s)"),
            ("violation-short-point", "fewer than 2 coordinates"),
            ("violation-zero-endpoint", "(0, 0) placeholder"),
            ("violation-zero-distance", "distance_m is 0"),
            ("violation-zero-limit", "speed_limits.truck is 0"),
            ("violation-missing-key", "missing required key 'description'"),
        ],
    )
    def test_violation_is_rejected(self, fixture, expected):
        errors = contract_violations(_fixture(fixture))
        assert errors, f"{fixture} was accepted — the rule is not enforced"
        assert any(expected in e for e in errors), (
            f"{fixture} was rejected, but for the wrong reason: {errors}"
        )

    def test_every_violation_names_the_clients_it_breaks(self):
        errors = contract_violations(_fixture("violation-missing-limits"))
        assert all("1.0.4" in e and "1.1.0" in e for e in errors), errors

    def test_every_constraint_in_the_contract_has_a_fixture(self):
        """Tripwire: a rule added without a fixture proving it fails here."""
        contract = load_manifest()[0]["_contract"]
        rule_ids = {c["id"] for c in contract["constraints"]}
        covered = {
            "centerline-min-points",
            "centerline-point-arity",
            "endpoints-not-null-island",
            "distance-positive",
            "limits-positive",
        }
        assert rule_ids == covered, (
            "contracts/wire-v1.json changed — add a fixture under "
            "contracts/fixtures/ and a case above for each new rule"
        )


class TestUnknownRuleIsNotSilentlySkipped:
    def test_an_unrecognized_rule_is_reported(self, tmp_path):
        contract = {
            "name": "bogus",
            "response": {"required": {"version": "string", "hash": "string",
                                      "zones": "array"}},
            "zone": {"required": {}, "optional": {}},
            "endpoint": {"required": {}, "optional": {}},
            "speed_limits": {"required": {}, "optional": {}},
            "constraints": [{"id": "future-rule", "rule": "not_implemented_yet"}],
        }
        (tmp_path / "c.json").write_text(json.dumps(contract), encoding="utf-8")
        (tmp_path / "manifest.json").write_text(
            json.dumps({
                "feeds": [{"version": 1, "status": "active"}],
                "clients": [{"version": "9.9.9", "status": "live", "feed": 1,
                             "contract": "c.json"}],
            }),
            encoding="utf-8",
        )
        errors = contract_violations(_fixture("compliant"), contracts_dir=tmp_path)
        assert any("unknown constraint rule" in e for e in errors), errors


class TestContractTracksTheClients:
    """The contract is a transcription of the released Kotlin/Swift models, and
    transcriptions rot silently. `check_drift` fingerprints the decode surface
    those models expose so a field added, removed, renamed or re-nullabled fails
    here — before the publish gate starts approving payloads the clients reject.
    """

    def test_no_drift_against_the_current_client_models(self):
        problems = drift()
        assert problems == [], (
            "the client decode surface changed — review contracts/wire-v1.json "
            "and contracts/fixtures/, then re-record with "
            "`python scrapers/contracts/check_drift.py --update`:\n  "
            + "\n  ".join(problems)
        )

    def test_the_extractor_actually_extracts(self):
        """Guard the guard: an extractor matching nothing would fingerprint every
        file identically and detect no drift at all."""
        contract = json.loads(
            (Path(__file__).parent.parent / "contracts" / "wire-v1.json")
            .read_text(encoding="utf-8")
        )
        prints = compute_fingerprints(contract)
        assert prints, "no decode-surface files were fingerprinted"
        assert all(
            v not in ("MISSING", "NO-FIELDS-EXTRACTED") for v in prints.values()
        ), prints
        assert len(set(prints.values())) == len(prints), (
            f"fingerprints collide, so drift would be invisible: {prints}"
        )


class TestVersionsDocMatchesTheManifest:
    """`VERSIONS.md` and `contracts/manifest.json` record the same fact — which
    releases are installed on real phones — for humans and for the publish gate.

    Two hand-maintained lists of the same thing drift; that is precisely the
    failure mode the contract exists to prevent, so it must not be reintroduced
    by the contract's own bookkeeping. Whichever one you edit, this fails until
    you edit the other.
    """

    VERSIONS_MD = Path(__file__).parent.parent.parent / "VERSIONS.md"

    def _published_from_markdown(self) -> dict[str, dict[str, str]]:
        """Parse the 'Currently published' table: version -> {column: value}.

        Columns are read by header name rather than position, so inserting one
        (as `Feed` was) cannot silently start comparing the wrong cell.
        """
        rows: dict[str, dict[str, str]] = {}
        header: list[str] = []
        in_table = False
        for line in self.VERSIONS_MD.read_text(encoding="utf-8").splitlines():
            if line.startswith("## Currently published"):
                in_table = True
                continue
            if in_table and line.startswith("## "):
                break
            if not in_table or not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not header:
                header = cells
                continue
            if set(cells[0]) <= {"-", ":"}:
                continue
            rows[cells[0]] = {
                key: value.strip("`") for key, value in zip(header, cells, strict=False)
            }
        return rows

    def test_the_same_versions_are_listed(self):
        documented = {v: row["Status"] for v, row in self._published_from_markdown().items()}
        enforced = {c["version"]: c["status"] for c in load_manifest()}
        assert documented == enforced, (
            "VERSIONS.md and contracts/manifest.json disagree about which "
            f"releases are in the field.\n  VERSIONS.md: {documented}\n"
            f"  manifest.json: {enforced}"
        )

    def test_the_same_feeds_are_listed(self):
        """The Feed column decides what a payload change can break, so it has
        the same drift problem as the status column and the same cure."""
        documented = {v: row["Feed"] for v, row in self._published_from_markdown().items()}
        enforced = {c["version"]: str(c["feed"]) for c in load_manifest()}
        assert documented == enforced, (
            "VERSIONS.md and contracts/manifest.json disagree about which data "
            f"feed each release fetches.\n  VERSIONS.md: {documented}\n"
            f"  manifest.json: {enforced}"
        )

    def test_exactly_one_version_is_live(self):
        live = [
            v for v, row in self._published_from_markdown().items()
            if row["Status"] == "live"
        ]
        assert len(live) == 1, f"expected one `live` version, found {live}"

    def test_the_parser_is_not_vacuous(self):
        """A table parser that silently matches nothing would make the
        comparison above pass against an empty document."""
        assert len(self._published_from_markdown()) >= 2

    def test_unpublished_tags_are_not_enforced(self):
        """v1.0.1-v1.0.3 shipped to nobody. Enforcing them would block publishes
        to protect no one — the inverse of this gate's purpose."""
        enforced = {c["version"] for c in load_manifest()}
        assert not (enforced & {"1.0.1", "1.0.2", "1.0.3"})
