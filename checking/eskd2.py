"""Дополнительные правила по ГОСТ 2.310, 2.311, 2.312, 2.316, 2.403, 9.306, 1139, 1643, 2789, 5264 (коды J01–J34).

Справка с таблицей «пункт стандарта → правило»: docs/norms/ESKD_RULES_2.md. Правила работают по тексту чертежа, ТТ,
таблице параметров зубчатого венца и распознанным обозначениям швов; геометрия (линии выносок, штриховка,
штрихпунктирные утолщённые линии) не анализируется."""
from __future__ import annotations

import re

from .model import Drawing, WARNING, INFO, ERROR, CAT_TT, CAT_VIEW, CAT_HEAT, CAT_GEAR, CAT_WELD, CAT_DIM, CAT_EL, CAT_FILE
from .textnorm import to_float
from .textreq import texts
from .titleblock import excluded

S_2316_44 = "ГОСТ Р 2.316-2023 п. 4.4, приложение А"
S_2316_414 = "ГОСТ Р 2.316-2023 п. 6.9"
S_2316_415 = "ГОСТ Р 2.316-2023 п. 6.9"
S_2316_416 = "ГОСТ Р 2.316-2023 п. 6.11"
S_2316_410 = "ГОСТ Р 2.316-2023 п. 6.3"
S_2316_412 = "ГОСТ Р 2.316-2023 п. 6.5"
S_2316_45 = "ГОСТ Р 2.316-2023 п. 5.2"
S_2316_419 = "ГОСТ Р 2.316-2023 п. 5.11"
S_2316_A = "ГОСТ Р 2.316-2023 приложение А"
S_2403 = "ГОСТ 2.403-75"
S_2403_4 = "ГОСТ 2.403-75 п. 4"
S_2403_6 = "ГОСТ 2.403-75 п. 6"
S_2403_7 = "ГОСТ 2.403-75 п. 7"
S_2403_10 = "ГОСТ 2.403-75 п. 10"
S_2403_3 = "ГОСТ 2.403-75 п. 3"
S_2310_11 = "ГОСТ 2.310-2022 п. 4.1"
S_2310_21 = "ГОСТ 2.310-2022 п. 5.1"
S_2310_25 = "ГОСТ 2.310-2022 п. 4.3, 4.4"
S_2311_10 = "ГОСТ 2.311-68 п. 10"
S_2311_12 = "ГОСТ 2.311-68 п. 12"
S_2312_LEG = "ГОСТ 2.312-72, ГОСТ 5264-80"
S_2312_STEP = "ГОСТ 2.312-72 п. 2.2"
S_9306 = "ГОСТ 9.306-85"
S_1139 = "ГОСТ 1139-80"
S_1643 = "ГОСТ 1643-81"
S_2789 = "ГОСТ 2789-73"

# допускаемые сокращения слов (ГОСТ 2.316 табл. А.1) — первые слова сокращений без точки, в нижнем регистре
ABBR_ALLOWED = set("""бч вед верхн откл взам внутр гл глуб дет дл докум дубл загот зенк изв изм инв инж инстр исполн кл кол
конич констр ко кб конусн конусообр лаб лев лит металл мет метр контр мех наиб наим нар нач н нижн номин обеспеч обраб
отв центр относит отд перв примен плоск поверхн подл подп поз покуп п прав пред прилож примеч пров пп разраб рассч
регистр рук сб ед черт св сеч см спец специф справ станд ст с тв теор техн т толщ точн утв усл давл прох хим цемент ц м
цилиндр шерох шт экз""".split())
ABBR_COMMON = {"др", "пр", "мм", "см", "кг", "мин", "рис", "табл", "мкм", "ном", "макс", "мин", "ср", "об", "ок"}
ABBR_STARRED = re.compile(r"\b(Разраб|Рассч|Утв|Нач|Рук|Констр|Инж|Техн|Мех|Мет|Лаб|Подл|Подп)\.")


def _items(drw: Drawing) -> list:
    return drw.facts.get("_tt_items") or [(t, None, None) for t in drw.tt]


def _short(t: str, n: int = 90) -> str:
    return t if len(t) <= n else t[:n].rstrip() + "…"


def _field_lines(drw: Drawing):
    tt_ids = {id(x) for x in drw.tt_lines}
    return [ln for ln in drw.lines if not excluded(drw, ln) and id(ln) not in tt_ids]


