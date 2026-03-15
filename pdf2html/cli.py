from __future__ import annotations

import argparse
from pathlib import Path

from .analyzer.layout import StructureAnalyzer
from .formatter.html_rules import HtmlFormatter
from .logging_setup import setup_logging
from .reader.pdf_text import PdfTextReader
from .utils.pagination import parse_pages_spec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", help='диапазон, напр. "1-10" или "1,3,7-9"')
    ap.add_argument("--out", default="out.html")
    args = ap.parse_args()

    try:
        selected_pages = parse_pages_spec(args.pages)
    except ValueError as exc:
        raise SystemExit(f"Invalid --pages value: {exc}") from exc

    setup_logging()

    reader = PdfTextReader()
    analyzer = StructureAnalyzer()
    fmt = HtmlFormatter()

    parts: list[str] = []

    for page_no, layout in reader.iter_pages(args.pdf, selected_pages=selected_pages):
        pm = analyzer.build_page_model(page_no, layout)
        if page_no == 1:
            parts.append(fmt.render_first_page(pm))
        else:
            parts.append(fmt.render_page(pm))

    Path(args.out).write_text("\n".join(parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()