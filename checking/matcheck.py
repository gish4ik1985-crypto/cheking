"""Запись материала в графе 3 (ГОСТ 2.109-73): вид сортамента, стандарт на сортамент и на марку."""
from __future__ import annotations

import re

from .material import norm_grade
from .model import Drawing, WARNING, CAT_TB
from .normdata import GRADE_FAMILIES, GRADE_MAIN_STANDARDS, SORTAMENT_BY_STANDARD, SORTAMENT_STANDARDS

STD_NUM = re.compile(r"ГОСТ\s*Р?\s*(\d{2,5})(?![\d.])")


def _family(grade: str):
    g = norm_grade(grade)
    for name, pat, main, allowed in GRADE_FAMILIES:
        if re.search(pat, g):
            return name, main, allowed
    return None


def check_material(drw: Drawing, cfg: dict) -> None:
    if drw.facts.get("is_assembly"):
        return
    raw = (drw.title.material or "").strip()
    if not raw:
        return
    pg, bb = drw.first_page, drw.title.bboxes.get("material")
    mat = drw.facts.get("material") or {}
    parts = [p.strip() for p in re.split(r"\s/\s|/(?=\s*[А-ЯA-Z0-9])", raw) if p.strip()]
    num_part = parts[0]
    grade_part = parts[1] if len(parts) > 1 else raw
    num_stds = STD_NUM.findall(num_part)
    sort = mat.get("sortament")

    # вид сортамента не указан, хотя стандарт на сортамент есть
    if not sort and len(parts) > 1:
        words = set()
        for s in num_stds:
            words |= SORTAMENT_BY_STANDARD.get(s, set())
        if words:
            w = "Круг" if {"Круг", "Пруток"} <= words else " / ".join(sorted(words))
            drw.add(WARNING, "M01", CAT_TB, f"В графе 3 «{raw}» по ГОСТ {num_stds[0]} не указан вид сортамента — "
                    f"«{w} …»", pg, bb, "ГОСТ 2.109-73")
    # стандарт на сортамент не того вида
    if sort in SORTAMENT_STANDARDS:
        for s in num_stds:
            other = SORTAMENT_BY_STANDARD.get(s)
            if other and sort not in other:
                drw.add(WARNING, "M03", CAT_TB, f"«{sort}» по ГОСТ {s}: этот стандарт — на "
                        f"{', '.join(sorted(other)).lower()}, а не на {sort.lower()}", pg, bb, "ГОСТ 2.109-73")
    # стандарт на марку
    grade = mat.get("grade")
    fam = _family(grade) if grade else None
    if fam:
        name, main, allowed = fam
        for s in STD_NUM.findall(grade_part):
            if s in GRADE_MAIN_STANDARDS and s not in allowed:
                drw.add(WARNING, "M02", CAT_TB, f"Марка {grade} ({name} сталь/сплав) указана по ГОСТ {s}; марки этой "
                        f"группы — по ГОСТ {main}", pg, bb, "ГОСТ 2.109-73")
