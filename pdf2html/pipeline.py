from __future__ import annotations

from pathlib import Path

from .analyzer.image_extractor import extract_illustration_image
from .analyzer.layout import StructureAnalyzer
from .analyzer.plate_inserts import is_unnumbered
from .formatter.html_rules import HtmlFormatter
from .utils.types import PageModel


class PageConverter:
    """Builds PageModels for each PDF page in order and renders them to HTML parts.

    Plates are sometimes printed without a visible page number. Two distinct things
    can be going on when that happens, and they must be told apart:

    1. The page still counts in the book's official pagination - it just doesn't show
       its number (common for full-page illustrations). Once we reach the next page
       with a known number, the numbers add up: last_known_book + pages_in_between
       equals that known number exactly. Render each unnumbered page as its own page,
       same as before - only its printed number is missing, not its place in line.

    2. The page is a physically inserted leaf that was never counted at all (glued
       between two consecutively-numbered pages). Here the numbers DON'T add up: the
       next known page's number is smaller than naive counting would predict, by
       exactly the number of unnumbered pages in between. Giving each of those pages
       its own anchor would create pager slots the book never had, permanently
       offsetting every later page. Instead they are folded into the end of the
       preceding numbered page - an illustration keeps its image, a blank page
       contributes nothing and disappears.

    Runs of unnumbered pages are buffered until a page with a known number is reached,
    at which point the deficit above decides which of the two cases applies.
    """

    def __init__(
        self,
        page_numbers: dict[int, int],
        first_content_page: int | None,
        volume: int | None,
        out_dir: Path,
        body_fontsize_seed: float | None = None,
    ) -> None:
        self._page_numbers = page_numbers
        self._first_content_page = first_content_page
        self._volume = volume
        self._out_dir = out_dir

        self._analyzer = StructureAnalyzer(body_fontsize_seed=body_fontsize_seed)
        self._fmt = HtmlFormatter(page_numbers=page_numbers)

        self.parts: list[str] = []
        self._first_rendered = True
        self._last_known_pdf: int | None = None
        self._last_known_book: int | None = None
        self._buffer: list[tuple[int, object, PageModel]] = []

    def feed(self, page_no: int, layout: object) -> None:
        if self._first_content_page and page_no < self._first_content_page:
            return

        pm = self._analyzer.build_page_model(page_no, layout)

        if is_unnumbered(pm, page_no, self._page_numbers):
            self._buffer.append((page_no, layout, pm))
            return

        known_book = self._page_numbers.get(page_no, pm.book_page_num)
        self._resolve_buffer(page_no, known_book)
        self._last_known_pdf = page_no
        self._last_known_book = known_book
        self._render(pm, page_no)

    def finish(self) -> None:
        # No later known page to compare against - render each buffered page on its own,
        # same as if it had turned out not to be part of an uncounted insert.
        for page_no, layout, pm in self._buffer:
            self._render_standalone(pm, layout, page_no)
        self._buffer = []

    # ------------------------------------------------------------------

    def _resolve_buffer(self, next_page_no: int, next_book: int) -> None:
        if not self._buffer:
            return

        deficit = 0
        if self._last_known_book is not None:
            naive_expected = self._last_known_book + (next_page_no - self._last_known_pdf)
            deficit = naive_expected - next_book

        if deficit == len(self._buffer):
            for _, layout, pm in self._buffer:
                self._merge_insert(pm, layout)
        else:
            for page_no, layout, pm in self._buffer:
                self._render_standalone(pm, layout, page_no)

        self._buffer = []

    def _extract_image(self, layout: object, book_page: int) -> str | None:
        if self._volume is None:
            return None
        img_bytes = extract_illustration_image(layout)
        if not img_bytes:
            return None
        img_name = f"{self._volume:02d}-{book_page}.jpg"
        (self._out_dir / img_name).write_bytes(img_bytes)
        return img_name

    def _standalone_book_page(self, page_no: int) -> int:
        if self._last_known_book is not None:
            return self._last_known_book + (page_no - self._last_known_pdf)
        return page_no

    def _render_standalone(self, pm: PageModel, layout: object, page_no: int) -> None:
        if pm.is_illustration:
            pm.image_src = self._extract_image(layout, self._standalone_book_page(page_no))
        self._render(pm, page_no)

    def _merge_insert(self, pm: PageModel, layout: object) -> None:
        if pm.is_illustration:
            book_page = self._last_known_book if self._last_known_book is not None else pm.page_num
            pm.image_src = self._extract_image(layout, book_page)
            if self.parts:
                self.parts[-1] += "\n" + self._fmt.render_illustration_fragment(pm)

    def _render(self, pm: PageModel, page_no: int) -> None:
        if page_no == 1:
            self.parts.append(self._fmt.render_first_page(pm))
        else:
            self.parts.append(self._fmt.render_page(pm, first=self._first_rendered))
        self._first_rendered = False
