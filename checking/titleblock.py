"""Поиск и разбор основной надписи (ГОСТ Р 2.104-2023, форма 1 и 2а)."""
from __future__ import annotations

import difflib
import re
import statistics

from .model import Drawing, TextLine, TitleBlock, Word
from .textnorm import ocr_fix, to_float

# опорные надписи граф: ключ -> смещение левого верхнего угла надписи от левого верхнего угла
# основной надписи 185×55 (мм); получены по КОМПАС-3D, у других САПР отличаются на 1–2 мм
ANCHORS = {
    "разраб": (1.0, 26.0), "пров": (1.0, 31.0), "тконтр": (1.0, 36.0), "нконтр": (1.0, 46.0),
    "утв": (1.0, 51.0), "лит": (139.1, 16.0), "масса": (153.1, 16.0), "масштаб": (168.0, 16.0),
    "листов": (157.9, 36.0),
}
LABELS = {"изм", "лист", "№докум", "№", "докум", "подп", "дата", "разраб", "пров", "тконтр", "нконтр",
          "утв", "лит", "масса", "масштаб", "листов", "копировал", "формат", "измлист"}

# графы формы 1 (x0, y0, x1, y1) от левого верхнего угла основной надписи
CELLS = {
    "designation": (65, 0, 185, 15),
    "name": (65, 15, 135, 40),
    "material": (65, 40, 135, 55),
    "organization": (135, 40, 185, 55),
    "litera": (135, 20, 150, 35),
    "mass": (150, 20, 167, 35),
    "scale": (167, 20, 185, 35),
    "sheet": (135, 35, 155, 40),
    "sheets": (155, 35, 185, 40),
    "format": (110, 55, 185, 61),
}
FREE_TEXT = ("designation", "name", "material", "organization")
PEOPLE_ROWS = {"Разраб.": (25, 30), "Пров.": (30, 35), "Т.контр.": (35, 40), "": (40, 45),
               "Н.контр.": (45, 50), "Утв.": (50, 55)}
SPEC_HEADERS = {"обозначение", "наименование", "кол", "поз", "зона", "прим", "примеч"}


def key(text: str) -> str:
    t = text.lower().translate(str.maketrans("abcehkmoptxy", "авсенкмортху"))
    return re.sub(r"[\s.,:]", "", t)


def _match_anchor(text: str, fuzzy: bool) -> str | None:
    k = key(text)
    if k in ANCHORS:
        return k
    if fuzzy and 3 <= len(k) <= 9:
        best = difflib.get_close_matches(k, ANCHORS.keys(), n=1, cutoff=0.75)
        return best[0] if best else None
    return None


def find_origin(lines: list[TextLine], page: int, fuzzy: bool) -> tuple[tuple[float, float] | None, list]:
    cands = []
    for ln in lines:
        if ln.page != page or abs(ln.dir[0] - 1) > 0.05:
            continue
        a = _match_anchor(ln.text, fuzzy)
        if a:
            dx, dy = ANCHORS[a]
            cands.append((a, ln.bbox[0] - dx, ln.bbox[1] - dy, ln))
    if len(cands) < 2:
        return None, cands
    mx = statistics.median(c[1] for c in cands)
    my = statistics.median(c[2] for c in cands)
    good = [c for c in cands if abs(c[1] - mx) < 6 and abs(c[2] - my) < 6]
    if len(good) < 2 or len({c[0] for c in good}) < 2:
        return None, cands
    return (statistics.median(c[1] for c in good), statistics.median(c[2] for c in good)), good


def has_form1(lines: list[TextLine], page: int, fuzzy: bool) -> bool:
    origin, good = find_origin(lines, page, fuzzy)
    return origin is not None and len({c[0] for c in good}) >= 3


def calibrate_scale(drw: Drawing, words: list[Word]) -> None:
    """Для растров: уточняет мм/px по расстоянию между графами «Разраб.» и «Масса»/«Масштаб»."""
    _, cands = find_origin(drw.lines, drw.first_page, fuzzy=True)
    left = [c for c in cands if c[0] in ("разраб", "пров", "нконтр", "утв")]
    right = [c for c in cands if c[0] in ("масса", "масштаб", "лит", "листов")]
    if not left or not right:
        return
    l, r = left[0], right[0]
    measured = r[3].bbox[0] - l[3].bbox[0]
    expected = ANCHORS[r[0]][0] - ANCHORS[l[0]][0]
    if measured <= 0:
        return
    k = expected / measured
    if 0.3 < k < 3 and abs(k - 1) > 0.03:
        for ln in drw.lines:
            ln.bbox = tuple(v * k for v in ln.bbox)
            ln.origin = (ln.origin[0] * k, ln.origin[1] * k)
            ln.size *= k
        for w in words:
            w.bbox = tuple(v * k for v in w.bbox)
        for p in drw.pages:
            p.width *= k
            p.height *= k


