#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scripts
#
# Set up (or verify) the single root .venv that the repo's Python tooling uses:
# the scrapers pipeline (bs4, requests, overpy, pydantic) and the QA harness +
# screenshot tooling (PyYAML, Pillow), plus the dev tools (pytest, ruff).
#
# Usage:
#   bash scripts/setup-python.sh            # create .venv + install everything
#   bash scripts/setup-python.sh --check    # verify only; print what to run, no install
#
# The shell wrappers (scrapers/scripts/refresh-zones.sh, qa/*.sh) call `--check`
# as a preflight and then run Python via .venv/bin/python directly, so they work
# whether or not the venv is "activated". The Python entry points have a matching
# guard that auto-uses the venv when present (see scrapers/src/_preflight.py,
# qa/_preflight.py). Nothing here installs itself behind your back — the default
# mode only runs when you invoke it explicitly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_ROOT/.venv"
VENV_PY="$VENV/bin/python"

# The third-party modules the repo's tooling needs (import names, not pip names).
REQUIRED_MODS="bs4 requests overpy pydantic yaml PIL"

instruct() {
    # Print the actionable instruction in the repo's house "error:" style.
    local detail="$1"
    echo "error: Python environment not set up (${detail})." >&2
    echo "error: run \`bash scripts/setup-python.sh\`, then retry." >&2
}

# --check: verify the venv interpreter has the deps. Activation-independent —
# it probes .venv/bin/python directly, never the caller's $PATH python.
if [ "${1:-}" = "--check" ]; then
    if [ ! -x "$VENV_PY" ]; then
        instruct ".venv missing"
        exit 1
    fi
    missing="$("$VENV_PY" - <<'PY'
import importlib.util
mods = "bs4 requests overpy pydantic yaml PIL".split()
print(" ".join(m for m in mods if importlib.util.find_spec(m) is None))
PY
)"
    if [ -n "$missing" ]; then
        instruct ".venv incomplete: $missing"
        exit 1
    fi
    exit 0
fi

if [ "${1:-}" != "" ]; then
    echo "usage: bash scripts/setup-python.sh [--check]" >&2
    exit 2
fi

# Default mode: create the venv (if needed) and install the full dev env.
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found. Install Python 3.11+ and re-run." >&2
    exit 1
fi

py_minor="$(python3 -c 'import sys; print(sys.version_info[1])')"
if [ "$(python3 -c 'import sys; print(sys.version_info[0])')" -ne 3 ] || [ "$py_minor" -lt 11 ]; then
    echo "warning: Python 3.11+ recommended (found $(python3 -V 2>&1)); continuing anyway." >&2
fi

if [ ! -x "$VENV_PY" ]; then
    echo "Creating virtualenv at $VENV …" >&2
    python3 -m venv "$VENV"
fi

echo "Installing dependencies (scrapers dev + qa) …" >&2
"$VENV_PY" -m pip install \
    -r "$REPO_ROOT/scrapers/requirements-dev.txt" \
    -r "$REPO_ROOT/qa/requirements.txt"

# Upgrade pip last (per project preference: keep it current after the deps land).
echo "Upgrading pip …" >&2
"$VENV_PY" -m pip install --upgrade pip

echo >&2
echo "✓ Python environment ready at $VENV" >&2
echo "  Activate it with:  source .venv/bin/activate" >&2
echo "  (The .sh wrappers and python entry points also use it automatically.)" >&2
