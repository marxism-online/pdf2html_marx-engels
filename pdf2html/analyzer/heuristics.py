from __future__ import annotations

import re

from pdf2html.utils.text_layer import PageTextLayer
from pdf2html.utils.text_layer import TextLine
from pdf2html.utils.text_layer import TextSpan
from pdf2html.utils.types import Heading
from pdf2html.utils.types import Inline
from pdf2html.utils.types import PageModel
from pdf2html.utils.types import Paragraph
from pdf2html.utils.types import SignatureBlock

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
        return f"{num_part} <br>{text_part}", int(num_part)
    m2 = _LONE_PAGE_NUM_RE.match(lines[0].text)
    if m2:
        num = int(m2.group(1))
        return str(num), num
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


def detect_headings(text_layer: PageTextLayer) -> tuple[list[Heading], float | None]:
    """Return (headings, heading_body_threshold).

    heading_body_threshold is the minimum y0 of detected heading lines.
    detect_paragraphs should skip lines with y0 >= this value.
    """
    lines = sorted(
        [l for l in text_layer.lines if l.text.strip()],
        key=lambda l: -l.y0,
    )
    if not lines:
        return [], None

    page_center = text_layer.width / 2

    # Skip running header (first line if it matches the header pattern)
    start = 1 if (_RUNNING_HEADER_RE.match(lines[0].text) or _LONE_PAGE_NUM_RE.match(lines[0].text)) else 0

    heading_lines: list[TextLine] = []
    orphan_sups: list[TextLine] = []
    for line in lines[start:]:
        text = line.text.strip()
        if not any(c.isalpha() for c in text):
            # Non-alphabetic lines inside the heading block (e.g. footnote numbers
            # like "278") are superscripts — collect and attach at the end.
            orphan_sups.append(line)
            continue
        if not _is_all_caps_line(text):
            break
        line_center = (line.x0 + line.x1) / 2
        if abs(line_center - page_center) <= _CENTERING_TOLERANCE:
            heading_lines.append(line)
        else:
            break

    if not heading_lines:
        return [], None

    # Group consecutive lines by bold/non-bold font
    groups: list[tuple[bool, list[TextLine]]] = []
    for line in heading_lines:
        bold = _line_is_bold(line)
        if groups and groups[-1][0] == bold:
            groups[-1][1].append(line)
        else:
            groups.append((bold, [line]))

    rendered: list[str] = []
    for is_bold, group_lines in groups:
        parts = [l.text.strip() for l in group_lines]
        text = "<br>".join(parts)
        if is_bold:
            text = f"<b>{text}</b>"
        rendered.append(text)

    combined = "<br><br>".join(rendered)
    if orphan_sups:
        combined += "".join(f"<sup>{l.text.strip()}</sup>" for l in orphan_sups)

    headings = [Heading(level=2, text=combined, align="CENTER")]

    all_heading_lines = heading_lines + orphan_sups
    heading_body_threshold = min(l.y0 for l in all_heading_lines)
    return headings, heading_body_threshold


