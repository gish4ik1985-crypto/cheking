"""Отраслевые стандарты, на которые ссылаются в ТТ. Требования действуют, только если на чертеже есть ссылка.

* ОСТ4 ГО.070.014 «Детали радиоэлектронной аппаратуры. Общие технические условия» (ред. 2-75, изм. 15–19) —
  справка по пунктам: docs/norms/OST4_GO.070.014.md. Правила O01–O02, O05–O18: что сказано в ТТ, материале и
  размерах чертежа не противоречит стандарту (общие допуски, углы, кромки, галтели, резьба, дерево, резина, стекло,
  форма записи ссылки);
* ОСТ 4 ГО.070.015 «Сборочные единицы радиоэлектронной аппаратуры. Общие технические условия» (ред. 2-75) —
  docs/norms/OST4_GO.070.015.md. Правила O03–O04, O19–O32: запись ссылки, повторы общих требований ОСТ в ТТ,
  числовые противоречия (п. 1.6, 2.5, 2.6, 2.8), лак и РД по п. 2.7.

Проверяется только то, что видно на чертеже. Требования к качеству изготовления (дефекты, приёмка, испытания)
по чертежу проверить нельзя — они перечислены в справке как «не проверяется»."""
from __future__ import annotations

import re

from .model import Drawing, WARNING, INFO, CAT_DIM, CAT_TT, CAT_TB
from .textnorm import ref_key, to_float
from .textreq import texts

OST_014 = "ОСТ4 ГО.070.014"
OST_015 = "ОСТ4 ГО.070.015"
_KEY_014 = ref_key(OST_014)
_KEY_015 = ref_key(OST_015)

# ссылки в замечаниях (из них собирается привязка «проверка → стандарт», tools/gen_rule_standards.py)
STD_014_REF = "ОСТ4 ГО.070.014 (запись ссылки)"
STD_014_1_1 = "ОСТ4 ГО.070.014 п. 1.1"
STD_014_1_2 = "ОСТ4 ГО.070.014 п. 1.2"
STD_014_1_4 = "ОСТ4 ГО.070.014 п. 1.4"
STD_014_2_2 = "ОСТ4 ГО.070.014 п. 2.2, 2.3"
STD_014_2_4 = "ОСТ4 ГО.070.014 п. 2.4"
STD_014_2_6 = "ОСТ4 ГО.070.014 п. 2.6"
STD_014_2_7 = "ОСТ4 ГО.070.014 п. 2.7"
STD_014_2_12 = "ОСТ4 ГО.070.014 п. 2.12"
STD_014_2_17 = "ОСТ4 ГО.070.014 п. 2.17"
STD_014_4_1 = "ОСТ4 ГО.070.014 п. 4.1"
STD_014_5_1 = "ОСТ4 ГО.070.014 п. 5.1"
STD_014_5_2 = "ОСТ4 ГО.070.014 п. 5.2"
STD_014_7 = "ОСТ4 ГО.070.014 п. 7"
STD_014_SCOPE = "ОСТ4 ГО.070.014 (область применения)"
STD_015_2_7 = "ОСТ4 ГО.070.015 п. 2.7"
STD_015_SCOPE = "ОСТ4 ГО.070.015 (область применения)"
STD_015_REF = "ОСТ4 ГО.070.015 (запись ссылки)"
STD_015_1_1 = "ОСТ4 ГО.070.015 п. 1.1"
STD_015_1_457 = "ОСТ4 ГО.070.015 п. 1.4, 1.5, 1.7"
STD_015_1_6 = "ОСТ4 ГО.070.015 п. 1.6"
STD_015_1_8 = "ОСТ4 ГО.070.015 п. 1.8"
STD_015_2_23 = "ОСТ4 ГО.070.015 п. 2.2, 2.3"
STD_015_2_5 = "ОСТ4 ГО.070.015 п. 2.5"
STD_015_2_6 = "ОСТ4 ГО.070.015 п. 2.6"
STD_015_2_8 = "ОСТ4 ГО.070.015 п. 2.8"
STD_015_3 = "ОСТ4 ГО.070.015 разд. 3"

