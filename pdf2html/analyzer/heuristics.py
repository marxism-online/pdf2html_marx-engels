from __future__ import annotations

from pdf2html.utils.text_layer import PageTextLayer
from pdf2html.utils.types import Heading
from pdf2html.utils.types import Inline
from pdf2html.utils.types import PageModel
from pdf2html.utils.types import Paragraph


def detect_headings(text_layer: PageTextLayer) -> Heading | None:
    # Пока заголовки не определяем.
    return None


def detect_paragraphs(text_layer: PageTextLayer) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []

    current_lines: list[str] = []
    prev_line = None

    for line in text_layer.lines:
        text = line.text.strip()
        if not text:
            continue

        if prev_line is None:
            current_lines.append(text)
            prev_line = line
            continue

        vertical_gap = prev_line.y0 - line.y1
        same_left_edge = abs(prev_line.x0 - line.x0) <= 3.0

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

    return left.endswith("-")