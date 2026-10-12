"""Технические требования и текст на чертеже (ГОСТ 2.316-2008, ГОСТ 2.105-2019), ссылки на стандарты,
общие допуски (ГОСТ 30893), термообработка и покрытия (ГОСТ 2.310-68, ГОСТ 9.306-85)."""
from __future__ import annotations

import re

from .model import Drawing, ERROR, WARNING, INFO, CAT_TT, CAT_REFS, CAT_HEAT
from .normdata import OBSOLETE_STANDARDS
from .textnorm import to_float
from .titleblock import excluded


STD_REF = re.compile(r"(?<![А-ЯA-Z])(?P<kind>ГОСТ|ОСТ)\s*(?P<r>Р\s*)?(?P<num>\d+(?:\.\d+)*)\s*[-–]\s*(?P<yr>\d{2,4})(?!\d)")
NO_NUMBER = re.compile(r"(?<![А-ЯA-Zа-я])ГОСТ(?:\s+Р)?(?![А-Яа-я])(?![^\d\n]{0,12}\d)")
TT_NUM = re.compile(r"^(\d{1,2})[.)]?\s+(?=[*А-ЯЁA-Z«\"(])")
DESIGNATION = re.compile(r"\d{3}-\d{6}|[А-Я]{4}\.\d{6}")


def texts(drw: Drawing) -> list[tuple[str, int | None, tuple | None]]:
    """Все надписи чертежа для поиска по тексту: пункты ТТ, прочие надписи (строка + перенос на следующую,
    если она начинается с цифры — «по ГОСТ» / «13755-2015» в ячейке таблицы), материал из графы 3."""
    out = [(t, p, b) for t, p, b in drw.facts.get("_tt_items", [])]
    if not out:
        out = [(t, None, None) for t in drw.tt]
    return out + line_texts(drw, with_tt=False)


def line_texts(drw: Drawing, with_tt: bool = True) -> list[tuple[str, int | None, tuple | None]]:
    """Надписи по строкам; строка, оканчивающаяся на «ГОСТ»/«по», склеивается с продолжением ниже."""
    out = []
    tt_ids = {id(x) for x in drw.tt_lines}
    pool = [ln for ln in drw.lines if not excluded(drw, ln)]
    for ln in pool:
        if not with_tt and id(ln) in tt_ids:
            continue
        t = ln.text.strip()
        h = max(ln.bbox[3] - ln.bbox[1], 2.0)
        if re.search(r"(ГОСТ|ОСТ|по)\s*Р?\s*$", t):
            below = [o for o in pool if o.page == ln.page and o is not ln and -1 <= o.bbox[1] - ln.bbox[3] < 0.9 * h
                     and abs(o.bbox[0] - ln.bbox[0]) < 25 and re.match(r"\s*\d", o.text)]
            if below:
                t = t + " " + min(below, key=lambda o: o.bbox[1]).text.strip()
        out.append((t, ln.page, ln.bbox))
    if drw.title.material:
        out.append((drw.title.material, drw.first_page, drw.title.bboxes.get("material")))
    return out


def _obsolete_table(cfg: dict) -> dict[str, str]:
    rows = cfg.get("obsolete_standards")
    if not rows:
        rows = [{"old": o, "new": n} for o, n in OBSOLETE_STANDARDS]
    return {_key(r["old"]): r["new"] for r in rows if r.get("old") and r.get("new")}


def _key(ref: str) -> str:
    m = STD_REF.search(ref.replace("—", "-"))
    if not m:
        return re.sub(r"\s+", "", ref.upper())
    return f"{m.group('kind')}{'Р' if m.group('r') else ''}{m.group('num')}-{m.group('yr')}"


def check_refs(drw: Drawing, cfg: dict) -> None:
    table = _obsolete_table(cfg)
    seen_old, seen_none = set(), False
    for t, pg, bb in texts(drw):
        for m in STD_REF.finditer(t.replace("—", "-")):
            k = f"{m.group('kind')}{'Р' if m.group('r') else ''}{m.group('num')}-{m.group('yr')}"
            if k in table and k not in seen_old:
                seen_old.add(k)
                drw.add(WARNING, "N01", CAT_REFS, f"Ссылка на «{m.group(0).strip()}» — редакция заменена, действует "
                        f"{table[k]}", pg, bb, "ГОСТ 2.105-2019")
    for t, pg, bb in line_texts(drw):
        if not seen_none and NO_NUMBER.search(t):
            seen_none = True
            drw.add(ERROR, "N02", CAT_REFS, f"«{t[:90]}»: ссылка «ГОСТ» без номера стандарта — ссылаются на "
                    f"стандарт с регистрационным номером", pg, bb, "ГОСТ 2.105-2019")


