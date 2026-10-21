"""Пункты стандартов: разбор текста PDF на пункты, привязка к ним проверок и отметки администратора.

* clauses(path) — пункты из текста PDF («5.17 Масса изделия…»): номер, страница, начало текста;
* coverage(cfg, key) — какие проверки на какие пункты ссылаются (по полю «стандарт» проверок);
* marks — отметки администратора: пункт стандарта, по которому нужно сделать проверку (заявка на правило). Хранятся в
  data/std_marks.json; разработчик читает их скриптом tools/std_marks.py и пишет правило."""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from functools import lru_cache

from . import catalog, norms, std_links
from .rule_docs import RULE_DOCS, rev_of
from .config import DATA

PATH = os.path.join(DATA, "std_marks.json")
STATUSES = ("open", "done", "rejected")
_LOCK = threading.Lock()

_CLAUSE = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){0,4})\.?\s+(?=\S)")           # в старых стандартах после номера стоит точка: «1.1. Текст»
_NUM_ONLY = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){1,4})$")
_START = re.compile(r"(?m)^\s*1\s+Область применения")


@lru_cache(maxsize=32)
def _clauses(path: str, mtime: float) -> tuple:
    pages = norms.pages_text(path)
    first = 0
    # оглавление тоже содержит «1 Область применения…… 1»: берём страницу, где за заголовком нет отточия
    for i, t in enumerate(pages):
        m = _START.search(t)
        if m and not re.search(r"\.{4,}", t[m.start(): m.start() + 120]):
            first = i
            break
    out: dict[str, dict] = {}
    cur = None
    for pn in range(first, len(pages)):
        for raw in pages[pn].split("\n"):
            line = raw.strip()                     # мягкий перенос в конце строки склеивает слово со следующей строкой
            if not line:
                continue
            m = _CLAUSE.match(line)
            only = _NUM_ONLY.match(line)             # «5.14» отдельной строкой, текст пункта на следующей
            if only:
                m, rest = only, ""
            else:
                rest = line[m.end():].strip() if m else ""
            if m and not re.search(r"\.{4,}", line) and (only or re.match(r"[А-Яа-яA-Za-z«\"(]", rest)):
                n = m.group(1)
                if n in out:                         # повторное вхождение (список, пример) — продолжение текста
                    if cur:
                        cur["text"] += ("" if cur["text"].endswith("­") else " ") + line
                    continue
                cur = {"n": n, "page": pn + 1, "text": rest}
                out[n] = cur
            elif cur and len(cur["text"]) < 1500:
                cur["text"] += ("" if cur["text"].endswith("­") else " ") + line
    res = []
    for c in out.values():
        t = re.sub(r"\s+", " ", c["text"].replace("­­", "")).strip().replace("­", "")
        res.append({"n": c["n"], "page": c["page"], "text": t[:1200]})
    return tuple(res)


_GRAF = re.compile(r"^(\d{1,2})(?:\s*\d\))?$")


@lru_cache(maxsize=32)
def _graphs(path: str, mtime: float) -> tuple:
    """Графы таблицы «Содержание и порядок заполнения граф основной надписи» (ГОСТ 2.104): «гр. N» с текстом порядка заполнения."""
    pages = norms.pages_text(path)
    joined = " ".join(pages)
    if not re.search(r"Порядок\s+заполнения\s+графы", joined) or re.search(r"Графа\s+\d", joined):
        return ()                                   # таблица другого вида (ГОСТ 2.104-2006: «Графа N» в конце строки) не разбирается
    out: dict[int, dict] = {}
    cur = None
    last = 0
    for pn, t in enumerate(pages):
        if not re.search(r"(?i)таблиц\w*\s*1(?<![A-Za-z])|Номер\s+графы", t) or "Приложение А" in t[:400] and "Т а б л и ц а 1" not in t:
            continue
        for raw in t.split("\n"):
            line = raw.replace("­", "").strip()
            m = _GRAF.match(line)
            if m and last < int(m.group(1)) <= last + 3 and int(m.group(1)) <= 41:
                last = int(m.group(1))
                cur = {"n": f"гр. {last}", "page": pn + 1, "text": ""}
                out[last] = cur
            elif cur and line and len(cur["text"]) < 500:
                cur["text"] += " " + line
    return tuple({"n": c["n"], "page": c["page"], "text": re.sub(r"\s+", " ", c["text"]).strip()[:400]} for c in out.values())


