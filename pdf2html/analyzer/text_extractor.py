from __future__ import annotations

from pdfminer.layout import LTChar
from pdfminer.layout import LTTextContainer
from pdfminer.layout import LTTextLine

from pdf2html.utils.text_layer import PageTextLayer
from pdf2html.utils.text_layer import TextBlock
from pdf2html.utils.text_layer import TextLine
from pdf2html.utils.text_layer import TextSpan

# Some embedded font subsets in this book map footnote-marker glyphs to
# Private Use Area codepoints instead of real Unicode characters, so pdfminer
# extracts them as unrenderable placeholders (browser tofu boxes) instead of
# the intended punctuation. Known cases, keyed by the extracted codepoint:
#   U+F02A — AHPFGN+TimesNewRomanPSMT footnote-marker asterisk. The source
#   PDF draws it twice at the identical position for a bold "**"; mapping
#   each occurrence to a plain "*" lets the two draws concatenate back into
#   the intended "**" with no extra dedup logic needed.
_GLYPH_FIXUPS = {
    "": "*",
}


def _fixup_char_text(text: str) -> str:
    return _GLYPH_FIXUPS.get(text, text)


def _merge_split_lines(lines: list[TextLine]) -> list[TextLine]:
    """Merge consecutive LTTextLine objects that pdfminer split apart even
    though they're really the same physical line.

    Two cases: zero-advance-width glyphs (e.g. the PUA footnote-marker glyphs
    above), which can confuse pdfminer's line clustering on an otherwise flat
    baseline; and a raised run mid-line (e.g. a footnote-reference number
    superscripted inside running footnote text) — pdfminer clusters it as its
    own line because its baseline sits above the surrounding text, even
    though it's horizontally contiguous with it. Only merges lines whose
    x-ranges touch with virtually no gap and whose y-ranges overlap; genuine
    same-row content (two-column signature blocks, etc.) sits far enough
    apart in x to be unaffected.
    """
    if not lines:
        return lines

    merged: list[TextLine] = [lines[0]]
    for line in lines[1:]:
        prev = merged[-1]
        gap = line.x0 - prev.x1
        touches = -1.0 <= gap <= 1.5
        overlap = min(prev.y1, line.y1) - max(prev.y0, line.y0)
        min_height = min(prev.y1 - prev.y0, line.y1 - line.y0)
        same_row = touches and min_height > 0 and overlap > min_height * 0.3
        if same_row:
            merged[-1] = TextLine(
                spans=prev.spans + line.spans,
                x0=prev.x0,
                y0=min(prev.y0, line.y0),
                x1=line.x1,
                y1=max(prev.y1, line.y1),
            )
        else:
            merged.append(line)
    return merged


class PdfTextExtractor:
    def extract_page_text_layer(self, page_no: int, layout: object) -> PageTextLayer:
        width = float(getattr(layout, "width", 0.0))
        height = float(getattr(layout, "height", 0.0))

        blocks: list[TextBlock] = []

        for obj in layout:
            if not isinstance(obj, LTTextContainer):
                continue

            block = self._extract_block(obj)
            if block.lines:
                blocks.append(block)

        blocks.sort(key=lambda b: (-b.y1, b.x0))

        # A split line's two halves can end up in two different LTTextContainer
        # blocks (pdfminer's own clustering, not just within one block's lines),
        # so the merge has to run on the page's full flattened, reading-order
        # line sequence rather than per block. Nothing downstream reads
        # block-level geometry (only the flattened .lines), so collapsing to a
        # single page-level block after merging is safe.
        all_lines = _merge_split_lines([line for block in blocks for line in block.lines])
        merged_block = TextBlock(
            lines=all_lines,
            x0=min((l.x0 for l in all_lines), default=0.0),
            y0=min((l.y0 for l in all_lines), default=0.0),
            x1=max((l.x1 for l in all_lines), default=0.0),
            y1=max((l.y1 for l in all_lines), default=0.0),
        )

        return PageTextLayer(
            page_no=page_no,
            width=width,
            height=height,
            blocks=[merged_block] if all_lines else [],
        )

    def _extract_block(self, obj: LTTextContainer) -> TextBlock:
        lines: list[TextLine] = []

        for child in obj:
            if not isinstance(child, LTTextLine):
                continue

            line = self._extract_line(child)
            if line.text:
                lines.append(line)

        if not lines:
            return TextBlock()

        x0 = min(line.x0 for line in lines)
        y0 = min(line.y0 for line in lines)
        x1 = max(line.x1 for line in lines)
        y1 = max(line.y1 for line in lines)

        return TextBlock(
            lines=lines,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
        )

    def _extract_line(self, line_obj: LTTextLine) -> TextLine:
        spans: list[TextSpan] = []

        current_text: list[str] = []
        current_chars: list[LTChar] = []
        current_fontname: str | None = None
        current_fontsize: float | None = None
        current_color: tuple[float, ...] | None = None

        def flush_span() -> None:
            nonlocal current_text, current_chars, current_fontname, current_fontsize, current_color

            if not current_text or not current_chars:
                current_text = []
                current_chars = []
                current_fontname = None
                current_fontsize = None
                current_color = None
                return

            spans.append(
                TextSpan(
                    text="".join(current_text),
                    x0=min(ch.x0 for ch in current_chars),
                    y0=min(ch.y0 for ch in current_chars),
                    x1=max(ch.x1 for ch in current_chars),
                    y1=max(ch.y1 for ch in current_chars),
                    fontname=current_fontname,
                    fontsize=current_fontsize,
                    color=current_color,
                )
            )

            current_text = []
            current_chars = []
            current_fontname = None
            current_fontsize = None
            current_color = None

        for elem in line_obj:
            if isinstance(elem, LTChar):
                fontname = getattr(elem, "fontname", None)
                fontsize = float(getattr(elem, "size", 0.0))
                ncolor = getattr(getattr(elem, "graphicstate", None), "ncolor", None)
                color = tuple(ncolor) if isinstance(ncolor, (list, tuple)) else None

                if (
                    current_fontname is not None
                    and current_fontsize is not None
                    and (fontname != current_fontname or fontsize != current_fontsize)
                ):
                    flush_span()

                current_text.append(_fixup_char_text(elem.get_text()))
                current_chars.append(elem)

                if current_fontname is None:
                    current_fontname = fontname
                if current_fontsize is None:
                    current_fontsize = fontsize
                if current_color is None:
                    current_color = color
            else:
                text = elem.get_text()
                if text:
                    current_text.append(text)

        flush_span()

        text_value = "".join(span.text for span in spans).strip()
        if not text_value:
            return TextLine()

        return TextLine(
            spans=spans,
            x0=float(getattr(line_obj, "x0", 0.0)),
            y0=float(getattr(line_obj, "y0", 0.0)),
            x1=float(getattr(line_obj, "x1", 0.0)),
            y1=float(getattr(line_obj, "y1", 0.0)),
        )