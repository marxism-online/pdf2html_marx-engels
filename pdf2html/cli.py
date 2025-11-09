import argparse
from pathlib import Path
from .logging_setup import setup_logging
from .reader.pdf_text import PdfTextReader
from .analyzer.layout import StructureAnalyzer
from .formatter.html_rules import HtmlFormatter

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", help="диапазон, напр. 1-10")
    ap.add_argument("--out", default="out.html")
    args = ap.parse_args()

    setup_logging()

    reader = PdfTextReader()
    analyzer = StructureAnalyzer()
    fmt = HtmlFormatter()

    parts: list[str] = []
    for page_no, layout in reader.iter_pages(args.pdf):
        pm = analyzer.build_page_model(page_no, layout)
        if page_no == 1:
            parts.append(fmt.render_first_page(pm))
        else:
            parts.append(fmt.render_page(pm))

    Path(args.out).write_text("\n".join(parts), encoding="utf-8")

if __name__ == "__main__":
    main()