def _cell_text(drw: Drawing, words: list[Word], page: int, ox: float, oy: float, cell,
               skip_labels=True) -> tuple[str, list]:
    x0, y0, x1, y1 = cell
    hits = [w for w in words if w.page == page and x0 <= w.cx - ox <= x1 and y0 <= w.cy - oy <= y1]
    if skip_labels:
        hits = [w for w in hits if key(w.text) not in LABELS]
    # группируем по исходным строкам текста (сохраняет «Лист 16 ГОСТ…» в дроби материала)
    groups: dict[int, list[Word]] = {}
    for w in hits:
        groups.setdefault(w.line_no, []).append(w)
    rows = sorted(groups.values(), key=lambda g: (min(w.bbox[1] for w in g), min(w.bbox[0] for w in g)))
    text_rows = [" ".join(w.text for w in sorted(g, key=lambda q: q.bbox[0])) for g in rows]
    return " / ".join(t for t in text_rows if t), hits


def _union(ws) -> tuple | None:
    if not ws:
        return None
    return (min(w.bbox[0] for w in ws), min(w.bbox[1] for w in ws),
            max(w.bbox[2] for w in ws), max(w.bbox[3] for w in ws))


def parse_title_block(drw: Drawing, words: list[Word]) -> None:
    tb = TitleBlock()
    drw.title = tb
    if not drw.pages:
        return
    p0 = drw.pages[0]
    pg = p0.number
    origin, _ = find_origin(drw.lines, pg, fuzzy=drw.ocr)
    if origin is None:
        # запасной вариант: стандартная рамка, основная надпись в правом нижнем углу
        origin = (p0.width - 5 - 185, p0.height - 5 - 55)
    else:
        tb.found = True
    tb.origin = origin
    ox, oy = origin

    for name, cell in CELLS.items():
        text, hits = _cell_text(drw, words, pg, ox, oy, cell, skip_labels=name not in FREE_TEXT)
        if name == "mass":
            tb.mass_raw = text
        else:
            setattr(tb, name, text)
        bb = _union(hits)
        if bb:
            tb.bboxes[name] = bb

    if drw.ocr:
        for f in ("designation", "name", "material", "organization"):
            setattr(tb, f, ocr_fix(getattr(tb, f)))
    rows = [r for r in tb.material.split(" / ") if r]
    sort_rows = [r for r in rows if re.fullmatch(r"(?i)(лист|круг|полоса|квадрат|труба|профиль|уголок|швеллер|"
                                                 r"шестигранник|пруток|лента|двутавр|плита)", r.strip())]
    if sort_rows and len(rows) >= 2:
        rest = [r for r in rows if r not in sort_rows]
        tb.material = " / ".join([sort_rows[0] + " " + rest[0]] + rest[1:])
    # обозначение — самая крупная надпись над графой наименования (у шаблонов Solid Edge с графами
    # «Рев./Вер.» основная надпись выше стандартной на ~10 мм)
    # выше штампа смотрим только если там есть графы «Рев./Вер.» (шаблон Solid Edge); иначе надпись над штампом
    # (размер, фаска, примечание) к обозначению не относится
    rev_strip = any(w.page == pg and 55 <= w.cx - ox <= 186 and -16 <= w.cy - oy <= 2 and re.fullmatch(r"(?i)(рев|вер)\.?", w.text.strip())
                    for w in words)
    top = -16 if rev_strip else -1.5
    cand = [w for w in words if w.page == pg and 60 <= w.cx - ox <= 186 and top <= w.cy - oy <= 14
            and key(w.text) not in LABELS and not re.fullmatch(r"(?i)(рев|вер)\.?|\d{1,2}", w.text.strip())]
    if cand:
        hmax = max(w.bbox[3] - w.bbox[1] for w in cand)
        big = [w for w in cand if w.bbox[3] - w.bbox[1] >= 0.75 * hmax]
        if hmax >= 5:
            big.sort(key=lambda w: w.bbox[0])
            tb.designation = " ".join(w.text for w in big)
            tb.bboxes["designation"] = _union(big)
    rev = [w for w in words if w.page == pg and 150 <= w.cx - ox <= 186 and -16 <= w.cy - oy <= 14
           and re.fullmatch(r"\d{1,2}", w.text.strip())]
    if rev:
        tb.revision = rev[0].text
    tb.designation = re.sub(r"(?i)\b(рев|вер)\.?\s*\d{0,2}\b", "", tb.designation.replace(" / ", " ")).strip()
    tb.name = tb.name.replace(" / ", " ")
    m = re.search(r"\d+(?:[.,]\d+)?", tb.mass_raw or "")
    tb.mass = to_float(m.group(0)) if m else None
    tb.format = re.sub(r"(?i)копировал|формат", "", tb.format).replace("/", " ").strip()

    for role, (y0, y1) in PEOPLE_ROWS.items():
        name, _ = _cell_text(drw, words, pg, ox, oy, (17, y0, 40, y1))
        date, _ = _cell_text(drw, words, pg, ox, oy, (55, y0, 65, y1))
        r = role or "доп."
        if name:
            tb.people[r] = name
        if date:
            tb.dates[r] = date
    for i in range(4):
        y0, y1 = i * 5, i * 5 + 5
        num, _ = _cell_text(drw, words, pg, ox, oy, (0, y0, 7, y1))
        sh, _ = _cell_text(drw, words, pg, ox, oy, (7, y0, 17, y1))
        doc, _ = _cell_text(drw, words, pg, ox, oy, (17, y0, 40, y1))
        date, _ = _cell_text(drw, words, pg, ox, oy, (55, y0, 65, y1))
        if num or doc:
            tb.changes.append({"num": num, "sheet": sh, "doc": doc, "date": date})

    # графа 26 (обозначение, повёрнутое на 180°) и «Перв. примен.»
    for ln in drw.lines:
        if ln.page != pg:
            continue
        if ln.dir[0] < -0.9 and ln.bbox[1] < 25:
            tb.rotated_designation = ln.text
        if abs(ln.dir[1] + 1) < 0.1 and ln.bbox[0] < 20.5 and ln.bbox[1] < 80 and key(ln.text) not in (
                "первпримен", "справ№", "справ") and re.search(r"\d", ln.text):
            tb.first_use = ln.text

    if not tb.designation and tb.rotated_designation:
        tb.designation = tb.rotated_designation.strip()
        drw.facts["designation_from_26"] = True

    # таблица спецификации на поле чертежа (над основной надписью, той же ширины)
    heads = [ln for ln in drw.lines if ln.page == pg and key(ln.text) in SPEC_HEADERS
             and ox - 2 <= ln.cx <= ox + 187 and ln.cy < oy]
    if len({key(h.text) for h in heads}) >= 2:
        top = min(h.bbox[1] for h in heads) - 2
        bottom = oy
        # ТТ под таблицей спецификации («1. *Размеры для справок.») в таблицу не входят
        for ln in sorted(drw.lines, key=lambda l: l.bbox[1]):
            if (ln.page == pg and top + 6 < ln.bbox[1] < oy and abs(ln.dir[0] - 1) < 0.05
                    and ln.bbox[0] - ox < 10 and len(ln.text) > 12
                    and len(re.findall(r"[А-Яа-я]", ln.text)) >= 6):
                bottom = ln.bbox[1] - 0.5
                break
        drw.facts["spec_table"] = (ox - 1, top, ox + 186, bottom)


