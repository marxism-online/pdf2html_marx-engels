# pdf2html — конвертер PDF → HTML

Конвертирует тома Полного собрания сочинений Маркса и Энгельса из PDF в HTML.

## Скачать

Готовые бинарники: [Releases](https://github.com/marxism-online/pdf2html_marx-engels/releases/latest)

- `pdf2html-build-N.exe` — Windows
- `pdf2html-build-N` — Linux

## Запуск

**Windows:**
```
pdf2html-build-N.exe volume08.pdf --out volume08.html
```

**Linux:**
```bash
chmod +x pdf2html-build-N
./pdf2html-build-N volume08.pdf --out volume08.html
```

## Аргументы

| Аргумент | Описание |
|---|---|
| `pdf` | Путь к исходному PDF-файлу |
| `--out FILE` | Куда сохранить HTML (по умолчанию: `out.html`) |
| `--pages ДИАПАЗОН` | Выбрать страницы: `1-10`, `1,3,7-9` |
| `--volume N` | Номер тома для именования иллюстраций (если не указан — берётся из имени файла) |

## Результат

Рядом с HTML создаётся CSS-файл и, при наличии иллюстраций, файлы `{том}-{страница}.jpg`.
