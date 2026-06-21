# web/

Static marketing site for `srednabg.com`. Pure HTML/CSS/JS — LiteSpeed/Apache 2.4.66 on Namecheap shared hosting; `.htaccess` is the only deploy lever.

Landing page is `web/html/index.html` (BG default, EN toggle; i18n strings as inline JSON `<script>` blocks in the `<head>`). Sections: hero, features, how-it-works, screen gallery, privacy, download. The **download grid** has five cards: **App Store** (`apps.apple.com/app/srednabg/id6773132524`), **Google Play** (`com.demosten.srednabg`), **F-Droid** (`f-droid.org/packages/com.demosten.srednabg/`), **APK from GitHub Releases** (with sideload steps), and **Source on GitHub**. The hero "Download the app" CTA anchors to that grid.

A second page **`web/html/faq.html`** holds the FAQ, linked from the nav (`nav.faq`) and served at the clean URL `/faq`. Same i18n pattern as the landing page — its own inline `#i18n-bg` / `#i18n-en` JSON blocks (`faq.*` keys) under `faq.*`, BG default with EN toggle. **Language carries across pages by query param, not storage:** `assets/js/site.js`'s `propagateLang(code)` rewrites every same-origin, non-asset, non-anchor `<a href>` to append `?lang=<code>` whenever the language is applied, so `/` ↔ `/faq` navigation keeps the chosen language. New standalone pages need only their own inline i18n blocks plus a `/<page>` rewrite — `propagateLang` wires the linking automatically.

## Hosting layout

Namecheap **addon domain**, served from `$HOME/srednabg_com/` on the cPanel host. **Not** under `public_html/srednabg_com/` — that's the default cPanel layout but this account places the addon docroot directly under `$HOME`.

| Path on host | Source in repo | Notes |
|---|---|---|
| `$HOME/srednabg_com/index.html` | `web/html/index.html` | Manual upload (FTP/SSH); no CI. |
| `$HOME/srednabg_com/privacy.html` | `web/html/privacy.html` | Served at clean `/privacy` (linked from both store listings). |
| `$HOME/srednabg_com/faq.html` | `web/html/faq.html` | Served at clean `/faq` (linked from the landing-page nav). |
| `$HOME/srednabg_com/assets/...` | `web/html/assets/...` | CSS, JS, i18n JSON, screenshots. |
| `$HOME/srednabg_com/.htaccess` | `web/html/.htaccess` | Force HTTPS, dotfile blocks, HSTS, gzip, expires, /api/* rewrites. |
| `$HOME/srednabg_com/api/zones.json` | (produced by cron) | Live zone data. Not committed. |
| `$HOME/srednabg_com/api/version.json` | (produced by cron) | Hash-gated app sync. Not committed. |
| `$HOME/srednabg_com/api/zones-<ts>.json` | (produced by cron) | Snapshot per change, 26 retained. |

The `/api/*` tree is **not in git** — it's produced by the scraper cron on the same host. See `scrapers/CLAUDE.md` "Hosted deployment (Namecheap)".

## F-Droid metadata (`web/fdroid/`)

Source of truth for the SrednaBG F-Droid listing. The build recipe is **merged into `fdroiddata`**; this dir stays the upstream copy used for ongoing per-tag updates. Nothing here is read by F-Droid directly — to push an update, `web/fdroid/scripts/stage-fdroiddata.sh` copies the relevant files into a local clone of the `fdroiddata` repo for the next PR.

- `metadata.yml` — draft of `metadata/com.demosten.srednabg.yml`. F-Droid's prebuild (`backend/scripts/fetch-fdroid-map-bundle.sh`) does `curl` + `sha256sum -c` on the per-tag `map-bundle-<tag>.zip` GitHub Release asset; the digest only changes when the map content does.
- `{en-US,bg}/{title,short_description,full_description}.txt` + `changelogs/<versionCode>.txt` — locale-aware listing copy.
- `map-bundle-checksums.txt` — a single `<sha256>  map-bundle.zip` line (the current bundle's digest); the one pinned source of truth, read at build time by `backend/scripts/fetch-fdroid-map-bundle.sh` and consumed by the Android release workflow to verify the latest download.
- `scripts/publish-map-bundle.sh` — run only when the map content changes: rebuilds the bundle, re-pins the single digest in `map-bundle-checksums.txt`, and uploads `map-bundle.zip` (+`.sha256`) to the rolling `map-bundle-latest` GitHub Release (`gh release upload --clobber`; the web host no longer serves the bundle). `.github/workflows/android-release.yml` downloads that asset, verifies it against the pinned digest, and snapshots it per-tag as the immutable `map-bundle-<tag>.zip` that F-Droid fetches.
- `scripts/stage-fdroiddata.sh` — stages the above files into an `fdroiddata` clone, ready for `git add`.

## .htaccess responsibilities

`web/html/.htaccess` is hardened for pre-launch:
- HTTP→HTTPS redirect (handles direct TLS and proxied front-ends)
- Dotfile + backup-file 404s (`.git`, `.env`, `.bak`, editor swap files)
- Security headers via `mod_headers` (HSTS 180d, `X-Content-Type-Options`, `X-Frame-Options DENY`, Permissions-Policy disabling geo/cam/mic). The site is **live**, so no `X-Robots-Tag noindex` — search engines may index it.
- gzip via `mod_deflate` for HTML/CSS/JS/JSON/SVG
- Cache headers via `mod_expires` + per-file `Cache-Control` (`version.json` 5min, `zones.json` 1h, timestamped snapshots 1yr immutable; CSS/JS 1h; HTML 5min)
- Extensionless rewrites: `/api/zones` + `/api/version` → `.json`, `/privacy` → `privacy.html`, `/faq` → `faq.html`

The site is live: the `X-Robots-Tag noindex` header has been dropped so search engines can index it. HSTS preload remains intentionally **not** enabled — it requires `max-age` ≥ 1yr + `includeSubDomains` + `preload` and submission to hstspreload.org, and is effectively a one-way door (removal is slow); not worth it for a static marketing site.

## Build commands

None. The site is static. Edit `web/html/`, copy to `$HOME/srednabg_com/` on Namecheap (FTP/SSH or rsync). No bundler, no minifier.

## Screenshot tree (`web/screenshots/`)

**Tracked in git.** Landing zone for the screenshot tooling under `qa/` — regenerable via the skills, but committed so the store listing is reproducible: `web/fdroid/scripts/stage-fdroiddata.sh` stages the framed PNGs straight from here.

- `web/screenshots/<platform>/NN-<platform>-<theme>-<lang>.png` — raw store screenshots produced by `/screenshot-app` (`qa/srednabg_screenshots.py`).
- `web/screenshots/<platform>/framed/NN-<theme>-<lang>.png` — Waze-style marketing frames produced by `/frame-screenshots` (`qa/srednabg_frame_screenshots.py`).
- `web/screenshots/playground/` — local scratch area (also tracked; keep throwaway experiments out of it).

Re-run the skills to rebuild; don't hand-edit. The deploy rsync target is `web/html/` only — this tree is **not** part of the marketing site. Anything that needs to be published has to be copied into `web/html/assets/img/` (or sibling) and committed there.
