"""Собирает данные классификатора ЕСКД из справки .chm (Общесоюзный классификатор ЕСКД, 1.79.100, сборка dwg.ru).

Порядок: распаковать .chm архиватором 7-Zip в пустую папку, затем
    python tools/build_classifier.py <папка_с_распакованным_chm>
Результат в папке classifier/ рядом с программой:
    eskd.json.gz  — коды и названия (47 классов, 296 подклассов, 1753 группы, 10 442 подгруппы, 67 415 видов)
                    и алфавитный указатель названий деталей классов 71–76;
    pz.html       — «Иллюстрированный определитель деталей классов 71–76. Пояснительная записка»;
    vv.html       — «Введение» к классификатору;
    img/pz/*.jpg  — рисунки пояснительной записки.
Исходные страницы в кодировке cp1251 с JavaScript; здесь они переводятся в чистый HTML без скриптов."""
from __future__ import annotations

import glob
import gzip
import html
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "classifier")

CSS = """<style>
:root { color-scheme: light dark; }
body { font: 15px/1.55 system-ui, "Segoe UI", sans-serif; max-width: 980px; margin: 0 auto; padding: 16px 20px 48px; }
h1, h2, h3 { line-height: 1.25; } img { max-width: 100%; height: auto; }
table { border-collapse: collapse; margin: 10px 0; } td, th { border: 1px solid #8886; padding: 3px 8px; vertical-align: top; }
a { color: #2563eb; } @media (prefers-color-scheme: dark) { a { color: #7aa7ff; } }
</style>"""


def read(path: str) -> str:
    return open(path, "rb").read().decode("cp1251", errors="replace")


def codes(src: str) -> dict[str, str]:
    data: dict[str, str] = {}
    rx = re.compile(r"\['(\d{2,6}\.{0,4})',\s*'((?:[^'\\]|\\.)*)'\]")
    for f in sorted(glob.glob(os.path.join(src, "script*_den.js"))):
        for m in rx.finditer(read(f)):
            data[m.group(1).replace(".", "")] = m.group(2).replace("\\'", "'").strip()
    return data


def alphabet(src: str) -> dict[str, list[str]]:
    """Алфавитный указатель классов 71–76: название → коды (как в справке; сопоставлять по нему название и код не стоит)."""
    t = read(os.path.join(src, "abc71_76_den.html"))
    idx: dict[str, list[str]] = {}
    for name, cell in re.findall(r"<tr>\s*<td>([^<]+)</td>\s*<td>(.*?)</td>\s*</tr>", t, re.S):
        found = re.findall(r"<font>(\d{6})</font>", cell)
        if found:
            idx[html.unescape(re.sub(r"\s+", " ", name)).strip()] = found
    return idx


def clean_page(src_file: str, title: str, image_prefix: str | None = None) -> str:
    t = read(src_file)
    t = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", t, flags=re.S | re.I)
    i = t.lower().find("<body")
    t = t[t.find(">", i) + 1:] if i >= 0 else t
    t = re.sub(r"(?is)\s+on\w+\s*=\s*(\"[^\"]*\"|'[^']*')", "", t)           # onclick, onmouseover…
    t = re.sub(r"(?i)<a\s+href=[\"'](?!#)[^\"']*[\"'][^>]*>(.*?)</a>", r"\1", t, flags=re.S)  # ссылки на другие страницы справки
    t = re.sub(r"(?i)\s+bgcolor=[\"'][^\"']*[\"']", "", t)                  # белая подложка ломает тёмную тему
    t = re.sub(r"(?i)<p id=\"p01\"></p>", "", t)
    # шапка со ссылками на другие страницы справки: до первого заголовка «КЛАССИФИКАТОР»
    j = re.search(r"КЛАССИФИКАТОР\s+ЕСКД|ВВЕДЕНИЕ", t)
    if j:
        k = t.rfind("</table>", 0, j.start())
        if 0 <= k < j.start() and j.start() - k < 600:
            t = t[k + 8:]
    t = re.sub(r"(?i)<img\s+src\s*=\s*[\"']pz/([^\"']+)[\"']\s*>", lambda m: f'<img src="img/pz/{m.group(1)}" loading="lazy" alt="">', t)
    t = t.replace("</body>", "").replace("</html>", "")
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{title}</title>{CSS}</head><body>{t}</body></html>")


def main(src: str) -> None:
    os.makedirs(os.path.join(OUT, "img", "pz"), exist_ok=True)
    data = codes(src)
    out = {"version": "1.79.100", "source": "Общесоюзный классификатор ЕСКД (справка .chm, сборка dwg.ru)",
           "codes": data, "alphabet": alphabet(src)}
    with gzip.open(os.path.join(OUT, "eskd.json.gz"), "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(OUT, "pz.html"), "w", encoding="utf-8") as f:
        f.write(clean_page(os.path.join(src, "pz.html"), "Классификатор ЕСКД: пояснительная записка (классы 71–76)"))
    with open(os.path.join(OUT, "vv.html"), "w", encoding="utf-8") as f:
        f.write(clean_page(os.path.join(src, "vv.html"), "Классификатор ЕСКД: введение"))
    n = 0
    for p in glob.glob(os.path.join(src, "pz", "*.jpg")):
        shutil.copy(p, os.path.join(OUT, "img", "pz", os.path.basename(p)))
        n += 1
    print(f"кодов {len(data)}, указатель {len(out['alphabet'])}, рисунков {n} → {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        sys.exit(__doc__)
    main(sys.argv[1])
