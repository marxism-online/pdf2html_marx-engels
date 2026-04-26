from __future__ import annotations

import re

from pdf2html.utils.text_layer import PageTextLayer
from pdf2html.utils.text_layer import TextLine
from pdf2html.utils.types import Heading
from pdf2html.utils.types import Inline
from pdf2html.utils.types import PageModel
from pdf2html.utils.types import Paragraph

# Паттерн: текст, 5+ пробелов, затем число (арабское или римское)
_RUNNING_HEADER_RE = re.compile(
    r'^(.+?)\s{5,}(\d+|[IVXLCDM]{1,8})\s*$'
)


def detect_running_header(text_layer: PageTextLayer) -> tuple[str, int] | None:
    lines = [line for line in text_layer.lines if line.text.strip()]
    if not lines:
        return None
    m = _RUNNING_HEADER_RE.match(lines[0].text)
    if not m:
        return None
    text_part = m.group(1).strip()
    num_part = m.group(2)
    if not num_part.isdigit():
        return None
    return f"{num_part} <br>{text_part}", int(num_part)


def detect_headings(text_layer: PageTextLayer) -> Heading | None:
    # Пока заголовки не определяем.
    return None


def detect_footnote(text_layer: PageTextLayer) -> tuple[Paragraph, float, bool] | None:
    """Returns (paragraph, body_min_y, is_footnote).
    is_footnote=True when text starts with *, meaning a real footnote with HR.
    is_footnote=False for closing signatures (no HR).
    """
    lines = [line for line in text_layer.lines if line.text.strip()]
    if not lines:
        return None

    all_sizes = [l.avg_fontsize for l in lines if l.avg_fontsize is not None]
    if not all_sizes:
        return None

    all_sizes.sort()
    main_size = all_sizes[len(all_sizes) // 2]
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

    footnote_lines.sort(key=lambda l: -l.y0)  # reading order
    inlines = _lines_to_inlines(footnote_lines)
    para = Paragraph(inlines=inlines, align="LEFT")

    top_y = max(l.y1 for l in footnote_lines)
    is_footnote = footnote_lines[0].text.strip().startswith("*")
    return para, top_y, is_footnote


def detect_paragraphs(text_layer: PageTextLayer, body_min_y: float | None = None) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []

    current_lines: list[str] = []
    prev_line = None

    for line in text_layer.lines:
        text = line.text.strip()
        if not text:
            continue
        if body_min_y is not None and line.y0 < body_min_y:
            continue

        if prev_line is None:
            current_lines.append(text)
            prev_line = line
            continue

        prev_text = prev_line.text.strip()

        # Если предыдущая строка заканчивается дефисом переноса,
        # следующая строка почти наверняка продолжает тот же абзац.
        if _ends_with_hyphen_wrap(prev_text):
            new_paragraph = False
        else:
            vertical_gap = prev_line.y0 - line.y1
            same_left_edge = abs(prev_line.x0 - line.x0) <= 6.0

            new_paragraph = False

            if vertical_gap > max(prev_line.height, line.height) * 0.9:
                new_paragraph = True
            elif not same_left_edge:
                new_paragraph = True

        if new_paragraph:
            para = _build_paragraph(current_lines)
            if para is not None:
                paragraphs.append(para)
            current_lines = [text]
        else:
            current_lines.append(text)

        prev_line = line

    if current_lines:
        para = _build_paragraph(current_lines)
        if para is not None:
            paragraphs.append(para)

    return paragraphs


def detect_quotes(pm: PageModel) -> PageModel:
    # Пока цитаты отдельно не выделяем.
    return pm


def _build_paragraph(lines: list[str]) -> Paragraph | None:
    text = _join_lines(lines).strip()
    if not text:
        return None

    return Paragraph(
        inlines=[Inline(text=text)],
        align="JUSTIFY",
    )


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


def _lines_to_inlines(lines: list[TextLine]) -> list[Inline]:
    """Build Inline list from TextLines preserving italic per span, handling hyphen-wrap."""
    inlines: list[Inline] = []

    for line in lines:
        line_parts: list[Inline] = []
        for span in line.spans:
            text = span.text.replace("\n", "").replace("\r", "")
            if not text:
                continue
            line_parts.append(Inline(text=text, italic=_is_italic_font(span.fontname)))

        if not line_parts:
            continue

        if inlines and _ends_with_hyphen_wrap(inlines[-1].text.rstrip()):
            inlines[-1].text = inlines[-1].text.rstrip()[:-1]
        elif inlines:
            line_parts[0].text = " " + line_parts[0].text

        inlines.extend(line_parts)

    # Merge adjacent inlines with same style
    merged: list[Inline] = []
    for inline in inlines:
        if merged and merged[-1].italic == inline.italic and merged[-1].bold == inline.bold:
            merged[-1].text += inline.text
        else:
            merged.append(Inline(text=inline.text, italic=inline.italic, bold=inline.bold))

    return merged