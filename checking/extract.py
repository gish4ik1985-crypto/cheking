"""Сборка размеров (номинал + отклонения/поля, стоящие отдельными строками), ТТ и шероховатости."""
from __future__ import annotations

import re

from .dimparse import parse_dimension, parse_dev, is_field_only, is_count_only
from .model import Dimension, Drawing, TextLine
from .textnorm import CYR_TO_LAT, ocr_fix, to_float
from .titleblock import excluded

CYR = re.compile(r"[А-Яа-яЁё]")
ROUGH = re.compile(r"^(R[aаzZ])\s*(\d+(?:[.,]\d+)?)")
TT_ITEM = re.compile(r"^(\d{1,2})[\s.)]+\S")
TT_MARK = re.compile(r"\d{1,2}[.)]")
# надписи изображений на поле чертежа, а не пункты ТТ: «ОН-0020.012 Балка (1:4)», «5 элементов», «Рис. 1 …»
VIEW_NOTE = re.compile(r"\(\s*\d+(?:,\d+)?\s*:\s*\d+(?:,\d+)?\s*\)|^\d+\s*элемент|^Рис\.\s*\d")


def _up(d):
    """Единичный вектор «вверх» для строки с направлением d (y вниз)."""
    return d[1], -d[0]


def _proj(pt, d):
    u = pt[0] * d[0] + pt[1] * d[1]
    n = _up(d)
    v = pt[0] * n[0] + pt[1] * n[1]
    return u, v


def _uv_box(ln: TextLine, d):
    xs = (ln.bbox[0], ln.bbox[2])
    ys = (ln.bbox[1], ln.bbox[3])
    pts = [_proj((x, y), d) for x in xs for y in ys]
    us = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    return min(us), max(us), min(vs), max(vs)


def _same_dir(a, b) -> bool:
    return a[0] * b[0] + a[1] * b[1] > 0.97


def _is_text_line(ln: TextLine) -> bool:
    t = ln.text
    letters = len(CYR.findall(t))
    return letters >= 4 and len(t) >= 7


RA_SERIES = {0.012, 0.025, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.3, 12.5, 25.0, 50.0, 100.0,
             0.032, 0.063, 0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 10.0, 16.0, 20.0, 32.0, 40.0, 63.0, 80.0}


def _is_roughness_sign(ln: TextLine, segs: list) -> bool:
    """Число — значение шероховатости, если прямо под ним знак √ (ГОСТ 2.309): две линии под ~60°
    к строке, сходящиеся в нижней вершине. У размерных и выносных линий такой «галочки» нет."""
    d = ln.dir
    u0, u1, v0, v1 = _uv_box(ln, d)
    h = max(v1 - v0, 1.5)
    near = []
    for (x1, y1, x2, y2) in segs:
        a, b = _proj((x1, y1), d), _proj((x2, y2), d)
        if max(a[0], b[0]) < u0 - 2 * h or min(a[0], b[0]) > u1 + 2 * h:
            continue
        if max(a[1], b[1]) < v0 - 3 * h or min(a[1], b[1]) > v1 + h:
            continue
        low, high = (a, b) if a[1] < b[1] else (b, a)
        du, dv = high[0] - low[0], high[1] - low[1]
        L = (du * du + dv * dv) ** 0.5
        if L > 0.8 and 0.75 < dv / L < 0.95:          # 50°…70° к строке, вверх от вершины
            near.append((low, du))
    for i, (p, du1) in enumerate(near):
        if not (u0 - 0.6 * h <= p[0] <= u1 + 0.6 * h and v0 - 2.0 * h <= p[1] <= v0 + 0.3 * h):
            continue
        for q, du2 in near[i + 1:]:
            if abs(p[0] - q[0]) < 0.4 and abs(p[1] - q[1]) < 0.4 and du1 * du2 < 0:
                return True
    return False


def _on_shelf(ln: TextLine, segs: list) -> bool:
    """Номер стоит на полке линии-выноски: под текстом горизонтальная полка, от её конца — наклонная выноска."""
    if abs(ln.dir[0] - 1) > 0.05:
        return False
    w = ln.bbox[2] - ln.bbox[0]
    for (x1, y1, x2, y2) in segs:
        if abs(y1 - y2) > 0.2:
            continue
        a, b, y = min(x1, x2), max(x1, x2), (y1 + y2) / 2
        if not (-0.5 < y - ln.bbox[3] < 2.0 and a <= ln.bbox[0] + 1 and b >= ln.bbox[2] - 1 and b - a < 80):
            continue
        for (p1, q1, p2, q2) in segs:
            L = ((p2 - p1) ** 2 + (q2 - q1) ** 2) ** 0.5
            if L < 6 or abs(q2 - q1) < 0.15 * L or abs(p2 - p1) < 0.15 * L:
                continue
            for ex, ey in ((a, y), (b, y)):
                if min(abs(p1 - ex) + abs(q1 - ey), abs(p2 - ex) + abs(q2 - ey)) < 0.6:
                    return True
    return False


