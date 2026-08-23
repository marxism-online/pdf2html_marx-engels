from __future__ import annotations

import re
import sys

from pdf2html.utils.text_layer import TextLine
from pdf2html.utils.types import Inline
from pdf2html.utils.types import LedgerRow
from pdf2html.utils.types import LedgerTable
from pdf2html.utils.types import Paragraph

# 4+ consecutive dots: a dot-leader between a label and a value (e.g. a wage
# breakdown or a table-of-contents entry). Deliberately narrow — a plain
# ellipsis ("...") never trips it, and a full-volume scan of the reference
# corpus found this pattern only on genuine table/contents pages, never in
# ordinary prose.
_DOT_LEADER_RE = re.compile(r"\.{4,}")

_TOTAL_KEYWORDS_RE = re.compile(r"^(итого|итог|всего)\b", re.IGNORECASE)

# How many plain (non-dot-leader) single-fragment lines before/after a
# dot-leader row can be a wrapped continuation of its label — e.g. a
# multi-line caption like "Общая сумма расходов, не / включая статей 13, 14"
# before the line that finally carries the dot-leader and value.
_MAX_LABEL_LOOKAROUND = 4


def _row_text(row: list[TextLine]) -> str:
    """Reassemble a physical row's fragments in left-to-right reading order.

    pdfminer's own internal ordering within a text block is not reliably
    x-sorted when a line is this widely split (dot-leader columns land in
    separate spans/lines) — verified on page 215 of volume 1, where the
    fragments came out in an arbitrary, non-x-sorted order.
    """
    joined = " ".join(
        line.text.strip() for line in sorted(row, key=lambda line: line.x0) if line.text.strip()
    )
    return re.sub(r"\s+", " ", joined)


def _group_table_rows(lines: list[TextLine]) -> list[list[TextLine]]:
    """Cluster lines into physical rows by y-overlap against the row's first
    line, with no cap on fragment count per row.

    Unlike heuristics._group_rows (which only ever pairs up to two lines,
    by design — see its docstring), a dot-leader row can fragment into many
    x-separated pieces (label+first value, then each unit/amount as its own
    piece), so this needs to keep absorbing same-y fragments regardless of
    count. Only used to *detect* ledger regions; lines outside a detected
    region still flow through the ordinary (more conservative) pipeline.
    """
    rows: list[list[TextLine]] = []
    for line in lines:
        if rows and min(rows[-1][0].y1, line.y1) - max(rows[-1][0].y0, line.y0) > 0:
            rows[-1].append(line)
        else:
            rows.append([line])
    return rows


# A caption continuation line is expected to be indented relative to the
# body's left margin by a modest, hanging-indent amount (e.g. "Общая сумма
# расходов, не" / "включая статей 13, 14" at x0 ~99-113 vs a body_x0 of
# 56.7 — a 40-60pt shift) — ordinary paragraph text always starts flush at
# body_x0. This is what lets the backward lookaround tell a genuine caption
# apart from the tail of an unrelated paragraph that happens to end in a
# short, single-fragment line (e.g. "...то получим следующий результат:",
# introducing the table on page 215 of volume 1). The upper bound matters
# too: a *centered* mid-page heading (e.g. a "К. МАРКС (1842-1844)" section
# divider inside a table of contents) can land at a much larger x0 than any
# hanging indent would, and must not be mistaken for one.
_CAPTION_INDENT_MIN = 20.0
_CAPTION_INDENT_MAX = 100.0


def _continues_by_hyphen(rows: list[list[TextLine]], idx: int) -> bool:
    """True if rows[idx]'s text ends in a genuine word-wrap hyphen (not a
    dash abbreviation) — an unambiguous continuation signal independent of
    indentation, e.g. a table-of-contents title split as "...ФЕЙЕР-" /
    "БАХОМ ..... 28 — 29", where both lines sit flush at the body margin.
    """
    from pdf2html.analyzer.heuristics import _ends_with_hyphen_wrap
    from pdf2html.analyzer.heuristics import _is_hyphen_abbreviation
    from pdf2html.analyzer.heuristics import _leading_word
    from pdf2html.analyzer.heuristics import _trailing_word

    text = rows[idx][-1].text.strip()
    if not _ends_with_hyphen_wrap(text):
        return False
    prefix_word = _trailing_word(text[:-1])
    suffix_word = _leading_word(_row_text(rows[idx + 1]))
    return not _is_hyphen_abbreviation(prefix_word, suffix_word)


