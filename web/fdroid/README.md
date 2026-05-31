# web/fdroid/

Draft of the F-Droid submission for SrednaBG. None of this is read directly
by F-Droid — at submission time, `scripts/stage-fdroiddata.sh` copies the
relevant files into a local clone of the `fdroiddata` repo.

See `test-data/f-droid-release.md` for the full release plan and the current
execution status.

## Layout

- `metadata.yml` — draft of `metadata/com.demosten.srednabg.yml` for fdroiddata.
- `{en-US,bg}/title.txt` — app title per locale.
- `{en-US,bg}/short_description.txt` — F-Droid short description (≤80 chars).
- `{en-US,bg}/full_description.txt` — F-Droid full description (≤4000 chars).
- `{en-US,bg}/changelogs/<versionCode>.txt` — per-release notes.
- `map-bundle-checksums.txt` — `<sha256>  <tag>` lines consumed by the
  release workflow and (in the metadata YAML) by F-Droid's build sandbox.
- `scripts/publish-map-bundle.sh` — builds the map bundle, computes SHA-256,
  prints the SCP/rsync command for manual upload to `srednabg.com/assets/`.
- `scripts/stage-fdroiddata.sh` — copies the files above into a target
  fdroiddata clone, ready for `git add`.

## Reviewer-facing notes (not in the YAML)

- `subdir: android` — Gradle root, not repo root.
- `gradle: [aosp]` — F-Droid builds the **aosp** product flavor
  (`assembleAospRelease`). The app has two flavors differing only in the
  location provider: `aosp` uses the platform `LocationManager` and has **no
  Google Play Services dependency**; `gms` adds `play-services-location`
  (FusedLocationProvider) and is published to the Play Store only. The
  GMS-specific code lives in `android/app/src/gms/`, the dependency is declared
  with the `gmsImplementation` configuration, and `src/main/` references no GMS
  type — so the aosp variant compiles and links entirely free of proprietary
  Google libraries.
- No `AntiFeatures`: backend sync is feature-flagged off
  (`FeatureFlags.IS_MAP_SYNC_ENABLED = false`), no tracking, and the built
  (aosp) variant has no non-free dependencies.
- Map bundle is fetched by F-Droid's sandbox from
  `srednabg.com/assets/map-bundle-<tag>.zip` and SHA-256 pinned in the
  metadata YAML.
- Reproducible builds are deferred to a later release; F-Droid signs the
  APK with its own key for v1.0.3.
