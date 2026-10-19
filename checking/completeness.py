"""Комплектность: какие позиции спецификации должны иметь чертёж и нашёлся ли он среди проверенных."""
from __future__ import annotations

import re

from .textnorm import norm_designation, strip_doc_code

NO_DRAWING_SECTIONS = re.compile(r"(?i)программн|стандартн|прочи|материал|комплект(?!ы)|документац")
DRAWING_SECTIONS = re.compile(r"(?i)детал|сборочн|комплекс")


def needs_drawing(row: dict) -> bool:
    """Позиции, которым положен чертёж: детали и сборочные единицы. Стандартные/прочие изделия, материалы,
    покупные (артикулы 3xx–5xx по классификатору ЯСТ) и помеченные «Без чертежа» — нет."""
    if re.search(r"(?i)без чертеж", row.get("note") or ""):
        return False
    sec = row.get("section") or ""
    if sec:
        if NO_DRAWING_SECTIONS.search(sec):
            return False
        if DRAWING_SECTIONS.search(sec):
            return True
    sku = (row.get("sku") or "").strip()
    if re.match(r"^[345]\d{2}-", sku):
        return False
    if re.match(r"^[12]\d{2}-", sku):
        return True
    return bool((row.get("designation") or "").strip())


def completeness(spec, drawings: list) -> dict:
    """drawings — словари из report.drawing_to_dict (или объекты Drawing)."""
    def get(d, *keys):
        for k in keys:
            d = (d.get(k) if isinstance(d, dict) else getattr(d, k, None)) or {}
        return d

    index_des, index_sku = {}, {}
    for d in drawings:
        if (d.get("kind") if isinstance(d, dict) else d.kind) in ("spec", "process"):
            continue                                   # сама спецификация — не чертёж
        des = get(d, "title", "designation") if isinstance(d, dict) else d.title.designation
        facts = d.get("facts", {}) if isinstance(d, dict) else d.facts
        counts = d.get("counts") if isinstance(d, dict) else d.counts
        fname = d.get("file") if isinstance(d, dict) else d.filename
        rec = {"file": fname, "counts": counts, "id": d.get("id") if isinstance(d, dict) else None}
        for x in (des, facts.get("file_designation")):
            if x:
                index_des.setdefault(norm_designation(x), rec)
                index_des.setdefault(strip_doc_code(x), rec)          # «…001 СБ» закрывает позицию «…001»
        sku = facts.get("file_sku") or (facts.get("spec_item") or {}).get("sku")
        if sku:
            index_sku.setdefault(sku, rec)

    rows, seen = [], set()
    for r in spec.rows:
        key = norm_designation(r.get("designation") or "") or r.get("sku")
        if not key or key in seen:
            continue
        seen.add(key)
        need = needs_drawing(r)
        hit = (index_des.get(norm_designation(r.get("designation") or "")) or index_des.get(strip_doc_code(r["designation"]))
               ) if r.get("designation") else None
        hit = hit or (index_sku.get(r.get("sku")) if r.get("sku") else None)
        if hit:
            c = hit["counts"]
            status = "errors" if c.get("error") else ("warnings" if c.get("warning") else "ok")
        else:
            status = "missing" if need else "not_required"
        rows.append({"pos": r.get("pos") or "", "designation": r.get("designation") or "", "sku": r.get("sku") or "",
                     "name": r.get("name") or "", "section": r.get("section") or "", "need": need, "status": status,
                     "file": hit["file"] if hit else "", "doc_id": hit["id"] if hit else None,
                     "errors": hit["counts"].get("error", 0) if hit else 0,
                     "warnings": hit["counts"].get("warning", 0) if hit else 0})
    spec_keys = {norm_designation(r["designation"]) for r in rows if r["designation"]} | {r["sku"] for r in rows if r["sku"]}
    extra = []
    for d in drawings:
        des = (d.get("title") or {}).get("designation") if isinstance(d, dict) else d.title.designation
        facts = d.get("facts", {}) if isinstance(d, dict) else d.facts
        fname = d.get("file") if isinstance(d, dict) else d.filename
        keys = {norm_designation(x) for x in (des, facts.get("file_designation")) if x}
        keys |= {strip_doc_code(x) for x in (des, facts.get("file_designation")) if x}
        if facts.get("file_sku"):
            keys.add(facts["file_sku"])
        if not keys & spec_keys:
            extra.append({"file": fname, "designation": des or ""})
    stats = {s: sum(1 for r in rows if r["status"] == s) for s in ("ok", "warnings", "errors", "missing", "not_required")}
    return {"rows": rows, "extra": extra, "stats": stats}
