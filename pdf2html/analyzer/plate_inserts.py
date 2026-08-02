from __future__ import annotations

from ..utils.types import PageModel


def is_unnumbered(pm: PageModel, page_no: int, page_numbers: dict[int, int]) -> bool:
    """True if this PDF page has no known printed page number (prescanned or detected).

    Plates are sometimes printed without a visible page number, either because the
    number was omitted for that one page (it still counts in the book's pagination -
    see PageConverter's deficit check) or because the inserted leaf was never counted
    at all (a physical insert glued between two consecutively numbered pages).
    """
    return page_no not in page_numbers and pm.book_page_num is None
