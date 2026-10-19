"""Собирает HTML-страницы ТЗ из docs/tz/*.md по шаблону docs/tz/_template.html.

Запуск: python tools/build_tz.py
Markdown встраивается в страницу и рендерится в браузере (marked, mermaid, значки Tabler с CDN).
"""
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "docs" / "tz"


def main() -> int:
    template = (ROOT / "_template.html").read_text(encoding="utf-8")
    files = sorted(p for p in ROOT.glob("[0-9][0-9]_*.md"))
    pages = []
    for p in files:
        text = p.read_text(encoding="utf-8")
        m = re.search(r"^#\s+(.+)$", text, re.M)
        pages.append((p, m.group(1).strip() if m else p.stem))
    for p, title in pages:
        text = p.read_text(encoding="utf-8")
        if "</script>" in text:
            print(f"{p.name}: содержит </script>, нельзя встроить", file=sys.stderr)
            return 1
        nav = "".join(
            '<a href="{}"{}>{}</a>'.format(
                q.with_suffix(".html").name,
                ' class="cur"' if q == p else "",
                html.escape(re.sub(r"^\d+\.\s*", "", t) if q != files[0] else "Содержание"),
            )
            for q, t in pages
        )
        out = template.replace("__TITLE__", html.escape(title)).replace("__NAV__", nav).replace("__MD__", text)
        p.with_suffix(".html").write_text(out, encoding="utf-8")
        print("собрано", p.with_suffix(".html").name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
