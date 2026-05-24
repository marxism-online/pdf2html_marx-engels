import sys
print("Загрузка библиотек...", file=sys.stderr, flush=True)

from pdf2html.gui import run

if __name__ == "__main__":
    run()