def excluded(drw: Drawing, ln: TextLine) -> bool:
    """Строка лежит в основной надписи, таблице спецификации, боковых графах или графе 26."""
    p = drw.page_info(ln.page)
    if p is None:
        return True
    cx, cy = ln.cx, ln.cy
    if cx < 20.5:                                   # поле подшивки с графами 19–23
        return True
    if ln.dir[0] < -0.9:                            # графа 26
        return True
    if ln.page == drw.first_page and drw.title.origin:
        ox, oy = drw.title.origin
        if ox - 1 <= cx <= ox + 186 and oy - 1 <= cy <= oy + 62:
            return True
        st = drw.facts.get("spec_table")
        if st and st[0] <= cx <= st[2] and st[1] <= cy <= st[3]:
            return True
        for t in drw.facts.get("tables") or []:      # спецификация / таблица исполнений на поле чертежа
            b = t["bbox"]
            if t["page"] == ln.page and b[0] - 0.5 <= cx <= b[2] + 0.5 and b[1] - 0.5 <= cy <= b[3] + 0.5:
                return True
        for bb in drw.title.bboxes.values():         # графы штампа, вынесенные за стандартную рамку
            if bb[0] - 1 <= cx <= bb[2] + 1 and bb[1] - 1 <= cy <= bb[3] + 1:
                return True
    else:                                           # форма 2а на последующих листах
        if cy > p.height - 21 and cx > p.width - 192:
            return True
    if cy > p.height - 6:                           # «Копировал / Формат»
        return True
    return False