def _is_caption_continuation(rows: list[list[TextLine]], idx: int, body_x0: float) -> bool:
    """True if rows[idx] is either indented like a caption's hanging
    continuation, or a genuine wrap-hyphen join to its neighbor — the two
    ways a short non-dot-leader line can legitimately belong to a caption.
    Anything else (flush-left ordinary prose, or a centered heading that
    happens to land inside the indent range) is not one.
    """
    x0 = rows[idx][0].x0
    if body_x0 + _CAPTION_INDENT_MIN < x0 < body_x0 + _CAPTION_INDENT_MAX:
        return True
    return _continues_by_hyphen(rows, idx)


def _backward_caption_lookback(
    rows: list[list[TextLine]], dot_flags: list[bool], start_idx: int, min_start: int, body_x0: float
) -> int:
    """How far back rows[start_idx]'s label extends: keep walking backward
    while each candidate line is a caption continuation. Stops at the first
    line that's neither — almost always the wrapped tail of an unrelated,
    flush-left paragraph (e.g. "...то получим следующий результат:"
    introducing the table on page 215 of volume 1).
    """
    j = start_idx - 1
    steps = 0
    while (
        j >= min_start
        and not dot_flags[j]
        and len(rows[j]) == 1
        and steps < _MAX_LABEL_LOOKAROUND
        and _is_caption_continuation(rows, j, body_x0)
    ):
        start_idx = j
        j -= 1
        steps += 1
    return start_idx


def _find_ledger_regions(rows: list[list[TextLine]], body_x0: float) -> dict[int, int]:
    """Maps a ledger region's start row-index to its exclusive end index.

    A region is a maximal run of dot-leader rows, each optionally preceded
    by short single-fragment label-continuation rows (a caption wrapped
    across 2-3 physical lines before the line that finally carries the
    dot-leader) and chained to further dot-leader rows the same way.
    """
    dot_flags = [bool(_DOT_LEADER_RE.search(_row_text(row))) for row in rows]
    regions: dict[int, int] = {}
    n = len(rows)
    i = 0
    min_start = 0
    while i < n:
        if not dot_flags[i]:
            i += 1
            continue

        start = _backward_caption_lookback(rows, dot_flags, i, min_start, body_x0)

        end = i + 1
        while end < n:
            if dot_flags[end]:
                end += 1
                continue
            k = end
            steps = 0
            while (
                k < n
                and not dot_flags[k]
                and len(rows[k]) == 1
                and steps < _MAX_LABEL_LOOKAROUND
                and _is_caption_continuation(rows, k, body_x0)
            ):
                k += 1
                steps += 1
            if k < n and dot_flags[k]:
                end = k + 1
            else:
                break

        regions[start] = end
        min_start = end
        i = end

    return regions


def _label_paragraphs(raw_lines: list[str]) -> list[Paragraph]:
    """One Paragraph per visual line of a label, joined by <br> in the
    template — except a wrap-hyphen at the end of a line, which merges into
    the next (a genuine word-wrap, not a caption line break).

    Lazily imported from heuristics to reuse the exact same hyphen/
    abbreviation judgment call already applied to ordinary body paragraphs
    (see the "г-на"/"Ге-гель" fix) — a table caption deserves the same rule,
    not a second copy of it.
    """
    from pdf2html.analyzer.heuristics import _ends_with_hyphen_wrap
    from pdf2html.analyzer.heuristics import _is_hyphen_abbreviation
    from pdf2html.analyzer.heuristics import _leading_word
    from pdf2html.analyzer.heuristics import _trailing_word

    merged: list[str] = []
    for raw in raw_lines:
        line = raw.strip()
        if not line:
            continue
        if merged and _ends_with_hyphen_wrap(merged[-1]):
            prefix_word = _trailing_word(merged[-1][:-1])
            suffix_word = _leading_word(line)
            if _is_hyphen_abbreviation(prefix_word, suffix_word):
                merged[-1] = f"{merged[-1]} {line}"
            else:
                merged[-1] = merged[-1][:-1] + line
        else:
            merged.append(line)

    return [Paragraph(inlines=[Inline(text=m)]) for m in merged]


