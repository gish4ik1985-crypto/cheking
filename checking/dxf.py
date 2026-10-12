"""Сверка чертежа с DXF-макетом для лазерной резки (развёрткой).

Из DXF берутся: габарит контура, отверстия (окружности, в т.ч. собранные из двух дуг), толщина из имени
файла («Ребро_5мм.dxf»), признак гибов. Слои гравировки/маркировки/осевых и тексты не учитываются —
так же, как в ERP (DxfCleanupService: маркировка лежит на текстовых слоях и Up_Etch).
"""
from __future__ import annotations

import os
import re
from collections import Counter

from .model import Drawing, WARNING, ERROR, INFO, CAT_DXF
from .standards import METRIC_THREADS, fmtn
from .textnorm import nfc, norm_designation

SKIP_LAYER = re.compile(r"(?i)etch|center|осев|text|текст|mark|маркир|гравир|dim|размер|annot|__")
BEND_LAYER = re.compile(r"(?i)bend|гиб")
SKU_RE = re.compile(r"(?<!\d)(\d{3}-\d{6})(?!\d)")
DES_RE = re.compile(r"[А-ЯA-Z]{2,5}[._]\d{6}[._]\d{3}(?:-\d{2,3})?|[А-ЯA-Z]{1,4}-\d{2,4}[А-ЯA-Z]?(?:\.\d{2,3}){1,3}")
THICK_RE = re.compile(r"_(\d+(?:[.,]\d+)?)\s*мм", re.I)


def _entities(msp):
    """Сущности модели с раскрытием блоков (КОМПАС кладёт геометрию в INSERT)."""
    for e in msp:
        if e.dxftype() == "INSERT":
            try:
                for v in e.virtual_entities():
                    if v.dxftype() == "INSERT":
                        yield from v.virtual_entities()
                    else:
                        yield v
            except Exception:
                continue
        else:
            yield e


def read_dxf(path: str) -> dict:
    import ezdxf
    from ezdxf import bbox as ebbox
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    units = doc.header.get("$INSUNITS", 4)
    k = {1: 25.4, 4: 1.0, 5: 10.0, 6: 1000.0}.get(units, 1.0)
    geom, circles, arcs, bends = [], [], [], 0
    for e in _entities(msp):
        t = e.dxftype()
        layer = str(getattr(e.dxf, "layer", "0"))
        if t in ("TEXT", "MTEXT", "DIMENSION", "HATCH", "POINT", "ATTRIB", "ATTDEF"):
            continue
        if BEND_LAYER.search(layer):
            bends += 1
            continue
        if SKIP_LAYER.search(layer):
            continue
        geom.append(e)
        if t == "CIRCLE":
            c = e.dxf.center
            circles.append((round(c.x * k, 3), round(c.y * k, 3), e.dxf.radius * k))
        elif t == "ARC":
            c = e.dxf.center
            span = (e.dxf.end_angle - e.dxf.start_angle) % 360 or 360
            arcs.append((round(c.x * k, 2), round(c.y * k, 2), round(e.dxf.radius * k, 3), span))
    # окружности из двух и более дуг с общим центром и радиусом
    groups: dict[tuple, float] = {}
    for x, y, r, span in arcs:
        key = (x, y, r)
        groups[key] = groups.get(key, 0) + span
    for (x, y, r), total in groups.items():
        if total >= 359:
            circles.append((x, y, r))
    ext = ebbox.extents(geom) if geom else None
    if ext is None or not ext.has_data:
        raise ValueError("в DXF не найдено геометрии контура")
    w, h = ext.size.x * k, ext.size.y * k
    # отверстия = окружности внутри габарита (наружная окружность кольца — не отверстие)
    big = max(w, h)
    holes = Counter()
    outer = None
    for x, y, r in circles:
        d = round(2 * r, 2)
        if d >= big - 0.05:
            outer = d
            continue
        holes[d] += 1
    name = nfc(os.path.splitext(os.path.basename(path))[0])
    m = THICK_RE.search(name)
    return {
        "path": path, "name": name, "size": (round(max(w, h), 2), round(min(w, h), 2)),
        "holes": dict(holes), "outer_diameter": outer, "bends": bends,
        "thickness": float(m.group(1).replace(",", ".")) if m else None,
        "sku": (SKU_RE.search(name).group(1) if SKU_RE.search(name) else None),
        "designations": [x.replace("_", ".") for x in DES_RE.findall(name)],
    }


class DxfIndex:
    def __init__(self, paths: list[str]):
        self.items: list[dict] = []
        self.errors: dict[str, str] = {}
        for p in paths:
            try:
                self.items.append(read_dxf(p))
            except Exception as e:
                self.errors[p] = f"{type(e).__name__}: {e}"

    def __len__(self):
        return len(self.items)

    def find(self, drw: Drawing) -> dict | None:
        keys_des = {norm_designation(x) for x in (drw.title.designation, drw.facts.get("file_designation")) if x}
        sku = drw.facts.get("file_sku") or (drw.facts.get("spec_item") or {}).get("sku")
        stem = nfc(os.path.splitext(os.path.basename(drw.filename))[0]).lower()
        for it in self.items:
            if sku and it["sku"] == sku:
                return it
            if any(norm_designation(d) in keys_des for d in it["designations"]):
                return it
        for it in self.items:
            base = THICK_RE.sub("", it["name"]).lower()
            if base and (base == stem or (len(base) > 6 and base in stem)):
                return it
        return None