# ------------------------------------------------------------------------------ ТТ и текст ----
def check_tt_text(drw: Drawing, cfg: dict) -> None:
    items = drw.facts.get("_tt_items") or [(t, None, None) for t in drw.tt]
    nums, first = [], None
    for t, pg, bb in items:
        m = TT_NUM.match(t)
        if m and not DESIGNATION.search(t[:20]):
            nums.append(int(m.group(1)))
            first = first or (pg, bb)
    if len(nums) >= 2 and nums != list(range(1, len(nums) + 1)):
        dup = sorted({n for n in nums if nums.count(n) > 1})
        gaps = sorted(set(range(1, max(nums) + 1)) - set(nums))
        why = "; ".join(x for x in (f"повторяются {', '.join(map(str, dup))}" if dup else "",
                                     f"пропущены {', '.join(map(str, gaps))}" if gaps else "",
                                     "нарушен порядок" if not dup and not gaps else "") if x)
        drw.add(WARNING, "P01", CAT_TT, f"Нумерация пунктов ТТ: {', '.join(map(str, nums))} — {why}. Пункты ТТ "
                f"имеют сквозную нумерацию", *(first or (None, None)), "ГОСТ 2.316-2008 п. 4.13")

    tt = " ".join(t for t, _, _ in items)
    loc = items[0][1:] if items else (None, None)
    # десятичная точка в числах ТТ (диапазоны «0.4...0.5», «… мм»)
    m = re.search(r"\d+\.\d+\s*(?:\.\.\.|…)\s*\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s*(?:\.\.\.|…)\s*\d+\.\d+|"
                  r"\d+\.\d+\s*мм\b", tt)
    if m:
        drw.add(INFO, "P02", CAT_TT, f"В ТТ «{m.group(0)}»: дробную часть отделяют запятой", *loc, "ГОСТ 2.105-2019")
    # знаки без числовых значений
    m = re.search(r"(?<![\d\s])\s*[≥≤≠](?!\s*[-+]?\d)|№(?!\s*\d)|(?<![\d\s])\s*%", tt)
    if m:
        drw.add(INFO, "P03", CAT_TT, f"В ТТ знак «{m.group(0).strip()}» без числового значения — в тексте пишут "
                f"словами («не более», «номер», «процент»)", *loc, "ГОСТ 2.105-2019")
    # общие допуски: «±IT14/2», «±t2/2»
    for m in re.finditer(r"(?P<pre>[±+\-]?\s*)(?P<v>IT\s?\d{1,2}\s*/\s*2|(?<![A-Za-z])t\s?[1-4]\s*/\s*2)", tt):
        if "±" not in m.group("pre"):
            drw.add(WARNING, "P04", CAT_TT, f"В ТТ «{m.group('v')}» без знака «±»: симметричные отклонения "
                    f"записывают «±{m.group('v').replace(' ', '')}»", *loc, "ГОСТ 30893.1-2002")
            break
    for m in re.finditer(r"30893\.1\s*[-–:]?\s*(?P<c>[A-Za-zА-Яа-я])\b", tt):
        c = m.group("c")
        if c in "fmcv":
            continue
        if c in "смт":
            drw.add(INFO, "P06", CAT_TT, f"Класс точности «{c}» в «ГОСТ 30893.1-{c}» набран русской буквой — нужна "
                    f"латинская ({'c' if c == 'с' else 'm'})", *loc, "ГОСТ 30893.1-2002")
        elif not re.search(r"30893\.1\s*:", m.group(0)):
            drw.add(WARNING, "P05", CAT_TT, f"Класс точности «{c}» по ГОСТ 30893.1 не существует (f, m, c, v)",
                    *loc, "ГОСТ 30893.1-2002")
    for m in re.finditer(r"30893\.2\s*[-–]\s*(?P<c>[A-Za-zА-Яа-я]{1,2})\b", tt):
        c = m.group("c")[-1]
        if c in "HKL":
            continue
        if c in "НК":
            drw.add(INFO, "P06", CAT_TT, f"Класс «{c}» в «ГОСТ 30893.2-{m.group('c')}» набран русской буквой — "
                    f"нужна латинская ({'H' if c == 'Н' else 'K'})", *loc, "ГОСТ 30893.2-2002")
        else:
            drw.add(WARNING, "P05", CAT_TT, f"Класс точности «{c}» по ГОСТ 30893.2 не существует (H, K, L)",
                    *loc, "ГОСТ 30893.2-2002")
    # русские буквы в обозначениях полей допусков в ТТ («Н14, h14»)
    if re.search(r"(?i)допуск|отклонен|30893|25346|25347", tt):
        m = re.search(r"(?<![А-Яа-яA-Za-z])([НК])(1[0-8]|[1-9])\b", tt)
        if m:
            drw.add(INFO, "P06", CAT_TT, f"В ТТ «{m.group(0)}»: в обозначении поля допуска русская буква — "
                    f"нужна латинская ({m.group(0).replace('Н', 'H').replace('К', 'K')})", *loc, "ГОСТ 25346-2013")


