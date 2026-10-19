"""Сварные швы: соответствие типа соединения описанию, способ сварки и толщина (коды Y01–Y08).

Таблицы типов взяты из ГОСТ 5264-80 и ГОСТ 14771-76 (табл. 1). Программа не видит геометрию шва, поэтому тип
соединения (стыковое, угловое, тавровое, нахлёсточное) проверяется по тому, что написано рядом с обозначением и в ТТ."""
from __future__ import annotations

import math
import re

from .model import Drawing, WARNING, INFO, CAT_WELD, CAT_FILE
from .standards import fmtn
from .welds import _parse, STD_NAMES

S_5264 = "ГОСТ 5264-80 табл. 1"
S_14771 = "ГОСТ 14771-76 п. 2, табл. 1"
S_2312 = "ГОСТ 2.312-72"

KINDS = {"С": "стыковое", "У": "угловое", "Т": "тавровое", "Н": "нахлёсточное", "К": "крестовое"}
# слово в тексте → буква типа соединения
WORD_KIND = (("стыков", "С"), ("углов", "У"), ("тавров", "Т"), ("нахлест", "Н"), ("нахлёст", "Н"), ("внахлест", "Н"),
             ("внахлёст", "Н"), ("крестов", "К"))
NEAR_MM = 40.0

# 14771: допустимые обозначения способа сварки; 5264 — ручная сварка, способа в обозначении нет
METHODS_14771 = {"ИН", "ИНп", "ИП", "УП"}
METHOD_RE = re.compile(r"-\s*(ИНп|ИН|ИП|УП|Нп|Н|Пр|П|Ф|Р|А|Г|Л)\b")

# 5264, толщина s, мм (только однозначно прочитанные строки табл. 1; остальные не проверяются, сверить)
RANGE_5264 = {("С", 1): (1, 4), ("С", 3): (1, 4), ("С", 4): (1, 4), ("С", 6): (1, 4), ("С", 7): (2, 5), ("С", 8): (3, 60),
              ("С", 15): (8, 100), ("С", 17): (3, 60), ("С", 19): (6, 100), ("С", 20): (3, 60), ("С", 25): (8, 120),
              ("У", 1): (1, 4), ("У", 2): (1, 12), ("У", 6): (3, 60), ("У", 8): (8, 100), ("У", 9): (3, 60),
              ("Т", 2): (15, 100), ("Т", 5): (30, 120), ("Т", 6): (3, 60), ("Т", 8): (8, 100), ("Т", 9): (12, 100)}



def _kind_of(word: str) -> str | None:
    w = word.lower().replace("ё", "е")
    for stem, k in WORD_KIND:
        if w.startswith(stem.replace("ё", "е")):
            return k
    return None


def _welds_with_bbox(drw: Drawing) -> list:
    out = []
    for ln in drw.lines:
        if len(ln.text) > 40:
            continue
        w = _parse(ln.text)
        if w:
            w["page"], w["bbox"] = ln.page, ln.bbox
            out.append(w)
    return out


def _dist(a, b) -> float:
    dx = max(a[0] - b[2], b[0] - a[2], 0)
    dy = max(a[1] - b[3], b[1] - a[3], 0)
    return math.hypot(dx, dy)


def _std_of(w: dict, tt_std: set) -> str | None:
    return w.get("std") or (next(iter(tt_std)) if len(tt_std) == 1 else None)


def check_weld_words(drw: Drawing, welds: list) -> None:
    """Y01: слово рядом с обозначением («стыковой», «угловой») не совпадает с буквой типа соединения;
    Y02: то же в ТТ («Швы У4 — стыковые»)."""
    seen = set()
    for w in welds:
        for ln in drw.lines:
            if ln.page != w["page"] or ln.text.strip() == w["raw"] or len(ln.text) > 80:
                continue
            if _dist(ln.bbox, w["bbox"]) > NEAR_MM:
                continue
            for m in re.finditer(r"[А-Яа-яЁё]{6,}", ln.text):
                k = _kind_of(m.group(0))
                if k and k != w["type"] and (w["raw"], k) not in seen:
                    seen.add((w["raw"], k))
                    drw.add(WARNING, "Y01", CAT_WELD, f"Шов «{w['raw']}» — {KINDS[w['type']]} соединение "
                            f"({w['type']}), а рядом написано «{m.group(0)}» ({KINDS[k]}): проверьте, какое соединение "
                            f"заложено — от этого зависят тип шва, разделка кромок и катет", w["page"], w["bbox"], S_2312)
    items = drw.facts.get("_tt_items") or [(t, None, None) for t in drw.tt]
    for t, pg, bb in items:
        for m in re.finditer(r"([А-Яа-яЁё]{6,})\s+(?:шв\w*|соединени\w*)?\W{0,3}\s*([СУТН])\s?(\d{1,2})(?!\d)", t):
            k = _kind_of(m.group(1))
            if k and k != m.group(2):
                drw.add(WARNING, "Y02", CAT_WELD, f"В ТТ «{m.group(1)}» относится к «{m.group(2)}{m.group(3)}», но "
                        f"{m.group(2)} — {KINDS[m.group(2)]} соединение", pg, bb, S_2312)
        for m in re.finditer(r"([СУТН])\s?(\d{1,2})(?!\d)\W{0,6}(?:шв\w*|соединени\w*)?\s*[-–—(]*\s*([А-Яа-яЁё]{6,})", t):
            k = _kind_of(m.group(3))
            if k and k != m.group(1):
                drw.add(WARNING, "Y02", CAT_WELD, f"В ТТ «{m.group(1)}{m.group(2)}» названо словом «{m.group(3)}», но "
                        f"{m.group(1)} — {KINDS[m.group(1)]} соединение", pg, bb, S_2312)


