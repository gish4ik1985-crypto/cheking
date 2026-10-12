"""Масса сборочных единиц и согласованность документов одной проверки.

* B15 — масса не больше массы сплошного стального тела по габаритам изображения: ловит граммы вместо
  килограммов, лишние разряды, массу чужой модели. Для сборок и для деталей, у которых B03 не посчитана;
* A15 — масса сборки не меньше суммы известных масс составных частей;
* A13 — масса сборки равна сумме масс составных частей, когда известны массы всех частей;
* A16 — масса составной части в графе «Примечание» спецификации совпадает с массой в её чертеже;
* A17 — наименование в спецификации соответствует основной надписи чертежа составной части (ГОСТ 2.106),
  одно обозначение в документах проверки — одно изделие.

Массы составных частей берутся из чертежей этой же проверки (графа 5 основной надписи), из загруженной СП
и из графы «Примечание» спецификации на поле чертежа (масса деталей без чертежа, материалы в кг)."""
from __future__ import annotations

import re
from collections import deque

from .model import Drawing, ERROR, WARNING, CAT_ASM, CAT_TB
from .standards import density_for, fmtn
from .textnorm import norm_designation, to_float

STEEL = 7850e-9                      # кг/мм³
CELL, BRIDGE = 2.0, 2                # сетка 2 мм; линии ближе 4 мм — одно изображение
STD_TB = "ГОСТ Р 2.104-2023"
STD_SB = "ГОСТ 2.109-73"
STD_SP = "ГОСТ 2.106-96"
DOC_CODE = re.compile(r"\s*(СБ|МЧ|ВО|ГЧ|ТЧ|МЭ|ЭСБ)\s*$")
SKU = re.compile(r"\d{3}-\d{6}")
NO_MASS = ("Документация", "Комплекты")


def _scale_factor(scale: str) -> float | None:
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*:\s*(\d+(?:[.,]\d+)?)", scale or "")
    if not m:
        return None
    a, b = (float(x.replace(",", ".")) for x in m.groups())
    return b / a if a else None


def _step(raw: str | None) -> float:
    """Половина единицы последнего разряда записанной массы."""
    m = re.search(r"[.,](\d+)", raw or "")
    return 0.5 * 10 ** -(len(m.group(1)) if m else 0)


# ------------------------------------------------------------------- габариты по изображению ----
def _field_segments(drw: Drawing, pg: int) -> list:
    """Линии поля чертежа: без рамки, основной надписи и таблиц."""
    p = drw.page_info(pg)
    segs = ((drw.facts.get("_segments") or {}).get(pg) or []) + ((drw.facts.get("_curves") or {}).get(pg) or [])
    if not p or not segs:
        return []
    ox, oy = drw.title.origin or (p.width - 190, p.height - 60)
    tabs = [t["bbox"] for t in drw.facts.get("tables") or [] if t["page"] == pg]
    out = []
    for s in segs:
        xa, xb, ya, yb = min(s[0], s[2]), max(s[0], s[2]), min(s[1], s[3]), max(s[1], s[3])
        if xa < 21 or xb > p.width - 6 or ya < 6 or yb > p.height - 6:
            continue
        if xa >= ox - 1 and ya >= oy - 1:
            continue
        if any(b[0] - 1 <= xa and xb <= b[2] + 1 and b[1] - 1 <= ya and yb <= b[3] + 1 for b in tabs):
            continue
        out.append(s)
    return out


def _clusters(segs: list) -> list[tuple[float, float]]:
    """Связные изображения (по сетке 2 мм), размеры на листе, от большего к меньшему."""
    occ = set()
    for x1, y1, x2, y2 in segs:
        n = int(max(abs(x2 - x1), abs(y2 - y1)) / CELL) + 1
        for i in range(n + 1):
            t = i / n
            occ.add((int((x1 + (x2 - x1) * t) / CELL), int((y1 + (y2 - y1) * t) / CELL)))
    seen, out = set(), []
    for c in occ:
        if c in seen:
            continue
        seen.add(c)
        q = deque([c])
        xa, xb, ya, yb = c[0], c[0], c[1], c[1]
        while q:
            x, y = q.popleft()
            xa, xb, ya, yb = min(xa, x), max(xb, x), min(ya, y), max(yb, y)
            for dx in range(-BRIDGE, BRIDGE + 1):
                for dy in range(-BRIDGE, BRIDGE + 1):
                    nb = (x + dx, y + dy)
                    if nb in occ and nb not in seen:
                        seen.add(nb)
                        q.append(nb)
        out.append(((xb - xa + 1) * CELL, (yb - ya + 1) * CELL))
    return sorted(out, key=lambda c: -c[0] * c[1])


