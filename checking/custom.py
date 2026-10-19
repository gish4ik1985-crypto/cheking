"""Правила предприятия, заданные администратором в настройках (config.json → "custom_rules").

Правило — декларативное описание (без кода): тип проверки, параметры, к каким документам применять, важность и
текст замечания. Проверяется по сохранённому результату разбора чертежа (report.drawing_to_dict), поэтому новое
правило сразу видно и в уже сохранённых отчётах."""
from __future__ import annotations

import re

from .material import norm_grade, parse_material
from .model import CAT_CUSTOM, ERROR, WARNING, INFO, SEVERITY_RU
from .standards import fmtn
from .textnorm import to_float

# Описание типов и их параметров — для формы в панели настроек
KINDS = {
    "text_required": "В тексте должно быть",
    "text_forbidden": "В тексте не должно быть",
    "field": "Графа основной надписи",
    "allowed": "Ограничительный перечень (разрешены только…)",
    "forbidden": "Запрещённые значения",
    "limit": "Предельное значение",
}
WHERE = {"tt": "технические требования", "all": "весь текст чертежа", "title": "основная надпись"}
FIELDS = {"designation": "Обозначение", "name": "Наименование", "material": "Материал", "organization": "Организация",
          "mass": "Масса", "scale": "Масштаб", "format": "Формат", "people:Разраб.": "Разраб.",
          "people:Пров.": "Пров.", "people:Т.контр.": "Т.контр.", "people:Н.контр.": "Н.контр.", "people:Утв.": "Утв."}
FIELD_CHECKS = {"filled": "заполнена", "equals": "равна", "contains": "содержит", "not_contains": "не содержит",
                "regex": "соответствует шаблону (регулярное выражение)"}
LIST_WHAT = {"grade": "марки материалов", "material": "материал (фрагмент записи в графе 3)",
             "field": "поля допусков (H7, h6…)", "thread": "метрические резьбы (M8, M10x1,25…)",
             "thread_tol": "допуск метрической резьбы (6g, 6H…)", "std": "стандарты (ГОСТ 19903, ОСТ…)", "ra": "значения шероховатости Ra"}
LIMIT_WHAT = {"it_min": "квалитет не точнее IT…", "ra_min": "шероховатость не точнее Ra…",
              "thickness_max": "толщина листа не больше, мм", "mass_max": "масса не больше, кг"}
APPLIES = {"all": "все документы", "drawings": "все чертежи", "parts": "детали", "assemblies": "сборочные чертежи",
           "sheet": "листовые детали", "spec": "спецификации"}


def _norm_thread(s: str) -> str:
    s = s.strip().upper().replace("М", "M").replace("Х", "X").replace("×", "X").replace(",", ".").replace(" ", "")
    s = re.sub(r"\.0+(?=X|$)", "", s)
    return s


def _norm_value(what: str, s: str) -> str:
    s = (s or "").strip()
    if what == "grade":
        return norm_grade(s)
    if what == "thread":
        return _norm_thread(s)
    if what in ("field", "thread_tol"):
        return s.replace(" ", "")
    if what == "std":
        return re.sub(r"\s+", "", s.upper())
    if what == "ra":
        v = to_float(s)
        return fmtn(v) if v is not None else s
    return s.lower()


def validate(rule: dict) -> list[str]:
    errs = []
    kind = rule.get("kind")
    if kind not in KINDS:
        errs.append("Не выбран тип проверки")
    if not (rule.get("title") or "").strip():
        errs.append("Укажите название правила")
    if rule.get("severity") not in (ERROR, WARNING, INFO):
        errs.append("Не выбрана важность")
    if (rule.get("when_tt") or "").strip():
        try:
            re.compile(rule["when_tt"])
        except re.error as e:
            errs.append(f"Ошибка в условии «если в тексте есть»: {e}")
    if kind in ("text_required", "text_forbidden"):
        if not (rule.get("pattern") or "").strip():
            errs.append("Укажите, какой текст искать")
        if rule.get("match") == "regex":
            try:
                re.compile(rule.get("pattern") or "")
            except re.error as e:
                errs.append(f"Ошибка в регулярном выражении: {e}")
    if kind == "field":
        if rule.get("field") not in FIELDS:
            errs.append("Не выбрана графа")
        if rule.get("check") not in FIELD_CHECKS:
            errs.append("Не выбрано условие")
        if rule.get("check") != "filled" and not (rule.get("value") or "").strip():
            errs.append("Укажите значение для сравнения")
        if rule.get("check") == "regex":
            try:
                re.compile(rule.get("value") or "")
            except re.error as e:
                errs.append(f"Ошибка в регулярном выражении: {e}")
    if kind in ("allowed", "forbidden"):
        if rule.get("what") not in LIST_WHAT:
            errs.append("Не выбрано, что проверять")
        if not [x for x in rule.get("values") or [] if str(x).strip()]:
            errs.append("Перечень пуст")
    if kind == "limit":
        if rule.get("what") not in LIMIT_WHAT:
            errs.append("Не выбрано, что ограничивать")
        if to_float(str(rule.get("value") or "")) is None:
            errs.append("Укажите числовое значение")
    return errs