OST_THREAD_TOL = {"6g", "6H"}
NUM = r"\d+(?:[.,]\d+)?"
ROLLING = re.compile(r"направлен\w*\s+прокат", re.I)
RIVETING = re.compile(r"клёп|клеп|заклёп|заклеп|развальц|расчекан", re.I)
VARNISH = re.compile(r"лак|АК-?113|107\.9\.4002", re.I)
GENERAL_TOL = re.compile(r"неуказанн|общ\w+\s+допуск|общих\s+допусков", re.I)
LAT_CLASS = str.maketrans("КНЛ", "KHL")                      # кириллица в классе точности ГОСТ 30893.2
WOOD = re.compile(r"фанер|древес|дерев|сосн|\bель\b|\bели\b|пихт|лиственниц|берез|берёз|\bдуб|\bбук\b|ольх|осин|"
                  r"\bлип|клён|клен\b|ясень|хвойн|лиственн", re.I)
RUBBER = re.compile(r"резин|ТМКЩ|7338", re.I)
GLASS = re.compile(r"стекл", re.I)
GLASS_NOT = re.compile(r"органич|стекловолок|стеклотекст|стеклопласт|стеклоткан|стекловат", re.I)


def _refers(drw: Drawing, key: str) -> bool:
    return any(key in ref_key(t) for t, _, _ in texts(drw))


def refers_070_014(drw: Drawing) -> bool:
    return _refers(drw, _KEY_014)


def refers_070_015(drw: Drawing) -> bool:
    return _refers(drw, _KEY_015)


def _nums(s: str) -> list[float]:
    return [v for v in (to_float(x) for x in re.findall(NUM, s)) if v is not None]


def _wood_std(material: str) -> tuple[str, str] | None:
    """(ГОСТ, название) по записи материала из древесины или None, если материал не из древесины."""
    if not WOOD.search(material):
        return None
    if re.search(r"фанер", material, re.I):
        return "3916", "фанера — ГОСТ 3916.1"
    if re.search(r"хвойн|сосн|\bель\b|\bели\b|пихт|лиственниц", material, re.I):
        return "8486", "хвойные породы — ГОСТ 8486"
    return "2695", "лиственные породы — ГОСТ 2695"


def check_ost(drw: Drawing, cfg: dict) -> None:
    items = drw.facts.get("_tt_items") or [(t, None, None) for t in drw.tt]
    if refers_070_014(drw):
        _check_014(drw, items)
    if refers_070_015(drw):
        _check_015(drw, items)


