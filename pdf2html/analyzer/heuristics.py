from __future__ import annotations

import re

from pdf2html.analyzer.ledger_table import LedgerTable
from pdf2html.analyzer.ledger_table import extract_ledger_tables
from pdf2html.utils.text_layer import PageTextLayer
from pdf2html.utils.text_layer import TextLine
from pdf2html.utils.text_layer import TextSpan
from pdf2html.utils.types import Heading
from pdf2html.utils.types import Inline
from pdf2html.utils.types import PageModel
from pdf2html.utils.types import Paragraph
from pdf2html.utils.types import SignatureBlock
from pdf2html.utils.types import TwoColumnBlock

# Паттерн: текст, 5+ пробелов, затем число (арабское или римское)
_RUNNING_HEADER_RE = re.compile(
    r'^(.+?)\s{5,}(\d+|[IVXLCDM]{1,8})\s*$'
)

# Паттерн: строка — только номер страницы, без имени автора
_LONE_PAGE_NUM_RE = re.compile(r'^\s*(\d+)\s*$')


def detect_running_header(text_layer: PageTextLayer) -> tuple[str, int] | None:
    lines = [line for line in text_layer.lines if line.text.strip()]
    if not lines:
        return None
    m = _RUNNING_HEADER_RE.match(lines[0].text)
    if m:
        text_part = m.group(1).strip()
        num_part = m.group(2)
        if not num_part.isdigit():
            return None
        return text_part, int(num_part)
    m2 = _LONE_PAGE_NUM_RE.match(lines[0].text)
    if m2:
        num = int(m2.group(1))
        return "", num
    return None


_CENTERING_TOLERANCE = 30.0  # pts


def _is_all_caps_line(text: str) -> bool:
    """True if all alphabetic words longer than 1 char are uppercase.
    Single-char words (conjunctions/prepositions like 'и', 'в') are ignored.
    """
    words = re.findall(r'[а-яёА-ЯЁa-zA-Z]+', text)
    long_words = [w for w in words if len(w) > 1]
    return bool(long_words) and all(w == w.upper() for w in long_words)


def _is_bold_font(fontname: str | None) -> bool:
    if not fontname:
        return False
    return "bold" in fontname.lower()


def _line_is_bold(line: TextLine) -> bool:
    return any(_is_bold_font(s.fontname) for s in line.spans)


def _line_is_italic(line: TextLine) -> bool:
    return any(_is_italic_font(s.fontname) for s in line.spans)


def _line_is_red(line: TextLine) -> bool:
    for span in line.spans:
        c = span.color
        if isinstance(c, tuple) and len(c) >= 3 and c[0] > 0.8 and c[1] < 0.2 and c[2] < 0.2:
            return True
    return False


