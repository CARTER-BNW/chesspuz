#!/usr/bin/env python
"""Apply chesspuz's settings to the buildozer.spec that pyside6-android-deploy generated.

Run inside the build box by wsl/build.sh before every build. Keys that buildozer's template
lists as comments (``#android.api = 31``) are replaced in place; missing keys are appended to
their section. The tool's own keys (requirements, p4a.bootstrap = qt, p4a.local_recipes,
android.add_jars, p4a.extra_args with --qt-libs, permissions, ndk/sdk paths) are kept, except
the ones listed here.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def set_key(text: str, section: str, key: str, value: str) -> str:
    """Set ``key = value`` inside ``[section]``; an existing (possibly commented) line wins."""
    lines = text.splitlines()
    start = end = None
    for i, line in enumerate(lines):
        if re.fullmatch(r"\s*\[([^\]]+)\]\s*", line):
            if start is not None:
                end = i
                break
            if line.strip() == f"[{section}]":
                start = i
    if start is None:
        lines += ["", f"[{section}]", f"{key} = {value}"]
        return "\n".join(lines) + "\n"
    if end is None:
        end = len(lines)
    pattern = re.compile(r"^\s*#?\s*" + re.escape(key) + r"\s*=")
    for i in range(start + 1, end):
        if pattern.match(lines[i]):
            lines[i] = f"{key} = {value}"
            break
    else:
        lines.insert(end, f"{key} = {value}")
    return "\n".join(lines) + "\n"


def get_key(text: str, key: str) -> str | None:
    match = re.search(r"(?m)^" + re.escape(key) + r"\s*=\s*(.*)$", text)
    return match.group(1).strip() if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--p4a-commit", required=True)
    parser.add_argument("--bin-dir", required=True)
    args = parser.parse_args()
    text = args.spec.read_text(encoding="utf-8")

    requirements = get_key(text, "requirements") or "python3,shiboken6,PySide6"
    wanted = [r.strip() for r in requirements.split(",") if r.strip()]
    for extra in ("sqlite3", "chess"):
        if extra not in wanted:
            wanted.append(extra)
    include_exts = get_key(text, "source.include_exts") or "py,png,jpg,kv,atlas"
    exts = [e.strip() for e in include_exts.split(",") if e.strip()]
    for extra in ("sqlite", "xml"):
        if extra not in exts:
            exts.append(extra)

    app = {
        "title": "chesspuz",
        "package.name": "chesspuz",
        "package.domain": "org.johncarter",
        "version": args.version,
        "requirements": ",".join(wanted),
        "source.include_exts": ",".join(exts),
        "source.exclude_dirs": "deployment,bin,.buildozer,__pycache__,tests",
        "source.exclude_patterns": "build.log,*.pyc,pysidedeploy.spec,buildozer.spec",
        "orientation": "portrait",
        "fullscreen": "1",
        "icon.filename": "icon.png",
        # the phone's own Android (16 = API 36): Play Protect refuses sideloaded APKs that
        # target an old API; Qt 6.11 needs API 28 at least
        "android.api": "36",
        "android.minapi": "28",
        "android.ndk_api": "28",
        "android.archs": "arm64-v8a",
        "android.accept_sdk_license": "True",
        "android.allow_backup": "True",
        # keep the .py sources: PySide reads class sources back at runtime (auto properties)
        # and tracebacks in logcat show the failing line
        "android.no-byte-compile-python": "True",
        # targetSdk 36 turns on predictive back, which never delivers the Back key to Qt;
        # this attribute (appended to <application>) restores the key flow
        "android.extra_manifest_application_arguments": "./manifest_application_args.xml",
        "android.logcat_filters": "*:S python:D",
        # python-for-android at its last revision that builds CPython 3.11 (the Qt Android
        # wheels link against libpython3.11.so; newer p4a builds 3.14)
        "p4a.branch": "develop",
        "p4a.commit": args.p4a_commit,
    }
    for key, value in app.items():
        text = set_key(text, "app", key, value)
    for key, value in {
        "bin_dir": args.bin_dir,
        "log_level": "2",
        "warn_on_root": "0",
    }.items():
        text = set_key(text, "buildozer", key, value)
    args.spec.write_text(text, encoding="utf-8")
    print(f"patched {args.spec}: version {args.version}, p4a {args.p4a_commit[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
