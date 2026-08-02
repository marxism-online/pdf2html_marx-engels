from pdf2html.analyzer.layout import StructureAnalyzer
from pdf2html import pipeline
from pdf2html.pipeline import PageConverter
from pdf2html.utils.types import PageModel, Paragraph, Inline


def _numbered_page(page_no, book_page):
    return PageModel(
        page_num=page_no,
        book_page_num=book_page,
        running_header=("Автор", book_page),
        blocks=[Paragraph(inlines=[Inline(text="текст")])],
    )


def _illustration_page(page_no):
    pm = PageModel(page_num=page_no)
    pm.is_illustration = True
    return pm


def _blank_page(page_no):
    return PageModel(page_num=page_no)


def _feed_all(monkeypatch, converter, pages_by_no):
    monkeypatch.setattr(
        StructureAnalyzer,
        "build_page_model",
        lambda self, page_no, layout: pages_by_no[page_no],
    )
    monkeypatch.setattr(pipeline, "extract_illustration_image", lambda layout: b"fakejpeg")
    for page_no in pages_by_no:
        converter.feed(page_no, layout=None)
    converter.finish()


def test_unnumbered_illustration_and_blank_are_folded_into_previous_page(monkeypatch, tmp_path):
    pages = {
        132: _numbered_page(132, 114),
        133: _illustration_page(133),
        134: _blank_page(134),
        135: _numbered_page(135, 115),
    }
    converter = PageConverter(
        page_numbers={132: 114, 135: 115},
        first_content_page=132,
        volume=8,
        out_dir=tmp_path,
    )
    _feed_all(monkeypatch, converter, pages)

    assert len(converter.parts) == 2
    assert '<a name="s114">' in converter.parts[0]
    assert converter.parts[0].count('<a name="') == 1
    assert '<img align="CENTER" class="illustration" src="08-114.jpg">' in converter.parts[0]
    assert (tmp_path / "08-114.jpg").read_bytes() == b"fakejpeg"

    assert '<a name="s115">' in converter.parts[1]
    assert "illustration" not in converter.parts[1]
    assert "<!--nextpage-->" not in converter.parts[0]
    assert "<!--nextpage-->" in converter.parts[1]


def test_illustration_not_followed_by_blank_renders_standalone(monkeypatch, tmp_path):
    pages = {
        132: _numbered_page(132, 114),
        133: _illustration_page(133),
        134: _numbered_page(134, 115),
    }
    converter = PageConverter(
        page_numbers={132: 114, 134: 115},
        first_content_page=132,
        volume=8,
        out_dir=tmp_path,
    )
    _feed_all(monkeypatch, converter, pages)

    assert len(converter.parts) == 3
    assert '<a name="s114">' in converter.parts[0]
    assert '<img align="CENTER" class="illustration" src="08-115.jpg">' in converter.parts[1]
    assert '<a name="s115">' in converter.parts[2]
