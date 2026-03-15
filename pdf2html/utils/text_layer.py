from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TextSpan:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    fontname: str | None = None
    fontsize: float | None = None

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass(slots=True)
class TextLine:
    spans: list[TextSpan] = field(default_factory=list)
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans).strip()

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def avg_fontsize(self) -> float | None:
        values = [span.fontsize for span in self.spans if span.fontsize is not None]
        if not values:
            return None
        return sum(values) / len(values)


@dataclass(slots=True)
class TextBlock:
    lines: list[TextLine] = field(default_factory=list)
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass(slots=True)
class PageTextLayer:
    page_no: int
    width: float
    height: float
    blocks: list[TextBlock] = field(default_factory=list)

    @property
    def lines(self) -> list[TextLine]:
        result: list[TextLine] = []
        for block in self.blocks:
            result.extend(block.lines)
        return result