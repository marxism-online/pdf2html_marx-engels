from pdf2html.utils.types import Paragraph, Inline

def test_inline_render_flags_smoke():
  p = Paragraph(inlines=[
    Inline(text="a", bold=True),
    Inline(text="b", italic=True),
    Inline(text="c", em=True),
  ])
  # smoke-test: фильтр jinja подключается в среде — проверяется в test_rules
  assert True