def _check_014(drw: Drawing, items: list) -> None:
    is_asm = bool(drw.facts.get("is_assembly"))
    material = (drw.title.material or "").strip()
    mpg, mbb = drw.first_page, drw.title.bboxes.get("material")
    if is_asm:
        drw.add(INFO, "O15", CAT_TT, f"Ссылка на {OST_014} на сборочном чертеже: стандарт распространяется на детали "
                f"(для сборочных единиц — {OST_015})", None, None, STD_014_SCOPE)

    # --- запись ссылки (титульная часть стандарта)
    for t, pg, bb in items:
        if _KEY_014 not in ref_key(t):
            continue
        if len(items) > 1 and not re.search(r"остальн", t, re.I):
            drw.add(INFO, "O16", CAT_TT, f"«{t[:90]}»: при наличии других требований ссылку записывают так: "
                    f"«Остальные технические требования — по {OST_014}»", pg, bb, STD_014_REF)
        if re.search(r"070\.014\W{0,12}(?:ред\w*\.?\s*)?1\s*[-–]\s*70|070\.014\W{0,12}ред\w*\.?\s*1\b", t, re.I):
            drw.add(WARNING, "O17", CAT_TT, f"«{t[:90]}»: редакция 1-70 заменена — действует редакция 2-75 "
                    f"(изм. 15–19)", pg, bb, STD_014_REF)
        break

    # --- 1.1 общие допуски формы и расположения — ГОСТ 30893.2, класс К
    for t, pg, bb in items:
        for m in re.finditer(r"30893\.2[^\dА-Яа-яA-Za-z]{0,12}(?:[-–—]\s*)?([KkHhLlКкНнЛл])(?![A-Za-zА-Яа-я])", t):
            cls = m.group(1).upper().translate(LAT_CLASS)
            if cls != "K":
                drw.add(WARNING, "O05", CAT_TT, f"«{t[:90]}»: класс общих допусков формы и расположения {cls} — "
                        f"{OST_014} устанавливает класс К", pg, bb, STD_014_1_1)
                break

    # --- 1.2 общие допуски линейных размеров: H14, h14, ±IT14/2
    for t, pg, bb in items:
        if not GENERAL_TOL.search(t):
            continue
        grades = {int(g) for g in re.findall(r"(?<![A-Za-z])(?:[Hh]|IT|js|JS)\s*(\d{1,2})(?!\d)", t)}
        bad = sorted(g for g in grades if g != 14)
        cls = re.search(r"30893\.1\s*[-–—]\s*([fcv])(?![A-Za-z])", t)
        if bad or cls:
            what = f"квалитет {', '.join('IT' + str(g) for g in bad)}" if bad else f"класс {cls.group(1)}"
            drw.add(WARNING, "O06", CAT_TT, f"«{t[:90]}»: неуказанные отклонения — {what}; {OST_014} п. 1.2: "
                    f"H14, h14, ±IT14/2 (ГОСТ 30893.1)", pg, bb, STD_014_1_2)
            break

    # --- 1.4 неуказанные отклонения углов: ±AT16/2
    for t, pg, bb in items:
        m = re.search(r"[AА][TТ]\s*(\d{1,2})(?!\d)", t)
        if m and int(m.group(1)) != 16:
            drw.add(WARNING, "O07", CAT_TT, f"«{t[:90]}»: неуказанные отклонения углов AT{m.group(1)}; "
                    f"{OST_014} п. 1.4 — ±AT16/2 (ГОСТ 8908) и ГОСТ 30893.1-m", pg, bb, STD_014_1_4)
            break

    # --- 2.2, 2.3 угловое положение отверстий: не более ±3° (штифтовые) и ±2° (по окружности)
    for t, pg, bb in items:
        if re.search(r"угл\w*", t, re.I) and re.search(r"отверст", t, re.I):
            vals = [to_float(x) for x in re.findall(rf"±\s*({NUM})\s*°", t)]
            if any(v is not None and v > 3 for v in vals):
                drw.add(WARNING, "O18", CAT_TT, f"«{t[:90]}»: угловое положение отверстий допущено грубее ±3° — "
                        f"по {OST_014} не более ±3° (штифтовые, установочные винты) и ±2° (по окружности)",
                        pg, bb, STD_014_2_2)
                break

    # --- 2.4 притупление острых кромок: радиус не более 0,3 мм или фаска 0,3×45°
    for t, pg, bb in items:
        if not re.search(r"притуп", t, re.I):
            continue
        vals = []
        for m in re.finditer(rf"(?:\bR|радиус\w*|фаск\w*)\s*(?:не\s+более\s+|до\s+)?({NUM})(?:\s*(?:\.\.\.|…|[-–])\s*({NUM}))?", t, re.I):
            vals += [to_float(g) for g in m.groups() if g]
        vals += [to_float(x) for x in re.findall(rf"({NUM})\s*[×xх]\s*45", t)]
        vals = [v for v in vals if v is not None]
        if vals and max(vals) > 0.3 + 1e-9:
            drw.add(INFO, "O08", CAT_TT, f"«{t[:90]}»: притупление кромок до {max(vals):g} мм; по {OST_014} п. 2.4 "
                    f"радиус притупления не более 0,3 мм (или фаска 0,3×45°)", pg, bb, STD_014_2_4)
            break

    # --- 2.6 радиусы галтелей не более 0,5 мм
    for t, pg, bb in items:
        if re.search(r"галтел", t, re.I):
            vals = [v for v in (to_float(x) for x in re.findall(rf"\bR\s*({NUM})", t)) if v is not None]
            if not vals:
                vals = [v for v in _nums(re.sub(r"(?i).*галтел\w*", "", t, count=1)) if v < 100]
            if vals and max(vals) > 0.5 + 1e-9:
                drw.add(INFO, "O09", CAT_TT, f"«{t[:90]}»: радиус галтелей {max(vals):g} мм; по {OST_014} п. 2.6 "
                        f"радиусы галтелей не более 0,5 мм", pg, bb, STD_014_2_6)
                break

    # --- 2.7 направление проката на чертеже детали не указывают
    if not is_asm:
        for t, pg, bb in items:
            if ROLLING.search(t):
                drw.add(INFO, "O02", CAT_TT, f"«{t[:90]}»: на чертежах деталей из проката направление проката "
                        f"не указывают", pg, bb, STD_014_2_7)
                break

    # --- 2.12 шероховатость профиля резьбы не более Rz40
    for t, pg, bb in items:
        if not re.search(r"резьб", t, re.I):
            continue
        for m in re.finditer(rf"\b(Rz|Ra)\s*({NUM})", t):
            v = to_float(m.group(2))
            if v is not None and (m.group(1) == "Rz" and v > 40 or m.group(1) == "Ra" and v > 6.3):
                drw.add(INFO, "O10", CAT_TT, f"«{t[:90]}»: шероховатость резьбы {m.group(1)} {v:g}; по {OST_014} "
                        f"п. 2.12 — не грубее Rz40", pg, bb, STD_014_2_12)
                break
        else:
            continue
        break

    # --- 2.17 допуски резьбы 6g (наружная) и 6H (внутренняя)
    seen = set()
    for d in drw.dims:
        tol = (d.thread_tol or "").replace(" ", "")
        if d.kind == "thread" and tol and tol not in OST_THREAD_TOL and tol not in seen:
            seen.add(tol)
            drw.add(WARNING, "O01", CAT_DIM, f"Резьба «{d.raw}» с допуском {tol}: по {OST_014} резьбу выполняют "
                    f"с допусками 6g (наружная) и 6H (внутренняя) — или оговорите допуск отдельно",
                    d.page, d.bbox, STD_014_2_17)

    # --- 4.1 резина: допуски по ТУ 2500-376-00152106-94
    all_text = " ".join(t for t, _, _ in texts(drw))
    if RUBBER.search(material) and "2500-376" not in all_text.replace(" ", ""):
        gen = next(((t, pg, bb) for t, pg, bb in items if GENERAL_TOL.search(t) or re.search(r"30893|H14|IT14", t)), None)
        if gen:
            drw.add(INFO, "O13", CAT_TT, f"Деталь из резины ({material[:40]}): по {OST_014} п. 4.1 допуски на изделия "
                    f"из резины — по ТУ 2500-376-00152106-94, а в ТТ их нет", gen[1], gen[2], STD_014_4_1)

    # --- 5.1, 5.2 древесина: стандарты на материал и неуказанные отклонения ±IT16/2 (ГОСТ 6449.5)
    wood = _wood_std(material)
    if wood:
        need, label = wood
        stds = re.findall(r"ГОСТ\s*(\d[\d.]*)", material)
        if not any(s.startswith(need) for s in stds):
            drw.add(WARNING, "O11", CAT_TB, f"Материал из древесины «{material[:50]}»: по {OST_014} п. 5.1 изделия "
                    f"должны соответствовать стандарту ({label}), в записи материала его нет", mpg, mbb, STD_014_5_1)
        for t, pg, bb in items:
            if GENERAL_TOL.search(t) and (re.search(r"30893|[Hh]\s*14|IT\s*14", t)):
                drw.add(WARNING, "O12", CAT_TT, f"«{t[:90]}»: деталь из древесины — неуказанные отклонения по "
                        f"{OST_014} п. 5.2: ±IT16/2 (ГОСТ 6449.5)", pg, bb, STD_014_5_2)
                break

    # --- 7 стекло: острые кромки притуплены радиусом или фаской 0,2–0,5 мм
    if GLASS.search(material) and not GLASS_NOT.search(material):
        for t, pg, bb in items:
            if re.search(r"кромк", t, re.I) and re.search(r"притуп|радиус|фаск|\bR\s*\d", t, re.I):
                vals = [v for v in (to_float(x) for x in re.findall(rf"(?:\bR|радиус\w*|фаск\w*)\s*({NUM})", t, re.I)) if v is not None]
                vals += [v for v in (to_float(x) for x in re.findall(rf"({NUM})\s*[×xх]\s*45", t)) if v is not None]
                if vals and (min(vals) < 0.2 - 1e-9 or max(vals) > 0.5 + 1e-9):
                    drw.add(WARNING, "O14", CAT_TT, f"«{t[:90]}»: кромки стеклянной детали — по {OST_014} разд. 7 "
                            f"притупляют радиусом или фаской 0,2–0,5 мм (45°)", pg, bb, STD_014_7)
                    break


