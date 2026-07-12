#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
BIN="$HOME/.local/bin"

echo "=== Instalando clasi ==="
echo

# ── 1. Dependencias del sistema ───────────────────────────────────────────────

if command -v pacman &>/dev/null; then
    echo "[1/3] Dependencias del sistema (Arch Linux)..."
    sudo pacman -S --needed python poppler ffmpeg \
        tesseract tesseract-data-spa tesseract-data-eng

elif command -v apt-get &>/dev/null; then
    echo "[1/3] Dependencias del sistema (Debian / Ubuntu / Zorin / Linux Mint)..."
    sudo apt-get update -qq
    sudo apt-get install -y \
        python3 python3-venv \
        poppler-utils ffmpeg \
        tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng

else
    echo "[1/3] Gestor de paquetes no reconocido."
    echo "      Instala manualmente antes de continuar:"
    echo "        python3, python3-venv, pdftotext, pdftoppm, ffprobe, tesseract"
    echo
fi

# ── 2. Entorno virtual + dependencias Python ──────────────────────────────────

echo
echo "[2/3] Creando entorno virtual e instalando dependencias Python..."
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$SCRIPT_DIR"

# ── 3. Comando global ─────────────────────────────────────────────────────────

echo
echo "[3/3] Registrando el comando clasi en ~/.local/bin/..."
mkdir -p "$BIN"
ln -sf "$VENV/bin/clasi" "$BIN/clasi"

# ── Resultado ─────────────────────────────────────────────────────────────────

echo
echo "Instalación completa."
echo

if [[ ":$PATH:" != *":$BIN:"* ]]; then
    echo "  Añade esta línea a tu ~/.bashrc (o ~/.zshrc) para usar clasi desde cualquier terminal:"
    echo
    echo "      export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo
    echo "  Luego ejecuta:  source ~/.bashrc"
    echo "  O cierra y vuelve a abrir la terminal."
    echo
fi

echo "  Prueba:"
echo
echo "      clasi sim ~/Downloads"
echo
