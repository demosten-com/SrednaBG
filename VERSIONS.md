# Published versions

Which SrednaBG releases actually reached users, and which is current.

**This file is load-bearing, not a changelog.** The scraper refuses to publish
zone data that any listed version cannot parse (`scrapers/contracts/`), because
a client-side fix can never reach an install that already exists. Getting a row
wrong here either drops protection for real users or blocks publishing to
protect nobody. `scrapers/contracts/manifest.json` is the machine-readable twin,
and `test_client_contract.py` fails if the two disagree.

A git tag is **not** a release. Only rows in the first table below were ever
shipped to anyone.

## Currently published

| Version | Status | Tag | Commit | versionCode | Released | Play | App Store | F-Droid | GitHub |
|---|---|---|---|---|---|---|---|---|---|
| 1.1.0 | `live` | `v1.1.0` | `fbdaa36` | 10100 | 2026-06-29 | ✅ | ✅ | ✅ | ✅ |
| 1.0.4 | `published` | `v1.0.4` | `dba1ef7` | 10004 | 2026-06-02 | superseded | superseded | superseded | superseded |

**Latest published: 1.1.0** — live on every channel (Play, App Store, F-Droid,
GitHub Releases).

Status vocabulary, shared with `contracts/manifest.json`:

- **`live`** — what a new user installs today.
- **`published`** — superseded, but still installed on real devices, so still
  protected. Enforced exactly as strictly as `live`: a release date cannot
  decide that someone's phone stopped mattering.
- A version is only exempted by explicitly marking it retired in
  `contracts/manifest.json`. On the day 2.0.0 goes live, 1.1.0 is still the
  entire installed base.

## Tagged but never published

These exist in git and shipped to **no one**. They impose no obligation on the
zone data, and listing them in the contract manifest would block publishing to
protect nobody.

| Tag | Commit | Date | Note |
|---|---|---|---|
| `v1.0.3` | `e169858` | 2026-05-31 | never released |
| `v1.0.2` | `afe2566` | 2026-05-25 | never released |
| `v1.0.1` | `65e029b` | 2026-05-20 | never released |

## When a new version is published

Tell whoever maintains this (or Claude) that a version went live, and these
steps follow together — they are one change, not four:

1. **This file** — add the new row as `live`, demote the previous `live` row to
   `published`, update "Latest published".
2. **`scrapers/contracts/manifest.json`** — same two edits, same vocabulary.
   The consistency test fails until both agree.
3. **Wire contract** — if the release changed the zone decode surface
   (`Zone` / `SpeedLimits` / `ZoneEndpoint` / `ZonesResponse` fields), add a new
   `contracts/wire-vN.json` and point the new version at it; otherwise reuse the
   existing one. `check_drift.py` will have already told you, since it fails the
   build when those models move.
4. **Verify against the real client** —
   `bash scrapers/contracts/verify_against_clients.sh`, which decodes every
   fixture using the models as released at each published tag.

Deliberately *not* recorded here: release notes, store metadata, build
instructions. Those live in `fastlane/`, `web/fdroid/` and the per-platform
`CLAUDE.md` files. This file answers exactly one question — whose phone are we
still obliged to keep working?