def detect_signatures(
    text_layer: PageTextLayer,
) -> tuple[SignatureBlock | None, float | None, Paragraph | None]:
    """Detect two-column article signatures at bottom of page.

    Returns (SignatureBlock, sig_top_y, star_footnote).
    star_footnote: editorial '*'-footnote found below the signature block, if any.
    sig_top_y is the y1 of the topmost signature line, used to limit footnote detection.
    """
    lines = [line for line in text_layer.lines if line.text.strip()]
    if not lines:
        return None, None, None

    all_sizes = [l.avg_fontsize for l in lines if l.avg_fontsize is not None]
    if not all_sizes:
        return None, None, None
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
        return None, None, None

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

    star_para: Paragraph | None = None
    if star_lines:
        star_lines.sort(key=lambda l: -l.y0)
        inlines = _lines_to_inlines(star_lines, break_on_asterisk=True)
        if inlines:
            star_para = Paragraph(inlines=inlines, align="LEFT")

    if not small_lines:
        return None, None, star_para

    small_lines.sort(key=lambda l: -l.y0)  # reading order
    if small_lines[0].text.strip().startswith("*"):
        return None, None, star_para  # remaining lines are also footnote

    # Reject if any small line is too wide to be a column in a two-column layout
    text_width = max((l.x1 for l in lines), default=0.0) - min((l.x0 for l in lines), default=0.0)
    if text_width > 0 and max(l.x1 - l.x0 for l in small_lines) > text_width * 0.55:
        return None, None, star_para

    page_center = text_layer.width / 2
    left_lines = [l for l in small_lines if (l.x0 + l.x1) / 2 < page_center]
    right_lines = [l for l in small_lines if (l.x0 + l.x1) / 2 >= page_center]

    if not left_lines or not right_lines:
        return None, None, star_para

    sig_top_y = max(l.y1 for l in small_lines)
    return SignatureBlock(
        left=_group_sig_lines(left_lines),
        right=_group_sig_lines(right_lines),
    ), sig_top_y, star_para


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
        body_size = max((s.fontsize for s in line.spans if s.fontsize), default=0.0)
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


def detect_footnote(text_layer: PageTextLayer, sig_top_y: float | None = None) -> tuple[Paragraph, float, bool] | None:
    """Returns (paragraph, body_min_y, is_footnote).
    is_footnote=True when text starts with *, meaning a real footnote with HR.
    is_footnote=False for closing signatures (no HR).
    sig_top_y: if provided, ignore lines with y0 < sig_top_y (they belong to signatures).
    """
    lines = [line for line in text_layer.lines if line.text.strip()]
    if sig_top_y is not None:
        lines = [l for l in lines if l.y0 >= sig_top_y]
    if not lines:
        return None

    all_sizes = [l.avg_fontsize for l in lines if l.avg_fontsize is not None]
    if not all_sizes:
        return None

    all_sizes.sort()
    main_size = all_sizes[int(len(all_sizes) * 0.9)]
    small_threshold = main_size * 0.85

    sorted_asc = sorted(lines, key=lambda l: l.y0)  # bottom-first

    footnote_lines = []
    for line in sorted_asc:
        fs = line.avg_fontsize
        if fs is not None and fs <= small_threshold:
            footnote_lines.append(line)
        else:
            break

    if not footnote_lines:
        return None

    # Reject if the small lines are directly adjacent to body text above them —
    # they're likely a blockquote continuation, not a footnote.
    fn_top_y = max(l.y1 for l in footnote_lines)
    body_above = sorted([l for l in lines if l.y0 >= fn_top_y], key=lambda l: l.y0)
    if body_above:
        avg_height = sum(l.height for l in footnote_lines) / len(footnote_lines)
        if body_above[0].y0 - fn_top_y <= avg_height * 1.5:
            return None

    footnote_lines.sort(key=lambda l: -l.y0)  # reading order
    inlines = _lines_to_inlines(footnote_lines, break_on_asterisk=True)
    para = Paragraph(inlines=inlines, align="LEFT")

    top_y = max(l.y1 for l in footnote_lines)
    is_footnote = footnote_lines[0].text.strip().startswith("*")
    return para, top_y, is_footnote


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
    if prev_line.x0 < body_x0 + 20.0:
        if line.x0 - prev_line.x0 > 6.0:
            return True
        if prev_line.x0 - line.x0 > 50.0:
            return True
        if prev_line.x1 < body_x1 - 60.0 and line.x0 > body_x0 + 6.0:
            return True
    return False


