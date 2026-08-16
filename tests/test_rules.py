from pdf2html.utils.types import PageModel, Paragraph, Inline, Heading
from pdf2html.formatter.html_rules import HtmlFormatter

def test_first_page_anchor_only():
  pm = PageModel(page_num=1, work_title="К. МАРКС<br>и<br>Ф. ЭНГЕЛЬС")
  html = HtmlFormatter().render_first_page(pm)
  assert '<a name="s1">' in html
  assert '<!--nextpage-->' not in html

def test_regular_page_has_nextpage():
  pm = PageModel(page_num=5, headings=[Heading(level=2, text="ЧТО ДЕЛАТЬ?")])
  html = HtmlFormatter().render_page(pm)
  assert '<!--nextpage-->' in html
  assert '<a name="s5">' in html

def test_blockquote_render():
  p = Paragraph(inlines=[Inline(text="цитата")], is_quote=True)
  pm = PageModel(page_num=2, blocks=[p])
  html = HtmlFormatter().render_page(pm)
  assert '<blockquote>' in html

def test_bottom_hr_small():
  p = Paragraph(inlines=[Inline(text="мелкий текст", small=True)])
  pm = PageModel(page_num=3, has_bottom_hr=True, footnote_blocks=[p])
  html = HtmlFormatter().render_page(pm)
  assert 'width:30%' in html and '<small>' in html
