# Contributing to SrednaBG

Thanks for considering a contribution! SrednaBG is a small, free, open-source project — issues, fixes, zone-data corrections, and translations are all welcome.

## Scope

SrednaBG covers **Bulgaria's section control (секционен контрол) zones only**. Adding other countries is out of scope for this repo — the data sources, road taxonomy, and unit conventions are BG-specific. If you want SrednaBG-style coverage elsewhere, fork is fine.

UI strings are Bulgarian + English. Zone data is Bulgarian Cyrillic by source.

## Reporting issues

Open a GitHub issue with:

- **What you expected vs. what happened.**
- **Where**: app version (Android phone / iOS phone, or AA / CarPlay surfaces — note these are WIP and not in the initial release), device or emulator, and — if relevant — the zone (road + direction, e.g. *AM Trakiya, east, km 132–148*).
- **Logs** if you have them. On Android: `adb logcat -s SrednaBG:V LocationTrackingService:V`. On iOS: Console.app filtered to the `SrednaBG` subsystem.
- **Zone-data problems** (wrong limit, wrong endpoints, missing zone, decommissioned zone) are especially useful — please cite the BG TOLL or other source if you have one.

Security issues: please do **not** file a public issue. Email demosten@gmail.com instead and include SrednaBG in the subject.

## Suggesting features

Open an issue first to discuss before writing code, especially for anything that changes the phone UI, the zone data schema, the alert behavior, or the WIP AA / CarPlay surfaces. The core engine and offline-first design constrain what's reasonable; a quick discussion saves rework.

## Development setup

The repo is a monorepo. Each area has its own `CLAUDE.md` with build commands, key files, and conventions — start there:

- `android/CLAUDE.md` — phone app (shipping) + the WIP Android Auto / AAOS targets. The pure-Kotlin calculation engine (no Android dependency; runs on JVM) lives at `android/core/CLAUDE.md`.
- `ios/CLAUDE.md` — Swift 6 / SwiftUI phone app + the WIP, currently-unwired CarPlay target.
- `scrapers/CLAUDE.md` — Python pipeline that produces `zones.json`.
- `backend/CLAUDE.md` — tileserver-gl + nginx Docker stack and the offline map-bundle builder.
- `qa/CLAUDE.md` — end-to-end harness driving the phone emulator via `adb`.
- `web/CLAUDE.md` — static marketing site at `srednabg.com`.

Top-level `README.md` has a Quick Start with the most common build/test commands.

## Pull request workflow

1. Fork and create a topic branch off `main`.
2. Make your change. Keep PRs small and focused on one thing.
3. Run the relevant tests for the area you touched (Gradle commands run from `android/`):
   - `cd android && ./gradlew :core:test` for engine changes.
   - `cd android && ./gradlew :app:test` and `cd android && ./gradlew :app:lint` for Android.
   - `cd scrapers && python -m pytest` for the data pipeline.
   - For UI/behavior changes on Android, run `python qa/srednabg_qa.py --suite smoke` against an emulator with the debug APK installed.
   - For iOS, build and run on the Simulator; if behavior is location-dependent, drive it with `scripts/feed_gpx_ios.py`.
4. Open a PR against `main`. Describe what changed and how you tested it. Link any related issue.
5. CI (`.github/workflows/android-build.yml`) runs core tests, lint, and assembles a debug APK. The scraper workflow runs on `scrapers/**` paths. Please make sure CI is green before requesting review.

## Coding style

- **Kotlin** (android): follow the existing style. Pure-Kotlin code in `android/core/` must stay free of Android dependencies — it runs on the JVM. The iOS side maintains its own Swift hand-port mirror at `ios/Packages/SrednaBGCore/`.
- **Swift** (ios): SwiftLint is configured; please run it locally before pushing. Swift 6 strict concurrency is on.
- **Python** (scrapers): keep `requirements.txt` / `requirements-dev.txt` as the source of truth — no `pyproject.toml`.
- **No new dependencies without discussion.** APK size and offline-first are constraints; map-bundle pages especially are scarce.
- **No Google-Maps / Mapbox / paid-tile dependencies.** Tiles come from the self-hosted MapLibre stack.

## Commit messages

Short, one-line, imperative-ish description of what the change does. Match the existing log:

```
Added green accent to Android
Fixed average speed max to not be above 250km/h
Updated map and map arrow settings for iOS, fixed issue with location permissions
```

No Conventional-Commits prefix is required. Reference issue numbers when relevant (`#123`).

## Adding yourself to AUTHORS

If you contribute non-trivial code or data, feel free to add yourself to [`AUTHORS`](AUTHORS) in the same PR — sorted alphabetically by surname. Trivial fixes (typos, single-line corrections) don't need an `AUTHORS` entry; the git history is enough.

## License

By submitting a pull request, you agree that your contribution is licensed under the project's [MIT License](LICENSE). No CLA is required — GitHub's standard inbound = outbound rule applies.

## Code of conduct

Be respectful. Disagreements about technical decisions are fine; personal attacks, harassment, or hostility are not. Maintainers may close or remove contributions that violate this in spirit.
