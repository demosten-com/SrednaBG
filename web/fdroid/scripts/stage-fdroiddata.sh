#!/usr/bin/env bash
#
# Copies the F-Droid metadata for SrednaBG into a local clone of fdroiddata,
# ready for `git add && git commit` against the user's MR branch.
#
# Usage:
#   bash web/fdroid/scripts/stage-fdroiddata.sh <path-to-fdroiddata-clone>
#
# Example:
#   bash web/fdroid/scripts/stage-fdroiddata.sh ~/dev/fdroiddata
#
# Mappings (source -> destination):
#
#   web/fdroid/metadata.yml
#     -> <target>/metadata/com.demosten.srednabg.yml
#
#   web/fdroid/{en-US,bg}/{title,short_description,full_description}.txt
#   web/fdroid/{en-US,bg}/changelogs/*.txt
#     -> <target>/metadata/com.demosten.srednabg/<locale>/...
#
#   test-data/design/SrednaBG complete files 2/play-store/icon-512.png
#     -> <target>/metadata/com.demosten.srednabg/<locale>/icon.png
#
#   test-data/design/SrednaBG complete files 2/temp/feature_graphic_dark_gradient_95.png
#     -> <target>/metadata/com.demosten.srednabg/<locale>/featureGraphic.png
#
#   web/screenshots/android/framed/<6 chosen shots per locale>
#     -> <target>/metadata/com.demosten.srednabg/<locale>/phoneScreenshots/
#
# F-Droid's tooling does not follow symlinks — files are copied, not linked.
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

ICON_SRC="$REPO_ROOT/test-data/design/SrednaBG complete files 2/play-store/icon-512.png"
FEATURE_SRC="$REPO_ROOT/test-data/design/SrednaBG complete files 2/temp/feature_graphic_dark_gradient_95.png"
FRAMED_DIR="$REPO_ROOT/web/screenshots/android/framed"

for f in "$ICON_SRC" "$FEATURE_SRC"; do
    if [[ ! -f "$f" ]]; then
        echo "error: missing source asset: $f" >&2
        exit 1
    fi
done

EN_SHOTS=(01-light-en.png 02-light-en.png 04-dark-en.png 05-dark-en.png 07-light-en.png 08-dark-en.png)
BG_SHOTS=(01-light-bg.png 02-light-bg.png 04-dark-bg.png 05-dark-bg.png 07-light-bg.png 08-dark-bg.png)

echo "==> Copying metadata.yml"
cp "$SRC/metadata.yml" "$DEST_YAML"

stage_locale() {
    local locale="$1"
    shift
    local -a shots=("$@")
    local locale_dir="$DEST_DIR/$locale"
    local shots_dir="$locale_dir/phoneScreenshots"

    echo "==> Staging locale: $locale"
    mkdir -p "$locale_dir/changelogs" "$shots_dir"

    cp "$SRC/$locale/title.txt" "$locale_dir/title.txt"
    cp "$SRC/$locale/short_description.txt" "$locale_dir/short_description.txt"
    cp "$SRC/$locale/full_description.txt" "$locale_dir/full_description.txt"

    for f in "$SRC/$locale/changelogs"/*.txt; do
        cp "$f" "$locale_dir/changelogs/"
    done

    cp "$ICON_SRC" "$locale_dir/icon.png"
    cp "$FEATURE_SRC" "$locale_dir/featureGraphic.png"

    local i=1
    for shot in "${shots[@]}"; do
        cp "$FRAMED_DIR/$shot" "$shots_dir/$(printf '%02d' "$i").png"
        i=$((i + 1))
    done
}

stage_locale en-US "${EN_SHOTS[@]}"
stage_locale bg    "${BG_SHOTS[@]}"

cat <<EOF

================================================================================
  Staged at: $DEST_DIR
  YAML at:   $DEST_YAML

  Next steps:
    cd "$TARGET"
    git checkout -b $APP_ID
    git add "metadata/${APP_ID}.yml" "metadata/${APP_ID}/"
    git status
    git commit -m "New app: $APP_ID (SrednaBG)"
    git push origin $APP_ID
    # Then open MR against master on gitlab.com/fdroid/fdroiddata
================================================================================
EOF