# ------------------------------------------------------------------------------- ГОСТ 2.316 --------
def check_tt_layout(drw: Drawing) -> None:
    # 4.4 сокращения слов — только из перечня приложения А
    for t, pg, bb in _items(drw):
        for m in re.finditer(r"(?<![А-Яа-яЁёA-Za-z./])([А-Яа-яЁё]{2,7})\.(?=\s+[а-яё0-9(])", t):
            w = m.group(1).lower()
            if m.group(1).isupper():
                continue
            if w not in ABBR_ALLOWED and w not in ABBR_COMMON:
                drw.add(INFO, "J01", CAT_TT, f"«{_short(t)}»: сокращение «{m.group(1)}.» не входит в перечень допускаемых "
                        f"сокращений ГОСТ 2.316 (приложение А) — слово пишут полностью", pg, bb, S_2316_44)
                break
        else:
            continue
        break
    for t, pg, bb in _items(drw):
        m = ABBR_STARRED.search(t)
        if m:
            drw.add(INFO, "J09", CAT_TT, f"«{_short(t)}»: сокращение «{m.group(0)}» применяют только в основной надписи "
                    f"(приложение А ГОСТ 2.316, знак «*»)", pg, bb, S_2316_A)
            break

    lines = [(t.strip(), pg, bb) for t, pg, bb in texts(drw)]
    head_tt = next(((t, pg, bb) for t, pg, bb in lines if re.fullmatch(r"(?i)технические\s+требования\s*:?", t)), None)
    head_ch = next(((t, pg, bb) for t, pg, bb in lines if re.fullmatch(r"(?i)техническая\s+характеристика\s*:?", t)), None)
    if head_tt and not head_ch:
        drw.add(WARNING, "J02", CAT_TT, "Заголовок «Технические требования» не пишут (он нужен, только если на чертеже "
                "есть «Техническая характеристика»)", head_tt[1], head_tt[2], S_2316_414)
    if head_ch and not head_tt:
        drw.add(WARNING, "J03", CAT_TT, "Есть заголовок «Техническая характеристика», а над техническими требованиями "
                "заголовка «Технические требования» нет — при технической характеристике оба заголовка обязательны",
                head_ch[1], head_ch[2], S_2316_415)

    tl = list(drw.tt_lines)
    if len(drw.pages) > 1:
        other = [ln for ln in tl if ln.page != drw.first_page and re.match(r"^\d{1,2}[.)]?\s", ln.text.strip())]
        if other:
            ln = other[0]
            drw.add(WARNING, "J04", CAT_TT, f"Технические требования («{_short(ln.text.strip(), 50)}») на листе "
                    f"{ln.page + 1}: на многолистовом чертеже текстовую часть помещают только на первом листе",
                    ln.page, ln.bbox, S_2316_416)
    wide = [ln for ln in tl if ln.bbox[2] - ln.bbox[0] > 185.5]
    if wide:
        ln = wide[0]
        drw.add(WARNING, "J05", CAT_TT, f"Строка технических требований шириной {ln.bbox[2] - ln.bbox[0]:.0f} мм: "
                f"ширина колонки текстовой части — не более 185 мм", ln.page, ln.bbox, S_2316_410)
    rot = [ln for ln in tl if abs(ln.dir[0]) < 0.9]
    if rot:
        ln = rot[0]
        drw.add(WARNING, "J07", CAT_TT, f"Строка «{_short(ln.text.strip(), 50)}» технических требований повёрнута: "
                f"текст располагают параллельно основной надписи", ln.page, ln.bbox, S_2316_45)

    # 4.12 порядок групп требований
    groups = [(0, r"материал|заготовк|термообраб|закал|отпуск|цементир|азотир|HRC|HRA|HB\b|твёрдост|твердост"),
              (1, r"болтов|заклёпоч|заклепоч|сварн|паян|клеен|соединени"),
              (2, r"размер|отклонен|допуск(?!ается|аются|ать)|масс[аы]\b|соосност|биени|радиус"),
              (3, r"зазор|расположени"),
              (4, r"регулир|настро"),
              (5, r"бесшумн|виброустойч|самотормож"),
              (6, r"испытани|испытат"),
              (7, r"поверхност|шероховат|покрыт|отделк|окрас|оксид|кромк|притуп"),
              (8, r"маркир|клейм"),
              (9, r"транспорт|хранени"),
              (10, r"эксплуатац")]
    seq = []
    for t, pg, bb in _items(drw):
        if not re.match(r"^\d{1,2}[.)]?\s", t.strip()) or re.search(r"справок", t) or len(t) > 400:
            continue
        for idx, rx in groups:
            if re.search(rx, t, re.I):
                seq.append((idx, t, pg, bb))
                break
    for a, b in zip(seq, seq[1:]):
        if b[0] < a[0]:
            drw.add(INFO, "J06", CAT_TT, f"Порядок требований: «{_short(b[1], 60)}» стоит после «{_short(a[1], 60)}» — по "
                    f"ГОСТ Р 2.316-2023 п. 6.5 порядок: материал и термообработка, соединения, размеры и отклонения, "
                    f"зазоры, настройка и регулировка, прочие требования к качеству, испытания, поверхности и покрытия, "
                    f"маркирование, транспортирование и хранение, особые условия эксплуатации", b[2], b[3], S_2316_412)
            break


