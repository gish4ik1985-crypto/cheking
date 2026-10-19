"""Спецификация в PDF (PDF) вместе со сборочным чертежом и Excel-спецификацией (ERP): E1xx.

Документы одной проверки связываются по обозначению: спецификация (обозначение без кода «СБ») ↔ её сборочный чертёж,
составные части спецификации ↔ чертежи деталей, спецификация в PDF ↔ строки Excel-спецификации. Замечания по
самой таблице (разделы, порядок, количество, коды документов) — прежние правила S01–S20; замечания по позициям на
сборочном чертеже — A01, A02; массы — A13, A15–A17 (masscheck)."""
from __future__ import annotations

import os
import re

from .assembly import compare_positions
from .masscheck import _keys, _word
from .pack import R, emit
from .specdoc import children_for
from .textnorm import norm_designation

S2106 = "ГОСТ Р 2.106-2019"

R("E101", "spec", "Спецификация в PDF: в PDF найдены строки таблицы", S2106 + " форма 1",
  "Что файл, распознанный как спецификация, содержит строки таблицы: графы «Поз.», «Обозначение», «Наименование», «Кол.».",
  "В документе есть таблица спецификации, но ни одной строки программа не прочитала (нестандартная форма, скан плохого качества).",
  "«В спецификации не найдено ни одной строки»: проверьте, что это спецификация по форме 1.",
  "Файл не распознан как спецификация — проверяется как обычный чертёж.", sev="warning")
R("E102", "spec", "Для спецификации в проверке есть сборочный чертёж", S2106 + " п. 3.1",
  "Что вместе со спецификацией загружен её сборочный чертёж (обозначение спецификации + «СБ»): без него не сверить номера позиций и наименование.",
  "Среди документов проверки нет чертежа с обозначением спецификации (с кодом «СБ» или без).",
  "«Сборочный чертёж ДТМЛ.333333.001 СБ не загружен: номера позиций не сверены».", sev="info")
R("E103", "spec", "Наименование в спецификации и в основной надписи сборочного чертежа", S2106 + " п. 3.2",
  "Что наименование сборки в основной надписи спецификации совпадает с наименованием на сборочном чертеже (без слов «Сборочный чертёж»).",
  "Первое слово наименований различается.", "«Спецификация: Кронштейн, сборочный чертёж: Планка»».")
R("E104", "spec", "Для составной части спецификации загружен чертёж", S2106 + " п. 3.5",
  "Что для деталей и сборочных единиц спецификации с обозначением среди загруженных документов есть чертёж.",
  "Обозначение строки раздела «Детали» или «Сборочные единицы» не найдено среди чертежей проверки.",
  "«В проверке нет чертежей: ДТМЛ.333333.002 Планка».", "Выключено по умолчанию: при проверке одной сборки без деталей замечание лишнее.",
  default=False, sev="info")
R("E105", "spec", "Наименование строки спецификации и основная надпись чертежа детали", S2106 + " п. 3.5, ГОСТ Р 2.201-2023",
  "Что наименование детали или сборочной единицы в спецификации совпадает с наименованием в основной надписи её чертежа.",
  "Для строки найден чертёж по обозначению, первое слово наименований различается.",
  "«ДТМЛ.333333.002: в спецификации «Планка», в основной надписи чертежа «Пластина»».")
R("E108", "spec", "Обозначение сборочного чертежа в разделе «Документация»", S2106 + " п. 3.4",
  "Что в разделе «Документация» сборочный чертёж записан с обозначением спецификации и кодом «СБ» («ДТМЛ.333333.001 СБ»).",
  "В строке «Сборочный чертёж» обозначение не совпадает с обозначением спецификации + «СБ».",
  "«В разделе «Документация» обозначение ДТМЛ.333333.002 СБ, а спецификация — ДТМЛ.333333.001»».")
R("E109", "spec", "Сборка из спецификации в PDF есть в Excel-спецификации", S2106,
  "Что для спецификации в PDF в загруженном Excel (ERP) найдена сборочная единица с тем же обозначением и её составные части.",
  "Обозначение спецификации не найдено среди сборок Excel.", "«В Excel-спецификации нет сборки ДТМЛ.333333.001»: сверка не выполнена».",
  "Excel не загружен — сверки нет.", sev="info")
R("E111", "spec", "Строка спецификации в PDF есть в Excel", S2106,
  "Что каждая составная часть спецификации в PDF (кроме документации) есть среди составных частей этой сборки в Excel.",
  "Строки (по обозначению, для стандартных изделий — по наименованию) нет в Excel.",
  "«В Excel нет строк из спецификации: поз. 4 ДТМЛ.333333.003 Втулка»».")
