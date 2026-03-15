from __future__ import annotations

from ..utils.pagination import page_anchor
from ..utils.types import PageModel
from .jinja_env import env


class HtmlFormatter:
    def render_first_page(self, pm: PageModel) -> str:
        tmpl = env.get_template("first_page.html.j2")
        return tmpl.render(pm=pm, anchor=page_anchor(pm.page_num)).strip()

    def render_page(self, pm: PageModel) -> str:
        tmpl = env.get_template("page.html.j2")
        return tmpl.render(
            pm=pm,
            anchor=page_anchor(pm.page_num),
            nextpage="<hr><!--nextpage-->",
        ).strip()