def check_scale_labels(drw: Drawing) -> None:
    rx = re.compile(r"^[А-ЯЁ]\d?(?:\s*[-–—]\s*[А-ЯЁ]\d?)?\s+(?:[МM]\s*)?\d+(?:[.,]\d+)?\s*:\s*\d+(?:[.,]\d+)?$")
    for ln in _field_lines(drw):
        if rx.match(ln.text.strip()):
            drw.add(INFO, "J08", CAT_VIEW, f"Надпись «{ln.text.strip()}»: масштаб изображения указывают в скобках "
                    f"после обозначения — «А-А (2:1)», «Б (5:1)»", ln.page, ln.bbox, S_2316_419)
            break


# ------------------------------------------------------------------------------- ГОСТ 2.403 --------
def check_gear_drawing(drw: Drawing) -> None:
    from .gears import parse_tables, _num
    tables = parse_tables(drw)
    name = (drw.title.name or "")
    if (not tables and re.search(r"(?i)колес[оа]\s+зубчат|зубчат\w+\s+колес|шестерн|венец|зубчат\w+\s+сектор|червяк",
                                 name)
            and not drw.facts.get("is_assembly") and drw.title.found):
        drw.add(WARNING, "J10", CAT_GEAR, f"«{name}»: на чертеже зубчатого колеса, червяка или венца обязательна таблица "
                f"параметров (модуль, число зубьев, исходный контур, смещение, степень точности, данные для контроля)",
                drw.first_page, drw.title.bboxes.get("name"), S_2403_4)
    for t in tables:
        if t["spline"]:
            continue
        p, pg, rows = t["params"], t["page"], t["rows"]
        bb = t["bbox"]
        beta = None
        if p.get("beta"):
            m = re.search(r"\d+(?:[.,]\d+)?", p["beta"]["value"])
            beta = to_float(m.group(0)) if m else None
        if beta:
            dr = next((r for r in rows if re.search(r"(?i)направлен\w*\s+лини\w*\s+зуб", r["label"])), None)
            if dr is None:
                drw.add(WARNING, "J11", CAT_GEAR, "У косозубого колеса в таблице параметров нет строки «Направление линии "
                        "зуба» («Правое», «Левое»; у шевронных — «Шевронное»)", pg, bb, S_2403_6)
            elif not re.search(r"(?i)прав|лев|шевр", dr["value"]):
                drw.add(WARNING, "J11", CAT_GEAR, f"Направление линии зуба «{dr['value']}»: указывают «Правое», «Левое» "
                        f"или «Шевронное»", pg, dr["line"].bbox, S_2403_6)
        if not re.search(r"(?i)общей\s+нормал|постоянн\w*\s+хорд|по\s+хорде|по\s+роликам|шарик|размер\s+по", t["text"]):
            drw.add(WARNING, "J12", CAT_GEAR, "В таблице параметров нет данных для контроля взаимного положения "
                    "разноимённых профилей (длина общей нормали, постоянная хорда, толщина по хорде или размер по "
                    "роликам)", pg, bb, S_2403_7)
        pr = p.get("profile")
        if pr and not re.search(r"(?i)ГОСТ|α|\*|угол профил", pr["value"] + " " + pr["label"] + " " + pr["sym"]):
            drw.add(WARNING, "J13", CAT_GEAR, f"Исходный контур «{pr['value'] or '—'}»: для стандартного контура дают ссылку "
                    f"на стандарт («ГОСТ 13755-2015»), для нестандартного — перечисляют параметры (α, ha*, c*…)",
                    pg, pr["line"].bbox, S_2403_6)
        empty = [r for r in rows if r["label"] and not r["value"].strip() and not r["sym"].strip()
                 and re.match(r"(?i)(?:модуль|число зубьев|угол наклона|направлен|исходный контур|коэффициент|степень точности|"
                              r"делительный диаметр|длина общей|постоянн|толщина по хорде|размер по роликам)", r["label"])]
        if empty:
            drw.add(INFO, "J14", CAT_GEAR, f"Строка «{empty[0]['label'][:50]}» таблицы параметров не заполнена: "
                    f"неиспользуемые строки исключают или прочёркивают", pg, empty[0]["line"].bbox, S_2403_10)
        z = _num(p.get("z"))
        if z is not None and (abs(z - round(z)) > 1e-9 or z < 1):
            drw.add(WARNING, "J15", CAT_GEAR, f"Число зубьев «{p['z']['value']}»: число зубьев — целое положительное",
                    pg, p["z"]["line"].bbox, S_2403_6)
        if not drw.roughness and not re.search(r"(?i)шероховат", " ".join(x for x, _, _ in texts(drw))) and not drw.ocr:
            drw.add(WARNING, "J16", CAT_GEAR, "На чертеже зубчатого колеса не обозначена шероховатость боковых "
                    "поверхностей зубьев", pg, bb, S_2403_3)
        if not any(d.kind == "chamfer" for d in drw.dims) and not re.search(
                r"(?i)фаск|притуп|скруглен|R\s*\d", " ".join(x for x, _, _ in _items(drw))):
            drw.add(INFO, "J17", CAT_GEAR, "На чертеже зубчатого колеса нет размеров фасок или радиусов притупления "
                    "кромок зубьев (допускается в технических требованиях)", pg, bb, S_2403_3)


