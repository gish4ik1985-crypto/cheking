"""Текстовые документы по ГОСТ Р 2.105-2019 (ТУ, паспорта, расчёты, пояснительные записки, руководства…).

Работает только для документов, распознанных как текстовые (is_text_document): формат А4 книжный и код текстового
документа в обозначении (ТУ, ПЗ, РЭ, ФО…) либо — запасной признак — многостраничный А4 без размеров с большим
объёмом текста. Для них проверки чертежа (размеры, масса, допуски…) не выполняются, а выполняются проверки группы
«Текстовые документы» (коды L01…). Справка по стандарту — docs/norms/GOST_R_2.105-2019.md.

Геометрия берётся из PDF: строки текста с гарнитурой, размером шрифта и координатами в мм. Положение рамки и
основной надписи принято по формам 2 и 2а ГОСТ 2.104 (левое поле 20 мм, остальные 5 мм, штамп 40 мм на первом листе
и 15 мм на последующих)."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .model import Drawing, WARNING, INFO, CAT_TD
from .textnorm import norm_designation, to_float

PT = 25.4 / 72.0
STD = "ГОСТ Р 2.105-2019"

# коды текстовых документов в обозначении (ГОСТ 2.102): …ТУ, …ПЗ, …РЭ
TEXT_DOC_CODES = ["ТУ", "ПЗ", "РР", "РЭ", "ФО", "ПС", "ИЭ", "ИМ", "ТО", "ИС", "ИП", "ИО", "ИМ", "ВП", "ВИ", "ВЭ", "ВД",
                  "ВС", "ВУ", "ПМ", "ПТ", "ПП", "ТБ", "Э5"]
FORBIDDEN_LETTERS = set("ЁЗЙОЧЬЫЪ")

UNIT = (r"мм|см|дм|км|мкм|кг|мг|мл|мин|сут|мА|кВ|мВ|кВт|Вт|кГц|МГц|Гц|кОм|МОм|Ом|кН|Н|кПа|МПа|Па|кДж|Дж|Кл|Тл|лм|лк|"
        r"кд|дБ|рад|°С|°|%")
UNIT_RE = rf"(?<![А-Яа-яA-Za-z])(?:{UNIT})(?![А-Яа-яA-Za-z])"
LET = r"[А-Яа-яЁёA-Za-z]"


def S(p: str) -> str:
    return f"{STD} п. {p}"


# ------------------------------------------------------------------------------------------ разбор строк ----
@dataclass
class Row:
    text: str
    page: int
    x0: float
    x1: float
    y0: float
    y1: float
    size_pt: float
    fonts: tuple
    bold: bool
    first_page: bool = False

    @property
    def bbox(self):
        return (self.x0, self.y0, self.x1, self.y1)


@dataclass
class Doc:
    drw: Drawing
    rows: list[Row] = field(default_factory=list)          # строки основного поля (без штампа, полей, колонтитулов)
    segs: list = field(default_factory=list)               # исходные сегменты TextLine основного поля
    page_nums: list[int] = field(default_factory=list)
    body_pt: float = 0.0
    left: float = 0.0                                      # левая граница текста, мм
    toc: set = field(default_factory=set)                  # id строк содержания
    w: dict = field(default_factory=dict)                  # ширина страницы по номеру
    h: dict = field(default_factory=dict)


def _is_bold(fonts) -> bool:
    return any(re.search(r"(?i)bold|black|heavy|demi|[-,]bd\b|semibold|полужир", f or "") for f in fonts)


def _family(font: str) -> str:
    f = re.sub(r"^[A-Z]{6}\+", "", font or "")
    f = re.split(r"[-,]", f)[0]
    f = re.sub(r"(?i)(ps)?(mt)?$", "", f)
    return f.replace(" ", "").lower()


def build_doc(drw: Drawing) -> Doc:
    doc = Doc(drw)
    for p in drw.pages:
        doc.page_nums.append(p.number)
        doc.w[p.number], doc.h[p.number] = p.width, p.height
    first = drw.pages[0].number if drw.pages else 0
    segs = []
    for ln in drw.lines:
        if abs(ln.dir[1]) > 0.2 or ln.dir[0] < 0 or not ln.text.strip() or ln.fonts == ("ocr",):
            continue
        W, H = doc.w.get(ln.page, 210), doc.h.get(ln.page, 297)
        stamp = H - 5 - (40 if ln.page == first else 15)
        if ln.bbox[3] > stamp or ln.bbox[0] < 19 or ln.bbox[2] > W - 3 or ln.bbox[1] < 3:
            continue
        segs.append(ln)
    doc.segs = segs
    # склейка сегментов одной строки
    by_page = defaultdict(list)
    for ln in segs:
        by_page[ln.page].append(ln)
    for pno in sorted(by_page):
        items = sorted(by_page[pno], key=lambda l: (round(l.bbox[1] * 2) / 2, l.bbox[0]))
        cur: list = []
        for ln in items:
            if cur and abs(ln.cy - cur[0].cy) < 0.4 * max(ln.size, cur[0].size):
                cur.append(ln)
                continue
            if cur:
                doc.rows.append(_row(cur, first))
            cur = [ln]
        if cur:
            doc.rows.append(_row(cur, first))
    for r in doc.rows:
        if re.search(r"(\.{4,}|…{2,}|(?:\.\s){4,})\s*\d+\s*$", r.text):
            doc.toc.add(id(r))
    sizes = Counter()
    lefts = Counter()
    for r in doc.rows:
        if len(r.text) >= 25 and id(r) not in doc.toc:
            sizes[round(r.size_pt * 2) / 2] += len(r.text)
            lefts[round(r.x0)] += 1
    if sizes:
        doc.body_pt = sizes.most_common(1)[0][0]
    if lefts:
        doc.left = float(lefts.most_common(1)[0][0])
    return doc


def _row(items: list, first: int) -> Row:
    items = sorted(items, key=lambda l: l.bbox[0])
    text = " ".join(l.text for l in items).replace("\u00ad", "-").replace("\u2011", "-")
    fonts = tuple(f for l in items for f in l.fonts)
    big = max(items, key=lambda l: len(l.text))
    return Row(text=text, page=items[0].page, x0=min(l.bbox[0] for l in items), x1=max(l.bbox[2] for l in items),
               y0=min(l.bbox[1] for l in items), y1=max(l.bbox[3] for l in items), size_pt=big.size / PT,
               fonts=tuple(f for l in [big] for f in l.fonts) or fonts, bold=_is_bold(big.fonts), first_page=items[0].page == first)


def is_text_document(drw: Drawing, designation: str, cfg: dict) -> bool:
    """Текстовый ли документ (а не чертёж и не спецификация)."""
    if drw.error or not drw.pages or drw.facts.get("cdw") or drw.facts.get("dft"):
        return False
    if sum(1 for p in drw.pages if p.scanned) > 0.1 * len(drw.pages):         # скан: шрифты и размеры недоступны
        return False
    if drw.facts.get("spec_table") or any(t.get("kind") == "spec" for t in drw.facts.get("tables") or []):
        return False
    p = drw.pages[0]
    if not (abs(min(p.width, p.height) - 210) < 6 and abs(max(p.width, p.height) - 297) < 6) or p.width > p.height:
        return False
    codes = set(cfg.get("text_doc_codes") or TEXT_DOC_CODES)
    cands = [designation or ""]
    cands += [ln.text for ln in drw.lines if ln.page == p.number and len(ln.text) < 60]
    for c in cands:
        t = norm_designation(c) if c is designation else c
        m = re.search(r"[А-ЯA-Z]{2,5}\.\d{6}\.\d{3}(?:-\d{2,3})?\s?([А-ЯA-Z]{1,3})(?![А-Яа-яA-Za-z0-9])", t)
        if m and m.group(1) in codes:
            return True
    if cfg.get("text_doc_auto", True) and len(drw.pages) >= 2 and not drw.dims:
        n = sum(1 for ln in drw.lines if len(ln.text) > 40)
        if n / len(drw.pages) >= 25 and not drw.facts.get("is_assembly"):
            return True
    return False


# ------------------------------------------------------------------------------------------ вспомогательное ----
def _clean(t: str) -> str:
    """«П р и м е ч а н и е» → «Примечание»: сжать разрядку одиночных букв."""
    if re.fullmatch(r"(?:\S\s){3,}\S[\s\S]*", t[:12]) and re.match(r"(?:\S ){4,}", t):
        m = re.match(r"((?:\S ){3,}\S)(.*)", t)
        if m:
            return m.group(1).replace(" ", "") + m.group(2)
    return t


def _caption_rest(rest: str) -> bool:
    """Остаток строки после «Таблица N»/«Рисунок N» — это подпись, а не продолжение предложения."""
    r = rest.strip()
    if not r:
        return True
    if r[0] in DASHES + ".:":
        return True
    return rest[:1] == " " and r[:1].isupper() and len(r) <= 70 and not r.endswith((",", ";"))


def _prose(t: str, n: int = 5) -> bool:
    return len(re.findall(r"[А-Яа-яЁё]{3,}", t)) >= n


def _pg(r) -> int:
    return r.page


def _flag(doc: Doc, sev, code, msg, row=None, std=None, page=None):
    drw = doc.drw
    if row is not None:
        drw.add(sev, code, CAT_TD, msg, row.page, row.bbox, std)
    else:
        drw.add(sev, code, CAT_TD, msg, page, None, std)


SECTION_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})(\.?)\s+([А-ЯЁA-Z«\"(][^\n]*)$")
APPX_HEAD = re.compile(r"^Приложение\s+([А-ЯЁA-Z]|\d{1,2})\s*$")
APPX_SEC = re.compile(r"^([А-ЯЁA-Z])\.(\d{1,2}(?:\.\d{1,2}){0,3})\s+([А-ЯЁA-Z«\"(][^\n]*)$")
TABLE_CAP = re.compile(r"^Таблица\s+(?:([А-ЯA-Z])\.)?(\d{1,3}(?:\.\d{1,2})?)(.*)$")
FIG_CAP = re.compile(r"^Рисунок\s+(?:([А-ЯA-Z])\.)?(\d{1,3}(?:\.\d{1,2})?)(.*)$")
DASHES = "—–―−-"


def _is_heading(r: Row, m: re.Match, level: int) -> bool:
    text = m.group(3).strip()
    if id(r) in () or len(text) > 110:
        return False
    if r.bold:
        return True
    return level <= 2 and len(text) <= 70 and not re.search(r"[.;,:]$", text) and len(text.split()) <= 9


# ------------------------------------------------------------------------------------------ структура ----
ELEMENTS = [("титульный лист", r"^$"), ("предисловие", r"^Предисловие$"), ("содержание", r"^Содержание$"),
            ("обозначения и сокращения", r"^(Обозначения и сокращения|Перечень сокращений|Сокращения)$"),
            ("термины и определения", r"^Термины и определения$"),
            ("приложения", r"^Приложение\s+[А-ЯA-Z0-9]$"),
            ("ссылочные нормативные документы", r"^Ссылочные нормативные документы$"),
            ("ссылочные документы", r"^Ссылочные документы$"), ("библиография", r"^Библиография$"),
            ("лист регистрации изменений", r"^Лист регистрации изменений$")]


def _find_elements(doc: Doc) -> dict:
    found: dict = {}
    for r in doc.rows:
        t = _clean(r.text).strip()
        if id(r) in doc.toc:
            continue
        for name, pat in ELEMENTS:
            if pat != r"^$" and re.match(pat, t, re.I) and name not in found:
                found[name] = r
    return found


def check_structure(doc: Doc) -> None:
    drw = doc.drw
    n_pages = len(drw.pages)
    first = drw.pages[0].number
    elems = _find_elements(doc)
    # L01 титульный лист
    p1 = [r for r in doc.rows if r.page == first]
    title_like = any(r.text.isupper() and len(r.text) > 8 for r in p1) and not any(
        SECTION_RE.match(r.text) and id(r) not in doc.toc for r in p1)
    if not title_like and not any(re.search(r"(?i)лист утверждения|утверждаю|согласовано", r.text) for r in p1):
        _flag(doc, INFO, "L01", "Титульного листа не найдено: первый лист должен быть титульным (наименование изделия "
              "прописными буквами, наименование и обозначение документа)", page=first, std=S("6.1.2, 8.1"))
    # L02 лист регистрации изменений
    if n_pages > 1 and "лист регистрации изменений" not in elems and not any(
            re.search(r"(?i)лист\s+регистрации\s+изменений", r.text) for r in doc.rows):
        _flag(doc, INFO, "L02", "Нет листа регистрации изменений: в текстовых документах его следует предусматривать",
              page=drw.pages[-1].number, std=S("5.1.8"))
    # L03 содержание
    if n_pages > 24 and "содержание" not in elems:
        _flag(doc, WARNING, "L03", f"Объём документа {n_pages} л., но элемента «Содержание» нет — его помещают в "
              f"документах большого объёма (как правило, свыше 24 листов)", page=first, std=S("6.2.1"))
    # L04 порядок структурных элементов
    order = [n for n, _ in ELEMENTS[1:]]
    seq = [(order.index(n), n, r) for n, r in elems.items() if n in order]
    seq.sort(key=lambda x: (x[2].page, x[2].y0))
    for (i1, n1, r1), (i2, n2, r2) in zip(seq, seq[1:]):
        if i2 < i1:
            _flag(doc, WARNING, "L04", f"Порядок структурных элементов нарушен: «{n2}» (л. {r2.page + 1}) расположен "
                  f"после «{n1}» (л. {r1.page + 1}); порядок — титульный лист, предисловие, содержание, обозначения и "
                  f"сокращения, термины и определения, основное содержание, приложения, ссылочные нормативные "
                  f"документы, ссылочные документы, библиография, лист регистрации изменений", r2, S("6.1.1"))
            break
    # L05–L07 содержание
    toc_rows = [r for r in doc.rows if id(r) in doc.toc]
    head = elems.get("содержание")
    if head is not None:
        W = doc.w.get(head.page, 210)
        cx = (head.x0 + head.x1) / 2
        t = _clean(head.text).strip()
        if abs(cx - (20 + (W - 5)) / 2) > 15 or not head.bold or t[:1] != t[:1].upper() or head.y0 > 70:
            why = []
            if abs(cx - (20 + (W - 5)) / 2) > 15:
                why.append("не посередине")
            if not head.bold:
                why.append("не полужирным шрифтом")
            if head.y0 > 70:
                why.append("не в верхней части страницы")
            _flag(doc, INFO, "L05", "Слово «Содержание» оформлено не по ГОСТ: " + ", ".join(why) + " (записывают в верхней "
                  "части страницы, посередине, с прописной буквы, полужирным)", head, S("6.2.5"))
        after = [r for r in doc.rows if (r.page, r.y0) > (head.page, head.y0)]
        loose = []
        seen_toc = False
        for r in after[:80]:
            if id(r) in doc.toc:
                seen_toc = True
                continue
            m = SECTION_RE.match(r.text) or APPX_HEAD.match(r.text)
            if m and not re.search(r"\d+\s*$", r.text) and not seen_toc:
                loose.append(r)
            elif m and seen_toc:
                break
        if loose and toc_rows:
            _flag(doc, INFO, "L06", f"В содержании записи без отточия и номера страницы: «{loose[0].text[:60]}»"
                  f"{' и др.' if len(loose) > 1 else ''} — после заголовка ставят отточие и номер страницы",
                  loose[0], S("6.2.2"))
    if toc_rows or head is not None:
        listed = " ".join(_clean(r.text).lower() for r in toc_rows)
        missing = []
        for name in ("библиография", "ссылочные нормативные документы", "ссылочные документы", "лист регистрации изменений"):
            if name in elems and name not in listed and name != "лист регистрации изменений":
                missing.append(name)
        appx = sorted({m.group(1) for r in doc.rows for m in [APPX_HEAD.match(r.text.strip())] if m and id(r) not in doc.toc})
        for a in appx:
            if not re.search(rf"приложение\s+{a.lower()}(?![а-яa-z])", listed):
                missing.append(f"приложение {a}")
        nums = []
        for r in doc.rows:
            m = SECTION_RE.match(r.text)
            if m and "." not in m.group(1) and id(r) not in doc.toc and _is_heading(r, m, 1) and head is not None \
                    and (r.page, r.y0) > (head.page, head.y0):
                nums.append(m.group(1))
        for n in nums:
            if toc_rows and not re.search(rf"(?m)(^|\s){n}[.\s]", listed):
                missing.append(f"раздел {n}")
        if toc_rows and missing:
            _flag(doc, WARNING, "L07", "В содержании нет: " + ", ".join(missing[:8]) + ("…" if len(missing) > 8 else "")
                  + " — в содержание включают разделы, приложения, библиографию", head, S("6.2.2, 6.3.8, 6.4.3"))


def check_numbering(doc: Doc) -> None:
    items = []          # (parts, row, heading?)
    for r in doc.rows:
        if id(r) in doc.toc or r.first_page and len(doc.drw.pages) > 1 and r.y0 < 20:
            continue
        t = r.text.strip()
        m = SECTION_RE.match(t)
        if m and r.x0 < doc.left + 20:
            parts = tuple(int(x) for x in m.group(1).split("."))
            level = len(parts)
            items.append((parts, r, m, level))
    # L08 точка после номера раздела
    for parts, r, m, level in items:
        if m.group(2) == "." and _is_heading(r, m, level) and level <= 2 or (m.group(2) == "." and level == 1 and r.bold):
            _flag(doc, WARNING, "L08", f"«{r.text[:50]}»: в конце номера {'раздела' if level == 1 else 'подраздела'} точку "
                  f"не ставят (1 Общие положения, а не «1. Общие положения»)", r, S("6.5.4"))
            break
    # L09 последовательность
    last: dict = {}
    problems = []
    for parts, r, m, level in items:
        if len(parts) == 1 and not _is_heading(r, m, 1) and not (r.bold):
            continue
        parent = parts[:-1]
        exp = last.get(parent, 0) + 1
        if parts[-1] != exp:
            if parts[-1] > exp and (parent == () or last.get(parent, 0) > 0 or True):
                problems.append((r, ".".join(map(str, parts)), exp, parent, "пропущен номер" if parts[-1] > exp else "повтор или нарушен порядок"))
            else:
                problems.append((r, ".".join(map(str, parts)), exp, parent, "повтор или нарушен порядок"))
        last[parent] = parts[-1]
        for k in [k for k in last if len(k) > len(parts) - 0 and k[:len(parts)] == parts]:
            del last[k]
    for r, num, exp, parent, why in problems[:3]:
        want = ".".join(map(str, parent + (exp,)))
        _flag(doc, WARNING, "L09", f"Нумерация: «{r.text[:40]}» — {num}, ожидается {want} ({why}). Разделы, подразделы и "
              f"пункты нумеруют подряд арабскими цифрами в пределах родительского элемента", r, S("6.5.4–6.5.9"))
    # L10 заголовки
    seen = 0
    for parts, r, m, level in items:
        if level > 2 or not _is_heading(r, m, level) or seen >= 6:
            continue
        text = m.group(3).strip()
        why = []
        if re.search(r"\.$", text) and text.count(". ") == 0:
            why.append("точка в конце")
        if text[:1].islower():
            why.append("не с прописной буквы")
        if not r.bold:
            why.append("не полужирным шрифтом")
        if re.search(r"[А-Яа-я]-$", text):
            why.append("перенос слова")
        if why:
            seen += 1
            _flag(doc, WARNING, "L10", f"Заголовок «{r.text[:60]}»: " + ", ".join(why) + " — заголовки печатают с "
                  f"прописной буквы без точки в конце, полужирным шрифтом, без переносов", r, S("6.6.2"))
    # L11 расстояния до заголовков (по умолчанию выключено)
    rows = doc.rows
    pos = {id(r): i for i, r in enumerate(rows)}
    for parts, r, m, level in items:
        if level != 1 or not _is_heading(r, m, 1):
            continue
        i = pos[id(r)]
        gaps = []
        if i + 1 < len(rows) and rows[i + 1].page == r.page:
            gaps.append(rows[i + 1].y0 - r.y1)
        if i > 0 and rows[i - 1].page == r.page:
            gaps.append(r.y0 - rows[i - 1].y1)
        if gaps and min(gaps) < 2.0 * (doc.body_pt * PT) * 0.9:
            _flag(doc, INFO, "L11", f"Заголовок раздела «{r.text[:40]}»: расстояние до соседнего текста {min(gaps):.1f} мм — "
                  f"должно быть не менее четырёх высот основного шрифта", r, S("6.6.3"))
            break
    # L12 раздел с нового листа (по умолчанию выключено)
    for parts, r, m, level in items:
        if level == 1 and _is_heading(r, m, 1) and parts[0] > 1 and r.y0 > 45:
            _flag(doc, INFO, "L12", f"Раздел «{r.text[:40]}» начинается не с нового листа — каждый раздел "
                  f"рекомендуется начинать с нового листа", r, S("6.6.5"))
            break


def check_appendices(doc: Doc) -> None:
    rows = doc.rows
    heads = []
    for i, r in enumerate(rows):
        m = APPX_HEAD.match(_clean(r.text).strip())
        if m and id(r) not in doc.toc and r.y0 < 60:
            heads.append((i, r, m.group(1)))
    # L13 оформление
    for i, r, letter in heads:
        nxt = rows[i + 1] if i + 1 < len(rows) and rows[i + 1].page == r.page else None
        W = doc.w.get(r.page, 210)
        cx = (r.x0 + r.x1) / 2
        why = []
        if abs(cx - (20 + (W - 5)) / 2) > 18:
            why.append("слово «Приложение» не посередине")
        if nxt is None or not re.match(r"^\((обязательное|рекомендуемое|справочное)\)$", nxt.text.strip(), re.I):
            why.append("нет статуса в скобках («обязательное», «рекомендуемое» или «справочное»)")
        if why:
            _flag(doc, WARNING, "L13", f"«{r.text.strip()}»: " + "; ".join(why), r, S("6.3.4"))
            break
    # L14 обозначение
    letters = [l for _, _, l in heads]
    bad = [l for l in letters if l in FORBIDDEN_LETTERS]
    cyr = [l for l in letters if re.fullmatch(r"[А-ЯЁ]", l)]
    seq_bad = None
    if cyr:
        alphabet = [c for c in "АБВГДЕЖИКЛМНПРСТУФХЦШЩЭЮЯ"]
        for a, b in zip(cyr, cyr[1:]):
            if a in alphabet and b in alphabet and alphabet.index(b) != alphabet.index(a) + 1:
                seq_bad = (a, b)
                break
        if cyr[0] != "А" and len(cyr) >= 1 and "А" in alphabet and not re.search(r"[A-Z]", "".join(letters)):
            seq_bad = seq_bad or ("начало", cyr[0])
    if bad:
        _flag(doc, WARNING, "L14", f"Приложение обозначено буквой «{bad[0]}» — для обозначения приложений не используют "
              f"Ё, З, Й, О, Ч, Ь, Ы, Ъ", heads[letters.index(bad[0])][1], S("6.3.5"))
    elif seq_bad:
        _flag(doc, WARNING, "L14", "Обозначения приложений идут не подряд: " + ", ".join(letters) + " — приложения "
              "обозначают прописными буквами по алфавиту, начиная с А", heads[0][1], S("6.3.5"))
    # L15 ссылки на приложения
    body = [r for r in rows if id(r) not in doc.toc and not APPX_HEAD.match(_clean(r.text).strip())]
    first_ref = {}
    for r in body:
        for m in re.finditer(r"(?i)приложени\w*\s+([А-ЯЁA-Z])(?![А-Яа-яA-Za-z])", r.text):
            first_ref.setdefault(m.group(1), (r.page, r.y0))
    missing = [l for l in letters if l not in first_ref]
    if missing:
        _flag(doc, WARNING, "L15", "В тексте нет ссылок на приложение " + ", ".join(missing) + " — на все приложения "
              "должны быть даны ссылки", heads[0][1], S("6.3.3"))
    else:
        order = [l for l in sorted(first_ref, key=lambda k: first_ref[k]) if l in letters]
        pos_app = [l for l in letters]
        if order and order != [l for l in pos_app if l in order]:
            _flag(doc, INFO, "L15", "Приложения расположены не в порядке ссылок на них в тексте: порядок ссылок " +
                  ", ".join(order) + ", порядок приложений " + ", ".join(pos_app), heads[0][1], S("6.3.3"))
    # L16 нумерация внутри приложения
    cur = None
    bounds = [(h[0], h[2]) for h in heads]
    for i, r in enumerate(rows):
        for bi, letter in bounds:
            if i == bi:
                cur = letter
        m = APPX_SEC.match(r.text.strip())
        if m and cur and id(r) not in doc.toc and m.group(1) != cur and re.fullmatch(r"[А-ЯЁ]", m.group(1)):
            _flag(doc, WARNING, "L16", f"«{r.text[:50]}»: в приложении {cur} перед номером ставится обозначение этого "
                  f"приложения ({cur}.1, {cur}.2), а указано «{m.group(1)}»", r, S("6.3.7"))
            break


def check_tables_figures(doc: Doc) -> None:
    rows = [r for r in doc.rows if id(r) not in doc.toc]
    tabs, figs, conts = [], [], []
    for r in rows:
        t = _clean(r.text).strip()
        m = TABLE_CAP.match(t)
        if m and _caption_rest(m.group(3)):
            tabs.append((r, m))
        mc = re.match(r"^Продолжение\s+таблицы\s+(?:([А-ЯA-Z])\.)?(\d{1,3}(?:\.\d{1,2})?)", t)
        if mc:
            conts.append((r, mc))
        m = FIG_CAP.match(t)
        if m and _caption_rest(m.group(3)):
            figs.append((r, m))

    def num(m):
        return (m.group(1) or "") + ("." if m.group(1) else "") + m.group(2)

    def seq_check(items, kind, code, std):
        groups: dict = defaultdict(list)
        for r, m in items:
            groups[m.group(1) or ""].append((r, m))
        for letter, lst in groups.items():
            nums = []
            for r, m in lst:
                nums.append(m.group(2))
            plain = [n for n in nums if "." not in n]
            if len(plain) == len(nums) and plain:
                ints = [int(n) for n in plain]
                exp = list(range(1, len(ints) + 1))
                if ints != exp and len(set(ints)) == len(ints) or (ints != exp and len(set(ints)) != len(ints)):
                    r = lst[0][0]
                    _flag(doc, WARNING, code, f"{kind} {('приложения ' + letter) if letter else ''}нумеруются не подряд: "
                          f"{', '.join((letter + '.' if letter else '') + str(n) for n in ints[:10])} (должно быть "
                          f"{(letter + '.' if letter else '')}1, {(letter + '.' if letter else '')}2…)", r, std)
                    return
    seq_check(tabs, "Таблицы ", "L17", S("6.8.2"))
    # L17: в приложении номер с обозначением приложения
    cur = None
    app_rows = {id(r): None for r in rows}
    appx_pos = []
    for r in doc.rows:
        m = APPX_HEAD.match(_clean(r.text).strip())
        if m and id(r) not in doc.toc and r.y0 < 60:
            appx_pos.append(((r.page, r.y0), m.group(1)))
    def appx_at(r):
        a = None
        for key, letter in appx_pos:
            if key <= (r.page, r.y0):
                a = letter
        return a
    for r, m in tabs:
        a = appx_at(r)
        if a and not m.group(1) and re.fullmatch(r"[А-ЯA-Z]", a):
            _flag(doc, WARNING, "L17", f"«{r.text[:40]}»: таблицы приложения обозначают с буквой приложения "
                  f"(Таблица {a}.1)", r, S("6.8.2"))
            break
        if not a and m.group(1):
            _flag(doc, WARNING, "L17", f"«{r.text[:40]}»: буква в номере таблицы есть, а приложения на этом месте нет",
                  r, S("6.8.2"))
            break
    # L18 формат наименования
    for r, m in tabs:
        rest = m.group(3).strip()
        why = None
        if rest and rest[0] not in DASHES:
            why = "после номера ставят тире («Таблица 1 — Наименование»)"
        elif rest and rest[0] == "-":
            why = "вместо тире (—) использован дефис"
        elif rest and len(rest) > 1 and rest[1:].strip()[:1].islower():
            why = "наименование начинают с прописной буквы"
        elif rest and rest.rstrip().endswith("."):
            why = "в конце наименования точку не ставят"
        if why:
            _flag(doc, WARNING, "L18", f"«{r.text[:60]}»: {why}", r, S("6.8.1"))
            break
    # L19 ссылки на таблицы
    cap_nums = {num(m) for _, m in tabs}
    refs = {}
    for r in rows:
        t = _clean(r.text).strip()
        if TABLE_CAP.match(t) and any(r is x for x, _ in tabs) or t.startswith("Продолжение таблицы"):
            continue
        for m in re.finditer(r"(?i)\bтаблиц\w*\s+(?:([А-ЯA-Z])\.)?(\d{1,3}(?:\.\d{1,2})?)(?!\d)", t):
            refs.setdefault((m.group(1) or "") + ("." if m.group(1) else "") + m.group(2), r)
    no_ref = [n for n in sorted(cap_nums) if n not in refs]
    ghost = [n for n in sorted(refs) if n not in cap_nums]
    if cap_nums and no_ref:
        _flag(doc, WARNING, "L19", "На таблицы " + ", ".join(no_ref[:8]) + " нет ссылок в тексте — на все таблицы "
              "должны быть даны ссылки (слово «таблица» с номером)", next(r for r, m in tabs if num(m) == no_ref[0]),
              S("6.8.3"))
    elif ghost and cap_nums:
        _flag(doc, WARNING, "L19", f"Ссылка на таблицу {ghost[0]}, которой в документе нет (есть: "
              f"{', '.join(sorted(cap_nums)[:8])})", refs[ghost[0]], S("6.8.3"))
    # L20 продолжение таблицы
    names = defaultdict(int)
    for r, m in tabs:
        names[num(m)] += 1
    dup = [n for n, c in names.items() if c > 1]
    if dup:
        r = next(r for r, m in tabs if num(m) == dup[0])
        _flag(doc, WARNING, "L20", f"Заголовок «Таблица {dup[0]}» повторяется — при переносе таблицы слово «Таблица» "
              f"указывают один раз, над следующими частями пишут «Продолжение таблицы {dup[0]}»", r, S("6.8.7"))
    else:
        for r, m in conts:
            n = (m.group(1) + "." if m.group(1) else "") + m.group(2)
            if n not in cap_nums and cap_nums:
                _flag(doc, WARNING, "L20", f"«{r.text[:50]}»: таблицы {n} в документе нет", r, S("6.8.7"))
                break
    # L21 графа «Номер по порядку»
    for r in doc.rows:
        if re.fullmatch(r"(?i)(№\s*п\s*/\s*п\.?|№\s*по\s*порядку|номер\s+по\s+порядку|№\s*п\.\s*п\.?|№\s*пп\.?)", r.text.strip()):
            _flag(doc, WARNING, "L21", f"Графа «{r.text.strip()}»: графу «Номер по порядку» в таблицу включать не "
                  f"допускается — при необходимости порядковые номера указывают в боковике перед наименованием",
                  r, S("6.8.8"))
            break
    # рисунки
    seq_check(figs, "Рисунки ", "L22", S("6.9.3"))
    for r, m in figs:
        rest = m.group(3).strip()
        why = None
        if rest and rest[0] not in DASHES:
            why = "после номера ставят тире («Рисунок 1 — Детали прибора»)"
        elif rest and rest[0] == "-":
            why = "вместо тире (—) использован дефис"
        elif rest and rest.rstrip().endswith("."):
            why = "в конце наименования точку не ставят"
        if why:
            _flag(doc, WARNING, "L23", f"«{r.text[:60]}»: {why}", r, S("6.9.4"))
            break
    fnums = {num(m) for _, m in figs}
    frefs = {}
    for r in rows:
        t = _clean(r.text).strip()
        if FIG_CAP.match(t) and any(r is x for x, _ in figs):
            continue
        for m in re.finditer(r"(?i)\bрисун(?:ок|к\w*)\s+(?:([А-ЯA-Z])\.)?(\d{1,3}(?:\.\d{1,2})?)(?!\d)", t):
            frefs.setdefault((m.group(1) or "") + ("." if m.group(1) else "") + m.group(2), r)
    gh = [n for n in sorted(frefs) if n not in fnums]
    if fnums and gh:
        _flag(doc, WARNING, "L24", f"Ссылка на рисунок {gh[0]}, которого в документе нет (есть: "
              f"{', '.join(sorted(fnums)[:8])})", frefs[gh[0]], S("6.9.3"))
    elif len(fnums) > 1:
        nr = [n for n in sorted(fnums) if n not in frefs]
        if nr:
            _flag(doc, WARNING, "L24", "На рисунки " + ", ".join(nr[:8]) + " нет ссылок в тексте (допускается не "
                  "нумеровать небольшие рисунки без ссылок)", next(r for r, m in figs if num(m) == nr[0]), S("6.9.3"))


def check_formulas(doc: Doc) -> None:
    nums = []
    for ln in doc.segs:
        m = re.fullmatch(r"\(((?:[А-ЯA-Z]\.)?\d{1,3}(?:\.\d{1,2})?)\)", ln.text.strip())
        if m and ln.bbox[0] > doc.w.get(ln.page, 210) - 45:
            nums.append((ln, m.group(1)))
    nums.sort(key=lambda x: (x[0].page, x[0].bbox[1]))
    plain = [n for _, n in nums if re.fullmatch(r"\d+", n)]
    if len(plain) >= 2 and [int(n) for n in plain] != list(range(1, len(plain) + 1)):
        ln = nums[0][0]
        doc.drw.add(WARNING, "L25", CAT_TD, f"Формулы нумеруются не подряд: ({'), ('.join(plain[:10])}) — нумерация "
                    f"сквозная арабскими цифрами в круглых скобках справа", ln.page, ln.bbox, S("6.10.4"))
    for r in doc.rows:
        if id(r) in doc.toc:
            continue
        t = r.text
        m = re.search(r"(?i)\bформул\w*\s+(\d{1,3}(?:\.\d{1,2})?)(?![\d)])", t)
        if m:
            _flag(doc, WARNING, "L26", f"«{t[max(0, m.start() - 20):m.end() + 10].strip()}»: ссылки на номера формул "
                  f"дают в скобках («по формуле (1)»)", r, S("6.10.4"))
            break
    for r in doc.rows:
        if re.match(r"^где\s*:", r.text.strip()):
            _flag(doc, WARNING, "L27", f"«{r.text[:40]}»: после слова «где» двоеточие не ставят", r, S("6.10.1"))
            break


def check_references(doc: Doc) -> None:
    rows = [r for r in doc.rows if id(r) not in doc.toc]
    text_all = " ".join(r.text for r in rows)
    # L28 ссылки на пункты, таблицы, рисунки других документов
    stdref = r"(?:ГОСТ|ОСТ|СТО|ТУ)\s*(?:Р\s*)?\d[\d.]*(?:\s*[-–]\s*\d{2,4})?"
    part = r"(?:пункт\w*|п\.|подраздел\w*|таблиц\w*|рисун(?:ок|к\w*))\s+[\d.А-Я]+"
    pats = (rf"{part}\s*(?:в|по|из|к)?\s*{stdref}", rf"{stdref}\s*,?\s*(?:\()?{part}")
    for r in rows:
        mm = None
        for pat in pats:
            mm = re.search(pat, r.text, re.I)
            if mm:
                break
        if mm:
            _flag(doc, WARNING, "L28", f"«{mm.group(0).strip()}»: ссылки на подразделы, пункты, таблицы и рисунки других "
                  f"документов не допускаются — ссылаются на документ в целом, его разделы и приложения", r, S("6.11.2"))
            break
    # L29 ссылки без года и перечень «Ссылочные нормативные документы»
    nogod = [(r, m) for r in rows for m in re.finditer(r"(?<![А-Яа-яA-Za-z])(ГОСТ(?:\s*Р)?)\s+(\d[\d.]*)(?!\s*[-–]\s*\d|\d)", r.text)]
    has_list = bool(re.search(r"(?mi)^\s*Ссылочные нормативные документы", "\n".join(r.text for r in doc.rows)))
    if nogod and not has_list:
        r, m = nogod[0]
        _flag(doc, WARNING, "L29", f"«{m.group(0)}» без года, а перечня «Ссылочные нормативные документы» в конце документа "
              f"нет — год можно не указывать только при записи обозначений с годом в этом перечне", r, S("6.11.3"))
    # L30 годы в ссылках и перечне
    if has_list:
        ids = [r for r in doc.rows if re.match(r"(?i)^\s*Ссылочные нормативные документы", r.text)]
        if ids:
            lr = ids[-1]
            tail = [r for r in doc.rows if (r.page, r.y0) > (lr.page, lr.y0)]
            years = {}
            for r in tail:
                for m in re.finditer(r"ГОСТ(?:\s*Р)?\s+(\d[\d.]*)\s*[-–]\s*(\d{2,4})", r.text):
                    years[m.group(1)] = m.group(2)
            for r in rows:
                if (r.page, r.y0) >= (lr.page, lr.y0):
                    break
                for m in re.finditer(r"ГОСТ(?:\s*Р)?\s+(\d[\d.]*)\s*[-–]\s*(\d{2,4})", r.text):
                    if m.group(1) in years and years[m.group(1)] != m.group(2):
                        _flag(doc, WARNING, "L30", f"«{m.group(0)}»: в перечне ссылочных документов {m.group(1)} указан с "
                              f"годом {years[m.group(1)]} — годы в тексте и перечне не совпадают", r, S("6.11.3"))
                        return


def check_notes(doc: Doc) -> None:
    rows = [r for r in doc.rows if id(r) not in doc.toc]
    body = doc.body_pt
    notes = 0
    for i, r in enumerate(rows):
        t = _clean(r.text).strip()
        m = re.match(r"^(Примечани[ея])(.*)$", t)
        if m:
            rest = m.group(2).strip()
            word, num_after = m.group(1), None
            why = None
            if word == "Примечание":
                if not rest or rest[0] not in "—–―":
                    why = "после слова «Примечание» ставится тире («Примечание — Текст»)"
                elif rest[0] != "—" and rest[0] != "―":
                    why = "тире записывают как «—», не «–»" if False else None
            else:
                if rest and rest[0] in "—–―:":
                    why = "при нескольких примечаниях слово «Примечания» ставят отдельно, примечания нумеруют (1, 2…)"
            if why and notes < 3:
                _flag(doc, WARNING, "L31", f"«{t[:50]}»: {why}", r, S("6.12.3"))
                notes += 1
            # L32: примечание не содержит требований
            txt = rest
            j = i + 1
            while j < len(rows) and rows[j].page == r.page and rows[j].y0 - rows[j - 1].y1 < 0.8 * (r.size_pt * PT) \
                    and not re.match(r"^(Примеч|Пример\b|\d+\s)", rows[j].text):
                txt += " " + rows[j].text
                j += 1
            if re.search(r"(?i)(?<![А-Яа-я])(должен|должна|должно|должны|следует|необходимо|не допускается|запрещается|"
                         r"требуется|не должен)(?![А-Яа-я])", txt):
                _flag(doc, WARNING, "L32", f"«{t[:60]}»: примечания не должны содержать требований (слова «должен», "
                      f"«следует», «не допускается» и т. п.) — требования излагают в тексте", r, S("6.12.1"))
            # L33 размер шрифта
            if body and r.size_pt >= body - 0.4 and notes < 6:
                _flag(doc, INFO, "L33", f"«{t[:40]}»: примечание набрано шрифтом основного текста ({r.size_pt:.0f} пт) — "
                      f"примечания выделяют уменьшенным размером шрифта (на 2 пт меньше)", r, S("6.12.2"))
                notes += 1
                break
    for r in rows:
        t = _clean(r.text).strip()
        m = re.match(r"^(Примеры?)\s*([:.\-–]?)", t)
        if m and (m.group(2) in (":", ".", "-")) and len(t) > len(m.group(1)) + 1:
            _flag(doc, INFO, "L34", f"«{t[:50]}»: после слова «Пример» ставится тире («Пример — …»); примеры выделяют "
                  f"полужирным курсивом уменьшенного размера", r, S("6.14.2"))
            break
    for r in rows:
        if re.search(r"(?<![\\*\w])\*{4,}", r.text):
            _flag(doc, INFO, "L35", f"«{r.text[:40]}»: более трёх звёздочек в сносках применять не рекомендуется",
                  r, S("6.13.5"))
            break


# ------------------------------------------------------------------------------------------ оформление ----
def check_typography(doc: Doc) -> None:
    rows = [r for r in doc.rows if id(r) not in doc.toc and len(r.text) >= 25 and not r.first_page]
    if len(rows) < 8:
        rows = [r for r in doc.rows if len(r.text) >= 25]
    if len(rows) < 6:
        return
    fam = Counter()
    for r in rows:
        for f in set(r.fonts):
            k = _family(f)
            if k and not re.search(r"symbol|math|wingding|cambria", k):
                fam[k] += len(r.text)
    ALLOWED = ("timesnewroman", "arial", "times-roman", "timesnewromanps", "arialmt", "liberationserif", "liberationsans")
    bad = [k for k in fam if not any(k.startswith(a.replace("-", "")) or k == a for a in ALLOWED)
           and not k.startswith(("times", "arial", "liberation"))]
    if bad:
        top = max(bad, key=lambda k: fam[k])
        r = next(r for r in rows if any(_family(f) == top for f in r.fonts))
        _flag(doc, WARNING, "L36", f"Гарнитура шрифта «{top}»: по ГОСТ Р 2.105 применяют Times New Roman или Arial",
              r, S("5.1.1"))
    kinds = {"times" if k.startswith(("times", "liberationserif")) else "arial" if k.startswith(("arial", "liberationsans")) else k
             for k in fam if fam[k] > 40}
    if len(kinds) > 1 and not bad:
        _flag(doc, INFO, "L37", "В документе использованы разные гарнитуры (" + ", ".join(sorted(kinds)) + ") — "
              "использование различных гарнитур в одном документе не рекомендуется", page=rows[0].page, std=S("5.1.1"))
    sizes = Counter()
    for r in rows:
        sizes[round(r.size_pt * 2) / 2] += len(r.text)
    body = doc.body_pt
    if body and not any(abs(body - a) <= 0.6 for a in (14, 13)):
        r = next(r for r in rows if abs(round(r.size_pt * 2) / 2 - body) < 0.3)
        _flag(doc, WARNING, "L38", f"Размер основного шрифта {body:g} пт — для основного текста применяют 14 пт "
              f"(допускается 13 пт)", r, S("5.1.1"))
    elif body:
        small = body - 2
        bad_sizes = [s for s in sizes if s != body and abs(s - small) > 0.6 and abs(s - body) > 0.6 and sizes[s] > 60
                     and s < body + 0.1 and s >= 8]
        used = {s for s in sizes if sizes[s] > 60}
        if len([s for s in used if s <= body + 0.1]) > 2 or bad_sizes:
            r = next(r for r in rows if round(r.size_pt * 2) / 2 in (bad_sizes or [min(used)]))
            _flag(doc, WARNING, "L39", f"Размеры шрифта {', '.join(f'{s:g}' for s in sorted(used))} пт: допустимые сочетания "
                  f"— 14 и 12 или 13 и 11 пт; использование различных сочетаний в одном документе не допускается",
                  r, S("5.1.1"))
    # L40 межстрочный интервал
    gaps = []
    for a, b in zip(rows, rows[1:]):
        if a.page == b.page and abs(a.size_pt - body) < 0.6 and abs(b.size_pt - body) < 0.6 and 0 < b.y1 - a.y1 < 3 * body * PT \
                and abs(a.x1 - b.x1) < 200:
            gaps.append((b.y1 - a.y1) / (body * PT))
    if len(gaps) >= 10:
        gaps.sort()
        med = gaps[len(gaps) // 2]
        if med < 1.45:
            _flag(doc, INFO, "L40", f"Межстрочный интервал около {med:.2f} размера шрифта — текст оформляют с "
                  f"полуторным (допускается двойным) межстрочным интервалом", page=rows[0].page, std=S("5.1.2"))
    # L41, L42 расстояния до рамки (по умолчанию выключено)
    side = [r for r in doc.rows if r.x0 < 23 and abs(r.x0 - doc.left) > 0.1 and r.x0 >= 20]
    right = [r for r in doc.rows if r.x1 > doc.w.get(r.page, 210) - 8 and r.x1 <= doc.w.get(r.page, 210) - 4]
    if side or right:
        r = (side or right)[0]
        _flag(doc, INFO, "L41", f"«{r.text[:40]}»: расстояние от рамки до текста менее 3 мм (рамка принята по форме 2/2а: "
              f"слева 20 мм, справа 5 мм)", r, S("5.1.3"))
    top = [r for r in doc.rows if r.y0 < 15]
    if top:
        _flag(doc, INFO, "L42", f"«{top[0].text[:40]}»: расстояние от верхней строки до рамки менее 10 мм (рамка на "
              f"расстоянии 5 мм от края листа)", top[0], S("5.1.3"))
    # L43 абзацный отступ
    left = doc.left
    ind = []
    for a, b in zip(doc.rows, doc.rows[1:]):
        if b.page == a.page and abs(b.size_pt - body) < 0.6 and 3 < b.x0 - left < 25 and len(b.text) > 30 \
                and abs(a.x0 - left) < 1.2 and id(b) not in doc.toc:
            ind.append(b.x0 - left)
    if len(ind) >= 6:
        ind.sort()
        med = ind[len(ind) // 2]
        spread = ind[-1 - len(ind) // 10] - ind[len(ind) // 10]
        if med < 12.5 - 0.8 or med > 17 + 0.8:
            _flag(doc, WARNING, "L43", f"Абзацный отступ ≈{med:.1f} мм — должен быть равен пяти знакам шрифта "
                  f"(12,5—17 мм)", page=doc.rows[0].page, std=S("5.1.4"))
        elif spread > 2.0:
            _flag(doc, WARNING, "L43", f"Абзацный отступ неодинаков по документу (от {ind[0]:.1f} до {ind[-1]:.1f} мм) — "
                  f"он должен быть одинаковым", page=doc.rows[0].page, std=S("5.1.4"))


# ------------------------------------------------------------------------------------------ текст ----
def _prose_rows(doc: Doc):
    for r in doc.rows:
        if id(r) in doc.toc or not _prose(r.text):
            continue
        yield r


def check_text(doc: Doc) -> None:
    found: dict = {}

    def hit(code, r, msg, sev=INFO, std=""):
        if code not in found:
            found[code] = 1
            _flag(doc, sev, code, msg, r, std)

    for r in _prose_rows(doc):
        t = r.text
        m = re.search(r"(?<![А-Яа-я])(?:рис|табл)\.(?!\s*[А-ЯA-Z0-9]\.)", t)
        if m and not re.search(r"(?i)(?:^|\s)см\.\s*(?:рис|табл)", t) or m and re.search(r"(?<![А-Яа-я])(?:рис|табл)\.\s*\d", t):
            hit("L44", r, f"«{t[max(0, m.start() - 15):m.end() + 12].strip()}»: слова «рисунок», «таблица» в тексте не "
                f"сокращают (по рисунку 2, в таблице 3)", WARNING, S("5.2.3, 6.9.3"))
        m = re.search(r"(?<![А-Яа-я\d])(?:в|на|по|от|до|за|через|около|не более|не менее)\s+(мм|см|кг|мин|мкм|МПа|кПа|кВт|Вт|°С)(?![А-Яа-я])", t)
        if m:
            hit("L45", r, f"«{t[max(0, m.start() - 10):m.end() + 10].strip()}»: обозначение единицы без числа в тексте не "
                f"сокращают — пишут словом («в миллиметрах»)", INFO, S("5.2.3"))
        m = re.search(r"[⌀∅Ø]\s*\d", t)
        if m:
            hit("L46", r, f"«{t[max(0, m.start() - 15):m.end() + 10].strip()}»: в тексте документа знак «⌀» для обозначения "
                f"диаметра не применяют — пишут слово «диаметр» (на рисунках, в формулах и таблицах знак допустим)",
                INFO, S("5.2.4"))
        m = re.search(r"(?:^|(?<=\s))[–−]\s?\d", t)
        if m:
            hit("L47", r, f"«{t[max(0, m.start() - 15):m.end() + 12].strip()}»: перед отрицательным значением в тексте "
                f"пишут слово «минус», а не знак «–»", INFO, S("5.2.4"))
        m = re.search(r"(?<![\d\s])\s*[<>=≥≤≠](?!\s*[-+]?\d)|№(?!\s*\d)|(?<![\d\s])\s*%", t)
        if m:
            hit("L48", r, f"«{t[max(0, m.start() - 15):m.end() + 12].strip()}»: математические знаки, № и % без числовых "
                f"значений в тексте не применяют — пишут словами («не более», «номер», «процент»)", INFO, S("5.2.4"))
        m = re.search(r"(?i)\bпо\s+(ТУ|ОСТ|СТО|СТП)(?![^\n]{0,18}\d)", t)
        if m:
            hit("L49", r, f"«{t[max(0, m.start()):m.end() + 12].strip()}»: индекс стандарта или технических условий без "
                f"регистрационного номера не допускается", WARNING, S("5.2.4"))
        m = re.search(r"(?<![А-Яа-я\d,.])(кгс(?:/см²?)?|ккал|Гс|л\.\s?с\.)(?![А-Яа-я])", t)
        if m:
            hit("L51", r, f"«{m.group(1)}»: единица вне Международной системы СИ — применяют единицы по ГОСТ 8.417 "
                f"(допускается в скобках указывать ранее применявшиеся)", INFO, S("6.16.1, 6.16.2"))
        m = re.search(rf"\b(\d+(?:,\d+)?)\s*({UNIT})\s*(?:до|…|\.\.\.)\s*(\d+(?:,\d+)?)\s*\2(?![А-Яа-я])", t)
        if m and m.group(2) not in ("°С", "%", "°"):
            hit("L52", r, f"«{m.group(0)}»: при диапазоне значений единицу указывают один раз — после последнего "
                f"числа («от 5 до 10 {m.group(2)}»)", WARNING, S("6.16.5"))
        m = re.search(rf"(?<![\d.,])(\d+(?:,\d+)?)\s*[–—-]\s*(\d+(?:,\d+)?)\s*({UNIT})(?![А-Яа-я])", t)
        if m and not re.search(r"\d{4}\s*[–—-]\s*\d{2}", t[max(0, m.start() - 3):m.end()]):
            hit("L56", r, f"«{m.group(0)}»: диапазон значений с единицей записывают со словами «от» и «до» («от "
                f"{m.group(1)} до {m.group(2)} {m.group(3)}»), тире — для порядковых номеров", INFO, S("6.8.20"))
        m = re.search(rf"(?<![\d.])(0\.\d+|\d+\.\d+\s*(?:{UNIT}))(?![\d.])", t)
        if m and not re.search(r"(?i)гост|ост\b|ту\b|п\.|рисун|таблиц|раздел|приложени|ред\.|версия", t[max(0, m.start() - 14):m.start()]):
            hit("L55", r, f"«{m.group(0).strip()}»: десятичную дробь отделяют запятой, а не точкой", INFO, S("6.16.9"))
        m = re.search(r"(?<![\d.])(\d{2})\.(\d{2})\.(\d{2})(?![\d.])", t)
        if m and 1 <= int(m.group(1)) <= 31 and 1 <= int(m.group(2)) <= 12:
            hit("L57", r, f"«{m.group(0)}»: с 2000 г. год в дате записывают четырьмя цифрами", INFO, S("приложение В"))
        # ряд чисел с разным числом знаков
        m = re.search(r"(?<![\d,])(\d+(?:,\d+)?(?:;\s*\d+(?:,\d+)?){2,})\s*(?:%s)?" % UNIT, t)
        if m:
            nums = re.findall(r"\d+(?:,(\d+))?", m.group(1))
            if len({len(n) for n in nums}) > 1:
                hit("L54", r, f"«{m.group(1)}»: в ряду значений выравнивают число знаков после запятой "
                    f"(1,50; 1,75; 2,00)", INFO, S("6.16.8"))
        # L50 числа 1–9 без единиц
        for m in re.finditer(r"(?<![\w.,№/−–-])(?:\s)([1-9])\s+(?=[а-яё]{3,})", " " + t):
            prev = (" " + t)[max(0, m.start() - 22):m.start() + 1].lower()
            nxt = (" " + t)[m.end():m.end() + 14].lower()
            if re.search(r"(пункт|п\.|раздел|таблиц|рисун|приложени|гост|формул|графе|поз|лист|стр|номер|№|версии?|класс|этап|"
                         r"уровень|категори|группа|вариант|исполнени|тип|ряд|степен)\w*\s*$", prev) \
                    or re.match(rf"({UNIT})", nxt) or re.match(r"(шт|раз|штук|мм|кг|м\b|ч\b|с\b|лет|год|мес|сут|дн|%|°)", nxt):
                continue
            hit("L50", r, f"«{(' ' + t)[max(0, m.start() - 8):m.end() + 14].strip()}»: числа от одного до девяти без "
                f"обозначения единицы величины или единицы счёта в тексте пишут словами", INFO, S("6.16.3"))
            break
    # L53 единица отделена от числа переносом
    rows = doc.rows
    for a, b in zip(rows, rows[1:]):
        if re.search(r"\d\s*$", a.text) and re.match(rf"^({UNIT})(?![А-Яа-я])", b.text.strip()) and a.page == b.page \
                and _prose(a.text, 3) and not re.fullmatch(r"[\d\s]+", b.text):
            _flag(doc, WARNING, "L53", f"«…{a.text[-20:].strip()} | {b.text[:15].strip()}»: единицу величины отделили от "
                  f"числового значения переносом на другую строку — это недопустимо", b, S("6.16.6"))
            break
    # L58–L59 перечисления
    letters_run: list = []
    for i, r in enumerate(rows):
        t = r.text.strip()
        if re.match(r"^[•·●▪■◦○∙*]\s+\S", t) and r.x0 > doc.left - 1 and _prose(t):
            _flag(doc, WARNING, "L58", f"«{t[:40]}»: перед позицией перечисления ставят дефис или строчную букву со "
                  f"скобкой (а), б), в)), а затем цифру со скобкой (1), 2)); маркеры-точки не применяют", r, S("6.7.2"))
            break
        if re.match(r"^[а-яa-z]\.\s+[а-яa-z]", t) and len(t) > 10:
            _flag(doc, WARNING, "L58", f"«{t[:40]}»: после буквы перечисления ставят скобку, а не точку («а) …»)", r,
                  S("6.7.2"))
            break
    run = []
    for r in rows + [None]:
        m = re.match(r"^([а-яёa-z])\)\s", r.text.strip()) if r is not None else None
        if m:
            run.append((m.group(1), r))
            continue
        if run and r is not None and not re.match(r"^(\d|[-—•]|[а-яa-z]\))", r.text.strip()) and run[-1][1].page == r.page \
                and r.y0 - run[-1][1].y1 < 1.3 * r.size_pt * PT and r.size_pt >= doc.body_pt - 0.5:
            run[-1] = (run[-1][0], r)                  # продолжение пункта перечисления
            continue
        if len(run) >= 2:
            alph = "абвгдежикл"
            ls = [x[0] for x in run]
            bad = [l for l in ls if l in "ёзйочьыъ"]
            skip = next(((a, b) for a, b in zip(ls, ls[1:]) if a in alph and b in alph and alph.index(b) != alph.index(a) + 1), None)
            if bad or skip or (ls[0] not in "аa"):
                what = (f"использована буква «{bad[0]}»" if bad else f"после «{skip[0]})» идёт «{skip[1]})»" if skip
                        else f"перечисление начинается с «{ls[0]})», а не с «а)»")
                _flag(doc, WARNING, "L59", f"Перечисление: {what} — буквы идут подряд по алфавиту, кроме ё, з, й, о, ч, ь, ы, ъ",
                      run[0][1], S("6.7.2"))
                break
        run = []


def check_front(doc: Doc) -> None:
    drw = doc.drw
    first = drw.pages[0].number
    # L60 обозначение листа утверждения
    for r in doc.rows:
        t = r.text
        for m in re.finditer(r"([А-ЯA-Z]{2,5}\.\d{6}\.\d{3}[А-Я]{0,3})\s*[-–—]?\s*(ЛУ)\b", t):
            if not re.fullmatch(r"[А-ЯA-Z]{2,5}\.\d{6}\.\d{3}[А-Я]{0,3}-ЛУ", m.group(0).replace(" ", "")):
                _flag(doc, WARNING, "L60", f"«{m.group(0)}»: обозначение листа утверждения — обозначение документа и через "
                      f"дефис код ЛУ (ХХХХ.ХХХХХХ.ХХХТУ-ЛУ)", r, S("8.4"))
                break
    # L61 ЛУ и титульный лист — формат А4
    for r in doc.rows:
        if re.match(r"(?i)^\s*лист\s+утверждения\s*$", r.text):
            p = next((p for p in drw.pages if p.number == r.page), None)
            if p and not (abs(min(p.width, p.height) - 210) < 6 and abs(max(p.width, p.height) - 297) < 6):
                _flag(doc, WARNING, "L61", f"Лист утверждения выполнен на листе {p.width:.0f}×{p.height:.0f} мм — "
                      f"титульный лист и лист утверждения выполняют на листах формата А4", r, S("8.9"))
                break
    # L62 наименование изделия на титульном листе и в основной надписи
    name = (drw.title.name or "").strip()
    if len(name) > 6:
        key = re.sub(r"[^а-яё0-9]+", "", name.lower().replace("ё", "е"))
        p1 = "".join(re.sub(r"[^а-яё0-9]+", "", r.text.lower().replace("ё", "е")) for r in doc.rows if r.page == first)
        if key and len(p1) > 40 and key[:12] not in p1:
            _flag(doc, WARNING, "L62", f"Наименование «{name[:50]}» из основной надписи не найдено на титульном листе — "
                  f"полное наименование изделия на титульном листе, в основной надписи и при первом упоминании в тексте "
                  f"должно быть одинаковым", page=first, std=S("5.2.1"))
    # L63 перечень принятых сокращений
    abbr = Counter()
    for r in doc.rows:
        if id(r) in doc.toc:
            continue
        for m in re.finditer(r"(?<![А-ЯA-Z\w.])([А-ЯA-Z]{2,6})(?![А-Яа-яA-Za-z\w])", r.text):
            abbr[m.group(1)] += 1
    common = {"ГОСТ", "ОСТ", "ТУ", "СТО", "РФ", "СИ", "ЕСКД", "ЕСТД", "СПДС", "ЭВМ", "ПО", "ОТК", "ГПО", "НТД", "КД", "ТД",
              "ЛУ", "ИС", "ЕС", "ООО", "АО", "ПАО", "ФГУП", "ISO", "DIN", "ОКПД", "УДК", "ИЭД", "ЭСО", "ТДЭ", "ЭЛД", "НЕТ", "ДА",
              "РЭА", "СБ", "ВО", "ПС", "ФО", "РЭ", "ПЗ", "РР", "ЭД", "ЧПУ", "ТЗ", "ЗИП", "ТО", "ИП", "ИМ", "ИЭ", "ИО", "ИВ"}
    uncommon = [a for a, n in abbr.items() if n >= 3 and a not in common and not re.fullmatch(r"[IVXLCM]+", a)]
    has_list = any(re.match(r"(?i)^(обозначения и сокращения|перечень сокращений|сокращения)\s*$", _clean(r.text).strip())
                   for r in doc.rows)
    if len(uncommon) >= 3 and not has_list:
        _flag(doc, INFO, "L63", f"Применены сокращения ({', '.join(sorted(uncommon)[:6])}…), а перечня принятых сокращений "
              f"(элемент «Обозначения и сокращения») нет", page=first, std=S("6.15.2"))


CHECKS = (check_structure, check_numbering, check_appendices, check_tables_figures, check_formulas, check_references,
          check_notes, check_typography, check_text, check_front)


def check_text_document(drw: Drawing, cfg: dict) -> None:
    from .model import CAT_FILE
    doc = build_doc(drw)
    if not doc.rows:
        return
    for chk in CHECKS:
        try:
            chk(doc)
        except Exception as e:
            drw.add(WARNING, "F07", CAT_FILE, f"Проверка «{chk.__name__}» (текстовый документ) не выполнена: "
                    f"{type(e).__name__}: {e}")