def _near(values, target, tol):
    return any(abs(v - target) <= tol for v in values)


def compare(drw: Drawing, dx: dict, cfg: dict) -> None:
    drw.facts["dxf"] = {k: v for k, v in dx.items() if k != "path"}
    fname = os.path.basename(dx["path"])
    page = drw.first_page

    # толщина
    s = drw.facts.get("sheet_thickness")
    if dx["thickness"] and s and abs(dx["thickness"] - s) > 1e-6:
        drw.add(ERROR, "X04", CAT_DXF, f"Толщина в имени DXF «{fname}» — {fmtn(dx['thickness'])} мм, на чертеже "
                f"лист {fmtn(s)} мм", page, drw.title.bboxes.get("material"))

    dims = [d for d in drw.dims if d.nominal and d.kind in ("linear", "diameter", "square")]
    lin = [d.nominal for d in dims]
    # габарит (для гнутых деталей развёртка больше размеров на виде — только информация)
    a, b = dx["size"]
    bent = dx["bends"] > 0 or re.search(r"(?i)гиб|развертк|развёртк", " ".join(drw.tt))
    missing = [v for v in (a, b) if not _near(lin, v, 0.5)]
    if dx.get("outer_diameter") and _near([d.nominal for d in drw.dims if d.kind == "diameter"], dx["outer_diameter"], 0.3):
        missing = []
    if missing and lin:
        sev = INFO if bent else WARNING
        drw.add(sev, "X01", CAT_DXF, f"Габарит DXF {fmtn(a)}×{fmtn(b)} мм: размер(ы) {', '.join(fmtn(v) for v in missing)} "
                f"не найдены среди размеров чертежа (наибольший на чертеже — {fmtn(max(lin))}). "
                + ("Деталь гнутая — сравните с развёрткой." if bent else
                   "Проверьте, что DXF соответствует актуальной версии чертежа."), page, None)

    # отверстия
    dx_holes = Counter({float(k): v for k, v in dx["holes"].items()})
    used = Counter()
    draw_holes = []
    for d in drw.dims:
        if d.kind == "diameter" and d.nominal and not d.reference and d.nominal < a - 0.5:
            draw_holes.append((d.nominal, d.count or 1, d, None))
        elif d.kind == "thread" and d.nominal and d.count:
            entry = METRIC_THREADS.get(d.nominal)
            p = d.pitch or (entry[0] if entry and entry[0] else 0)
            draw_holes.append((d.nominal, d.count, d, round(d.nominal - p, 2) if p else None))
    for nom, cnt, d, tap in draw_holes:
        cands = [k for k in dx_holes if abs(k - nom) <= 0.2 or (tap and abs(k - tap) <= 0.35)]
        have = sum(dx_holes[k] for k in cands)
        if not cands:
            if d.kind == "thread":
                drw.add(INFO, "X02", CAT_DXF, f"Резьбовые отверстия «{d.raw}» в DXF не вырезаются — "
                        f"будут сверлиться (ожидаемо, если так и задумано)", d.page, d.bbox)
            else:
                drw.add(WARNING, "X02", CAT_DXF, f"Отверстие «{d.raw}» есть на чертеже, но окружности ⌀{fmtn(nom)} в "
                        f"DXF «{fname}» нет", d.page, d.bbox)
        elif have < cnt:
            drw.add(WARNING, "X02", CAT_DXF, f"«{d.raw}»: на чертеже {cnt} отв., в DXF {have}", d.page, d.bbox)
        for k in cands:
            used[k] += dx_holes[k]
    extra = {k: v for k, v in dx_holes.items() if used[k] == 0}
    if extra:
        lst = ", ".join(f"⌀{fmtn(k)} — {v} шт." for k, v in sorted(extra.items()))
        drw.add(WARNING, "X03", CAT_DXF, f"В DXF «{fname}» есть отверстия, которых нет на чертеже: {lst}",
                page, None)
    if not any(f.code.startswith("X") for f in drw.findings):
        drw.add(INFO, "X00", CAT_DXF, f"DXF «{fname}» соответствует чертежу: габарит {fmtn(a)}×{fmtn(b)}, "
                f"отверстий {sum(dx_holes.values())}", page, None)


def compare_erp_bbox(drw: Drawing, item: dict) -> None:
    """Габарит DXF из карточки ERP (products.length/width) против размеров чертежа."""
    L, W = item.get("dxf_length"), item.get("dxf_width")
    if not L or not W:
        return
    a, b = max(L, W), min(L, W)
    lin = [d.nominal for d in drw.dims if d.nominal and d.kind in ("linear", "diameter")]
    missing = [v for v in (a, b) if not _near(lin, v, 0.5)]
    if missing and lin:
        drw.add(WARNING, "X01", CAT_DXF, f"Габарит активного DXF в ERP {fmtn(a)}×{fmtn(b)} мм: "
                f"{', '.join(fmtn(v) for v in missing)} не найдены среди размеров чертежа", drw.first_page, None)