def _applies(d: dict, rule: dict) -> bool:
    if d.get("error"):
        return False
    facts = d.get("facts") or {}
    a = rule.get("applies") or "all"
    spec = d.get("kind") == "spec"
    if a == "spec" and not spec or a != "spec" and a != "all" and spec:
        return False
    if a == "parts" and facts.get("is_assembly"):
        return False
    if a == "assemblies" and not facts.get("is_assembly"):
        return False
    if a == "sheet" and not facts.get("sheet_thickness"):
        return False
    t = d.get("title") or {}
    wt = (rule.get("when_tt") or "").strip()
    if wt and not re.search(wt, _text(d, "all"), re.I):
        return False
    mc = (rule.get("material_contains") or "").strip().lower()
    if mc and mc not in (t.get("material") or "").lower():
        return False
    dp = (rule.get("designation_prefix") or "").strip()
    if dp and not (t.get("designation") or "").upper().startswith(dp.upper()):
        return False
    return True


def _text(d: dict, where: str) -> str:
    t = d.get("title") or {}
    if where == "tt":
        return " ".join(d.get("tt") or [])
    if where == "title":
        return " ".join(str(t.get(k) or "") for k in ("designation", "name", "material", "organization", "mass",
                                                     "scale", "format"))
    return " ".join((d.get("texts") or []) + (d.get("tt") or []) + [str(t.get("material") or "")])


def _found(text: str, rule: dict) -> str | None:
    pat = rule.get("pattern") or ""
    if rule.get("match") == "regex":
        m = re.search(pat, text, re.I)
        return m.group(0) if m else None
    i = text.lower().find(pat.lower())
    return text[i:i + len(pat)] if i >= 0 else None


def _values(d: dict, what: str) -> list[tuple[str, int | None, list | None]]:
    """(значение, лист, место) из результата разбора."""
    t = d.get("title") or {}
    out = []
    if what == "grade":
        g = parse_material(t.get("material") or "").get("grade")
        if g:
            out.append((g, None, None))
    elif what == "material":
        if t.get("material"):
            out.append((t["material"], None, None))
    elif what == "field":
        for x in d.get("dims") or []:
            for f in ([x["field"]] if x.get("field") else []) + (x["fit"].split("/") if x.get("fit") else []):
                out.append((f, x.get("page"), x.get("bbox")))
    elif what == "thread":
        for x in d.get("dims") or []:
            if x.get("kind") == "thread" and x.get("nominal"):
                m = re.match(r"[MМ]\s*\d+(?:[.,]\d+)?(?:\s*[×xх]\s*\d+(?:[.,]\d+)?)?", x.get("raw") or "")
                out.append((m.group(0) if m else f"M{fmtn(x['nominal'])}", x.get("page"), x.get("bbox")))
    elif what == "thread_tol":
        for x in d.get("dims") or []:
            if x.get("kind") == "thread" and x.get("thread_tol"):
                out.append((x["thread_tol"], x.get("page"), x.get("bbox")))
    elif what == "std":
        for m in re.finditer(r"(?:ГОСТ|ОСТ|СТО|СТП)\s*Р?\s*[\d.]+", _text(d, "all")):
            out.append((re.sub(r"\s+", " ", m.group(0)), None, None))
    elif what == "ra":
        for r in d.get("roughness") or []:
            if r.get("value") is not None and (r.get("param") or "Ra") == "Ra":
                out.append((fmtn(r["value"]), None, None))
    return out