R("E112", "spec", "Строка Excel есть в спецификации в PDF", S2106,
  "Что каждая составная часть этой сборки в Excel есть и в спецификации в PDF.",
  "Строки Excel нет в спецификации.", "«В спецификации нет строк из Excel: поз. 7 Шайба 6 ГОСТ 11371-78»».")
R("E113", "spec", "Наименования в спецификации в PDF и Excel", S2106,
  "Что наименование совпадающих по обозначению строк одинаково в спецификации в PDF и в Excel (регистр, пробелы, «х»/«×» не учитываются).",
  "Нормализованные наименования отличаются.", "«ДТМЛ.333333.002: PDF — «Планка», Excel — «Пластина»».")
R("E114", "spec", "Количество в спецификации в PDF и Excel", S2106,
  "Что количество совпадающих строк одинаково в спецификации в PDF и в Excel.",
  "Числа различаются.", "«ДТМЛ.333333.002: в PDF — 2, в Excel — 4»».", sev="error")
R("E115", "spec", "Номера позиций в спецификации в PDF и Excel", S2106,
  "Что номер позиции совпадающих строк одинаков в спецификации в PDF и в Excel.",
  "Номера различаются (последний разряд позиции).", "«ДТМЛ.333333.002: в PDF поз. 3, в Excel поз. 4»».", sev="info")


def _nname(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = s.translate(str.maketrans({"x": "х", "×": "х", "–": "-", "—": "-", "a": "а", "c": "с", "e": "е", "o": "о", "p": "р"}))
    return re.sub(r"[\s,.;]+", "", s)


def _key(row: dict) -> str:
    des = row.get("designation") or ""
    if des and not row.get("designation_is_sku"):
        return "d:" + norm_designation(des)
    if row.get("sku"):
        return "s:" + row["sku"]
    return "n:" + _nname(row.get("name"))


def _label(r: dict) -> str:
    return " ".join(x for x in ((f"поз. {r['pos']}" if r.get("pos") else ""), r.get("designation") if not r.get("designation_is_sku")
                                else "", r.get("name") or "") if x)


def _list(rows: list, n: int = 6) -> str:
    return "; ".join(_label(r) for r in rows[:n]) + (f" и ещё {len(rows) - n}" if len(rows) > n else "")


def _fnum(v) -> str:
    return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)


def compare_with_excel(s, sp, excel) -> None:
    """Составные части спецификации в PDF ↔ Excel (ERP) для сборки с этим обозначением."""
    ch = children_for(excel, sp.designation)
    if not ch:
        emit(s, "E109", f"В Excel-спецификации нет сборки «{sp.designation}» или у неё нет составных частей: "
             f"сверка с {os.path.basename(excel.path)} не выполнена", s.first_page, s.title.bboxes.get("designation"))
        return
    x_rows = [r for r in ch if r.get("_section") != "Документация"]
    p_rows = [r for r in sp.body if r.get("_section") not in ("Документация", "Комплекты")]
    xi: dict[str, dict] = {}
    for r in x_rows:
        xi.setdefault(_key(r), r)
    pi: dict[str, dict] = {}
    for r in p_rows:
        pi.setdefault(_key(r), r)
    only_p = [r for k, r in pi.items() if k not in xi]
    only_x = [r for k, r in xi.items() if k not in pi]
    src = os.path.basename(excel.path)
    if only_p:
        emit(s, "E111", f"В Excel «{src}» нет строк из спецификации: {_list(only_p)}", only_p[0].get("page"), only_p[0].get("bbox"))
    if only_x:
        emit(s, "E112", f"В спецификации нет строк из Excel «{src}»: {_list(only_x)}", s.first_page, None)
    names, qtys, poss = [], [], []
    for k, p in pi.items():
        x = xi.get(k)
        if x is None:
            continue
        if _nname(p.get("name")) != _nname(x.get("name")):
            names.append(f"{p.get('designation') or p.get('pos')}: PDF — «{p.get('name')}», Excel — «{x.get('name')}»")
        pq, xq = p.get("qty"), x.get("qty")
        if isinstance(pq, (int, float)) and isinstance(xq, (int, float)) and abs(pq - xq) > 1e-9:
            qtys.append(f"{p.get('designation') or p.get('name')}: PDF — {_fnum(pq)}, Excel — {_fnum(xq)}")
        pp, xp = (p.get("pos") or "").rsplit(".", 1)[-1], (x.get("pos") or "").rsplit(".", 1)[-1]
        if pp.isdigit() and xp.isdigit() and pp != xp:
            poss.append(f"{p.get('designation') or p.get('name')}: PDF — поз. {pp}, Excel — поз. {xp}")
    for code, lst, head in (("E113", names, "Наименования различаются"), ("E114", qtys, "Количество различается"),
                            ("E115", poss, "Номера позиций различаются")):
        if lst:
            emit(s, code, f"{head} (спецификация в PDF и Excel «{src}»): " + "; ".join(lst[:6])
                 + (f" и ещё {len(lst) - 6}" if len(lst) > 6 else ""), s.first_page, None)


