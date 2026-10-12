"""Таблица параметров зубчатого венца (ГОСТ 2.403-75): модуль (ГОСТ 9563-60), обязательные строки,
делительный диаметр d = m·z / cos β, степень точности (ГОСТ 1643-81), эвольвентные шлицы (ГОСТ 6033-80)."""
from __future__ import annotations

import math
import re

from .model import Drawing, ERROR, WARNING, INFO, CAT_GEAR
from .normdata import MODULES_1, MODULES_2, SPLINE_MODULES, GEAR_FITS
from .standards import fmtn
from .textnorm import to_float

STD = "ГОСТ 2.403-75"
SPL = re.compile(r"(?<![\d,.])\d{2,3}\s*[×xх]\s*\d+(?:[.,]\d+)?\s*[×xх]\s*\d{1,2}[A-Za-zА-Яа-я]{1,2}\b|ГОСТ\s*6[03]33")

PARAMS = [
    ("m", re.compile(r"(?i)^модуль")),
    ("z", re.compile(r"(?i)^число зубьев$")),
    ("beta", re.compile(r"(?i)^угол наклона")),
    ("profile", re.compile(r"(?i)исходный контур$|^нормальный исходный контур")),
    ("x", re.compile(r"(?i)^коэффициент смещения|^смещение исходного контура")),
    ("precision", re.compile(r"(?i)^степень точности")),
    ("d", re.compile(r"(?i)^делительный диаметр|^диаметр делит\w* окружности")),
]
NAMES = {"m": "модуль m", "z": "число зубьев z", "profile": "исходный контур", "x": "коэффициент смещения x",
         "precision": "степень точности", "d": "делительный диаметр d"}


def parse_tables(drw: Drawing) -> list[dict]:
    """Таблицы параметров: строка = подпись (левая колонка) + обозначение + значение (правые колонки)."""
    tables = []
    for anchor in [ln for ln in drw.lines if re.match(r"(?i)^модуль\b", ln.text.strip())]:
        x0, pg = anchor.bbox[0], anchor.page
        h = max(anchor.bbox[3] - anchor.bbox[1], 2.0)
        col = sorted([ln for ln in drw.lines if ln.page == pg and abs(ln.bbox[0] - x0) < 1.5
                      and abs(ln.dir[0] - 1) < 0.05], key=lambda l: l.bbox[1])
        # непрерывный столбец подписей вокруг «Модуль»
        i = col.index(anchor)
        lo = hi = i
        while lo > 0 and col[lo].bbox[1] - col[lo - 1].bbox[3] < 3 * h:
            lo -= 1
        while hi + 1 < len(col) and col[hi + 1].bbox[1] - col[hi].bbox[3] < 3 * h:
            hi += 1
        labels = col[lo:hi + 1]
        top, bottom = labels[0].bbox[1] - 1, labels[-1].bbox[3] + 3 * h
        right = [ln for ln in drw.lines if ln.page == pg and x0 + 20 < ln.bbox[0] < x0 + 160
                 and top <= ln.cy <= bottom and abs(ln.dir[0] - 1) < 0.05]
        rows: list[dict] = []
        for lb in labels:
            same = sorted([r for r in right if abs(r.cy - lb.cy) < 0.5 * h], key=lambda r: r.bbox[0])
            if same or not rows:
                sym, val = "", ""
                if len(same) >= 2:                  # обозначение (m, z, x…) + значение
                    sym, val = same[0].text.strip(), " ".join(s.text.strip() for s in same[1:])
                elif same:
                    val = same[0].text.strip()
                rows.append({"label": lb.text.strip(), "sym": sym, "value": val, "line": lb, "vals": same})
            else:
                rows[-1]["label"] += " " + lb.text.strip()
        # значения, перенесённые на следующую строку ячейки («по ГОСТ» / «13755-2015»)
        used = {id(v) for r in rows for v in r["vals"]}
        for r in right:
            if id(r) in used:
                continue
            prev = [row for row in rows if row["line"].cy < r.cy]
            if prev and prev[-1]["vals"] and abs(r.bbox[0] - prev[-1]["vals"][-1].bbox[0]) < 2:
                prev[-1]["value"] = (prev[-1]["value"] + " " + r.text.strip()).strip()
        params = {}
        for row in rows:
            lab = re.sub(r"\s+", " ", row["label"]).strip(" ,")
            for key, rx in PARAMS:
                if key not in params and rx.search(lab):
                    params[key] = row
                    break
        text = " ".join(r["label"] + " " + r["value"] for r in rows)
        spline = bool(re.search(r"(?i)шлиц|6033|6333|условное обозначение", text)) or (
            "profile" not in params and any(SPL.search(ln.text) for ln in drw.lines))
        tables.append({"page": pg, "bbox": anchor.bbox, "rows": rows, "params": params, "spline": spline,
                       "text": text})
    return tables


