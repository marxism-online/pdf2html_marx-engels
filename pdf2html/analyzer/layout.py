from __future__ import annotations

from pdfminer.layout import LTFigure

from pdf2html.analyzer.heuristics import detect_footnote
from pdf2html.analyzer.heuristics import detect_headings
from pdf2html.analyzer.heuristics import detect_paragraphs
from pdf2html.analyzer.heuristics import detect_quotes
from pdf2html.analyzer.heuristics import detect_running_header
from pdf2html.analyzer.heuristics import detect_signatures
from pdf2html.analyzer.text_extractor import PdfTextExtractor
from pdf2html.utils.types import PageModel


class StructureAnalyzer:
    def __init__(self) -> None:
        self.text_extractor = PdfTextExtractor()

    def build_page_model(self, page_no: int, layout: object) -> PageModel:
        text_layer = self.text_extractor.extract_page_text_layer(page_no, layout)

        header = detect_running_header(text_layer)
        top_title, book_page_num = header if header else (None, None)

        signature_block, sig_top_y, star_footnote = detect_signatures(text_layer)

        footnote_result = detect_footnote(text_layer, sig_top_y=sig_top_y)
        footnote_block, body_min_y, has_bottom_hr = footnote_result if footnote_result else (None, None, False)

        if star_footnote and not footnote_block:
            footnote_block = star_footnote
            has_bottom_hr = True

        if body_min_y is None and sig_top_y is not None:
            body_min_y = sig_top_y

        headings, heading_body_threshold = detect_headings(text_layer)
        if headings:
            blocks = detect_paragraphs(
                text_layer,
                body_min_y=body_min_y,
                heading_body_threshold=heading_body_threshold,
            )
        else:
            blocks = detect_paragraphs(text_layer, body_min_y=body_min_y)
            if top_title and blocks:
                blocks = blocks[1:]

        pm = PageModel(
            page_num=page_no,
            book_page_num=book_page_num,
            top_title=top_title,
            headings=headings,
            blocks=blocks,
            footnote_block=footnote_block,
            has_bottom_hr=has_bottom_hr,
            signature_block=signature_block,
        )

        detect_quotes(pm)

        if any(isinstance(obj, LTFigure) for obj in layout):
            pm.is_illustration = True

        return pm