from __future__ import annotations

from pathlib import Path

from .analyzer.image_extractor import extract_illustration_image
from .analyzer.layout import StructureAnalyzer
from .analyzer.plate_inserts import is_insert_blank, is_insert_illustration
from .formatter.html_rules import HtmlFormatter
from .utils.types import PageModel


class PageConverter:
    """Builds PageModels for each PDF page in order and renders them to HTML parts.

    Some plates are printed on an unnumbered inserted leaf: an illustration with no
    printed page number, followed by a blank verso side also with no printed number.
    Rendering each as its own page would give the leaf two pager slots it never had
    in the book, permanently offsetting every later page's slot from its printed
    number. Such a pair is folded into the end of the preceding numbered page instead -
    the image gets no anchor or page break of its own, and the blank leaf is dropped.
    See analyzer.plate_inserts for the detection rules.
    """

    def __init__(
        self,
        page_numbers: dict[int, int],
        first_content_page: int | None,
        volume: int | None,
        out_dir: Path,
    ) -> None:
        self._page_numbers = page_numbers
        self._first_content_page = first_content_page
        self._volume = volume
        self._out_dir = out_dir

        self._analyzer = StructureAnalyzer()
        self._fmt = HtmlFormatter(page_numbers=page_numbers)

        self.parts: list[str] = []
        self._first_rendered = True
        self._last_known_pdf: int | None = None
        self._last_known_book: int | None = None
        self._pending: tuple[int, object, PageModel] | None = None

    def feed(self, page_no: int, layout: object) -> None:
        if self._first_content_page and page_no < self._first_content_page:
            return

        pm = self._analyzer.build_page_model(page_no, layout)

        # Resolve any pending illustration using last_known_* as of the page BEFORE
        # this one - the current page's own number must not leak into that lookup.
        if self._pending is not None:
            p_page_no, p_layout, p_pm = self._pending
            self._pending = None
            if is_insert_blank(pm, page_no, self._page_numbers):
                self._merge_insert(p_pm, p_layout)
                return
            self._emit_illustration(p_pm, p_layout, p_page_no)

        if page_no in self._page_numbers:
            self._last_known_pdf = page_no
            self._last_known_book = self._page_numbers[page_no]

        if is_insert_illustration(pm, page_no, self._page_numbers):
            self._pending = (page_no, layout, pm)
            return

        if pm.is_illustration:
            pm.image_src = self._extract_image(layout, self._standalone_book_page(page_no))
        self._render(pm, page_no)

    def finish(self) -> None:
        if self._pending is not None:
            page_no, layout, pm = self._pending
            self._pending = None
            self._emit_illustration(pm, layout, page_no)

    # ------------------------------------------------------------------

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

    def _emit_illustration(self, pm: PageModel, layout: object, page_no: int) -> None:
        pm.image_src = self._extract_image(layout, self._standalone_book_page(page_no))
        self._render(pm, page_no)

    def _merge_insert(self, pm: PageModel, layout: object) -> None:
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
