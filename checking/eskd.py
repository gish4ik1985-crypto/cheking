"""Дополнительные правила по основным стандартам ЕСКД: ГОСТ 2.105, 2.109, 2.201, 2.301, 2.302, 2.305, 2.307, 2.308, 2.309.

Коды Q01–Q40. Справка с таблицей «пункт стандарта → правило»: docs/norms/ESKD_RULES.md. Проверяется только то, что
видно в тексте чертежа, основной надписи и рамках допусков; геометрия (толщины линий, стрелки, штриховка)
не анализируется. Правила, которые часто дают лишние замечания, выключены по умолчанию (см. catalog.RULES)."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from .model import Drawing, WARNING, INFO, CAT_TB, CAT_REFS, CAT_TT, CAT_VIEW, CAT_DIM, CAT_GDT, CAT_ASM
from .normdata import GDT_FORM_ONLY
from .standards import fmtn
from .textnorm import norm_designation, split_designation
from .textreq import texts
from .titleblock import excluded

# ссылки в замечаниях (из них собирается привязка «проверка → стандарт», tools/gen_rule_standards.py)
S_2301_FORMATS = "ГОСТ 2.301-68 п. 4–6"
S_2301_REF = "ГОСТ 2.301-68 п. 5"
S_2302_5 = "ГОСТ 2.302-68 п. 5"
S_2201_21 = "ГОСТ Р 2.201-2023 п. 5.2.2–5.2.5"
S_2201_46 = "ГОСТ Р 2.201-2023 п. 4.6, 5.2.3"
S_2201_16 = "ГОСТ 2.201-80 п. 1.6"
S_2201_25 = "ГОСТ Р 2.201-2023 п. 5.4.5"
S_2201_26 = "ГОСТ 2.201-80 п. 2.6"
S_2201_22 = "ГОСТ 2.201-80 п. 2.2"
S_2109_112 = "ГОСТ Р 2.109-2023 п. 4.9"
S_2109_54 = "ГОСТ Р 2.109-2023 п. 5.4"
S_2109_113 = "ГОСТ Р 2.109-2023 п. 5.2"
S_2109_118 = "ГОСТ Р 2.109-2023 п. 5.12"
S_2109_121 = "ГОСТ Р 2.109-2023 п. 10.1.2"
S_2109_1114 = "ГОСТ Р 2.109-2023 п. 5.14"
S_2109_1112 = "ГОСТ Р 2.109-2023 п. 5.17"
S_2109_24 = "ГОСТ Р 2.109-2023 п. 6.3"
S_2109_323 = "ГОСТ Р 2.109-2023 п. 7.3.3"
S_2109_4 = "ГОСТ Р 2.109-2023 п. 9.1, 9.9"
S_2105_524 = "ГОСТ 2.105-2019 п. 5.2.4"
S_2105_616 = "ГОСТ 2.105-2019 п. 6.16"
S_2305_51 = "ГОСТ 2.305-2008 п. 5.1"
S_2305_66 = "ГОСТ 2.305-2008 п. 6.6, 7.4"
S_2305_LAT = "ГОСТ 2.305-2008 п. 6.6, 7.4, 8.2"
S_2307 = "ГОСТ 2.307-2011"
S_2307_66 = "ГОСТ 2.307-2011 п. 6.6"
S_2308 = "ГОСТ 2.308-2011"
S_2309_15 = "ГОСТ 2.309-73 п. 1.5"
S_2309_26 = "ГОСТ 2.309-73 п. 2.6, 2.7"
S_2309_11 = "ГОСТ 2.309-73 п. 1.1"

FORMAT_BASE = {"А0": (841, 1189), "А1": (594, 841), "А2": (420, 594), "А3": (297, 420), "А4": (210, 297),
               "А5": (148, 210)}
# ГОСТ 2.301 табл. 2: кратности производных форматов
FORMAT_MULT = {"А0": (2, 3), "А1": (3, 4), "А2": (3, 4, 5), "А3": (3, 4, 5, 6, 7), "А4": (3, 4, 5, 6, 7, 8, 9)}


def _tol(side: float) -> float:
    """ГОСТ 2.301 табл. 3: предельные отклонения сторон формата."""
    return 1.5 if side <= 150 else 2.0 if side <= 600 else 3.0


def format_sizes() -> dict[str, tuple[float, float]]:
    """Обозначение формата → (меньшая, большая сторона), мм: основные и производные."""
    out = dict(FORMAT_BASE)
    for name, ks in FORMAT_MULT.items():
        a, b = FORMAT_BASE[name]
        for k in ks:
            out[f"{name}×{k}"] = (b, a * k)
    return out


def _tt_items(drw: Drawing) -> list:
    return drw.facts.get("_tt_items") or [(t, None, None) for t in drw.tt]


def _page_lines(drw: Drawing):
    """Надписи поля чертежа: без основной надписи, таблиц и ТТ (строки ТТ — отдельно)."""
    tt_ids = {id(x) for x in drw.tt_lines}
    return [ln for ln in drw.lines if not excluded(drw, ln) and id(ln) not in tt_ids]


def _short(t: str, n: int = 90) -> str:
    return t if len(t) <= n else t[:n].rstrip() + "…"


# --------------------------------------------------------------------- ГОСТ 2.301, 2.302 --------
def check_formats(drw: Drawing) -> None:
    sizes = format_sizes()
    bad = []
    for p in drw.pages:
        if p.scanned or drw.ocr:
            continue
        a, b = sorted((p.width, p.height))
        if not any(abs(a - s) <= _tol(s) + 0.5 and abs(b - t) <= _tol(t) + 0.5 for s, t in sizes.values()):
            bad.append((p.number, a, b))
    if bad:
        n, a, b = bad[0]
        drw.add(WARNING, "Q01", CAT_TB, f"Размер листа {fmtn(round(a, 1))}×{fmtn(round(b, 1))} мм не соответствует "
                f"ни одному формату ГОСТ 2.301 (А0–А5 и производные по таблице 2, предельные отклонения по таблице 3)"
                f"{f' (лист {n + 1} и ещё {len(bad) - 1})' if len(bad) > 1 else ''}", n, None, S_2301_FORMATS)

    tb = drw.title
    raw = (tb.format or "").strip()
    if not tb.found or not raw:
        return
    t = raw.replace(" ", "")
    m = re.fullmatch(r"([AА])([0-5])(?:[×xXхХ*](\d))?", t)
    if not m:
        drw.add(INFO, "Q02", CAT_TB, f"Обозначение формата «{raw}» в основной надписи не соответствует ГОСТ 2.301: "
                f"А4, А3, производный — «А3×3»", drw.first_page, tb.bboxes.get("format"), S_2301_REF)
        return
    name = "А" + m.group(2)
    if m.group(1) == "A":
        drw.add(INFO, "Q41", CAT_TB, f"Обозначение формата «{raw}» набрано латинской «A» — по ГОСТ 2.301 буква "
                f"русская («{name}»)", drw.first_page, tb.bboxes.get("format"), S_2301_REF)
    elif m.group(3):
        k = int(m.group(3))
        if k not in FORMAT_MULT.get(name, ()):
            drw.add(INFO, "Q02", CAT_TB, f"Формат «{raw}»: кратность {k} для {name} в таблице 2 ГОСТ 2.301 "
                    f"не предусмотрена", drw.first_page, tb.bboxes.get("format"), S_2301_REF)


def check_scale_notation(drw: Drawing) -> None:
    tb = drw.title
    raw = (tb.scale or "").strip()
    if not tb.found or not raw:
        return
    n = re.sub(r"\s+", "", raw)
    m = re.fullmatch(r"[МM]?(\d+(?:[.,]\d+)?)([:/\-–xх×])(\d+(?:[.,]\d+)?)", n)
    if not m:
        return                                     # нераспознанная запись — замечание B06
    problems = []
    if re.search(r"\s", raw):
        problems.append("пробелы вокруг двоеточия")
    if n[0] in "МM":
        problems.append("буква «М» перед масштабом")
    if m.group(2) != ":":
        problems.append(f"разделитель «{m.group(2)}» вместо двоеточия")
    if "." in n:
        problems.append("десятичная точка вместо запятой («2,5:1»)")
    if problems:
        drw.add(INFO, "Q03", CAT_TB, f"Масштаб «{raw}» в основной надписи записан не по типу «1:2» ГОСТ 2.302: "
                f"{', '.join(problems)}", drw.first_page, tb.bboxes.get("scale"), S_2302_5)


# --------------------------------------------------------------------- ГОСТ 2.201 -----------------
_DES_LOOSE = re.compile(r"^(?:[A-Za-zА-Яа-яЁё]{2,6}|\d{8})\.\d{4,7}\.\d{2,}")
_DES_CORE = re.compile(r"(?:[А-Я]{4}|\d{8})\.\d{6}\.\d{3,}")                 # ГОСТ Р 2.201-2023 п. 5.2.2–5.2.5
_LAT_LOOK = set("ABCEHKMOPTXYabcehkmoptxy")


def check_designation(drw: Drawing) -> None:
    """Обозначение в основной надписи проверяется по частям: децимальный номер изделия (Q04), номер исполнения (Q06),
    код документа (Q07); буквы (Q05) — в каждой группе знаков отдельно."""
    tb = drw.title
    des = (tb.designation or "").strip()
    if not tb.found or not des:
        return
    flagged_b12 = any(f.code == "B12" and f.severity == WARNING for f in drw.findings)
    pg, bb = drw.first_page, tb.bboxes.get("designation")
    flat = des.replace(" ", " ")

    # латиница: в коде организации (п. 5.2.3) и смесь латиницы с кириллицей в одной группе знаков (визуальные двойники);
    # прописные латинские буквы в других группах допускаются (п. 4.6)
    org = re.match(r"^([A-Za-zА-Яа-яЁё]+)\.", flat)
    bad = set()
    if org:
        bad |= {ch for ch in org.group(1) if "A" <= ch <= "Z" or "a" <= ch <= "z"}
    for tok in re.findall(r"[A-Za-zА-Яа-яЁё]+", flat):
        lat = {ch for ch in tok if "A" <= ch <= "Z" or "a" <= ch <= "z"}
        if lat and len(lat) < len(tok):
            bad |= lat
    if bad:
        drw.add(WARNING, "Q05", CAT_TB, f"В обозначении «{des}» латинские буквы {', '.join(sorted(bad))} — "
                f"код организации и код документа записывают русскими буквами", pg, bb, S_2201_46)
    if not _DES_LOOSE.match(flat):
        return                                    # другая система обозначений — структуру не проверяем
    norm = norm_designation(flat)
    sd = split_designation(flat)                  # (децимальный номер, исполнение, код документа)
    if (sd is None or not _DES_CORE.fullmatch(sd[0])) and not flagged_b12:
        parts = flat.split(".")
        why = []
        org_l = re.match(r"^([A-Za-zА-Яа-яЁё]+)\.", flat)
        if org_l and len(org_l.group(1)) != 4:
            why.append(f"код организации — {len(org_l.group(1))} букв (должно быть 4)")
        if len(parts) > 1 and not re.fullmatch(r"\d{6}", parts[1]):
            why.append("классификационная характеристика — ровно 6 цифр")
        if len(parts) > 2 and len(re.match(r"\d*", parts[2]).group(0)) < 3:
            why.append("порядковый регистрационный номер — не менее 3 цифр")
        drw.add(WARNING, "Q04", CAT_TB, f"Обозначение «{des}» не соответствует структуре ГОСТ 2.201 "
                f"(ХХХХ.ХХХХХХ.ХХХ[-ХХ]){': ' + '; '.join(why) if why else ''}", pg, bb, S_2201_21)
    ver = sd[1] if sd else ""
    if re.fullmatch(r"-00(?:\.\d+)?", ver) or (sd is None and re.search(r"-00(?!\d)", flat)):
        drw.add(INFO, "Q06", CAT_TB, f"Номер исполнения «-00» в обозначении «{des}»: простую нумерацию исполнений начинают с 01",
                pg, bb, S_2201_25)
    if sd is not None and sd[2]:
        if len(sd[2]) > 4:
            drw.add(WARNING, "Q07", CAT_TB, f"Код документа «{sd[2]}» в обозначении «{des}» длиннее четырёх знаков",
                    pg, bb, S_2201_26)
    elif sd is None and re.search(r"\d{3}\s?[А-Яа-я]{4,}\d*$", flat):
        drw.add(WARNING, "Q07", CAT_TB, f"Код документа в обозначении «{des}» длиннее четырёх знаков "
                f"(включая номер части)", pg, bb, S_2201_26)

    # обозначение на каждом листе
    if len(drw.pages) > 1 and not drw.ocr and norm:
        per_page = defaultdict(list)
        for ln in drw.lines:
            per_page[ln.page].append(ln.text)
        missing = [p.number for p in drw.pages[1:] if per_page.get(p.number)
                   and norm not in norm_designation(" ".join(per_page[p.number]))]
        if missing:
            drw.add(WARNING, "Q08", CAT_TB, f"Обозначение «{des}» не найдено на листе "
                    f"{', '.join(str(n + 1) for n in missing[:6])} — оно должно быть на каждом листе чертежа",
                    missing[0], None, S_2201_16)


# --------------------------------------------------------------------- ГОСТ 2.109 -----------------
_PAR_A = re.compile(r"(?<![А-ЯA-Zа-я])(?:ГОСТ|ОСТ|СТО|ТУ|РД)(?![А-Яа-я])[^;]{0,25}?"
                    r"(?<![А-Яа-я])(?:п\.|пп\.|пункт\w*|подпункт\w*|табл\.|таблиц\w*|рис\.|рисун\w*)\s*\d")
_PAR_B = re.compile(r"(?<![А-Яа-я])(?:п\.|пп\.|пункт\w*|подпункт\w*)\s*\d+(?:\.\d+)*\s*,?\s*"
                    r"(?:ГОСТ|ОСТ|СТО|ТУ|РД)(?![А-Яа-я])")


def check_refs_2109(drw: Drawing) -> None:
    seen = set()
    for t, pg, bb in texts(drw):
        if t in seen:
            continue
        seen.add(t)
        if _PAR_A.search(t) or _PAR_B.search(t):
            drw.add(WARNING, "Q09", CAT_REFS, f"«{_short(t)}»: на чертеже не дают ссылок на отдельные пункты, таблицы и "
                    f"рисунки стандартов и ТУ — ссылаются на весь документ или его раздел", pg, bb, S_2109_112)
            break
    found10 = False
    for t, pg, bb in texts(drw):
        if found10:
            break
        for m in re.finditer(r"(?<![А-Яа-яA-Za-z0-9.\-])(ТУ|ОСТ|СТО)(?![А-Яа-яA-Za-z0-9])", t):
            tail = t[m.end():m.end() + 16]
            head = t[max(0, m.start() - 12):m.start()].lower()
            if re.search(r"\d", tail) or re.search(r"не\s+\w+\s*$|\b(?:ра|та)$", head):
                continue
            if m.group(1) == "ОСТ" and re.match(r"\s*\d", t[m.end():]):
                continue
            drw.add(WARNING, "Q10", CAT_REFS, f"«{_short(t)}»: ссылка «{m.group(1)}» без обозначения документа — "
                    f"при ссылке на ТУ, ОСТ, СТО указывают обозначение (технические условия должны быть зарегистрированы)",
                    pg, bb, S_2109_112)
            found10 = True
            break
    for t, pg, bb in texts(drw):
        m = re.search(r"(фаск\w*|канавк\w*|проточк\w*|выточк\w*)[^.;]{0,30}?\bпо\s+(?:ГОСТ|ОСТ|СТО)", t, re.I)
        if m:
            drw.add(INFO, "Q11", CAT_REFS, f"«{_short(t)}»: на документы, определяющие форму и размеры конструктивных "
                    f"элементов ({m.group(1).lower()}), ссылаться нельзя, если в стандарте нет условного обозначения "
                    f"элемента — все данные приводят на чертеже", pg, bb, S_2109_54)
            break


_TECH = re.compile(r"^(?:\d+[.)]?\s*)?(?:Точить|Обточить|Расточить|Растачивать|Фрезеровать|Строгать|Шлифовать|Сверлить|"
                   r"Рассверлить|Зенковать|Нарезать|Накатать|Штамповать|Отлить|Протянуть|Прошить|Подрезать)\b", re.I)
_TECH_OK = re.compile(r"совместн|по месту|при сборке|в сборе|единственн|вместе с", re.I)


def check_tech_in_tt(drw: Drawing) -> None:
    for t, pg, bb in _tt_items(drw):
        m = _TECH.match(t.strip())
        if m and not _TECH_OK.search(t):
            drw.add(INFO, "Q12", CAT_TT, f"«{_short(t)}»: на рабочих чертежах технологические указания "
                    f"(«{m.group(0).strip(' .)0123456789').lower()}…») не помещают, кроме случаев, когда способ "
                    f"изготовления единственный гарантирует качество изделия", pg, bb, S_2109_113)
            break


_DIM_BR = r"[⌀Ø∅R]?\s*\d+(?:[.,]\d+)?(?:\s*°)?"


def check_brackets(drw: Drawing) -> None:
    tt_text = " ".join(t for t, _, _ in _tt_items(drw)).lower()
    lines = _page_lines(drw)
    rnd = [ln for ln in lines if re.fullmatch(rf"\(\s*{_DIM_BR}[^():]*\)", ln.text.strip())
           and len(ln.text.strip()) <= 22 and not re.fullmatch(r"\(\s*\d{1,3}\s*\)", ln.text.strip())]
    sq = [ln for ln in lines if re.fullmatch(rf"\[\s*{_DIM_BR}[^\[\]]*\]", ln.text.strip())]
    said_round = bool(re.search(r"в\s+(?:круглых\s+)?скобках|после\s+сборки", tt_text))
    said_square = bool(re.search(r"в\s+квадратных\s+скобках|совместн", tt_text))
    if rnd and not said_round:
        ln = rnd[0]
        drw.add(WARNING, "Q13", CAT_TT, f"Размер «{ln.text.strip()}» в круглых скобках: размеры, получающиеся после "
                f"обработки при сборке, заключают в скобки и поясняют в ТТ («Размеры в скобках — после сборки»), "
                f"а такой записи в ТТ нет", ln.page, ln.bbox, S_2109_118)
    elif not rnd and re.search(r"размеры\s+в\s+(?:круглых\s+)?скобках", tt_text) and drw.dims:
        drw.add(INFO, "Q13", CAT_TT, "В ТТ есть запись «Размеры в скобках …», а размеров в круглых скобках на "
                "чертеже не найдено", None, None, S_2109_118)
    if sq and not said_square:
        ln = sq[0]
        drw.add(WARNING, "Q14", CAT_TT, f"Размер «{ln.text.strip()}» в квадратных скобках: такие размеры "
                f"обрабатывают совместно с другим изделием, в ТТ должно быть указание «Обработку по размерам в "
                f"квадратных скобках производить совместно с…»", ln.page, ln.bbox, S_2109_121)
    elif not sq and re.search(r"размерам\s+в\s+квадратных\s+скобках", tt_text) and drw.dims:
        drw.add(INFO, "Q14", CAT_TT, "В ТТ есть указание об обработке по размерам в квадратных скобках, а таких "
                "размеров на чертеже не найдено", None, None, S_2109_121)


def check_edges(drw: Drawing) -> None:
    for t, pg, bb in _tt_items(drw):
        if re.fullmatch(r"(?:\d+[.)]?\s*)?(?:Все\s+)?(?:острые\s+)?кромки\s+притупить\.?|"
                        r"(?:\d+[.)]?\s*)?(?:Все\s+)?острые\s+(?:кромки|углы)\s+притупить\.?", t.strip(), re.I):
            drw.add(INFO, "Q15", CAT_TT, f"«{_short(t)}»: если на чертеже нет указаний о форме кромок, они и так "
                    f"должны быть притуплены — запись без размера притупления не нужна (указывают размер или "
                    f"«острые кромки»)", pg, bb, S_2109_1114)
            break


def check_title_2109(drw: Drawing) -> None:
    tb = drw.title
    if not tb.found:
        return
    if tb.mass_raw and re.search(r"(?i)\bкг\b|\bkg\b", tb.mass_raw):
        drw.add(INFO, "Q16", CAT_TB, f"Масса «{tb.mass_raw}»: в графе 5 массу указывают в килограммах без единицы "
                f"измерения (другие единицы — с обозначением: 0,25 т)", drw.first_page, tb.bboxes.get("mass"),
                S_2109_1112)
    mat = tb.material or ""
    if re.search(r"(?i)(?<![А-Яа-я])или(?![А-Яа-я])|заменител|допускается\s+замен|взамен", mat):
        drw.add(WARNING, "Q17", CAT_TB, f"Материал «{_short(mat)}»: в графе 3 указывают не более одного материала, "
                f"заменители — в технических требованиях", drw.first_page, tb.bboxes.get("material"), S_2109_24)


def check_positions_dir(drw: Drawing) -> None:
    if not drw.facts.get("is_assembly"):
        return
    boxes = {(p["page"], tuple(round(v, 1) for v in p["bbox"])): p["n"] for p in drw.facts.get("positions") or []}
    rotated = []
    for ln in drw.lines:
        n = boxes.get((ln.page, tuple(round(v, 1) for v in ln.bbox)))
        if n is not None and abs(ln.dir[0]) < 0.95:
            rotated.append((n, ln))
    if rotated:
        n, ln = rotated[0]
        drw.add(WARNING, "Q18", CAT_ASM, f"Номер позиции {n} повёрнут: номера позиций располагают параллельно "
                f"основной надписи чертежа{f' (и ещё {len(rotated) - 1})' if len(rotated) > 1 else ''}",
                ln.page, ln.bbox, S_2109_323)


def check_gabarit(drw: Drawing) -> None:
    des = re.sub(r"\s", "", drw.title.designation or "")
    if not re.search(r"ГЧ\d?$", des):
        return
    for t, pg, bb in _tt_items(drw):
        if re.search(r"справ(?:к|ок|очн)", t, re.I):
            drw.add(INFO, "Q19", CAT_TT, f"«{_short(t)}»: на габаритном чертеже не указывают, что все размеры "
                    f"справочные", pg, bb, S_2109_4)
            return
    for t, pg, bb in _tt_items(drw):
        if re.search(r"неуказанн\w+\s+(?:предельн\w+\s+)?отклонен|шероховатост", t, re.I):
            drw.add(INFO, "Q19", CAT_TT, f"«{_short(t)}»: габаритный чертёж не предназначен для изготовления — "
                    f"данных для изготовления (общие допуски, шероховатость) он не содержит", pg, bb, S_2109_4)
            return
    if drw.roughness:
        r = drw.roughness[0]
        drw.add(INFO, "Q19", CAT_TT, "На габаритном чертеже обозначена шероховатость — данных для изготовления "
                "такой чертёж не содержит", r.get("page"), r.get("bbox"), S_2109_4)


# --------------------------------------------------------------------- ГОСТ 2.105 (ТТ) -----------
def check_tt_text(drw: Drawing) -> None:
    for t, pg, bb in _tt_items(drw):
        s = t
        for m in re.finditer(r"(?<![\w)\].,;°%/])[-–−]\s?\d", s):
            before = s[max(0, m.start() - 14):m.start()]
            if re.search(r"[+±]\s?\d+(?:[.,]\d+)?\s*$", before) or re.search(r"[-–−]\s*$", before):
                continue
            drw.add(INFO, "Q20", CAT_TT, f"«{_short(t)}»: перед отрицательным значением в тексте пишут слово «минус», "
                    f"а не знак «{m.group(0)[0]}» («минус 40 °С»)", pg, bb, S_2105_524)
            break
        else:
            continue
        break
    for t, pg, bb in _tt_items(drw):
        m = re.search(r"(?<![\w,.\-])\d+(?:[.,]\d+)?(мм|см|кг|мкм|МПа|кПа|Па|кВт|Вт|Гц|кГц)(?![А-Яа-яA-Za-z])", t)
        if m:
            drw.add(INFO, "Q21", CAT_TT, f"«{_short(t)}»: число и обозначение единицы разделяют пробелом "
                    f"(«{m.group(0)}» → «{m.group(0)[:len(m.group(0)) - len(m.group(1))]} {m.group(1)}»)",
                    pg, bb, S_2105_616)
            break
    for t, pg, bb in _tt_items(drw):
        if re.search(r"[⌀Ø∅]\s*\d", t) and re.search(r"[А-Яа-я]{4,}", t):
            drw.add(INFO, "Q22", CAT_TT, f"«{_short(t)}»: в тексте вместо знака диаметра по ГОСТ 2.105 пишут слово "
                    f"«диаметр» (знак ⌀ — на изображениях, в формулах и таблицах)", pg, bb, S_2105_524)
            break


# --------------------------------------------------------------------- ГОСТ 2.305 -----------------
_MAIN_VIEWS = re.compile(r"^(?:Главный\s+вид|Вид\s+(?:спереди|сверху|слева|справа|снизу|сзади))\.?$", re.I)


def check_view_labels(drw: Drawing) -> None:
    from .views import collect
    lines = _page_lines(drw)
    for ln in lines:
        if _MAIN_VIEWS.match(re.sub(r"\s+", " ", ln.text.strip())):
            drw.add(WARNING, "Q23", CAT_VIEW, f"Надпись «{ln.text.strip()}»: названия основных видов на чертежах "
                    f"не надписывают (направление взгляда задают стрелкой и буквой)", ln.page, ln.bbox, S_2305_51)
            break
    pair = re.compile(r"^([А-ЯЁA-Z])\s*[-–—]\s*([А-ЯЁA-Z])$")
    low = re.compile(r"^[а-яё]\s*[-–—]\s*[а-яё]$")
    for ln in lines:
        t = ln.text.strip()
        m = pair.match(t)
        if low.match(t):
            drw.add(WARNING, "Q24", CAT_VIEW, f"Надпись «{t}»: обозначение разреза или сечения — прописные буквы "
                    f"(«А-А»)", ln.page, ln.bbox, S_2305_66)
            break
        if m and m.group(1) != m.group(2):
            drw.add(WARNING, "Q24", CAT_VIEW, f"Надпись «{t}»: разрез или сечение обозначают двумя одинаковыми "
                    f"буквами через тире («А-А»)", ln.page, ln.bbox, S_2305_66)
            break
    if drw.ocr:
        return
    c = collect(drw)
    seen = []
    for x in c["sections"] + c["views"]:
        ch = x["letter"][0]
        if "A" <= ch <= "Z" and ch not in seen:
            seen.append(ch)
            if len(seen) == 1:
                first = x["line"]
    if seen:
        drw.add(INFO, "Q25", CAT_VIEW, f"В обозначениях видов, разрезов и выносных элементов латинские буквы "
                f"({', '.join(seen)}): по ГОСТ 2.305 применяют прописные буквы русского алфавита",
                first.page, first.bbox, S_2305_LAT)


# --------------------------------------------------------------------- ГОСТ 2.307 -----------------
def check_dim_notation(drw: Drawing) -> None:
    zero_bad = pos_bad = None
    for d in drw.dims:
        if d.upper is None or d.lower is None or d.symmetric:
            continue
        for raw, val, other in ((d.upper_raw, d.upper, d.lower), (d.lower_raw, d.lower, d.upper)):
            if not raw or val is None or raw.startswith("±"):
                continue
            r = raw.replace(" ", "")
            if re.fullmatch(r"[+\-−–]?0(?:[.,]0+)?", r) and other not in (None, 0) and zero_bad is None:
                zero_bad = (d, r)
            if val > 0 and not r.startswith("+") and not re.fullmatch(r"0(?:[.,]0+)?", r) and pos_bad is None:
                pos_bad = (d, r)
    if zero_bad:
        d, r = zero_bad
        drw.add(INFO, "Q26", CAT_DIM, f"Размер «{d.raw}»: предельное отклонение, равное нулю, не указывают (в записи "
                f"«{r}») — пишут только второе отклонение", d.page, d.bbox, S_2307_66)
    if pos_bad:
        d, r = pos_bad
        drw.add(WARNING, "Q27", CAT_DIM, f"Размер «{d.raw}»: положительное отклонение «{r}» записывают со знаком «+»",
                d.page, d.bbox, "ГОСТ 2.307-2011 п. 6.6")

    for t, pg, bb in texts(drw):
        if re.search(r"(?<![\d])\+\s?[/\\]\s?[-–−]\s?\d|\+\s?-\s?\d", t):
            drw.add(WARNING, "Q28", CAT_DIM, f"«{_short(t)}»: симметричные отклонения записывают знаком «±», а не "
                    f"«+/-» или «+-»", pg, bb, "ГОСТ 2.307-2011 п. 6.6")
            break
    for t, pg, bb in texts(drw):
        if re.search(r"\d\s*(?:град(?:\.|ус\w*)?|гр\.?)(?![а-яА-Я])", t):
            drw.add(INFO, "Q29", CAT_DIM, f"«{_short(t)}»: угловые размеры записывают в градусах со знаком «°» "
                    f"(«30°»), а не словом", pg, bb, "ГОСТ 2.307-2011 п. 4.9")
            break
    for t, pg, bb in texts(drw):
        m = re.fullmatch(r"\s*\d+(?:[.,]\d+)?\s*([xXхХ])\s*(?:15|30|45|60)\s*°?\s*", t)
        if m:
            drw.add(INFO, "Q30", CAT_DIM, f"«{t.strip()}»: в размере фаски между числами стоит знак «×» "
                    f"(«1×45°»), а не буква «{m.group(1)}»", pg, bb, "ГОСТ 2.307-2011 п. 5.44")
            break


def check_repeated_dims(drw: Drawing) -> None:
    if drw.facts.get("is_assembly"):
        return
    groups = defaultdict(list)
    for d in drw.dims:
        if d.kind == "linear" and d.nominal and d.nominal >= 10 and d.count is None and not d.reference:
            groups[(d.page, d.raw.strip())].append(d)
    for (pg, raw), ds in groups.items():
        far = [d for d in ds if abs(d.bbox[0] - ds[0].bbox[0]) + abs(d.bbox[1] - ds[0].bbox[1]) > 15]
        if far:
            drw.add(INFO, "Q31", CAT_DIM, f"Размер «{raw}» нанесён на чертеже {len(ds)} раза — размеры одного и того "
                    f"же элемента не повторяют на разных изображениях", pg, ds[0].bbox, "ГОСТ 2.307-2011 п. 4.6")
            break


# --------------------------------------------------------------------- ГОСТ 2.308 -----------------
def check_frames(drw: Drawing) -> None:
    if drw.ocr:
        return
    from .views import collect
    from .views import _norm
    frames = collect(drw)["frames"]
    seen = set()
    for f in frames:
        ln = f["line"]
        key = _norm(ln.text)
        if key in seen:
            continue
        seen.add(key)
        if f["sym"] in GDT_FORM_ONLY and f["bases"]:
            drw.add(WARNING, "Q32", CAT_GDT, f"Рамка «{ln.text.strip()}»: допуски формы (плоскостность, круглость, "
                    f"цилиндричность, прямолинейность) задают без баз", ln.page, ln.bbox, S_2308)
        if f["val"] is not None and f["val"] == 0 and not f["mod"]:
            drw.add(WARNING, "Q33", CAT_GDT, f"Рамка «{ln.text.strip()}»: нулевой допуск задают только с "
                    f"зависимым допуском (Ⓜ или Ⓟ), иначе значение допуска не имеет смысла", ln.page, ln.bbox, S_2308)
        if len(f["bases"]) != len(set(f["bases"])):
            drw.add(WARNING, "Q34", CAT_GDT, f"Рамка «{ln.text.strip()}»: одна и та же база указана в рамке дважды",
                    ln.page, ln.bbox, S_2308)


# --------------------------------------------------------------------- ГОСТ 2.309 -----------------
def check_roughness_notation(drw: Drawing) -> None:
    items = texts(drw)
    for t, pg, bb in items:
        if re.search(r"\bR[az]\d", t):
            drw.add(INFO, "Q35", CAT_DIM, f"«{_short(t.strip())}»: между обозначением параметра и значением ставят "
                    f"пробел («Ra 3,2»)", pg, bb, S_2309_15)
            break
    for t, pg, bb in items:
        if re.search(r"\bR[az]\s*\d+\.\d", t):
            drw.add(WARNING, "Q36", CAT_DIM, f"«{_short(t.strip())}»: дробную часть значения шероховатости "
                    f"отделяют запятой («Ra 3,2»)", pg, bb, S_2309_15)
            break
    for t, pg, bb in items:
        if re.search(r"\bR[az]\s*\d[\d,.]*\s*(?:мкм|μm|µm|um)(?![А-Яа-яA-Za-z])", t):
            drw.add(INFO, "Q37", CAT_DIM, f"«{_short(t.strip())}»: единицы измерения в обозначении шероховатости "
                    f"не указывают", pg, bb, S_2309_15)
            break
    general = [r for r in drw.roughness if r.get("general") and r.get("bbox") and r.get("page") is not None]
    for g in general:
        p = drw.page_info(g["page"])
        if not p:
            continue
        cx, cy = (g["bbox"][0] + g["bbox"][2]) / 2, (g["bbox"][1] + g["bbox"][3]) / 2
        if not (cx > 0.5 * p.width and cy < 0.4 * p.height):
            drw.add(WARNING, "Q38", CAT_DIM, f"Общее обозначение шероховатости «{g.get('raw') or g.get('param')}» "
                    f"помещают в правом верхнем углу чертежа", g["page"], g["bbox"], S_2309_26)
            break
    if not general:
        for t, pg, bb in _tt_items(drw):
            if re.search(r"(?:неуказанн\w+|остальн\w+)\s+(?:поверхност\w+\s+)?шероховатост|"
                         r"шероховатост\w*\s+(?:неуказанн\w+|остальн\w+)", t, re.I) and re.search(r"R[az]\s*\d", t):
                drw.add(INFO, "Q39", CAT_DIM, f"«{_short(t)}»: шероховатость, общую для остальных поверхностей, "
                        f"обозначают знаком в правом верхнем углу чертежа («Ra 6,3 (√)»), а не текстом ТТ",
                        pg, bb, S_2309_26)
                break
    if (not drw.roughness and not drw.facts.get("is_assembly") and not drw.facts.get("sheet_thickness")
            and not drw.ocr and drw.title.found and len(drw.dims) >= 3
            and not any(re.search(r"шероховат", t, re.I) for t, _, _ in _tt_items(drw))):
        from .rules import _graphic_signs
        if not _graphic_signs(drw, []):
            drw.add(INFO, "Q40", CAT_DIM, "На чертеже детали не найдено ни одного обозначения шероховатости — "
                    "шероховатость обозначают для всех поверхностей, выполняемых по чертежу (если она не задана "
                    "требованиями конструкции)", drw.first_page, None, S_2309_11)


def check_eskd(drw: Drawing, cfg: dict) -> None:
    for fn in (check_formats, check_scale_notation, check_designation, check_refs_2109, check_tech_in_tt,
               check_brackets, check_edges, check_title_2109, check_positions_dir, check_gabarit, check_tt_text,
               check_view_labels, check_dim_notation, check_repeated_dims, check_frames,
               check_roughness_notation):
        try:
            fn(drw)
        except Exception as e:                  # одна неудачная проверка не должна ронять остальные
            from .model import CAT_FILE
            drw.add(WARNING, "F07", CAT_FILE, f"Проверка «{fn.__name__}» не выполнена: {type(e).__name__}: {e}")
