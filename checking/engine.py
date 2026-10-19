"""Оркестрация проверки: чтение файла → разбор → правила → отчёт."""
from __future__ import annotations

import os
import re
import traceback

from .cadreaders import read_cdw_meta, read_dft_meta, kompas_to_pdf, solidedge_to_pdf
from .config import load_config
from .dxf import DxfIndex, compare as dxf_compare, compare_erp_bbox, CAT_DXF
from .extract import extract
from .material import parse_material
from .model import Drawing, PageInfo, INFO, WARNING, ERROR, CAT_FILE, SEVERITY_ORDER, CATEGORY_ORDER
from .pdfreader import read_pdf, read_image
from .rules import (check_dimensions, check_roughness, check_tt, check_technology, check_title, check_erp,
                    file_notes)
from . import catalog
from .elements import check_elements
from .layout import check_layout
from .gears import check_gears
from .matcheck import check_material
from .textreq import check_heat, check_refs, check_tt_text
from .views import check_views
from .assembly import find_tables, check_assembly
from . import masscheck, ext_spec, specpdf
from .spec import Spec
from .textnorm import nfc
from .titleblock import parse_title_block, calibrate_scale, has_form1
from .welds import check_welds
from .ost import check_ost
from .eskd import check_eskd
from .eskd2 import check_eskd2
from .welds2 import check_welds2
from .eskd3 import check_eskd3
from .ext_all import check_ext
from .textdoc import check_text_document, is_text_document
from .exceptions import load_rules, apply_to_drawing

