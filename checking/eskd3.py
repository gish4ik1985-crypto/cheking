"""Правила по ГОСТ 6033, 6357, 6636, 8724, 8908, 9013, 9563, 10948, 11284, 14034 (коды U01–U10).

Часть требований по этим стандартам уже контролируют D11, D15, D17, D23, D25, D26, D29, H02, K01, K04, Z01, Z07;
здесь — дополнительные проверки записи резьб, твёрдости, радиусов, отверстий под крепёж и центровых отверстий.
Справка: docs/norms/ESKD_RULES_3.md."""
from __future__ import annotations

import re

from .model import Drawing, WARNING, INFO, CAT_DIM, CAT_HEAT, CAT_EL, CAT_FILE
from .normdata import CLEARANCE_HOLES
from .standards import fmtn
from .textnorm import to_float
from .textreq import texts

S_8724 = "ГОСТ 8724-2002; ГОСТ 2.311-68 п. 12"
S_6357 = "ГОСТ 6357-81"
S_9013 = "ГОСТ 9013-59 (ИСО 6508)"
S_10948 = "ГОСТ 10948-64"
S_11284 = "ГОСТ 11284-75"
S_14034 = "ГОСТ 14034-74"
S_6636 = "ГОСТ 6636-69"

# нормальные радиусы свыше 10 мм (ГОСТ 10948-64)
RADII_ABOVE_10 = {12, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 320, 400, 500}
# ряд Ra40 ГОСТ 6636-69 для 1…10 (дальше умножается на 10, 100…)
_RA40 = [1.0, 1.05, 1.1, 1.15, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.4, 2.5, 2.6, 2.8, 3.0, 3.2,
         3.4, 3.6, 3.8, 4.0, 4.2, 4.5, 4.8, 5.0, 5.3, 5.6, 6.0, 6.3, 6.7, 7.1, 7.5, 8.0, 8.5, 9.0, 9.5]


def _in_ra40(x: float) -> bool:
    if x <= 0:
        return True
    while x >= 10 - 1e-9:
        x /= 10
    while x < 1 - 1e-9:
        x *= 10
    # «ряды» ГОСТ 6636 округляют значения до 3 знаков, поэтому сравниваем с допуском
    return any(abs(x - r) < 0.011 * max(1.0, r) for r in _RA40)


def check_thread_write(drw: Drawing) -> None:
    """U01–U03: запись резьб (ГОСТ 8724, 6357, 2.311)."""
    done = set()
    for t, pg, bb in texts(drw):
        if "U01" not in done:
            m = re.search(r"(?<![A-Za-zА-Яа-я])[МM]\s?(\d{1,3}(?:[.,]\d+)?)\s*[xXхХ]\s?(\d(?:[.,]\d+)?)(?!\d)", t)
            if m:
                done.add("U01")
                drw.add(INFO, "U01", CAT_DIM, f"«{m.group(0)}»: шаг резьбы отделяют знаком «×» (умножения), а не буквой "
                        f"«x»/«х» — «М{m.group(1)}×{m.group(2)}»", pg, bb, S_8724)
        if "U02" not in done:
            m = re.search(r"[Тт]руб(?:н\w*|\.)\s*(?:цилиндр\w*\.?|цил\.)?\s*(?:резьб\w*)?\s*(\d+(?:/\d+)?)\s*(?:\"|”|″|дюйм)", t)
            if m:
                done.add("U02")
                drw.add(WARNING, "U02", CAT_DIM, f"«{m.group(0).strip()}»: трубную цилиндрическую резьбу обозначают "
                        f"буквой G и размером в дюймах без кавычек — «G{m.group(1)}» (с классом A или B для наружной)",
                        pg, bb, S_6357)
        if "U03" not in done:
            m = re.search(r"[⌀Ø∅]\s?G\s?\d", t)
            if m:
                done.add("U03")
                drw.add(WARNING, "U03", CAT_DIM, f"«{t.strip()[:40]}»: размер трубной резьбы G — условный проход трубы "
                        f"в дюймах, знак ⌀ перед обозначением не ставят", pg, bb, S_6357)


