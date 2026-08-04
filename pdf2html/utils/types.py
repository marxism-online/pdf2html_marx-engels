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
    sup: bool = False
    sub: bool = False

@dataclass
class Paragraph:
    inlines: List[Inline]
    align: Align = "JUSTIFY"
    is_quote: bool = False
    is_q_inline: bool = False
    is_small: bool = False
    heading_level: Optional[int] = None

@dataclass
class Heading:
    level: Literal[1, 2, 3]
    text: str
    align: Align = "CENTER"
    bold: bool = False
    offset_right: bool = False

@dataclass
class SignatureBlock:
    left: List[Paragraph]
    right: List[Paragraph]

@dataclass
class PageModel:
    page_num: int
    book_page_num: Optional[int] = None
    running_header: Optional[tuple[str, int]] = None
    author: Optional[str] = None
    work_title: Optional[str] = None
    headings: List[Heading] = field(default_factory=list)
    heading_blocks: list = field(default_factory=list)  # ordered List[Heading | Paragraph]
    blocks: List[Paragraph] = field(default_factory=list)
    footnote_block: Optional[Paragraph] = None
    has_bottom_hr: bool = False
    signature_block: Optional[SignatureBlock] = None
    opening_signature: Optional[SignatureBlock] = None
    is_illustration: bool = False
    image_src: Optional[str] = None

    @property
    def is_blank(self) -> bool:
        return (
            not self.is_illustration
            and not self.blocks
            and not self.headings
            and not self.heading_blocks
            and not self.running_header
            and not self.footnote_block
            and not self.signature_block
            and not self.opening_signature
        )
