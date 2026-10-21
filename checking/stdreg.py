"""Реестр стандартов: справочный перечень (stdcatalog) + реально загруженные PDF (norms) + ссылки из правил (catalog).
Для каждого стандарта: загружен ли PDF, сколько проверок на него ссылается, какую редакцию называют правила."""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from functools import lru_cache

from . import catalog, norms, stdclauses
from .config import DATA
from .normdata import OBSOLETE_STANDARDS
from .stdcatalog import ENTRIES, SECTION_TITLES

OTHER = "other"


_OST4 = re.compile(r"ОСТ\s*4\s*Г[ОO0]\.?\s*(\d{3}\.\d{3})", re.I)


# Справочные стандарты: общие положения и термины, в них нет требований, которые можно проверять по чертежу или техпроцессу
REFERENCE_ONLY = {("ГОСТ", "2.001"), ("ГОСТ", "2.005"), ("ГОСТ", "3.1109"), ("ГОСТ", "14.004")}


REF_PATH = os.path.join(DATA, "std_reference.json")           # выбор администратора: {"ГОСТ|2.001": true/false}


def _rk(key: tuple) -> str:
    return "|".join(key)


def load_reference() -> dict:
    try:
        with open(REF_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def set_reference(designation: str, value: bool | None) -> bool:
    """Отметка администратора «справочный стандарт» (None — вернуть значение по умолчанию). Возвращает итоговое значение."""
    key = _key(designation)
    d = load_reference()
    if value is None:
        d.pop(_rk(key), None)
    else:
        d[_rk(key)] = bool(value)
    tmp = REF_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, REF_PATH)
    return d.get(_rk(key), key in REFERENCE_ONLY)


def _key(designation: str) -> tuple:
    """Ключ без года и без признака «Р»: ('ГОСТ', '2.106') — чтобы связать редакции одного стандарта."""
    m = _OST4.search(designation or "")
    if m:                                                           # «ОСТ4 ГО.070.014» — не «ОСТ 4»: номер идёт после буквенной группы
        return "ОСТ4 ГО", m.group(1)
    d = norms.parse_designation(designation)
    if d:
        return d[0], d[2]
    return ("RAW", re.sub(r"\s+", "", designation or "").upper())


def _edition(designation: str) -> str:
    d = norms.parse_designation(designation)
    return f"{'Р' if d[1] else ''}{d[3]}" if d else ""


_STOP = {"единая", "система", "конструкторской", "документации", "общие", "правила", "требования", "основные", "ескд", "онв", "естд", "естпп"}


def _fmt(d: tuple) -> str:
    kind, nat, num, yr = d
    yy = int(yr) if yr else 0
    full = (1900 + yy if yy >= 50 else 2000 + yy) if yr else 0
    return f"{kind}{' Р' if nat else ''} {num}" + ((f"-{full % 100:02d}" if full < 2000 else f"-{full}") if yr else "")


@lru_cache(maxsize=256)
def _head_cached(path: str, mtime: float) -> tuple:
    import pymupdf
    with pymupdf.open(path) as d:
        return tuple(d[i].get_text() for i in range(min(3, len(d))))


def _head(path: str) -> tuple:
    """Текст первых трёх страниц (для сверки обозначения) без чтения всего файла."""
    import os
    return _head_cached(path, os.path.getmtime(path))


def _in_document(path: str, exp: tuple) -> bool:
    """Обозначение стандарта (вид, номер, год) встречается в тексте файла не меньше трёх раз (колонтитулы): сборник или обложка со списком."""
    try:
        flat = re.sub(r"\s+", " ", " ".join(norms.pages_text(path)))
    except Exception:
        return False
    n = 0
    for m in norms._DESIG.finditer(flat):
        d = norms.parse_designation(m.group(0))
        if d and d[0] == exp[0] and d[2] == exp[2] and d[3] == exp[3]:
            n += 1
    return n >= 3


