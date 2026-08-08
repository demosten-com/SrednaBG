#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers
#
# Proves `contracts/wire-v1.json` describes the REAL clients, not our belief
# about them, by decoding every fixture with the models as released.
#
# The Python gate in `src/client_contract.py` is a transcription of somebody
# else's parser. A transcription that nothing checks is a guess, and the fleet
# has no second line of defence — so for each published version this script
# checks the tag out into a git worktree, compiles a decoder from THAT tag's
# `Models.swift` + `ApiTypes.swift`, and asserts:
#
#   contracts/fixtures/compliant.json            -> decodes
#   contracts/fixtures/violation-*.json          -> fails, OR is tolerated
#
# A violation the released client tolerates is not a lie, but it does mean the
# contract is stricter than necessary — the script prints those as TOLERATED so
# a human can decide whether to relax the rule. A *compliant* fixture that fails
# to decode is a hard error: the contract is too loose and the gate would wave
# through data that bricks the fleet.
#
# Swift only: an iOS decode failure loses the entire catalog, which is the
# outage that motivated this. Android's Gson tolerates nearly anything at parse
# time — its real exposure is MapLibre's render rule, which needs a device and
# is covered by `qa/scenarios/sync/zones_all_usable.py`.
#
# Usage:  bash scrapers/contracts/verify_against_clients.sh [tag ...]
#         (defaults to every published version in manifest.json)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
WORKTREES="$(mktemp -d)"
trap 'cd "$REPO" && for w in "$WORKTREES"/*; do [ -d "$w" ] && git worktree remove --force "$w" 2>/dev/null || true; done; rm -rf "$WORKTREES"' EXIT

if ! command -v swift >/dev/null 2>&1; then
  echo "swift toolchain not found — run this on macOS with Xcode installed" >&2
  exit 2
fi

if [ $# -gt 0 ]; then
  TAGS=("$@")
else
  # No `mapfile` on macOS's bash 3.2 — read the list the portable way.
  TAGS=()
  while IFS= read -r line; do
    [ -n "$line" ] && TAGS+=("$line")
  done < <(python3 -c "
import json, pathlib
m = json.loads(pathlib.Path('$HERE/manifest.json').read_text())
for c in m['clients']:
    print('v' + c['version'])
")
fi

FAILURES=0

for TAG in "${TAGS[@]}"; do
  echo "=============================================================="
  echo "Verifying contract against released client $TAG"
  echo "=============================================================="
  WT="$WORKTREES/$TAG"
  git -C "$REPO" worktree add --detach --quiet "$WT" "$TAG"

  MODELS="$WT/ios/Packages/SrednaBGCore/Sources/SrednaBGCore/Models.swift"
  APITYPES="$WT/ios/Packages/SrednaBGData/Sources/SrednaBGData/ApiTypes.swift"
  if [ ! -f "$MODELS" ] || [ ! -f "$APITYPES" ]; then
    echo "  !! $TAG has no Models.swift/ApiTypes.swift at the expected path" >&2
    FAILURES=$((FAILURES + 1))
    continue
  fi

  DRIVER="$WT/contract_check.swift"
  # Only the wire types are needed; strip anything referring to the engine.
  {
    echo "import Foundation"
    sed -n '/public struct ZoneEndpoint/,/^}/p;/public struct SpeedLimits/,/^}/p;/public struct Zone:/,/^}/p' "$MODELS"
    sed -n '/public struct ZonesResponse/,/^}/p' "$APITYPES"
    cat <<'SWIFT'

// Exit 0 = decoded, 1 = decode failed. The caller decides which is expected.
let path = CommandLine.arguments[1]
let data = try! Data(contentsOf: URL(fileURLWithPath: path))
let decoder = JSONDecoder()
decoder.keyDecodingStrategy = .convertFromSnakeCase
do {
    let r = try decoder.decode(ZonesResponse.self, from: data)
    // Mirror the unguarded subscripting the released map layer does, so a
    // malformed centerline point surfaces here rather than as a device crash.
    for z in r.zones where z.centerline.count >= 2 {
        for p in z.centerline where p.count < 2 { throw NSError(
            domain: "contract", code: 2,
            userInfo: [NSLocalizedDescriptionKey: "centerline point with \(p.count) coords in \(z.id)"]) }
    }
    print("decoded \(r.zones.count) zones")
    exit(0)
} catch {
    print("decode failed: \(error)")
    exit(1)
}
SWIFT
  } > "$DRIVER"

  for FIXTURE in "$HERE"/fixtures/*.json; do
    NAME="$(basename "$FIXTURE" .json)"
    [ "$NAME" = "expectations" ] && continue

    EXPECTED="$(python3 -c "
import json, pathlib, sys
e = json.loads(pathlib.Path('$HERE/fixtures/expectations.json').read_text())
entry = e.get('$NAME')
print(entry['swift_decode'] if entry else 'UNDECLARED')
")"

    if swift "$DRIVER" "$FIXTURE" >/dev/null 2>&1; then ACTUAL="succeeds"; else ACTUAL="fails"; fi
    # 'tolerated' means "decodes, and the rule exists for a reason the Swift
    # decoder cannot see" — same observable outcome as 'succeeds'.
    [ "$EXPECTED" = "tolerated" ] && EXPECTED_RC="succeeds" || EXPECTED_RC="$EXPECTED"

    if [ "$EXPECTED" = "UNDECLARED" ]; then
      echo "  MISSING    $NAME has no entry in fixtures/expectations.json"
      FAILURES=$((FAILURES + 1))
    elif [ "$ACTUAL" = "$EXPECTED_RC" ]; then
      printf "  OK         %-28s %s on %s (as declared)\n" "$NAME" "$ACTUAL" "$TAG"
    else
      echo "  MISMATCH   $NAME: expected to $EXPECTED_RC on $TAG, actually $ACTUAL"
      echo "             The contract and the released client disagree. Either the"
      echo "             rule is wrong, or expectations.json is stale — do not"
      echo "             'fix' this by editing the expectation without checking."
      swift "$DRIVER" "$FIXTURE" 2>&1 | sed 's/^/               /'
      FAILURES=$((FAILURES + 1))
    fi
  done
done

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "FAILED: $FAILURES contract/client mismatch(es)" >&2
  exit 1
fi
echo "Contract is consistent with every published client checked."
