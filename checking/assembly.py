"""Сборочные чертежи и спецификация на поле чертежа.

* ГОСТ 2.109-73 разд. 3: размеры на сборочном чертеже (п. 3.1.2), номера позиций по спецификации (п. 3.2.1),
  один раз (п. 3.2.4), шрифт на 1–2 номера больше размерных чисел (п. 3.2.5);
* ГОСТ 2.106: сквозная нумерация позиций, количество, порядок разделов, совмещение спецификации
  со сборочным чертежом — только на формате А4 (форма 1).
"""
from __future__ import annotations

import re
from collections import Counter

from .model import Drawing, Word, ERROR, WARNING, INFO, CAT_ASM

STD_SB = "ГОСТ 2.109-73"
STD_SP = "ГОСТ 2.106-2019"
SECTIONS = ["документация", "комплексы", "сборочные единицы", "детали", "стандартные изделия", "прочие изделия",
            "материалы", "комплекты"]
SECTIONS_RU = [s[0].upper() + s[1:] for s in SECTIONS]
COLS = [("pos", r"^поз"), ("des", r"^обозначен"), ("name", r"^наименован"), ("qty", r"^кол"),
        ("note", r"^приме"), ("fmt", r"^формат"), ("zone", r"^зона"), ("mass", r"^масса")]


# ----------------------------------------------------------------------------------- таблицы ----
def _segments(drw: Drawing, page: int):
    hor, ver = [], []
    for (x1, y1, x2, y2) in (drw.facts.get("_segments") or {}).get(page, []):
        if abs(y1 - y2) < 0.3 and abs(x2 - x1) > 3:
            hor.append((min(x1, x2), max(x1, x2), (y1 + y2) / 2))
        elif abs(x1 - x2) < 0.3 and abs(y2 - y1) > 3:
            ver.append((min(y1, y2), max(y1, y2), (x1 + x2) / 2))
    return hor, ver


def find_tables(drw: Drawing, words: list[Word]) -> None:
    """Таблицы на поле чертежа с графой «Обозначение»: спецификация (Поз./Обозначение/Наименование/Кол.)
    или таблица исполнений. Записывает facts["tables"]; их текст не попадает в ТТ и размеры."""
    tables = []
    for hw in [w for w in words if re.fullmatch(r"Обозначение|ОБОЗНАЧЕНИЕ", w.text)]:
        pg = hw.page
        if any(t["page"] == pg and t["bbox"][0] <= hw.cx <= t["bbox"][2] and t["bbox"][1] <= hw.cy <= t["bbox"][3]
               for t in tables):
            continue
        hor, ver = _segments(drw, pg)
        tops = [h for h in hor if h[0] - 1 <= hw.bbox[0] and h[1] + 1 >= hw.bbox[2] and 0 < hw.bbox[1] - h[2] < 12]
        if not tops:
            continue
        top = max(tops, key=lambda h: h[2])
        X0, X1 = top[0], top[1]
        width = X1 - X0
        if width < 60:
            continue
        # линии строк в КОМПАС нарисованы по ячейкам — объединяем отрезки на одной высоте
        by_y: dict[float, list] = {}
        for h in hor:
            if h[2] > top[2] + 1 and h[1] > X0 and h[0] < X1:
                by_y.setdefault(round(h[2] * 2) / 2, []).append((max(h[0], X0), min(h[1], X1)))
        lines_y = []
        for y, spans in by_y.items():
            covered, end = 0.0, X0
            for a, b in sorted(spans):
                if b > end:
                    covered += b - max(a, end)
                    end = b
            if covered >= 0.6 * width:
                lines_y.append(y)
        lines_y.sort()
        if not lines_y:
            continue
        bottom = top[2]
        tb_top = None
        if (drw.title.origin and pg == drw.first_page and drw.title.origin[1] > top[2]
                and X1 > drw.title.origin[0] + 10 and X0 < drw.title.origin[0] + 176):
            tb_top = drw.title.origin[1]                      # таблица над основной надписью — до её верха
        for y in lines_y:                                     # строки сетки идут подряд
            if y - bottom > 30 or (tb_top is not None and y > tb_top + 0.5):
                break
            bottom = y
        header_bottom = next((y for y in lines_y if y > hw.cy), bottom)
        xs = sorted({round(v[2], 1) for v in ver if X0 - 1 <= v[2] <= X1 + 1 and v[0] <= hw.cy <= v[1]})
        xs = sorted(set([round(X0, 1)] + xs + [round(X1, 1)]))
        cols = {}
        for a, b in zip(xs, xs[1:]):
            if b - a < 2:
                continue
            txt = " ".join(w.text for w in words if w.page == pg and a <= w.cx <= b
                           and top[2] <= w.cy <= header_bottom).lower().replace("- ", "").replace("-", "")
            for key, rx in COLS:
                if key not in cols and re.search(rx, txt.strip()):
                    cols[key] = (a, b)
        kind = "spec" if {"des", "name"} <= cols.keys() and ({"pos", "qty"} & cols.keys()) else "table"
        t = {"page": pg, "bbox": (X0, top[2], X1, bottom), "kind": kind, "cols": cols, "items": [],
             "header_bottom": header_bottom}
        if kind == "spec":
            t["items"], t["sections"] = _items(words, pg, X0, X1, header_bottom, bottom, cols)
        tables.append(t)
    drw.facts["tables"] = tables