def detect_headings(
    text_layer: PageTextLayer,
    body_fontsize_ref: float | None = None,
) -> tuple[list[Heading], float | None, list[Paragraph]]:
    """Return (headings, heading_body_threshold, subtitle_paras).

    heading_body_threshold is the minimum y0 of detected heading lines.
    detect_paragraphs should skip lines with y0 >= this value.
    subtitle_paras: small-font non-alphabetic lines (e.g. year ranges) that
    were attached to the heading block but should render as centered paragraphs.
    """
    lines = sorted(
        [l for l in text_layer.lines if l.text.strip()],
        key=lambda l: -l.y0,
    )
    if not lines:
        return [], None

    # Skip running header (first line if it matches the header pattern)
    start = 1 if (_RUNNING_HEADER_RE.match(lines[0].text) or _LONE_PAGE_NUM_RE.match(lines[0].text)) else 0

    heading_lines: list[TextLine] = []
    all_sup_textlines: list[TextLine] = []   # for heading_body_threshold
    line_sups: dict[int, list[str]] = {}     # heading_line_index → inline sup texts
    pending: list[tuple[TextLine, str]] = [] # digit-only lines not yet assigned
    # Center is established from the first heading line — not assumed to be the
    # page center. This handles title pages where the block sits right-of-center.
    expected_center: float | None = None

    def _flush_pending(idx: int) -> None:
        if pending:
            line_sups[idx] = [s for _, s in pending]
            all_sup_textlines.extend(tl for tl, _ in pending)
            pending.clear()

    for line in lines[start:]:
        text = line.text.strip()
        if not any(c.isalpha() for c in text):
            if text.isdigit():
                # Digit-only line: defer to the next alphabetic heading line.
                pending.append((line, text))
            else:
                # Non-numeric decorators (e.g. "———") join the heading if centered.
                if expected_center is not None:
                    line_center = (line.x0 + line.x1) / 2
                    if abs(line_center - expected_center) <= _CENTERING_TOLERANCE:
                        heading_lines.append(line)
            continue
        if not _is_all_caps_line(text):
            # Allow single-char connectors ("и", "в") if centered between heading lines.
            words = re.findall(r'[а-яёА-ЯЁa-zA-Z]+', text)
            if words and all(len(w) == 1 for w in words) and expected_center is not None:
                line_center = (line.x0 + line.x1) / 2
                if abs(line_center - expected_center) <= _CENTERING_TOLERANCE:
                    heading_lines.append(line)
                    _flush_pending(len(heading_lines) - 1)
                    continue
            break
        if _line_is_italic(line):
            break
        line_center = (line.x0 + line.x1) / 2
        if expected_center is None:
            expected_center = line_center
        elif abs(line_center - expected_center) > _CENTERING_TOLERANCE:
            break
        heading_lines.append(line)
        _flush_pending(len(heading_lines) - 1)

    # Digit-only lines that came after all heading text become trailing sups.
    trailing_sup_texts = [s for _, s in pending]
    all_sup_textlines.extend(tl for tl, _ in pending)

    if not heading_lines:
        return [], None

    # Some title pages typeset the heading block noticeably right of the true
    # page center (binding-margin quirk in the source PDF). Flag it so the
    # template can nudge it right instead of dead-centering it like the rest.
    offset_right = (
        expected_center is not None
        and (expected_center - text_layer.width / 2) > _CENTERING_TOLERANCE * 2
    )

    main_size = heading_lines[0].avg_fontsize if heading_lines else None
    # Tier reference for main/sub classification below: prefer the known cross-page
    # body fontsize over the block's own first line. An isolated in-article subheading
    # that happens to land at the top of a page (no full-size title above it) would
    # otherwise be compared to itself and misclassified as a "main" (H2) title.
    tier_ref = body_fontsize_ref if body_fontsize_ref is not None else main_size

    all_heading_lines = heading_lines + all_sup_textlines
    heading_body_threshold = min(l.y0 for l in all_heading_lines)

    _DASH_SEP_RE = re.compile(r'^[—–\-\s]+$')
    _HR = '<hr class="heading-hr">'

    def _is_subtitle(line: TextLine) -> bool:
        """Non-alphabetic line whose font is much smaller than the main heading."""
        return (
            main_size is not None
            and line.avg_fontsize is not None
            and line.avg_fontsize < main_size * 0.75
            and not any(c.isalpha() for c in line.text.strip())
        )

    def _render_group(key: tuple[bool, str], group: list[TextLine]) -> Heading | Paragraph:
        is_bold, size_cat = key
        # Split on dash-separator lines; join rendered segments with <hr>.
        segs: list[list[TextLine]] = [[]]
        for gl in group:
            if _DASH_SEP_RE.match(gl.text.strip()):
                segs.append([])
            else:
                segs[-1].append(gl)
        segs = [s for s in segs if s]
        seg_strs: list[str] = []
        for seg in segs:
            line_strs: list[str] = []
            for gl in seg:
                lt = gl.text.strip()
                for s in line_sups.get(heading_lines.index(gl), []):
                    lt += f"<sup>{s}</sup>"
                line_strs.append(lt)
            seg_strs.append("<br>".join(line_strs))
        text = _HR.join(seg_strs)
        if is_bold:
            text = f"<b>{text}</b>"
            alpha_lines = [gl for gl in group if any(c.isalpha() for c in gl.text)]
            level = 3 if size_cat == "sub" else (1 if (alpha_lines and _line_is_red(alpha_lines[0])) else 2)
            return Heading(level=level, text=text, align="CENTER", offset_right=offset_right)
        return Paragraph(inlines=[Inline(text=text)], align="CENTER")

    heading_blocks: list = []
    current_key: tuple[bool, str] | None = None
    current_group: list[TextLine] = []

    for line in heading_lines:
        text = line.text.strip()

        if _is_subtitle(line):
            if current_group:
                heading_blocks.append(_render_group(current_key, current_group))
                current_key, current_group = None, []
            lt = text
            for s in line_sups.get(heading_lines.index(line), []):
                lt += f"<sup>{s}</sup>"
            inlines = _lines_to_inlines_br([line]) or [Inline(text=lt)]
            heading_blocks.append(Paragraph(inlines=inlines, align="CENTER"))
            continue

        is_alpha = any(c.isalpha() for c in text)
        if not is_alpha:
            if current_group:
                current_group.append(line)
            continue

        is_bold = _line_is_bold(line)
        size_cat = (
            "main" if tier_ref is None or line.avg_fontsize is None
            or line.avg_fontsize >= tier_ref * 0.9
            else "sub"
        )
        key: tuple[bool, str] = (is_bold, size_cat)

        if current_key is not None and current_key != key:
            heading_blocks.append(_render_group(current_key, current_group))
            current_group = []

        current_key = key
        current_group.append(line)

    if current_group:
        heading_blocks.append(_render_group(current_key, current_group))

    if trailing_sup_texts and heading_blocks:
        last = heading_blocks[-1]
        if isinstance(last, Heading):
            last.text += "".join(f"<sup>{s}</sup>" for s in trailing_sup_texts)
        elif isinstance(last, Paragraph) and last.inlines:
            last.inlines[-1].text += "".join(f"<sup>{s}</sup>" for s in trailing_sup_texts)

    return heading_blocks, heading_body_threshold