def clauses(path: str) -> list[dict]:
    mt = os.path.getmtime(path)
    return list(_clauses(path, mt)) + list(_graphs(path, mt))


def _graf_nums(tail: str) -> list[str]:
    """«гр. 7, 8», «гр. 14–17» → ["гр. 7", "гр. 8"], ["гр. 14", …, "гр. 17"]."""
    m = re.search(r"гр\.\s*([\d,\s–-]+)", tail)
    if not m:
        return []
    out: list[str] = []
    for part in re.split(r"\s*,\s*", m.group(1).strip()):
        r = re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", part.strip())
        if r:
            out += [f"гр. {i}" for i in range(int(r.group(1)), int(r.group(2)) + 1)]
        elif part.strip().isdigit():
            out.append(f"гр. {int(part)}")
    return out


def _nums(tail: str) -> list[str]:
    """Номера пунктов из хвоста ссылки: «п. 7.3.4 (примечание)», «пп. 5.9–5.10», «разд. 3», «п. 9.1, 9.9»."""
    g = _graf_nums(tail)
    if g:
        return g
    if not re.search(r"(?i)\b(?:п|пп|разд|раздел)\.?\s*\d", tail):
        return []
    tail = re.split(r"(?i)приложени", tail)[0]
    return re.findall(r"(?<![\d.])\d{1,2}(?:\.\d{1,3})*", tail)


def _std_texts(cfg: dict) -> dict[str, list[str]]:
    from .rule_standards import RULE_STANDARDS
    texts = {c: list(v) for c, v in RULE_STANDARDS.items()}
    for code, r in catalog.EXT_REG.items():
        texts.setdefault(code, []).append(r["std"])
    for r in cfg.get("custom_rules") or []:
        if r.get("code") and r.get("ref"):
            texts.setdefault(r["code"], []).append(r["ref"])
    return texts


def coverage(cfg: dict, key: tuple, edition: tuple | None = None) -> dict:
    """Проверки, ссылающиеся на стандарт с ключом key = (вид, номер): по пунктам и без пункта.
    {"by_clause": {"7.3.4": [code…]}, "whole": [code…], "codes": {code: {"text", "sev", "default"}}}"""
    from .stdreg import _key, _OST4
    info = {c: {"text": t, "sev": sev, "default": d} for c, _g, t, d, sev in catalog.all_rules(cfg)}
    by_clause: dict[str, list[str]] = {}
    whole: list[str] = []
    for code, texts in _std_texts(cfg).items():
        if code not in info:
            continue
        for t in texts:
            ost = list(_OST4.finditer(t))            # «ОСТ4 ГО.070.014» целиком: общий разбор видит в нём только «ОСТ4»
            ms = sorted(ost + [m for m in norms._DESIG.finditer(t) if not any(o.start() <= m.start() < o.end() for o in ost)],
                        key=lambda m: m.start())      # в одной строке может быть несколько стандартов: «…; ГОСТ … п. 6.1»
            for i, m in enumerate(ms):
                if _key(m.group(0)) != key:
                    continue
                dm = norms.parse_designation(m.group(0))
                if edition and dm and dm[3] and edition[1] and (dm[3], dm[1]) != (edition[1], edition[0]):
                    continue                          # ссылка на другую редакцию этого стандарта (другой год или «Р»)
                nums = _nums(t[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(t)])
                if not nums and code not in whole:
                    whole.append(code)
                for n in nums:
                    lst = by_clause.setdefault(n, [])
                    if code not in lst:
                        lst.append(code)
    return {"by_clause": by_clause, "whole": sorted(whole), "codes": info}


