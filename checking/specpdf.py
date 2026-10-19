"""Спецификация КОМПАС в PDF (отдельный документ формы 1/1а ГОСТ 2.106): распознавание, разбор таблицы и проверка.

Такой файл приходит вместе со сборочным чертежом. Он не является чертежом: размеры, шероховатость, ТТ и основная
надпись к нему не применяются — вместо них проверяется сама таблица (разделы, порядок, количество, обозначения,
код документа, ГОСТ 2.106) теми же правилами S, что и загруженная СП из Excel. Сверка с её сборочным чертежом,
чертежами составных частей и Excel-спецификацией — в specpair.py."""
from __future__ import annotations

import os
import re

from .model import Drawing, CAT_SPEC
from . import ext_spec  # noqa: F401  (регистрирует правила E1xx)
from .pack import emit
from .specdoc import STD, canon_section, check_children, section_of
from .textnorm import norm_designation, strip_doc_code, to_float

CODE = re.compile(r"\s*(СБ|МЧ|ВО|ГЧ|ТЧ|МЭ|ЭСБ)\s*$")


_canon_section = canon_section


def _qty(raw: str) -> tuple[float | None, str]:
    """«4» → (4, ''), «0,25 кг» → (0.25, 'кг')."""
    m = re.search(r"\d+(?:[.,]\d+)?", raw or "")
    unit = re.sub(r"[\d.,\s]", "", (raw or "")[m.end():]) if m else ""
    return (to_float(m.group(0)) if m else None), unit


def spec_tables(drw: Drawing) -> list[dict]:
    return [t for t in drw.facts.get("tables") or [] if t["kind"] == "spec"]


def is_spec_document(drw: Drawing, cfg: dict | None = None) -> bool:
    """Документ — спецификация, а не чертёж: таблица занимает основную часть листа, изображения нет.
    Спецификация, совмещённая со сборочным чертежом (таблица под изображением, есть размеры, номера позиций),
    остаётся сборочным чертежом."""
    force = (cfg or {}).get("_force_spec") or ()
    if drw.path in force or os.path.abspath(drw.path) in force:
        return bool(spec_tables(drw))
    tabs = spec_tables(drw)
    if not tabs:
        return False
    pi = drw.page_info(tabs[0]["page"]) or drw.page_info(drw.first_page)
    if not pi:
        return False
    big = any((t["bbox"][3] - t["bbox"][1]) >= 0.45 * pi.height for t in tabs)
    dims = [d for d in drw.dims if d.kind in ("linear", "diameter", "radius", "square")]
    return big and len(dims) < 3 and not drw.facts.get("positions")


def rows_of(drw: Drawing) -> list[dict]:
    """Строки спецификации (все листы документа) в формате строк загруженной СП."""
    rows = []
    for t in spec_tables(drw):
        for it in t["items"]:
            q, unit = _qty(it.get("qty") or "")
            des = (it.get("designation") or "").strip()
            sec = _canon_section(it.get("section"))
            row = {"pos": str(it["pos"]) if it.get("pos") else "", "designation": des, "name": (it.get("name") or "").strip(),
                   "qty": q, "qty_raw": it.get("qty") or "", "unit": unit, "note": (it.get("note") or "").strip(), "fmt": (it.get("fmt") or "").strip(),
                   "section": sec or "", "mass": None, "material": "", "sku": "", "page": t["page"], "bbox": it.get("bbox")}
            if re.fullmatch(r"\d{3}-\d{6}", des):
                row["sku"], row["designation_is_sku"] = des, True
            row["_section"] = sec or section_of(row, False)
            rows.append(row)
    return rows


class PdfSpec:
    """Спецификация из PDF как «загруженная СП»: те же поля строк, чтобы работали children_for, masscheck и сверка."""

    def __init__(self, drw: Drawing):
        self.path = drw.path
        self.drawing = drw
        self.items: dict[str, dict] = {}
        self.by_sku: dict[str, dict] = {}
        tb = drw.title
        des = tb.designation or drw.facts.get("file_designation") or ""
        self.designation = CODE.sub("", des).strip()
        self.name = re.sub(r"(?i)\s*сборочн\w*\s+чертеж\w*\s*$", "", tb.name or "").strip()
        root = {"pos": "", "designation": self.designation, "name": self.name, "qty": 1.0, "unit": "", "note": "",
                "section": "Сборочные единицы", "_section": "Сборочные единицы", "mass": tb.mass, "material": "", "sku": "",
                "page": drw.first_page, "bbox": tb.bboxes.get("designation"), "root": True}
        self.body = rows_of(drw)
        self.rows = [root] + self.body
        for r in self.rows:
            r["row"] = len(self.items) + 1
            if r.get("designation") and r.get("_section") != "Документация":
                self.items.setdefault(norm_designation(r["designation"]), r)
            if r.get("sku"):
                self.by_sku.setdefault(r["sku"], r)

    def find(self, designation: str, sku: str | None = None) -> dict | None:
        hit = self.items.get(norm_designation(designation)) if designation else None
        if hit is None and designation:
            hit = next((r for k, r in self.items.items() if strip_doc_code(k) == strip_doc_code(designation)), None)
        return hit if hit is not None else (self.by_sku.get(sku) if sku else None)

    def __len__(self):
        return len(self.body)


def try_spec_document(drw: Drawing, cfg: dict) -> bool:
    """Если документ — спецификация: записать разбор и замечания ГОСТ 2.106, вернуть True (остальные проверки
    чертежа к нему не применяются)."""
    if not is_spec_document(drw, cfg):
        return False
    sp = PdfSpec(drw)
    drw.kind = "spec"
    drw.facts["spec_document"] = True
    drw.facts["spec_obj"] = sp
    drw.facts["file_designation"] = sp.designation
    drw.facts["spec_rows"] = [{k: v for k, v in r.items() if k not in ("bbox", "root")} for r in sp.body]
    drw.facts["spec_tree"] = [{"pos": "", "designation": sp.designation, "name": sp.name, "children": len(sp.body)}]
    drw.facts["texts"] = [" ".join(x for x in (r["designation"], r["name"]) if x) for r in sp.body][:5000]
    if not sp.body:
        emit(drw, "E101", "В спецификации не найдено ни одной строки: проверьте, что файл — спецификация по форме 1 "
             "(графы «Поз.», «Обозначение», «Наименование», «Кол.»)", drw.first_page, None)
        return True

    def add(sev, code, msg, page, bbox):
        drw.add(sev, code, CAT_SPEC, msg, page if page is not None else drw.first_page, bbox, STD)

    check_children(add, f"{sp.designation} {sp.name}".strip(), sp.body)
    nums = []
    for c in sp.body:
        last = (c.get("pos") or "").rsplit(".", 1)[-1]
        if last.isdigit():
            nums.append(int(last))
    if any(b <= a for a, b in zip(nums, nums[1:])):
        dup = sorted({n for n in nums if nums.count(n) > 1})
        add("warning", "S13", f"Позиции не по порядку записи"
            f"{' (повторяются ' + ', '.join(map(str, dup)) + ')' if dup else ''}", None, None)
    return True
