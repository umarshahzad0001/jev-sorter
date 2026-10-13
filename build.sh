#!/usr/bin/env bash
# Builds the macOS .dmg or the Linux .tar.gz into dist/. Run it on the OS you are building for
# (PyInstaller cannot cross-compile). On Windows use build.ps1.
# Needs: python3 with tkinter, then  python3 -m pip install customtkinter pillow keyring pyinstaller
# plus pystray on Linux (macOS has no tray icon, so the macOS build leaves it out).
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
ARCH=$(uname -m)

export JEVSORTER_NO_KEYRING=1   # a CI keychain may be locked; the self-tests cover the vault-free path
"$PY" jevsorter.py selftest | tail -1
"$PY" jevsorter_settings.py
"$PY" jevsorter_tray.py
"$PY" jevsorter_presets.py

rm -rf build/gui dist
COMMON=(--noconfirm --clean --windowed --name JevSorter --workpath build/gui --specpath build/gui
        --add-data "$PWD/assets:assets" --add-data "$PWD/jevsorter.png:." --add-data "$PWD/jevsorter.ico:."
        --add-data "$PWD/licenses:licenses" --add-data "$PWD/LICENSE:." --add-data "$PWD/THIRD_PARTY_NOTICES.md:."
        --collect-data customtkinter --collect-all keyring)

case "$(uname -s)" in
  Darwin)
    "$PY" -m PyInstaller "${COMMON[@]}" --exclude-module pystray --icon "$PWD/jevsorter.icns" \
        --osx-bundle-identifier com.umarca.jevsorter "$PWD/jevsorter_gui.py"
    rm -rf build/dmg && mkdir -p build/dmg
    cp -R dist/JevSorter.app build/dmg/
    cp -R LICENSE THIRD_PARTY_NOTICES.md licenses build/dmg/
    ln -s /Applications build/dmg/Applications
    hdiutil create -volname "Jev Sorter" -srcfolder build/dmg -ov -format UDZO \
        "dist/JevSorter-$VERSION-macos-$ARCH.dmg"
    ;;
  Linux)
    "$PY" -m PyInstaller "${COMMON[@]}" "$PWD/jevsorter_gui.py"
    cp packaging/linux/install.sh packaging/linux/jevsorter.desktop jevsorter.png dist/JevSorter/
    cp -R LICENSE THIRD_PARTY_NOTICES.md licenses dist/JevSorter/
    chmod +x dist/JevSorter/install.sh
    tar -czf "dist/JevSorter-$VERSION-linux-$ARCH.tar.gz" -C dist JevSorter
    ;;
  *)
    echo "Unsupported system. Use build.ps1 on Windows." >&2
    exit 1
    ;;
esac

ls -lh dist/JevSorter-*
