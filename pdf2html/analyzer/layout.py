from __future__ import annotations

from pdfminer.layout import LTFigure

from pdf2html.analyzer.heuristics import apply_quote_continuation
from pdf2html.analyzer.heuristics import detect_footnote
from pdf2html.analyzer.heuristics import detect_headings
from pdf2html.analyzer.heuristics import detect_opening_signature
from pdf2html.analyzer.heuristics import detect_paragraphs
from pdf2html.analyzer.heuristics import detect_quotes
from pdf2html.analyzer.heuristics import detect_running_header
from pdf2html.analyzer.heuristics import detect_signatures
from pdf2html.analyzer.heuristics import quote_is_open_at_page_end
from pdf2html.analyzer.text_extractor import PdfTextExtractor
from pdf2html.utils.types import Heading
from pdf2html.utils.types import PageModel


class StructureAnalyzer:
    def __init__(self, body_fontsize_seed: float | None = None) -> None:
        """body_fontsize_seed: initial cross-page body-fontsize reference, from a
        whole-document pre-scan. Without it the reference starts at None and is
        built up page by page from whatever the requested --pages range happens
        to contain — if that range starts inside a long quoted passage (smaller
        font than the surrounding narrative), the reference stays pinned to the
        quote's size and same-size in-article subheadings get misclassified as
        main (H2) instead of sub (H3) headings until enough real body text is seen.
        """
        self.text_extractor = PdfTextExtractor()
        self._prev_quote_open: bool = False
        self._body_fontsize: float | None = body_fontsize_seed

    def build_page_model(self, page_no: int, layout: object) -> PageModel:
        text_layer = self.text_extractor.extract_page_text_layer(page_no, layout)

        header = detect_running_header(text_layer)
        book_page_num = header[1] if header else None

        running_header_min_y: float | None = None
        if header:
            visible = [l for l in text_layer.lines if l.text.strip()]
            if visible:
                running_header_min_y = visible[0].y0

        # Snapshot the cross-page reference before this page can update it below —
        # detect_headings/detect_opening_signature must judge this page's own font
        # sizes against what came BEFORE it, not against themselves.
        body_fontsize_ref = self._body_fontsize

        heading_blocks, heading_body_threshold = detect_headings(
            text_layer, body_fontsize_ref=body_fontsize_ref
        )
        headings = [item for item in heading_blocks if isinstance(item, Heading)]

        # Track body font size across pages using the 75th percentile.
        # Exclude heading and running-header areas so that large title fonts on cover
        # pages do not inflate the reference and cause all body text to appear "small".
        # Only update when the current page is body-dominated (percentile stays high);
        # quote-heavy pages have a depressed percentile and must NOT pull the reference down.
        page_sizes = sorted(
            s.fontsize
            for l in text_layer.lines
            for s in l.spans
            if s.fontsize
            and (heading_body_threshold is None or l.y0 < heading_body_threshold)
            and (running_header_min_y is None or l.y0 < running_header_min_y)
        )
        if page_sizes:
            page_p75 = page_sizes[int(len(page_sizes) * 0.75)]
            if self._body_fontsize is None or page_p75 > self._body_fontsize * 0.95:
                self._body_fontsize = page_p75

        signature_block, sig_top_y, star_footnotes = detect_signatures(
            text_layer, heading_body_threshold=heading_body_threshold
        )

        footnote_result = detect_footnote(text_layer, sig_top_y=sig_top_y)
        footnote_blocks, body_min_y, has_bottom_hr = footnote_result if footnote_result else ([], None, False)

        if star_footnotes and not footnote_blocks:
            footnote_blocks = star_footnotes
            has_bottom_hr = True

        if body_min_y is None and sig_top_y is not None:
            body_min_y = sig_top_y

        # A work-opening title page (heading followed only by a small italic
        # "Написано .../Печатается по ..." two-column note) renders as its own
        # block, not the regular paragraph flow — see detect_opening_signature.
        opening_signature = (
            detect_opening_signature(text_layer, heading_body_threshold, body_fontsize_ref=body_fontsize_ref)
            if headings else None
        )

        if opening_signature is not None:
            blocks = []
        elif headings:
            blocks = detect_paragraphs(
                text_layer,
                body_min_y=body_min_y,
                heading_body_threshold=heading_body_threshold,
                body_fontsize_ref=self._body_fontsize,
                running_header_min_y=running_header_min_y,
            )
        else:
            blocks = detect_paragraphs(
                text_layer,
                body_min_y=body_min_y,
                body_fontsize_ref=self._body_fontsize,
                running_header_min_y=running_header_min_y,
            )

        pm = PageModel(
            page_num=page_no,
            book_page_num=book_page_num,
            running_header=header,
            headings=headings,
            heading_blocks=heading_blocks,
            blocks=blocks,
            footnote_blocks=footnote_blocks,
            has_bottom_hr=has_bottom_hr,
            signature_block=signature_block,
            opening_signature=opening_signature,
        )

        # apply_quote_continuation must run before detect_quotes (uses raw is_small).
        apply_quote_continuation(pm, self._prev_quote_open)
        detect_quotes(pm, prev_quote_open=self._prev_quote_open)
        self._prev_quote_open = quote_is_open_at_page_end(pm)

        if any(isinstance(obj, LTFigure) for obj in layout):
            pm.is_illustration = True

        return pm