def view_size(drw: Drawing) -> dict | None:
    """Оценка габаритов изделия сверху: наибольшее изображение листа × масштаб. Масштаб — крупнейший из
    штампа и надписей видов; если размеры на чертеже больше изображения, масштаб в штампе занижен —
    изображение растягивается до наибольшего размера. Третий габарит — не больше наибольшей стороны
    изображений."""
    segs = _field_segments(drw, drw.first_page)
    if len(segs) < 20:
        return None
    ks = [_scale_factor(drw.title.scale)] + [_scale_factor(s) for s in (drw.facts.get("views") or {}).get("scales", [])]
    ks = [k for k in ks if k]
    cl = _clusters(segs)
    if not ks or not cl:
        return None
    k = max(ks)
    a, b = cl[0][0] * k, cl[0][1] * k
    c = max(a, b, max((max(x) for x in cl[1:3]), default=0) * k)
    dims = [d.nominal for d in drw.dims if d.nominal and d.kind in ("linear", "diameter") and not d.reference]
    f = max(1.0, max(dims, default=0) / max(a, b))
    return {"a": a * f, "b": b * f, "c": c * f}


def check_mass_view(drw: Drawing, cfg: dict) -> None:
    tb = drw.title
    if drw.ocr or drw.kind == "spec" or not tb.mass or tb.mass <= 0:
        return
    asm = bool(drw.facts.get("is_assembly"))
    if not asm and drw.facts.get("mass_bbox"):
        return                                    # деталь: B03 точнее (габариты по размерам и плотность)
    v = view_size(drw)
    if not v:
        return
    rho = STEEL
    d = None if asm else density_for(tb.material)
    if d:
        rho = max(rho, d[0] * 1e-9)
    bound = rho * v["a"] * v["b"] * v["c"]
    drw.facts["mass_view"] = {"size": [round(v["a"]), round(v["b"]), round(v["c"])], "bound": round(bound, 3)}
    if tb.mass - _step(tb.mass_raw) <= bound:
        return
    what = "сборки" if asm else "детали"
    drw.add(ERROR if tb.mass > 2 * bound else WARNING, "B15", CAT_TB,
            f"Масса {what} {tb.mass_raw} кг больше массы сплошного стального бруса по габаритам изображения "
            f"(≈ {v['a']:.0f}×{v['b']:.0f}×{v['c']:.0f} мм, {fmtn(round(bound, 1))} кг) — такая масса "
            f"невозможна (единицы, лишние разряды, масса другой модели)", drw.first_page, tb.bboxes.get("mass"), STD_TB)


# --------------------------------------------------------------- массы составных частей ----
def _num(s) -> float | None:
    m = re.search(r"\d+(?:[.,]\d+)?", str(s or ""))
    return to_float(m.group(0)) if m else None


def _word(name: str) -> str:
    m = re.match(r"\s*([A-Za-zА-Яа-яЁё]{3,})", name or "")
    return m.group(1).lower().replace("ё", "е") if m else ""


def _keys(drw: Drawing) -> list[str]:
    out = []
    for x in (drw.title.designation, drw.facts.get("file_designation")):
        if x:
            out += [norm_designation(x), norm_designation(DOC_CODE.sub("", x))]
    if drw.facts.get("file_sku"):
        out.append(drw.facts["file_sku"])
    return [k for k in dict.fromkeys(out) if k]


def components(drw: Drawing) -> list[dict]:
    """Составные части сборки: спецификация на поле чертежа или загруженная СП."""
    out = []
    spec = next((t for t in drw.facts.get("tables") or [] if t["kind"] == "spec"), None)
    if spec:
        for it in spec["items"]:
            des, note, qty = it.get("designation") or "", it.get("note") or "", it.get("qty") or ""
            in_kg = bool(re.fullmatch(r"\s*кг\.?\s*", note) or re.search(r"\d\s*кг", qty))
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*кг", note)
            out.append({"pos": it.get("pos"), "designation": "" if SKU.fullmatch(des) else des,
                        "sku": des if SKU.fullmatch(des) else "", "name": it.get("name") or "", "qty": _num(qty),
                        "note_mass": 1.0 if in_kg else (to_float(m.group(1)) if m else None), "in_kg": in_kg,
                        "section": it.get("_section") or it.get("section") or "", "page": spec["page"],
                        "bbox": it.get("bbox"), "src": "table"})
    elif drw.facts.get("spec_children"):
        from .specdoc import section_of
        for c in drw.facts["spec_children"]:
            sec = c.get("_section") or section_of(c, False)
            m = c.get("mass")
            out.append({"pos": c.get("pos"), "designation": c.get("designation") or "", "sku": c.get("sku") or "",
                        "name": c.get("name") or "", "qty": _num(c.get("qty")), "note_mass": None, "in_kg": False,
                        "spec_mass": m if isinstance(m, (int, float)) and m > 0 and sec != "Материалы" else None,
                        "section": sec, "page": None, "bbox": None, "src": "spec"})
    return out


def _label(c: dict) -> str:
    pos = f"поз. {c['pos']} " if c.get("pos") else ""
    return f"{pos}«{c['designation'] or c['sku'] or c['name']}»"