def _table_value(ln: TextLine, labels: list) -> bool:
    """Число в таблице (параметры зубчатого колеса и т.п.): слева на той же строке — текстовая подпись."""
    d = ln.dir
    u0, u1, v0, v1 = _uv_box(ln, d)
    for lb in labels:
        if lb is ln or lb.page != ln.page or not _same_dir(lb.dir, d):
            continue
        a0, a1, b0, b1 = _uv_box(lb, d)
        if min(v1, b1) - max(v0, b0) > 0.6 * min(v1 - v0, b1 - b0) and a1 < u0 and u0 - a1 < 40:
            return True
    return False


def _in_table_cell(ln: TextLine, segs: list) -> bool:
    """Текст в ячейке таблицы: линии сетки сверху и снизу, слева и справа, и они замыкаются в прямоугольник
    (вертикали проходят от нижней линии до верхней). Контур детали вокруг размера так не выглядит."""
    d = ln.dir
    u0, u1, v0, v1 = _uv_box(ln, d)
    h = max(v1 - v0, 1.5)
    hor, ver, hor_all = [], [], []
    for (x1, y1, x2, y2) in segs:
        a, b = _proj((x1, y1), d), _proj((x2, y2), d)
        du, dv = abs(b[0] - a[0]), abs(b[1] - a[1])
        if du > 0 and dv < 0.02 * du:
            vv = (a[1] + b[1]) / 2
            hor_all.append((min(a[0], b[0]), max(a[0], b[0]), vv))
            if v0 - 1.2 * h <= vv <= v1 + 1.2 * h and not (v0 < vv < v1):
                hor.append((min(a[0], b[0]), max(a[0], b[0]), vv))
        elif dv > 0 and du < 0.02 * dv:
            uu = (a[0] + b[0]) / 2
            if u0 - 30 <= uu <= u1 + 60 and not (u0 < uu < u1):
                ver.append((min(a[1], b[1]), max(a[1], b[1]), uu))
    tops = [x for x in hor if x[2] >= v1 and x[0] <= u0 and x[1] >= u1]
    bots = [x for x in hor if x[2] <= v0 and x[0] <= u0 and x[1] >= u1]
    for t in tops:
        for bt in bots:
            left = [x for x in ver if x[2] <= u0 and x[0] <= bt[2] + 0.5 and x[1] >= t[2] - 0.5]
            right = [x for x in ver if x[2] >= u1 and x[0] <= bt[2] + 0.5 and x[1] >= t[2] - 0.5]
            if left and right:
                lu, ru = max(x[2] for x in left), min(x[2] for x in right)
                if t[0] <= lu + 0.5 and t[1] >= ru - 0.5 and bt[0] <= lu + 0.5 and bt[1] >= ru - 0.5:
                    if _dimension_frame(ver, hor_all, lu, ru, bt[2], t[2]):
                        continue
                    return True
    return False


def _overshoot(ver: list, uu: float, line_v: float, down: bool) -> float | None:
    for a, b, u in ver:
        if abs(u - uu) > 0.3:
            continue
        if down and b >= line_v - 0.3 and 0.5 <= line_v - a <= 6:
            return a
        if not down and a <= line_v + 0.3 and 0.5 <= b - line_v <= 6:
            return b
    return None


def _dimension_frame(ver: list, hor_all: list, lu: float, ru: float, bot_v: float, top_v: float) -> bool:
    """«Клетка» из контура детали, двух выносных и размерной линии — не ячейка таблицы: выносные линии
    выходят за размерную на 1…5 мм (ГОСТ 2.307) и там ничем не замыкаются; у таблицы вертикали либо
    кончаются на линии строки, либо идут до следующей строки."""
    for line_v, down in ((bot_v, True), (top_v, False)):
        el, er = _overshoot(ver, lu, line_v, down), _overshoot(ver, ru, line_v, down)
        if el is None or er is None:
            continue
        closed = any(abs(v - e) < 0.5 and x0 <= lu + 0.5 and x1 >= ru - 0.5
                     for x0, x1, v in hor_all for e in (el, er))
        if not closed:
            return True
    return False


