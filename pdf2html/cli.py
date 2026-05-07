from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .analyzer.image_extractor import extract_illustration_image
from .analyzer.layout import StructureAnalyzer
from .formatter.html_rules import HtmlFormatter
from .logging_setup import setup_logging
from .reader.pdf_text import PdfTextReader
from .utils.pagination import parse_pages_spec


def _parse_volume(pdf_path: str, volume_arg: int | None) -> int | None:
    if volume_arg is not None:
        return volume_arg
    m = re.search(r"(\d+)", Path(pdf_path).stem)
    return int(m.group(1)) if m else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", help='диапазон, напр. "1-10" или "1,3,7-9"')
    ap.add_argument("--out", default="out.html")
    ap.add_argument("--volume", type=int, default=None, help="номер тома для именования иллюстраций")
    args = ap.parse_args()

    try:
        selected_pages = parse_pages_spec(args.pages)
    except ValueError as exc:
        raise SystemExit(f"Invalid --pages value: {exc}") from exc

    setup_logging()

    volume = _parse_volume(args.pdf, args.volume)
    out_dir = Path(args.out).parent

    reader = PdfTextReader()
    analyzer = StructureAnalyzer()
    fmt = HtmlFormatter()

    parts: list[str] = []
    total = len(selected_pages) if selected_pages else None
    done = 0
    last_pdf_page: int | None = None
    last_book_page: int | None = None

    for page_no, layout in reader.iter_pages(args.pdf, selected_pages=selected_pages):
        done += 1
        if total:
            pct = done * 100 // total
            print(f"\r[{done}/{total}] стр. {page_no} ({pct}%)", end="", file=sys.stderr)
        else:
            print(f"\rстр. {page_no}", end="", file=sys.stderr)

        pm = analyzer.build_page_model(page_no, layout)

        if pm.book_page_num is not None:
            last_pdf_page = page_no
            last_book_page = pm.book_page_num

        if pm.is_illustration:
            img_bytes = extract_illustration_image(layout)
            if img_bytes and volume is not None:
                if pm.book_page_num is not None:
                    book_page = pm.book_page_num
                elif last_book_page is not None:
                    book_page = last_book_page + (page_no - last_pdf_page)
                else:
                    book_page = page_no
                img_name = f"{volume:02d}-{book_page}.jpg"
                (out_dir / img_name).write_bytes(img_bytes)
                pm.image_src = img_name

        if page_no == 1:
            parts.append(fmt.render_first_page(pm))
        else:
            parts.append(fmt.render_page(pm))

    print(file=sys.stderr)
    Path(args.out).write_text("\n".join(parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()