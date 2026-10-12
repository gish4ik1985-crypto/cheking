"""Разбор текста размерной надписи: номинал, поле допуска, посадка, отклонения, резьба, фаска."""
from __future__ import annotations

import re

from .textnorm import normalize_dim, to_float, CYR_TO_LAT

NUM = r"\d+(?:[.,]\d+)?"
DEV = r"[+\-]\s?" + NUM + r"|0"
FIELD = r"[A-Za-zА-Яа-я]{1,2}\d{1,2}"

COUNT_HEAD = re.compile(r"^(?P<n>\d+)\s*(?:отв\.?|фаск[иа]?|паз(?:а|ов)?|шт\.?)\s*", re.I)
COUNT_TAIL = re.compile(r"\s*(?P<n>\d+)\s*(?:отв\.?|фаск[иа]?|паз(?:а|ов)?|шт\.?)$", re.I)
COUNT_ONLY = re.compile(r"^(?P<n>\d+)\s*(?:отв\.?|фаск[иа]?|паз(?:а|ов)?)$", re.I)
CHAMFER = re.compile(rf"^(?P<leg>{NUM})\s*×\s*(?P<ang>\d+)\s*°$")
ANGLE = re.compile(rf"^(?P<deg>{NUM})\s*°(?:\s*\d+\s*['′])?(?:\s*±\s*\d+\s*['′°])?$")
TOL_CH = r"[A-Za-zЕНеGgh]"
THREAD = re.compile(
    rf"^(?P<m>[MМ])\s*(?P<d>{NUM})(?:\s*×\s*(?P<p>{NUM}))?(?:\s*LH)?"
    rf"(?:\s*-\s*(?P<tol>\d{TOL_CH}(?:\d{TOL_CH})?))?$")
TRAP = re.compile(rf"^Tr\s*(?P<d>{NUM})\s*×\s*(?P<p>{NUM})(?:\s*\(\s*P\s*(?P<p2>{NUM})\s*\))?(?:\s*LH)?"
                  rf"(?:\s*-\s*(?P<tol>\d{TOL_CH}(?:\d?{TOL_CH})?))?$")
PIPE = re.compile(r"^G\s*(?P<size>\d+\s+\d/\d+|\d/\d+|\d+)(?:\s*-\s*(?P<cls>[ABАВ]))?(?:\s*-?\s*LH)?$")
OTHER_THREAD = re.compile(rf"^(?:Tr|G|Rc|Rp|K|Пг)\s*{NUM}", re.I)
GENERAL = re.compile(rf"^(?P<prefix>S⌀|SR|⌀|R|□|s|S)?\s*(?P<nom>{NUM})(?P<rest>.*)$")
FIT_PART = re.compile(rf"^\s*(?P<f1>{FIELD})(?:\s*/\s*(?P<f2>{FIELD}))?")
PM_PART = re.compile(rf"^\s*\(?\s*±\s*(?P<v>{NUM})\s*\)?")
DEVS_PART = re.compile(rf"^\s*\(?\s*(?P<a>{DEV})(?:\s*/?\s*(?P<b>{DEV}))?\s*\)?")
DEV_ONLY = re.compile(rf"^\(?\s*(?P<v>(?:[+\-±]\s?)?{NUM})\s*\)?$")
FIELD_ONLY = re.compile(rf"^\(?\s*(?P<f>{FIELD})\s*\)?$")

PREFIX_KIND = {"⌀": "diameter", "R": "radius", "SR": "sphere", "S⌀": "sphere", "□": "square",
               "s": "thickness", "S": "thickness"}


def _field_norm(code: str) -> tuple[str, bool]:
    """Латинизирует кириллические двойники в обозначении поля; возвращает (код, была_кириллица)."""
    lat = code.translate(CYR_TO_LAT)
    return lat, lat != code


def parse_dev(text: str) -> tuple[float | None, str | None, bool]:
    """Отдельная строка с отклонением: (значение, исходная строка, симметричное ±)."""
    s = normalize_dim(text)
    m = DEV_ONLY.match(s)
    if not m:
        return None, None, False
    v = m.group("v").replace(" ", "")
    if v.startswith("±"):
        return to_float(v[1:]), v, True
    return to_float(v), v, False


def is_field_only(text: str) -> str | None:
    m = FIELD_ONLY.match(normalize_dim(text))
    if not m or m.group("f").upper().startswith("IT"):      # «IT14» — квалитет в ТТ, не поле допуска
        return None
    return m.group("f")


def is_count_only(text: str) -> int | None:
    m = COUNT_ONLY.match(normalize_dim(text))
    return int(m.group("n")) if m else None


