"""Классификатор ЕСКД (K1xx): код классификационной характеристики в обозначении изделия («ЮМЛТ.741211.022» → 741211).

Блок «Классификатор ЕСКД» выключен по умолчанию и включается целиком в настройках (модуль cls). Код сверяется с чертежом:
что код говорит о детали (отверстия, резьба, пазы, форма, заготовка) и что видно на чертеже. Расхождения выдаются предупреждениями
и собираются в таблицу «Код и чертёж» на вкладке «Классификатор» отчёта (drw.facts["classifier"])."""
from __future__ import annotations

import re

from . import classifier
from .model import Drawing
from .pack import R, emit
from .textnorm import split_designation

SRC = "Классификатор ЕСКД 1.79.100"
ROTATION = ("71", "72")                  # тела вращения: диаметры на чертеже — размеры самой детали, а не отверстий
NOT_ROTATION = ("73", "74")
PARTS = ("71", "72", "73", "74", "75", "76")

R("K101", "classifier", "Код классификации есть в классификаторе ЕСКД", SRC,
  "Что шесть цифр обозначения («741211» в «ЮМЛТ.741211.022») есть в классификаторе: класс, подкласс, группа, подгруппа и вид существуют. "
  "Код с нулями в конце («713000») допустим: нули означают, что нижние уровни не указаны.",
  "Код или его начало (класс, подкласс…) в классификаторе не найдены.",
  "«Код 741219 не найден в классификаторе ЕСКД: есть 74121 «С контуром выпуклым…», вида 9 в нём нет».",
  "Только обозначения вида «КОД.ХХХХХХ.ХХХ»; другие системы обозначений и сканы без обозначения не проверяются.", sev="warning")
R("K102", "classifier", "Расшифровка кода классификации (справочно, не ошибка)", SRC,
  "Показывает, как классификатор называет код из обозначения: подгруппа › вид и выше. Не замечание, а справка, чтобы конструктор или "
  "проверяющий сразу видел, что за деталь заложена кодом. Подробная сверка с чертежом — на вкладке «Классификатор» отчёта.",
  "Код найден в классификаторе — в отчёт добавляется строка с расшифровкой.",
  "«Справочно, не ошибка: код классификации 741211 — С параллельными основными плоскостями… › С контуром выпуклым… › Без отв.».",
  "Не выдаётся, если код не найден (тогда K101).", sev="info")
R("K103", "classifier", "Отверстия: код классификации и чертёж", SRC,
  "Что код и чертёж согласованы по отверстиям. Код «без отв.» при записи «4 отв. ⌀10» на чертеже — расхождение кода и детали; "
  "код «с отв.» без отверстий на чертеже — тоже. Центральные отверстия тел вращения не сверяются.",
  "Классификатор говорит об отверстиях вне оси (или о плоской детали с/без отверстий), а на чертеже обратное.",
  "«Код 741211 — «без отверстий», а на чертеже «4 отв. ⌀10»: исправьте код или чертёж».",
  "Только детали классов 71–76.", sev="warning")
R("K104", "classifier", "Резьба: код классификации и чертёж", SRC,
  "Что код и чертёж согласованы по резьбе: код «с резьбой» при отсутствии резьбовых размеров и слова «резьба» на чертеже, "
  "либо «без резьбы» при наличии резьбы.",
  "В названии кода есть признак «с резьбой» / «без резьбы», а на чертеже наоборот.",
  "«Код 715162 — «с резьбой», но резьбы на чертеже не найдено».",
  "Только детали классов 71–76. Резьба наружная и внутренняя не различаются.", sev="warning")
R("K105", "classifier", "Пазы и шлицы: код классификации и чертёж", SRC,
  "Что код и чертёж согласованы по пазам и шлицам: код «с пазами и/или шлицами» при отсутствии на чертеже слов «паз», «шлиц», «шпоноч», "
  "либо «без пазов» при их наличии. Кольцевые пазы на торцах не сверяются.",
  "В названии кода есть признак «с пазами» / «без пазов», а на чертеже наоборот.",
  "«Код 741514 — «с пазами», но пазов и шлицев на чертеже не найдено».",
  "Только детали классов 71–76. Ищутся слова в тексте чертежа, геометрия не анализируется.", sev="warning")
