#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

# Cron wrapper for the SrednaBG zone scraper on Namecheap shared hosting.
# Loads env, runs the scraper into the public api dir, then pings Telegram.
#
# Layout (cPanel user $HOME):
#   ~/srednabg-scraper/         private; this script lives in scripts/
#   ~/srednabg_com/api/         public docroot for /api/zones, /api/version
#   ~/.config/srednabg/scraper.env  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
set -u

ROOT="$HOME/srednabg-scraper"
TARGET="$HOME/srednabg_com/api"
LOG="$ROOT/logs/cron.log"
STATE="$ROOT/state/last_hash"
ENV_FILE="$HOME/.config/srednabg/scraper.env"

mkdir -p "$ROOT/logs" "$ROOT/state" "$TARGET"

# Rotate the log at >5 MB. stat -c is GNU; -f is BSD/macOS.
if [ -f "$LOG" ]; then
  SIZE=$(stat -c%s "$LOG" 2>/dev/null || stat -f%z "$LOG" 2>/dev/null || echo 0)
  if [ "$SIZE" -gt 5242880 ]; then
    mv "$LOG" "$LOG.1"
  fi
fi

# Load secrets (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) without echoing them.
# shellcheck disable=SC1090
if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

cd "$ROOT" || exit 2

START=$(date -u +%s)
{
  echo "=== $(date -u +%FT%TZ) start ==="
  ./venv/bin/python -m src.output --target-dir "$TARGET"
} >>"$LOG" 2>&1
RC=$?
DUR=$(( $(date -u +%s) - START ))

# Read the new hash from the version.json the scraper just wrote.
NEW_HASH=$(./venv/bin/python -c \
  "import json,sys; print(json.load(open(sys.argv[1]))['hash'])" \
  "$TARGET/version.json" 2>/dev/null || echo "")
PREV_HASH=$(cat "$STATE" 2>/dev/null || echo "")
if [ "$RC" -eq 0 ] && [ -n "$NEW_HASH" ]; then
  echo "$NEW_HASH" > "$STATE"
fi

./venv/bin/python -m src.notify "$RC" "$DUR" "$NEW_HASH" "$PREV_HASH" "$LOG" \
  >>"$LOG" 2>&1

exit "$RC"
