from pdf2html.analyzer.plate_inserts import is_unnumbered
from pdf2html.utils.types import PageModel, Paragraph, Inline


def test_illustration_without_page_number_is_unnumbered():
    pm = PageModel(page_num=133)
    pm.is_illustration = True
    assert is_unnumbered(pm, 133, {132: 114}) is True


def test_illustration_with_known_page_number_is_not_unnumbered():
    pm = PageModel(page_num=133, book_page_num=115)
    pm.is_illustration = True
    assert is_unnumbered(pm, 133, {132: 114, 133: 115}) is False


def test_blank_without_page_number_is_unnumbered():
    pm = PageModel(page_num=134)
    assert is_unnumbered(pm, 134, {132: 114}) is True


def test_page_with_content_and_known_number_is_not_unnumbered():
    p = Paragraph(inlines=[Inline(text="текст")])
    pm = PageModel(page_num=135, book_page_num=115, blocks=[p])
    assert is_unnumbered(pm, 135, {135: 115}) is False