def detect_signatures(
    text_layer: PageTextLayer,
    heading_body_threshold: float | None = None,
) -> tuple[SignatureBlock | None, float | None, list[Paragraph]]:
    """Detect two-column article signatures at bottom of page.

    Returns (SignatureBlock, sig_top_y, star_footnotes).
    star_footnotes: editorial '*'-footnote paragraphs found below the signature block, one per marker.
    sig_top_y is the y1 of the topmost signature line, used to limit footnote detection.
    heading_body_threshold: lines at or above this y0 belong to the heading — skip them.
    """
    lines = [line for line in text_layer.lines if line.text.strip()]
    if heading_body_threshold is not None:
        lines = [l for l in lines if l.y0 < heading_body_threshold]
    if not lines:
        return None, None, []

    all_sizes = [l.avg_fontsize for l in lines if l.avg_fontsize is not None]
    if not all_sizes:
        return None, None, []
    all_sizes.sort()
    main_size = all_sizes[int(len(all_sizes) * 0.9)]
    small_threshold = main_size * 0.85

    sorted_asc = sorted(lines, key=lambda l: l.y0)  # bottom-first
    all_small: list[TextLine] = []
    for line in sorted_asc:
        fs = line.avg_fontsize
        if fs is not None and fs <= small_threshold:
            all_small.append(line)
        else:
            break

    if not all_small:
        return None, None, []

    # Separate '*' editorial footnote lines at the very bottom.
    # Collect the entire contiguous block of star lines, then verify they are
    # separated from the remaining small lines (signature) by a meaningful gap.
    star_lines: list[TextLine] = []
    small_lines = list(all_small)  # bottom-first
    while small_lines and small_lines[0].text.strip().startswith("*"):
        star_lines.append(small_lines.pop(0))
    if star_lines and small_lines:
        # gap between top of star block and bottom of the line just above it
        gap = small_lines[0].y0 - star_lines[-1].y1
        if gap <= 20:
            small_lines = star_lines + small_lines
            star_lines = []

    star_paras: list[Paragraph] = []
    if star_lines:
        star_lines.sort(key=lambda l: -l.y0)
        for group in _split_footnote_entries(star_lines):
            inlines = _lines_to_inlines(group)
            if inlines:
                star_paras.append(Paragraph(inlines=inlines, align="LEFT"))

    if not small_lines:
        return None, None, star_paras

    small_lines.sort(key=lambda l: -l.y0)  # reading order
    if small_lines[0].text.strip().startswith("*"):
        return None, None, star_paras  # remaining lines are also footnote

    # Reject if any small line is too wide to be a column in a two-column layout
    text_width = max((l.x1 for l in lines), default=0.0) - min((l.x0 for l in lines), default=0.0)
    if text_width > 0 and max(l.x1 - l.x0 for l in small_lines) > text_width * 0.55:
        return None, None, star_paras

    page_center = text_layer.width / 2
    left_lines = [l for l in small_lines if (l.x0 + l.x1) / 2 < page_center]
    right_lines = [l for l in small_lines if (l.x0 + l.x1) / 2 >= page_center]

    sig_top_y = max(l.y1 for l in small_lines)

    if not left_lines or not right_lines:
        return SignatureBlock(
            left=_group_sig_lines(left_lines) if left_lines else [],
            right=_group_sig_lines(right_lines) if right_lines else [],
        ), sig_top_y, star_paras

    return SignatureBlock(
        left=_group_sig_lines(left_lines),
        right=_group_sig_lines(right_lines),
    ), sig_top_y, star_paras


def detect_opening_signature(
    text_layer: PageTextLayer,
    heading_body_threshold: float | None,
    body_fontsize_ref: float | None = None,
) -> SignatureBlock | None:
    """Detect the small italic two-column dedication block that opens a major
    work right under its title (e.g. "Написано К. Марксом летом 1843 г." /
    "Печатается по рукописи"), typeset with a large blank gap below the
    heading and nothing else on the page. Mirrors detect_signatures' left/right
    column split, but for the top of a page instead of the bottom.

    Italic alone isn't enough: some short works (e.g. "ЗАЯВЛЕНИЕ") set their
    entire body text in italic at normal body size. Also require the lines to
    be small relative to body_fontsize_ref, matching the actual dedication
    block's font (~9pt vs ~12pt body) and excluding italicized body text.
    """
    if heading_body_threshold is None:
        return None
    lines = [l for l in text_layer.lines if l.text.strip() and l.y0 < heading_body_threshold]
    if len(lines) < 2 or not all(_line_is_italic(l) for l in lines):
        return None
    if body_fontsize_ref is not None:
        small_threshold = body_fontsize_ref * 0.85
        if not all(l.avg_fontsize is not None and l.avg_fontsize <= small_threshold for l in lines):
            return None

    page_center = text_layer.width / 2
    left_lines = [l for l in lines if (l.x0 + l.x1) / 2 < page_center]
    right_lines = [l for l in lines if (l.x0 + l.x1) / 2 >= page_center]
    if not left_lines and not right_lines:
        return None

    return SignatureBlock(
        left=_group_sig_lines(left_lines) if left_lines else [],
        right=_group_sig_lines(right_lines) if right_lines else [],
    )


def _group_sig_lines(lines: list[TextLine]) -> list[Paragraph]:
    """Group lines into paragraphs by vertical gap; use <br> within each paragraph."""
    lines = sorted(lines, key=lambda l: -l.y0)
    groups: list[list[TextLine]] = [[lines[0]]]
    for line in lines[1:]:
        prev = groups[-1][-1]
        gap = prev.y0 - line.y1
        if gap > prev.height * 1.2:
            groups.append([line])
        else:
            groups[-1].append(line)

    result: list[Paragraph] = []
    for group in groups:
        inlines = _lines_to_inlines_br(group)
        result.append(Paragraph(inlines=inlines, align="LEFT", is_small=True))
    return result