def _items(words, pg, X0, X1, y0, y1, cols):
    data = sorted([w for w in words if w.page == pg and X0 <= w.cx <= X1 and y0 < w.cy < y1],
                  key=lambda w: (w.cy, w.bbox[0]))
    rows: list[list[Word]] = []
    for w in data:
        h = max(w.bbox[3] - w.bbox[1], 1.5)
        if rows and abs(rows[-1][0].cy - w.cy) < 0.45 * h:
            rows[-1].append(w)
        else:
            rows.append([w])
    items, sections, section = [], [], None
    fresh = False                                            # после заголовка раздела — новая запись
    for r in rows:
        cells = {}
        for key, (a, b) in cols.items():
            ws = sorted([w for w in r if a <= w.cx <= b], key=lambda w: w.bbox[0])
            if ws:
                cells[key] = " ".join(w.text for w in ws)
        name = cells.get("name", "")
        pos = cells.get("pos", "")
        bbox = (min(w.bbox[0] for w in r), min(w.bbox[1] for w in r), max(w.bbox[2] for w in r),
                max(w.bbox[3] for w in r))
        if not cells.get("des") and not re.fullmatch(r"\d{1,3}", pos) and name.strip().lower() in SECTIONS:
            section = name.strip()
            sections.append((section, bbox))
            fresh = True
            continue
        if cells.get("des") or re.fullmatch(r"\d{1,3}", pos):
            fresh = False
            items.append({"pos": int(pos) if re.fullmatch(r"\d{1,3}", pos) else None,
                          "designation": cells.get("des", ""), "name": name, "qty": cells.get("qty", ""),
                          "note": cells.get("note", ""), "mass": cells.get("mass", ""), "section": section,
                          "bbox": bbox})
        elif items and not fresh and (name or cells.get("qty") or cells.get("note")):
            it = items[-1]                                   # продолжение строки (материал, длина)
            it["name"] = (it["name"] + " " + name).strip()
            it["qty"] = it["qty"] or cells.get("qty", "")
            it["note"] = (it["note"] + " " + cells.get("note", "")).strip()
        elif name and section is None and not items:
            continue
        elif name:                                           # строка без позиции (например, материал)
            fresh = False
            items.append({"pos": None, "designation": "", "name": name, "qty": cells.get("qty", ""),
                          "note": cells.get("note", ""), "mass": "", "section": section, "bbox": bbox})
    return items, sections


# ------------------------------------------------------------------------------------- правила ----
def _format_a4(drw: Drawing, pg: int) -> bool:
    p = drw.page_info(pg)
    return bool(p) and abs(min(p.width, p.height) - 210) < 4 and abs(max(p.width, p.height) - 297) < 4