def _first(items, rx, flags=re.I):
    """Первый пункт ТТ, где есть совпадение: (текст, страница, рамка, match) или None."""
    for t, pg, bb in items:
        m = re.search(rx, t, flags)
        if m:
            return t, pg, bb, m
    return None


def _num_after(t: str, m, unit: str = r"мм") -> float | None:
    """Число с единицей мм после слова в пункте ТТ (в пределах 50 знаков)."""
    mm = re.search(rf"({NUM})\s*{unit}", t[m.end():m.end() + 70])
    return to_float(mm.group(1)) if mm else None


def _check_015(drw: Drawing, items: list) -> None:
    if not drw.facts.get("is_assembly"):
        drw.add(INFO, "O04", CAT_TT, f"Ссылка на {OST_015} на чертеже детали: стандарт распространяется на "
                f"сборочные единицы (для деталей — {OST_014})", None, None, STD_015_SCOPE)
    tt = [(t, pg, bb) for t, pg, bb in items if RIVETING.search(t)]
    if tt and not any(VARNISH.search(t) for t, _, _ in items):
        t, pg, bb = tt[0]
        drw.add(INFO, "O03", CAT_TT, f"«{t[:90]}»: места клепки, развальцовки и расчеканки покрывают бесцветным "
                f"лаком (АК-113 и др.) по РД 107.9.4002 — в ТТ лак не указан", pg, bb, STD_015_2_7)

    _check_015_text(drw, items)


