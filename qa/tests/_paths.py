# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa

"""Put the repo root on sys.path so `from qa import …` resolves under
`python -m unittest discover qa/tests` (which only adds qa/tests itself).

Import this first in every test module:  ``import _paths  # noqa: F401``.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
