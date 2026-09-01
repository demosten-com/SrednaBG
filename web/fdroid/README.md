# web/fdroid/

Upstream source of truth for the SrednaBG F-Droid listing. The build recipe is
**merged into `fdroiddata`**; this dir is kept as the editable copy for ongoing
per-tag updates. None of this is read directly by F-Droid — to push an update,
`scripts/stage-fdroiddata.sh` copies the relevant files into a local clone of the
`fdroiddata` repo for the next PR.

## Layout

- `metadata.yml` — **mirror** of `metadata/com.demosten.srednabg.yml` in fdroiddata.
  Routine version bumps are written there by F-Droid's checkupdates bot
  (`AutoUpdateMode: Version`), not by us, so treat upstream master as the source
  of truth and re-sync this file from it before making any recipe change:
  `curl -fsSL https://gitlab.com/fdroid/fdroiddata/-/raw/master/metadata/com.demosten.srednabg.yml -o web/fdroid/metadata.yml`
- `{en-US,bg}/title.txt` — app title per locale.
- `{en-US,bg}/short_description.txt` — F-Droid short description (≤80 chars).
- `{en-US,bg}/full_description.txt` — F-Droid full description (≤4000 chars).
- `{en-US,bg}/changelogs/<versionCode>.txt` — per-release notes, **max 500
  characters each**. fdroiddata's CI warns above that
  (`Fastlane/Triple-T whatsNew in <locale> should be shorter than 500
  characters`) and Play's "What's new" field caps at the same 500, so a
  compliant note can be pasted into both. `gen-fastlane-metadata.sh` enforces
  this and fails rather than generating an over-long note.
- `map-bundle-checksums.txt` — a single `<sha256>  map-bundle.zip` line (the
  current bundle's digest); the one pinned source of truth, read at build time
  by `backend/scripts/fetch-fdroid-map-bundle.sh`. The Android release workflow
  uses it to verify the mutable `map-bundle.zip` from the rolling
  `map-bundle-latest` GitHub Release before snapshotting it per-tag onto the
  version's Release.
- `scripts/publish-map-bundle.sh` — run only when the map content changes:
  rebuilds the bundle, re-pins the digest in `map-bundle-checksums.txt`, and
  uploads the new latest to the rolling `map-bundle-latest` GitHub Release.
- `scripts/stage-fdroiddata.sh` — copies **only** `metadata.yml` into a target
  fdroiddata clone (`metadata/com.demosten.srednabg.yml`), ready for `git add`.
  Listing copy/graphics are **not** staged — they live in the app repo's
  Fastlane tree (below) and F-Droid imports them from the built tag.
- `scripts/gen-fastlane-metadata.sh` — regenerates the in-repo Fastlane tree at
  `fastlane/metadata/android/<locale>/` (title, descriptions, changelogs, and
  `images/{icon,featureGraphic,phoneScreenshots}`, EXIF-stripped) from the
  `web/fdroid/` copy + `design/` assets. `web/fdroid/` stays the single source of
  truth; the Fastlane tree is a generated artifact — edit the copy here and
  re-run, don't hand-edit `fastlane/`.

## Listing metadata lives in the app repo (Fastlane), not fdroiddata

F-Droid imports listing copy/graphics from the **app's own repo** in the Fastlane
layout (`fastlane/metadata/android/<locale>/`) at `fdroid update`, reading the
**built tag's** checkout. As long as the built tag contains `fastlane/`, the
fdroiddata submission is just the build recipe — **no locale dirs, no PNGs in
fdroiddata**. (This also keeps fdroiddata's CI happy: its EXIF-strip and
`name/summary/description` filename checks only run on files committed *there*,
so committing nothing but the yml sidesteps them.)

Note the filename split: the in-repo Fastlane tree uses Fastlane names
(`title`/`short_description`/`full_description`), while if you ever *did* put copy
in fdroiddata it would need F-Droid names (`name`/`summary`/`description`). We
don't, so it's moot — `gen-fastlane-metadata.sh` writes the Fastlane names.

## Reviewer-facing notes (not in the YAML)

- `subdir: android/app` — the app module dir (where `build/` is generated), so
  F-Droid auto-detects the APK under `<subdir>/build/outputs/apk/aosp/release/`
  and no `output:` field is needed. Gradle is invoked from there and walks up to
  `android/settings.gradle.kts` for the multi-module build. `commit:` is the full
  40-char SHA (not a tag — tags can move).
- `prebuild` runs in `android/app`, so it calls the map-bundle fetch script via
  `../../backend/scripts/fetch-fdroid-map-bundle.sh` (two levels up to repo root).
- `gradle: [aosp]` — F-Droid builds the **aosp** product flavor
  (`assembleAospRelease`). The app has two flavors differing only in the
  location provider: `aosp` uses the platform `LocationManager` and has **no
  Google Play Services dependency**; `gms` adds `play-services-location`
  (FusedLocationProvider) and is published to the Play Store only. The
  GMS-specific code lives in `android/app/src/gms/`, the dependency is declared
  with the `gmsImplementation` configuration, and `src/main/` references no GMS
  type — so the aosp variant compiles and links entirely free of proprietary
  Google libraries.
- No `AntiFeatures`: the only network calls are first-party GETs to
  `srednabg.com/api/{version,zones}` (zone data, no PII). That periodic zone
  sync is a **user opt-out** — the *Automatic zone updates* setting
  (`zone_sync_enabled`, default on); the manual *Sync zones now* button stays
  available regardless. Map sync is a separate path, compile-time gated off
  (`FeatureFlags.IS_MAP_SYNC_ENABLED = false`). No tracking, and the built
  (aosp) variant has no non-free dependencies.
- Map bundle is fetched by F-Droid's sandbox from the GitHub Release asset
  `map-bundle-<tag>.zip` and SHA-256-verified by
  `backend/scripts/fetch-fdroid-map-bundle.sh`, which the recipe's `prebuild`
  invokes. The fetch+verify lives in that repo script (not inline prebuild)
  because the curl flags + URL and the 64-char digest each exceed F-Droid's
  metadata line width, and `rewritemeta`'s line-folding then collides with the
  trailing-spaces lint — a single short `bash …` call satisfies both. The URL
  stays auditable in the script and the digest in `map-bundle-checksums.txt`,
  both in the repo at the build tag.
- Reproducible builds are deferred to a later release; F-Droid signs the
  APK with its own key (current recipe builds v1.0.4 / versionCode 10004).
