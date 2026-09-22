"""Test configuration.

Qt tests run headless: the offscreen platform plugin is selected before any Qt import, and on
Windows that plugin needs to be told where the system fonts are.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
