#!/usr/bin/env bash
# One-time setup of the chesspuz Android toolchain inside the WSL build box (the Ubuntu 24.04
# distro "dd-android" on D:, run as root by android/sync.py setup). Digit Defender's setup.sh
# already installed buildozer, the JDK and the Android SDK/NDK there; this adds what Qt's
# deployment tool needs on top. Idempotent: a marker file skips a second run.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export PATH="$HOME/.local/bin:$PATH"
MARK=/root/.chesspuz-setup-done
if [ -f "$MARK" ]; then
    echo "chesspuz toolchain already set up ($(cat "$MARK")) - delete $MARK to redo"
    exit 0
fi
QT_VERSION="${QT_VERSION:-6.11.2}"
QT_PY="cp311"          # the Qt Android wheels are built for CPython 3.11
NDK_DIR="$HOME/.buildozer/android/platform/android-ndk-r28c"
SDK_DIR="$HOME/.buildozer/android/platform/android-sdk"
if [ ! -d "$NDK_DIR" ] || [ ! -d "$SDK_DIR" ]; then
    echo "expected the Android SDK/NDK from the Digit Defender box at $SDK_DIR / $NDK_DIR"
    echo "run  python android\\sync.py setup  in the Digit Defender project first (or a build)"
    exit 2
fi
echo "== apt packages =="
apt-get update
apt-get install -y --no-install-recommends \
    git zip unzip openjdk-17-jdk-headless \
    python3 python3-pip python3-venv python3-setuptools python3-dev \
    autoconf automake libtool libltdl-dev pkg-config zlib1g-dev libncurses-dev cmake \
    libffi-dev libssl-dev build-essential ccache rsync patch curl wget \
    ca-certificates lsb-release file
echo "== uv + Python 3.11 (pyside6-android-deploy refuses to run on 3.12+) =="
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
uv python install 3.11
VENV="$HOME/chesspuz-venv"
[ -x "$VENV/bin/python" ] || uv venv --python 3.11 "$VENV"
# pip itself: uv venvs come without it, and buildozer installs python-for-android's
# requirements with `python -m pip`
uv pip install --python "$VENV/bin/python" pip \
    "pyside6==$QT_VERSION" "buildozer==1.6.0" cython pkginfo jinja2 sh appdirs colorama \
    toml packaging setuptools wheel virtualenv pexpect
# the deploy tool's own extra requirements (tqdm, ...)
ANDROID_REQS=$("$VENV/bin/python" -c "import PySide6, pathlib; print(pathlib.Path(PySide6.__file__).parent / 'scripts' / 'requirements-android.txt')")
[ -f "$ANDROID_REQS" ] && uv pip install --python "$VENV/bin/python" -r "$ANDROID_REQS"
"$VENV/bin/python" -c "import PySide6, buildozer; print('host PySide6', PySide6.__version__, 'buildozer', buildozer.__version__)"
echo "== Qt for Python Android wheels (aarch64) =="
mkdir -p "$HOME/wheels"
cd "$HOME/wheels"
BASE="https://download.qt.io/official_releases/QtForPython"
for whl in "pyside6/pyside6-$QT_VERSION-$QT_VERSION-$QT_PY-$QT_PY-android_aarch64.whl" \
           "shiboken6/shiboken6-$QT_VERSION-$QT_VERSION-$QT_PY-$QT_PY-android_aarch64.whl"; do
    name=$(basename "$whl")
    [ -f "$name" ] || curl -L -o "$name" "$BASE/$whl"
done
ls -la "$HOME/wheels"
date > "$MARK"
echo "== chesspuz toolchain ready =="
