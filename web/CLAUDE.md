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
| `$HOME/srednabg_com/assets/map-bundle-<tag>.zip` | (produced by `web/fdroid/scripts/publish-map-bundle.sh`) | Per-release immutable map bundle. SHA-256 pinned by `.github/workflows/android-release.yml` against `web/fdroid/map-bundle-checksums.txt`, and by F-Droid's build sandbox via the hash in `web/fdroid/metadata.yml`. Manual SCP upload — no automation. |

The `/api/*` tree is **not in git** — it's produced by the scraper cron on the same host. See `scrapers/CLAUDE.md` "Hosted deployment (Namecheap)".

## F-Droid submission draft (`web/fdroid/`)

Source of truth for the SrednaBG F-Droid listing. Nothing here is read by F-Droid directly — at submission time, `web/fdroid/scripts/stage-fdroiddata.sh` copies the relevant files into a local clone of the `fdroiddata` repo for PR.

- `metadata.yml` — draft of `metadata/com.demosten.srednabg.yml`. F-Droid's sandbox does `curl` + `sha256sum -c` on the hosted `map-bundle-<tag>.zip`; update the pinned hash here when re-cutting a release.
- `{en-US,bg}/{title,short_description,full_description}.txt` + `changelogs/<versionCode>.txt` — locale-aware listing copy.
- `map-bundle-checksums.txt` — `<sha256>  <tag>` lines maintained by `scripts/publish-map-bundle.sh`; consumed by the Android release workflow.
- `scripts/publish-map-bundle.sh` — rebuilds the bundle, copies it to `map-bundle-<tag>.zip`, computes the hash, updates `map-bundle-checksums.txt`, prints the SCP command for upload.
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

**Gitignored.** Landing zone for the screenshot tooling under `qa/` — regenerable, not committed:

- `web/screenshots/<platform>/NN-<platform>-<theme>-<lang>.png` — raw store screenshots produced by `/screenshot-app` (`qa/srednabg_screenshots.py`).
- `web/screenshots/<platform>/framed/NN-<theme>-<lang>.png` — Waze-style marketing frames produced by `/frame-screenshots` (`qa/srednabg_frame_screenshots.py`).
- `web/screenshots/playground/` — local-only scratch area.

Re-run the skills to rebuild; don't hand-edit. The deploy rsync target is `web/html/` only — this tree is **not** part of the marketing site. Anything that needs to be published has to be copied into `web/html/assets/img/` (or sibling) and committed there.
