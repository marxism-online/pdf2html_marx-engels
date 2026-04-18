#!/usr/bin/env bash

set -euo pipefail

# === НАСТРОЙКИ ===
# Укажи путь к корню проекта
PROJECT_DIR="/home/alex/pdf2html_project"

# Куда складывать архив
OUTPUT_DIR="$HOME"

# Имя архива
ARCHIVE_NAME="pdf2html_project_$(date +%Y-%m-%d_%H-%M-%S).zip"

# === ПРОВЕРКИ ===
if [[ ! -d "$PROJECT_DIR" ]]; then
    echo "Ошибка: каталог проекта не найден: $PROJECT_DIR"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

ARCHIVE_PATH="$OUTPUT_DIR/$ARCHIVE_NAME"

echo "Каталог проекта: $PROJECT_DIR"
echo "Архив будет создан: $ARCHIVE_PATH"

# === УПАКОВКА ===
cd "$(dirname "$PROJECT_DIR")"
PROJECT_BASENAME="$(basename "$PROJECT_DIR")"

zip -r "$ARCHIVE_PATH" "$PROJECT_BASENAME" \
    -x "*/.git/*" \
    -x "*/.venv/*" \
    -x "*/venv/*" \
    -x "*/__pycache__/*" \
    -x "*/.pytest_cache/*" \
    -x "*/.mypy_cache/*" \
    -x "*/.ruff_cache/*" \
    -x "*/.idea/*" \
    -x "*/.vscode/*" \
    -x "*/build/*" \
    -x "*/dist/*" \
    -x "*/htmlcov/*" \
    -x "*/.coverage" \
    -x "*/.DS_Store" \
    -x "*/node_modules/*" \
    -x "*/tmp/*" \
    -x "*/temp/*" \
    -x "*/*.pyc" \
    -x "*/*.pyo"

echo "Готово."
echo "Архив создан: $ARCHIVE_PATH"
