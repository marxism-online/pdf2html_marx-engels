#!/usr/bin/env bash
cd "$(dirname "$0")/.."
source .venv/bin/activate
python -m pdf2html.cli test.pdf --out out.html
