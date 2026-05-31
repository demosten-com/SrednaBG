#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — web / fdroid

# Stages the SrednaBG F-Droid build recipe into a local clone of fdroiddata,
# ready for `git add && git commit` against the user's MR branch.
#
# Listing copy + graphics (name/summary/description, icon, featureGraphic,
# screenshots) are NOT staged here: they live in the app's own repo under
# `fastlane/metadata/android/<locale>/` (see gen-fastlane-metadata.sh) and
# F-Droid imports them from the built tag at `fdroid update`. fdroiddata only
# needs the build recipe, so this script copies a single file:
#
#   web/fdroid/metadata.yml -> <target>/metadata/com.demosten.srednabg.yml
#
# Usage:
#   bash web/fdroid/scripts/stage-fdroiddata.sh <path-to-fdroiddata-clone>
#
# Example:
#   bash web/fdroid/scripts/stage-fdroiddata.sh ~/dev/fdroiddata
#
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <path-to-fdroiddata-clone>" >&2
    exit 64
fi

TARGET="$1"
if [[ ! -d "$TARGET/metadata" ]]; then
    echo "error: $TARGET does not look like an fdroiddata clone (missing metadata/)" >&2
    exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
SRC="$REPO_ROOT/web/fdroid"
APP_ID="com.demosten.srednabg"
DEST_YAML="$TARGET/metadata/${APP_ID}.yml"
DEST_DIR="$TARGET/metadata/${APP_ID}"

echo "==> Copying metadata.yml -> metadata/${APP_ID}.yml"
cp "$SRC/metadata.yml" "$DEST_YAML"

LEGACY_NOTE=""
if [[ -d "$DEST_DIR" ]]; then
    LEGACY_NOTE="
  NOTE: a metadata/${APP_ID}/ directory exists in the clone. Listing copy now
  lives in the app repo's fastlane/ tree, so remove the stale locale dir:
    git -C \"$TARGET\" rm -r \"metadata/${APP_ID}\"
"
fi

cat <<EOF

================================================================================
  Staged: $DEST_YAML
$LEGACY_NOTE
  Next steps:
    cd "$TARGET"
    git checkout -b $APP_ID    # or switch to your existing branch
    git add "metadata/${APP_ID}.yml"
    git status
    git commit -m "New app: $APP_ID (SrednaBG)"
    git push origin $APP_ID
    # Then open / update the MR against master on gitlab.com/fdroid/fdroiddata
================================================================================
EOF