def _other_year(cnt: Counter, exp: tuple, path: str) -> tuple | None:
    """Тот же номер, но другой год, и в тексте он встречается заметно чаще названного (файл назван по старой редакции)."""
    if not exp or not exp[3]:
        return None
    alts = [(n, d) for d, n in cnt.items() if d[:3] == exp[:3] and d[3] != exp[3]]
    if not alts:
        return None
    n, alt = max(alts)
    if n >= 2 and n >= 2 * cnt.get(exp, 0) and not _in_document(path, exp):
        return alt
    return None


def verify(path: str, designation: str, title: str = "") -> dict:
    """Сверяет файл с тем, чем он назван: обозначение, которое чаще всего встречается в тексте первых трёх страниц
    (колонтитулы повторяют обозначение стандарта), должно совпасть с ожидаемым по номеру, признаку «Р» и году;
    название из перечня должно встречаться в тексте. status: ok | bad (другой документ или другая редакция) |
    warn (название не найдено) | scan (текста нет, проверить нельзя)."""
    try:
        pages = _head(path)
    except Exception:
        return {"status": "scan", "detected": "", "note": "файл не читается"}
    flat = re.sub(r"\s+", " ", " ".join(pages))
    if len(flat) < 300:
        return {"status": "scan", "detected": "", "note": "в файле нет текста (скан): сверить обозначение нельзя"}
    mo = _OST4.search(designation or "")
    if mo:                                                           # отраслевой стандарт «ОСТ4 ГО.070.0xx»: сверяем номер по самому частому в тексте
        found = Counter(m.group(1) for m in _OST4.finditer(flat))
        if found and found.most_common(1)[0][0] != mo.group(1):
            top = found.most_common(1)[0][0]
            return {"status": "bad", "detected": f"ОСТ4 ГО.{top}",
                    "note": f"в тексте файла «ОСТ4 ГО.{top}», а он загружен как «{designation}»: проверьте, тот ли это документ"}
    cnt = Counter()
    for m in norms._DESIG.finditer(flat):
        d = norms.parse_designation(m.group(0))
        if d and d[3]:
            cnt[d] += 1
    exp = norms.parse_designation(designation)
    detected = ""
    if cnt:
        top = cnt.most_common(1)[0][0]
        detected = _fmt(top)
        alt = _other_year(cnt, exp, path)
        if alt:
            detected = _fmt(alt)
            return {"status": "bad", "detected": detected,
                    "note": f"в тексте файла «{detected}», а ожидается «{designation}»: другая редакция или год"}
        if exp and (exp in cnt or _in_document(path, exp)):   # обозначение из названия встречается в тексте: файл тот (сборники из нескольких стандартов тоже)
            pass
        elif exp and (top[0], top[2]) != (exp[0], exp[2]):
            return {"status": "bad", "detected": detected,
                    "note": f"в тексте файла «{detected}», а он загружен как «{designation}»: проверьте, тот ли это документ"}
        elif exp and exp[3] and (top[1], top[3]) != (exp[1], exp[3]):
            return {"status": "bad", "detected": detected,
                    "note": f"в тексте файла «{detected}», а ожидается «{designation}»: другая редакция или год"}
    title = re.sub(r"\([^)]*\)", " ", title or "")                   # пометки вроде «(прежняя редакция)» — не часть названия
    words = [w for w in re.findall(r"[а-яё]{5,}", title.lower()) if w not in _STOP]
    if words:
        low = flat.lower().replace("ё", "е")
        hit = sum(1 for w in words if w.replace("ё", "е")[:max(5, len(w) - 2)] in low)
        if hit / len(words) < 0.4:
            return {"status": "warn", "detected": detected,
                    "note": f"название «{title}» в начале файла не найдено: проверьте, тот ли это документ"}
    return {"status": "ok", "detected": detected, "note": ""}