def extract(drw: Drawing) -> None:
    lines = [ln for ln in drw.lines if not excluded(drw, ln)]

    # 1) шероховатость
    for ln in lines:
        m = ROUGH.match(ln.text.strip())
        if m:
            p = drw.page_info(ln.page)
            general = ("(" in ln.text) or (ln.bbox[1] < 30 and ln.bbox[0] > p.width - 75)
            param = "Ra" if m.group(1)[1] in "aAаА" else "Rz"
            drw.roughness.append({"param": param, "value": to_float(m.group(2)), "raw": ln.text.strip(),
                                  "general": general, "page": ln.page, "bbox": ln.bbox,
                                  "cyrillic": m.group(1)[1] in "аА"})
            ln.used = True

    # 2) технические требования и надписи
    tt_lines = [ln for ln in lines if not ln.used and _is_text_line(ln) and abs(ln.dir[0] - 1) < 0.05
                and parse_dimension(ln.text) is None and is_count_only(ln.text) is None
                and not VIEW_NOTE.search(ln.text)]
    tt_lines.sort(key=lambda l: (l.page, l.bbox[1], l.bbox[0]))
    # Solid Edge выводит номера пунктов ТТ («1.», «2.») отдельными надписями слева от текста пункта
    numbered: dict[int, str] = {}
    for mk in lines:
        if mk.used or not TT_MARK.fullmatch(mk.text.strip()) or abs(mk.dir[0] - 1) > 0.05:
            continue
        h = max(mk.bbox[3] - mk.bbox[1], 2.0)
        for t in tt_lines:
            if t.page == mk.page and abs(t.cy - mk.cy) < 0.5 * h and 0 <= t.bbox[0] - mk.bbox[2] < 6:
                numbered[id(t)] = mk.text.strip().rstrip(".)")
                mk.used = True
                break
    # строки ТТ, разорванные выравниванием по ширине («1. Конструкция    сварная.»), — в одну
    rows: list[list[TextLine]] = []
    for ln in tt_lines:
        ln.used = True
        last = rows[-1][-1] if rows else None
        if (last and last.page == ln.page and abs(last.cy - ln.cy) < 0.4 * max(ln.size, 2.5)
                and 0 <= ln.bbox[0] - last.bbox[2] < 60):
            rows[-1].append(ln)
        else:
            rows.append([ln])
    items: list[list] = []
    for row in rows:
        ln = row[0]
        text_row = " ".join(x.text for x in row)
        prev = items[-1] if items else None
        cont = (prev and id(ln) not in numbered and not TT_ITEM.match(text_row) and prev[1].page == ln.page
                and 0 < ln.bbox[1] - prev[1].bbox[1] < 1.9 * max(ln.size, 2.5) + 2
                and abs(ln.bbox[0] - prev[2]) < 15)
        if cont:
            prev[0] += " " + text_row
            prev[1] = ln
        else:
            text = f"{numbered[id(ln)]}. {text_row}" if id(ln) in numbered else text_row
            items.append([text, ln, ln.bbox[0], ln])
    drw.tt = [ocr_fix(i[0]) if drw.ocr else i[0] for i in items]
    drw.tt_lines = tt_lines
    drw.facts["_tt_items"] = [(drw.tt[k], i[3].page, i[3].bbox) for k, i in enumerate(items)]
    # короткие числа внутри строк ТТ («±IT14/2», «HRC 42…46») — часть текста, а не размеры
    for ln in lines:
        if ln.used or len(ln.text) > 6:
            continue
        for t in tt_lines:
            if t.page == ln.page and t.bbox[0] - 2 <= ln.cx <= t.bbox[2] + 8 and t.bbox[1] - 3 <= ln.cy <= t.bbox[3] + 3:
                ln.used = True
                break
    for item in drw.tt:
        if re.search(r"(?i)неуказ|остальн", item):
            for m in re.finditer(r"(Ra|Rz)\s*(\d+(?:[.,]\d+)?)", item):
                drw.roughness.append({"param": m.group(1), "value": to_float(m.group(2)), "general": True,
                                      "page": None, "bbox": None})
    seen = set()
    uniq = []
    for r in drw.roughness:
        k = (r["param"], r["value"], r["general"], r["page"] if not r["general"] else None)
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    drw.roughness = uniq

    # 3) шероховатость без обозначения параметра (старая редакция ГОСТ 2.309: значение над знаком √)
    segs_by_page = drw.facts.get("_segments") or {}
    for ln in lines:
        if ln.used:
            continue
        v = to_float(ln.text.strip()) if re.fullmatch(r"\d+(?:,\d+)?", ln.text.strip()) else None
        if v is not None and v in RA_SERIES and _is_roughness_sign(ln, segs_by_page.get(ln.page, [])):
            drw.roughness.append({"param": "Ra", "value": v, "general": False, "page": ln.page, "bbox": ln.bbox})
            ln.used = True
    labels = [ln for ln in drw.lines if len(CYR.findall(ln.text)) >= 3 and not excluded(drw, ln)
              and is_count_only(ln.text) is None and not re.search(r"(?i)отв|фаск|паз|шт\.", ln.text)]

    # 4) размеры
    asm_like = bool(re.search(r"(?<![А-Я])СБ(?![А-Я])", drw.title.designation or "")
                    or re.search(r"(?i)сбороч", drw.title.name or "")
                    or any(t["kind"] == "spec" for t in drw.facts.get("tables") or []))
    tt_sz = sorted(l.size for l in drw.tt_lines)
    tt_med = tt_sz[len(tt_sz) // 2] if tt_sz else None
    dims: list[tuple[Dimension, TextLine]] = []
    devs, fields, counts, stars, prefixes = [], [], [], [], []
    for ln in lines:
        if ln.used:
            continue
        t = ln.text.strip()
        if t in ("(", ")", "()"):
            ln.used = True
            continue
        if t in ("*", "**"):
            stars.append(ln)
            continue
        if t in ("⌀", "□", "R", "SR", "S⌀"):          # Solid Edge выводит знак ⌀ отдельной надписью
            prefixes.append(ln)
            continue
        n = is_count_only(t)
        if n is not None:
            counts.append((n, ln))
            continue
        f = is_field_only(t)
        if f and not parse_dimension(t):
            fields.append((f, ln))
            continue
        v, raw, sym = parse_dev(t)
        if raw is not None and (raw[0] in "+-±" or raw == "0"):
            devs.append((v, raw, sym, ln))
            continue
        p = parse_dimension(t)
        on_shelf = bool(p and re.fullmatch(r"\d{1,3}", t) and (
            _on_shelf(ln, segs_by_page.get(ln.page, [])) or (asm_like and tt_med and ln.size > 1.25 * tt_med)))
        if p and not on_shelf and (_table_value(ln, labels) or _in_table_cell(ln, segs_by_page.get(ln.page, []))):
            ln.used = True
            continue
        if p:
            d = Dimension(page=ln.page, bbox=ln.bbox, source="ocr" if drw.ocr else "pdf",
                          vertical=abs(ln.dir[0]) < 0.5, **{k: v for k, v in p.items()})
            dims.append((d, ln))
            ln.used = True

    def nearest(ln: TextLine, right_only=True, max_k=6.0):
        best, best_d = None, 1e9
        for d, dl in dims:
            if dl.page != ln.page or not _same_dir(dl.dir, ln.dir):
                continue
            u0, u1, v0, v1 = _uv_box(dl, dl.dir)
            cu, cv = _proj((ln.cx, ln.cy), dl.dir)
            h = max(dl.size, 2.0)
            if right_only and not (u1 - 0.6 * h <= cu <= u1 + max_k * h):
                continue
            if not (v0 - 1.0 * h <= cv <= v1 + 1.0 * h):
                continue
            out = max(0.0, v0 - cv, cv - v1)                # отклонение сбоку от надписи — скорее соседнего размера
            dist = abs(cu - u1) + abs(cv - (v0 + v1) / 2) * 0.5 + 3.0 * out
            if dist < best_d:
                best, best_d = (d, dl), dist
        return best

    # знак ⌀ (□, R), стоящий отдельно перед числом
    for ln in prefixes:
        best, best_d = None, 1e9
        for d, dl in dims:
            if dl.page != ln.page or not _same_dir(dl.dir, ln.dir) or d.kind not in ("linear",):
                continue
            u0, u1, v0, v1 = _uv_box(dl, dl.dir)
            pu0, pu1, pv0, pv1 = _uv_box(ln, dl.dir)
            h = max(dl.size, 2.0)
            gap = u0 - pu1
            score = abs(gap) + abs((pv0 + pv1) / 2 - (v0 + v1) / 2)     # соседние размеры в ряд: берём тот, что на одной оси
            if -0.5 * h <= gap <= 1.5 * h and pv1 > v0 - 0.5 * h and pv0 < v1 + 0.5 * h and score < best_d:
                best, best_d = d, score
        if best is not None:
            sym = ln.text.strip()
            best.kind = {"⌀": "diameter", "□": "square", "R": "radius", "SR": "sphere", "S⌀": "sphere"}[sym]
            best.raw = sym + best.raw
            best.bbox = (min(best.bbox[0], ln.bbox[0]), min(best.bbox[1], ln.bbox[1]),
                         max(best.bbox[2], ln.bbox[2]), max(best.bbox[3], ln.bbox[3]))
            ln.used = True

    # отклонения, стоящие отдельными строками (верхнее/нижнее)
    attached: dict[int, list] = {}
    for v, raw, sym, ln in devs:
        hit = nearest(ln)
        if hit is None:
            continue
        d, dl = hit
        if d.upper is not None or d.lower is not None:
            continue
        _, cv = _proj((ln.cx, ln.cy), dl.dir)
        attached.setdefault(id(d), [d, dl, []])[2].append((cv, v, raw, sym, ln))
        ln.used = True
    for d, dl, lst in attached.values():
        lst.sort(key=lambda x: -x[0])
        if len(lst) == 1:
            _, v, raw, sym, ln = lst[0]
            if sym:
                d.upper, d.lower, d.symmetric = v, -v if v is not None else None, True
                d.upper_raw = d.lower_raw = raw
            elif raw.startswith("+") or (v is not None and v > 0):
                d.upper, d.upper_raw, d.lower = v, raw, 0.0
            else:
                d.lower, d.lower_raw, d.upper = v, raw, 0.0
        else:
            (_, vu, ru, _, lu), (_, vl, rl, _, ll) = lst[0], lst[-1]
            d.upper, d.upper_raw, d.lower, d.lower_raw = vu, ru, vl, rl
        d.raw = d.raw + " " + " / ".join(x[2] for x in lst)
        boxes = [d.bbox] + [x[4].bbox for x in lst]
        d.bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                  max(b[2] for b in boxes), max(b[3] for b in boxes))

    # поля допусков / посадки отдельными строками (дробь H7/g6)
    fattached: dict[int, list] = {}
    for f, ln in fields:
        hit = nearest(ln)
        if hit is None:
            continue
        d, dl = hit
        if d.field or d.fit_hole:
            continue
        _, cv = _proj((ln.cx, ln.cy), dl.dir)
        fattached.setdefault(id(d), [d, []])[1].append((cv, f, ln))
        ln.used = True
    for d, lst in fattached.values():
        lst.sort(key=lambda x: -x[0])
        codes = [x[1].translate(CYR_TO_LAT) for x in lst]
        if any(x[1] != c for x, c in zip(lst, codes)):
            d.cyrillic_in_field = True
        if len(codes) >= 2:
            d.fit_hole, d.fit_shaft = codes[0], codes[-1]
        else:
            d.field = codes[0]
        d.raw = d.raw + " " + "/".join(x[1] for x in lst)

    # «4 отв.», «2 фаски» под размером
    for n, ln in counts:
        best, best_d = None, 1e9
        for d, dl in dims:
            if dl.page != ln.page:
                continue
            dy = ln.cy - dl.cy
            dx = abs(ln.bbox[0] - dl.bbox[0])
            if d.vertical:
                dy, dx = abs(ln.cx - dl.cx), abs(ln.cy - dl.cy)
            if 0 < dy < 14 and dx < 12 and dy + dx < best_d:
                best, best_d = d, dy + dx
        if best is not None and best.count is None:
            best.count = n

    for ln in stars:
        hit = nearest(ln, max_k=3)
        if hit and not hit[0].reference:
            hit[0].reference = ln.text.strip()

    # номера позиций на сборочных чертежах: целые числа заметно крупнее размерного шрифта (ГОСТ 2.109 п. 3.2.5)
    def plain(d):
        return (d.kind == "linear" and not d.has_tolerance and not d.reference and d.count is None
                and re.fullmatch(r"\d{1,3}", d.raw.strip()))
    other = sorted(dl.size for d, dl in dims if not plain(d))
    tt_sizes = tt_sz
    if other:
        modal, k = other[len(other) // 2], 1.25
    elif asm_like and tt_sizes:
        modal, k = tt_sizes[len(tt_sizes) // 2], 1.25
    else:
        sizes = sorted(dl.size for d, dl in dims if d.kind == "linear")
        modal, k = (sizes[len(sizes) // 2] if sizes else None), 1.3
    positions = []
    if modal:
        drw.facts["dim_font"] = modal
        keep = []
        for d, dl in dims:
            if plain(d) and (dl.size > modal * k or (asm_like and _on_shelf(dl, segs_by_page.get(dl.page, [])))):
                positions.append({"n": int(d.raw), "page": dl.page, "bbox": dl.bbox, "size": dl.size})
            else:
                keep.append((d, dl))
        dims = keep
    drw.facts["positions"] = positions
    drw.dims = [d for d, _ in dims]
