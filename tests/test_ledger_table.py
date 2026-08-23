from pdf2html.analyzer.ledger_table import LedgerTable
from pdf2html.analyzer.ledger_table import extract_ledger_tables
from pdf2html.utils.text_layer import TextLine
from pdf2html.utils.text_layer import TextSpan

BODY_X0 = 56.7


def _line(text: str, x0: float, y0: float, x1: float, height: float = 10.0) -> TextLine:
    span = TextSpan(text=text, x0=x0, y0=y0, x1=x1, y1=y0 + height, fontsize=12.0)
    return TextLine(spans=[span], x0=x0, y0=y0, x1=x1, y1=y0 + height)


class TestLedgerTableExtraction:
    def test_wage_breakdown_table(self):
        # Mirrors volume 1, p. 195 (PDF p. 215): a label/value ledger table
        # with a multi-line label, a fused dot-leader+value row, and an
        # "Итого" total that should get an auto-inserted divider above it.
        lines = [
            _line("то получим следующий результат:", BODY_X0, 251.1, 312.5),
            _line("Валовой доход .......................... 53 тал. 21 зильбергрош 6 пф.", 99.2, 227.8, 246.8),
            _line("Общая сумма расходов, не", 99.2, 204.6, 213.4),
            _line("включая статей 13, 14", 113.4, 187.3, 207.0),
            _line("и 17 ....................................... 39 » 5 » — »", 113.4, 170.1, 436.8),
            _line("Итого чистый доход............ 14 тал. 16 збгр. 6 пф.».", 99.2, 146.8, 265.5),
            _line("Возражение правления Общества: «Расчёт сам по себе верен", BODY_X0, 123.6, 400.0),
        ]

        items, found, notes = extract_ledger_tables(lines, BODY_X0, page_no=215)

        assert found is True
        # The introductory sentence stays out of the table, as its own line.
        assert items[0] is lines[0]
        table = items[1]
        assert isinstance(table, LedgerTable)
        assert len(table.rows) == 4  # Валовой, Общая сумма, divider, Итого

        labels = [" ".join(p.inlines[0].text for p in row.label) for row in table.rows]
        assert labels[0] == "Валовой доход"
        assert labels[1] == "Общая сумма расходов, не включая статей 13, 14 и 17"
        assert table.rows[2].value is None  # auto-inserted divider before "Итого"
        assert labels[3] == "Итого чистый доход"

        values = [row.value.inlines[0].text if row.value else None for row in table.rows]
        assert values[0] == "53 тал. 21 зильбергрош 6 пф."
        assert values[1] == "39 » 5 » — »"
        assert values[3] == "14 тал. 16 збгр. 6 пф.»."

        # The trailing sentence after the table is untouched.
        assert items[-1] is lines[-1]

    def test_table_of_contents_entries(self):
        # Mirrors volume 1, p. 696 (PDF p. 720): consecutive dot-leader
        # entries with no gap between them merge into one table, and a
        # hyphen-wrapped title ("...ФЕЙЕР-" / "БАХОМ") rejoins correctly.
        lines = [
            _line("Предисловие ко второму изданию................... V — IX", BODY_X0, 569.6, 400.0),
            _line("ЛЮТЕР КАК ТРЕТЕЙСКИЙ СУДЬЯ МЕЖДУ ШТРАУСОМ И ФЕЙЕР-", BODY_X0, 454.4, 400.0),
            _line("БАХОМ .............................................. 28 — 29", BODY_X0, 440.6, 452.6),
        ]

        items, found, notes = extract_ledger_tables(lines, BODY_X0, page_no=720)

        assert found is True
        assert len(items) == 1
        table = items[0]
        assert isinstance(table, LedgerTable)
        assert len(table.rows) == 2
        labels = [" ".join(p.inlines[0].text for p in row.label) for row in table.rows]
        assert labels[0] == "Предисловие ко второму изданию"
        assert labels[1] == "ЛЮТЕР КАК ТРЕТЕЙСКИЙ СУДЬЯ МЕЖДУ ШТРАУСОМ И ФЕЙЕРБАХОМ"

    def test_heading_before_dot_leader_stays_out_of_table(self):
        # A centered mid-page heading right before a table-of-contents
        # section must not be swallowed as that section's first label line.
        lines = [
            _line("Предисловие ко второму изданию................... V — IX", BODY_X0, 569.6, 400.0),
            _line("К. МАРКС (1842 — 1844)", 229.3, 511.9, 400.0),
            _line("ЗАМЕТКИ О НОВЕЙШЕЙ ПРУССКОЙ ЦЕНЗУРНОЙ ИНСТРУКЦИИ.......... 3 — 27", BODY_X0, 480.2, 492.2),
        ]

        items, found, notes = extract_ledger_tables(lines, BODY_X0, page_no=720)

        assert found is True
        # heading line is untouched, sitting between two table blocks
        assert items[1] is lines[1]
        assert isinstance(items[0], LedgerTable)
        assert isinstance(items[2], LedgerTable)
        labels = [" ".join(p.inlines[0].text for p in row.label) for row in items[2].rows]
        assert labels == ["ЗАМЕТКИ О НОВЕЙШЕЙ ПРУССКОЙ ЦЕНЗУРНОЙ ИНСТРУКЦИИ"]

    def test_no_dot_leader_no_table(self):
        lines = [
            _line("Обычный абзац без каких-либо точек-заполнителей.", BODY_X0, 700.0, 400.0),
            _line("И многоточие в конце предложения... тоже не триггерит.", BODY_X0, 680.0, 400.0),
        ]

        items, found, notes = extract_ledger_tables(lines, BODY_X0, page_no=1)

        assert found is False
        assert items == lines

    def test_empty_value_bails_out(self, capsys):
        # A dot-leader with nothing after it can't be split into label/value
        # confidently — must fall back to plain lines and warn, not guess.
        lines = [_line("Название раздела ......................", BODY_X0, 500.0, 400.0)]

        items, found, notes = extract_ledger_tables(lines, BODY_X0, page_no=42)

        assert found is False
        assert items == lines
        assert len(notes) == 1
        assert "42" in notes[0]
        err = capsys.readouterr().err.lower()
        assert "стр" in err and "42" in err
