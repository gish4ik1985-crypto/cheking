"""Правила проверки чертежа. Каждое замечание ссылается на стандарт и, где возможно, на место на листе."""
from __future__ import annotations

import math
import re

from . import tolerances as T
from .material import parse_material, norm_grade
from .model import (Drawing, Dimension, ERROR, WARNING, INFO,
                    CAT_DIM, CAT_TECH, CAT_TT, CAT_TB, CAT_ERP, CAT_FILE)
from .normdata import RA_SERIES as RA_GOST, RZ_SERIES, RA_PREFERRED, RZ_PREFERRED, clearance_for
from .standards import (check_metric_thread, THREAD_TOL_RE, FILLET_SERIES, in_ra40, RA_FOR_IT,
                        density_for, METRIC_THREADS, fmtn)
from .textnorm import norm_designation, norm_words, ref_key

STD_DIM = "ГОСТ 2.307-2011"
STD_TOL = "ГОСТ 25346-2013"
STD_FIT = "ГОСТ 25347-2013"

FORMATS = {"A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297)}
SCALES = {"1:1", "1:2", "1:2,5", "1:4", "1:5", "1:10", "1:15", "1:20", "1:25", "1:40", "1:50", "1:75",
          "1:100", "1:200", "1:400", "1:500", "1:800", "1:1000", "2:1", "2,5:1", "4:1", "5:1", "10:1",
          "20:1", "40:1", "50:1", "100:1"}
DESIG_RE = r"(?P<org>[А-ЯA-Z]{4})\.(?P<cls>\d{6})\.(?P<num>\d{3})(?:-(?P<isp>\d{2,3}))?(?:\s?(?P<doc>[А-Я]{1,3}\d?))?"


def _decimals(raw: str | None) -> int:
    if not raw:
        return 0
    m = re.search(r"[.,](\d+)", raw)
    return len(m.group(1)) if m else 0


def _lbl(d: Dimension) -> str:
    return f"«{d.raw.strip()}»"


def _fmt_lim(up, lo) -> str:
    return f"{T.fmt(up, sign=True)} / {T.fmt(lo, sign=True)}"


# ------------------------------------------------------------- размеры -----
def check_dimensions(drw: Drawing, cfg: dict) -> None:
    limits_info = []
    for d in drw.dims:
        pg, bb = d.page, d.bbox
        nom = d.nominal

        if d.decimal_point:
            drw.add(WARNING, "D07", CAT_DIM, f"В размере {_lbl(d)} дробная часть отделена точкой — по ЕСКД "
                    f"используют запятую", pg, bb, STD_DIM)
        if d.cyrillic_in_field:
            drw.add(INFO, "D16", CAT_DIM, f"В обозначении {_lbl(d)} использованы русские буквы вместо "
                    f"латинских (М/Н/К…) — для ЧПУ и поиска это разные символы", pg, bb, STD_TOL)
        if d.reference and d.has_tolerance:
            drw.add(ERROR, "D08", CAT_DIM, f"Справочный размер {_lbl(d)} указан с предельными отклонениями — "
                    f"у справочных размеров отклонения не указывают", pg, bb, STD_DIM)

        if d.kind == "thread" and nom:
            ok, msg = check_metric_thread(nom, d.pitch)
            if not ok:
                drw.add(ERROR, "D15", CAT_DIM, f"Резьба {_lbl(d)}: {msg}", pg, bb, "ГОСТ 8724-2002")
            elif msg:
                drw.add(INFO, "D26", CAT_DIM, f"Резьба {_lbl(d)}: {msg}", pg, bb, "ГОСТ 8724-2002")
            if d.thread_tol and not THREAD_TOL_RE.match(d.thread_tol):
                drw.add(WARNING, "D27", CAT_DIM, f"Резьба {_lbl(d)}: поле допуска «{d.thread_tol}» не по ГОСТ 16093 "
                        f"(наружная — 6g, 6h, 8g…; внутренняя — 6H, 7H, 6G…)", pg, bb, "ГОСТ 16093-2004")
            continue
        if d.kind == "chamfer":
            if nom and not any(abs(nom - x) < 1e-6 for x in FILLET_SERIES):
                drw.add(INFO, "D17", CAT_DIM, f"Фаска {_lbl(d)}: катет {fmtn(nom)} не из ряда ГОСТ 10948-64",
                        pg, bb, "ГОСТ 10948-64")
            continue
        if d.kind in ("angle", "thread_other") or not nom:
            continue
        if (d.kind == "radius" and nom <= 10 and not d.reference
                and not any(abs(nom - x) < 1e-6 for x in FILLET_SERIES)):
            drw.add(INFO, "D29", CAT_DIM, f"Радиус {_lbl(d)} не из ряда ГОСТ 10948-64 "
                    f"(…{', '.join(fmtn(x) for x in FILLET_SERIES if 0.5 * nom <= x <= 2 * nom)}…)",
                    pg, bb, "ГОСТ 10948-64")

        computed = None
        # --- поле допуска размера (⌀20H7)
        if d.field:
            try:
                f = T.parse_field(d.field)
                if not T.in_standard_series(d.field):
                    drw.add(WARNING, "D02", CAT_DIM, f"Поле допуска {d.field} в размере {_lbl(d)} не входит в ряды "
                            f"ГОСТ 25347 (ISO 286-2) — проверьте квалитет", pg, bb, STD_FIT)
                computed = T.limits(nom, d.field)
                limits_info.append((d, d.field, computed))
                if d.upper is not None or d.lower is not None:
                    up = d.upper if d.upper is not None else 0.0
                    lo = d.lower if d.lower is not None else 0.0
                    tol = 0.0006 if f.letter.lower() == "js" else 0.0002
                    if abs(up - computed[0]) > tol or abs(lo - computed[1]) > tol:
                        dec = max(_decimals(d.upper_raw), _decimals(d.lower_raw), 1)
                        rounded = (round(computed[0], dec), round(computed[1], dec))
                        if abs(up - rounded[0]) < 1e-9 and abs(lo - rounded[1]) < 1e-9:
                            drw.add(WARNING, "D03", CAT_DIM,
                                    f"Размер {_lbl(d)}: отклонения поля {d.field} округлены до {dec} знак(ов). По ГОСТ "
                                    f"25346 для {fmtn(nom)}{d.field}: {_fmt_lim(*computed)} — на чертеже получился "
                                    f"другой допуск. Увеличьте точность отображения допусков в САПР до 3 знаков",
                                    pg, bb, STD_TOL)
                        else:
                            drw.add(ERROR, "D03", CAT_DIM,
                                    f"Размер {_lbl(d)}: отклонения не соответствуют полю {d.field}. "
                                    f"Для {fmtn(nom)}{d.field} по ГОСТ 25346: {_fmt_lim(*computed)}, "
                                    f"на чертеже: {_fmt_lim(up, lo)}", pg, bb, STD_TOL)
                if f.grade <= cfg.get("tight_it", 5):
                    drw.add(WARNING, "T02", CAT_TECH, f"Размер {_lbl(d)}: квалитет IT{f.grade} — требует доводки/"
                            f"шлифования и измерения специнструментом; убедитесь, что точность действительно нужна",
                            pg, bb, STD_TOL)
            except T.ToleranceError as e:
                drw.add(ERROR, "D01", CAT_DIM, f"Размер {_lbl(d)}: {e}", pg, bb, STD_TOL)

        # --- посадка (H7/g6)
        if d.fit_hole and d.fit_shaft:
            try:
                fh, fs = T.parse_field(d.fit_hole), T.parse_field(d.fit_shaft)
                if not fh.is_hole or fs.is_hole:
                    if fs.is_hole and not fh.is_hole:
                        msg = (f"Посадка {_lbl(d)}: в числителе должно быть поле отверстия (прописная буква), "
                               f"в знаменателе — вала (строчная). Вероятно, имелось в виду "
                               f"{d.fit_shaft}/{d.fit_hole}")
                    else:
                        msg = f"Посадка {_lbl(d)}: оба поля — {'отверстия' if fh.is_hole else 'вала'}"
                    drw.add(ERROR, "D13", CAT_DIM, msg, pg, bb, STD_FIT)
                else:
                    fi = T.fit_info(nom, d.fit_hole, d.fit_shaft)
                    limits_info.append((d, f"{d.fit_hole}/{d.fit_shaft}", fi))
                    code = f"{d.fit_hole}/{d.fit_shaft}"
                    drw.add(INFO, "D18", CAT_DIM,
                            f"Посадка ⌀{fmtn(nom)} {code} — {fi.kind}: отверстие {_fmt_lim(*fi.hole_limits)}, вал "
                            f"{_fmt_lim(*fi.shaft_limits)}; S/N max {T.fmt(fi.smax)}, S/N min {T.fmt(fi.smin)} мм",
                            pg, bb, STD_FIT)
                    if fh.letter != "H" and fs.letter != "h":
                        drw.add(INFO, "D12", CAT_DIM, f"Посадка {code} — комбинированная (ни в системе отверстия H, "
                                f"ни в системе вала h)", pg, bb, STD_FIT)
                    elif code not in T.PREFERRED_FITS:
                        drw.add(INFO, "D30", CAT_DIM, f"Посадка {code} не из рекомендуемых ГОСТ 25347 — "
                                f"проверьте, нет ли подходящей предпочтительной", pg, bb, STD_FIT)
                    if fh.grade < fs.grade and fs.grade <= 8:
                        drw.add(WARNING, "D28", CAT_DIM, f"Посадка {code}: отверстие точнее вала — обычно квалитет "
                                f"отверстия на 1 грубее (H7/g6), отверстие обработать точнее труднее",
                                pg, bb, STD_FIT)
                    for ff in (fh, fs):
                        if not T.in_standard_series(ff.code):
                            drw.add(WARNING, "D02", CAT_DIM, f"Поле {ff.code} в посадке {code} не входит в ряды "
                                    f"ГОСТ 25347", pg, bb, STD_FIT)
            except T.ToleranceError as e:
                drw.add(ERROR, "D01", CAT_DIM, f"Посадка {_lbl(d)}: {e}", pg, bb, STD_FIT)

        # --- числовые отклонения без поля
        if not d.field and (d.upper is not None or d.lower is not None):
            up = d.upper if d.upper is not None else 0.0
            lo = d.lower if d.lower is not None else 0.0
            if up < lo:
                drw.add(ERROR, "D04", CAT_DIM, f"Размер {_lbl(d)}: верхнее отклонение ({T.fmt(up, True)}) меньше "
                        f"нижнего ({T.fmt(lo, True)}) — перепутаны местами", pg, bb, STD_DIM)
            elif up == lo:
                drw.add(ERROR, "D04", CAT_DIM, f"Размер {_lbl(d)}: верхнее и нижнее отклонения равны — "
                        f"нулевой допуск", pg, bb, STD_DIM)
            if not d.symmetric and up > lo and not d.reference and abs(up + lo) < 1e-9:
                drw.add(WARNING, "D05", CAT_DIM, f"Размер {_lbl(d)}: равные по модулю отклонения указывают "
                        f"одним числом со знаком ± ({fmtn(nom)}±{fmtn(up)})", pg, bb, STD_DIM)
            if (d.upper_raw and d.lower_raw and not d.symmetric and up != 0 and lo != 0
                    and _decimals(d.upper_raw) != _decimals(d.lower_raw)):
                drw.add(WARNING, "D06", CAT_DIM, f"Размер {_lbl(d)}: разное число знаков после запятой в верхнем и "
                        f"нижнем отклонениях — их выравнивают (например, +0,10 / −0,05)", pg, bb, STD_DIM)
            tol = up - lo
            if tol > 0:
                g = T.equivalent_grade(nom, tol)
                if g is not None and g <= cfg.get("tight_it", 5):
                    grade_txt = f"≈IT{g}" if g else "точнее IT1"
                    drw.add(WARNING, "T02", CAT_TECH, f"Размер {_lbl(d)}: допуск {T.fmt(tol)} мм ({grade_txt}) — "
                            f"очень жёсткий, проверьте необходимость такой точности", pg, bb, STD_TOL)
                try:
                    if tol * 1000 > T.it_value(nom, cfg.get("coarse_it", 17)):
                        drw.add(INFO, "D19", CAT_DIM, f"Размер {_lbl(d)}: допуск {T.fmt(tol)} мм грубее IT"
                                f"{cfg.get('coarse_it', 17)} — проверьте, не ошибка ли в отклонении", pg, bb, STD_TOL)
                except T.ToleranceError:
                    pass
                limits_info.append((d, None, (up, lo)))

        if ((d.field or d.fit_hole) and d.kind in ("diameter", "linear")
                and not in_ra40(nom)):
            drw.add(INFO, "D11", CAT_DIM, f"Номинал {fmtn(nom)} в {_lbl(d)} не из ряда Ra40 ГОСТ 6636 — для "
                    f"посадочных размеров предпочтителен нормальный ряд (если размер не задан покупным изделием)",
                    pg, bb, "ГОСТ 6636-69")

    drw.facts["limits"] = [
        {"dim": d.raw, "code": code,
         "limits": (_fmt_lim(*val) if isinstance(val, tuple) else
                    f"отв. {_fmt_lim(*val.hole_limits)}; вал {_fmt_lim(*val.shaft_limits)} ({val.kind})"),
         "grade": _grade_of(d, code, val)}
        for d, code, val in limits_info]


def _grade_of(d: Dimension, code, val) -> int | None:
    try:
        if code and "/" not in code:
            return T.parse_field(code).grade
        if code:
            return T.parse_field(code.split("/")[1]).grade
        return T.equivalent_grade(d.nominal, val[0] - val[1])
    except Exception:
        return None


# ------------------------------------------------- технические требования --
def check_tt(drw: Drawing, cfg: dict) -> None:
    tt = " ".join(drw.tt)
    refs1 = [d for d in drw.dims if d.reference == "*"]
    refs2 = [d for d in drw.dims if d.reference == "**"]
    if refs1 and not re.search(r"(?<!\*)\*(?!\*)", tt):
        d = refs1[0]
        drw.add(WARNING, "D09", CAT_TT, f"На чертеже {len(refs1)} размер(ов) со знаком «*» "
                f"({', '.join(x.raw for x in refs1[:5])}), но в ТТ нет пояснения «* Размер(ы) для справок»",
                d.page, d.bbox, "ГОСТ 2.316-2008")
    if refs2 and "**" not in tt:
        d = refs2[0]
        drw.add(WARNING, "D09", CAT_TT, f"Размеры со знаком «**» ({', '.join(x.raw for x in refs2[:5])}) "
                f"не пояснены в ТТ", d.page, d.bbox, "ГОСТ 2.316-2008")
    if re.search(r"\*\s*Размер", tt) and not refs1 and drw.dims and not drw.ocr:
        drw.add(INFO, "P07", CAT_TT, "В ТТ есть пункт «* Размеры для справок», но размеров со знаком «*» "
                "на чертеже не найдено", None, None, "ГОСТ 2.316-2008")

    untoleranced = [d for d in drw.dims if d.kind in ("linear", "diameter", "radius", "square", "thickness")
                    and not d.has_tolerance and not d.reference]
    if untoleranced:
        tt_key = ref_key(tt)
        refs = [ref_key(r) for r in cfg.get("general_tolerance_refs", [])]
        if not any(r and r in tt_key for r in refs):
            drw.add(WARNING, "D10", CAT_TT, f"{len(untoleranced)} размер(ов) без предельных отклонений, а в ТТ нет "
                    f"указания неуказанных предельных отклонений (например, «Неуказанные предельные отклонения "
                    f"размеров — по ГОСТ 30893.1-m» или «H14, h14, ±IT14/2»)", None, None, "ГОСТ 30893.1-2002")

    # шероховатость vs квалитет
    graded = [(x["grade"], x["dim"]) for x in drw.facts.get("limits", []) if x.get("grade")]
    if graded:
        gmin, dmin = min(graded)
        need = RA_FOR_IT.get(gmin)
        if need:
            ras = [r["value"] if r["param"].lower() == "ra" else r["value"] / 5
                   for r in drw.roughness if r.get("value")]
            if not ras:
                drw.add(WARNING, "D14", CAT_DIM, f"Есть размеры с допуском IT{gmin} ({dmin}), но шероховатость "
                        f"на чертеже не указана; для IT{gmin} обычно нужна Ra ≤ {fmtn(need)} мкм",
                        None, None, "ГОСТ 2.309-73, ГОСТ 2789-73")
            elif min(ras) > need * 1.01:
                drw.add(WARNING, "D14", CAT_DIM, f"Размер {dmin} выполнен по IT{gmin}, а самая чистая "
                        f"шероховатость на чертеже ≈ Ra {fmtn(round(min(ras), 2))} — для IT{gmin} рекомендуется "
                        f"Ra ≤ {fmtn(need)} мкм. Проверьте шероховатость посадочной поверхности",
                        None, None, "ГОСТ 2789-73")


def _graphic_signs(drw: Drawing, general: list[dict]) -> list[tuple[float, float]]:
    """Знаки шероховатости, нарисованные графикой (без текста значения — например, «без обработки» —
    или со значением, набранным отдельно): две линии из общей точки под ≈60°, короткая 3–8 мм, длинная в
    1,4–2,3 раза длиннее. Знаки у общего обозначения в углу листа (само √ и √ в скобках) не считаются."""
    pg = drw.first_page
    segs = (drw.facts.get("_segments") or {}).get(pg) or []
    ends: dict[tuple[int, int], list] = {}
    for x1, y1, x2, y2 in segs:
        ln = math.hypot(x2 - x1, y2 - y1)
        if 3.0 <= ln <= 20.0:
            for (px, py), (qx, qy) in (((x1, y1), (x2, y2)), ((x2, y2), (x1, y1))):
                ends.setdefault((round(px * 4), round(py * 4)), []).append((qx - px, qy - py, ln, px, py))
    out = []
    for arms in ends.values():
        for i, a in enumerate(arms):
            for b in arms[i + 1:]:
                short, long_ = sorted((a, b), key=lambda t: t[2])
                if not (3.0 <= short[2] <= 8.0 and 1.4 <= long_[2] / short[2] <= 2.3):
                    continue
                cos = (a[0] * b[0] + a[1] * b[1]) / (a[2] * b[2])
                if not 50 <= math.degrees(math.acos(max(-1, min(1, cos)))) <= 70:
                    continue
                if abs(a[0] * b[1] - a[1] * b[0]) < 1e-6:
                    continue
                out.append((a[3], a[4]))
    keep = []
    for x, y in out:
        if any(g.get("bbox") and g["bbox"][0] - 30 <= x <= g["bbox"][2] + 10 and g["bbox"][1] - 12 <= y <= g["bbox"][3] + 12
               for g in general):
            continue
        if drw.title.origin and x >= drw.title.origin[0] and y >= drw.title.origin[1]:
            continue
        keep.append((x, y))
    return keep


def check_roughness(drw: Drawing, cfg: dict) -> None:
    std = "ГОСТ 2789-73"
    seen = set()
    for r in drw.roughness:
        v, prm = r.get("value"), r.get("param")
        if v is None or (prm, v) in seen:
            continue
        seen.add((prm, v))
        series, pref = (RA_GOST, RA_PREFERRED) if prm == "Ra" else (RZ_SERIES, RZ_PREFERRED)
        where = (r.get("page"), r.get("bbox"))
        if not any(abs(v - x) < 1e-6 for x in series):
            near = sorted(series, key=lambda x: abs(x - v))[:2]
            drw.add(WARNING, "R01", CAT_DIM, f"Шероховатость {prm} {fmtn(v)} не из ряда ГОСТ 2789-73 (ближайшие: "
                    f"{', '.join(fmtn(x) for x in sorted(near))})", *where, std)
        elif not any(abs(v - x) < 1e-6 for x in pref):
            drw.add(INFO, "R03", CAT_DIM, f"Шероховатость {prm} {fmtn(v)} — не из предпочтительных значений "
                    f"ГОСТ 2789-73 ({', '.join(fmtn(x) for x in pref if v / 3 < x < v * 3)}…)", *where, std)
        if r.get("cyrillic"):
            drw.add(INFO, "D16", CAT_DIM, f"«{r.get('raw')}»: в обозначении параметра шероховатости русская буква "
                    f"«а» вместо латинской", *where, "ГОСТ 2.309-73")
    general = [r for r in drw.roughness if r.get("general") and r.get("page") is not None]
    local = [r for r in drw.roughness if not r.get("general")]
    signs = _graphic_signs(drw, general) if general and not local else []
    drw.facts["rough_signs"] = len(signs)
    for g in general:
        if "(" in (g.get("raw") or "") and not local and not signs and not drw.ocr:
            drw.add(INFO, "R02", CAT_DIM, f"Общее обозначение «{g['param']} {fmtn(g['value'])} (√)», а на изображении "
                    f"шероховатость не указана. Если шероховатость одна для всех поверхностей, знак (√) не ставят "
                    f"(ГОСТ 2.309-73 п. 2.6); проверьте, не потеряны ли обозначения на изображении",
                    g.get("page"), g.get("bbox"), "ГОСТ 2.309-73")


# ---------------------------------------------------- технологичность ------
def _sheet_thickness(drw: Drawing) -> float | None:
    mat = drw.facts.get("material", {})
    if mat.get("sortament") in ("Лист", "Плита", "Полоса") and mat.get("size"):
        return mat["size"]
    th = [d.nominal for d in drw.dims if d.kind == "thickness" and d.nominal]
    if th:
        return th[0]
    spec_mat = drw.facts.get("spec_material", {})
    if spec_mat.get("sortament") == "Лист" and spec_mat.get("size"):
        return spec_mat["size"]
    return None


def check_technology(drw: Drawing, cfg: dict) -> None:
    if drw.facts.get("is_assembly"):
        return
    s = _sheet_thickness(drw)
    drw.facts["sheet_thickness"] = s
    if not s:
        return
    las = cfg.get("laser", {})
    k = las.get("hole_min_ratio", 1.0)
    for d in drw.dims:
        if d.kind == "diameter" and d.nominal and d.nominal < k * s and not d.reference:
            bolt = clearance_for(d.nominal) if not d.has_tolerance else None
            if bolt:
                drw.add(INFO, "T01", CAT_TECH, f"Отверстие {_lbl(d)} меньше толщины листа s={fmtn(s)}, но это "
                        f"отверстие под крепёж М{bolt} (ГОСТ 11284): конусность и грат после лазера для него "
                        f"обычно не критичны — уточните у оператора, режет ли станок ⌀{fmtn(d.nominal)} в листе "
                        f"{fmtn(s)}", d.page, d.bbox, "ГОСТ 11284-75")
            else:
                drw.add(WARNING, "T01", CAT_TECH, f"Отверстие {_lbl(d)} меньше толщины листа s={fmtn(s)}: лазером "
                        f"такое отверстие режется плохо (конусность, оплавление) — предусмотрите сверловку или "
                        f"увеличьте ⌀", d.page, d.bbox)
        if d.kind == "thread" and d.nominal and d.count:
            entry = METRIC_THREADS.get(d.nominal)
            p = d.pitch or (entry[0] if entry and entry[0] else None)
            if p and s / p < cfg.get("thread_min_turns", 3):
                drw.add(WARNING, "T04", CAT_TECH, f"Резьба {_lbl(d)} в листе s={fmtn(s)}: всего ≈{s / p:.1f} витка — "
                        f"соединение ненадёжно; рассмотрите вварную гайку/бобышку или резьбу с мелким шагом",
                        d.page, d.bbox)
    lim = las.get("it_limit", 11)
    tight = [x for x in drw.facts.get("limits", []) if x.get("grade") and x["grade"] < lim]
    if tight:
        first = next((d for d in drw.dims if d.raw == tight[0]["dim"]), None)
        listing = "; ".join(f"«{x['dim']}» ≈IT{x['grade']}" for x in tight[:8]) + ("…" if len(tight) > 8 else "")
        drw.add(WARNING, "T03", CAT_TECH, f"На листовой детали {len(tight)} размер(а/ов) точнее IT{lim}: {listing}. "
                f"Лазерная/плазменная резка даёт ≈IT12–IT14 — для этих поверхностей нужна мехобработка, "
                f"проверьте технологию", first.page if first else None, first.bbox if first else None)


# ------------------------------------------------- основная надпись/масса --
def _scale_factor(scale: str) -> float | None:
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*:\s*(\d+(?:[.,]\d+)?)", scale or "")
    if not m:
        return None
    a, b = (float(x.replace(",", ".")) for x in m.groups())
    return b / a if a else None


def _overall(drw: Drawing) -> dict:
    """Оценка габаритов по размерам (без учёта справочных толщин)."""
    s = drw.facts.get("sheet_thickness")
    lin_h, lin_v, diam = [], [], []
    p0 = drw.page_info(drw.first_page)
    k = _scale_factor(drw.title.scale)
    limit = max(p0.width, p0.height) * (k or 1) * 1.2 if (p0 and k) else None
    for d in drw.dims:
        if not d.nominal or d.kind in ("angle", "chamfer", "thread_other"):
            continue
        if limit and d.nominal > limit:          # не помещается на лист в указанном масштабе — не размер детали
            continue
        if s and abs(d.nominal - s) < 1e-6 and (d.reference or d.kind == "thickness"):
            continue
        if d.kind in ("diameter", "sphere"):
            diam.append(d.nominal)
        elif d.kind == "thread":
            diam.append(d.nominal)
        elif d.kind in ("linear", "square"):
            (lin_v if d.vertical else lin_h).append(d.nominal)
    out = {}
    if lin_h or lin_v or diam:
        allv = lin_h + lin_v + diam
        out["L"] = max(allv)
        if lin_h and lin_v:
            out["W"] = min(max(lin_h), max(lin_v))
        rest = sorted(allv, reverse=True)[1:]
        if rest:
            out["W_max"] = rest[0]                      # самая «щедрая» оценка второй стороны
        if diam:
            out["D"] = max(diam)
    return out


def check_title(drw: Drawing, cfg: dict, spec_item: dict | None) -> None:
    tb = drw.title
    fn = drw.filename
    if not tb.found and not drw.facts.get("cdw"):
        drw.add(INFO, "B00", CAT_TB, "Основная надпись по форме 1 не распознана — поля штампа не проверены",
                None, None, "ГОСТ Р 2.104-2023")
        return
    des = tb.designation.strip()
    is_asm = drw.facts.get("is_assembly")
    if not des:
        drw.add(WARNING, "B04", CAT_TB, "Обозначение в основной надписи (графа 2) не найдено", drw.first_page, None,
                "ГОСТ Р 2.104-2023")
    elif drw.facts.get("designation_from_26"):
        drw.add(INFO, "B04", CAT_TB, f"Обозначение взято из графы 26 («{des}») — в графе 2 текст не найден "
                f"(возможно, выведен кривыми)", drw.first_page, None)

    # обозначение: имя файла, графа 26
    fdes = drw.facts.get("file_designation")
    if des and fdes and norm_designation(fdes) not in norm_designation(des):
        drw.add(WARNING, "B10", CAT_TB, f"Обозначение в штампе «{des}» не совпадает с именем файла «{fdes}»",
                drw.first_page, tb.bboxes.get("designation"))
    if des and tb.rotated_designation and norm_designation(tb.rotated_designation) != norm_designation(des):
        drw.add(WARNING, "B11", CAT_TB, f"Обозначение в графе 26 «{tb.rotated_designation}» отличается от "
                f"основной надписи «{des}»", drw.first_page, None, "ГОСТ Р 2.104-2023")
    m = re.fullmatch(DESIG_RE, des.replace(" ", " "))
    if des and any(des.startswith(o + ".") for o in cfg.get("org_codes", [])):
        if not m:
            drw.add(WARNING, "B12", CAT_TB, f"Обозначение «{des}» не соответствует структуре ГОСТ 2.201: "
                    f"КОД.ХХХХХХ.ХХХ[-ХХ] [код документа]", drw.first_page, tb.bboxes.get("designation"),
                    "ГОСТ 2.201-80")
        else:
            cls = int(m.group("cls")[:2])
            if not is_asm and not 71 <= cls <= 76 and m.group("doc") is None:
                drw.add(INFO, "B12", CAT_TB, f"Класс {m.group('cls')[:2]} в обозначении детали «{des}»: по "
                        f"классификатору ЕСКД детали — классы 71–76", drw.first_page,
                        tb.bboxes.get("designation"), "Классификатор ЕСКД")
            if is_asm and 71 <= cls <= 76:
                drw.add(WARNING, "B12", CAT_TB, f"Сборочный чертёж «{des}» имеет класс детали ({cls})",
                        drw.first_page, tb.bboxes.get("designation"), "Классификатор ЕСКД")

    # масса
    mass = tb.mass
    if mass is None and re.search(r"(?i)табл", tb.mass_raw or ""):
        pass                                           # групповой чертёж: «см. табл.» (ГОСТ 2.113)
    elif mass is None:
        drw.add(WARNING, "B01", CAT_TB, "Масса в основной надписи не указана (графа 5)", drw.first_page,
                None, "ГОСТ 2.109-73")
    else:
        mass_tol_cfg = cfg.get("mass", {})
        ref = None
        src = None
        if spec_item and isinstance(spec_item.get("mass"), (int, float)) and spec_item["mass"] > 0:
            ref, src = float(spec_item["mass"]), drw.facts.get("spec_source", "спецификации")
        if ref is not None:
            step = 0.5 * 10 ** (-_decimals(tb.mass_raw)) if tb.mass_raw else 0
            allowed = max(mass_tol_cfg.get("abs_tol", 0.005), mass_tol_cfg.get("rel_tol", 0.03) * ref) + step
            drw.facts["mass_ref"] = ref
            if abs(mass - ref) > allowed:
                drw.add(ERROR, "B02", CAT_TB, f"Масса в штампе {tb.mass_raw} кг, в {src} — {fmtn(round(ref, 4))} кг "
                        f"(расхождение {abs(mass - ref) / ref * 100:.0f} %). Пересчитайте массу по 3D-модели",
                        drw.first_page, tb.bboxes.get("mass"))
        # физическая правдоподобность
        mat = drw.facts.get("material", {})
        rho = density_for(tb.material) or density_for(spec_item.get("material", "") if spec_item else "")
        ov = _overall(drw)
        drw.facts["overall"] = ov
        s = drw.facts.get("sheet_thickness")
        vol = None
        if rho and not is_asm:
            if s and ov.get("L"):
                w = ov.get("W") or ov.get("D") or ov.get("L")
                vol = s * ov["L"] * w
                vol_max = s * ov["L"] * max(w, ov.get("W_max") or w)
                shape = f"лист {fmtn(s)}×{fmtn(ov['L'])}×{fmtn(w)}"
            elif ov.get("D") and ov.get("L"):
                vol = vol_max = math.pi / 4 * ov["D"] ** 2 * ov["L"]
                shape = f"цилиндр ⌀{fmtn(ov['D'])}×{fmtn(ov['L'])}"
        if vol and not drw.ocr:
            mmax = rho[0] * vol * 1e-9
            drw.facts["mass_bbox"] = round(mmax, 4)
            step = 0.5 * 10 ** (-_decimals(tb.mass_raw)) if tb.mass_raw else 0
            mgen = rho[0] * vol_max * 1e-9
            if mass > mgen * 1.05 + step:
                drw.add(ERROR if mass > mgen * 1.5 + step else WARNING, "B03", CAT_TB, f"Масса {tb.mass_raw} кг больше массы сплошной заготовки по габаритам "
                        f"({shape}, {rho[1]}) ≈ {fmtn(round(mmax, 3))} кг — масса указана неверно (единицы, "
                        f"плотность, не та модель)", drw.first_page, tb.bboxes.get("mass"))
            elif s and mass < mmax * mass_tol_cfg.get("min_fill", 0.12) - step:
                drw.add(WARNING, "B03", CAT_TB, f"Масса {tb.mass_raw} кг составляет лишь "
                        f"{mass / mmax * 100:.0f} % от массы габаритной заготовки ({shape}) ≈ "
                        f"{fmtn(round(mmax, 3))} кг — проверьте массу", drw.first_page, tb.bboxes.get("mass"))

    # материал
    mat = drw.facts.get("material", {})
    if not is_asm and not tb.material:
        drw.add(WARNING, "B07", CAT_TB, "Не указан материал детали (графа 3)", drw.first_page, None,
                "ГОСТ 2.109-73")
    elif not is_asm and mat.get("grade") and not mat.get("sortament"):
        th = [d for d in drw.dims if d.kind == "thickness" or
              (d.reference and drw.facts.get("spec_material", {}).get("size") == d.nominal)]
        if th or drw.facts.get("spec_material", {}).get("sortament"):
            drw.add(WARNING, "B13", CAT_TB, f"В графе 3 указана только марка «{tb.material}» без сортамента; для "
                    f"детали из проката записывают «Лист 5 ГОСТ 19903-2015 / Ст3сп ГОСТ 14637-89»",
                    drw.first_page, tb.bboxes.get("material"), "ГОСТ 2.109-73")
    s_mat = mat.get("size") if mat.get("sortament") in ("Лист", "Полоса", "Плита") else None
    if s_mat:
        for d in drw.dims:
            if d.kind == "thickness" and d.nominal and abs(d.nominal - s_mat) > 1e-6:
                drw.add(ERROR, "B14", CAT_TB, f"Толщина {_lbl(d)} не совпадает с толщиной листа в графе 3 "
                        f"({fmtn(s_mat)})", d.page, d.bbox)

    # формат и масштаб
    fmt_txt = tb.format.replace(" ", "").upper().replace("А", "A")
    p0 = drw.page_info(drw.first_page)
    m = re.match(r"A(\d)(?:[X×Х](\d))?", fmt_txt)
    if m and p0:
        base = FORMATS.get(f"A{m.group(1)}")
        if base:
            a, b = base
            if m.group(2):
                a, b = b, a * int(m.group(2))
            dims_page = sorted((p0.width, p0.height))
            exp = sorted((a, b))
            if abs(dims_page[0] - exp[0]) > 4 or abs(dims_page[1] - exp[1]) > 4:
                drw.add(WARNING, "B05", CAT_TB, f"В штампе формат {tb.format}, а лист {fmtn(round(p0.width))}×"
                        f"{fmtn(round(p0.height))} мм", drw.first_page, tb.bboxes.get("format"), "ГОСТ 2.301-68")
    sc = tb.scale.replace(" ", "")
    if sc and sc not in SCALES:
        k = _scale_factor(sc)
        hint = ""
        if k and k > 1 and f"1:{fmtn(round(k, 2))}" in SCALES:
            hint = f" — записывается как 1:{fmtn(round(k, 2))}"
        elif k and k < 1 and f"{fmtn(round(1 / k, 2))}:1" in SCALES:
            hint = f" — записывается как {fmtn(round(1 / k, 2))}:1"
        drw.add(WARNING, "B06", CAT_TB, f"Масштаб «{tb.scale}» записан не по ГОСТ 2.302-68{hint}", drw.first_page,
                tb.bboxes.get("scale"), "ГОСТ 2.302-68")

    # номер изменения в имени файла
    m = re.search(r"(?i)изм\.?\s*(\d+)", fn)
    if m:
        nums = [int(c["num"]) for c in tb.changes if c.get("num", "").isdigit()]
        if not nums:
            drw.add(WARNING, "B08", CAT_TB, f"В имени файла указано изм. {m.group(1)}, а в таблице изменений "
                    f"основной надписи изменений нет", drw.first_page, None)
        elif max(nums) != int(m.group(1)):
            drw.add(WARNING, "B08", CAT_TB, f"В имени файла изм. {m.group(1)}, а в основной надписи последнее "
                    f"изменение № {max(nums)}", drw.first_page, None)

    for role in ("Разраб.", "Пров.", "Н.контр.", "Утв."):
        if role not in tb.people:
            drw.add(INFO, "B09", CAT_TB, f"Не заполнена графа «{role}»", drw.first_page, None,
                    "ГОСТ Р 2.104-2023")


# ------------------------------------------------------------ ERP / СП ------
def check_erp(drw: Drawing, cfg: dict, spec_item: dict | None, spec_loaded: bool) -> None:
    tb = drw.title
    if not spec_loaded:
        return
    if spec_item is None:
        drw.add(INFO, "E01", CAT_ERP, f"Обозначение «{tb.designation or drw.facts.get('file_designation') or '?'}» "
                f"не найдено в спецификации/ERP", None, None)
        return
    src = drw.facts.get("spec_source", "спецификации")
    if spec_item.get("name") and tb.name:
        a, b = norm_words(tb.name), norm_words(spec_item["name"])
        if a and b and a not in b and b not in a:
            drw.add(WARNING, "E02", CAT_ERP, f"Наименование в штампе «{tb.name}», в {src} — «{spec_item['name']}»",
                    drw.first_page, tb.bboxes.get("name"))
    sm = drw.facts.get("spec_material") or {}
    dm = drw.facts.get("material") or {}
    if sm.get("raw") and tb.material:
        if sm.get("grade") and dm.get("grade") and norm_grade(sm["grade"]) != norm_grade(dm["grade"]):
            drw.add(ERROR, "E04", CAT_ERP, f"Марка материала на чертеже «{dm['grade']}», в {src} — «{sm['grade']}» "
                    f"({sm['raw']})", drw.first_page, tb.bboxes.get("material"))
        if sm.get("sortament") and dm.get("sortament") and sm["sortament"] != dm["sortament"]:
            drw.add(ERROR, "E06", CAT_ERP, f"Сортамент на чертеже «{dm['sortament']}», в {src} — «{sm['sortament']}»",
                    drw.first_page, tb.bboxes.get("material"))
        elif (sm.get("sortament") in ("Лист", "Полоса", "Плита", "Круг") and sm.get("size") and dm.get("size")
              and abs(sm["size"] - dm["size"]) > 1e-6):
            drw.add(ERROR, "E07", CAT_ERP, f"Типоразмер заготовки на чертеже {fmtn(dm['size'])}, в {src} — "
                    f"{fmtn(sm['size'])} ({sm['raw']})", drw.first_page, tb.bboxes.get("material"))
        elif sm.get("sortament") == "Лист" and sm.get("size") and not dm.get("sortament"):
            th = [d for d in drw.dims if d.kind == "thickness" or d.reference]
            if th and not any(abs(d.nominal - sm["size"]) < 1e-6 for d in th if d.nominal):
                drw.add(ERROR, "E07", CAT_ERP, f"В {src} лист {fmtn(sm['size'])} мм, на чертеже толщины "
                        f"{fmtn(sm['size'])} не найдено (справочные: {', '.join(d.raw for d in th[:5])})",
                        drw.first_page, None)
    if spec_item.get("grade") and dm.get("grade") and norm_grade(spec_item["grade"]) not in norm_grade(dm["grade"]) \
            and norm_grade(dm["grade"]) not in norm_grade(spec_item["grade"]):
        drw.add(ERROR, "E04", CAT_ERP, f"Марка материала на чертеже «{dm['grade']}», в {src} — "
                f"«{spec_item['grade']}»", drw.first_page, tb.bboxes.get("material"))
    # размеры заготовки из ERP (ДхШ)
    bs = str(spec_item.get("blank_size") or "")
    ov = drw.facts.get("overall") or _overall(drw)
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", bs)]
    if nums and ov.get("L") and sm.get("sortament") != "Лист":
        L = max(nums)
        if abs(L - ov["L"]) > max(3.0, 0.03 * L) and L < ov["L"]:
            drw.add(WARNING, "E05", CAT_ERP, f"Длина заготовки в {src} {fmtn(L)} мм меньше наибольшего размера "
                    f"детали на чертеже {fmtn(ov['L'])} мм", None, None)


def file_notes(drw: Drawing) -> None:
    if drw.ocr:
        confs = [l.conf for l in drw.lines]
        avg = sum(confs) / len(confs) if confs else 0
        drw.add(INFO, "F01", CAT_FILE, f"Текст распознан OCR (средняя уверенность {avg * 100:.0f} %). Значения "
                f"размеров и отклонений сверьте с изображением — мелкие индексы допусков OCR может пропустить",
                None, None)
    for p in drw.pages:
        if p.scanned and not drw.ocr:
            drw.add(WARNING, "F02", CAT_FILE, f"Лист {p.number + 1} — растровое изображение без текста, а OCR "
                    f"недоступен/выключен: содержимое не проверено", p.number, None)
