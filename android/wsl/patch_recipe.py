#!/usr/bin/env python
"""Keep only the Qt the app uses in the APK.

pyside6-android-deploy's generated PySide6 recipe unpacks the whole Qt for Python wheel into the
target site-packages and copies every Qt library into the APK's lib folder: 60-odd Qt modules,
ffmpeg, QML, translations, headers, all for an app that needs Core, Gui, Widgets and Svg. That
makes a 200 MB APK, and a few of the unused libraries are not 16 KB-aligned, which Android 15+
flags with a "compatibility" dialog on every debug install.

This appends a pruning step to the recipe (``deployment/recipes/PySide6/__init__.py``) that runs
after its ``build_arch``: it computes the closure of shared-library dependencies from the Qt
modules and plugins in buildozer.spec (``--qt-libs`` / ``--load-local-libs``) with the NDK's
``llvm-readobj``, deletes every other wheel library from the libs folder, and strips the
site-packages copy of PySide6/shiboken6 down to the kept modules. Idempotent (marker comment).
Prints ``patched`` or ``already patched``; wsl/build.sh wipes the generated dist and the
python-installs folder on ``patched`` so the recipe runs again.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MARKER = "# chesspuz: prune unused Qt (wsl/patch_recipe.py)"

PRUNE_CODE = """

{marker}
QT_MODULES = {modules!r}
LOCAL_LIBS = {local_libs!r}


def _chesspuz_needed(readobj, path):
    import subprocess

    out = subprocess.run([readobj, "--needed-libs", str(path)], capture_output=True, text=True)
    names, listing = [], False
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("NeededLibraries"):
            listing = True
        elif listing and line.startswith("lib") and line.endswith(".so"):
            names.append(line)
    return names


def _chesspuz_prune(self, arch):
    import os
    import shutil
    from pathlib import Path

    libs_dir = Path(self.ctx.get_libs_dir(arch.arch))
    site = Path(self.ctx.get_python_install_dir(arch.arch))
    pyside = site / "PySide6"
    shiboken = site / "shiboken6"
    readobj = os.path.join(self.ctx.ndk.llvm_bin_dir, "llvm-readobj")
    suffix = arch.arch

    roots = [f"libQt6{{m}}_{{suffix}}.so" for m in QT_MODULES]
    roots += [f"Qt{{m}}.abi3.so" for m in QT_MODULES]
    roots += [f"lib{{lib}}_{{suffix}}.so" for lib in LOCAL_LIBS]
    roots += ["libpyside6.abi3.so", "libshiboken6.abi3.so", "libc++_shared.so"]
    keep, queue = set(), [name for name in roots if (libs_dir / name).exists()]
    while queue:
        name = queue.pop()
        if name in keep:
            continue
        keep.add(name)
        for dep in _chesspuz_needed(readobj, libs_dir / name):
            if (libs_dir / dep).exists() and dep not in keep:
                queue.append(dep)

    # everything the wheel contributed to the libs folder: Qt/lib (ffmpeg and friends included),
    # plugins, and the PySide6 modules copied next to them
    from_wheel = {{p.name for p in (pyside / "Qt" / "lib").glob("*.so")}}
    from_wheel |= {{p.name for p in libs_dir.glob("libQt6*.so")}}
    from_wheel |= {{p.name for p in libs_dir.glob("libplugins_*.so")}}
    from_wheel |= {{p.name for p in libs_dir.glob("Qt*.abi3.so")}}
    removed = 0
    for name in sorted(from_wheel):
        target = libs_dir / name
        if name not in keep and target.exists():
            target.unlink()
            removed += 1

    # site-packages: the Qt libraries there are never loaded (the APK's lib folder is), nor are
    # headers, QML, translations, type stubs and the modules the app does not import
    for sub in ("include", "typesystems", "glue", "scripts", "jar", "lib", "examples", "QtAsyncio",
                "Qt/lib", "Qt/plugins", "Qt/qml", "Qt/translations", "Qt/libexec", "Qt/resources",
                "Qt/metatypes", "Qt/modules", "Qt/mkspecs"):
        shutil.rmtree(pyside / sub, ignore_errors=True)
    for sub in ("Qt/lib", "Qt/plugins"):
        (pyside / sub).mkdir(parents=True, exist_ok=True)
    for path in list(pyside.glob("*.pyi")) + list(pyside.glob("libpyside6qml*.so")):
        path.unlink()
    for path in pyside.glob("Qt*.abi3.so"):
        module = path.name[2:].split(".", 1)[0]
        if module not in QT_MODULES:
            path.unlink()
    for sub in ("include", "lib", "docs"):
        shutil.rmtree(shiboken / sub, ignore_errors=True)
    for path in shiboken.glob("*.pyi"):
        path.unlink()
    info(f"chesspuz: removed {{removed}} unused wheel libraries from the APK")
    info(f"chesspuz: kept {{sorted(keep)}}")


_chesspuz_build_arch = PySideRecipe.build_arch


def _chesspuz_build_arch_and_prune(self, arch):
    _chesspuz_build_arch(self, arch)
    _chesspuz_prune(self, arch)


PySideRecipe.build_arch = _chesspuz_build_arch_and_prune
"""


def extra_arg(spec_text: str, name: str) -> list[str]:
    """Comma-separated values of ``--<name>=`` inside the spec's ``p4a.extra_args`` line."""
    line = re.search(r"(?m)^p4a\.extra_args\s*=\s*(.*)$", spec_text)
    if not line:
        return []
    match = re.search(r"--" + re.escape(name) + r"=([^\s]*)", line.group(1))
    if not match:
        return []
    return [v for v in match.group(1).split(",") if v]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: patch_recipe.py RECIPE_INIT_PY BUILDOZER_SPEC", file=sys.stderr)
        return 2
    recipe, spec = Path(argv[0]), Path(argv[1])
    if not recipe.exists():
        print(f"missing: {recipe}")
        return 1
    text = recipe.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"already patched: {recipe}")
        return 0
    spec_text = spec.read_text(encoding="utf-8")
    modules = extra_arg(spec_text, "qt-libs")
    local_libs = extra_arg(spec_text, "load-local-libs")
    if not modules:
        print("no --qt-libs in the spec's p4a.extra_args; not patching", file=sys.stderr)
        return 1
    text += PRUNE_CODE.format(marker=MARKER, modules=modules, local_libs=local_libs)
    recipe.write_text(text, encoding="utf-8")
    print(f"patched: {recipe} (modules {modules}, local libs {local_libs})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