def check_assembly(drw: Drawing, cfg: dict) -> None:
    tables = drw.facts.get("tables") or []
    spec = next((t for t in tables if t["kind"] == "spec"), None)
    positions = drw.facts.get("positions") or []
    tb = drw.title
    name = (tb.name or "").lower()
    is_asm = bool(drw.facts.get("is_assembly") or spec or (positions and re.search(r"\bСБ\b", tb.designation or "")))
    if not is_asm:
        return
    drw.facts["is_assembly"] = True
    pg0 = drw.first_page

    # размеры (п. 3.1.2 д, е)
    if not drw.ocr and not [d for d in drw.dims if d.kind in ("linear", "diameter", "square", "radius")]:
        drw.add(WARNING, "A05", CAT_ASM, "На сборочном чертеже нет размеров: указывают габаритные, установочные и "
                "присоединительные размеры (кроме сборочных единиц, не поставляемых самостоятельно)", pg0, None,
                "ГОСТ 2.109-73 п. 3.1.2")

    # номера позиций
    nums = [p["n"] for p in positions]
    cnt = Counter(nums)
    if spec:
        spec_pos = {it["pos"] for it in spec["items"] if it["pos"]}
        missing = sorted(spec_pos - set(nums))
        extra = sorted(set(nums) - spec_pos)
        if missing and positions:
            drw.add(WARNING, "A01", CAT_ASM, f"Позиции спецификации не указаны на чертеже: "
                    f"{', '.join(map(str, missing))}", spec["page"], spec["bbox"], "ГОСТ 2.109-73 п. 3.2.1")
        elif missing:
            drw.add(WARNING, "A01", CAT_ASM, f"Номера позиций {', '.join(map(str, missing))} на чертеже не найдены — "
                    f"их наносят на полках линий-выносок шрифтом крупнее размерных чисел", spec["page"], spec["bbox"],
                    "ГОСТ 2.109-73 п. 3.2.1")
        for n in extra:
            p = next(x for x in positions if x["n"] == n)
            drw.add(ERROR, "A02", CAT_ASM, f"Позиция {n} есть на чертеже, но её нет в спецификации", p["page"],
                    p["bbox"], "ГОСТ 2.109-73 п. 3.2.1")
    elif drw.facts.get("spec_children"):
        # спецификация — отдельный документ (загруженная СП): позиции составных частей, кроме материалов
        src = drw.facts.get("spec_children_src", "спецификации")
        exp = {}
        for c in drw.facts["spec_children"]:
            last = (c.get("pos") or "").rsplit(".", 1)[-1]
            if last.isdigit() and c.get("_section") not in ("Материалы", "Документация", "Комплекты"):
                exp[int(last)] = c
        missing = sorted(set(exp) - set(nums))
        extra = sorted(set(nums) - set(exp))
        if missing and exp:
            drw.add(WARNING, "A01", CAT_ASM, f"По {src} на чертеже нет позиций: "
                    + "; ".join(f"{n} {exp[n].get('name') or exp[n].get('designation')}" for n in missing[:10]),
                    pg0, None, "ГОСТ 2.109-73 п. 3.2.1")
        for n in extra:
            p = next(x for x in positions if x["n"] == n)
            drw.add(ERROR, "A02", CAT_ASM, f"Позиция {n} есть на чертеже, но её нет в {src}", p["page"], p["bbox"],
                    "ГОСТ 2.109-73 п. 3.2.1")
    elif nums:
        gaps = sorted(set(range(1, max(nums) + 1)) - set(nums))
        if gaps:
            drw.add(INFO, "A03", CAT_ASM, f"Номера позиций на чертеже: {', '.join(map(str, sorted(set(nums))))} — нет "
                    f"{', '.join(map(str, gaps))}. Сверьте со спецификацией", pg0, None, "ГОСТ 2.109-73 п. 3.2.1")
    rep = sorted(n for n, k in cnt.items() if k > 1)
    if rep:
        p = [x for x in positions if x["n"] == rep[0]][1]
        drw.add(INFO, "A06", CAT_ASM, f"Номера позиций указаны повторно: {', '.join(f'{n} ({cnt[n]} раза)' for n in rep)} "
                f"— номер позиции наносят, как правило, один раз (повторно — для одинаковых составных частей)",
                p["page"], p["bbox"], "ГОСТ 2.109-73 п. 3.2.4")
    font = drw.facts.get("dim_font")
    small = [p for p in positions if font and p["size"] < 1.15 * font]
    if small:
        p = small[0]
        drw.add(WARNING, "A04", CAT_ASM, f"Номера позиций ({', '.join(str(x['n']) for x in small[:8])}) выполнены "
                f"шрифтом размерных чисел — шрифт номеров позиций на 1–2 номера больше", p["page"], p["bbox"],
                "ГОСТ 2.109-73 п. 3.2.5")

    # спецификация на поле чертежа
    if not spec:
        return
    sp, bb = spec["page"], spec["bbox"]
    if re.search(r"(?<![А-Я])СБ(?![А-Я])", tb.designation or "") and "fmt" in spec["cols"]:
        drw.add(WARNING, "A14", CAT_ASM, f"Спецификация совмещена со сборочным чертежом, а в обозначении «{tb.designation}» "
                f"код «СБ» — совмещённому документу присваивают обозначение основного конструкторского документа "
                f"(спецификации), без кода", pg0, tb.bboxes.get("designation"), "ГОСТ 2.106-96 п. 3.19")
    # правила ГОСТ 2.106 к содержимому (обозначения, стандарты, сортировка)
    from .specdoc import check_children, section_of
    for it in spec["items"]:
        it["_section"] = next((s for s in SECTIONS_RU if (it.get("section") or "").lower().startswith(s.lower()[:6])),
                              None) or section_of({**it, "sku": it["designation"] if re.fullmatch(r"\d{3}-\d{6}",
                                                  it["designation"] or "") else ""}, False)
        if re.fullmatch(r"\d{3}-\d{6}", it["designation"] or ""):
            it["designation_is_sku"] = True
    check_children(lambda sev, code, msg, p, b: drw.add(sev, code, CAT_ASM, msg, sp, bb, STD_SP), "",
                   spec["items"], (sp, bb), drawing_table=True)
    if not _format_a4(drw, sp):
        drw.add(WARNING, "A11", CAT_ASM, "Спецификация совмещена со сборочным чертежом на формате больше А4 — "
                "совмещать допускается только на А4; на остальных форматах спецификацию выпускают отдельным "
                "документом", sp, bb, STD_SP)
    lost = [c for c, t in (("fmt", "Формат"), ("zone", "Зона"), ("note", "Примечание")) if c not in spec["cols"]]
    if lost:
        drw.add(INFO, "A12", CAT_ASM, f"Таблица составных частей на поле чертежа не по форме 1 спецификации: нет граф "
                f"{', '.join({'fmt': '«Формат»', 'zone': '«Зона»', 'note': '«Примечание»'}[c] for c in lost)}",
                sp, bb, STD_SP)
    items = spec["items"]
    pos = [it["pos"] for it in items if it["pos"]]
    # номера идут по порядку записи; резервировать номера (пропуски) ГОСТ 2.106 допускает
    if pos and any(b <= a for a, b in zip(pos, pos[1:])):
        drw.add(WARNING, "A07", CAT_ASM, f"Позиции в спецификации: {', '.join(map(str, pos))} — номера позиций "
                f"проставляют по порядку записи, без повторов", sp, bb, STD_SP)
    for it in items:
        if it["pos"] and not re.search(r"\d", it["qty"] or "") and (it["section"] or "").lower() not in (
                "документация", "комплекты"):
            drw.add(ERROR, "A08", CAT_ASM, f"Позиция {it['pos']} «{it['designation'] or it['name']}»: не указано "
                    f"количество", sp, it["bbox"], STD_SP)
    des = Counter(it["designation"].replace(" ", "") for it in items if it["designation"])
    for d, k in des.items():
        if k > 1:
            drw.add(WARNING, "A09", CAT_ASM, f"Обозначение «{d}» записано в спецификации {k} раза", sp, bb, STD_SP)
    order = [SECTIONS.index(s.lower()) for s, _ in spec.get("sections", []) if s.lower() in SECTIONS]
    if order != sorted(order):
        drw.add(WARNING, "A10", CAT_ASM, "Разделы спецификации не в порядке ГОСТ 2.106 (документация, комплексы, "
                "сборочные единицы, детали, стандартные изделия, прочие изделия, материалы, комплекты): "
                + ", ".join(s for s, _ in spec["sections"]), sp, bb, STD_SP)
    # масса сборки и составных частей — masscheck.check_job (по всем документам проверки)
