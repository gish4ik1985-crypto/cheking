"""Спецификация по ГОСТ 2.106: загруженная СП (выгрузка ERP, отчёт КОМПАС, экспорт Solid Edge) и спецификация
на поле чертежа. Многоуровневая СП разбирается на спецификации отдельных сборочных единиц — каждая
проверяется как самостоятельный документ по форме 1."""
from __future__ import annotations

import os
import re
from collections import Counter

from .model import Drawing, ERROR, WARNING, INFO, CAT_SPEC
from .standards import fmtn
from .textnorm import norm_designation

STD = "ГОСТ Р 2.106-2019"
SECTIONS = ["Документация", "Комплексы", "Сборочные единицы", "Детали", "Программные изделия и базы данных",
            "Стандартные изделия", "Прочие изделия", "Материалы", "Комплекты"]
# графа «Кол.» необязательна (ГОСТ Р 2.106-2019, табл. 4.1): у документации не заполняют, у программных и прочих изделий по желанию
QTY_OPTIONAL = ("Документация", "Программные изделия и базы данных", "Прочие изделия")
QTY_MARK = re.compile(r"(?i)(?<![а-яё])(?:техн|приб)")      # «Техн.» / «Приб.» вместо числа у материалов (п. 4.2.17.6)


def canon_section(raw: str | None) -> str | None:
    """Название раздела из графы «Раздел»/заголовка → элемент SECTIONS (по первым 8 буквам: «Комплексы» ≠ «Комплекты»)."""
    low = (raw or "").strip().lower()
    return next((s for s in SECTIONS if low.startswith(s.lower()[:8])), None)


def qty_missing(c: dict, section: str) -> bool:
    """Количество не указано там, где графа «Кол.» обязательна. У материалов «Техн.»/«Приб.» допустимы (п. 4.2.17.6)."""
    if section in QTY_OPTIONAL or (c.get("qty") not in (None, 0)):
        return False
    return not (section == "Материалы" and QTY_MARK.search(f"{c.get('qty_raw') or ''} {c.get('note') or ''}"))
SKU_SECTION = {"1": "Сборочные единицы", "2": "Детали", "3": "Стандартные изделия", "4": "Прочие изделия",
               "5": "Материалы"}
ESKD = re.compile(r"^[А-ЯA-Z]{2,5}[.\s]?\d{6}\.\d{3}(?:-\d{2,3})?$|^[А-ЯA-Z]{1,4}\s?\d{1,3}(?:\.\d{2,3})+(?:-\d{2,3})?$")
STD_REF = re.compile(r"(?i)\b(ГОСТ|ОСТ|СТО|СТП|ТУ|DIN|ISO|EN|ИСО)\b")
STD_NUM = re.compile(r"(?:ГОСТ|ОСТ|СТО|DIN|ISO|ИСО)\s*Р?\s*(?:ИСО\s*)?([\d.]+)")


def section_of(row: dict, has_children: bool) -> str:
    found = canon_section(row.get("section"))
    if found:
        return found
    bt = (row.get("blank_type") or "").lower()
    if bt.startswith("материал"):
        return "Материалы"
    if bt.startswith("стандарт"):
        return "Стандартные изделия"
    if bt.startswith("прочее"):
        return "Прочие изделия"
    sku = (row.get("sku") or "").strip()
    if re.match(r"^\d{3}-\d{6}$", sku) and sku[0] in SKU_SECTION:
        return SKU_SECTION[sku[0]]
    if has_children:
        return "Сборочные единицы"
    if row.get("designation") and not row.get("designation_is_sku"):
        return "Детали"
    if STD_REF.search(row.get("name") or ""):
        return "Стандартные изделия"
    return "Прочие изделия"


def build_tree(spec) -> list[dict]:
    """Узлы-сборки: {"row", "children": [row…]} по номерам позиций «1.2.3» (или по графе «Обозначение сборки»)."""
    rows = [r for r in spec.rows if r.get("pos") or r.get("designation") or r.get("sku")]
    by_pos = {r["pos"]: r for r in rows if r.get("pos")}
    roots = [r for r in rows if not r.get("pos")]
    top = [r for r in rows if r.get("pos") and "." not in r["pos"]]
    root = roots[0] if roots else (top[0] if len(top) == 1 else None)
    kids: dict[int, list] = {}
    for r in rows:
        p = r.get("pos")
        if not p or r is root:
            continue
        parent = by_pos.get(p.rsplit(".", 1)[0]) if "." in p else root
        if parent is None and r.get("parent_des"):
            parent = next((x for x in rows if x.get("designation") == r["parent_des"]), None)
        if parent is not None:
            kids.setdefault(id(parent), []).append(r)
    nodes = []
    for r in ([root] if root else []) + rows:
        if r is None or id(r) not in kids or any(n["row"] is r for n in nodes):
            continue
        ch = kids[id(r)]
        for c in ch:
            c["_section"] = section_of(c, id(c) in kids)
        nodes.append({"row": r, "children": ch})
    return nodes