# ------------------------------------------------------------------------------- ГОСТ 2.310 --------
COAT_DESIG = re.compile(r"(?<![А-Яа-яA-Za-z])(?:Ц|Кд|Хтв|Хч|Ср|Зл)\d{1,3}(?:\.[а-я]{2,4})?(?![А-Яа-яA-Za-z0-9])"
                        r"|(?<![А-Яа-яA-Za-z])(?:Н|Х|М|О)\d{1,3}\.[а-я]{2,4}(?![А-Яа-яA-Za-z0-9])"
                        r"|(?<![А-Яа-я])(?:Хим|Ан)\.\s?[А-Яа-яЁё]")


def check_heat_coat(drw: Drawing) -> None:
    items = _items(drw)
    for t, pg, bb in items:
        if COAT_DESIG.search(t) and not re.search(r"(?i)покрыт", t) and not re.search(r"(?i)ГОСТ\s*9\.306\s*$", t):
            drw.add(WARNING, "J18", CAT_HEAT, f"«{_short(t)}»: данные о покрытии в технических требованиях записывают "
                    f"после слова «Покрытие» («Покрытие Ц6.хр»)", pg, bb, S_2310_11)
            break
    for t, pg, bb in items:
        if re.search(r"(?i)глубин\w*\s+(?:сло\w+|цементац\w*|азотир\w*|закал\w*)\s*[:=]?\s*\d", t) \
                and not re.search(r"(?<![А-Яа-яA-Za-z])h\s*\d", t):
            drw.add(INFO, "J19", CAT_HEAT, f"«{_short(t)}»: глубину обработки обозначают буквой h («h 0,7…0,9»)",
                    pg, bb, S_2310_21)
            break
    hrc = re.compile(r"(?<![A-Za-zА-Яа-я])([НH])([RРrр])([СCАA])(?![A-Za-zА-Яа-я])|(?<![A-Za-zА-Яа-я])([НH])([VУ])(?![A-Za-zА-Яа-я])")
    for t, pg, bb in texts(drw):
        for m in hrc.finditer(t):
            if re.search(r"[А-Яа-я]", m.group(0)):
                drw.add(WARNING, "J20", CAT_HEAT, f"«{_short(t)}»: шкала твёрдости «{m.group(0)}» набрана русскими буквами — "
                        f"обозначения HRC, HRA, HV пишут латиницей", pg, bb, S_2310_21)
                break
        else:
            continue
        break
    for t, pg, bb in items:
        if re.search(r"(?<![A-Za-z])HR[CAB]\s*\d+(?:[.,]\d+)?\s*(?:\.\.\.|…|[-–])\s*\d", t):
            drw.add(INFO, "J22", CAT_HEAT, f"«{_short(t)}»: в ГОСТ 2.310 значение пишут перед шкалой — «40…45 HRC»",
                    pg, bb, S_2310_21)
            break
    # 2.5 «поверхность А» в ТТ — буква обозначена на изображении
    if not drw.ocr:
        marks = {ln.text.strip() for ln in _field_lines(drw)}
        for t, pg, bb in items:
            m = re.search(r"(?i)поверхност\w*\s+([А-ЯЁ])(?![А-Яа-яЁё])", t)
            if m and m.group(1) not in marks and not any(x.strip().startswith(m.group(1) + " ") or x.strip().startswith(m.group(1) + "-") for x in marks):
                drw.add(WARNING, "J21", CAT_HEAT, f"«{_short(t)}»: поверхность «{m.group(1)}» на изображении не "
                        f"обозначена этой буквой", pg, bb, S_2310_25)
                break