def _num(row: dict | None) -> float | None:
    if not row:
        return None
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", row["value"])
    return to_float(m.group(0)) if m else None


def _beta(row: dict | None) -> float:
    if not row:
        return 0.0
    v = row["value"]
    m = re.search(r"(\d+)\s*°(?:\s*(\d+)\s*['′])?(?:\s*(\d+(?:[.,]\d+)?)\s*(?:\"|″|''))?", v)
    if not m:
        return 0.0
    return int(m.group(1)) + int(m.group(2) or 0) / 60 + (to_float(m.group(3)) or 0) / 3600


def check_gears(drw: Drawing, cfg: dict) -> None:
    tables = parse_tables(drw)
    drw.facts["gear"] = [{k: (v["value"] if v else None) for k, v in t["params"].items()} | {"spline": t["spline"]}
                         for t in tables]
    for t in tables:
        p, pg = t["params"], t["page"]

        def where(key):
            r = p.get(key)
            return (pg, r["line"].bbox) if r else (pg, t["bbox"])

        m, z, d = _num(p.get("m")), _num(p.get("z")), _num(p.get("d"))
        if m:
            series = SPLINE_MODULES if t["spline"] else MODULES_1 + MODULES_2
            if not any(abs(m - x) < 1e-6 for x in series):
                near = sorted(series, key=lambda x: abs(x - m))[:2]
                drw.add(WARNING, "Z01", CAT_GEAR, f"Модуль {fmtn(m)} не из ряда {'ГОСТ 6033-80' if t['spline'] else 'ГОСТ 9563-60'} "
                        f"(ближайшие {', '.join(fmtn(x) for x in sorted(near))})", *where("m"),
                        "ГОСТ 6033-80" if t["spline"] else "ГОСТ 9563-60")
            elif not t["spline"] and not any(abs(m - x) < 1e-6 for x in MODULES_1):
                drw.add(INFO, "Z07", CAT_GEAR, f"Модуль {fmtn(m)} — из 2-го ряда ГОСТ 9563-60; 1-й ряд предпочтительнее",
                        *where("m"), "ГОСТ 9563-60")
        if not t["spline"]:
            missing = [NAMES[k] for k in ("m", "z", "profile", "x", "precision", "d") if k not in p]
            if missing:
                drw.add(WARNING, "Z02", CAT_GEAR, f"В таблице параметров зубчатого венца нет строк: "
                        f"{', '.join(missing)}", pg, t["bbox"], STD)
        if m and z and d:
            beta = _beta(p.get("beta"))
            exp = m * z / math.cos(math.radians(beta))
            if abs(d - exp) > 0.01 + 0.0005 * exp:
                drw.add(ERROR, "Z03", CAT_GEAR, f"Делительный диаметр d = {fmtn(d)}, а m·z{'/cos β' if beta else ''} = "
                        f"{fmtn(round(exp, 3))} (m = {fmtn(m)}, z = {int(z)}{f', β = {beta:.4g}°' if beta else ''})",
                        *where("d"), STD)
        pr = p.get("precision")
        if pr and not t["spline"]:
            v = pr["value"].strip()
            mm = re.match(r"^(\d{1,2})(?:\s*-\s*(\d{1,2})\s*-\s*(\d{1,2}))?\s*(-)?\s*([A-Za-zА-Яа-я])([a-zа-я])?", v)
            if mm:
                if int(mm.group(1)) > 12 or int(mm.group(1)) < 1:
                    drw.add(WARNING, "Z04", CAT_GEAR, f"Степень точности «{v}»: по ГОСТ 1643-81 — от 1 до 12",
                            *where("precision"), "ГОСТ 1643-81")
                elif mm.group(5).upper() not in GEAR_FITS:
                    drw.add(WARNING, "Z04", CAT_GEAR, f"Степень точности «{v}»: вид сопряжения «{mm.group(5)}» по "
                            f"ГОСТ 1643-81 — A, B, C, D, E, H", *where("precision"), "ГОСТ 1643-81")
                elif not mm.group(4):
                    drw.add(INFO, "Z04", CAT_GEAR, f"Степень точности «{v}»: записывают через дефис — "
                            f"«{mm.group(1)}-{mm.group(5)}»", *where("precision"), "ГОСТ 1643-81")
            if "ГОСТ" not in v and not re.search(r"ГОСТ\s*1643", t["text"]):
                drw.add(WARNING, "Z05", CAT_GEAR, f"Степень точности «{v}» указана без обозначения стандарта — "
                        f"«{v} ГОСТ 1643-81»", *where("precision"), STD)
        xr = p.get("x")
        if xr and not t["spline"]:
            v = xr["value"].strip()
            xv = _num(xr)
            if xv and not re.match(r"^[-+−]", v):
                drw.add(INFO, "Z06", CAT_GEAR, f"Коэффициент смещения «{v}» указывают со знаком («+{v}» или «−{v}»)",
                        *where("x"), STD)
