# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Dependency preflight for the QA / screenshot entry points.

Same three-state behaviour as scrapers/src/_preflight.py (run / re-exec under an
unactivated .venv / instruct), so a fresh clone gets an actionable message
instead of a raw ``ModuleNotFoundError``. Stdlib-only; call before the
third-party imports.
"""

import importlib.util
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VENV = _REPO_ROOT / ".venv"
_VENV_PY = _VENV / "bin" / "python"


def require(*mods: str, module: str | None = None) -> None:
    """Ensure ``mods`` are importable, else re-exec under .venv or instruct.

    Pass ``module`` (dotted name) for ``python -m`` entry points; script-form
    entries (``python qa/foo.py``) omit it and re-exec via ``sys.argv``.
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