R("K106", "classifier", "Форма: тело вращения или нет", SRC,
  "Что код и чертёж согласованы по форме: классы 71 и 72 — тела вращения, на чертеже должны быть диаметры (⌀). "
  "Код тела вращения при отсутствии ⌀ на чертеже — расхождение. Обратное (диаметры на «не теле вращения») не проверяется: это могут быть отверстия.",
  "Класс 71 или 72, а размеров ⌀ на чертеже нет.",
  "«Код 715122 — тело вращения (класс 71), но размеров ⌀ на чертеже нет».",
  "Только детали классов 71 и 72.", sev="warning")
R("K107", "classifier", "Заготовка: сортамент в графе 3 и код", SRC,
  "Что сортамент в графе 3 («Швеллер», «Двутавр», «Уголок», «Труба») согласуется с кодом: профильные детали и трубы имеют соответствующие "
  "группы классификатора. Деталь из швеллера с кодом «не профильные» или, наоборот, профильный код у детали из листа — расхождение.",
  "Сортамент профиля или трубы не совпадает с названием кода, либо код профильный, а сортамент — лист или круг.",
  "«Код 746211 — профильный, а в графе 3 «Лист»: проверьте сортамент или код».",
  "Только детали классов 73–76 с распознанным материалом.", sev="warning")

PROFILE_WORDS = ("швеллер", "двутавр", "уголок", "труба", "балка")
PLATE_WORDS = ("лист", "круг", "полоса", "квадрат", "пруток", "лента")


def _code(drw: Drawing) -> str | None:
    sd = split_designation(drw.title.designation or "")
    if not sd:
        return None
    parts = sd[0].split(".")
    return parts[1] if len(parts) >= 3 and re.fullmatch(r"\d{6}", parts[1]) else None


def _prefix(code: str) -> str:
    """Код без нулей в конце: «713000» → «713» (нули — «не указано»)."""
    return code.rstrip("0") if len(code.rstrip("0")) >= 2 else code[:2]


def _text(drw: Drawing) -> str:
    return " ".join([ln.text for ln in drw.lines] + list(drw.tt) + [d.raw for d in drw.dims]).lower()


def _yn(v: bool | None, yes: str, no: str) -> str:
    return "не указано" if v is None else (yes if v else no)