def _lines_to_inlines_br(lines: list[TextLine]) -> list[Inline]:
    """Like _lines_to_inlines but inserts <br> between lines."""
    inlines: list[Inline] = []
    for line in lines:
        body_size = _line_body_fontsize(line)
        parts: list[Inline] = []
        for span in line.spans:
            text = span.text.replace("\n", "").replace("\r", "")
            if not text:
                continue
            parts.append(Inline(
                text=text,
                italic=_is_italic_font(span.fontname),
                bold=_is_bold_font(span.fontname),
                sup=_is_superscript(span, line.y0, body_size),
                sub=_is_subscript(span, line.y1, body_size),
            ))
        if not parts:
            continue
        if inlines:
            parts[0].text = "<br>" + parts[0].text.lstrip()
        inlines.extend(parts)

    merged: list[Inline] = []
    for inline in inlines:
        if (merged
                and merged[-1].italic == inline.italic
                and merged[-1].bold == inline.bold
                and merged[-1].sup == inline.sup
                and merged[-1].sub == inline.sub):
            merged[-1].text += inline.text
        else:
            merged.append(Inline(
                text=inline.text,
                italic=inline.italic,
                bold=inline.bold,
                sup=inline.sup,
                sub=inline.sub,
            ))
    return merged


def detect_footnote(text_layer: PageTextLayer, sig_top_y: float | None = None) -> tuple[list[Paragraph], float, bool] | None:
    """Returns (paragraphs, body_min_y, True) for a "*"-prefixed editorial footnote block.
    One paragraph per '*'/'**' marker entry in the block.
    sig_top_y: if provided, ignore lines with y0 < sig_top_y (they belong to signatures).
    """
    lines = [line for line in text_layer.lines if line.text.strip()]
    if sig_top_y is not None:
        lines = [l for l in lines if l.y0 >= sig_top_y]
    if not lines:
        return None

    sorted_asc = sorted(lines, key=lambda l: l.y0)  # bottom-first

    # Collect lines from the bottom until a significant gap (the HR separator).
    # Normal inter-line spacing is 1–4 pt; an HR creates a gap of 10 pt or more.
    footnote_lines = [sorted_asc[0]]
    for line in sorted_asc[1:]:
        prev = footnote_lines[-1]
        if line.y0 - prev.y1 > prev.height * 2.0:
            break
        footnote_lines.append(line)

    # Validate: the collected block must be separated from the body above by a
    # significant gap — that gap is the HR rule visible in the PDF.
    fn_top_y = max(l.y1 for l in footnote_lines)
    body_above = sorted([l for l in lines if l.y0 >= fn_top_y], key=lambda l: l.y0)
    if not body_above:
        return None
    avg_height = sum(l.height for l in footnote_lines) / len(footnote_lines)
    if body_above[0].y0 - fn_top_y < avg_height * 2.0:
        return None

    footnote_lines.sort(key=lambda l: -l.y0)  # reading order

    # Only accept as footnote if it starts with "*" — that's the editorial marker.
    # Without this check, body text separated from a heading above by a large gap
    # would be misidentified as a footnote.
    if not footnote_lines[0].text.strip().startswith("*"):
        return None

    paras = []
    for group in _split_footnote_entries(footnote_lines):
        inlines = _lines_to_inlines(group)
        if inlines:
            paras.append(Paragraph(inlines=inlines, align="LEFT"))

    top_y = max(l.y1 for l in footnote_lines)
    return paras, top_y, True


def _is_paragraph_break(
    prev_line: TextLine,
    line: TextLine,
    body_x0: float,
    body_x1: float,
) -> bool:
    """True if a paragraph boundary exists between prev_line and line.

    Indent-based conditions (indent, outdent, short-line) only apply when the
    previous line started near the body left margin — they make no sense for
    right-aligned or otherwise offset lines.
    """
    vertical_gap = prev_line.y0 - line.y1
    if vertical_gap > max(prev_line.height, line.height) * 0.9:
        return True
    if prev_line.x0 < body_x0 + 60.0:
        if line.x0 - prev_line.x0 > 6.0:
            return True
        if prev_line.x0 - line.x0 > 50.0:
            return True
        if prev_line.x1 < body_x1 - 25.0 and line.x0 > body_x0 + 6.0:
            return True
    # Offset line (right-aligned date, signature) before a body-left line
    if prev_line.x0 > body_x0 + 50.0 and line.x0 < body_x0 + 20.0:
        return True
    return False


_COLUMN_GUTTER_MIN = 20.0
_TWO_COLUMN_MIN_ROWS = 3
_COLUMN_FIT_TOL = 5.0


def _group_rows(lines: list[TextLine]) -> list[list[TextLine]]:
    """Cluster lines into physical PDF rows by merging list-adjacent lines
    whose y-ranges overlap — deliberately conservative, no global re-sort.

    text_extractor hands lines to us in pdfminer's own block order, which is
    already correct reading order for the vast majority of a page. A real
    two-column body passage does interleave row by row in that order (each
    row's left/right pair land next to each other in the list). But other
    same-y-range cases exist for unrelated reasons — e.g. a small signature
    note where pdfminer clusters one whole column into a block, then the
    other, so two lines can share a y-range without being row-mates at all.
    Re-sorting the full line list by y0 to find "rows" would silently
    reorder those, corrupting paragraph text (verified: it flipped the order
    of a "Написано .../Печатается по тексту сборника" note). Only ever
    merging an immediately adjacent pair avoids that: it catches genuine
    row-interleaved columns while leaving everything else exactly as
    text_extractor ordered it.
    """
    rows: list[list[TextLine]] = []
    for line in lines:
        if (
            rows and len(rows[-1]) == 1
            and min(rows[-1][0].y1, line.y1) - max(rows[-1][0].y0, line.y0) > 0
        ):
            rows[-1].append(line)
        else:
            rows.append([line])
    return rows