def check_hardness_scale(drw: Drawing) -> None:
    """U04: твёрдость по шкале C Роквелла определяют в пределах 20…70 HRC (ГОСТ 9013)."""
    for t, pg, bb in texts(drw):
        for m in re.finditer(r"(?:HRC|HRС|НRС|HRc)[^\d]{0,3}(\d{1,3})(?:\s*[…\-–]\s*(\d{1,3}))?|"
                             r"(\d{1,3})(?:\s*[…\-–]\s*(\d{1,3}))?\s*(?:HRC|HRС|НRС)", t):
            nums = [float(x) for x in m.groups() if x]
            if nums and min(nums) < 20 - 1e-9:
                drw.add(WARNING, "U04", CAT_HEAT, f"«{m.group(0).strip()}»: по шкале C Роквелла твёрдость определяют "
                        f"в пределах 20…70 HRC; мягкие материалы задают в HB (ГОСТ 9012) или по шкале B (HRB)",
                        pg, bb, S_9013)
                return


def check_radii_series(drw: Drawing) -> None:
    """U05: радиусы 10…500 мм из ряда ГОСТ 10948 (выключено по умолчанию)."""
    for d in drw.dims:
        if d.kind == "radius" and d.nominal and 10 < d.nominal <= 500 and d.nominal not in RADII_ABOVE_10 \
                and abs(d.nominal - round(d.nominal)) < 1e-9 and not (d.upper_raw or d.lower_raw):
            drw.add(INFO, "U05", CAT_DIM, f"Радиус «{d.raw}»: {fmtn(d.nominal)} мм нет в ряду нормальных радиусов "
                    f"ГОСТ 10948-64 (…12, 16, 20, 25, 32, 40, 50, 63, 80, 100…)", d.page, d.bbox, S_10948)
            break


def check_hole_for_fastener(drw: Drawing) -> None:
    """U06: «N отв. ⌀X» близко к стандартному отверстию под крепёж ГОСТ 11284, но не совпадает."""
    std = sorted({x for row in CLEARANCE_HOLES.values() for x in row})
    for t, pg, bb in texts(drw):
        m = re.search(r"(\d+)\s*отв\.?[^⌀Ø∅\d]{0,20}[⌀Ø∅]\s?(\d+(?:[.,]\d+)?)(?![\d,.]*\s*[Hh]\d)", t)
        if not m:
            continue
        x = to_float(m.group(2))
        if x is None or x in std or x < 3 or x > 56:
            continue
        near = min(std, key=lambda s: abs(s - x))
        if abs(near - x) <= 0.3:
            drw.add(INFO, "U06", CAT_EL, f"«{m.group(0).strip()}»: ближайшее стандартное сквозное отверстие под крепёж — "
                    f"⌀{fmtn(near)} (ГОСТ 11284-75); если это отверстие под болт или винт, возьмите значение из ряда",
                    pg, bb, S_11284)
            break


def check_center_holes(drw: Drawing) -> None:
    """U07: центровые отверстия упомянуты без формы и размера по ГОСТ 14034."""
    for t, pg, bb in texts(drw):
        if re.search(r"центров\w*\s+отв|центр\.\s*отв|центровк", t, re.I):
            if not re.search(r"(?<![А-Яа-яA-Za-z])[ABTCERFHPАВСЕ]\s?\d(?:[.,]\d+)?|14034|ГОСТ", t):
                drw.add(INFO, "U07", CAT_EL, f"«{t.strip()[:60]}»: у центровых отверстий указывают форму и размер — "
                        f"«Центровые отверстия А2,5 ГОСТ 14034-74»", pg, bb, S_14034)
                break


def check_nominal_series(drw: Drawing) -> None:
    """U08: диаметры свыше 10 мм без допуска — из ряда Ra40 ГОСТ 6636 (выключено по умолчанию)."""
    for d in drw.dims:
        if d.kind == "diameter" and d.nominal and 10 < d.nominal <= 1000 and not (d.upper_raw or d.lower_raw) \
                and not getattr(d, "fit", None) and abs(d.nominal * 10 - round(d.nominal * 10)) < 1e-6 \
                and not _in_ra40(d.nominal):
            drw.add(INFO, "U08", CAT_DIM, f"Диаметр «{d.raw}»: {fmtn(d.nominal)} мм нет в ряду Ra40 ГОСТ 6636-69 — "
                    f"по возможности возьмите нормальное значение", d.page, d.bbox, S_6636)
            break


def check_eskd3(drw: Drawing, cfg: dict) -> None:
    for fn in (check_thread_write, check_hardness_scale, check_radii_series, check_hole_for_fastener,
               check_center_holes, check_nominal_series):
        try:
            fn(drw)
        except Exception as e:
            drw.add(WARNING, "F07", CAT_FILE, f"Проверка «{fn.__name__}» не выполнена: {type(e).__name__}: {e}")
