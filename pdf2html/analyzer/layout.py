from __future__ import annotations

from pdfminer.layout import LTFigure

from pdf2html.analyzer.heuristics import apply_quote_continuation
from pdf2html.analyzer.heuristics import detect_footnote
from pdf2html.analyzer.heuristics import detect_headings
from pdf2html.analyzer.heuristics import detect_paragraphs
from pdf2html.analyzer.heuristics import detect_quotes
from pdf2html.analyzer.heuristics import detect_running_header
from pdf2html.analyzer.heuristics import detect_signatures
from pdf2html.analyzer.heuristics import quote_is_open_at_page_end
from pdf2html.analyzer.text_extractor import PdfTextExtractor
from pdf2html.utils.types import Heading
from pdf2html.utils.types import PageModel


class StructureAnalyzer:
    def __init__(self) -> None:
        self.text_extractor = PdfTextExtractor()
        self._prev_quote_open: bool = False
        self._body_fontsize: float | None = None

    def build_page_model(self, page_no: int, layout: object) -> PageModel:
        text_layer = self.text_extractor.extract_page_text_layer(page_no, layout)

        header = detect_running_header(text_layer)
        book_page_num = header[1] if header else None

        # Running header is always body text — use its font size as cross-page reference.
        if header is not None:
            first_line = next((l for l in text_layer.lines if l.text.strip()), None)
            if first_line and first_line.avg_fontsize:
                self._body_fontsize = first_line.avg_fontsize

        heading_blocks, heading_body_threshold = detect_headings(text_layer)
        headings = [item for item in heading_blocks if isinstance(item, Heading)]

        signature_block, sig_top_y, star_footnote = detect_signatures(
            text_layer, heading_body_threshold=heading_body_threshold
        )

        footnote_result = detect_footnote(text_layer, sig_top_y=sig_top_y)
        footnote_block, body_min_y, has_bottom_hr = footnote_result if footnote_result else (None, None, False)

        if star_footnote and not footnote_block:
            footnote_block = star_footnote
            has_bottom_hr = True

        if body_min_y is None and sig_top_y is not None:
            body_min_y = sig_top_y
        if headings:
            blocks = detect_paragraphs(
                text_layer,
                body_min_y=body_min_y,
                heading_body_threshold=heading_body_threshold,
                body_fontsize_ref=self._body_fontsize,
            )
        else:
            blocks = detect_paragraphs(
                text_layer,
                body_min_y=body_min_y,
                body_fontsize_ref=self._body_fontsize,
            )
            if header and blocks:
                blocks = blocks[1:]

        pm = PageModel(
            page_num=page_no,
            book_page_num=book_page_num,
            running_header=header,
            headings=headings,
            heading_blocks=heading_blocks,
            blocks=blocks,
            footnote_block=footnote_block,
            has_bottom_hr=has_bottom_hr,
            signature_block=signature_block,
        )

        # apply_quote_continuation must run before detect_quotes (uses raw is_small).
        apply_quote_continuation(pm, self._prev_quote_open)
        detect_quotes(pm)
        self._prev_quote_open = quote_is_open_at_page_end(pm)

        if any(isinstance(obj, LTFigure) for obj in layout):
            pm.is_illustration = True

        return pm