def detail(cfg: dict, norm_id: str) -> dict | None:
    from .stdreg import _key
    it = norms.get(norm_id)
    if not it:
        return None
    key = _key(it["designation"] if norms.parse_designation(it["designation"]) else it["id"])
    de = norms.parse_designation(it["designation"])
    cov = coverage(cfg, key, (de[1], de[3]) if de else None)
    marks = [m for m in load_marks() if m["file_id"] == it["id"]]
    rows = []
    for c in clauses(it["path"]):
        own = cov["by_clause"].get(c["n"], [])
        child = sorted({code for n, codes in cov["by_clause"].items() if n.startswith(c["n"] + ".") for code in codes})
        rows.append({**c, "checks": own, "child_checks": [x for x in child if x not in own],
                     "marks": [m for m in marks if m["clause"] == c["n"]]})
    used = {c for r in rows for c in r["checks"] + r["child_checks"]} | set(cov["whole"])
    codes = {}
    for c in used:
        if c in cov["codes"]:
            lv, note = std_links.level(c)
            doc = RULE_DOCS.get(c)
            if doc is None:
                cr = next((r for r in cfg.get("custom_rules") or [] if r.get("code") == c), None)
                doc = catalog.custom_doc(cfg, c) if cr else None
            codes[c] = {**cov["codes"][c], "link": lv, "link_note": note, "rev": rev_of(c), "doc": doc}
    known = {r["n"] for r in rows}
    return {"id": it["id"], "designation": it["designation"], "title": it["title"], "pages": it["pages"], "clauses": rows,
            "whole": cov["whole"], "codes": codes,
            "stale": sorted(n for n in cov["by_clause"] if n not in known),   # пункты, на которые ссылаются проверки, но в тексте PDF не найдены
            "marks_without_clause": [m for m in marks if m["clause"] not in known]}


