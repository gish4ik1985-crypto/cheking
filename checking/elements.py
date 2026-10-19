"""Элементы деталей и соединения: центровые отверстия (ГОСТ 14034-74), шпоночные пазы (ГОСТ 23360-78),
шлицы (ГОСТ 1139-80, ГОСТ 6033-80), резьбы Tr (ГОСТ 24738-81) и G (ГОСТ 6357-81), фаски и углы (ГОСТ 2.307,
ГОСТ 8908-81)."""
from __future__ import annotations

import re

from .model import Drawing, ERROR, WARNING, INFO, CAT_DIM, CAT_EL
from .normdata import (CENTER_HOLES, KEYS_23360, KEY_SLOT_FIELDS, SPLINES_1139, SPLINE_MODULES, TRAPEZOID,
                       PIPE_G, NORMAL_ANGLES)
from .standards import fmtn
from .textnorm import to_float, CYR_TO_LAT
from .textreq import texts

CENTER = re.compile(r"(?i)отв\.?\s*центр\.?\s*(?P<form>[A-ZА-Я])\s*(?P<thr>[MМ])?\s*(?P<d>\d+(?:[.,]\d+)?)")
SPL_1139 = re.compile(r"\b(?P<c>[dDb])\s*-\s*(?P<z>\d{1,2})\s*[×xхX]\s*(?P<d>\d{2,3})(?:[A-Za-z]{1,2}\d{1,2}"
                      r"(?:/[a-z]{1,2}\d{1,2})?)?\s*[×xхX]\s*(?P<D>\d{2,3})(?:[A-Za-z]{1,2}\d{1,2}(?:/[a-z]{1,2}\d{1,2})?)?"
                      r"\s*[×xхX]\s*(?P<b>\d+(?:[.,]\d+)?)")
SPL_6033 = re.compile(r"(?<![\d,.])(?P<D>\d{2,3})\s*[×xх]\s*(?P<m>\d+(?:[.,]\d+)?)\s*[×xх]\s*"
                      r"(?P<fit>\d{1,2}[A-Za-zА-Яа-я]{1,2})\b")
FORM_LAT = str.maketrans("АВТСЕНРR", "ABTCEHPR")


def check_elements(drw: Drawing, cfg: dict) -> None:
    all_t = texts(drw)
    _center_holes(drw, all_t)
    _splines(drw, all_t)
    _keyways(drw)
    _threads_angles(drw)


def _center_holes(drw: Drawing, all_t) -> None:
    seen = set()
    for t, pg, bb in all_t:
        for m in CENTER.finditer(t):
            form = m.group("form").upper().translate(FORM_LAT)
            d = to_float(m.group("d"))
            if (form, d) in seen:
                continue
            seen.add((form, d))
            src = m.group(0).strip()
            if form not in CENTER_HOLES:
                drw.add(ERROR, "K01", CAT_EL, f"«{src}»: формы {m.group('form')} в ГОСТ 14034-74 нет (A, B, T, C, E, R, "
                        f"F, H, P)", pg, bb, "ГОСТ 14034-74")
                continue
            series = CENTER_HOLES[form]
            if d is not None and not any(abs(d - x) < 1e-6 for x in series):
                hint = ""
                if form in "CE" and any(abs(d - x) < 1e-6 for x in CENTER_HOLES["A"]):
                    hint = f" — возможно, имелась в виду форма A или B ({'A'}{fmtn(d)})"
                kind = "резьбы М" if form in "FHP" else "d = "
                drw.add(ERROR, "K01", CAT_EL, f"«{src}»: для формы {form} по ГОСТ 14034-74 {kind}"
                        f"{', '.join(fmtn(x) for x in series)}; {fmtn(d)} нет{hint}", pg, bb, "ГОСТ 14034-74")


def _splines(drw: Drawing, all_t) -> None:
    joined = " ".join(t for t, _, _ in all_t)
    for t, pg, bb in all_t:
        for m in SPL_1139.finditer(t):
            z, d, D = int(m.group("z")), int(m.group("d")), int(m.group("D"))
            b = to_float(m.group("b"))
            exp = SPLINES_1139.get((z, d, D))
            if exp is None:
                drw.add(ERROR, "K03", CAT_EL, f"Шлицевое соединение «{m.group(0)}»: сочетания z×d×D = {z}×{d}×{D} "
                        f"нет в ГОСТ 1139-80", pg, bb, "ГОСТ 1139-80")
            elif b is not None and abs(b - exp) > 1e-6:
                drw.add(ERROR, "K03", CAT_EL, f"Шлицевое соединение «{m.group(0)}»: для {z}×{d}×{D} ширина зуба "
                        f"b = {fmtn(exp)}, указано {fmtn(b)}", pg, bb, "ГОСТ 1139-80")
    seen = False
    for t, pg, bb in all_t:
        for m in SPL_6033.finditer(t):
            if seen:
                return
            seen = True
            mod = to_float(m.group("m"))
            if mod is not None and not any(abs(mod - x) < 1e-6 for x in SPLINE_MODULES):
                drw.add(WARNING, "K04", CAT_EL, f"Эвольвентное шлицевое соединение «{m.group(0)}»: модуль {fmtn(mod)} "
                        f"не из ряда ГОСТ 6033-80", pg, bb, "ГОСТ 6033-80")
            if re.search(r"ГОСТ\s*6033\s*[-–]\s*80", joined):
                continue
            wrong = re.search(r"ГОСТ\s*(\d{4})\s*[-–]\s*(\d{2,4})", t) or \
                re.search(r"ГОСТ\s*(6\d33|60\d3|603\d)\s*[-–]\s*(\d{2,4})", joined)
            if wrong:
                drw.add(WARNING, "K04", CAT_EL, f"Эвольвентное шлицевое соединение «{m.group(0)}» обозначено со ссылкой "
                        f"на «{wrong.group(0)}» — такие соединения выполняют по ГОСТ 6033-80", pg, bb, "ГОСТ 6033-80")