# ------------------------------------------------------------------ термообработка/покрытия ----
HARD = re.compile(r"(?P<sym>HRC[эЭ]?|HRA|HRB|HV|HB|НВ)\s*(?P<a>\d+(?:[.,]\d+)?)(?:\s*(?:\.\.\.|…|\.\.|÷|-|–)\s*"
                  r"(?P<b>\d+(?:[.,]\d+)?))?|(?P<a2>\d+(?:[.,]\d+)?)(?:\s*(?:\.\.\.|…|\.\.|÷|-|–)\s*"
                  r"(?P<b2>\d+(?:[.,]\d+)?))?\s*(?P<sym2>HRC[эЭ]?|HRA|HRB|HV|HB|НВ)\b(?!\s*\d)")
HEAT_WORDS = re.compile(r"(?i)закал|улучш|цементир|цементац|азотир|нитроцемент|\bТВЧ\b|нормализ|термообработ|"
                        r"термически обработ")
CASE_WORDS = re.compile(r"(?i)цементир|цементац|азотир|нитроцемент|\bТВЧ\b|поверхностн\w* закал")
COATING = re.compile(r"(?<![А-Яа-яA-Za-z])(?P<m>Ц|Кд|Хтв|Хч|Х|Н|М|О|Ср)(?P<t>\d{1,3})(?P<add>хр|бцв|фос|окс|"
                     r"прм|нхр)\b")


def check_heat(drw: Drawing, cfg: dict) -> None:
    all_t = texts(drw)
    tt = " ".join(t for t, _, _ in all_t)
    loc = next(((p, b) for t, p, b in all_t if HEAT_WORDS.search(t) or HARD.search(t)), (None, None))
    min_rng = cfg.get("hardness_min_range_hrc", 4)
    seen = set()
    for t, pg, bb in all_t:
        for m in HARD.finditer(t):
            sym = (m.group("sym") or m.group("sym2")).replace("НВ", "HB")
            a, b = to_float(m.group("a") or m.group("a2")), to_float(m.group("b") or m.group("b2"))
            key = (sym, a, b)
            if key in seen or a is None:
                continue
            seen.add(key)
            before = t[max(0, m.start() - 16):m.start()].lower()
            if b is None:
                if not re.search(r"не (?:менее|более|ниже|выше)|≥|≤|>|<|min|max|до\s*$|от\s*$", before + " "
                                 + t[m.end():m.end() + 10].lower()):
                    drw.add(WARNING, "H01", CAT_HEAT, f"Твёрдость «{m.group(0).strip()}» задана одним числом — "
                            f"указывают пределы («{sym} {int(a)}…{int(a) + 5}») или «не менее»", pg, bb, "ГОСТ 2.310-68")
                continue
            if a > b:
                drw.add(ERROR, "H02", CAT_HEAT, f"Твёрдость «{m.group(0).strip()}»: нижний предел больше верхнего",
                        pg, bb, "ГОСТ 2.310-68")
            elif sym.startswith("HRC") and (a < 20 or b > 70):
                drw.add(WARNING, "H02", CAT_HEAT, f"Твёрдость «{m.group(0).strip()}» вне шкалы HRC (20…70) — "
                        f"проверьте шкалу (HB/HV?)", pg, bb, "ГОСТ 9013-59")
            elif sym.startswith("HRC") and b - a < min_rng:
                drw.add(INFO, "H03", CAT_HEAT, f"Твёрдость «{m.group(0).strip()}»: диапазон {b - a:g} ед. HRC — после "
                        f"термообработки выдержать трудно; обычно задают не менее {min_rng} ед. "
                        f"(например, {sym} {a:g}…{a + min_rng + 2:g})", pg, bb)
    if HEAT_WORDS.search(tt) and not re.search(r"(?i)не требуется|без термо", tt):
        if not HARD.search(tt) and not re.search(r"σв|σ0,2|Rm\b|предел прочности|ударн", tt):
            drw.add(WARNING, "H05", CAT_HEAT, "В ТТ указана термообработка, но не указана твёрдость (или другие "
                    "показатели свойств материала после обработки)", *loc, "ГОСТ 2.310-68")
        if CASE_WORDS.search(tt) and not re.search(r"(?i)глубин|\bh\s*=?\s*\d|толщин\w* сло", tt):
            drw.add(WARNING, "H06", CAT_HEAT, "Для цементации/азотирования/закалки ТВЧ не указана глубина слоя "
                    "(«h 0,8…1,2»)", *loc, "ГОСТ 2.310-68")
    for t, pg, bb in all_t:
        m = COATING.search(t)
        if m:
            drw.add(WARNING, "H04", CAT_HEAT, f"Покрытие «{m.group(0)}»: по ГОСТ 9.306 дополнительную обработку "
                    f"отделяют точкой — «{m.group('m')}{m.group('t')}.{m.group('add')}»", pg, bb, "ГОСТ 9.306-85")
            break