def reconcile(path: str, designation: str) -> tuple[str, str]:
    """Обозначение по содержимому файла: (обозначение, причина). Если в тексте то же число и год, но с «Р» (файл назван без неё),
    или файл на самом деле другой стандарт (в тексте повторяется другое обозначение, а названное не встречается),
    возвращается обозначение из текста. Иначе — прежнее и пустая причина."""
    try:
        flat = re.sub(r"\s+", " ", " ".join(_head(path)))
    except Exception:
        return designation, ""
    cnt = Counter()
    for m in norms._DESIG.finditer(flat):
        d = norms.parse_designation(m.group(0))
        if d and d[3]:
            cnt[d] += 1
    exp = norms.parse_designation(designation)
    alt = _other_year(cnt, exp, path)
    if alt:
        return _fmt(alt), f"в тексте файла «{_fmt(alt)}» (другой год), а не «{designation}»"
    if cnt and exp and exp not in cnt:
        for d in cnt:
            if d[0] == exp[0] and d[2:] == exp[2:] and d[1] != exp[1] and cnt[d] >= 2:   # «Р» есть только в тексте или только в названии
                return _fmt(d), "в тексте файла обозначение " + ("с «Р»" if d[1] else "без «Р»")
    if not cnt or not exp or exp in cnt or _in_document(path, exp):
        return designation, ""
    top, n = cnt.most_common(1)[0]
    if (top[0], top[2], top[3]) == (exp[0], exp[2], exp[3]):
        return _fmt(top), "в тексте файла обозначение с «Р»"
    if n >= 2 and (top[0], top[2]) != (exp[0], exp[2]) and exp[:3] not in {c[:3] for c in cnt}:
        return _fmt(top), f"в тексте файла «{_fmt(top)}», а не «{designation}»"
    return designation, ""


def fix_designations() -> list[dict]:
    """Приводит обозначения загруженных файлов к тем, что стоят в тексте (см. reconcile). Возвращает список изменений."""
    out = []
    for it in norms.listing():
        new, why = reconcile(it["path"], it["designation"])
        if why and new != it["designation"] and it["source"] == "user":
            norms.update(it["id"], it["title"], new)
            out.append({"file": it["id"], "was": it["designation"], "now": new, "why": why})
    return out


def _year(designation: str) -> int:
    d = norms.parse_designation(designation)
    if not d or not d[3]:
        return 0
    yy = int(d[3])
    return 1900 + yy if yy >= 50 else 2000 + yy


def _replaced_by(designation: str) -> str:
    """Чем заменён стандарт (по таблице заменённых стандартов программы), если заменён."""
    d = re.sub(r"\s+", " ", designation).strip().lower()
    for old, new in OBSOLETE_STANDARDS:
        if old.lower() == d:
            return new
    return ""


