# SrednaBG Backend

Self-hosted infrastructure for serving Bulgaria map tiles and zone data. Runs on a Mac Mini M4 with Docker.

## Services

- **tileserver-gl** — Serves Bulgaria OpenMapTiles vector tiles (host port 8070 → container 8080)
- **nginx** — Reverse proxy with rate limiting, gzip, and CORS (port 80)

## Endpoints

| Endpoint | Description | Cache |
|----------|-------------|-------|
| `/tiles/` | Vector tile proxy to tileserver-gl | 24 hours |
| `/api/zones` | Zone database (zones.json) | 1 hour |
| `/api/version` | Version metadata | 5 minutes |
| `/health` | Health check | None |

## Prerequisites

- Docker and Docker Compose (Docker must be running for the tile build)
- ~4 GB free RAM (for the Planetiler JVM)
- ~1 GB free disk (PBF download + mbtiles output + sources)

## Quick Start

### 1. Generate Bulgaria tiles

```bash
./scripts/download-tiles.sh
```

The script runs [Planetiler](https://github.com/onthegomap/planetiler) in
Docker against the Geofabrik Bulgaria OSM extract (~200 MB) and writes
`tiles/bulgaria.mbtiles` (z5–z12, ~50 MB). No API key needed; takes a few
minutes on first run. Tile data © OpenStreetMap contributors (ODbL).

### 2. Update zone data

If you have generated `zones.json` from the scrapers:

```bash
./scripts/update-zones.sh
```

### 3. Start services

```bash
docker compose up -d
```

### 4. Verify

```bash
# Health check
curl http://localhost/health

# Zone data
curl http://localhost/api/zones | python3 -m json.tool | head -20

# Version info
curl http://localhost/api/version

# Tile server (open in browser)
open http://localhost/tiles/
```

## Updating Zone Data

After running the scraper pipeline:

```bash
cd ../scrapers
python -m src.output
cd ../backend
./scripts/update-zones.sh
```

Nginx serves the files directly — no restart needed (cache expires in 1 hour for zones, 5 minutes for version).

## Production Setup

### Dynamic DNS

For a home server, set up dynamic DNS so the app can reach it:

1. Register at [DuckDNS](https://www.duckdns.org/) (free)
2. Create a subdomain (e.g., `srednabg.duckdns.org`)
3. Set up a cron job to update the IP:
   ```bash
   */5 * * * * curl -s "https://www.duckdns.org/update?domains=srednabg&token=YOUR_TOKEN"
   ```

### HTTPS with Let's Encrypt

Option A: Use Caddy as a reverse proxy (automatic HTTPS):
```bash
# Replace nginx with Caddy in docker-compose.yml
# Caddy handles Let's Encrypt certificates automatically
```

Option B: Use certbot with nginx:
```bash
# Install certbot
brew install certbot

# Get certificate
sudo certbot certonly --standalone -d srednabg.duckdns.org

# Update nginx config to use HTTPS (port 443 with ssl_certificate directives)
```

### Firewall / Port Forwarding

1. Forward port 80 (HTTP) and 443 (HTTPS) to the Mac Mini's local IP
2. On macOS, ensure the firewall allows Docker connections:
   ```bash
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /usr/local/bin/docker
   ```

## Monitoring

Check service status:
```bash
docker compose ps
docker compose logs -f nginx
docker compose logs -f tileserver
```

Restart services:
```bash
docker compose restart
```