PDF_EXT = {".pdf"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
CDW_EXT = {".cdw", ".spw", ".frw"}
SE_EXT = {".dft"}
# Родные файлы КОМПАС-3D и Solid Edge пока не принимаются — работаем с PDF. Код чтения и конвертации
# (checking/cadreaders.py) сохранён: чтобы вернуть форматы, поставьте True (и добавьте расширения в accept страницы загрузки).
CAD_FORMATS = False
SUPPORTED = PDF_EXT | IMG_EXT | (CDW_EXT | SE_EXT if CAD_FORMATS else set())

FILE_DES_RE = re.compile(r"[А-ЯA-Z]{2,5}[._]\d{6}[._]\d{3}(?:-\d{2,3})?|[А-ЯA-Z]{1,5}-[А-ЯA-Z]{0,4}-?\d{3,4}(?:\.\d{3})?")
SKU_RE = re.compile(r"(?<!\d)(\d{3}-\d{6})(?!\d)")


def _file_facts(drw: Drawing) -> None:
    stem = nfc(os.path.splitext(drw.filename)[0])
    m = FILE_DES_RE.search(stem)
    if m:
        drw.facts["file_designation"] = m.group(0).replace("_", ".")
    m = SKU_RE.search(stem)
    if m:
        drw.facts["file_sku"] = m.group(1)


def _split_documents(drw: Drawing, words: list) -> list[tuple[Drawing, list]]:
    """PDF-пакет (несколько документов с основной надписью формы 1) → отдельные чертежи."""
    if len(drw.pages) < 2:
        return [(drw, words)]
    starts = [p.number for p in drw.pages if has_form1(drw.lines, p.number, drw.ocr)]
    if len(starts) < 2:
        return [(drw, words)]
    if drw.pages[0].number not in starts:
        starts.insert(0, drw.pages[0].number)
    out = []
    all_nums = [p.number for p in drw.pages]
    for i, st in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else all_nums[-1] + 1
        nums = set(range(st, end))
        sub = Drawing(drw.path, drw.filename, kind=drw.kind)
        sub.pages = [p for p in drw.pages if p.number in nums]
        sub.ocr = drw.ocr
        idx_map = {}
        for j, ln in enumerate(drw.lines):
            if ln.page in nums:
                idx_map[j] = len(sub.lines)
                sub.lines.append(ln)
        sub_words = []
        for w in words:
            if w.page in nums:
                w.line_no = idx_map.get(w.line_no, -1)
                sub_words.append(w)
        sub.facts["part_of_package"] = True
        for key in ("_segments", "_curves", "_seg_widths"):
            sub.facts[key] = {k: v for k, v in (drw.facts.get(key) or {}).items() if k in nums}
        sub.facts["sheets_label"] = f"л. {st + 1}" + (f"–{end}" if end - st > 1 else "")
        out.append((sub, sub_words))
    return out


# проверки чертежа, которые сохраняются для текстового документа (остальные к нему не относятся)
TEXT_DOC_KEEP = {"B04", "B05", "B08", "B10", "B11", "B12", "N01", "N02"}

_ERP = {"db": None, "error": None}


def _erp(cfg: dict):
    """Подключение к базе ERP (если включено в config.json), создаётся один раз."""
    c = cfg.get("erp_db") or {}
    if not c.get("enabled"):
        return None
    if _ERP["db"] is None and _ERP["error"] is None:
        try:
            from .erp_db import ErpDb
            _ERP["db"] = ErpDb(c)
        except Exception as e:
            _ERP["error"] = f"{type(e).__name__}: {e}"
    return _ERP["db"]


def _analyze(drw: Drawing, words: list, cfg: dict, spec: Spec | None, first_in_file: bool,
             dxf_index: DxfIndex | None = None) -> None:
    if not drw.facts.get("cdw") and not drw.facts.get("dft"):
        parse_title_block(drw, words)
        find_tables(drw, words)
        extract(drw)
    if first_in_file:
        _file_facts(drw)
    if specpdf.try_spec_document(drw, cfg):      # спецификация КОМПАС в PDF — не чертёж: проверяется таблица
        return
    tb = drw.title
    drw.facts["material"] = parse_material(tb.material)
    des = tb.designation or drw.facts.get("file_designation", "")
    spec_item = spec.find(des, drw.facts.get("file_sku")) if spec else None
    if spec:
        drw.facts["spec_source"] = ("карточке ERP" if spec.path == "ERP"
                                    else f"спецификации «{os.path.basename(spec.path)}»")
    erp = _erp(cfg)
    if spec_item is None and erp is not None:
        try:
            spec_item = erp.find(des, drw.facts.get("file_sku"))
            drw.facts["spec_source"] = "ERP"
        except Exception as e:
            drw.add(WARNING, "F06", CAT_FILE, f"Нет связи с базой ERP: {type(e).__name__}: {e}")
    elif (cfg.get("erp_db") or {}).get("enabled") and _ERP["error"]:
        drw.add(WARNING, "F06", CAT_FILE, f"Сверка с базой ERP недоступна: {_ERP['error']}")
    if spec_item:
        drw.facts["spec_item"] = {k: v for k, v in spec_item.items()}
        drw.facts["spec_material"] = parse_material(spec_item.get("material") or "")
    name = (tb.name or "").lower()
    drw.facts["is_assembly"] = bool(
        re.search(r"\bСБ\b|\bМЧ\b|\bВО\b", tb.designation or "") or "сборочный" in name
        or drw.facts.get("spec_table") or any(t["kind"] == "spec" for t in drw.facts.get("tables") or [])
        or (spec_item and re.search(r"(?i)сбороч|комплекс|комплект", spec_item.get("section") or "")))

    if spec is not None and drw.facts["is_assembly"] and hasattr(spec, "rows"):
        from .specdoc import children_for
        ch = children_for(spec, des)
        if ch:
            drw.facts["spec_children"] = ch
            drw.facts["spec_children_src"] = f"спецификации «{os.path.basename(spec.path)}»"
    check_dimensions(drw, cfg)
    check_roughness(drw, cfg)
    check_tt(drw, cfg)
    check_technology(drw, cfg)
    check_welds(drw, cfg)
    for extra in (check_views, check_tt_text, check_refs, check_heat, check_material, check_elements,
                  check_gears, check_assembly, check_layout, check_ost, check_eskd, check_eskd2, check_welds2, check_eskd3, check_ext):
        try:
            extra(drw, cfg)
        except Exception as e:          # одна неудачная проверка не должна ронять весь чертёж
            drw.add(WARNING, "F07", CAT_FILE, f"Проверка «{extra.__name__}» не выполнена: {type(e).__name__}: {e}")
    check_title(drw, cfg, spec_item)
    try:
        masscheck.check_mass_view(drw, cfg)
    except Exception as e:
        drw.add(WARNING, "F07", CAT_FILE, f"Проверка «check_mass_view» не выполнена: {type(e).__name__}: {e}")
    check_erp(drw, cfg, spec_item, spec is not None or erp is not None)
    if dxf_index is not None and len(dxf_index) and not drw.facts.get("is_assembly"):
        dx = dxf_index.find(drw)
        if dx:
            dxf_compare(drw, dx, cfg)
        elif drw.facts.get("sheet_thickness"):
            drw.add(INFO, "X05", CAT_DXF, "Для листовой детали не найден DXF среди загруженных файлов "
                    "(сопоставление по артикулу, обозначению или имени файла)")
    if spec_item and spec_item.get("dxf_length"):
        compare_erp_bbox(drw, spec_item)
    if is_text_document(drw, des, cfg):
        # текстовый документ (ТУ, ПЗ, РЭ…): проверки чертежа не применимы, выполняются проверки ГОСТ Р 2.105
        drw.facts["text_document"] = True
        drw.findings = [f for f in drw.findings if f.code in TEXT_DOC_KEEP or f.code.startswith(("F", "L"))]
        check_text_document(drw, cfg)
    file_notes(drw)
    if drw.facts.get("cdw"):
        drw.add(INFO, "F03", CAT_FILE, "Файл КОМПАС прочитан без КОМПАС-3D: проверены основная надпись, масса, "
                "материал и ТТ. Размеры и допуски из .cdw без КОМПАСа не извлекаются — для полной проверки "
                "сохраните чертёж в PDF (или установите КОМПАС-3D на этом компьютере)")
    if drw.facts.get("dft"):
        drw.add(WARNING, "F04", CAT_FILE, "Чертёж Solid Edge прочитан без Solid Edge: доступны только свойства "
                "документа (обозначение/наименование/материал, если заполнены). Размеры и допуски не проверены — "
                "сохраните чертёж в PDF или запустите проверку на компьютере с Solid Edge")
    _sort(drw)


def _sort(drw: Drawing) -> None:
    drw.findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], CATEGORY_ORDER.index(f.category)
                                     if f.category in CATEGORY_ORDER else 99))


