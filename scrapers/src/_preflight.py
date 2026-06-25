# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — scrapers

"""Dependency preflight for the scraper entry points.

Keeps a developer who hasn't set up the Python env from seeing a raw
``ModuleNotFoundError``. Three states, mirroring the build's house pattern of
"detect missing prerequisite -> tell the developer the exact command":

1. deps importable in the current interpreter -> run normally.
2. the root ``.venv`` exists but isn't the current interpreter (not activated)
   -> transparently re-exec under it (no install).
3. ``.venv`` missing or incomplete -> print the instruction and exit 1.

Stdlib-only so it imports cleanly even when nothing else is installed; must run
*before* the heavy third-party imports.
"""

import importlib.util
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VENV = _REPO_ROOT / ".venv"
_VENV_PY = _VENV / "bin" / "python"


def require(*mods: str, module: str | None = None) -> None:
    """Ensure ``mods`` are importable, else re-exec under .venv or instruct.

    ``module`` is the dotted name to re-exec with ``-m`` (e.g. "src.output");
    pass it for ``python -m`` entry points so the re-exec keeps the package
    context. Script-form entries omit it and re-exec via ``sys.argv``.
    """
    if all(importlib.util.find_spec(m) is not None for m in mods):
        return  # state 1

    # Compare venv prefixes, not the interpreter realpath: a venv's python is a
    # symlink to the base interpreter, so realpath() would collapse every venv
    # to the same target and the re-exec would never fire.
    running_under_venv = Path(sys.prefix).resolve() == _VENV.resolve()
    if _VENV_PY.exists() and not running_under_venv:  # state 2
        sys.stderr.write("note: re-running under .venv (not activated)\n")
        py = str(_VENV_PY)
        if module:
            os.execv(py, [py, "-m", module, *sys.argv[1:]])
        else:
            os.execv(py, [py, *sys.argv])

    # state 3: venv missing, or it IS this interpreter and deps still missing.
    missing = [m for m in mods if importlib.util.find_spec(m) is None]
    sys.stderr.write(
        f"error: Python env not set up (.venv missing or incomplete: "
        f"{', '.join(missing)}).\n"
    )
    sys.stderr.write("error: run `bash scripts/setup-python.sh`, then retry.\n")
    raise SystemExit(1)
