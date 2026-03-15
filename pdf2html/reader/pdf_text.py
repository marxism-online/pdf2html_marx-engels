from __future__ import annotations

from collections.abc import Iterator

from pdfminer.high_level import extract_pages


class PdfTextReader:
    def iter_pages(
        self,
        pdf_path: str,
        selected_pages: set[int] | None = None,
    ) -> Iterator[tuple[int, object]]:
        """
        Итерирует только по нужным страницам PDF.

        Аргументы:
            pdf_path:
                Путь к PDF-файлу.
            selected_pages:
                Множество 1-based номеров страниц.
                Если None, читаются все страницы.

        Возвращает:
            tuple(page_no, layout), где page_no — 1-based номер страницы.
        """
        if selected_pages is None:
            for page_no, layout in enumerate(extract_pages(pdf_path), start=1):
                yield page_no, layout
            return

        page_numbers = [page_num - 1 for page_num in sorted(selected_pages)]

        for zero_based_page_no, layout in zip(
            page_numbers,
            extract_pages(pdf_path, page_numbers=page_numbers),
            strict=False,
        ):
            yield zero_based_page_no + 1, layout