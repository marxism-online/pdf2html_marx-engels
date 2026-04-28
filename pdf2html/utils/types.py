from dataclasses import dataclass, field
from typing import List, Optional, Literal

Align = Literal["LEFT", "RIGHT", "CENTER", "JUSTIFY"]

@dataclass
class Inline:
    text: str
    italic: bool = False
    bold: bool = False
    small: bool = False
    em: bool = False

@dataclass
class Paragraph:
    inlines: List[Inline]
    align: Align = "JUSTIFY"
    is_quote: bool = False
    is_q_inline: bool = False
    is_small: bool = False

@dataclass
class Heading:
    level: Literal[2, 3]
    text: str
    align: Align = "CENTER"
    bold: bool = False

@dataclass
class PageModel:
    page_num: int
    book_page_num: Optional[int] = None
    top_title: Optional[str] = None
    author: Optional[str] = None
    work_title: Optional[str] = None
    headings: List[Heading] = field(default_factory=list)
    blocks: List[Paragraph] = field(default_factory=list)
    footnote_block: Optional[Paragraph] = None
    has_bottom_hr: bool = False
