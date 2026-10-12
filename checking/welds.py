"""Сварные швы: обозначения по ГОСТ 2.312-72 и стандартам на соединения."""
from __future__ import annotations

import re

from .model import Drawing, ERROR, WARNING, INFO, CAT_WELD
from .standards import fmtn
from .textnorm import to_float

# Диапазоны условных обозначений соединений по стандартам (С — стыковые, У — угловые, Т — тавровые,
# Н — нахлёсточные). Границы взяты с запасом — замечание выдаётся только за явный выход из ряда.
JOINTS = {
    "5264": {"С": 40, "У": 10, "Т": 9, "Н": 2},       # ручная дуговая
    "14771": {"С": 27, "У": 10, "Т": 10, "Н": 2},     # в защитном газе
    "8713": {"С": 59, "У": 11, "Т": 9, "Н": 2},       # под флюсом
    "11534": {"У": 10, "Т": 10},                       # РДС под острыми и тупыми углами
    "11533": {"У": 9, "Т": 10},                        # под флюсом под углами
    "23518": {"У": 9, "Т": 11},                        # в защитных газах под углами
    "14776": {"Н": 4, "Т": 10},                        # точечная/рельефная
    "14098": {"С": 30, "Т": 15, "Н": 3, "К": 3},      # арматура
}
STD_NAMES = {"5264": "ГОСТ 5264-80", "14771": "ГОСТ 14771-76", "8713": "ГОСТ 8713-79", "11534": "ГОСТ 11534-75",
             "11533": "ГОСТ 11533-75", "23518": "ГОСТ 23518-79", "14776": "ГОСТ 14776-79", "14098": "ГОСТ 14098-2014"}

STD_IN_TEXT = re.compile(r"ГОСТ\s?Р?\s?(5264|14771|8713|11534|11533|23518|14776|14098|15164)")
WELD_LINE = re.compile(
    r"^(?:(?:ГОСТ\s?Р?\s?)?(?P<std>\d{4,5})(?:-\d{2,4})?\s*-\s*)?"
    r"(?P<type>[СУТНКCYTHK])(?P<num>\d{1,2})"
    r"(?:\s*-\s*(?P<method>[А-ЯA-Z]{1,3}))?"
    r"(?:\s*-\s*(?P<leg_mark>[⊿△▷]|ì)\s*(?P<leg>\d+(?:[.,]\d+)?)?)?"
    r"(?P<rest>.*)$")
LAT = str.maketrans("CYTHK", "СУТНК")


def _parse(text: str) -> dict | None:
    t = text.strip().replace("–", "-")
    if not re.search(r"[СУТНКCYTHK]\d{1,2}", t):
        return None
    m = WELD_LINE.match(t)
    if not m:
        return None
    has_leg_mark = bool(m.group("leg_mark")) or "⊿" in t
    if not has_leg_mark and not m.group("std") and not m.group("method"):
        return None                                   # «Т1» без признаков шва — может быть что угодно
    return {"raw": t, "std": m.group("std"), "type": m.group("type").translate(LAT), "num": int(m.group("num")),
            "method": m.group("method"), "leg_mark": has_leg_mark, "leg": to_float(m.group("leg"))}


def check_welds(drw: Drawing, cfg: dict) -> None:
    welds = []
    for ln in drw.lines:
        if len(ln.text) > 40:
            continue
        w = _parse(ln.text)
        if w:
            w["page"], w["bbox"] = ln.page, ln.bbox
            welds.append(w)
    tt = " ".join(drw.tt)
    tt_std = set(STD_IN_TEXT.findall(tt))
    drw.facts["welds"] = [{k: v for k, v in w.items() if k != "bbox"} for w in welds]
    if not welds:
        return
    thick = [d.nominal for d in drw.dims if d.kind == "thickness" and d.nominal]
    if drw.facts.get("sheet_thickness"):
        thick.append(drw.facts["sheet_thickness"])
    for w in welds:
        pg, bb = w["page"], w["bbox"]
        std = w["std"] or (next(iter(tt_std)) if len(tt_std) == 1 else None)
        if w["leg_mark"] and w["leg"] is None:
            drw.add(ERROR, "W01", CAT_WELD, f"Обозначение шва «{w['raw']}»: после знака ⊿ не указан катет",
                    pg, bb, "ГОСТ 2.312-72")
        if not w["std"] and not tt_std:
            drw.add(WARNING, "W03", CAT_WELD, f"Шов «{w['raw']}»: не указан стандарт на сварное соединение — ни в "
                    f"обозначении, ни в ТТ («Сварные швы по ГОСТ 14771-76»)", pg, bb, "ГОСТ 2.312-72")
        if w["std"] and tt_std and w["std"] not in tt_std:
            drw.add(WARNING, "W05", CAT_WELD, f"Шов «{w['raw']}» выполнен по {STD_NAMES.get(w['std'], w['std'])}, а в ТТ "
                    f"указан {', '.join(STD_NAMES.get(s, s) for s in sorted(tt_std))}", pg, bb)
        rng = JOINTS.get(std or "")
        if rng is not None:
            top = rng.get(w["type"])
            if top is None:
                drw.add(WARNING, "W02", CAT_WELD, f"Шов «{w['raw']}»: соединений типа «{w['type']}» в "
                        f"{STD_NAMES.get(std, std)} нет — проверьте обозначение", pg, bb, STD_NAMES.get(std))
            elif w["num"] > top:
                drw.add(WARNING, "W02", CAT_WELD, f"Шов «{w['raw']}»: в {STD_NAMES.get(std, std)} соединения "
                        f"{w['type']}1…{w['type']}{top}, «{w['type']}{w['num']}» нет — проверьте обозначение",
                        pg, bb, STD_NAMES.get(std))
        if w["leg"]:
            if thick and w["leg"] > 1.2 * max(thick) + 1e-6:
                drw.add(WARNING, "W04", CAT_WELD, f"Катет {fmtn(w['leg'])} мм в «{w['raw']}» больше 1,2·s "
                        f"наибольшей толщины на чертеже ({fmtn(max(thick))} мм) — шов перегревает металл, "
                        f"проверьте катет", pg, bb, STD_NAMES.get(std))
            if w["leg"] < 3:
                drw.add(INFO, "W04", CAT_WELD, f"Катет {fmtn(w['leg'])} мм в «{w['raw']}» меньше 3 мм — для "
                        f"полуавтомата обычно минимальный катет 3 мм", pg, bb)
