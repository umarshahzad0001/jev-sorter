#!/usr/bin/env bash
# Installs Jev Sorter for the current user. No root needed.
#   ./install.sh              install to ~/.local/opt/JevSorter with a menu entry and a launcher
#   ./install.sh --uninstall  remove all of that (your settings and move history stay)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="$HOME/.local"
APP="$PREFIX/opt/JevSorter"
BIN="$PREFIX/bin/jevsorter-gui"
DESKTOP="$PREFIX/share/applications/jevsorter.desktop"
ICON="$PREFIX/share/icons/hicolor/256x256/apps/jevsorter.png"

if [ "${1:-}" = "--uninstall" ]; then
  rm -rf "$APP" "$BIN" "$DESKTOP" "$ICON" "$HOME/.config/autostart/jevsorter.desktop"
  echo "Jev Sorter removed. Settings and history are still in ~/.local/share/jevsorter."
  exit 0
fi

mkdir -p "$APP" "$PREFIX/bin" "$(dirname "$DESKTOP")" "$(dirname "$ICON")"
cp -R "$HERE"/. "$APP"/
ln -sf "$APP/JevSorter" "$BIN"
cp "$HERE/jevsorter.png" "$ICON"
sed -e "s|@EXEC@|$APP/JevSorter|" -e "s|^Icon=.*|Icon=$ICON|" "$HERE/jevsorter.desktop" > "$DESKTOP"
command -v update-desktop-database >/dev/null && update-desktop-database "$(dirname "$DESKTOP")" || true

echo "Installed. Find Jev Sorter in your applications menu, or run: jevsorter-gui"
case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) echo "Note: $PREFIX/bin is not on your PATH yet." ;; esac