def check_classifier(drw: Drawing) -> None:
    if not classifier.available() or not drw.title.found:
        return
    code = _code(drw)
    if not code:
        return
    pg, bb = drw.first_page, drw.title.bboxes.get("designation")
    pre = _prefix(code)
    if code not in classifier.data()["codes"] and pre not in classifier.data()["codes"]:
        ch = classifier.chain(code)
        tail = f": есть {ch[-1][0]} «{ch[-1][1][:70]}», дальше кода нет" if ch else ": такого класса нет"
        emit(drw, "K101", f"Код классификации {code} не найден в классификаторе ЕСКД{tail}", pg, bb)
        return
    names = classifier.chain(pre if pre != code and code not in classifier.data()["codes"] else code)
    tail3 = [n for _c, n in names][-3:]                   # три нижних уровня; полный путь — в справочнике
    emit(drw, "K102", f"Справочно, не ошибка: код классификации {code} — {' › '.join(tail3)}", pg, bb)
    rows: list[dict] = []
    drw.facts["classifier"] = {"code": code, "path": [{"code": c, "name": n} for c, n in names], "rows": rows}
    if code[:2] not in PARTS or drw.facts.get("is_assembly"):
        return
    feats = classifier.features(code)
    full = _text(drw)

    def row(attr: str, says: str, sees: str, status: str, rule: str | None = None, msg: str | None = None) -> None:
        rows.append({"attr": attr, "code_says": says, "drawing_shows": sees, "status": status})   # ok | diff | unknown
        if status == "diff" and rule and msg:
            emit(drw, rule, msg, pg, bb)

    # отверстия
    holes_text = re.findall(r"\d+\s*отв\.?|\bотв\.", full)
    centre_only = bool(re.search(r"центр\w*\.?\s*отв", full)) and len(holes_text) <= 1
    thread_dims = [d for d in drw.dims if d.kind == "thread"]
    diameters = [d for d in drw.dims if d.kind == "diameter"]
    has_holes = bool(holes_text) and not centre_only
    sample = next((d.raw.strip() for d in drw.dims if d.count and "отв" in d.raw.lower()), holes_text[0].strip() if holes_text else "")
    says = _yn(feats["holes"], "есть отверстия", "без отверстий")
    if feats["holes"] is False and has_holes:
        row("Отверстия", says, f"есть: «{sample}»", "diff", "K103", f"Код {code} — «без отверстий», а на чертеже «{sample}»: исправьте код или чертёж")
    elif feats["holes"] is True and not has_holes and not thread_dims and (code[:2] in ROTATION or not diameters):
        row("Отверстия", says, "не найдено", "diff", "K103", f"Код {code} — «с отверстиями», но отверстий на чертеже не найдено")
    elif feats["holes"] is None:
        row("Отверстия", says, f"есть: «{sample}»" if has_holes else "не найдено", "unknown")
    else:
        row("Отверстия", says, f"есть: «{sample}»" if has_holes else ("есть ⌀" if diameters else "не найдено"), "ok")

    # резьба
    has_thread = bool(thread_dims) or bool(re.search(r"резьб|(?<![а-яa-z])м\d{1,3}(?:\s*[×x]\s*\d)?", full))
    th_sample = thread_dims[0].raw.strip() if thread_dims else ("слово «резьба»" if has_thread else "")
    says = _yn(feats["thread"], "с резьбой", "без резьбы")
    if feats["thread"] is True and not has_thread:
        row("Резьба", says, "не найдена", "diff", "K104", f"Код {code} — «с резьбой», но резьбы на чертеже не найдено")
    elif feats["thread"] is False and thread_dims:
        row("Резьба", says, f"есть: «{th_sample}»", "diff", "K104", f"Код {code} — «без резьбы», а на чертеже резьбовой размер «{th_sample}»")
    else:
        row("Резьба", says, f"есть: {th_sample}" if has_thread else "не найдена", "unknown" if feats["thread"] is None else "ok")

    # пазы и шлицы
    has_slots = bool(re.search(r"(?<![а-яё])(?:паз|шлиц|шпоноч)", full))
    says = _yn(feats["slots"], "с пазами/шлицами", "без пазов и шлицев")
    if feats["slots"] is True and not has_slots:
        row("Пазы и шлицы", says, "не найдены", "diff", "K105", f"Код {code} — «с пазами/шлицами», но пазов и шлицев на чертеже не найдено")
    elif feats["slots"] is False and has_slots:
        row("Пазы и шлицы", says, "есть слово «паз», «шлиц» или «шпоноч»", "diff", "K105",
            f"Код {code} — «без пазов и шлицев», а на чертеже есть слово «паз», «шлиц» или «шпоноч»")
    else:
        row("Пазы и шлицы", says, "есть" if has_slots else "не найдены", "unknown" if feats["slots"] is None else "ok")

    # форма
    if code[:2] in ROTATION:
        if diameters or thread_dims:
            row("Форма", "тело вращения (класс " + code[:2] + ")", f"есть ⌀ ({len(diameters)})", "ok")
        else:
            row("Форма", "тело вращения (класс " + code[:2] + ")", "размеров ⌀ нет", "diff", "K106",
                f"Код {code} — тело вращения (класс {code[:2]}), но размеров ⌀ на чертеже нет")
    elif code[:2] in NOT_ROTATION:
        row("Форма", "не тело вращения (класс " + code[:2] + ")", f"⌀ на чертеже: {len(diameters)}", "unknown")

    # заготовка
    mat = (drw.title.material or "").lower()
    group_text = " ".join(n.lower() for _c, n in names[1:])      # название класса («…профильные; трубы») не в счёт: оно общее для всех деталей класса
    code_profile = bool(re.search(r"профильн|швеллер|двутавр|уголк|балк|труб", group_text))
    word = next((w for w in PROFILE_WORDS if w in mat), "")
    plate = next((w for w in PLATE_WORDS if re.search(r"(?<![а-яё])" + w, mat)), "")
    if code[:2] in ("73", "74", "75", "76") and mat:
        if word and not code_profile:
            row("Заготовка", "не профильная деталь", f"в графе 3 «{word}»", "diff", "K107",
                f"Код {code} — не профильный, а в графе 3 «{word}»: проверьте сортамент или код")
        elif plate and code_profile and code[:2] == "74":
            row("Заготовка", "профильная деталь", f"в графе 3 «{plate}»", "diff", "K107",
                f"Код {code} — профильный, а в графе 3 «{plate}»: проверьте сортамент или код")
        elif word or plate:
            row("Заготовка", "профильная деталь" if code_profile else "не профильная деталь", f"в графе 3 «{word or plate}»", "ok")