def check_file(path: str, cfg: dict | None = None, spec: Spec | None = None, img_dir: str | None = None,
               display_name: str | None = None, dxf_index: DxfIndex | None = None,
               apply_profile: bool = True) -> list[Drawing]:
    """apply_profile=False — вернуть все замечания (веб-интерфейс применяет настройки правил при показе)."""
    cfg = cfg or load_config()
    name = display_name or os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()
    drw = Drawing(path, nfc(name), kind=ext.lstrip("."))
    if ext in (CDW_EXT | SE_EXT) and not CAD_FORMATS:
        drw.add(ERROR, "F05", CAT_FILE, f"Формат «{ext}» пока не принимается: сохраните чертёж в PDF")
        return [drw]
    if img_dir:
        os.makedirs(img_dir, exist_ok=True)
    try:
        words: list = []
        if ext in PDF_EXT:
            drw.kind = "pdf"
            words = read_pdf(path, drw, img_dir, use_ocr=cfg.get("ocr", True))
        elif ext in IMG_EXT:
            drw.kind = "image"
            words = read_image(path, drw, img_dir, use_ocr=cfg.get("ocr", True))
            if drw.ocr:
                calibrate_scale(drw, words)
        elif ext in CDW_EXT:
            pdf = kompas_to_pdf(path)
            if pdf:
                drw.kind = "cdw→pdf"
                words = read_pdf(pdf, drw, img_dir, use_ocr=False)
                drw.facts["converted"] = "КОМПАС-3D"
            else:
                drw.kind = "cdw"
                read_cdw_meta(path, drw)
        elif ext in SE_EXT:
            pdf = solidedge_to_pdf(path)
            if pdf:
                drw.kind = "dft→pdf"
                words = read_pdf(pdf, drw, img_dir, use_ocr=False)
                drw.facts["converted"] = "Solid Edge"
            else:
                drw.kind = "dft"
                read_dft_meta(path, drw)
        else:
            drw.add(ERROR, "F05", CAT_FILE, f"Формат «{ext}» не поддерживается")
            return [drw]

        native = drw.facts.get("cdw") or drw.facts.get("dft")
        if drw.pages and not drw.lines and not native:
            drw.add(WARNING, "F02", CAT_FILE, "На листах не найден текст: файл — изображение, а OCR недоступен или "
                    "ничего не распознал")
        parts = _split_documents(drw, words) if not native else [(drw, words)]
        rules = load_rules()
        for i, (d, w) in enumerate(parts):
            _analyze(d, w, cfg, spec, first_in_file=(i == 0), dxf_index=dxf_index)
            if apply_profile:
                from .custom import apply_to_drawing as custom_rules
                custom_rules(d, cfg)                # правила предприятия (config.json → custom_rules)
                catalog.apply_to_drawing(d, cfg)    # выключенные правила (config.json → rules)
            apply_to_drawing(d, rules)
        return [d for d, _ in parts]
    except Exception as e:  # отчёт должен собраться даже если один файл «битый»
        drw.error = f"{type(e).__name__}: {e}"
        drw.add(ERROR, "F00", CAT_FILE, f"Файл не удалось обработать: {drw.error}")
        drw.facts["traceback"] = traceback.format_exc()
        return [drw]


def check_job(drawings: list[Drawing], cfg: dict | None = None, spec: Spec | None = None,
              apply_profile: bool = True) -> set[int]:
    """Сверка документов одной проверки между собой: масса сборки и составных частей, наименования и
    обозначения в спецификациях. Вызывается после check_file для всех файлов. Возвращает номера чертежей
    (в списке drawings), к которым добавлены замечания."""
    cfg = cfg or load_config()
    try:
        changed = ext_spec.pair_documents(drawings, spec)      # СП КОМПАС ↔ сборочный чертёж, детали, Excel
        changed |= masscheck.check_job(drawings, spec)
    except Exception as e:
        if drawings:
            drawings[0].add(WARNING, "F07", CAT_FILE, f"Сверка документов между собой не выполнена: "
                            f"{type(e).__name__}: {e}")
        return {0} if drawings else set()
    rules = load_rules() if apply_profile else None
    for i in changed:
        d = drawings[i]
        if apply_profile:
            catalog.apply_to_drawing(d, cfg)
            apply_to_drawing(d, rules)
        _sort(d)
    return changed


def collect_dxf(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                out += [os.path.join(root, f) for f in sorted(files) if f.lower().endswith(".dxf")]
        elif p.lower().endswith(".dxf"):
            out.append(p)
    return out


def collect_files(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in sorted(files):
                    if os.path.splitext(f)[1].lower() in SUPPORTED and not f.startswith("~$"):
                        out.append(os.path.join(root, f))
        elif os.path.splitext(p)[1].lower() in SUPPORTED:
            out.append(p)
    return out