MACHINING = re.compile(r"сверл|развер[нт]|фрез|обраб[оа]т|шлиф|точить|зенков|нарез\w+\s+резьб|подгон|пригон", re.I)
AT_ASSEMBLY = re.compile(r"при\s+сборке|по\s+месту|совместно|по\s+(?:дет|сопряга)", re.I)


def _check_015_text(drw: Drawing, items: list) -> None:
    """Пункты ТТ сборочной единицы со ссылкой на ОСТ 015: запись ссылки, повторы и противоречия стандарту."""
    # --- запись ссылки и редакция (титульная часть)
    for t, pg, bb in items:
        if _KEY_015 not in ref_key(t):
            continue
        if len(items) > 1 and not re.search(r"остальн", t, re.I):
            drw.add(INFO, "O19", CAT_TT, f"«{t[:90]}»: при наличии других требований ссылку записывают так: "
                    f"«Остальные технические требования — по {OST_015}»", pg, bb, STD_015_REF)
        if re.search(r"07[0О]\.015\W{0,12}(?:ред\w*\.?\s*)?1\s*[-–]\s*70|07[0О]\.015\W{0,12}ред\w*\.?\s*1\b", t, re.I):
            drw.add(WARNING, "O20", CAT_TT, f"«{t[:90]}»: редакция 1-70 заменена — действует редакция 2-75 "
                    f"(изм. 3–5)", pg, bb, STD_015_REF)
        break

    # --- 1.1 механическая обработка при сборке — по ОСТ 014
    if not refers_070_014(drw):
        for t, pg, bb in items:
            if AT_ASSEMBLY.search(t) and MACHINING.search(t):
                drw.add(INFO, "O21", CAT_TT, f"«{t[:90]}»: механическую обработку при сборке и детали без чертежа "
                        f"выполняют по {OST_014}, а ссылки на него в ТТ нет", pg, bb, STD_015_1_1)
                break

    # --- общие требования стандарта, которые не нужно повторять в ТТ
    for code, rx, what, std in (
            ("O22", r"расконсерв|промыт\w*\s+(?:и\s+)?(?:очищ|обезжир)|очищен\w*\s+и\s+промыт|механическ\w+\s+повреждени|"
                    r"стружк\w*|опилк\w*|\bворс", "очистка деталей и сохранность при сборке (п. 1.4, 1.5, 1.7)", STD_015_1_457),
            ("O23", r"затян\w+\s+(?:плотно|равномерно)|(?:шлиц\w*|грани\s+головок)[^.;]{0,40}(?:сорван|смят)",
             "затяжка крепёжных соединений, сохранность шлицев и граней (п. 2.2, 2.3)", STD_015_2_23),
            ("O24", r"\bплавно\b|без\s+заедан|свободно\s+(?:вращ|перемещ|откид|выдвиг|проворач)|"
                    r"не\s+проворачива|чётко\s+фиксир|четко\s+фиксир|не\s+качаются", "плавность и фиксация подвижных "
             "соединений (п. 3.1–3.7)", STD_015_3),
            ("O25", r"прокладк\w*[^.;]{0,60}(?:плотно|трещин|складк|выровнен)", "посадка и состояние прокладок (п. 1.8)",
             STD_015_1_8)):
        hit = _first(items, rx)
        if hit:
            t, pg, bb, _ = hit
            drw.add(INFO, code, CAT_TT, f"«{t[:90]}»: {what} — это требование уже содержится в {OST_015}; в ТТ его "
                    f"повторять не нужно (оно действует при ссылке на ОСТ)", pg, bb, std)

    # --- противоречия числовым требованиям
    hit = _first(items, r"вмятин\w*")
    if hit:
        t, pg, bb, m = hit
        v = _num_after(t, m)
        if v is not None and v > 0.2 + 1e-9:
            drw.add(WARNING, "O26", CAT_TT, f"«{t[:90]}»: вмятины вокруг заклёпочных головок допущены {v:g} мм; по "
                    f"{OST_015} п. 2.5 — не глубже 0,2 мм", pg, bb, STD_015_2_5)
    hit = _first(items, r"радиальн\w+\s+разрыв\w*|разрыв\w*[^.;]{0,30}(?:развальц|втулк|заклёп|заклеп)")
    if hit:
        t, pg, bb, _ = hit
        nums = [int(x) for x in re.findall(r"(?:не\s+более|до)\s+(\d+)", t)] + [int(x) for x in re.findall(r"(\d+)\s+радиальн", t)]
        if nums and max(nums) > 2:
            drw.add(WARNING, "O27", CAT_TT, f"«{t[:90]}»: допущено разрывов {max(nums)}; по {OST_015} п. 2.6 у "
                    f"развальцовываемых деталей не более двух радиальных разрывов", pg, bb, STD_015_2_6)
    hit = _first(items, r"осветл\w*")
    if hit:
        t, pg, bb, m = hit
        v = _num_after(t, m)
        if v is not None and v > 1 + 1e-9:
            drw.add(WARNING, "O28", CAT_TT, f"«{t[:90]}»: осветлённые участки допущены до {v:g} мм; по {OST_015} "
                    f"п. 2.8 на деталях из изоляционных материалов — не более 1 мм", pg, bb, STD_015_2_8)
    hit = _first(items, r"допуска\w*[^.;]{0,60}(?:нарушени|повреждени|царапин|облез|отслоени)[^.;]{0,40}покрыт|"
                         r"покрыт\w*[^.;]{0,40}(?:допуска\w*|не\s+контролир)[^.;]{0,20}(?:нарушени|повреждени|царапин)")
    if hit:
        t, pg, bb, _ = hit
        drw.add(WARNING, "O29", CAT_TT, f"«{t[:90]}»: допущено нарушение покрытий; по {OST_015} п. 1.6 нарушение "
                f"антикоррозионных и декоративных покрытий не допускается (частично — только плёнок на местах "
                f"приложения инструмента и на трущихся поверхностях)", pg, bb, STD_015_1_6)

    # --- 2.7 места клёпки покрывают бесцветным лаком, а не краской
    for t, pg, bb in items:
        if RIVETING.search(t) and re.search(r"эмал|краск|окраси|покраси", t, re.I) and not re.search(r"лак|АК-?113", t, re.I):
            drw.add(WARNING, "O30", CAT_TT, f"«{t[:90]}»: места клёпки, развальцовки и расчеканки покрывают "
                    f"бесцветным лаком (АК-113), а не эмалью или краской", pg, bb, STD_015_2_7)
            break
    for t, pg, bb in items:
        m = re.search(r"107\.9\.4002\s*[-–]\s*(\d{2,4})", t)
        if m and m.group(1) not in ("88", "1988"):
            drw.add(INFO, "O31", CAT_TT, f"«{t[:90]}»: РД 107.9.4002 введён в 1988 г. (РД 107.9.4002-88) — "
                    f"год «{m.group(1)}» не соответствует", pg, bb, STD_015_2_7)
            break
    for t, pg, bb in items:
        m = re.search(r"(?<![А-Яа-я])(?:AK|АК\s)\s*-?\s*113|\bAK-113|\bАК113", t)
        if m:
            drw.add(INFO, "O32", CAT_TT, f"«{t[:90]}»: марка лака записывается «АК-113» (русские буквы, дефис)",
                    pg, bb, STD_015_2_7)
            break
