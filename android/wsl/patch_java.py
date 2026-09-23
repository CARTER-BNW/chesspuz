#!/usr/bin/env python
"""Let the phone's Back key reach Qt.

python-for-android's Qt bootstrap ships a ``PythonActivity.java`` whose ``onKeyDown`` swallows
the first Back press ("Click again to close the app") and only forwards a second press within
two seconds. chesspuz handles Back itself (close a puzzle window, ask to end a run, go home), so
the key must arrive every time. This rewrites that method to forward straight to Qt's activity,
in every copy of the file it is given (the bootstrap template and the generated build copies).
Idempotent: a marker comment skips files already patched.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MARKER = "chesspuz: Back goes straight to Qt"
PATTERN = re.compile(
    r"    long lastBackClick = SystemClock\.elapsedRealtime\(\);\n"
    r"    @Override\n"
    r"    public boolean onKeyDown\(int keyCode, KeyEvent event\) \{\n"
    r".*?\n"
    r"        lastBackClick = SystemClock\.elapsedRealtime\(\);\n"
    r"        return super\.onKeyDown\(keyCode, event\);\n"
    r"    \}\n",
    re.DOTALL,
)
REPLACEMENT = (
    "    @Override\n"
    "    public boolean onKeyDown(int keyCode, KeyEvent event) {\n"
    f"        // {MARKER}: the app decides what Back does and never quits on it\n"
    "        return super.onKeyDown(keyCode, event);\n"
    "    }\n"
)


def patch(path: Path) -> str:
    if not path.exists():
        return "missing"
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return "already patched"
    new, count = PATTERN.subn(REPLACEMENT, text, count=1)
    if count != 1:
        return "pattern not found (python-for-android changed?)"
    path.write_text(new, encoding="utf-8")
    return "patched"


def main(argv: list[str]) -> int:
    status = 0
    for arg in argv:
        result = patch(Path(arg))
        print(f"{result}: {arg}")
        if result.startswith("pattern"):
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
