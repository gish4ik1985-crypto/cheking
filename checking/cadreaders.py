"""Нативные форматы САПР.

КОМПАС .cdw — ZIP-контейнер: свойства основной надписи лежат в MetaProductInfo (XML, UTF-16),
технические требования — в images/*.TechnicalDemand. Геометрию и размеры без КОМПАСа не извлечь,
поэтому, если на компьютере установлен полный КОМПАС-3D или SolidWorks, файл сначала
конвертируется в PDF через их COM-API и проверяется полностью.
"""
from __future__ import annotations

import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from .model import Drawing, PageInfo, TitleBlock
from .textnorm import to_float

FORMAT_SIZES = {"A0": (1189, 841), "A1": (841, 594), "A2": (594, 420), "A3": (420, 297), "A4": (297, 210)}


def _utf16_strings(data: bytes) -> list[str]:
    out = []
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00|[\x00-\xff]\x04){4,}", data):
        try:
            s = m.group().decode("utf-16-le").strip()
        except UnicodeDecodeError:
            continue
        if re.search(r"[А-Яа-яA-Za-z]{2}", s):
            out.append(s)
    return out


def read_cdw_meta(path: str, drw: Drawing) -> None:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        props: dict[str, str] = {}
        if "MetaProductInfo" in names:
            xml = z.read("MetaProductInfo").decode("utf-16", errors="ignore")
            xml = xml.replace('encoding="utf-16"', "")
            root = ET.fromstring(xml)
            doc = root.find(".//product/document")
            if doc is not None:
                for p in doc.findall("property"):
                    pid = p.get("id")
                    if pid == "marking":
                        sub = {c.get("id"): c.get("value") or "" for c in p.findall("property")}
                        des = sub.get("base", "")
                        if sub.get("embodimentNumber"):
                            des += (sub.get("embodimentDelimiter") or "-") + sub["embodimentNumber"]
                        if sub.get("documentNumber"):
                            des += " " + sub["documentNumber"]
                        props["marking"] = des.strip()
                    elif pid == "material":
                        sub = {c.get("id"): c.get("value") or "" for c in p.findall("property")}
                        mat = " ".join(sub.get("name", "").split())
                        mat = re.sub(r"\$[dm](.*?);(.*?)\$", r" \1 / \2", mat)     # дробь КОМПАС
                        props["material"] = " ".join(mat.split())
                    else:
                        props[pid] = p.get("value") or ""
        tt = []
        for n in names:
            if n.lower().endswith(".technicaldemand"):
                tt += _utf16_strings(z.read(n))
    tb = TitleBlock(found=True)
    tb.designation = props.get("marking", "")
    tb.name = props.get("name", "")
    tb.material = props.get("material", "")
    tb.organization = props.get("organization", "")
    tb.mass_raw = props.get("mass", "")
    tb.mass = to_float(tb.mass_raw) if tb.mass_raw else None
    if tb.mass is not None:
        tb.mass_raw = f"{tb.mass:g}".replace(".", ",")
    tb.sheets = props.get("sheetsNumber", "")
    fmt = props.get("format", "")
    tb.format = fmt.split("@")[0] if fmt else ""
    for role, pid in (("Разраб.", "stampAuthor"), ("Пров.", "checkedBy"), ("Т.контр.", "mfgApprovedBy"),
                      ("Н.контр.", "rateOfInspection"), ("Утв.", "approvedBy")):
        if props.get(pid):
            tb.people[role] = props[pid]
    drw.title = tb
    drw.facts["cdw"] = True
    drw.facts["cdw_props"] = props
    # технические требования: строки начинаются со служебного байта длины — чистим
    items: list[str] = []
    for s in tt:
        s = re.sub(r"^[^\wА-Яа-я*]+", "", s)
        s = re.sub(r"[Ѐ-Џ]+$", "", s).strip()
        if len(s) < 3 or re.fullmatch(r"(?i)gost\s*type\s*\w+|default", s):
            continue
        if items and (s[0].islower() or items[-1].rstrip().endswith((",", "-")) or re.match(r"^IT\d", s)):
            items[-1] += " " + s
        else:
            items.append(s)
    drw.tt = items
    w, h = FORMAT_SIZES.get(tb.format.upper().replace("А", "A"), (420, 297))
    drw.pages.append(PageInfo(0, w, h))


