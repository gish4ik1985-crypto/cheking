"""Командная строка:  python -m checking <файлы/папки> [--spec СП.xlsx] [--out отчёт.xlsx] [--json out.json]"""
from __future__ import annotations

import argparse
import os
import sys
import time

from .config import load_config
from .dxf import DxfIndex
from .engine import check_file, check_job, collect_dxf, collect_files
from .model import SEVERITY_RU, ERROR, WARNING, INFO
from .report import save_excel, save_json
from .spec import Spec

COLORS = {ERROR: "\033[91m", WARNING: "\033[93m", INFO: "\033[94m"}
RESET = "\033[0m"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="checking", description="Проверка чертежей: размеры, допуски, посадки, "
                                 "ТТ, масса, сверка со спецификацией/ERP")
    ap.add_argument("paths", nargs="+", help="PDF/CDW/DFT/PNG/JPG/TIF или папки")
    ap.add_argument("--spec", help="спецификация / выгрузка ERP (xlsx, xlsm, xls)")
    ap.add_argument("--out", help="отчёт Excel (.xlsx)")
    ap.add_argument("--json", help="отчёт JSON")
    ap.add_argument("--docx", help="перечень замечаний для конструктора (Word)")
    ap.add_argument("--dxf", nargs="*", default=[], help="DXF-макеты/папки для сверки (DXF из переданных папок "
                    "подхватываются автоматически)")
    ap.add_argument("--no-ocr", action="store_true", help="не распознавать сканы")
    ap.add_argument("--min", choices=["error", "warning", "info"], default="info",
                    help="показывать замечания не ниже этого уровня")
    ap.add_argument("--config", help="путь к config.json")
    a = ap.parse_args(argv)

    if sys.platform == "win32":
        os.system("")          # включает ANSI-цвета в консоли Windows
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    cfg = load_config(a.config)
    if a.no_ocr:
        cfg["ocr"] = False
    spec = Spec(a.spec) if a.spec else None
    files = collect_files(a.paths)
    dxf_index = DxfIndex(collect_dxf(a.paths + a.dxf))
    for p, err in dxf_index.errors.items():
        print(f"DXF не прочитан: {p}: {err}")
    if not files:
        print("Файлы чертежей не найдены")
        return 2
    level = {"error": 0, "warning": 1, "info": 2}[a.min]
    order = {ERROR: 0, WARNING: 1, INFO: 2}
    drawings = []
    t0 = time.time()
    for path in files:
        drawings += check_file(path, cfg, spec, dxf_index=dxf_index)
    check_job(drawings, cfg, spec)                  # сверка документов между собой (массы сборок, обозначения)
    for d in drawings:
        c = d.counts
        head = f"{d.filename}" + (f" [{d.facts['sheets_label']}]" if d.facts.get("sheets_label") else "")
        print(f"\n=== {head}  {d.title.designation}  {d.title.name}")
        print(f"    ошибок: {c[ERROR]}, предупреждений: {c[WARNING]}, замечаний: {c[INFO]}")
        for f in d.findings:
            if order[f.severity] <= level:
                std = f"  [{f.standard}]" if f.standard else ""
                print(f"  {COLORS[f.severity]}{SEVERITY_RU[f.severity]:<14}{RESET} {f.code} {f.message}{std}")
    tot = {k: sum(d.counts[k] for d in drawings) for k in (ERROR, WARNING, INFO)}
    print(f"\nИтого: {len(drawings)} док., ошибок {tot[ERROR]}, предупреждений {tot[WARNING]}, "
          f"замечаний {tot[INFO]} ({time.time() - t0:.1f} с)")
    comp = None
    if spec is not None:
        from .specdoc import check_spec_document
        from . import catalog
        sd = check_spec_document(spec, cfg)
        from .custom import apply_to_drawing as custom_rules
        custom_rules(sd, cfg)
        catalog.apply_to_drawing(sd, cfg)
        drawings.append(sd)
        from .completeness import completeness
        comp = completeness(spec, drawings)
        st = comp["stats"]
        print(f"Комплектность по СП: чертежей нет — {st['missing']}, с ошибками — {st['errors']}, "
              f"проверить — {st['warnings']}, без замечаний — {st['ok']}")
        for r in comp["rows"]:
            if r["status"] == "missing":
                print(f"  нет чертежа: поз. {r['pos']} {r['designation'] or r['sku']} {r['name']}")
    if a.out:
        print("Excel:", save_excel(drawings, a.out, comp))
    if a.docx:
        from .remarks import build_docx
        from .report import drawing_to_dict
        print("Word:", build_docx([drawing_to_dict(d) for d in drawings], a.docx))
    if a.json:
        print("JSON:", save_json(drawings, a.json))
    return 1 if tot[ERROR] else 0


if __name__ == "__main__":
    sys.exit(main())