def pair_documents(drawings: list, excel=None) -> set[int]:
    """Связывает спецификации в PDF (PDF) со сборочными чертежами и чертежами деталей этой проверки, сверяет с Excel.
    Вызывается до masscheck: у связанной сборки появляются составные части (spec_children), по которым
    сверяются позиции и массы. Возвращает номера документов, к которым добавлены замечания."""
    changed: set[int] = set()
    specs = [(i, d) for i, d in enumerate(drawings) if d.facts.get("spec_document")]
    if not specs:
        return changed
    index: dict[str, int] = {}
    for i, d in enumerate(drawings):
        if d.facts.get("spec_document") or d.kind == "process" or d.error:
            continue
        for k in _keys(d):
            index.setdefault(k, i)
    for i, s in specs:
        sp = s.facts["spec_obj"]
        before = len(s.findings)
        key = norm_designation(sp.designation)
        j = index.get(key)
        asm = drawings[j] if j is not None else None
        if asm is None:
            emit(s, "E102", f"Сборочный чертёж {sp.designation} СБ в проверке не найден: номера позиций и наименование "
                 "не сверены", s.first_page, s.title.bboxes.get("designation"))
        else:
            kids = children_for(sp, sp.designation) or []
            src = f"спецификации «{os.path.basename(s.path)}»"
            if kids and not any(t["kind"] == "spec" for t in asm.facts.get("tables") or []):
                asm.facts["spec_children"], asm.facts["spec_children_src"] = kids, src
                n0 = len(asm.findings)
                compare_positions(asm, kids, src)
                if len(asm.findings) > n0:
                    changed.add(j)
            a_name = re.sub(r"(?i)\s*сборочн\w*\s+чертеж\w*\s*$", "", asm.title.name or "").strip()
            if a_name and sp.name and _word(a_name) and _word(a_name) != _word(sp.name):
                emit(s, "E103", f"В основной надписи спецификации «{sp.name}», на сборочном чертеже {asm.title.designation} — "
                     f"«{a_name}»", s.first_page, s.title.bboxes.get("name"))
        doc_row = next((r for r in sp.body if r.get("_section") == "Документация" and re.search(r"(?i)сборочн\w*\s+чертеж", r["name"])), None)
        if doc_row and doc_row.get("designation"):
            want = norm_designation(sp.designation) + "СБ"
            if norm_designation(doc_row["designation"]) != want:
                emit(s, "E108", f"В разделе «Документация» сборочный чертёж записан как «{doc_row['designation']}», а по "
                     f"обозначению спецификации ожидается «{sp.designation} СБ»", doc_row.get("page"), doc_row.get("bbox"))
        missing = []
        for c in sp.body:
            if c.get("_section") not in ("Детали", "Сборочные единицы") or not c.get("designation") or c.get("designation_is_sku"):
                continue
            jj = index.get(norm_designation(c["designation"]))
            if jj is None:
                missing.append(c)
                continue
            part = drawings[jj]
            w1, w2 = _word(c.get("name")), _word(part.title.name)
            if w1 and w2 and w1 != w2:
                emit(s, "E105", f"{c['designation']}: в спецификации «{c['name']}», в основной надписи чертежа "
                     f"{part.title.designation} — «{part.title.name}»", c.get("page"), c.get("bbox"))
        if missing and len(index) > 1:
            emit(s, "E104", "В проверке нет чертежей: " + "; ".join(f"{c['designation']} {c['name']}" for c in missing[:8])
                 + (f" и ещё {len(missing) - 8}" if len(missing) > 8 else ""), s.first_page, None)
        if excel is not None and hasattr(excel, "rows"):
            compare_with_excel(s, sp, excel)
        if len(s.findings) > before:
            changed.add(i)
    return changed
