# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

pdfminer_datas = collect_data_files("pdfminer")

a = Analysis(
    ["pdf2html_entry.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("pdf2html/formatter/templates", "pdf2html/formatter/templates"),
        ("pdf2html/formatter/volume.css", "pdf2html/formatter"),
    ] + pdfminer_datas,
    hiddenimports=[
        "pdfminer.high_level",
        "pdfminer.layout",
        "pdfminer.converter",
        "pdfminer.pdfpage",
        "pdfminer.pdfinterp",
        "pdfminer.image",
        "pdfminer.utils",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytesseract", "tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="pdf2html",
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)
