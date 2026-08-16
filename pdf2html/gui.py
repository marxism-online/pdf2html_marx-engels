from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog

from .pipeline import PageConverter
from .reader.pdf_text import PdfTextReader
from .utils.pagination import parse_pages_spec
from ._version import __version__

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("pdf2html")
        self.geometry("560x420")
        self.resizable(False, False)

        self._queue: queue.Queue[str | None] = queue.Queue()
        self._running = False

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 16, "pady": (8, 0)}

        # PDF input
        ctk.CTkLabel(self, text="PDF файл", anchor="w").pack(fill="x", **pad)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 0))
        self._pdf_var = ctk.StringVar()
        ctk.CTkEntry(row, textvariable=self._pdf_var, width=420).pack(side="left")
        ctk.CTkButton(row, text="Обзор", width=80, command=self._pick_pdf).pack(side="left", padx=(8, 0))

        # Output folder
        ctk.CTkLabel(self, text="Выходная папка", anchor="w").pack(fill="x", **pad)
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(4, 0))
        self._out_var = ctk.StringVar()
        ctk.CTkEntry(row2, textvariable=self._out_var, width=420).pack(side="left")
        ctk.CTkButton(row2, text="Обзор", width=80, command=self._pick_out).pack(side="left", padx=(8, 0))

        # Pages + Volume on one row
        row3 = ctk.CTkFrame(self, fg_color="transparent")
        row3.pack(fill="x", padx=16, pady=(12, 0))

        left = ctk.CTkFrame(row3, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text="Страницы (необяз.)", anchor="w").pack(anchor="w")
        pages_row = ctk.CTkFrame(left, fg_color="transparent")
        pages_row.pack(anchor="w", pady=(4, 0))
        self._page_from_var = ctk.StringVar()
        self._page_to_var = ctk.StringVar()
        ctk.CTkLabel(pages_row, text="От").pack(side="left")
        ctk.CTkEntry(pages_row, textvariable=self._page_from_var, placeholder_text="1", width=70).pack(side="left", padx=(4, 0))
        ctk.CTkLabel(pages_row, text="До").pack(side="left", padx=(10, 0))
        ctk.CTkEntry(pages_row, textvariable=self._page_to_var, placeholder_text="100", width=70).pack(side="left", padx=(4, 0))

        right = ctk.CTkFrame(row3, fg_color="transparent")
        right.pack(side="left", padx=(16, 0))
        ctk.CTkLabel(right, text="Том (необяз.)", anchor="w").pack(anchor="w")
        self._vol_var = ctk.StringVar()
        ctk.CTkEntry(right, textvariable=self._vol_var, placeholder_text="8", width=100).pack(anchor="w", pady=(4, 0))

        # Progress bar
        self._progress = ctk.CTkProgressBar(self, width=510)
        self._progress.set(0)
        self._progress.pack(padx=16, pady=(16, 0))

        # Status label
        self._status = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self._status.pack(fill="x", padx=16, pady=(4, 0))

        # Log box
        self._log = ctk.CTkTextbox(self, height=100, state="disabled")
        self._log.pack(fill="x", padx=16, pady=(8, 0))

        # Button
        self._btn = ctk.CTkButton(self, text="Конвертировать", command=self._on_convert)
        self._btn.pack(pady=16)

        # Build number, drawn last so it stays on top of the widgets it overlaps
        ctk.CTkLabel(
            self,
            text=f"build {__version__}",
            font=("", 11),
            text_color="gray",
        ).place(relx=1.0, x=-8, y=6, anchor="ne")

    # ------------------------------------------------------------------ pickers

    def _pick_pdf(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self._pdf_var.set(path)
            if not self._out_var.get():
                self._out_var.set(str(Path(path).parent))

    def _pick_out(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self._out_var.set(path)

    # ------------------------------------------------------------------ convert

    def _on_convert(self) -> None:
        if self._running:
            return

        pdf = self._pdf_var.get().strip()
        out_dir = self._out_var.get().strip()
        out = str(Path(out_dir) / Path(pdf).with_suffix(".html").name) if out_dir and pdf else ""
        page_from = self._page_from_var.get().strip()
        page_to = self._page_to_var.get().strip()
        vol_str = self._vol_var.get().strip()

        if not pdf:
            self._set_status("Выберите PDF файл.", error=True)
            return
        if not out_dir:
            self._set_status("Укажите выходную папку.", error=True)
            return

        if page_from or page_to:
            try:
                f = int(page_from) if page_from else None
                t = int(page_to) if page_to else None
            except ValueError:
                self._set_status("Страницы должны быть числами.", error=True)
                return
            if f is not None and t is not None:
                pages_str = f"{f}-{t}"
            elif f is not None:
                pages_str = str(f)
            else:
                pages_str = str(t)
        else:
            pages_str = None

        try:
            selected_pages = parse_pages_spec(pages_str)
        except ValueError as e:
            self._set_status(f"Ошибка в диапазоне страниц: {e}", error=True)
            return

        volume: int | None = None
        if vol_str:
            try:
                volume = int(vol_str)
            except ValueError:
                self._set_status("Том должен быть числом.", error=True)
                return

        self._running = True
        self._btn.configure(state="disabled")
        self._progress.set(0)
        self._log_clear()
        self._set_status("Запуск…")

        thread = threading.Thread(
            target=self._worker,
            args=(pdf, out, selected_pages, volume),
            daemon=True,
        )
        thread.start()
        self._poll_queue()

    def _worker(self, pdf: str, out: str, selected_pages, volume: int | None) -> None:
        try:
            import shutil
            from .cli import _prescan_page_numbers, _prescan_body_fontsize, _parse_volume

            vol = volume if volume is not None else _parse_volume(pdf, None)
            out_dir = Path(out).parent

            self._queue.put("STATUS:Определение нумерации страниц…")
            page_numbers = _prescan_page_numbers(pdf, selected_pages)
            first_content_page = min(page_numbers) if page_numbers else None

            # Only needed for a partial page range — a full-document run
            # already builds up an accurate reference on its own.
            body_fontsize_seed = None
            if selected_pages is not None:
                self._queue.put("STATUS:Определение размера шрифта…")
                body_fontsize_seed = _prescan_body_fontsize(pdf, selected_pages)

            reader = PdfTextReader()
            converter = PageConverter(
                page_numbers=page_numbers,
                first_content_page=first_content_page,
                volume=vol,
                out_dir=out_dir,
                body_fontsize_seed=body_fontsize_seed,
            )

            all_pages = list(reader.iter_pages(pdf, selected_pages=selected_pages))
            total = len(all_pages)

            for idx, (page_no, layout) in enumerate(all_pages, 1):
                self._queue.put(f"PROGRESS:{idx}/{total}")
                self._queue.put(f"STATUS:стр. {page_no} ({idx}/{total})")
                converter.feed(page_no, layout)

            converter.finish()

            out_path = Path(out)
            css_src = Path(__file__).parent / "formatter" / "volume.css"
            css_dst = out_path.with_suffix(".css")
            shutil.copy(css_src, css_dst)

            link_tag = f'<link rel="stylesheet" href="{css_dst.name}">'
            out_path.write_text(link_tag + "\n" + "\n".join(converter.parts) + "\n", encoding="utf-8")

            self._queue.put("STATUS:Готово!")
            self._queue.put("LOG:Сохранено: " + out)
            self._queue.put(None)  # done
        except Exception as e:
            self._queue.put(f"ERROR:{e}")
            self._queue.put(None)

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                if msg is None:
                    self._running = False
                    self._btn.configure(state="normal")
                    self._progress.set(1.0)
                    return
                elif msg.startswith("PROGRESS:"):
                    cur, total = msg[9:].split("/")
                    self._progress.set(int(cur) / int(total))
                elif msg.startswith("STATUS:"):
                    self._set_status(msg[7:])
                elif msg.startswith("LOG:"):
                    self._log_append(msg[4:])
                elif msg.startswith("ERROR:"):
                    self._set_status(msg[6:], error=True)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------ helpers

    def _set_status(self, text: str, error: bool = False) -> None:
        color = "#e05555" if error else "gray"
        self._status.configure(text=text, text_color=color)

    def _log_append(self, text: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n")
        self._log.configure(state="disabled")
        self._log.see("end")

    def _log_clear(self) -> None:
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")


def run() -> None:
    app = App()
    app.mainloop()