def detect_paragraphs(
    text_layer: PageTextLayer,
    body_min_y: float | None = None,
    heading_body_threshold: float | None = None,
) -> list[Paragraph]:
    # Compute body line bounds and median font size
    body_lines_all: list[TextLine] = []
    body_sizes: list[float] = []
    for line in text_layer.lines:
        if body_min_y is not None and line.y0 < body_min_y:
            continue
        if heading_body_threshold is not None and line.y0 >= heading_body_threshold:
            continue
        if line.text.strip():
            body_lines_all.append(line)
        body_sizes.extend(s.fontsize for s in line.spans if s.fontsize)
    body_median = sorted(body_sizes)[len(body_sizes) // 2] if body_sizes else None
    body_x0 = min((l.x0 for l in body_lines_all), default=0.0)
    body_x1 = max((l.x1 for l in body_lines_all), default=text_layer.width)

    paragraphs: list[Paragraph] = []
    current_lines: list[TextLine] = []
    prev_line: TextLine | None = None

    for line in text_layer.lines:
        text = line.text.strip()
        if not text:
            continue
        if body_min_y is not None and line.y0 < body_min_y:
            continue
        if heading_body_threshold is not None and line.y0 >= heading_body_threshold:
            continue

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
            para = _build_paragraph(current_lines, body_median, body_x0, body_x1)
            if para is not None:
                paragraphs.append(para)
            current_lines = [line]
        else:
            current_lines.append(line)

        prev_line = line

    if current_lines:
        para = _build_paragraph(current_lines, body_median, body_x0, body_x1)
        if para is not None:
            paragraphs.append(para)

    return paragraphs


def detect_quotes(pm: PageModel) -> PageModel:
    for p in pm.blocks:
        if p.is_small and p.align == "JUSTIFY":
            p.is_quote = True
            p.is_small = False
    return pm


def _build_paragraph(
    lines: list[TextLine],
    body_fontsize: float | None = None,
    body_x0: float = 0.0,
    body_x1: float = 0.0,
) -> Paragraph | None:
    # Detect alignment first — RIGHT paragraphs use <br> between lines
    para_x0 = min(l.x0 for l in lines)
    para_x1 = max(l.x1 for l in lines)
    left_indent = para_x0 - body_x0
    right_indent = body_x1 - para_x1
    align: str = "RIGHT" if left_indent > right_indent * 2 and left_indent > 50 else "JUSTIFY"

    inlines = _lines_to_inlines_br(lines) if align == "RIGHT" else _lines_to_inlines(lines)
    if not inlines or not any(i.text.strip() for i in inlines):
        return None

    # Detect small font: paragraph median < 85% of body median
    is_small = False
    if body_fontsize is not None:
        sizes = [s.fontsize for l in lines for s in l.spans if s.fontsize]
        if sizes:
            para_median = sorted(sizes)[len(sizes) // 2]
            is_small = para_median < body_fontsize * 0.85

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


def _is_italic_font(fontname: str | None) -> bool:
    if not fontname:
        return False
    fn = fontname.lower()
    return "italic" in fn or "oblique" in fn


def _is_superscript(span: TextSpan, line_y0: float, body_size: float) -> bool:
    if not span.fontsize or not body_size:
        return False
    return span.fontsize < body_size * 0.85 and span.y0 > line_y0 + 2.0


def _is_subscript(span: TextSpan, line_y1: float, body_size: float) -> bool:
    if not span.fontsize or not body_size:
        return False
    return span.fontsize < body_size * 0.85 and span.y1 < line_y1 - 2.0


def _lines_to_inlines(lines: list[TextLine], break_on_asterisk: bool = False) -> list[Inline]:
    """Build Inline list from TextLines preserving italic/sup/sub per span, handling hyphen-wrap."""
    inlines: list[Inline] = []

    for line in lines:
        body_size = max((s.fontsize for s in line.spans if s.fontsize), default=0.0)
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

        if inlines and _ends_with_hyphen_wrap(inlines[-1].text.rstrip()):
            inlines[-1].text = inlines[-1].text.rstrip()[:-1]
        elif inlines:
            first_text = "".join(lp.text for lp in line_parts).lstrip()
            if break_on_asterisk and first_text.startswith("*"):
                line_parts[0].text = "<br>" + line_parts[0].text.lstrip()
            else:
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