def _label(r: dict) -> str:
    return " ".join(x for x in (r.get("designation") if not r.get("designation_is_sku") else "", r.get("name")) if x)


def _rows_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "строка"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "строки"
    return "строк"


def _std_key(name: str):
    m = STD_NUM.search(name or "")
    nums = [int(x) for x in re.findall(r"\d+", m.group(1))] if m else []
    return nums


def _alpha_key(name: str) -> str:
    return re.split(r"[\s\d]", (name or "").strip().lower(), maxsplit=1)[0]


# ГОСТ 2.106: код документа в обозначении соответствует наименованию в разделе «Документация»
DOC_CODES = [(r"сборочн\w+\s+чертеж", ("СБ",)), (r"чертеж\s+общего\s+вида", ("ВО",)), (r"габаритн\w+\s+чертеж", ("ГЧ",)),
             (r"монтажн\w+\s+чертеж", ("МЧ",)), (r"технические\s+условия", ("ТУ",)),
             (r"руководство\s+по\s+эксплуатации", ("РЭ",)), (r"паспорт", ("ПС",)), (r"формуляр", ("ФО",)),
             (r"пояснительная\s+записка", ("ПЗ",)), (r"схема\s+электрическая\s+принципиальная", ("Э3",)),
             (r"схема\s+электрическая\s+структурная", ("Э1",)), (r"схема\s+электрическая\s+функциональная", ("Э2",)),
             (r"схема\s+электрическая\s+соединений", ("Э4",)), (r"схема\s+электрическая\s+подключения", ("Э5",)),
             (r"перечень\s+элементов", ("ПЭ3", "ПЭ")), (r"ведомость\s+покупных", ("ВП",)),
             (r"ведомость\s+спецификаций", ("ВС",))]
MATERIAL_UNITS = {"кг", "г", "т", "м", "см", "мм", "л", "мл", "м2", "м²", "м3", "м³", "дм2", "дм²", "дм3", "дм³", "кв.м",
                  "куб.м", "пог.м", "м.п."}