def _keyways(drw: Drawing) -> None:
    diams = sorted({d.nominal for d in drw.dims if d.kind == "diameter" and d.nominal and not d.reference})
    if not diams:
        return
    widths = {row[2] for row in KEYS_23360}
    for d in drw.dims:
        f = (d.field or "").upper()
        if d.kind != "linear" or not d.nominal or f not in KEY_SLOT_FIELDS or d.nominal not in widths:
            continue
        rows = [r for r in KEYS_23360 if r[2] == d.nominal]
        if any(lo < x <= hi for r in rows for lo, hi in [(r[0], r[1])] for x in diams):
            continue
        r = rows[0]
        drw.add(INFO, "K02", CAT_EL, f"Паз «{d.raw}»: шпонка b = {fmtn(d.nominal)} по ГОСТ 23360-78 — для валов "
                f"⌀ свыше {fmtn(r[0])} до {fmtn(r[1])} мм; таких диаметров на чертеже нет "
                f"({', '.join(fmtn(x) for x in diams[:6])}) — проверьте ширину паза", d.page, d.bbox, "ГОСТ 23360-78")


def _threads_angles(drw: Drawing) -> None:
    for d in drw.dims:
        pg, bb = d.page, d.bbox
        if d.kind == "chamfer" and d.angle and abs(d.angle - 45) > 1e-6:
            drw.add(WARNING, "D21", CAT_DIM, f"Фаска «{d.raw}» не под 45°: такие фаски задают двумя линейными или "
                    f"линейным и угловым размерами, запись «a×α» — только для 45°", pg, bb, "ГОСТ 2.307-2011 п. 5.44")
        elif d.kind == "angle" and d.nominal is not None:
            deg = d.nominal
            mm = re.search(r"°\s*(\d+)\s*['′]", d.raw)
            if mm:
                deg += int(mm.group(1)) / 60
            if not any(abs(deg - a) < 1e-6 for a in NORMAL_ANGLES):
                drw.add(INFO, "D23", CAT_DIM, f"Угол «{d.raw}» не из рядов нормальных углов ГОСТ 8908-81", pg, bb,
                        "ГОСТ 8908-81")
        elif d.kind == "thread_tr" and d.nominal:
            pitches = TRAPEZOID.get(d.nominal)
            if pitches is None:
                near = sorted(TRAPEZOID, key=lambda x: abs(x - d.nominal))[:2]
                drw.add(ERROR, "D24", CAT_DIM, f"Резьба «{d.raw}»: диаметра {fmtn(d.nominal)} нет в ГОСТ 24738-81 "
                        f"(ближайшие Tr{', Tr'.join(fmtn(x) for x in sorted(near))})", pg, bb, "ГОСТ 24738-81")
            elif d.pitch and not any(abs(d.pitch - p) < 1e-6 for p in pitches):
                drw.add(ERROR, "D24", CAT_DIM, f"Резьба «{d.raw}»: шаг {fmtn(d.pitch)} не предусмотрен для Tr"
                        f"{fmtn(d.nominal)} (по ГОСТ 24738-81: {', '.join(fmtn(p) for p in pitches)})", pg, bb,
                        "ГОСТ 24738-81")
        elif d.kind == "thread_g":
            size = (d.g_size or "").strip()
            if size and size not in PIPE_G:
                drw.add(ERROR, "D25", CAT_DIM, f"Резьба «{d.raw}»: размера G {size} нет в ГОСТ 6357-81", pg, bb,
                        "ГОСТ 6357-81")
            elif not d.thread_tol:
                drw.add(INFO, "D25", CAT_DIM, f"Резьба «{d.raw}»: не указан класс точности (A или B) — «G {size}-A»",
                        pg, bb, "ГОСТ 6357-81")
    for ln in drw.lines:
        if re.fullmatch(r"\s*[⌀R]?\d+(?:[.,]\d+)?\s*мм\s*", ln.text) and ln not in drw.tt_lines:
            from .titleblock import excluded
            if not excluded(drw, ln):
                drw.add(WARNING, "D22", CAT_DIM, f"Размер «{ln.text.strip()}» с единицами: линейные размеры на чертеже "
                        f"указывают в миллиметрах без обозначения единицы", ln.page, ln.bbox, "ГОСТ 2.307-2011 п. 4.7")
                break
