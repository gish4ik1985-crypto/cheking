"""Тестовая спецификация формы 1 (как КОМПАС): PDF с таблицей «Формат / Зона / Поз. / Обозначение / Наименование /
Кол. / Примечание» над основной надписью. Используется тестами сверки спецификации со сборочным чертежом."""
from __future__ import annotations

import os
import sys

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_samples as ms  # noqa: E402

MM = ms.MM
COLS = [("Формат", 12), ("Зона", 10), ("Поз.", 10), ("Обозначение", 62), ("Наименование", 62), ("Кол.", 12), ("Примечание", 17)]

# строка: (раздел-заголовок) | (формат, зона, поз, обозначение, наименование, кол, примечание)
ROWS_OK = [
    ("sec", "Документация"),
    ("", "", "", "ДТМЛ.333333.001 СБ", "Сборочный чертеж", "", ""),
    ("sec", "Детали"),
    ("А4", "", "1", "ДТМЛ.333333.002", "Пластина", "1", ""),
    ("А4", "", "2", "ДТМЛ.333333.003", "Планка", "1", ""),
    ("", "", "3", "ДТМЛ.333333.004", "Втулка", "2", ""),
    ("sec", "Стандартные изделия"),
    ("", "", "4", "", "Болт М8-6gх20.58 ГОСТ 7798-70", "4", ""),
]


def make_spec(path: str, des: str = "ДТМЛ.333333.001", name: str = "Кронштейн", rows=None) -> str:
    rows = rows or ROWS_OK
    doc = pymupdf.open()
    pw, ph = 210, 297
    page = doc.new_page(width=pw * MM, height=ph * MM)
    ms._title_block(page, pw, ph, des, name, "", "", rotated=False)
    x0, top, hdr, rh = 20.0, 5.0, 15.0, 8.0
    stamp_top = ph - 60
    sh = page.new_shape()
    xs = [x0]
    for _, w in COLS:
        xs.append(xs[-1] + w)
    for x in xs:
        sh.draw_line(pymupdf.Point(x * MM, top * MM), pymupdf.Point(x * MM, stamp_top * MM))
    y = top
    ys = [y, y + hdr]
    while ys[-1] + rh <= stamp_top:
        ys.append(ys[-1] + rh)
    for yy in ys:
        sh.draw_line(pymupdf.Point(x0 * MM, yy * MM), pymupdf.Point(xs[-1] * MM, yy * MM))
    sh.finish(width=0.5, color=(0, 0, 0))
    sh.commit()
    for (title, _), xa in zip(COLS, xs):
        ms._t(page, xa + 0.5, top + 9, title, 2.4)
    for k, row in enumerate(rows):
        yy = ys[2 + k] if 2 + k < len(ys) else None
        if yy is None:
            break
        if row[0] == "sec":
            ms._t(page, xs[4] + 6, yy + 5.5, row[1], 3.5)
            continue
        for val, xa in zip(row, xs):
            if val:
                ms._t(page, xa + 1, yy + 5.5, val, 3.5)
    doc.save(path)
    return path


if __name__ == "__main__":
    out = os.path.join(ms.ROOT, "samples", "test", "ДТМЛ.333333.001 - Спецификация.pdf")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    print(make_spec(out))
