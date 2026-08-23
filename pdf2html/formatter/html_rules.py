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
            nextpage="" if first else "<!--nextpage-->",
        ).strip()

    def render_ledger_table_fragment(self, table) -> str:
        """Renders a single LedgerTable's <table>...</table> on its own —
        used to log every detected dot-leader table next to the output file
        for manual review (the automatic column layout is a best effort,
        not always a good visual match for the PDF's real columns).
        """
        tmpl = env.get_template("ledger_table_fragment.html.j2")
        return tmpl.render(p=table).strip()

    def render_illustration_fragment(self, pm: PageModel) -> str:
        """Renders an illustration's image/caption without its own anchor or page break.

        Used to fold an unnumbered plate insert into the end of the preceding page
        instead of giving it its own pager slot (see is_insert_illustration).
        """
        tmpl = env.get_template("illustration_fragment.html.j2")
        return tmpl.render(pm=pm).strip()