def parse_dimension(text: str) -> dict | None:
    """Возвращает словарь полей Dimension или None, если строка — не размер."""
    raw = normalize_dim(text)
    s = raw
    if not s or re.match(r"^(Ra|Rz|Rmax|п\.|поз)", s, re.I):
        return None
    out: dict = {"raw": raw, "decimal_point": False, "cyrillic_in_field": False}

    m = COUNT_HEAD.match(s)
    if m:
        out["count"] = int(m.group("n"))
        s = s[m.end():]
    m = COUNT_TAIL.search(s)
    if m:
        out["count"] = int(m.group("n"))
        s = s[:m.start()]
    s = s.strip()
    ref = re.search(r"(\*{1,2})\s*$", s)
    if ref:
        out["reference"] = ref.group(1)
        s = s[:ref.start()].strip()
    if not s or not re.search(r"\d", s):
        return None
    if re.search(r"\d\.\d", s):
        out["decimal_point"] = True

    m = CHAMFER.match(s)
    if m:
        out.update(kind="chamfer", nominal=to_float(m.group("leg")), angle=to_float(m.group("ang")))
        return out
    m = ANGLE.match(s)
    if m:
        out.update(kind="angle", nominal=to_float(m.group("deg")))
        return out
    m = THREAD.match(s)
    if m:
        tol, cyr = _field_norm(m.group("tol")) if m.group("tol") else (None, False)
        out.update(kind="thread", nominal=to_float(m.group("d")), pitch=to_float(m.group("p")), thread_tol=tol)
        out["cyrillic_in_field"] = m.group("m") == "М" or cyr
        return out
    m = TRAP.match(s)
    if m:
        tol, cyr = _field_norm(m.group("tol")) if m.group("tol") else (None, False)
        out.update(kind="thread_tr", nominal=to_float(m.group("d")),
                   pitch=to_float(m.group("p2") or m.group("p")), thread_tol=tol, cyrillic_in_field=cyr)
        return out
    m = PIPE.match(s)
    if m:
        cls = (m.group("cls") or "").translate(CYR_TO_LAT) or None
        out.update(kind="thread_g", nominal=None, thread_tol=cls, pitch=None)
        out["g_size"] = re.sub(r"\s+", " ", m.group("size"))
        return out
    if OTHER_THREAD.match(s):
        out.update(kind="thread_other", nominal=None)
        return out

    m = GENERAL.match(s)
    if not m:
        return None
    prefix = m.group("prefix") or ""
    nom_s = m.group("nom")
    # «01.2025», «301321.001» и т.п. — не размеры
    if re.match(r"0\d", nom_s) or len(re.split(r"[.,]", nom_s + ".")[1]) > 3 or len(nom_s.split(",")[0].split(".")[0]) > 5:
        return None
    nominal = to_float(nom_s)
    rest = m.group("rest")
    out.update(kind=PREFIX_KIND.get(prefix, "linear"), nominal=nominal)
    if nominal is None or nominal <= 0:
        return None

    fm = FIT_PART.match(rest)
    if fm and fm.group("f1").upper().startswith("IT"):
        return None
    if fm:
        f1, cyr1 = _field_norm(fm.group("f1"))
        if fm.group("f2"):
            f2, cyr2 = _field_norm(fm.group("f2"))
            out.update(fit_hole=f1, fit_shaft=f2)
            out["cyrillic_in_field"] = cyr1 or cyr2
        else:
            out["field"] = f1
            out["cyrillic_in_field"] = cyr1
        rest = rest[fm.end():]

    pm = PM_PART.match(rest)
    if pm:
        v = to_float(pm.group("v"))
        out.update(upper=v, lower=-v if v is not None else None, symmetric=True,
                   upper_raw="±" + pm.group("v"), lower_raw="±" + pm.group("v"))
        rest = rest[pm.end():]
    else:
        dm = DEVS_PART.match(rest)
        if dm and dm.group(0).strip():
            a, b = dm.group("a"), dm.group("b")
            va, vb = to_float(a), to_float(b)
            if b is None:
                if a.strip() == "0":
                    return None
                if va is not None and va >= 0:
                    out.update(upper=va, lower=0.0, upper_raw=a.replace(" ", ""))
                else:
                    out.update(upper=0.0, lower=va, lower_raw=a.replace(" ", ""))
            else:
                out.update(upper=va, lower=vb, upper_raw=a.replace(" ", ""), lower_raw=b.replace(" ", ""))
            rest = rest[dm.end():]
    if rest.strip():
        return None
    # отсечь ложные срабатывания: «3-2025», даты и т.п.
    for key in ("upper", "lower"):
        v = out.get(key)
        if v is not None and abs(v) > max(10.0, nominal * 0.5):
            return None
    return out
