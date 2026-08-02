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


def test_uncounted_insert_is_folded_into_previous_page(monkeypatch, tmp_path):
    # volume08.pdf: pdf114->book90, pdf115 illustration, pdf116 blank, pdf117->book91.
    # 90 + (117-114) = 93 != 91: the 2 unnumbered pages consumed no real page numbers.
    pages = {
        114: _numbered_page(114, 90),
        115: _illustration_page(115),
        116: _blank_page(116),
        117: _numbered_page(117, 91),
    }
    converter = PageConverter(
        page_numbers={114: 90, 117: 91},
        first_content_page=114,
        volume=8,
        out_dir=tmp_path,
    )
    _feed_all(monkeypatch, converter, pages)

    assert len(converter.parts) == 2
    assert '<a name="s90">' in converter.parts[0]
    assert converter.parts[0].count('<a name="') == 1
    assert '<img align="CENTER" class="illustration" src="08-90.jpg">' in converter.parts[0]

    assert '<a name="s91">' in converter.parts[1]
    assert "illustration" not in converter.parts[1]


def test_counted_but_unprinted_insert_keeps_its_own_pages(monkeypatch, tmp_path):
    # volume01.pdf: pdf258->book236, pdf259 illustration, pdf260 blank, pdf261->book239.
    # 236 + (261-258) = 239 == 239: the 2 unnumbered pages DO count (237, 238), they
    # just don't print their number - each must keep its own anchor/pager slot.
    pages = {
        258: _numbered_page(258, 236),
        259: _illustration_page(259),
        260: _blank_page(260),
        261: _numbered_page(261, 239),
    }
    converter = PageConverter(
        page_numbers={258: 236, 261: 239},
        first_content_page=258,
        volume=1,
        out_dir=tmp_path,
    )
    _feed_all(monkeypatch, converter, pages)

    assert len(converter.parts) == 4
    assert '<a name="s236">' in converter.parts[0]
    assert '<a name="s237">' in converter.parts[1]
    assert '<img align="CENTER" class="illustration" src="01-237.jpg">' in converter.parts[1]
    assert '<a name="s238">' in converter.parts[2]
    assert '<a name="s239">' in converter.parts[3]
