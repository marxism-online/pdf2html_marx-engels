from pdf2html.analyzer.plate_inserts import is_insert_blank, is_insert_illustration
from pdf2html.utils.types import PageModel, Paragraph, Inline


def test_illustration_without_page_number_is_insert_candidate():
    pm = PageModel(page_num=133)
    pm.is_illustration = True
    assert is_insert_illustration(pm, 133, {132: 114}) is True


def test_illustration_with_known_page_number_is_not_insert_candidate():
    pm = PageModel(page_num=133, book_page_num=115)
    pm.is_illustration = True
    assert is_insert_illustration(pm, 133, {132: 114, 133: 115}) is False


def test_blank_without_page_number_is_insert_blank():
    pm = PageModel(page_num=134)
    assert is_insert_blank(pm, 134, {132: 114}) is True


def test_page_with_content_is_not_insert_blank():
    p = Paragraph(inlines=[Inline(text="текст")])
    pm = PageModel(page_num=135, book_page_num=115, blocks=[p])
    assert is_insert_blank(pm, 135, {135: 115}) is False
