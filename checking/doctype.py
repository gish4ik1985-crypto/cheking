"""Вид загруженного файла при общей загрузке: чертёж (в том числе PDF-спецификация, её программа определяет при проверке),
Excel-спецификация (ERP) или технологический документ (маршрутная карта, техпроцесс, операционная карта…).

Определение по расширению и началу текста; сканы без текста считаются чертежами."""
from __future__ import annotations

import os
import re

from .process import KINDS

DRAWING, SPEC, PROCESS = "drawing", "spec", "process"
LABEL = {DRAWING: "чертёж", SPEC: "Excel-спецификация", PROCESS: "технологический документ"}
_STAMP = re.compile(r"(?is)(?=.*масштаб)(?=.*\bмасса\b)")              # основная надпись чертежа


def _kind_in(text: str) -> str | None:
    for _k, name, rx in KINDS:
        if re.search(rx, text, re.I):
            return name
    return None


def _pdf_head(path: str) -> str:
    import pymupdf
    with pymupdf.open(path) as d:
        out = []
        for i in range(min(2, len(d))):
            out += d[i].get_text().split(chr(10))
    return chr(10).join(out[:80])


def classify(path: str) -> tuple[str, str]:
    """(вид, пояснение): DRAWING | SPEC | PROCESS."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return PROCESS, "документ Word: технологическая документация"
    if ext in (".xlsx", ".xlsm", ".xls"):
        try:
            from .process import _xlsx_lines
            kind = _kind_in(chr(10).join(_xlsx_lines(path)[:60]))
        except Exception:
            kind = None
        return (PROCESS, kind) if kind else (SPEC, "таблица Excel: спецификация")
    if ext == ".pdf":
        try:
            head = _pdf_head(path)
        except Exception:
            return DRAWING, "PDF"
        kind = _kind_in(head)
        if kind and not _STAMP.search(head):
            return PROCESS, kind
        return DRAWING, "PDF"
    return DRAWING, ext.lstrip(".").upper()