def check_weld_method(drw: Drawing, welds: list, tt_std: set) -> None:
    """Y03–Y04: способ сварки в обозначении и стандарт на соединение."""
    for w in welds:
        std = _std_of(w, tt_std)
        m = METHOD_RE.search(w["raw"])
        method = m.group(1) if m else None
        if std == "5264" and method:
            drw.add(WARNING, "Y03", CAT_WELD, f"Шов «{w['raw']}»: ГОСТ 5264-80 — ручная дуговая сварка, способ сварки в "
                    f"обозначении не указывают; если сварка в газе или под флюсом, нужен ГОСТ 14771-76 или 8713-79",
                    w["page"], w["bbox"], S_5264)
        elif std == "14771":
            if method and method not in METHODS_14771:
                drw.add(WARNING, "Y04", CAT_WELD, f"Шов «{w['raw']}»: способ сварки «{method}» не предусмотрен "
                        f"ГОСТ 14771-76 — допустимы ИН, ИНп, ИП, УП", w["page"], w["bbox"], S_14771)
            elif not method:
                drw.add(INFO, "Y04", CAT_WELD, f"Шов «{w['raw']}»: в обозначении по ГОСТ 14771-76 указывают способ "
                        f"сварки (ИН, ИНп, ИП или УП)", w["page"], w["bbox"], S_14771)


def check_weld_thickness(drw: Drawing, welds: list, tt_std: set) -> None:
    """Y05: толщина детали выходит за диапазон, для которого ГОСТ 5264-80 даёт это соединение."""
    thick = [d.nominal for d in drw.dims if d.kind == "thickness" and d.nominal]
    if drw.facts.get("sheet_thickness"):
        thick.append(drw.facts["sheet_thickness"])
    if not thick:
        return
    lo_t, hi_t = min(thick), max(thick)
    for w in welds:
        if _std_of(w, tt_std) != "5264":
            continue
        rng = RANGE_5264.get((w["type"], w["num"]))
        if not rng:
            continue
        if hi_t < rng[0] or lo_t > rng[1]:
            drw.add(INFO, "Y05", CAT_WELD, f"Шов «{w['raw']}»: по ГОСТ 5264-80 это соединение для толщин "
                    f"{rng[0]}–{rng[1]} мм, а на чертеже {fmtn(lo_t)}"
                    f"{'' if lo_t == hi_t else '–' + fmtn(hi_t)} мм — подберите другое соединение",
                    w["page"], w["bbox"], S_5264)


def check_weld_presence(drw: Drawing, welds: list, tt_std: set) -> None:
    """Y06: сварная конструкция без обозначений швов; Y07: ТТ про швы без стандарта на соединение."""
    name = (getattr(drw.title, "name", "") or "").lower()
    tt = " ".join(drw.tt).lower()
    weld_words = re.search(r"сварн|сварк|\bшв[аоеиу]|приварит", tt) or "сварн" in name or "сварк" in name
    if weld_words and not welds:
        drw.add(INFO, "Y06", CAT_WELD, "В названии или в ТТ говорится о сварке, а обозначений сварных швов на чертеже "
                "не найдено — швы обозначают по ГОСТ 2.312-72 (знак шва, выноска, катет)", None, None, S_2312)


def check_weld_mix(drw: Drawing, welds: list, tt_std: set) -> None:
    """Y07: на чертеже швы по разным стандартам без пояснения; Y08: «К» (крестовое) в стандарте без таких соединений."""
    stds = {w["std"] for w in welds if w["std"]}
    if len(stds) > 1 and not tt_std:
        drw.add(INFO, "Y07", CAT_WELD, "Швы обозначены по разным стандартам (" + ", ".join(
            STD_NAMES.get(s, s) for s in sorted(stds)) + "), общего пояснения в ТТ нет — укажите, какие швы по какому "
                "стандарту", None, None, S_2312)
    for w in welds:
        std = _std_of(w, tt_std)
        if w["type"] == "К" and std in ("5264", "14771", "8713"):
            drw.add(WARNING, "Y08", CAT_WELD, f"Шов «{w['raw']}»: крестовых соединений в {STD_NAMES.get(std, std)} "
                    f"нет — они есть в ГОСТ 14098-2014 (арматура); для остальных конструкций проверьте тип шва",
                    w["page"], w["bbox"], STD_NAMES.get(std))
            break


def check_welds2(drw: Drawing, cfg: dict) -> None:
    welds = _welds_with_bbox(drw)
    tt_std = set(re.findall(r"ГОСТ\s?Р?\s?(5264|14771|8713|11534|11533|23518|14776|14098)", " ".join(drw.tt)))
    for fn, args in ((check_weld_words, (welds,)), (check_weld_method, (welds, tt_std)),
                     (check_weld_thickness, (welds, tt_std)), (check_weld_presence, (welds, tt_std)),
                     (check_weld_mix, (welds, tt_std))):
        try:
            fn(drw, *args)
        except Exception as e:
            drw.add(WARNING, "F07", CAT_FILE, f"Проверка «{fn.__name__}» не выполнена: {type(e).__name__}: {e}")
