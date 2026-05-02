# pdf2html

Конвертер PDF → HTML. Читает PDF постранично, анализирует структуру текста и генерирует HTML.

## Запуск

```bash
python3 -m pdf2html.cli input.pdf --out output.html
python3 -m pdf2html.cli input.pdf --pages 1-10 --out output.html
python3 -m pdf2html.cli input.pdf --pages 1,3,7-9 --out output.html
```

## Архитектура

```
pdf2html/
├── cli.py                  # точка входа, argparse
├── reader/
│   └── pdf_text.py         # чтение PDF через pdfminer, итерация по страницам
├── analyzer/
│   ├── layout.py           # StructureAnalyzer — сборка PageModel
│   ├── heuristics.py       # detect_headings, detect_paragraphs, detect_quotes
│   └── text_extractor.py   # извлечение текстового слоя (координаты строк)
├── formatter/
│   ├── html_rules.py       # HtmlFormatter — рендеринг через Jinja2
│   ├── jinja_env.py        # настройка Jinja2
│   └── templates/          # first_page.html.j2, page.html.j2
└── utils/
    ├── types.py             # PageModel, Paragraph, Heading, Inline, Align
    ├── pagination.py        # parse_pages_spec, page_anchor
    └── text_layer.py        # PageTextLayer, TextLine (координаты)
```

## Типы данных (utils/types.py)

- `PageModel` — модель страницы: heading, blocks, footnote_block, has_bottom_hr
- `Paragraph` — список Inline, выравнивание, флаги is_quote / is_q_inline
- `Heading` — уровень (2/3), текст, выравнивание
- `Inline` — текст с атрибутами: italic, bold, small, em

## Зависимости

- `pdfminer.six` — извлечение текста из PDF
- `jinja2` — шаблоны HTML

## Тесты

```bash
pytest tests/
```

## Текущее состояние эвристик

- `detect_headings` — заглушка, всегда возвращает `None`
- `detect_paragraphs` — работает: разбивка по вертикальному зазору и смещению левого края
- `detect_quotes` — заглушка, цитаты не выделяются
- Сноски (`footnote_block`) — не реализованы

## Ветки

- `master` — стабильная
- `agent/heuristics` — разработка эвристик

## Другие материалы

- volume08.pdf - образец PDF-документа, откуда берем фрагменты для форматирования
- volume08.htm - образец html-документа, к какому виду должно быть приведено.
