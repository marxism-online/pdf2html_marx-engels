import sys
print("Загрузка библиотек...", file=sys.stderr, flush=True)

from pdf2html.cli import main

if __name__ == "__main__":
    main()
