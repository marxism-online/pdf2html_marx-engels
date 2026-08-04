from pdf2html.analyzer.heuristics import detect_quotes, _is_quote_tail
from pdf2html.utils.types import PageModel, Paragraph, Inline


def _para(text: str, is_small: bool = False, align: str = "JUSTIFY") -> Paragraph:
    return Paragraph(inlines=[Inline(text=text)], is_small=is_small, align=align)


class TestDetectQuotes:
    def test_small_justified_becomes_blockquote(self):
        p = _para("«Демократия страны — это значит народ».", is_small=True)
        pm = PageModel(page_num=1, blocks=[p])
        detect_quotes(pm)
        assert pm.blocks[0].is_quote is True
        assert pm.blocks[0].is_small is False

    def test_small_justified_no_quotes_still_blockquote(self):
        # Statistical data in small font — blockquote without guillemets
        p = _para("На 1 января 1849 г. в 590 округах попечительства о бедных — 201644", is_small=True)
        pm = PageModel(page_num=1, blocks=[p])
        detect_quotes(pm)
        assert pm.blocks[0].is_quote is True

    def test_small_justified_ditto_mark_blockquote(self):
        # Ditto marks (») used as abbreviation — still a blockquote (small font)
        p = _para("1849 г. ..................................... на  58910883      »              »", is_small=True)
        pm = PageModel(page_num=1, blocks=[p])
        detect_quotes(pm)
        assert pm.blocks[0].is_quote is True

    def test_small_right_aligned_not_blockquote(self):
        # Date line in small font, right-aligned — not a blockquote
        p = _para("Лондон, вторник, 9 ноября 1852 г.", is_small=True, align="RIGHT")
        pm = PageModel(page_num=1, blocks=[p])
        detect_quotes(pm)
        assert pm.blocks[0].is_quote is False

    def test_normal_size_not_blockquote(self):
        p = _para("Обычный текст основного шрифта.", is_small=False)
        pm = PageModel(page_num=1, blocks=[p])
        detect_quotes(pm)
        assert pm.blocks[0].is_quote is False

    def test_cross_page_quote_tail(self):
        # Продолжение реального blockquote с предыдущей страницы: нет «, но
        # есть закрывающее », и предыдущая страница закончилась внутри цитаты.
        p = _para("пор, пока народ не убедится в необходимости небольшой народной партии в парламенте».")
        pm = PageModel(page_num=1, blocks=[p])
        detect_quotes(pm, prev_quote_open=True)
        assert pm.blocks[0].is_quote is True

    def test_stray_closing_guillemet_without_open_quote_not_promoted(self):
        # Автор сам обрывает предложение с открывающей « в конце обычного
        # (не-blockquote) абзаца перед разрывом страницы; продолжение на
        # следующей странице не должно стать blockquote, если реальной
        # цитаты на предыдущей странице не было.
        p = _para("их имманентная цель, и оно имеет свою силу в том, что индивиды имеют права».")
        pm = PageModel(page_num=1, blocks=[p])
        detect_quotes(pm, prev_quote_open=False)
        assert pm.blocks[0].is_quote is False

    def test_inline_closing_quote_not_tail(self):
        # Закрывающее » есть, но и открывающее « тоже — не хвост, обычный абзац
        p = _para("Он сказал «хорошо», и получил ответ «согласен».")
        pm = PageModel(page_num=1, blocks=[p])
        detect_quotes(pm)
        assert pm.blocks[0].is_quote is False
