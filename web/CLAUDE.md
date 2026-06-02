# web/

Static marketing site for `srednabg.com`. Pure HTML/CSS/JS — Apache 2.4.66 on Namecheap shared hosting; `.htaccess` is the only deploy lever.

Landing page lives at `/indexx.html`; root `/` intentionally returns 403.

## Hosting layout

Namecheap **addon domain**, served from `$HOME/srednabg_com/` on the cPanel host. **Not** under `public_html/srednabg_com/` — that's the default cPanel layout but this account places the addon docroot directly under `$HOME`.

| Path on host | Source in repo | Notes |
|---|---|---|
| `$HOME/srednabg_com/indexx.html` | `web/html/indexx.html` | Manual upload (FTP/SSH); no CI. |
| `$HOME/srednabg_com/assets/...` | `web/html/assets/...` | CSS, JS, i18n JSON, screenshots. |
| `$HOME/srednabg_com/.htaccess` | `web/html/.htaccess` | Force HTTPS, dotfile blocks, HSTS, gzip, expires, /api/* rewrites. |
| `$HOME/srednabg_com/api/zones.json` | (produced by cron) | Live zone data. Not committed. |
| `$HOME/srednabg_com/api/version.json` | (produced by cron) | Hash-gated app sync. Not committed. |
| `$HOME/srednabg_com/api/zones-<ts>.json` | (produced by cron) | Snapshot per change, 26 retained. |
| `$HOME/srednabg_com/assets/map-bundle.zip` | (produced by `web/fdroid/scripts/publish-map-bundle.sh`) | The single mutable latest map bundle. `.github/workflows/android-release.yml` downloads it, verifies it against the digest in `web/fdroid/map-bundle-checksums.txt`, and snapshots it per-tag onto the GitHub Release as the immutable `map-bundle-<tag>.zip` that F-Droid fetches. Manual SCP upload — no automation. |

The `/api/*` tree is **not in git** — it's produced by the scraper cron on the same host. See `scrapers/CLAUDE.md` "Hosted deployment (Namecheap)".

## F-Droid submission draft (`web/fdroid/`)

Source of truth for the SrednaBG F-Droid listing. Nothing here is read by F-Droid directly — at submission time, `web/fdroid/scripts/stage-fdroiddata.sh` copies the relevant files into a local clone of the `fdroiddata` repo for PR.

- `metadata.yml` — draft of `metadata/com.demosten.srednabg.yml`. F-Droid's prebuild (`backend/scripts/fetch-fdroid-map-bundle.sh`) does `curl` + `sha256sum -c` on the per-tag `map-bundle-<tag>.zip` GitHub Release asset; the digest only changes when the map content does.
- `{en-US,bg}/{title,short_description,full_description}.txt` + `changelogs/<versionCode>.txt` — locale-aware listing copy.
- `map-bundle-checksums.txt` — a single `<sha256>  map-bundle.zip` line (the current bundle's digest), kept in sync with the `SHA256` in `backend/scripts/fetch-fdroid-map-bundle.sh`; consumed by the Android release workflow to verify the latest download.
- `scripts/publish-map-bundle.sh` — run only when the map content changes: rebuilds the bundle, re-pins the single digest in `map-bundle-checksums.txt` + `fetch-fdroid-map-bundle.sh`, prints the SCP command to replace the hosted `map-bundle.zip`.
- `scripts/stage-fdroiddata.sh` — stages the above files into an `fdroiddata` clone, ready for `git add`.

## .htaccess responsibilities

`web/html/.htaccess` is hardened for pre-launch:
- HTTP→HTTPS redirect (handles direct TLS and proxied front-ends)
- Dotfile + backup-file 404s (`.git`, `.env`, `.bak`, editor swap files)
- Security headers via `mod_headers` (HSTS 180d, `X-Content-Type-Options`, `X-Frame-Options DENY`, Permissions-Policy disabling geo/cam/mic, `X-Robots-Tag noindex,nofollow` while pre-launch)
- gzip via `mod_deflate` for HTML/CSS/JS/JSON/SVG
- Cache headers via `mod_expires` (HTML 5min, CSS/JS/JSON 1h, snapshots 1 year)
- `/api/zones` and `/api/version` extensionless rewrites to the underlying `.json` files

When site goes live: drop `X-Robots-Tag noindex` and consider HSTS preload — both are .htaccess one-liners.

## Build commands

None. The site is static. Edit `web/html/`, copy to `$HOME/srednabg_com/` on Namecheap (FTP/SSH or rsync). No bundler, no minifier.

## Screenshot tree (`web/screenshots/`)

**Tracked in git.** Landing zone for the screenshot tooling under `qa/` — regenerable via the skills, but committed so the store listing is reproducible: `web/fdroid/scripts/stage-fdroiddata.sh` stages the framed PNGs straight from here.

- `web/screenshots/<platform>/NN-<platform>-<theme>-<lang>.png` — raw store screenshots produced by `/screenshot-app` (`qa/srednabg_screenshots.py`).
- `web/screenshots/<platform>/framed/NN-<theme>-<lang>.png` — Waze-style marketing frames produced by `/frame-screenshots` (`qa/srednabg_frame_screenshots.py`).
- `web/screenshots/playground/` — local scratch area (also tracked; keep throwaway experiments out of it).

Re-run the skills to rebuild; don't hand-edit. The deploy rsync target is `web/html/` only — this tree is **not** part of the marketing site. Anything that needs to be published has to be copied into `web/html/assets/img/` (or sibling) and committed there.
