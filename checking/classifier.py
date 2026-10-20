"""Классификатор ЕСКД: коды и названия, расшифровка кода из обозначения изделия, признаки из названий.

Данные — classifier/eskd.json.gz (собираются tools/build_classifier.py из справки .chm: Общесоюзный классификатор ЕСКД 1.79.100).
Код классификационной характеристики — шесть цифр обозначения «ЮМЛТ.741211.022»: класс (2), подкласс, группа, подгруппа, вид (по одной)."""
from __future__ import annotations

import gzip
import json
import os
import re
from functools import lru_cache

from .config import RES

DIR = os.path.join(RES, "classifier")
LEVELS = {2: "класс", 3: "подкласс", 4: "группа", 5: "подгруппа", 6: "вид"}


@lru_cache(maxsize=1)
def data() -> dict:
    try:
        with gzip.open(os.path.join(DIR, "eskd.json.gz"), "rt", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"version": "", "source": "", "codes": {}, "alphabet": {}}


def available() -> bool:
    return bool(data()["codes"])


def lookup(code: str) -> str | None:
    return data()["codes"].get(code)


def chain(code: str) -> list[tuple[str, str]]:
    """[(код, название)] от класса до вида; пропущенные в классификаторе уровни не показываются."""
    out = []
    for n in (2, 3, 4, 5, 6):
        c = code[:n]
        if len(c) == n and c in data()["codes"]:
            out.append((c, data()["codes"][c]))
    return out


def full_name(code: str) -> str:
    return " › ".join(n for _, n in chain(code))


def children(prefix: str = "") -> list[dict]:
    """Следующий уровень под prefix (пусто — классы): [{code, name, level, has_children}]."""
    n = 2 if not prefix else len(prefix) + 1
    if n > 6:
        return []
    codes = data()["codes"]
    out = []
    for c in sorted(k for k in codes if len(k) == n and k.startswith(prefix)):
        out.append({"code": c, "name": codes[c], "level": LEVELS[n], "has_children": n < 6 and any(len(k) == n + 1 and k.startswith(c) for k in codes)})
    return out


def search(q: str, limit: int = 60) -> list[dict]:
    """Поиск по коду (начало) или по слову в названии; затем по алфавитному указателю деталей."""
    q = (q or "").strip().lower()
    if len(q) < 2:
        return []
    codes = data()["codes"]
    out = []
    if q.isdigit():
        for c in sorted(codes):
            if c.startswith(q):
                out.append({"code": c, "name": codes[c], "path": full_name(c)})
                if len(out) >= limit:
                    break
        return out
    words = q.split()
    for c in sorted(codes):
        if all(w in codes[c].lower() for w in words):
            out.append({"code": c, "name": codes[c], "path": full_name(c)})
            if len(out) >= limit:
                return out
    for name, cs in data()["alphabet"].items():
        if all(w in name.lower() for w in words):
            for c in cs:
                if len(out) < limit and not any(o["code"] == c for o in out):
                    out.append({"code": c, "name": codes.get(c, ""), "path": full_name(c), "index": name})
    return out


# ---- признаки изделия, которые видны в названиях классификатора -------------------------------------------------------
_RX = {
    "holes": re.compile(r"(?<![\w.])(без|с)\s+отв\b"),
    "central_hole": re.compile(r"(?<![\w.])(без|с)\s+центр\.?\s"),
    "thread": re.compile(r"(?<![\w.])(без|с)\s+(?:\w+\s+)?резьб"),
    "slots": re.compile(r"(?<![\w.])(без|с)\s+(?!кольцев)(?:\w+\.?\s+)?(?:паз|шлиц)"),
}


def features(code: str) -> dict:
    """Что код говорит о детали, по названиям всех уровней (глубокий уровень важнее):
    holes — отверстия вне оси или в плоской детали (True/False), central_hole — центральное отверстие, thread — резьба,
    slots — пазы и шлицы на наружной поверхности (кольцевые пазы на торцах не считаются). None — код об этом не говорит."""
    res: dict = {k: None for k in _RX}
    for _c, name in chain(code):
        low = name.lower()
        for k, rx in _RX.items():
            for m in rx.finditer(low):
                res[k] = m.group(1) == "с"
    return res