def _is_split_row(row: list[TextLine]) -> bool:
    if len(row) != 2:
        return False
    a, b = row
    left, right = (a, b) if a.x0 <= b.x0 else (b, a)
    if len(left.text.strip()) < 3 or len(right.text.strip()) < 3:
        return False
    return right.x0 - left.x1 >= _COLUMN_GUTTER_MIN


def _find_two_column_runs(rows: list[list[TextLine]]) -> dict[int, int]:
    """Maximal contiguous stretches of rows that each split into two
    horizontally separated lines — a genuine two-column body passage, not an
    isolated coincidental gap. Maps each run's start row index to its
    (exclusive) end row index.
    """
    runs: dict[int, int] = {}
    i = 0
    while i < len(rows):
        if _is_split_row(rows[i]):
            j = i + 1
            while j < len(rows) and _is_split_row(rows[j]):
                j += 1
            if j - i >= _TWO_COLUMN_MIN_ROWS:
                runs[i] = j
            i = j
        else:
            i += 1
    return runs


def _lines_to_paragraphs(
    lines: list[TextLine],
    body_median: float | None,
    body_x0: float,
    body_x1: float,
    page_width: float,
) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    current_lines: list[TextLine] = []
    prev_line: TextLine | None = None

    for line in lines:
        if prev_line is None:
            current_lines.append(line)
            prev_line = line
            continue

        prev_text = prev_line.text.strip()

        # Если предыдущая строка заканчивается дефисом переноса,
        # следующая строка почти наверняка продолжает тот же абзац.
        if _ends_with_hyphen_wrap(prev_text):
            new_paragraph = False
        else:
            new_paragraph = _is_paragraph_break(prev_line, line, body_x0, body_x1)

        if new_paragraph:
            para = _build_paragraph(current_lines, body_median, body_x0, body_x1, page_width)
            if para is not None:
                paragraphs.append(para)
            current_lines = [line]
        else:
            current_lines.append(line)

        prev_line = line

    if current_lines:
        para = _build_paragraph(current_lines, body_median, body_x0, body_x1, page_width)
        if para is not None:
            paragraphs.append(para)

    return paragraphs


def detect_paragraphs(
    text_layer: PageTextLayer,
    body_min_y: float | None = None,
    heading_body_threshold: float | None = None,
    body_fontsize_ref: float | None = None,
    running_header_min_y: float | None = None,
    page_no: int | None = None,
) -> tuple[list, list[str]]:
    # Compute body line bounds and median font size
    body_lines_all: list[TextLine] = []
    body_sizes: list[float] = []
    for line in text_layer.lines:
        if body_min_y is not None and line.y0 < body_min_y:
            continue
        if heading_body_threshold is not None and line.y0 >= heading_body_threshold:
            continue
        if running_header_min_y is not None and line.y0 >= running_header_min_y:
            continue
        if line.text.strip():
            body_lines_all.append(line)
        body_sizes.extend(s.fontsize for s in line.spans if s.fontsize)
    # Use 75th percentile instead of median: a large inline quote block can
    # push the median down to the quote's font size, masking the real body size.
    body_median = sorted(body_sizes)[int(len(body_sizes) * 0.75)] if body_sizes else None
    # If the page is dominated by small text (e.g. a cross-page quote continuation),
    # the percentile is skewed. Fall back to the cross-page body size reference.
    if body_fontsize_ref is not None and (body_median is None or body_median < body_fontsize_ref * 0.92):
        body_median = body_fontsize_ref
    body_x0 = min((l.x0 for l in body_lines_all), default=0.0)
    body_x1 = max((l.x1 for l in body_lines_all), default=text_layer.width)

    items, found_ledger_table, table_notes = extract_ledger_tables(body_lines_all, body_x0, page_no=page_no)
    if not found_ledger_table:
        blocks = _paragraphs_and_two_column_blocks(
            body_lines_all, body_median, body_x0, body_x1, text_layer.width
        )
        return blocks, table_notes

    blocks: list = []
    segment: list[TextLine] = []
    for item in items:
        if isinstance(item, LedgerTable):
            if segment:
                blocks.extend(_paragraphs_and_two_column_blocks(
                    segment, body_median, body_x0, body_x1, text_layer.width
                ))
                segment = []
            blocks.append(item)
        else:
            segment.append(item)
    if segment:
        blocks.extend(_paragraphs_and_two_column_blocks(
            segment, body_median, body_x0, body_x1, text_layer.width
        ))
    return blocks, table_notes


