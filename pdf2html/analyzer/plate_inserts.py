from __future__ import annotations

from ..utils.types import PageModel


def is_unnumbered(pm: PageModel, page_no: int, page_numbers: dict[int, int]) -> bool:
    """True if this PDF page has no known printed page number (prescanned or detected)."""
    return page_no not in page_numbers and pm.book_page_num is None


def is_insert_illustration(pm: PageModel, page_no: int, page_numbers: dict[int, int]) -> bool:
    """An illustration page with no printed number - candidate for a plate insert leaf."""
    return pm.is_illustration and is_unnumbered(pm, page_no, page_numbers)


def is_insert_blank(pm: PageModel, page_no: int, page_numbers: dict[int, int]) -> bool:
    """A blank page with no printed number - the verso side of a plate insert leaf."""
    return pm.is_blank and is_unnumbered(pm, page_no, page_numbers)
