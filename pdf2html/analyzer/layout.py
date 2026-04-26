from __future__ import annotations

from pdf2html.analyzer.heuristics import detect_footnote
from pdf2html.analyzer.heuristics import detect_headings
from pdf2html.analyzer.heuristics import detect_paragraphs
from pdf2html.analyzer.heuristics import detect_quotes
from pdf2html.analyzer.heuristics import detect_running_header
from pdf2html.analyzer.text_extractor import PdfTextExtractor
from pdf2html.utils.types import PageModel


class StructureAnalyzer:
    def __init__(self) -> None:
        self.text_extractor = PdfTextExtractor()

    def build_page_model(self, page_no: int, layout: object) -> PageModel:
        text_layer = self.text_extractor.extract_page_text_layer(page_no, layout)

        header = detect_running_header(text_layer)
        top_title, book_page_num = header if header else (None, None)

        footnote_result = detect_footnote(text_layer)
        footnote_block, body_min_y, has_bottom_hr = footnote_result if footnote_result else (None, None, False)

        heading = detect_headings(text_layer)
        blocks = detect_paragraphs(text_layer, body_min_y=body_min_y)

        if top_title and blocks:
            blocks = blocks[1:]

        pm = PageModel(
            page_num=page_no,
            book_page_num=book_page_num,
            top_title=top_title,
            heading=heading,
            blocks=blocks,
            footnote_block=footnote_block,
            has_bottom_hr=has_bottom_hr,
        )

        detect_quotes(pm)
        return pm