# ------------------------------------------------------------------------------- ГОСТ 9.306 --------
def check_coating_notation(drw: Drawing) -> None:
    all_t = texts(drw)
    for t, pg, bb in all_t:
        m = re.search(r"(?<![A-Za-zА-Яа-я])(Zn|Cd|Ni|Cr|Cu|Sn|Ag|Au)\s?\d{1,3}(?:\.[а-яa-z]{2,4})?(?![A-Za-zА-Яа-я0-9])", t)
        if m and re.search(r"(?i)покрыт|\.хр|\.фос|\.окс", t):
            drw.add(WARNING, "J27", CAT_HEAT, f"«{_short(t)}»: обозначение покрытия «{m.group(0)}» записано латинскими "
                    f"буквами — по ГОСТ 9.306 металлы обозначают русскими буквами (Ц, Кд, Н, Х…)", pg, bb, S_9306)
            break
    for t, pg, bb in _items(drw):
        m = re.search(r"(?i)оцинков\w*|никелир\w*|хромир\w*|кадмир\w*|лужен\w*|серебрен\w*|анодир\w*|оксидир\w*|"
                      r"фосфатир\w*|пассивир\w*|хроматир\w*", t)
        if m and not COAT_DESIG.search(t) and not re.search(r"ГОСТ\s*9\.(?:306|032|303)|Хим\.|Ан\.", t):
            drw.add(INFO, "J28", CAT_HEAT, f"«{_short(t)}»: покрытие словом «{m.group(0).lower()}» — по ГОСТ 2.310 и "
                    f"ГОСТ 9.306 его обозначают условным обозначением («Покрытие Ц6.хр»)", pg, bb, S_9306)
            break


# ------------------------------------------------------------------------------- резьба, швы -------
def check_thread_notation(drw: Drawing) -> None:
    for ln in _field_lines(drw):
        t = ln.text.strip()
        if re.search(r"[⌀Ø∅]\s*[МM]\s*\d|(?<![A-Za-zА-Я])[МM]\s*[⌀Ø∅]\s*\d", t):
            drw.add(WARNING, "J24", CAT_DIM, f"«{t}»: обозначение резьбы пишут без знака диаметра («М20×1,5»), оно "
                    f"относится к наружному диаметру резьбы", ln.page, ln.bbox, S_2311_12)
            break
    rx = re.compile(r"(?i)^(?:(?:двух|трех|трёх|много)заходн\w+|лев(?:ая|ое|ый))(?:\s+(?:(?:двух|трех|трёх)заходн\w+|лев(?:ая|ое|ый)))?$")
    for ln in _field_lines(drw) + list(drw.tt_lines):
        if rx.match(ln.text.strip()):
            drw.add(INFO, "J23", CAT_DIM, f"«{ln.text.strip()}»: данные о резьбе (число заходов, левое направление) "
                    f"пишут со словом «Резьба» («Резьба двухзаходная левая»)", ln.page, ln.bbox, S_2311_10)
            break


def check_weld_legs(drw: Drawing) -> None:
    for w in drw.facts.get("welds") or []:
        if w["type"] in ("У", "Т", "Н") and not w["leg_mark"] and w.get("std"):
            drw.add(WARNING, "J25", CAT_WELD, f"Шов «{w['raw']}»: у угловых, тавровых и нахлёсточных соединений в "
                    f"обозначении указывают катет шва (знак ⊿ и размер)", w.get("page"), None, S_2312_LEG)
            break
    for w in drw.facts.get("welds") or []:
        if w["type"] == "С" and w["leg_mark"]:
            drw.add(WARNING, "J26", CAT_WELD, f"Шов «{w['raw']}»: у стыкового соединения катета нет — знак ⊿ ставят у "
                    f"угловых, тавровых и нахлёсточных швов", w.get("page"), None, S_2312_LEG)
            break