def _msg(rule: dict, default: str, value: str = "") -> str:
    m = (rule.get("message") or "").strip()
    if m:
        return m.replace("{value}", value)
    return default


def evaluate(d: dict, rule: dict) -> list[dict]:
    """Замечания одного правила к одному документу (словари в формате отчёта)."""
    if not _applies(d, rule):
        return []
    kind, title = rule.get("kind"), rule.get("title", "")
    hits: list[tuple[str, int | None, list | None]] = []
    if kind == "text_required":
        where = rule.get("where") or "tt"
        if not _found(_text(d, where), rule):
            hits.append((_msg(rule, f"{title}: в {WHERE.get(where, where)} нет «{rule.get('pattern')}»"), None, None))
    elif kind == "text_forbidden":
        where = rule.get("where") or "all"
        f = _found(_text(d, where), rule)
        if f:
            hits.append((_msg(rule, f"{title}: в {WHERE.get(where, where)} есть «{f}»", f), None, None))
    elif kind == "field":
        fld = rule.get("field") or "designation"
        t = d.get("title") or {}
        val = str((t.get("people") or {}).get(fld.split(":", 1)[1], "") if fld.startswith("people:")
                  else t.get(fld) or "").strip()
        chk, ref = rule.get("check"), (rule.get("value") or "").strip()
        ok = {"filled": bool(val), "equals": val.lower() == ref.lower(), "contains": ref.lower() in val.lower(),
              "not_contains": ref.lower() not in val.lower(),
              "regex": bool(re.search(ref, val)) if chk == "regex" else True}.get(chk, True)
        if not ok:
            hits.append((_msg(rule, f"{title}: графа «{FIELDS.get(fld, fld)}» — «{val or 'пусто'}» "
                                    f"({FIELD_CHECKS.get(chk, chk)}{' «' + ref + '»' if chk != 'filled' else ''})", val),
                         None, None))
    elif kind in ("allowed", "forbidden"):
        what = rule.get("what")
        lst = [str(x).strip() for x in rule.get("values") or [] if str(x).strip()]
        seen = set()
        for v, pg, bb in _values(d, what):
            nv = _norm_value(what, v)
            if what == "material":
                inside = any(x.lower() in v.lower() for x in lst)
            elif what == "std":
                inside = any(nv.startswith(_norm_value("std", x)) for x in lst)
            else:
                inside = nv in {_norm_value(what, x) for x in lst}
            bad = not inside if kind == "allowed" else inside
            if bad and nv not in seen:
                seen.add(nv)
                default = (f"{title}: «{v}» нет в перечне разрешённых ({', '.join(lst[:12])}"
                           f"{'…' if len(lst) > 12 else ''})" if kind == "allowed"
                           else f"{title}: «{v}» — в перечне запрещённых")
                hits.append((_msg(rule, default, v), pg, bb))
    elif kind == "limit":
        what, lim = rule.get("what"), to_float(str(rule.get("value") or ""))
        facts, t = d.get("facts") or {}, d.get("title") or {}
        if what == "it_min":
            for x in d.get("limits") or []:
                if x.get("grade") and x["grade"] < lim:
                    dim = next((y for y in d.get("dims") or [] if y.get("raw") == x.get("dim")), {})
                    hits.append((_msg(rule, f"{title}: «{x['dim']}» — IT{x['grade']}, точнее IT{fmtn(lim)}",
                                      x.get("dim", "")), dim.get("page"), dim.get("bbox")))
        elif what == "ra_min":
            for r in d.get("roughness") or []:
                v = r.get("value")
                if v is not None and (r.get("param") == "Ra" and v < lim or r.get("param") == "Rz" and v / 5 < lim):
                    hits.append((_msg(rule, f"{title}: {r.get('param')} {fmtn(v)} — точнее Ra {fmtn(lim)}",
                                      fmtn(v)), None, None))
                    break
        elif what == "thickness_max" and facts.get("sheet_thickness") and facts["sheet_thickness"] > lim:
            hits.append((_msg(rule, f"{title}: лист {fmtn(facts['sheet_thickness'])} мм — больше {fmtn(lim)} мм",
                              fmtn(facts["sheet_thickness"])), None, None))
        elif what == "mass_max":
            m = to_float(str(t.get("mass") or "").replace(" ", ""))
            if m is not None and m > lim:
                hits.append((_msg(rule, f"{title}: масса {fmtn(m)} кг — больше {fmtn(lim)} кг", fmtn(m)), None, None))
    sev = rule.get("severity") or WARNING
    return [{"severity": sev, "severity_ru": SEVERITY_RU[sev], "code": rule["code"], "category": CAT_CUSTOM,
             "message": msg, "page": pg, "bbox": bb, "standard": (rule.get("ref") or "").strip() or None,
             "hint": None} for msg, pg, bb in hits]