# ------------------------------------------------------------ отметки администратора
def load_marks() -> list[dict]:
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(marks: list[dict]) -> None:
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(marks, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def add_mark(user: str, file_id: str, designation: str, clause: str, text: str, comment: str) -> dict:
    mark = {"id": uuid.uuid4().hex[:10], "file_id": file_id, "std": designation, "clause": clause.strip(),
            "text": (text or "")[:400], "comment": (comment or "").strip(), "status": "open", "code": "",
            "author": user, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    if not mark["clause"]:
        raise ValueError("не указан пункт")
    with _LOCK:
        marks = load_marks()
        if any(m["file_id"] == file_id and m["clause"] == mark["clause"] and m["status"] == "open" for m in marks):
            raise ValueError("по этому пункту заявка уже есть")
        marks.append(mark)
        _save(marks)
    return mark


def update_mark(mark_id: str, status: str | None, comment: str | None, code: str | None) -> dict | None:
    with _LOCK:
        marks = load_marks()
        m = next((x for x in marks if x["id"] == mark_id), None)
        if not m:
            return None
        if status in STATUSES:
            m["status"] = status
        if comment is not None:
            m["comment"] = comment.strip()
        if code is not None:
            m["code"] = code.strip()
        _save(marks)
    return m


def delete_mark(mark_id: str) -> bool:
    with _LOCK:
        marks = load_marks()
        rest = [m for m in marks if m["id"] != mark_id]
        if len(rest) == len(marks):
            return False
        _save(rest)
    return True


# ------------------------------------------------------------ подсказки: что в стандарте можно проверять
_SKIP_HEAD = re.compile(r"(?i)^(область применения|нормативные ссылки|термины|определени|сокращени|предисловие|введение|библиограф|общие положения$)")
_MODAL = re.compile(r"(?i)\b(должн\w*|следует|не допуска\w*|допускается|не более|не менее|запрещ\w*|обязательн\w*|необходимо|не должн\w*)\b")
_NUMERIC = re.compile(r"(?i)(±|\d\s?(?:мм|мкм|°|%|кг|н\b|мпа|квт|с\b|мин|шт)|\bR[az]\s?\d|\bIT\s?\d+|\d+\s*[xх×]\s*\d+|не более|не менее|от \d+ до \d+)")
_SHOW = re.compile(r"(?i)\b(указыва\w*|наносят|обознача\w*|приводят|записыва\w*|изображ\w*|проставля\w*|вноси\w*|должн\w* быть (?:указан|нанесен|приведен|обозначен))")
_DRAW = re.compile(r"(?i)(чертеж|размер|надпис|штамп|обозначени|шероховат|допуск|отклонен|резьб|линии|линий|шрифт|масштаб|формат|спецификац|таблиц|граф[аыеу]|технически\w* требован|покрыти|материал|маркиров|сварн|шов|вид[аеыов]?\b|разрез|сечени|ссылк)")
_ORG = re.compile(r"(?i)(организац|предприяти|разработчик|заказчик|порядок|регистрац|хранени|утвержден|внедрен|применяют)")


def _readable(s: str) -> bool:
    """Отсекает мусор распознавания и таблиц: нужны слова, а не россыпь букв и цифр."""
    body = re.sub(r"\s+", "", s)
    words = re.findall(r"[А-Яа-яЁё]{3,}", s)
    return len(body) > 0 and sum(len(w) for w in words) / len(body) >= 0.55 and len(words) >= 4


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\((?:Измененная|Введен\w*|Исключен\w*)[^)]*\)", " ", text)
    text = re.sub(r"\s+\d{1,3}\.?\s+(?:ГОСТ|С\.)[^.]{0,30}$", "", text)
    out = []
    for s in re.split(r"(?<=[.;:])\s+(?=[А-ЯЁ\-–—«(])", text):
        s = re.sub(r"\s+\d{1,2}\.\s*$", ".", s.strip())
        if len(s) > 25 and _readable(s) and not s.startswith("Издание"):
            out.append(s)
    return out


def _hint(sent: str) -> str:
    if _NUMERIC.search(sent):
        return "числовое ограничение: сравнить значение на чертеже"
    if re.search(r"(?i)не допуска\w*|запрещ\w*", sent):
        return "запрет: проверить, что на чертеже этого нет"
    if _SHOW.search(sent):
        return "обязательная запись или обозначение: проверить наличие"
    return "требование оформления"


_WHERE = [
    (r"(?i)шероховат", "в обозначениях шероховатости на изображении и в знаке «в остальном» (поле чертежа)"),
    (r"(?i)технически\w* требован", "в технических требованиях на поле чертежа"),
    (r"(?i)основн\w* надпис|штамп|граф[аыеу]\b", "в основной надписи (штампе) чертежа"),
    (r"(?i)спецификац", "в спецификации (таблица или отдельный документ)"),
    (r"(?i)резьб", "в размерах и обозначениях резьбы на видах и разрезах"),
    (r"(?i)покрыти|термообработ|материал", "в обозначении материала, покрытия, в технических требованиях и графе материала"),
    (r"(?i)размер|отклонен|допуск|квалитет|посадк", "в размерных числах и допусках на видах, разрезах и сечениях"),
    (r"(?i)линии|линий|штрих|шрифт|стрелк", "в графике чертежа: типы линий, шрифт, стрелки"),
    (r"(?i)обозначени|надпис|запис", "в надписях и обозначениях на поле чертежа"),
    (r"(?i)вид[аеыов]?\b|разрез|сечени|выносн", "в изображениях: виды, разрезы, сечения"),
]
_READABLE_SIMPLE = re.compile(r"(?i)(шероховат|размер|отклонен|допуск|надпис|обозначени|резьб|технически\w* требован|материал|покрыти|штамп|граф[аыеу]\b|спецификац|запис|масштаб|формат)")
_READABLE_HARD = re.compile(r"(?i)(изображ|вид[аеыов]?\b|разрез|сечени|линии|линий|штрих|стрелк|симметрич|расположен|взаимн|форм[аыуе]\b)")


def _where(sent: str) -> str:
    for rx, txt in _WHERE:
        if re.search(rx, sent):
            return txt
    return "на листе чертежа (место уточним по тексту пункта)"


_LIMIT = re.compile(r"(?i)(?:от\s+[\d.,]+\s+до\s+[\d.,]+\s?(?:мм|мкм|°|%)?|[±]\s?[\d.,]+\s?(?:мм|мкм|°|%)?|[\d.,]+\s?(?:мм2?|мкм|°|%|МПа|кгс/мм2|кг|Н|кВт|с|мин|шт)(?![А-Яа-яA-Za-z])|(?<![A-Za-z])R[az]\s?[\d.,]+|(?<![A-Za-z])IT\s?\d+|[\d.,]+\s*[xх×]\s*[\d.,]+\s?°?)")


def _limits(sent: str) -> str:
    vals = []
    for m in _LIMIT.finditer(sent):
        v = re.sub(r"\s+", " ", m.group(0)).strip(" .,")
        if v and v not in vals:
            vals.append(v)
    return ", ".join(vals[:4])


def _plan(sent: str, hint: str) -> dict:
    """Черновик описания проверки: что, где, как, когда ошибка, насколько сложно. Это предположение, его правит администратор."""
    lim = _limits(sent)
    if hint.startswith("числовое"):
        how = "Найти на чертеже соответствующее значение и сравнить с пределом из пункта" + (f" ({lim})" if lim else "") + "."
        err = "значение на чертеже выходит за допустимый предел" + (f" ({lim})" if lim else "") + "."
    elif hint.startswith("запрет"):
        how = "Найти на чертеже то, что пункт запрещает (в тексте надписей или в обозначениях), и показать место."
        err = "на чертеже есть запрещённая запись или обозначение."
    elif hint.startswith("обязательная"):
        how = "Проверить, что требуемая запись или обозначение есть на чертеже и записано по форме пункта."
        err = "требуемой записи или обозначения нет либо оно оформлено иначе, чем в пункте."
    else:
        how = "Сверить оформление на чертеже с формулировкой пункта; способ сравнения уточняется при разработке правила."
        err = "оформление расходится с требованием пункта."
    if _READABLE_HARD.search(sent) and not _READABLE_SIMPLE.search(sent):
        hardness = "сложно: нужен анализ изображения (виды, линии, взаимное расположение), текстом не проверить"
    elif _READABLE_SIMPLE.search(sent):
        hardness = "реально: нужные данные программа уже читает с чертежа (надписи, размеры, обозначения)"
    else:
        hardness = "нужно уточнить, какие данные чертежа для этого понадобятся"
    return {"what": sent[:300], "where": _where(sent), "how": how, "error": err, "hardness": hardness}


def _draft(plan: dict) -> str:
    return (f"Что проверяем: {plan['what']}\nГде: {plan['where']}\nКак: {plan['how']}\n"
            f"Ошибка, если: {plan['error']}\nСложность: {plan['hardness']}")


def suggest(cfg: dict, norm_id: str, limit: int = 12, include_all: bool = False) -> dict | None:
    """Пункты стандарта без проверок: кандидаты (по формулировкам есть проверяемое требование) и черновик описания проверки.
    include_all — вернуть описание для всех пунктов без проверок (candidate=False у не похожих на требование).
    Это эвристика по тексту, а не готовые правила."""
    d = detail(cfg, norm_id)
    if not d:
        return None
    taken = {m["clause"] for m in d_marks(norm_id)}
    out, total = [], 0
    for c in d["clauses"]:
        if c["checks"] or c["child_checks"] or c["n"].startswith(("гр.", "0.")):
            continue
        text = c["text"]
        if len(text) < 40 or _SKIP_HEAD.match(text.strip()):
            continue
        total += 1
        sents = _sentences(text)
        cands = [(s, len(_MODAL.findall(s)) * 2 + (2 if _NUMERIC.search(s) else 0) + (1 if _SHOW.search(s) else 0)
                  + (2 if _DRAW.search(s) else 0) - (2 if _ORG.search(s) else 0)) for s in sents if _MODAL.search(s)]
        if cands:
            best, score = max(cands, key=lambda x: x[1])
            score += min(2, len(cands) - 1)
        elif include_all and (sents or text):
            best, score = (sents[0] if sents else text[:260]), 0
        else:
            continue
        candidate = score >= 4
        if not candidate and not include_all:
            continue
        hint = _hint(best)
        plan = _plan(best, hint)
        out.append({"n": c["n"], "page": c["page"], "excerpt": best[:260], "hint": hint, "score": score, "candidate": candidate,
                    "marked": c["n"] in taken or bool(c["marks"]), "plan": plan, "draft": _draft(plan)})
    out.sort(key=lambda x: (-x["score"], x["n"]))
    found = sum(1 for x in out if x["candidate"])
    return {"id": d["id"], "designation": d["designation"], "items": out if include_all else out[:limit], "found": found,
            "clauses_without_checks": total}


def d_marks(norm_id: str) -> list[dict]:
    return [m for m in load_marks() if m["file_id"] == norm_id]
