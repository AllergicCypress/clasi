#!/usr/bin/env bash
# install.sh — configura clasi en Arch Linux, Debian, Ubuntu, Zorin y Linux Mint.
#
# Qué hace:
#   1. Instala las herramientas del sistema (poppler, ffmpeg, tesseract) via el
#      gestor de paquetes de la distribución.
#   2. Crea un entorno virtual Python en .venv/ e instala todas las dependencias
#      Python de clasi dentro de él (click, rich, mutagen, Pillow, pytesseract…).
#   3. Registra el comando 'clasi' en ~/.local/bin/ mediante un symlink al
#      ejecutable del entorno virtual. No es necesario activar el entorno virtual
#      manualmente en ningún momento.
#   4. Verifica que las herramientas del sistema estén disponibles y avisa si
#      falta alguna.
#
# Uso:
#   git clone https://github.com/AllergicCypress/clasi.git
#   cd clasi
#   ./install.sh
#
# Para reinstalar o actualizar, vuelve a ejecutar ./install.sh.
# Los pasos son idempotentes: no reinstala lo que ya está instalado.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
BIN="$HOME/.local/bin"

echo "=== Instalando clasi ==="
echo

# ── 1. Dependencias del sistema ───────────────────────────────────────────────

if command -v pacman &>/dev/null; then
    echo "[1/4] Dependencias del sistema (Arch Linux)..."
    sudo pacman -S --needed python poppler ffmpeg \
        tesseract tesseract-data-spa tesseract-data-eng

elif command -v apt-get &>/dev/null; then
    echo "[1/4] Dependencias del sistema (Debian / Ubuntu / Zorin / Linux Mint)..."
    sudo apt-get update -qq
    sudo apt-get install -y \
        python3 python3-venv \
        poppler-utils ffmpeg \
        tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng

else
    echo "[1/4] Gestor de paquetes no reconocido (no es pacman ni apt)."
    echo "      Instala estas herramientas manualmente antes de continuar:"
    echo
    echo "        pdftotext   — extracción de texto de PDF    (paquete: poppler / poppler-utils)"
    echo "        tesseract   — OCR para PDFs escaneados e imágenes"
    echo "        ffprobe     — metadatos de audio y video    (paquete: ffmpeg)"
    echo
    echo "      Continuando con la instalación de Python..."
    echo
fi

# ── 2. Entorno virtual + dependencias Python ──────────────────────────────────

echo
echo "[2/4] Creando entorno virtual e instalando dependencias Python..."
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$SCRIPT_DIR"

# ── 3. Comando global ─────────────────────────────────────────────────────────

echo
echo "[3/4] Registrando el comando clasi en ~/.local/bin/..."
mkdir -p "$BIN"
ln -sf "$VENV/bin/clasi" "$BIN/clasi"

# ── 4. Verificación de herramientas del sistema ───────────────────────────────

echo
echo "[4/4] Verificando herramientas del sistema..."

declare -A TOOL_DESC=(
    [pdftotext]="extracción de texto de PDF"
    [tesseract]="OCR (PDFs escaneados e imágenes)"
    [ffprobe]="metadatos de audio y video"
)

MISSING=()
for tool in pdftotext tesseract ffprobe; do
    if command -v "$tool" &>/dev/null; then
        echo "        ✓ $tool"
    else
        echo "        ✗ $tool  — ${TOOL_DESC[$tool]}"
        MISSING+=("$tool")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo
    echo "  Advertencia: faltan herramientas del sistema."
    echo "  clasi está instalado, pero no podrá procesar algunos tipos de archivo"
    echo "  hasta que estén disponibles."
    echo "  Instálalas con tu gestor de paquetes y vuelve a ejecutar ./install.sh."
fi

# ── Resultado ─────────────────────────────────────────────────────────────────

echo
echo "Instalación completa."
echo

if [[ ":$PATH:" != *":$BIN:"* ]]; then
    echo "  ~/.local/bin no está en tu PATH."
    echo "  Añade esta línea a tu ~/.bashrc (o ~/.zshrc):"
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
