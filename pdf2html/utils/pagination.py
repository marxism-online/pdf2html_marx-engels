from __future__ import annotations


def page_anchor(n: int) -> str:
    return f"s{n}"


def parse_pages_spec(spec: str | None) -> set[int] | None:
    """
    Преобразует строку диапазона страниц в множество 1-based номеров страниц.

    Примеры:
        None -> None
        "" -> None
        "5" -> {5}
        "5-10" -> {5,6,7,8,9,10}
        "1,3,10-12" -> {1,3,10,11,12}
        "7-5" -> {5,6,7}
    """
    if spec is None:
        return None

    spec = spec.strip()
    if not spec:
        return None

    pages: set[int] = set()

    for raw_part in spec.split(","):
        part = raw_part.strip()
        if not part:
            raise ValueError("Empty page item in pages specification")

        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start_text = start_text.strip()
            end_text = end_text.strip()

            if not start_text or not end_text:
                raise ValueError(f"Invalid page range: '{part}'")

            start = int(start_text)
            end = int(end_text)

            if start <= 0 or end <= 0:
                raise ValueError("Pages must be positive integers")

            if start > end:
                start, end = end, start

            pages.update(range(start, end + 1))
        else:
            page = int(part)
            if page <= 0:
                raise ValueError("Pages must be positive integers")
            pages.add(page)

    return pages


def to_pdfminer_page_numbers(selected_pages: set[int] | None) -> list[int] | None:
    """
    Преобразует 1-based номера страниц в 0-based индексы для pdfminer.

    pdfminer.extract_pages(..., page_numbers=[...]) ожидает 0-based индексы.
    """
    if selected_pages is None:
        return None

    return [page_num - 1 for page_num in sorted(selected_pages)]