#!/usr/bin/env bash
# Build the chesspuz APK inside the WSL build box (run as root by android/sync.py build).
# CP_SRC = the android folder as a WSL path (/mnt/d/...), CP_MODE = debug (default) | clean.
# (Environment variables, not positionals: `wsl -- bash -c script args` drops the args.)
#
# The folder is mirrored into the Linux filesystem first (~/chesspuz-android): builds there are
# fast and python-for-android never sees a path with spaces. Qt's pyside6-android-deploy is run
# once, with --init, to generate the buildozer project (buildozer.spec, the PySide6/shiboken6
# recipes and the Qt .jar files in app/deployment); wsl/patch_spec.py then applies our settings
# (python-for-android pinned to its last CPython 3.11 revision, API 36, portrait, version, ...)
# and plain buildozer builds the APK. The generated files stay in the box between builds; a
# `clean` removes them so the next build regenerates everything.
set -euo pipefail
SRC="${CP_SRC:-${1:-}}"
MODE="${CP_MODE:-${2:-debug}}"
if [ -z "$SRC" ]; then
    echo "CP_SRC (the android folder as a wsl path) is not set"
    exit 2
fi
export PATH="$HOME/.local/bin:$PATH"
WORK="$HOME/chesspuz-android"
VENV="$HOME/chesspuz-venv"
WHEELS="$HOME/wheels"
NDK_DIR="$HOME/.buildozer/android/platform/android-ndk-r28c"
SDK_DIR="$HOME/.buildozer/android/platform/android-sdk"
mkdir -p "$WORK"
rsync -a --delete \
      --exclude 'app/deployment' --exclude 'app/.buildozer' --exclude 'app/buildozer.spec' \
      --exclude 'app/pysidedeploy.spec' --exclude 'app/bin' --exclude 'bin' \
      --exclude 'build.log' --exclude '__pycache__' --exclude '.pytest_cache' \
      "$SRC/" "$WORK/"
find "$WORK" -name '*.sh' -exec sed -i 's/\r$//' {} +
cd "$WORK/app"
if [ "$MODE" = "clean" ]; then
    rm -rf "$WORK/app/.buildozer" "$WORK/app/deployment" "$WORK/app/buildozer.spec" \
           "$WORK/app/pysidedeploy.spec" "$WORK/app/bin" "$WORK/bin"
    echo "== generated buildozer project removed (the SDK/NDK and wheels stay) =="
    exit 0
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
# buildozer asks "running as root, continue?" before a spec exists (the deploy tool's
# `buildozer init`); the environment override answers it
export BUILDOZER_WARN_ON_ROOT=0
PYSIDE_WHL=$(ls "$WHEELS"/pyside6-*-android_aarch64.whl | sort -V | tail -n 1)
SHIBOKEN_WHL=$(ls "$WHEELS"/shiboken6-*-android_aarch64.whl | sort -V | tail -n 1)
if [ ! -f buildozer.spec ] || [ ! -d deployment/recipes/PySide6 ]; then
    echo "== generating the buildozer project with pyside6-android-deploy --init =="
    rm -rf deployment buildozer.spec pysidedeploy.spec
    # the tool's own default config, except that it must not downgrade our buildozer
    DEFAULT_SPEC=$(python -c "import PySide6, pathlib; print(pathlib.Path(PySide6.__file__).parent / 'scripts' / 'deploy_lib' / 'default.spec')")
    sed -e 's/^android_packages = .*/android_packages = buildozer==1.6.0,cython==0.29.37/' \
        "$DEFAULT_SPEC" > pysidedeploy.spec
    NO_INSTALL=""
    if pyside6-android-deploy --help 2>/dev/null | grep -q -- "--no-install"; then
        NO_INSTALL="--no-install"
    fi
    yes y | pyside6-android-deploy --init --keep-deployment-files -f -v $NO_INSTALL \
        --name chesspuz -c pysidedeploy.spec \
        --wheel-pyside "$PYSIDE_WHL" --wheel-shiboken "$SHIBOKEN_WHL" \
        --ndk-path "$NDK_DIR" --sdk-path "$SDK_DIR" \
        --extra-ignore-dirs .buildozer,bin,deployment || true
    if [ ! -f buildozer.spec ] || [ ! -d deployment/recipes/PySide6 ]; then
        echo "== pyside6-android-deploy --init did not produce buildozer.spec + deployment/recipes =="
        exit 3
    fi
fi
python "$WORK/wsl/patch_spec.py" buildozer.spec \
    --version "$(tr -d '\r\n' < "$WORK/VERSION")" \
    --p4a-commit "$(tr -d '\r\n' < "$WORK/wsl/p4a_pin.txt")" \
    --bin-dir "$WORK/bin"
echo "== buildozer.spec (effective, uncommented lines) =="
grep -v -E '^\s*(#|$)' buildozer.spec
mkdir -p "$WORK/bin" "$SRC/bin"
rm -f "$WORK"/bin/*.apk  # only this build's APK gets copied back
echo "== buildozer android debug  (work dir $WORK/app) =="
set +e
buildozer android debug 2>&1 | tee "$WORK/build.log"
STATUS=${PIPESTATUS[0]}
set -e
if [ "$STATUS" -ne 0 ]; then
    echo "== BUILD FAILED (exit $STATUS) - see build.log =="
    exit "$STATUS"
fi
cp -f "$WORK"/bin/*.apk "$SRC/bin/"
echo "== APK(s) copied to $SRC/bin =="
ls -la "$SRC/bin"
