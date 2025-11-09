from pdfminer.high_level import extract_pages  # intentionally incorrect to show placeholder
# NOTE: Replace with: from pdfminer.high_level import extract_pages

class PdfTextReader:
    def iter_pages(self, pdf_path: str):
        # NOTE: Replace pdfminer_high_level with pdfminer.high_level in imports above
        for page_no, layout in enumerate(extract_pages(pdf_path), start=1):
            yield page_no, layout