def build(cfg: dict) -> dict:
    reference = load_reference()
    files: dict[tuple, list[dict]] = {}
    for it in norms.listing():
        k = _key(it["designation"] if norms.parse_designation(it["designation"]) else it["id"])
        files.setdefault(k, []).append(it)
    rules: dict[tuple, dict] = {}
    for e in catalog.standards_index(cfg):
        k = _key(e["label"])
        r = rules.setdefault(k, {"direct": {}, "related": set(), "cited": []})
        for d in e["direct"]:
            r["direct"].setdefault(d["code"], []).extend(c for c in d["clauses"] if c not in r["direct"][d["code"]])
        r["related"].update(e["related"])
        if e["label"] not in r["cited"]:
            r["cited"].append(e["label"])

    open_marks = Counter(m["file_id"] for m in stdclauses.load_marks() if m["status"] == "open")
    rows, used = [], set()
    editions: dict[tuple, list[str]] = {}          # стандарты с несколькими редакциями в перечне (например, ГОСТ 2.102-2013 и ГОСТ Р 2.102-2023)
    for e in ENTRIES:
        editions.setdefault(_key(e["designation"]), []).append(e["designation"])

    def row(designation, title, section, force=None):
        k = _key(designation)
        used.add(k)
        fl = files.get(k, [])
        f = None
        was = ""
        multi = len(editions.get(k, [])) > 1
        newest = not multi or designation == max(editions[k], key=_year)
        if multi:                                   # каждой редакции — свой файл, без подмены более новой
            fl = [x for x in fl if _edition(x["designation"]) == _edition(designation)]
        if force:                                   # файл другой редакции того же стандарта — отдельная строка
            fl, multi, newest = [force], True, False
        if fl:       # лучший файл: та же редакция, иначе самая новая из загруженных
            f = max(fl, key=lambda x: ((_edition(x["designation"]) == _edition(designation)) if multi else 0, _year(x["designation"]), x["source"] == "user"))
            if not multi and _year(f["designation"]) > _year(designation) > 0:      # загружена редакция новее, чем в перечне: она и считается действующей
                was, designation = designation, f["designation"]
        r = rules.get(k) if newest else None        # ссылки правил относим к самой новой редакции
        cited = [c for c in (r["cited"] if r else []) if _edition(c) != _edition(designation)]
        return {
            "designation": designation, "title": title, "section": section,
            "file": ({"id": f["id"], "designation": f["designation"], "pages": f["pages"], "size": f["size"], "has_text": f["has_text"],
                      "source": f["source"], "same_edition": _edition(f["designation"]) == _edition(designation),
                      "check": verify(f["path"], f["designation"], title)} if f else None),
            "rules": len(r["direct"]) if r else 0,
            "codes": sorted(r["direct"]) if r else [],
            "related": len(r["related"] - set(r["direct"])) if r else 0,
            "reference": reference.get(_rk(_key(designation)), _key(designation) in REFERENCE_ONLY),
            "marks_open": open_marks.get(f["id"], 0) if f else 0, "cited_other": cited, "replaced_by": _replaced_by(was or designation), "catalog_was": was,
        }

    for e in ENTRIES:
        rows.append(row(e["designation"], e["title"], e["section"]))
    # стандарты, на которые ссылаются правила или которые загружены, но которых нет в перечне
    for k, r in rules.items():
        if k not in used:
            lab = max(r["cited"], key=len)
            rows.append(row(lab, "", OTHER))
    for k, fl in files.items():
        if k not in used:
            rows.append(row(fl[0]["designation"], fl[0]["title"], OTHER))
    shown = {r["file"]["id"] for r in rows if r["file"]}
    sec_of = {_key(r["designation"]): r["section"] for r in rows}
    for it in norms.listing():                      # загруженные файлы, не попавшие в строки (другие редакции, дубли): отдельными строками
        if it["id"] not in shown:
            k = _key(it["designation"] if norms.parse_designation(it["designation"]) else it["id"])
            rows.append(row(it["designation"], it["title"], sec_of.get(k, OTHER), force=it))
            shown.add(it["id"])
    sections = [{"key": key, "title": t} for key, t in SECTION_TITLES.items()] + [{"key": OTHER, "title": "Прочие (из правил или загруженные, нет в перечне)"}]
    summary = {
        "total": len(rows), "loaded": sum(1 for r in rows if r["file"]),
        "needed_missing": sum(1 for r in rows if r["rules"] and not r["file"]),
        "edition_mismatch": sum(1 for r in rows if r["file"] and not r["file"]["same_edition"]),
        "no_checks": sum(1 for r in rows if r["file"] and not r["rules"] and not r["reference"]),
        "marks_open": sum(open_marks.values()),
        "check_failed": sum(1 for r in rows if r["file"] and r["file"]["check"]["status"] in ("bad", "warn")),
        "stale_refs": sum(1 for r in rows if r["cited_other"]),
    }
    return {"sections": sections, "rows": rows, "summary": summary}


def detect_designation(filename: str, first_page: str = "") -> str:
    """Обозначение стандарта по имени файла, иначе по тексту первой страницы; пусто, если не найдено."""
    for src in (filename, first_page[:1500]):
        d = norms.parse_designation(src or "")
        if d:
            kind, nat, num, yr = d
            year = ""
            m = re.search(r"[-—–]\s*(\d{4}|\d{2})\b", src[src.upper().find(num):] if num in src else "")
            if m:
                year = m.group(1)
            return f"{kind}{' Р' if nat else ''} {num}" + (f"-{year}" if year else "")
    return ""
