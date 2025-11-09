from .heuristics import detect_paragraphs, detect_headings, detect_quotes
from ..utils.types import PageModel

class StructureAnalyzer:
    def build_page_model(self, page_no: int, layout) -> PageModel:
        pm = PageModel(page_num=page_no)
        pm.heading = detect_headings(layout)
        pm.blocks = detect_paragraphs(layout)
        detect_quotes(pm)
        return pm
