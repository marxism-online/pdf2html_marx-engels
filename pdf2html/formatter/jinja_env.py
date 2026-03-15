from __future__ import annotations

from pathlib import Path

from jinja2 import Environment
from jinja2 import FileSystemLoader
from jinja2 import select_autoescape


def _render_inlines(p) -> str:
    parts: list[str] = []

    for inline in p.inlines:
        t = inline.text
        if inline.em:
            t = f"<em>{t}</em>"
        if inline.italic:
            t = f"<i>{t}</i>"
        if inline.bold:
            t = f"<b>{t}</b>"
        if inline.small:
            t = f"<small>{t}</small>"
        parts.append(t)

    return "".join(parts)


TPL_DIR = Path(__file__).with_name("templates")

env = Environment(
    loader=FileSystemLoader(str(TPL_DIR)),
    autoescape=select_autoescape([]),
    trim_blocks=True,
    lstrip_blocks=True,
)

env.filters["render_inlines"] = _render_inlines