def _insert_total_dividers(rows: list[LedgerRow]) -> None:
    """Auto-insert a bare <hr> divider row above a row whose label starts
    with "Итого"/"Итог"/"Всего" — the standard Russian ledger convention for
    a sum line, and the one case this module infers without a real drawn
    line in the PDF (the vector graphics aren't extracted at all; see
    ledger_table module discussion). Skipped for a table's very first row.
    """
    i = 1
    while i < len(rows):
        label_text = "".join(p.inlines[0].text for p in rows[i].label)
        if _TOTAL_KEYWORDS_RE.match(label_text.strip()) and rows[i - 1].value is not None:
            rows.insert(i, LedgerRow(label=[Paragraph(inlines=[Inline(text=" ")])], value=None))
            i += 1
        i += 1


def _build_ledger_table(
    rows: list[list[TextLine]], page_no: int | None
) -> tuple[LedgerTable | None, str | None]:
    ledger_rows: list[LedgerRow] = []
    label_buffer: list[str] = []

    for row in rows:
        text = _row_text(row)
        m = _DOT_LEADER_RE.search(text)
        if not m:
            label_buffer.append(text)
            continue

        label_part = text[: m.start()].strip()
        value_part = text[m.end() :].strip()
        if not value_part:
            # The dot-leader signal fired but nothing followed it — our
            # label/value split assumption doesn't hold here. Bail on the
            # whole region rather than guess; the caller falls back to
            # rendering these lines as ordinary paragraphs.
            note = (
                f"Страница {page_no}: похоже на таблицу с точками-заполнителями, "
                f"но не удалось разобрать строку со значением: {text!r} — проверьте вручную."
            )
            print(note, file=sys.stderr)
            return None, note

        raw_label_lines = label_buffer + ([label_part] if label_part else [])
        ledger_rows.append(LedgerRow(
            label=_label_paragraphs(raw_label_lines),
            value=Paragraph(inlines=[Inline(text=value_part)]),
        ))
        label_buffer = []

    if label_buffer:
        # Trailing label-only lines with no value ever showed up — same
        # bail-out reasoning as above.
        note = (
            f"Страница {page_no}: похоже на таблицу с точками-заполнителями, "
            f"но остался неприкреплённый текст подписи: {' / '.join(label_buffer)!r} — "
            "проверьте вручную."
        )
        print(note, file=sys.stderr)
        return None, note

    _insert_total_dividers(ledger_rows)
    return LedgerTable(rows=ledger_rows), None


def extract_ledger_tables(
    lines: list[TextLine], body_x0: float, page_no: int | None = None
) -> tuple[list[TextLine | LedgerTable], bool, list[str]]:
    """Split a page's body lines into a sequence of plain TextLines and
    detected LedgerTable blocks, in original reading order.

    Returns (items, any_table_found, notes). Lines belonging to a region
    that failed to parse confidently are returned unchanged (as plain
    TextLines) so they still go through the ordinary paragraph pipeline,
    and a note describing the failure is added to `notes` — see
    _build_ledger_table's bail-out cases. Callers should surface these
    notes (e.g. in a log next to the output file) since automatic table
    detection is a best effort, not a guarantee.
    """
    rows = _group_table_rows(lines)
    regions = _find_ledger_regions(rows, body_x0)
    if not regions:
        return list(lines), False, []

    items: list[TextLine | LedgerTable] = []
    notes: list[str] = []
    found_any = False
    row_idx = 0
    while row_idx < len(rows):
        end = regions.get(row_idx)
        if end is None:
            items.extend(rows[row_idx])
            row_idx += 1
            continue
        table, note = _build_ledger_table(rows[row_idx:end], page_no)
        if table is not None:
            items.append(table)
            found_any = True
        else:
            for row in rows[row_idx:end]:
                items.extend(row)
            if note is not None:
                notes.append(note)
        row_idx = end

    return items, found_any, notes