def check_job(drawings: list, spec=None) -> set[int]:
    """Сверка документов одной проверки. Возвращает номера чертежей, к которым добавлены замечания."""
    changed: set[int] = set()
    docs = [(i, d) for i, d in enumerate(drawings) if d.kind != "spec" and not d.error]
    index: dict[str, int] = {}
    for i, d in docs:
        for k in _keys(d):
            index.setdefault(k, i)
    rows = spec if spec is not None and hasattr(spec, "rows") else None
    first: dict[str, tuple] = {}                 # обозначение → (чертёж, запись) первой спецификации
    for i, d in docs:
        if not d.facts.get("is_assembly"):
            continue
        comps = components(d)
        if not comps:
            continue
        before = len(d.findings)
        own = set(_keys(d))
        known, unknown, parts = 0.0, [], []
        for c in comps:
            if c["section"] in NO_MASS:
                continue
            key = norm_designation(c["designation"]) if c["designation"] else c["sku"]
            if key in own:
                continue
            j = index.get(key) if key else None
            child = drawings[j] if j is not None and j != i else None
            m_draw = child.title.mass if child is not None and child.title.mass else None
            if c["src"] == "table" and key:
                if child is not None:
                    w1, w2 = _word(c["name"]), _word(child.title.name)
                    if w1 and w2 and w1 != w2:
                        d.add(WARNING, "A17", CAT_ASM, f"{_label(c)}: в спецификации — «{c['name']}», в основной надписи "
                              f"чертежа {child.title.designation} — «{child.title.name}». Наименование в спецификации "
                              f"записывают по основной надписи чертежа составной части", c["page"], c["bbox"], STD_SP)
                    elif c["note_mass"] and m_draw and not c["in_kg"] and abs(c["note_mass"] - m_draw) > max(
                            0.05 * m_draw, 0.01) + _step(child.title.mass_raw):
                        d.add(WARNING, "A16", CAT_ASM, f"{_label(c)}: масса в спецификации {fmtn(c['note_mass'])} кг, в "
                              f"чертеже {child.title.designation} — {child.title.mass_raw} кг", c["page"], c["bbox"],
                              STD_SP)
                elif key in first:
                    d0, c0 = first[key]
                    w1, w2 = _word(c["name"]), _word(c0["name"])
                    m1, m2 = c["note_mass"], c0["note_mass"]
                    mass_diff = bool(m1 and m2 and not c["in_kg"] and abs(m1 - m2) > max(0.1 * max(m1, m2), 0.01))
                    if (w1 and w2 and w1 != w2) or mass_diff:
                        m_txt = f" ({fmtn(m2)} кг и {fmtn(m1)} кг)" if mass_diff else ""
                        d.add(ERROR if (w1 != w2 and mass_diff) else WARNING, "A17", CAT_ASM,
                              f"Обозначение «{c['designation'] or c['sku']}»: в спецификации {d0.title.designation} — "
                              f"«{c0['name']}», здесь ({_label(c)}) — «{c['name']}»{m_txt}. Одно обозначение "
                              f"присвоено разным изделиям", c["page"], c["bbox"], "ГОСТ 2.201-80")
                else:
                    first[key] = (d, c)
            m_spec = c.get("spec_mass")
            if m_spec is None and rows is not None and key and c["section"] != "Материалы":
                r = rows.find(c["designation"], c["sku"] or None)
                if r and isinstance(r.get("mass"), (int, float)) and r["mass"] > 0:
                    m_spec = r["mass"]
            m, src = ((m_draw, "чертёж") if m_draw else (m_spec, "СП") if m_spec
                      else (c["note_mass"], "примечание") if c["note_mass"] else (None, ""))
            if m is None or not c["qty"]:
                unknown.append(c)
                continue
            known += m * c["qty"]
            parts.append((m * c["qty"], c, src, m))
        d.facts["mass_parts"] = {"known": round(known, 3), "parts": len(parts), "unknown": len(unknown)}
        M = d.title.mass
        if M and M > 0 and parts:
            tol = _step(d.title.mass_raw) + 0.005 * len(parts)
            top = "; ".join(f"{_label(c)} {fmtn(m)} кг × {fmtn(c['qty'])} ({s})"
                            for _, c, s, m in sorted(parts, key=lambda x: -x[0])[:4])
            if known > M * 1.03 + tol:
                rest = f"; без учёта {len(unknown)} поз. с неизвестной массой" if unknown else ""
                d.add(ERROR, "A15", CAT_ASM, f"Масса сборки {d.title.mass_raw} кг меньше суммы масс составных частей — "
                      f"{fmtn(round(known, 3))} кг{rest}. Наибольшие: {top}", d.first_page,
                      d.title.bboxes.get("mass"), STD_SB)
            elif not unknown and abs(known - M) > max(0.05 * M, 0.01) + tol:
                d.add(WARNING, "A13", CAT_ASM, f"Масса сборки {d.title.mass_raw} кг, сумма масс всех составных частей "
                      f"{fmtn(round(known, 3))} кг (расхождение {abs(known - M) / M * 100:.0f} %). Наибольшие: {top}",
                      d.first_page, d.title.bboxes.get("mass"), STD_SB)
        if len(d.findings) > before:
            changed.add(i)
    return changed