def check_children(add, node_name: str, children: list[dict], where=(None, None), drawing_table: bool = False) -> None:
    """Правила ГОСТ 2.106 к списку составных частей одной сборочной единицы. add(sev, code, message, page, bbox)."""
    pg, bb = where
    pref = f"«{node_name}»: " if node_name else ""
    secs = [c["_section"] for c in children]
    order = [SECTIONS.index(s) for s in secs]
    if not drawing_table:
        for i in range(1, len(order)):
            if order[i] < order[i - 1]:
                c = children[i]
                add(WARNING, "S01", f"{pref}разделы не по порядку ГОСТ 2.106 — «{secs[i]}» ({_label(c)}, поз. "
                    f"{c.get('pos')}) записан после «{secs[i - 1]}»", pg, bb)
                break
        # повторы одной составной части — одна строка с общим количеством
        keyf = lambda c: norm_designation(c["designation"]) if c.get("designation") and not c.get(
            "designation_is_sku") else (c.get("sku") or "") + "|" + re.sub(r"\s+", " ", (c.get("name") or "").lower())
        cnt = Counter(keyf(c) for c in children)
        rep = [(k, n) for k, n in cnt.items() if n > 1 and k.strip("|")]
        if rep:
            ex = [next(c for c in children if keyf(c) == k) for k, _ in rep]
            add(WARNING, "S02", f"{pref}одна и та же составная часть записана несколькими строками: "
                f"{'; '.join(f'{_label(c)} — {n} {_rows_word(n)}' for c, (_, n) in zip(ex[:6], rep[:6]))}"
                f"{' и др.' if len(rep) > 6 else ''} — записывают одной строкой с общим количеством", pg, bb)
    # сортировка: сборочные единицы и детали — по возрастанию обозначений (п. 4.2.5)
    for sec in ("Сборочные единицы", "Детали"):
        des = [norm_designation(c["designation"]) for c in children if c["_section"] == sec and c.get("designation")
               and not c.get("designation_is_sku")]
        uniq = list(dict.fromkeys(des))
        if uniq != sorted(uniq):
            bad = next(i for i in range(1, len(uniq)) if uniq[i] < uniq[i - 1])
            add(INFO, "S03", f"{pref}в разделе «{sec}» обозначения не по возрастанию: {uniq[bad - 1]} записано перед "
                f"{uniq[bad]}", pg, bb)
    # стандартные и прочие изделия — по алфавиту наименований, затем по стандарту (пп. 4.2.6, 4.2.7)
    for sec, code in (("Стандартные изделия", "S04"), ("Прочие изделия", "S05")):
        items = [c for c in children if c["_section"] == sec and c.get("name")]
        keyf = (lambda c: (_alpha_key(c["name"]), tuple(_std_key(c["name"])))) if code == "S04" else \
            (lambda c: (_alpha_key(c["name"]), ()))
        for a, b in zip(items, items[1:]):
            if keyf(b) < keyf(a):
                why = "по номеру стандарта" if keyf(a)[0] == keyf(b)[0] else "по алфавиту наименований"
                add(INFO, code, f"{pref}в разделе «{sec}» записи не {why}: «{a['name']}» (поз. {a.get('pos') or '—'}) "
                    f"записано перед «{b['name']}» (поз. {b.get('pos') or '—'})", pg, bb)
                break
    # построчные правила: для таблицы на чертеже — у каждой строки (с подсветкой), для СП — сводкой по сборке
    found: dict[str, list] = {}

    def hit(sev, code, c, text_row, text_sum):
        found.setdefault(code, [sev, text_sum, []])[2].append(c)

    for c in children:
        sec, name = c["_section"], c.get("name") or ""
        if sec in ("Сборочные единицы", "Детали", "Комплексы"):
            if c.get("designation_is_sku"):
                hit(WARNING, "S06", c, f"в графе «Обозначение» артикул {c.get('designation')} — записывают обозначение "
                    f"основного конструкторского документа (ГОСТ 2.201)",
                    "в графе «Обозначение» артикул вместо обозначения основного конструкторского документa (ГОСТ 2.201)")
            elif not c.get("designation"):
                hit(WARNING, "S06", c, "графа «Обозначение» не заполнена — для деталей и сборочных единиц записывают "
                    "обозначение основного конструкторского документа",
                    "не заполнена графа «Обозначение» у деталей/сборочных единиц")
        elif sec != "Документация" and c.get("designation") and not ESKD.match(c["designation"].replace(" ", " ")):
            hit(WARNING if drawing_table else INFO, "S07", c, f"в графе «Обозначение» «{c['designation']}» — для "
                f"стандартных и прочих изделий и материалов без своей КД графу не заполняют, обозначение стандарта "
                f"пишут в наименовании", "графа «Обозначение» заполнена у стандартных/прочих изделий или материалов "
                "(без своей КД её не заполняют)")
        if sec == "Стандартные изделия" and name and not STD_REF.search(name + " " + (c.get("material") or "")):
            hit(WARNING, "S08", c, "стандартное изделие записано без обозначения стандарта («Болт М8-6g×30.58 ГОСТ "
                "7798-70»)", "стандартные изделия записаны без обозначения стандарта")
        if not name and not c.get("designation"):
            hit(ERROR, "S14", c, "не заполнено наименование", "не заполнено наименование")
        if not drawing_table and qty_missing(c, sec):
            hit(ERROR, "S09", c, "не указано количество", "не указано количество")
        if not drawing_table and sec == "Материалы" and not (c.get("unit") or "").strip():
            hit(WARNING, "S10", c, "для материалов количество указывают с единицами измерения",
                "у материалов не указаны единицы измерения количества")
        if re.search(r"(?i)без чертеж|^бч$", (c.get("note") or "") + " " + (c.get("fmt") or "")) and sec == "Детали":
            if not (c.get("material") or re.search(r"(?i)гост|ост|ту|лист|круг|труба|швеллер|уголок|полоса", name)):
                hit(WARNING, "S11", c, "деталь без чертежа (БЧ) — указывают материал и размеры для изготовления",
                    "у деталей без чертежа (БЧ) не указаны материал и размеры")
    # --- ГОСТ 2.106-2019: форма записи
    for c in children:
        sec, name = c["_section"], (c.get("name") or "").strip()
        qty, unit = c.get("qty"), (c.get("unit") or "").strip().lower().replace(" ", "")
        if sec == "Документация":
            if c.get("pos"):
                hit(INFO, "S15", c, "у документации графу «Поз.» не заполняют",
                    "в разделе «Документация» заполнена графа «Поз.» (её не заполняют)")
            des = norm_designation(c.get("designation") or "")
            for rx, codes in DOC_CODES:
                if re.search(rx, name.replace("ё", "е").replace("Ё", "Е"), re.I):
                    if des and not any(re.search(re.escape(norm_designation(k)) + r"\d?$", des) for k in codes):
                        hit(WARNING, "S16", c, f"код документа в обозначении не соответствует наименованию "
                            f"(ожидается {'/'.join(codes)})", "код документа в обозначении не соответствует наименованию "
                            "(«Сборочный чертёж» — СБ, «Технические условия» — ТУ…)")
                    break
        elif isinstance(qty, (int, float)) and qty > 0 and abs(qty - round(qty)) > 1e-9 and sec != "Материалы"                 and not unit:
            hit(WARNING, "S17", c, "количество штучного изделия — целое число",
                "у штучных изделий количество дробное (дробные количества записывают только для материалов "
                "с единицей измерения)")
        if name and name[0].islower() and not re.match(r"[a-z0-9]", name[0]):
            hit(INFO, "S18", c, "наименование начинается со строчной буквы",
                "наименование записано со строчной буквы (в графе «Наименование» первое слово пишут с прописной)")
        if sec == "Стандартные изделия" and re.match(r"(?i)^(?:ГОСТ|ОСТ|DIN|ISO|ТУ)\b", name):
            hit(INFO, "S19", c, "обозначение стандарта в начале наименования",
                "в наименовании стандартного изделия обозначение стандарта стоит в начале (его записывают после "
                "наименования и типоразмера: «Болт М6-6g×20.58 ГОСТ 7798-70»)")
        if sec == "Материалы" and unit and unit not in MATERIAL_UNITS:
            hit(WARNING, "S20", c, f"единица измерения «{c.get('unit')}» не годится для материала",
                "у материалов единица измерения не из принятых (кг, г, т, м, мм, л, м², м³)")
    for code, (sev, text, rows) in found.items():
        names = [f"{c.get('pos') or '—'} {c.get('name') or c.get('designation')}" for c in rows]
        add(sev, code, f"{pref}{text}: {'; '.join(names[:8])}{f' и ещё {len(names) - 8}' if len(names) > 8 else ''}",
            pg, bb)


