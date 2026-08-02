from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from .analyzer.text_extractor import PdfTextExtractor
from .analyzer.heuristics import detect_running_header
from .logging_setup import setup_logging
from .pipeline import PageConverter
from .reader.pdf_text import PdfTextReader
from .utils.pagination import parse_pages_spec


def _parse_volume(pdf_path: str, volume_arg: int | None) -> int | None:
    if volume_arg is not None:
        return volume_arg
    m = re.search(r"(\d+)", Path(pdf_path).stem)
    return int(m.group(1)) if m else None


def _prescan_page_numbers(pdf_path: str, selected_pages: set[int] | None) -> dict[int, int]:
    """Quick pre-scan: collect Arabic page numbers, infer backward from first numbered page."""
    reader = PdfTextReader()
    ext = PdfTextExtractor()
    known: dict[int, int] = {}

    for page_no, layout in reader.iter_pages(pdf_path, selected_pages=selected_pages):
        tl = ext.extract_page_text_layer(page_no, layout)
        header = detect_running_header(tl)
        if header is not None:
            known[page_no] = header[1]

    if not known:
        return {}

    first_pdf = min(known)
    first_book = known[first_pdf]

    result = dict(known)
    pages = sorted(selected_pages) if selected_pages else list(range(1, first_pdf))
    for pdf_page in reversed([p for p in pages if p < first_pdf]):
        book_page = first_book - (first_pdf - pdf_page)
        if book_page >= 1:
            result[pdf_page] = book_page

    return result


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

    print("Определение нумерации страниц...", end=" ", file=sys.stderr, flush=True)
    page_numbers = _prescan_page_numbers(args.pdf, selected_pages)
    print("готово", file=sys.stderr, flush=True)

    first_content_page = min(page_numbers) if page_numbers else None

    reader = PdfTextReader()
    converter = PageConverter(
        page_numbers=page_numbers,
        first_content_page=first_content_page,
        volume=volume,
        out_dir=out_dir,
    )

    total = len(selected_pages) if selected_pages else None
    done = 0

    for page_no, layout in reader.iter_pages(args.pdf, selected_pages=selected_pages):
        done += 1
        if total:
            pct = done * 100 // total
            print(f"\r[{done}/{total}] стр. {page_no} ({pct}%)", end="", file=sys.stderr)
        else:
            print(f"\rстр. {page_no}", end="", file=sys.stderr)
        converter.feed(page_no, layout)

    converter.finish()
    print(file=sys.stderr)

    out_path = Path(args.out)
    css_src = Path(__file__).parent / "formatter" / "volume.css"
    css_dst = out_path.with_suffix(".css")
    shutil.copy(css_src, css_dst)

    link_tag = f'<link rel="stylesheet" href="{css_dst.name}">'
    out_path.write_text(link_tag + "\n" + "\n".join(converter.parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()