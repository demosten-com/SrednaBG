#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — web / fdroid

# Generates the in-repo Fastlane metadata tree that F-Droid scans from the app's
# own source repository:
#
#   fastlane/metadata/android/<locale>/
#     title.txt
#     short_description.txt
#     full_description.txt
#     changelogs/<versionCode>.txt
#     images/icon.png
#     images/featureGraphic.png
#     images/phoneScreenshots/01..08.png
#
# `web/fdroid/` stays the single source of truth for the listing copy; this
# script derives the Fastlane tree from it plus the design assets, so the two
# F-Droid surfaces (in-repo Fastlane + the fdroiddata staging) never drift.
#
# Effective range: F-Droid imports Fastlane metadata from the *built commit's*
# tree, so this tree applies to whatever release tag contains it (v1.0.4+).
# v1.0.3 predates it and is served by the fdroiddata-embedded copy instead.
#
# Usage:
#   bash web/fdroid/scripts/gen-fastlane-metadata.sh
#
# Run from anywhere; paths resolve against the repo root.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
SRC="$REPO_ROOT/web/fdroid"
DEST_ROOT="$REPO_ROOT/fastlane/metadata/android"

# Same source assets the fdroiddata staging uses, so the two listings match.
ICON_SRC="$REPO_ROOT/design/android/512px-custom.png"
FEATURE_SRC="$REPO_ROOT/design/android/feature_graphic_white_95.png"
FRAMED_DIR="$REPO_ROOT/web/screenshots/android/framed"

# Per-locale release-note cap, enforced below. F-Droid CI flags anything longer
# as "Fastlane/Triple-T whatsNew in <locale> should be shorter than 500
# characters"; Play's "What's new" field has the identical limit.
CHANGELOG_MAX_CHARS=500

# versionCodes whose notes were already published over the cap and are left
# as-is: rewriting a shipped release's notes changes what F-Droid displays for
# a version users already have, to silence a Minor warning about the past.
# 10004/10100/20000 shipped at 587/690/1105 (en-US) chars. Do NOT extend this
# list to excuse a new release — shorten the new file instead.
CHANGELOG_GRANDFATHERED="10004 10100 20000"

for f in "$ICON_SRC" "$FEATURE_SRC"; do
    if [[ ! -f "$f" ]]; then
        echo "error: missing source asset: $f" >&2
        exit 1
    fi
done

# Listing order (becomes phoneScreenshots/01..08.png): 04-light, 05-dark,
# 07-light, 01-light, 02-light, 11-light (history list), 12-dark (history
# detail), 08-dark (settings).
EN_SHOTS=(04-light-en.png 05-dark-en.png 07-light-en.png 01-light-en.png 02-light-en.png 11-light-en.png 12-dark-en.png 08-dark-en.png)
BG_SHOTS=(04-light-bg.png 05-dark-bg.png 07-light-bg.png 01-light-bg.png 02-light-bg.png 11-light-bg.png 12-dark-bg.png 08-dark-bg.png)

# F-Droid's fdroiddata CI lints Fastlane/Triple-T whatsNew at 500 chars (the
# same cap Play enforces on "What's new"), warning once per locale on every
# longer file. Play truncates silently and F-Droid only warns, so this is the
# one place that catches an over-long release note before either store does.
# Runs BEFORE any destination dir is wiped, so a failure leaves the tree intact.
check_changelogs() {
    local locale="$1" f code n
    for f in "$SRC/$locale/changelogs"/*.txt; do
        code=$(basename "$f" .txt)
        case " $CHANGELOG_GRANDFATHERED " in
            *" $code "*) continue ;;
        esac
        n=$(wc -m < "$f" | tr -d ' ')
        if [ "$n" -gt "$CHANGELOG_MAX_CHARS" ]; then
            echo "error: $locale changelog $(basename "$f") is $n chars (max $CHANGELOG_MAX_CHARS)." >&2
            echo "       Shorten it in $SRC/$locale/changelogs/ and re-run." >&2
            exit 1
        fi
    done
}

gen_locale() {
    local locale="$1"
    shift
    local -a shots=("$@")
    local dir="$DEST_ROOT/$locale"
    local img="$dir/images"
    local shots_dir="$img/phoneScreenshots"

    check_changelogs "$locale"

    echo "==> Generating locale: $locale"
    # Start clean so removed screenshots don't linger.
    rm -rf "$dir"
    mkdir -p "$dir/changelogs" "$shots_dir"

    cp "$SRC/$locale/title.txt" "$dir/title.txt"
    cp "$SRC/$locale/short_description.txt" "$dir/short_description.txt"
    cp "$SRC/$locale/full_description.txt" "$dir/full_description.txt"

    for f in "$SRC/$locale/changelogs"/*.txt; do
        cp "$f" "$dir/changelogs/"
    done

    cp "$ICON_SRC" "$img/icon.png"
    cp "$FEATURE_SRC" "$img/featureGraphic.png"

    local i=1
    for shot in "${shots[@]}"; do
        cp "$FRAMED_DIR/$shot" "$shots_dir/$(printf '%02d' "$i").png"
        i=$((i + 1))
    done

    # Strip EXIF/metadata from every PNG. F-Droid's fdroiddata CI rejects images
    # that still carry metadata; keeping the in-repo copies clean matches that
    # bar so the same assets can be reused anywhere.
    if command -v exiftool >/dev/null 2>&1; then
        exiftool -quiet -overwrite_original -all= "$img"/icon.png "$img"/featureGraphic.png "$shots_dir"/*.png
    else
        echo "warning: exiftool not found — PNGs left with embedded metadata" >&2
    fi
}

gen_locale en-US "${EN_SHOTS[@]}"
gen_locale bg    "${BG_SHOTS[@]}"

echo
echo "Done. Fastlane tree written under: $DEST_ROOT"
