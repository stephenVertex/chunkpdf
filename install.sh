#!/usr/bin/env bash
# Install chunkpdf as a globally accessible command via symlink in ~/.local/bin
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/chunkpdf.py"
BIN_DIR="$HOME/.local/bin"
LINK="$BIN_DIR/chunkpdf"

chmod +x "$TARGET"
mkdir -p "$BIN_DIR"
ln -sfn "$TARGET" "$LINK"

echo "Installed: $LINK -> $TARGET"
if ! command -v chunkpdf >/dev/null 2>&1; then
  echo "Note: $BIN_DIR is not on your PATH. Add it to your shell config."
fi
