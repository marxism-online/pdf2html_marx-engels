from __future__ import annotations

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

        top_title = detect_running_header(text_layer)
        heading = detect_headings(text_layer)
        blocks = detect_paragraphs(text_layer)

        if top_title and blocks:
            blocks = blocks[1:]

        pm = PageModel(
            page_num=page_no,
            top_title=top_title,
            heading=heading,
            blocks=blocks,
            footnote_block=None,
            has_bottom_hr=False,
        )

        detect_quotes(pm)
        return pm