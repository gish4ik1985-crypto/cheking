"""Разбор записи материала: сортамент, типоразмер, марка (ГОСТ 2.109 — графа 3)."""
from __future__ import annotations

import re

from .textnorm import LAT_TO_CYR, to_float

SORTAMENTS = ["Лист", "Полоса", "Круг", "Пруток", "Квадрат", "Шестигранник", "Труба", "Профиль", "Уголок",
              "Швеллер", "Двутавр", "Лента", "Проволока", "Шпилька", "Плита"]
STD = re.compile(r"(?:ГОСТ\s?Р?|ОСТ|ТУ|DIN|EN|ISO|СТО)\s*[\dA-Za-zА-Яа-я.\-–]*\d[\d.\-–]*", re.I)
STRONG_GRADE = re.compile(
    r"(?<!\w)(Ст\s?\d(?:кп|пс|сп)\d?|\d{1,2}Х\d{1,2}Н\d{1,2}[А-Я0-9]*|\d{2}[ХГСНМТФЮРДАБ][А-Я0-9]*|"
    r"AISI\s?\d{3}[A-Z]?|C\d{2}E?\b|S\d{3}[A-Z0-9+]*|E\d{3}(?:\+[A-Z]+)?|Д16Т?|АМг\d+М?|АД31Т?\d?|"
    r"Л\d{2}\b|ЛС\d{2}-\d|65Г|У\d{1,2}А?)")
PLAIN_GRADE = re.compile(r"(?<![\d.,×х])\b(\d{2})\b(?![\d.,×х])")


def norm_grade(g: str | None) -> str:
    if not g:
        return ""
    return re.sub(r"\s+", "", g).upper().translate(LAT_TO_CYR)


def parse_material(text: str) -> dict:
    raw = (text or "").strip()
    out = {"raw": raw, "sortament": None, "size": None, "sizes": [], "grade": None}
    if not raw:
        return out
    parts = [p.strip() for p in re.split(r"\s/\s|/(?=\s*[А-ЯA-Z0-9])", raw) if p.strip()]
    first = parts[0]
    sort_part, grade_part = None, None
    for s in SORTAMENTS:
        if re.match(rf"(?i){s}\b", first):
            out["sortament"] = s
            sort_part = first
            grade_part = " ".join(parts[1:]) if len(parts) > 1 else None
            break
    if out["sortament"] is None:
        grade_part = raw
    if sort_part:
        body = STD.sub(" ", sort_part[len(out["sortament"]):])
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*[×хxX]\s*\d{3,}", body)        # 16х1500х6000, 42х6000
        nums = [to_float(x) for x in re.findall(r"(?<![A-Za-zА-Яа-я\d.,])(\d+(?:[.,]\d+)?)", body)]
        nums = [n for n in nums if n is not None]
        out["sizes"] = nums
        if m:
            out["size"] = to_float(m.group(1))
        elif nums:
            out["size"] = nums[0]
    if grade_part:
        g = STD.sub(" ", grade_part)
        g = re.sub(r"(?i)\bсталь\b", " ", g)
        m = STRONG_GRADE.search(g)
        if m:
            out["grade"] = m.group(1)
        else:
            m = PLAIN_GRADE.search(g)
            if m:
                out["grade"] = m.group(1)
    return out