def _paragraphs_and_two_column_blocks(
    lines: list[TextLine],
    body_median: float | None,
    body_x0: float,
    body_x1: float,
    page_width: float,
) -> list:
    rows = _group_rows(lines)
    two_col_runs = _find_two_column_runs(rows)

    blocks: list = []
    segment: list[TextLine] = []
    row_idx = 0
    while row_idx < len(rows):
        run_end = two_col_runs.get(row_idx)
        if run_end is not None:
            if segment:
                blocks.extend(_lines_to_paragraphs(segment, body_median, body_x0, body_x1, page_width))
                segment = []
            left_lines = [min(row, key=lambda l: l.x0) for row in rows[row_idx:run_end]]
            right_lines = [max(row, key=lambda l: l.x0) for row in rows[row_idx:run_end]]
            left_x0, left_x1 = min(l.x0 for l in left_lines), max(l.x1 for l in left_lines)
            right_x0, right_x1 = min(l.x0 for l in right_lines), max(l.x1 for l in right_lines)

            # One column can run a few lines longer than the other (e.g. a
            # numbered breakdown that's wordier than the passage it quotes).
            # Once its sibling has run out, that tail no longer forms a split
            # row — absorb it into whichever column's x-range it still fits,
            # stopping only once a line spans neither (real return to single
            # column body text).
            tail = run_end
            while tail < len(rows) and len(rows[tail]) == 1:
                line = rows[tail][0]
                if line.x0 >= left_x0 - _COLUMN_FIT_TOL and line.x1 <= left_x1 + _COLUMN_FIT_TOL:
                    left_lines.append(line)
                elif line.x0 >= right_x0 - _COLUMN_FIT_TOL and line.x1 <= right_x1 + _COLUMN_FIT_TOL:
                    right_lines.append(line)
                else:
                    break
                tail += 1

            blocks.append(TwoColumnBlock(
                left=_lines_to_paragraphs(
                    left_lines, body_median,
                    min(l.x0 for l in left_lines), max(l.x1 for l in left_lines),
                    page_width,
                ),
                right=_lines_to_paragraphs(
                    right_lines, body_median,
                    min(l.x0 for l in right_lines), max(l.x1 for l in right_lines),
                    page_width,
                ),
            ))
            row_idx = tail
            continue

        segment.extend(rows[row_idx])
        row_idx += 1

    if segment:
        blocks.extend(_lines_to_paragraphs(segment, body_median, body_x0, body_x1, page_width))

    return blocks


_CLOSING_QUOTE_RE = re.compile(r'(?<!\s)[»""]\s*[.,:;!?]?\s*$')
_OPENING_QUOTE_RE = re.compile(r'[«"„]')


def _is_quote_tail(para: Paragraph) -> bool:
    """Closing fragment of a cross-page quote: ends with word-adjacent » but has no opening «.

    The opening guillemet was on the previous page, so the only trace here is
    the closing guillemet at the end of this paragraph.
    """
    text = "".join(il.text for il in para.inlines)
    return bool(_CLOSING_QUOTE_RE.search(text)) and not bool(_OPENING_QUOTE_RE.search(text))


def _is_heading_like_paragraph(p: Paragraph) -> bool:
    """Bold, centered, ALL-CAPS paragraph — an in-article subheading (e.g. a
    section title inside a longer article) that landed in the regular body flow
    instead of the page-top heading area. Rendered as <h3>, not as a quote/paragraph.

    A trailing <sup> footnote-reference number (folded on by
    _fold_footnote_ref_lines) doesn't have to be bold itself.
    """
    if p.align != "CENTER" or not p.inlines:
        return False
    if not all(i.bold or i.sup for i in p.inlines):
        return False
    text = "".join(i.text for i in p.inlines if not i.sup)
    text = re.sub(r'<[^>]+>', ' ', text)  # strip embedded <br> etc. before the caps check
    return _is_all_caps_line(text)


def detect_quotes(pm: PageModel, prev_quote_open: bool = False) -> PageModel:
    """prev_quote_open: True if the previous page ended inside an actual
    <blockquote> left unclosed (see quote_is_open_at_page_end). Without this,
    a normal paragraph that merely closes with a stray » (e.g. Marx re-quoting
    a clause inline, cut by a page break, with no blockquote on either side)
    would be wrongly promoted to <blockquote> just because it lacks a local «.
    """
    for i, p in enumerate(pm.blocks):
        if not isinstance(p, Paragraph):
            continue
        if _is_heading_like_paragraph(p):
            p.heading_level = 3
            p.is_small = False
        elif p.is_small and p.align in ("JUSTIFY", "CENTER"):
            p.is_quote = True
            p.is_small = False
        elif i == 0 and prev_quote_open and p.align == "JUSTIFY" and _is_quote_tail(p):
            p.is_quote = True
    return pm


def _para_closes_quote(para: Paragraph) -> bool:
    """True if the paragraph's quotation is closed by its end.

    Looks at the LAST « or » in the whole paragraph rather than requiring »
    to be the final character: trailing editorial text after the closing
    guillemet (e.g. '...целому» и т. д.') is common and doesn't reopen the quote.
    """
    text = "".join(il.text for il in para.inlines)
    marks = re.findall(r'[«»]', text)
    if marks:
        return marks[-1] == '»'
    return bool(_CLOSING_QUOTE_RE.search(text))


def quote_is_open_at_page_end(pm: PageModel) -> bool:
    """True if the page ends with a blockquote that has no closing guillemet."""
    for p in reversed(pm.blocks):
        if not isinstance(p, Paragraph):
            continue
        if p.is_quote:
            return not _para_closes_quote(p)
    return False


