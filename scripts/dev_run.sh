#!/usr/bin/env bash
set -euo pipefail
python -m pdf2html.cli test.pdf --out out.html