def rules_of(cfg: dict) -> list[dict]:
    return [r for r in cfg.get("custom_rules") or [] if r.get("code") and not validate(r)]


def apply_to_dict(d: dict, cfg: dict) -> dict:
    """Добавляет замечания правил предприятия (на копии; прежние U-замечания заменяются)."""
    rules = rules_of(cfg)
    out = dict(d)
    base = [f for f in d.get("findings", []) if not f.get("code", "").startswith("U")]
    extra = []
    for r in rules:
        try:
            extra += evaluate(d, r)
        except Exception:
            continue
    out["findings"] = base + extra
    return out


def apply_to_drawing(drw, cfg: dict) -> None:
    from .model import Finding
    from .report import drawing_to_dict
    rules = rules_of(cfg)
    if not rules:
        return
    d = drawing_to_dict(drw)
    for r in rules:
        for f in evaluate(d, r):
            drw.findings.append(Finding(f["severity"], f["code"], f["category"], f["message"], f["page"],
                                        tuple(f["bbox"]) if f["bbox"] else None, f["standard"]))


def next_code(rules: list[dict]) -> str:
    nums = [int(r["code"][1:]) for r in rules if re.fullmatch(r"U\d{2,3}", r.get("code") or "")]
    return f"U{(max(nums) + 1) if nums else 1:02d}"


def describe(rule: dict) -> dict:
    """Описание правила предприятия для панели настроек: что проверяет и как."""
    kind, title = rule.get("kind"), rule.get("title", "")
    pat, where = rule.get("pattern") or "", WHERE.get(rule.get("where") or "tt", "")
    values = rule.get("values") or []
    vals = ", ".join(str(x) for x in values[:12]) + ("…" if len(values) > 12 else "")
    what_l = LIST_WHAT.get(rule.get("what"), "")
    how_pat = "регулярное выражение" if rule.get("match") == "regex" else "фрагмент"
    ref = (" «" + str(rule.get("value")) + "»") if rule.get("check") != "filled" else ""
    how = {
        "text_required": f"В тексте ({where}) ищется {how_pat} «{pat}». Если его нет — замечание.",
        "text_forbidden": f"В тексте ({where}) ищется {how_pat} «{pat}». Если найден — замечание.",
        "field": f"Графа «{FIELDS.get(rule.get('field'), rule.get('field'))}» основной надписи: "
                 f"{FIELD_CHECKS.get(rule.get('check'), '')}{ref}.",
        "allowed": f"Значения ({what_l}) на чертеже сверяются с перечнем: {vals}. Всё, чего нет в перечне, — замечание.",
        "forbidden": f"Значения ({what_l}) на чертеже сверяются с перечнем запрещённых: {vals}. Совпадение — замечание.",
        "limit": f"{LIMIT_WHAT.get(rule.get('what'), '')} {rule.get('value')}: превышение — замечание.",
    }.get(kind, "")
    scope = [APPLIES.get(rule.get("applies") or "all", "")]
    if rule.get("material_contains"):
        scope.append(f"материал содержит «{rule['material_contains']}»")
    if rule.get("designation_prefix"):
        scope.append(f"обозначение начинается с «{rule['designation_prefix']}»")
    if rule.get("when_tt"):
        scope.append(f"в тексте чертежа есть «{rule['when_tt']}»")
    return {"what": title, "how": how, "example": rule.get("message") or "",
            "skip": "Правило применяется к: " + "; ".join(x for x in scope if x) + ".", "params": ""}
