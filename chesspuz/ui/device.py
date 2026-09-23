"""Where the UI runs: a desktop window, or a phone (``android/mobile/entry.py`` sets the flag).

The pages lay themselves out from their own size (portrait = board above the panel), so this
flag only covers what cannot be derived from geometry: no window sizing on the phone, no
features that need a desktop (engine executable, database rebuild).
"""

from __future__ import annotations

import os

ENV_VAR = "CHESSPUZ_MOBILE"

MOBILE = os.environ.get(ENV_VAR, "").strip() not in ("", "0")
