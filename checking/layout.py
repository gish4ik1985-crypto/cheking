"""Расположение размеров на чертеже (ГОСТ 2.307-2011, п. 5.1–5.2 и рисунки нанесения размеров).

* D31 — размерные надписи накладываются друг на друга или на другой текст чертежа;
* D32 — расстояние от размерной линии до контура (длина выносных линий) меньше 10 мм;
* D33 — расстояние между параллельными размерными линиями меньше 7 мм.

Размерная линия — отрезок под текстом размера (прямой горизонтальной или вертикальной надписи) с выносными линиями
на концах; расстояние до контура оценивается по длине выносных линий: они идут от размерной линии к контуру и
начинаются в 1–2 мм от него. Размеры, у которых выносных линий нет (диаметры и радиусы на самом изображении,
размеры на выносных полках), не проверяются."""
from __future__ import annotations

import re

from .model import Drawing, WARNING, INFO, CAT_DIM
from .titleblock import excluded

STD = "ГОСТ 2.307-2011"
MIN_CONTOUR = 10.0
MIN_PARALLEL = 7.0
TOL = 2.0          # оценка по выносным линиям грубая (±2 мм): замечание — только при явном нарушении


def _overlap(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _minor(t: str) -> bool:
    """Надписи, которые по построению стоят вплотную: отклонения (+0,2 / -0,1), номера пунктов, одиночные знаки."""
    return len(t) < 2 or bool(re.fullmatch(r"[+\-−±]?\s*\d+(?:[.,]\d+)?|\d+[.)]|IT\d+|[^\w⌀]+", t))


def _area(b) -> float:
    return max(b[2] - b[0], 0.01) * max(b[3] - b[1], 0.01)


def _lines_of(drw: Drawing, pg: int):
    """Горизонтальные и вертикальные отрезки листа: (a, b, c) — диапазон по оси и положение."""
    hor, ver = [], []
    for x1, y1, x2, y2 in (drw.facts.get("_segments") or {}).get(pg, []):
        if abs(y1 - y2) < 0.15 and abs(x2 - x1) > 2.5:
            hor.append((min(x1, x2), max(x1, x2), (y1 + y2) / 2))
        elif abs(x1 - x2) < 0.15 and abs(y2 - y1) > 2.5:
            ver.append((min(y1, y2), max(y1, y2), (x1 + x2) / 2))
    return hor, ver


def _chain(segs: list, gap: float = 8.0) -> list:
    """Склейка коротких (до 12 мм) отрезков на одной прямой с просветом до gap мм: штрихи осевых и штрихпунктирных линий
    становятся одной длинной линией (выносной линией она быть не может)."""
    out = []
    for a, b, c in sorted(segs, key=lambda s: (round(s[2] * 5), s[0])):
        if out and abs(out[-1][2] - c) < 0.2 and a - out[-1][1] <= gap and b - a <= 12 and out[-1][3] <= 12:
            out[-1] = (out[-1][0], max(out[-1][1], b), out[-1][2], out[-1][3])
        else:
            out.append((a, b, c, b - a))
    return [(a, b, c) for a, b, c, _ in out]


def _dim_line(d, hor, ver, chor, cver):
    """(положение размерной линии, ось, длина выносной слева/сверху, справа/снизу) или None."""
    x0, y0, x1, y1 = d.bbox
    if d.vertical:                       # надпись повёрнута: линия вертикальная, слева или справа от текста
        cand = [v for v in ver if abs(v[2] - x1) <= 3.5 or abs(v[2] - x0) <= 3.5]
        cand = [v for v in cand if v[0] <= d.bbox[1] + 1 and v[1] >= d.bbox[3] - 1]
        cross = chor
    else:
        cand = [h for h in hor if (-1.5 <= h[2] - y1 <= 3.5 or -1.5 <= y0 - h[2] <= 3.5) and h[0] <= x0 + 1 and h[1] >= x1 - 1]
        cross = cver
    if not cand:
        return None
    ln = min(cand, key=lambda s: abs(s[2] - ((y1 if not d.vertical else x1))))
    a, b, pos = ln
    lens = []
    for end in (a, b):
        best = None
        for e in cross:                   # выносная линия: на конце размерной линии, пересекает её или касается
            if abs(e[2] - end) > 0.8:
                continue
            lo, hi = e[0], e[1]
            if lo - 1.0 <= pos <= hi + 1.0:
                length = max(pos - lo, hi - pos)
                over = min(pos - lo, hi - pos)
                if over <= 6.0:           # выступ за размерную линию 1–5 мм
                    best = max(best or 0.0, length)
        lens.append(best)
    return pos, (a, b), lens, ln


def check_layout(drw: Drawing, cfg: dict) -> None:
    if drw.ocr:
        return
    dims = [d for d in drw.dims if d.bbox and d.page == drw.first_page]
    if not dims:
        return
    # --- D31: наложение надписей (по строкам текста: рамки размеров могут включать соседние допуски) ---
    texts = [ln for ln in drw.lines if ln.page == drw.first_page and not excluded(drw, ln) and ln.text.strip()]
    texts.sort(key=lambda ln: ln.bbox[0])
    seen = set()
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            if b.bbox[0] >= a.bbox[2]:
                break
            if (abs(a.dir[0]) > 0.7) != (abs(b.dir[0]) > 0.7):
                continue                                  # разное направление надписей — не сравниваем
            ov = _overlap(a.bbox, b.bbox)
            if ov <= 0.3 * min(_area(a.bbox), _area(b.bbox)):
                continue
            ta, tb = a.text.strip(), b.text.strip()
            if min(a.size, b.size) < 0.8 * max(a.size, b.size):
                continue                                      # индекс или отклонение мелким шрифтом
            if _minor(ta) or _minor(tb):
                continue
            key = (round(a.bbox[0]), round(a.bbox[1]), ta, tb)
            if key in seen:
                continue
            seen.add(key)
            drw.add(WARNING, "D31", CAT_DIM, f"Надписи «{ta[:40]}» и «{tb[:40]}» наложены друг на друга — "
                    f"их нужно разнести", a.page, a.bbox, STD)

    # --- D32/D33: расстояния ---
    hor, ver = _lines_of(drw, drw.first_page)
    chor, cver = _chain(hor), _chain(ver)
    found = []
    for d in dims:
        if d.kind not in ("linear", "diameter"):
            continue
        r = _dim_line(d, hor, ver, chor, cver)
        if r:
            found.append((d, r))
    for d, (pos, (a, b), lens, _) in found:
        ls = [x for x in lens if x is not None]
        if len(ls) == 2 and min(ls) + 2.0 < MIN_CONTOUR - TOL:
            drw.add(WARNING, "D32", CAT_DIM, f"Размер «{d.raw.strip()}»: размерная линия на расстоянии ≈{min(ls) + 2:.0f} мм от "
                    f"контура — должно быть не менее {MIN_CONTOUR:.0f} мм (выносные линии {min(ls):.1f} мм)",
                    d.page, d.bbox, STD)
    flagged = set()
    for i, (d, (pos, (a, b), _, ln)) in enumerate(found):
        for e, (pos2, (a2, b2), _, ln2) in found[i + 1:]:
            if d.vertical != e.vertical:
                continue
            gap = abs(pos - pos2)
            share = min(b, b2) - max(a, a2)
            if 2.5 < gap < MIN_PARALLEL - 1.0 and share > max(4.0, 0.5 * min(b - a, b2 - a2)) and (d.page, round(pos), round(pos2)) not in flagged:
                flagged.add((d.page, round(pos), round(pos2)))
                drw.add(WARNING, "D33", CAT_DIM, f"Размерные линии «{d.raw.strip()}» и «{e.raw.strip()}» расположены на "
                        f"расстоянии {gap:.1f} мм — между параллельными размерными линиями должно быть не менее "
                        f"{MIN_PARALLEL:.0f} мм", d.page, d.bbox, STD)
    drw.facts["dimlines"] = len(found)