def _mass_check(add, node: dict) -> None:
    """Масса сборки = сумма масс составных частей × количество (материалы — расходные, не учитываются)."""
    r, ch = node["row"], node["children"]
    total, ok = 0.0, True
    for c in ch:
        if c["_section"] in ("Документация", "Комплекты", "Материалы"):
            continue
        m, q = c.get("mass"), c.get("qty")
        if m is None or q is None:
            ok = False
            break
        total += m * q
    if ok and r.get("mass") and total > 0:
        if abs(total - r["mass"]) > max(0.03 * r["mass"], 0.01):
            add(WARNING, "S12", f"«{_label(r)}»: масса сборки {fmtn(round(r['mass'], 3))} кг, сумма масс составных "
                f"частей {fmtn(round(total, 3))} кг (расхождение {abs(total - r['mass']) / r['mass'] * 100:.0f} %)",
                None, None)


def _positions(add, node: dict) -> None:
    """Номера позиций в порядке записи, без повторов (п. 3.17)."""
    nums = []
    for c in node["children"]:
        last = (c.get("pos") or "").rsplit(".", 1)[-1]
        if last.isdigit():
            nums.append(int(last))
    if any(b <= a for a, b in zip(nums, nums[1:])):
        dup = sorted({n for n in nums if nums.count(n) > 1})
        add(WARNING, "S13", f"«{_label(node['row'])}»: позиции не по порядку записи"
            f"{' (повторяются ' + ', '.join(map(str, dup)) + ')' if dup else ''}", None, None)


def check_spec_document(spec, cfg: dict | None = None) -> Drawing:
    """Загруженная спецификация → отдельный документ отчёта с замечаниями по ГОСТ 2.106."""
    name = os.path.basename(spec.path)
    drw = Drawing(spec.path, name, kind="spec")
    nodes = build_tree(spec)
    root = nodes[0]["row"] if nodes else None
    if root:
        drw.title.designation = "" if root.get("designation_is_sku") else root.get("designation", "")
        drw.title.name = root.get("name", "")
        drw.title.found = True
    def add(sev, code, msg, page=None, bbox=None):
        drw.add(sev, code, CAT_SPEC, msg, None, None, STD)

    for n in nodes:
        if n["row"] is not root and section_of(n["row"], True) not in ("Сборочные единицы", "Комплексы"):
            continue                       # у детали своей спецификации нет (её «состав» — материалы покрытия)
        check_children(add, _label(n["row"]), n["children"])
        _mass_check(add, n)
        _positions(add, n)
    drw.facts["spec_tree"] = [{"pos": n["row"].get("pos"), "designation": n["row"].get("designation"),
                               "name": n["row"].get("name"), "children": len(n["children"])} for n in nodes]
    drw.facts["file_designation"] = drw.title.designation
    drw.facts["texts"] = [" ".join(str(r.get(k) or "") for k in ("designation", "name", "material")).strip()
                          for r in spec.rows][:5000]
    return drw


def children_for(spec, designation: str) -> list[dict] | None:
    """Составные части сборки с этим обозначением (для сверки номеров позиций на сборочном чертеже)."""
    key = norm_designation(re.sub(r"\s*СБ\s*$", "", designation or ""))
    if not key:
        return None
    for n in build_tree(spec):
        if norm_designation(n["row"].get("designation") or "") == key:
            return n["children"]
    return None
