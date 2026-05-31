#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — backend / scripts

# Fetches + SHA-256-verifies the offline map bundle for F-Droid's build sandbox.
# Called from the `prebuild` step of the F-Droid recipe
# (web/fdroid/metadata.yml -> fdroiddata metadata/com.demosten.srednabg.yml).
#
# Why a script instead of inline prebuild commands: the curl (flags + URL) and
# the sha256sum line (64-char digest) both exceed F-Droid's metadata line
# width. `fdroid rewritemeta` folds long lines, and that fold collides with the
# trailing-spaces lint — so a single short `bash ...` call is the only form that
# satisfies both rewritemeta and lint. The URL + digest stay auditable here, in
# the repo at the build tag.
#
# Release checklist: update URL + SHA256 below when cutting a new tag; the digest
# must match the entry in web/fdroid/map-bundle-checksums.txt for that tag.
set -euo pipefail

URL="https://srednabg.com/assets/map-bundle-v1.0.3.zip"
SHA256="0513907ed5108c34a5a13646f5c4dc8968c44f372587bef888543c80b757bcd1"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$SCRIPT_DIR/../data"
ZIP="$DATA_DIR/map-bundle.zip"

mkdir -p "$DATA_DIR"
curl -fsSL --http1.1 --retry 5 --retry-delay 3 --retry-all-errors -o "$ZIP" "$URL"
echo "$SHA256  $ZIP" | sha256sum -c -
rm -rf "$DATA_DIR/map-bundle"
unzip -q "$ZIP" -d "$DATA_DIR/map-bundle"
rm "$ZIP"