# -------------------------------------------------- конвертация через САПР --
def _dispatch(progid: str):
    import win32com.client  # type: ignore
    return win32com.client.Dispatch(progid)


def kompas_to_pdf(path: str) -> str | None:
    """Конвертирует .cdw/.spw в PDF через установленный КОМПАС-3D (API7). None — если КОМПАСа нет."""
    try:
        app = _dispatch("Kompas.Application.7")
    except Exception:
        return None
    out = os.path.join(tempfile.mkdtemp(prefix="chk_"), os.path.splitext(os.path.basename(path))[0] + ".pdf")
    try:
        app.Visible = False
        app.HideMessage = 1
        base = app.ApplicationPath
        for cand in (os.path.join(base, "Pdf2d.dll"), os.path.join(base, "Bin", "Pdf2d.dll"),
                     os.path.join(os.path.dirname(base), "Bin", "Pdf2d.dll")):
            if os.path.exists(cand):
                conv = app.Converter(cand)
                conv.Convert(path, out, 0, False)
                break
        return out if os.path.exists(out) else None
    except Exception:
        return None


def solidedge_to_pdf(path: str) -> str | None:
    """Конвертирует чертёж Solid Edge (.dft) в PDF через установленный Solid Edge. None — если его нет."""
    try:
        app = _dispatch("SolidEdge.Application")
    except Exception:
        return None
    out = os.path.join(tempfile.mkdtemp(prefix="chk_"), os.path.splitext(os.path.basename(path))[0] + ".pdf")
    try:
        app.DisplayAlerts = False
        doc = app.Documents.Open(path)
        doc.SaveAs(out)                 # чертёж (DraftDocument) сохраняется в PDF по расширению
        doc.Close(False)
        return out if os.path.exists(out) else None
    except Exception:
        return None


def read_dft_meta(path: str, drw: Drawing) -> None:
    """Без Solid Edge: свойства документа из OLE-контейнера .dft (обозначение, наименование, материал…)."""
    import olefile
    tb = TitleBlock(found=False)
    props: dict[str, str] = {}
    if olefile.isOleFile(path):
        with olefile.OleFileIO(path) as ole:
            meta = ole.get_metadata()
            for k in ("title", "subject", "author", "keywords", "comments", "company", "last_saved_by"):
                v = getattr(meta, k, None)
                if v:
                    props[k] = v.decode("cp1251", "ignore") if isinstance(v, bytes) else str(v)
            for entry in ole.listdir(streams=True):
                name = "/".join(entry)
                if not name.startswith("\x05"):
                    continue
                try:
                    for pid, val in ole.getproperties(entry).items():
                        if isinstance(val, bytes):
                            val = val.decode("cp1251", "ignore")
                        if isinstance(val, str) and val.strip():
                            props[f"{name}:{pid}"] = val.strip()
                except Exception:
                    continue
    texts = list(props.values())
    des = next((t for t in texts if re.fullmatch(r"[А-ЯA-Z]{2,5}\.\d{6}\.\d{3}(?:-\d{2,3})?(?:\s?[А-Я]{1,3})?", t)), "")
    tb.designation = des
    tb.name = props.get("title", "")
    tb.material = next((t for t in texts if re.search(r"(?i)ГОСТ|Ст\d|сталь|AISI|09Г2С", t)
                        and t not in (des, tb.name)), "")
    drw.title = tb
    drw.facts["dft"] = True
    drw.facts["dft_props"] = props
    drw.pages.append(PageInfo(0, 420, 297))