def apply_quote_continuation(pm: PageModel, prev_quote_open: bool) -> None:
    """Mark leading paragraphs on this page as blockquote if the previous page
    ended with an unclosed quote.

    Must be called BEFORE detect_quotes so that is_small is still set.
    Uses is_small as the primary signal: a small-font paragraph at the start of
    a page following an open quote is a continuation. Stops at the first
    non-small, non-quote paragraph (= body text). Does nothing when the page
    opens a new section (has headings).
    """
    if not prev_quote_open:
        return
    if pm.headings or pm.heading_blocks:
        return
    for p in pm.blocks:
        if not isinstance(p, Paragraph):
            # A two-column block can't be a quote continuation — treat it like
            # reaching body text and stop.
            return
        if p.is_quote:
            # Already marked (e.g. is_quote_tail from a previous run) — keep going.
            if _para_closes_quote(p):
                return
            continue
        if not p.is_small or p.align != "JUSTIFY":
            # First non-small paragraph = body text boundary; stop.
            return
        p.is_quote = True
        p.is_small = False
        if _para_closes_quote(p):
            return


def _fold_footnote_ref_lines(lines: list[TextLine]) -> list[TextLine]:
    """Fold a standalone small digit-only line into the next (bold) line as a
    trailing superscript, when it's really a footnote-reference number attached
    to that line — e.g. an in-article heading like "ГЛАВА О БРАКЕ 39".

    Its raised baseline makes pdfminer split it into its own TextLine, which
    then reads (top-to-bottom) *before* the line it visually follows. Only
    folds when the digit line is small, horizontally flush against the next
    line, and vertically overlaps it — the geometric signature of a footnote
    marker, not an unrelated standalone number.
    """
    if len(lines) < 2:
        return lines

    result: list[TextLine] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        text = line.text.strip()
        if i + 1 < len(lines) and text.isdigit() and len(text) <= 3:
            nxt = lines[i + 1]
            overlap = min(line.y1, nxt.y1) - max(line.y0, nxt.y0)
            gap = line.x0 - nxt.x1
            if (
                overlap > 0
                and -1.0 <= gap <= 6.0
                and line.avg_fontsize and nxt.avg_fontsize
                and line.avg_fontsize < nxt.avg_fontsize * 0.85
                and _line_is_bold(nxt)
            ):
                result.append(TextLine(
                    spans=nxt.spans + line.spans,
                    x0=nxt.x0,
                    y0=nxt.y0,
                    x1=line.x1,
                    y1=max(nxt.y1, line.y1),
                ))
                i += 2
                continue
        result.append(line)
        i += 1
    return result


