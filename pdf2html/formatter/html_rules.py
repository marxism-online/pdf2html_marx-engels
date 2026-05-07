from __future__ import annotations

from ..utils.pagination import page_anchor
from ..utils.types import PageModel
from .jinja_env import env


class HtmlFormatter:
    def __init__(self, page_numbers: dict[int, int] | None = None) -> None:
        self._page_numbers: dict[int, int] = page_numbers or {}
        self._last_pdf_page: int | None = None
        self._last_book_page: int | None = None

    def _resolve_anchor(self, pm: PageModel) -> str:
        if pm.page_num in self._page_numbers:
            book_page = self._page_numbers[pm.page_num]
            self._last_pdf_page = pm.page_num
            self._last_book_page = book_page
            return page_anchor(book_page)
        # Fallback: lazy forward inference for gaps not in the prescan map
        if pm.book_page_num is not None:
            self._last_pdf_page = pm.page_num
            self._last_book_page = pm.book_page_num
            return page_anchor(pm.book_page_num)
        if self._last_book_page is not None:
            inferred = self._last_book_page + (pm.page_num - self._last_pdf_page)
            return page_anchor(inferred)
        return page_anchor(pm.page_num)

    def render_first_page(self, pm: PageModel) -> str:
        tmpl = env.get_template("first_page.html.j2")
        return tmpl.render(pm=pm, anchor=self._resolve_anchor(pm)).strip()

    def render_page(self, pm: PageModel, first: bool = False) -> str:
        tmpl = env.get_template("page.html.j2")
        return tmpl.render(
            pm=pm,
            anchor=self._resolve_anchor(pm),
            nextpage="" if first else "<hr><!--nextpage-->",
        ).strip()