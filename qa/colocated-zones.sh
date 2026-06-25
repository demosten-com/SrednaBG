#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# colocated-zones.sh — thin wrapper around colocated_zones.py.
#
# Drives a continuous route through a co-located zone pair (one camera ends zone
# A and begins zone B) and asserts, from the app's TTS log, that ENTERING the
# second zone is announced — the back-to-back case where the engine steps
# InZone(A) -> Exiting(A) -> InZone(B) with no Outside between them. Regression
# for the AudioAlertManager `Exiting->InZone` announcement fix.
#
#   qa/colocated-zones.sh                               # first detected pair
#   qa/colocated-zones.sh --pair trakiya-02-east,trakiya-03-east
#   qa/colocated-zones.sh --all                         # every co-located pair
#   qa/colocated-zones.sh --keep-online                 # device's current data
#
# Requires the DEBUG build installed. Exit code 0 = all pairs passed.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
bash "$REPO_ROOT/scripts/setup-python.sh" --check || exit 1
exec "$REPO_ROOT/.venv/bin/python" "$SCRIPT_DIR/colocated_zones.py" "$@"