def _build_paragraph(
    lines: list[TextLine],
    body_fontsize: float | None = None,
    body_x0: float = 0.0,
    body_x1: float = 0.0,
    page_width: float = 0.0,
) -> Paragraph | None:
    lines = _fold_footnote_ref_lines(lines)

    # Detect small font first — used in alignment heuristic below.
    is_small = False
    if body_fontsize is not None:
        sizes = [s.fontsize for l in lines for s in l.spans if s.fontsize]
        if sizes:
            para_median = sorted(sizes)[len(sizes) // 2]
            is_small = para_median < body_fontsize * 0.85

    para_x0 = min(l.x0 for l in lines)
    para_x1 = max(l.x1 for l in lines)
    left_indent = para_x0 - body_x0
    right_indent = body_x1 - para_x1
    # Verse/poetry lines vary in length, so their collective bounding box is
    # wider than any single line and may push the measured asymmetry above the
    # standard 30 pt tolerance.  Allow a wider tolerance for small-font blocks
    # so that indented poem stanzas are correctly classified as CENTER.
    center_tol = 50 if is_small else 30
    if left_indent > 30 and abs(left_indent - right_indent) <= center_tol:
        align = "CENTER"
    elif page_width > 0 and para_x1 - para_x0 < page_width * 0.7:
        # Fallback: narrow paragraph centered on the page (title pages with no body reference)
        para_center = (para_x0 + para_x1) / 2
        if abs(para_center - page_width / 2) <= 15:
            align = "CENTER"
        elif left_indent > right_indent * 2 and left_indent > 50:
            align = "RIGHT"
        else:
            align = "JUSTIFY"
    elif left_indent > right_indent * 2 and left_indent > 50:
        align = "RIGHT"
    else:
        align = "JUSTIFY"

    inlines = _lines_to_inlines_br(lines) if align in ("RIGHT", "CENTER") else _lines_to_inlines(lines)
    if not inlines or not any(i.text.strip() for i in inlines):
        return None

    return Paragraph(inlines=inlines, align=align, is_small=is_small)


def _join_lines(lines: list[str]) -> str:
    if not lines:
        return ""

    result: list[str] = [lines[0]]

    for next_line in lines[1:]:
        prev = result[-1]

        if _should_concatenate_without_space(prev, next_line):
            result[-1] = prev[:-1] + next_line
        else:
            result.append(" " + next_line)

    return "".join(result)


def _should_concatenate_without_space(left: str, right: str) -> bool:
    if not left or not right:
        return False

    return _ends_with_hyphen_wrap(left)


def _ends_with_hyphen_wrap(text: str) -> bool:
    if not text:
        return False

    return text.endswith("-")


# Дефисные сокращения, которые не являются переносом слова: если разрыв
# строки случайно совпал с дефисом внутри такого сокращения ("г-на" → "г-" /
# "на"), дефис нужно сохранить, а не вырезать как перенос.
_HYPHEN_ABBREVIATIONS = {
    "об-во", "т-во", "изд-во", "уч-ще", "гос-во", "р-н",
}


def _is_hyphen_abbreviation(prefix_word: str, suffix_word: str) -> bool:
    """True if the '-' joining prefix_word and suffix_word is a real dash
    inside an abbreviation, not a word-wrap hyphenation point.

    Russian typographic rules never hyphenate a word leaving a single-letter
    fragment on either side of the break — so a one-letter prefix (as in
    "г-н", "т-во", "р-н") can only be a genuine dash. Longer prefixes are
    checked against a curated list of known abbreviations, since they are
    otherwise indistinguishable from a valid syllable-boundary hyphenation.
    """
    if len(prefix_word) <= 1:
        return True
    return f"{prefix_word}-{suffix_word}".lower() in _HYPHEN_ABBREVIATIONS


def _trailing_word(text: str) -> str:
    match = re.search(r"[^\W\d_]+$", text)
    return match.group(0) if match else ""


def _accumulated_trailing_text(inlines: list[Inline], limit: int = 8) -> str:
    """Concatenate the last few Inline texts back to the nearest whitespace.

    pdfminer sometimes puts a wrap-hyphen in its own span, separate from the
    letter before it (e.g. "Ге" and "-" as two spans of one PDF line), so
    inlines[-1].text alone can be just "-" with no letters to judge. Looking
    back across recent same-run inlines recovers the actual word fragment.
    """
    parts: list[str] = []
    for inline in reversed(inlines[-limit:]):
        parts.append(inline.text)
        if re.search(r"\s", inline.text):
            break
    return "".join(reversed(parts))


def _leading_word(text: str) -> str:
    match = re.match(r"[^\W\d_]+", text.lstrip())
    return match.group(0) if match else ""


def _is_italic_font(fontname: str | None) -> bool:
    if not fontname:
        return False
    fn = fontname.lower()
    return "italic" in fn or "oblique" in fn


def _line_body_fontsize(line: TextLine) -> float:
    """Dominant font size of a line's actual text, by character count.

    A plain max() over span sizes is thrown off by a single stray glyph —
    e.g. an oversized invisible word-space pdfminer sometimes emits mid-line
    — which then makes ordinary body text look "small" next to it and get
    misclassified as sup/sub. Weighting by non-whitespace character count
    picks the size that's actually running text.
    """
    counts: dict[float, int] = {}
    for span in line.spans:
        text = span.text.strip()
        if not text or not span.fontsize:
            continue
        counts[span.fontsize] = counts.get(span.fontsize, 0) + len(text)
    if not counts:
        return 0.0
    return max(counts, key=counts.get)


def _is_superscript(span: TextSpan, line_y0: float, body_size: float) -> bool:
    if not span.fontsize or not body_size:
        return False
    return span.fontsize < body_size * 0.85 and span.y0 > line_y0 + 2.0


def _is_subscript(span: TextSpan, line_y1: float, body_size: float) -> bool:
    if not span.fontsize or not body_size:
        return False
    return span.fontsize < body_size * 0.85 and span.y1 < line_y1 - 2.0


def _split_footnote_entries(lines: list[TextLine]) -> list[list[TextLine]]:
    """Split footnote lines into groups, one per '*'/'**' marker entry.

    A footnote block can stack multiple editorial notes (e.g. '*' and '**'
    definitions) back to back; each line starting with an asterisk begins a
    new entry, and following lines (word-wrap continuations) belong to it.
    """
    groups: list[list[TextLine]] = []
    for line in lines:
        if not groups or line.text.strip().startswith("*"):
            groups.append([line])
        else:
            groups[-1].append(line)
    return groups


def _lines_to_inlines(lines: list[TextLine]) -> list[Inline]:
    """Build Inline list from TextLines preserving italic/sup/sub per span, handling hyphen-wrap."""
    inlines: list[Inline] = []

    for line in lines:
        body_size = _line_body_fontsize(line)
        line_parts: list[Inline] = []
        for span in line.spans:
            text = span.text.replace("\n", "").replace("\r", "")
            if not text:
                continue
            line_parts.append(Inline(
                text=text,
                italic=_is_italic_font(span.fontname),
                bold=_is_bold_font(span.fontname),
                sup=_is_superscript(span, line.y0, body_size),
                sub=_is_subscript(span, line.y1, body_size),
            ))

        if not line_parts:
            continue

        prev_text = inlines[-1].text.rstrip() if inlines else ""
        if inlines and _ends_with_hyphen_wrap(prev_text):
            lookback_text = _accumulated_trailing_text(inlines).rstrip()
            prefix_word = _trailing_word(lookback_text[:-1])
            suffix_word = _leading_word(line_parts[0].text)
            if _is_hyphen_abbreviation(prefix_word, suffix_word):
                inlines[-1].text = prev_text
            else:
                inlines[-1].text = prev_text[:-1]
        elif inlines:
            line_parts[0].text = " " + line_parts[0].text

        inlines.extend(line_parts)

    # Merge adjacent inlines with same style
    merged: list[Inline] = []
    for inline in inlines:
        if (merged
                and merged[-1].italic == inline.italic
                and merged[-1].bold == inline.bold
                and merged[-1].sup == inline.sup
                and merged[-1].sub == inline.sub):
            merged[-1].text += inline.text
        else:
            merged.append(Inline(
                text=inline.text,
                italic=inline.italic,
                bold=inline.bold,
                sup=inline.sup,
                sub=inline.sub,
            ))

    return merged