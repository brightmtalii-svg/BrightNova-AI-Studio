#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPLICATIONS="$HOME/.local/share/applications"
TARGET="$APPLICATIONS/brightnova-ai-studio.desktop"

mkdir -p "$APPLICATIONS"
cat > "$TARGET" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=BrightNova AI Studio
GenericName=Local AI Development Studio
Comment=Build Locally. Think Beyond.
Exec=$ROOT/run.sh
TryExec=$ROOT/run.sh
Path=$ROOT
Icon=$ROOT/assets/icons/logo.svg
Terminal=false
StartupNotify=true
StartupWMClass=BrightNova AI Studio
Categories=Development;IDE;Utility;
Keywords=AI;Ollama;OpenCode;Python;Coding;
DESKTOP

chmod +x "$TARGET" "$ROOT/run.sh"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS" >/dev/null 2>&1 || true
fi
printf '%s\n' "Installed BrightNova AI Studio at $TARGET"