def check_weld_pitch(drw: Drawing) -> None:
    for w in drw.facts.get("welds") or []:
        m = re.search(r"(?<![\d,.])(\d+)\s*([/Zz])\s*(\d+)(?![\d,.])", w["raw"])
        if m and int(m.group(3)) <= int(m.group(1)):
            drw.add(WARNING, "J34", CAT_WELD, f"Шов «{w['raw']}»: у прерывистого шва шаг {m.group(3)} не больше длины "
                    f"провариваемого участка {m.group(1)} — шаг должен быть больше длины участка", w.get("page"), None,
                    S_2312_STEP)
            break


# ------------------------------------------------------------------------------- 1139, 1643, 2789 ---
_FIT = r"[A-Za-z]{1,2}\d{1,2}(?:/[a-z]{1,2}\d{1,2})?"
SPL = re.compile(rf"(?<![A-Za-z])(?P<c>[dDb])\s*-\s*(?P<z>\d{{1,2}})\s*[×xхX]\s*(?P<d>\d{{2,3}})(?P<fd>{_FIT})?\s*[×xхX]\s*"
                 rf"(?P<D>\d{{2,3}})(?P<fD>{_FIT})?\s*[×xхX]\s*(?P<b>\d+(?:[.,]\d+)?)(?P<fb>{_FIT})?")


def check_splines_gears(drw: Drawing) -> None:
    all_t = texts(drw)
    joined = " ".join(t for t, _, _ in all_t)
    for t, pg, bb in all_t:
        m = SPL.search(t)
        if not m:
            continue
        if not re.search(r"ГОСТ\s*1139", joined):
            drw.add(WARNING, "J29", CAT_EL, f"Шлицевое соединение «{m.group(0)}»: в обозначении нет ссылки на стандарт "
                    f"(«… ГОСТ 1139-80»)", pg, bb, S_1139)
        fit = {"d": m.group("fd"), "D": m.group("fD"), "b": m.group("fb")}[m.group("c")]
        if not fit:
            drw.add(WARNING, "J30", CAT_EL, f"Шлицевое соединение «{m.group(0)}»: у центрирующего элемента "
                    f"«{m.group('c')}» не указана посадка или поле допуска", pg, bb, S_1139)
        break
    from .gears import parse_tables
    for t in parse_tables(drw):
        pr = t["params"].get("precision")
        if not pr or t["spline"]:
            continue
        v = re.sub(r"(?i)ГОСТ.*", "", pr["value"]).strip()
        if re.fullmatch(r"\d{1,2}(?:\s*-\s*\d{1,2}){0,2}", v):
            drw.add(WARNING, "J31", CAT_GEAR, f"Степень точности «{pr['value']}» указана без вида сопряжения по нормам "
                    f"бокового зазора — «{v}-С», «8-7-6-Da»", t["page"], pr["line"].bbox, S_1643)
        m = re.match(r"^\d{1,2}(?:\s*-\s*\d{1,2}\s*-\s*\d{1,2})?\s*-?\s*[A-Za-zА-Яа-я]([A-Za-zА-Яа-я])\b", v)
        if m and m.group(1).lower() not in "xyzabcdh":
            drw.add(WARNING, "J32", CAT_GEAR, f"Степень точности «{pr['value']}»: вид допуска на боковой зазор "
                    f"«{m.group(1)}» — по ГОСТ 1643 x, y, z, a, b, c, d, h", t["page"], pr["line"].bbox, S_1643)
    for r in drw.roughness:
        if r.get("param") == "Rz" and r.get("value") is not None and r["value"] < 10:
            drw.add(INFO, "J33", CAT_DIM, f"Шероховатость Rz {r['value']:g}: для таких значений по ГОСТ 2789 "
                    f"предпочтителен параметр Ra", r.get("page"), r.get("bbox"), S_2789)
            break


def check_eskd2(drw: Drawing, cfg: dict) -> None:
    for fn in (check_tt_layout, check_scale_labels, check_gear_drawing, check_heat_coat, check_coating_notation,
               check_thread_notation, check_weld_legs, check_weld_pitch, check_splines_gears):
        try:
            fn(drw)
        except Exception as e:                  # одна неудачная проверка не должна ронять остальные
            drw.add(WARNING, "F07", CAT_FILE, f"Проверка «{fn.__name__}» не выполнена: {type(e).__name__}: {e}")
