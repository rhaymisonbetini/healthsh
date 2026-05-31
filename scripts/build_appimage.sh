#!/bin/bash
# Build the Healthsh AppImage end to end.
#
# Pipeline:
#   1. PyInstaller bundles healthsh/app.py and its deps into dist/healthsh/
#   2. The PyInstaller output is copied into packaging/healthsh.AppDir/usr/bin/
#   3. appimagetool packages the AppDir into a single AppImage in dist/
#
# Requirements:
#   - Python 3.11+ with healthsh installed in editable mode (.venv/bin/pip install -e .[build])
#   - FUSE for appimagetool (or run with --appimage-extract-and-run)
#   - scripts/appimagetool present (download from
#     https://github.com/AppImage/AppImageKit/releases — see README)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APPDIR="${REPO_ROOT}/packaging/healthsh.AppDir"
DIST="${REPO_ROOT}/dist"
PY="${REPO_ROOT}/.venv/bin/python"
PYINSTALLER="${REPO_ROOT}/.venv/bin/pyinstaller"
APPIMAGETOOL="${REPO_ROOT}/scripts/appimagetool"
VERSION="$("${PY}" -c "import healthsh; print(healthsh.__version__)")"
ARCH="x86_64"
OUTPUT="${DIST}/Healthsh-${VERSION}-${ARCH}.AppImage"

if [ ! -x "${PYINSTALLER}" ]; then
    echo "pyinstaller is missing. Run: ${REPO_ROOT}/.venv/bin/pip install -e .[build]" >&2
    exit 1
fi

if [ ! -x "${APPIMAGETOOL}" ]; then
    echo "appimagetool is missing. Download into scripts/ from:" >&2
    echo "  https://github.com/AppImage/AppImageKit/releases/latest" >&2
    exit 1
fi

echo "==> Cleaning previous artifacts"
rm -rf "${APPDIR}/usr/bin" "${REPO_ROOT}/build" "${REPO_ROOT}/dist/healthsh"
mkdir -p "${APPDIR}/usr/bin"

echo "==> Running PyInstaller"
cd "${REPO_ROOT}"
"${PYINSTALLER}" \
    --name healthsh \
    --windowed \
    --onedir \
    --noconfirm \
    --clean \
    --distpath "${DIST}" \
    --workpath "${REPO_ROOT}/build" \
    --collect-data healthsh \
    healthsh/app.py

echo "==> Staging into AppDir"
cp -a "${DIST}/healthsh/." "${APPDIR}/usr/bin/"

echo "==> Building AppImage"
mkdir -p "${DIST}"
export ARCH
if ! "${APPIMAGETOOL}" --no-appstream "${APPDIR}" "${OUTPUT}" 2>&1; then
    echo "==> Retrying appimagetool via --appimage-extract-and-run (FUSE fallback)"
    "${APPIMAGETOOL}" --appimage-extract-and-run --no-appstream "${APPDIR}" "${OUTPUT}"
fi

echo "==> Done"
ls -lh "${OUTPUT}"
