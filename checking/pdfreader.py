"""Чтение PDF (векторного или скана) и растровых изображений в набор строк текста."""
from __future__ import annotations

import math
import os

import pymupdf

from .model import Drawing, PageInfo, TextLine, Word
from .textnorm import remap_char, nfc

PT = 25.4 / 72.0     # pt -> мм


def _dir(d) -> tuple[float, float]:
    x, y = float(d[0]), float(d[1])
    n = math.hypot(x, y) or 1.0
    return round(x / n, 3), round(y / n, 3)


def _segments(ln: dict) -> list[list[dict]]:
    """Делит строку PyMuPDF на части по размеру шрифта и базовой линии.

    PyMuPDF может склеить номинал и верхнее отклонение («50» + «+0,2») в одну строку,
    если они стоят близко; отклонения набраны меньшим шрифтом и смещены по высоте."""
    d = ln.get("dir", (1, 0))
    nx, ny = d[1], -d[0]                      # нормаль «вверх»
    segs: list[list[dict]] = []
    prev = None
    for sp in ln.get("spans", []):
        if not sp.get("chars"):
            continue
        size = sp.get("size", 0) or 1
        o = sp.get("origin", (0, 0))
        v = o[0] * nx + o[1] * ny
        if prev is not None:
            psize, pv = prev
            only_space = not "".join(c["c"] for c in sp["chars"]).strip()
            if not only_space and (abs(size - psize) > 0.15 * max(size, psize) or abs(v - pv) > 0.3 * max(size, psize)):
                segs.append([])
        if not segs:
            segs.append([])
        segs[-1].append(sp)
        if "".join(c["c"] for c in sp["chars"]).strip():
            prev = (size, v)
    return [g for g in segs if g]


def extract_vector_lines(page: pymupdf.Page, pno: int) -> tuple[list[TextLine], list[Word]]:
    lines: list[TextLine] = []
    words: list[Word] = []
    # координаты текста PyMuPDF отдаёт в неповёрнутой системе страницы; у листов Solid Edge
    # А3/А2 часто стоит /Rotate 90 — приводим к тому, как лист выглядит
    m = page.rotation_matrix
    o0 = pymupdf.Point(0, 0) * m

    def rect(b):
        r = pymupdf.Rect(b) * m
        return (r.x0 * PT, r.y0 * PT, r.x1 * PT, r.y1 * PT)

    def point(p):
        q = pymupdf.Point(p) * m
        return (q.x * PT, q.y * PT)

    def direction(d):
        q = pymupdf.Point(d) * m - o0
        return _dir((q.x, q.y))

    raw = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_CID_FOR_UNKNOWN_UNICODE)
    for block in raw.get("blocks", []):
        for ln in block.get("lines", []):
            for spans in _segments(ln):
                chars = []
                fonts = []
                size = 0.0
                for sp in spans:
                    fonts.append(sp.get("font", ""))
                    size = max(size, sp.get("size", 0) * PT)
                    for ch in sp.get("chars", []):
                        chars.append((remap_char(ch["c"], sp.get("font", "")), ch["bbox"]))
                text = nfc("".join(c for c, _ in chars))
                if not text.strip():
                    continue
                boxes = [b for c, b in chars if not c.isspace()]
                x0 = min(b[0] for b in boxes)
                y0 = min(b[1] for b in boxes)
                x1 = max(b[2] for b in boxes)
                y1 = max(b[3] for b in boxes)
                tl = TextLine(text=" ".join(text.split()), page=pno, bbox=rect((x0, y0, x1, y1)),
                              dir=direction(ln.get("dir", (1, 0))), size=size,
                              origin=point(spans[0]["origin"]), fonts=tuple(fonts))
                lines.append(tl)
                lno = len(lines) - 1
                # слова (для раскладки по графам основной надписи)
                cur, box = "", None
                for c, b in chars + [(" ", None)]:
                    if c.isspace() or b is None:
                        if cur.strip():
                            words.append(Word(cur.strip(), pno, rect(box), lno))
                        cur, box = "", None
                        continue
                    cur += c
                    box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]),
                                                 max(box[2], b[2]), max(box[3], b[3]))
    # Solid Edge кладёт часть надписей в PDF дважды (поверх) — убираем дубли
    seen: dict[tuple, int] = {}
    keep: list[TextLine] = []
    remap: dict[int, int] = {}
    for i, ln in enumerate(lines):
        k = (ln.text, round(ln.bbox[0] * 3), round(ln.bbox[1] * 3))
        if k in seen:
            remap[i] = seen[k]
            continue
        seen[k] = len(keep)
        remap[i] = len(keep)
        keep.append(ln)
    if len(keep) != len(lines):
        uniq_words = []
        wseen = set()
        for w in words:
            wk = (w.text, round(w.bbox[0] * 3), round(w.bbox[1] * 3))
            if wk in wseen:
                continue
            wseen.add(wk)
            w.line_no = remap[w.line_no]
            uniq_words.append(w)
        words = uniq_words
    return keep, words


def extract_segments(page: pymupdf.Page, curves: list | None = None) -> list[tuple[float, float, float, float]]:
    """Прямые отрезки графики листа в мм (в системе повёрнутого листа). Кривые Безье (окружности, дуги)
    в отрезки не входят; если передан список curves — туда пишется их контрольный многоугольник."""
    m = page.rotation_matrix
    segs = []
    try:
        paths = page.get_drawings()
    except Exception:
        return segs
    for p in paths:
        for it in p.get("items", []):
            if it[0] == "c":
                if curves is not None:
                    q = [x * m for x in it[1:5]]
                    curves.extend((a.x * PT, a.y * PT, b.x * PT, b.y * PT) for a, b in zip(q, q[1:]))
                continue
            if it[0] == "l":
                pts = [(it[1], it[2])]
            elif it[0] == "re":
                r = it[1]
                pts = [(r.tl, r.tr), (r.tr, r.br), (r.br, r.bl), (r.bl, r.tl)]
            elif it[0] == "qu":
                q = it[1]
                pts = [(q.ul, q.ur), (q.ur, q.lr), (q.lr, q.ll), (q.ll, q.ul)]
            else:
                continue
            for a, b in pts:
                a, b = a * m, b * m
                segs.append((a.x * PT, a.y * PT, b.x * PT, b.y * PT))
    return segs


# ---------------------------------------------------------------- OCR ------
_OCR_ENGINE = None


def ocr_available() -> bool:
    try:
        import rapidocr  # noqa: F401
        return True
    except Exception:
        return False


def _engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from rapidocr import RapidOCR, LangRec, OCRVersion, ModelType
        _OCR_ENGINE = RapidOCR(params={
            "Rec.lang_type": LangRec.CYRILLIC, "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.MOBILE, "Global.log_level": "error"})
    return _OCR_ENGINE


def ocr_image(img, pno: int, mm_per_px: float) -> tuple[list[TextLine], list[Word]]:
    """img — numpy RGB. Возвращает строки и слова в мм."""
    res = _engine()(img)
    lines: list[TextLine] = []
    words: list[Word] = []
    if res is None or res.boxes is None:
        return lines, words
    for box, txt, score in zip(res.boxes, res.txts, res.scores):
        txt = nfc(str(txt)).strip()
        if not txt:
            continue
        pts = [(float(p[0]) * mm_per_px, float(p[1]) * mm_per_px) for p in box]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        e1 = (pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
        e2 = (pts[3][0] - pts[0][0], pts[3][1] - pts[0][1])
        len1, len2 = math.hypot(*e1), math.hypot(*e2)
        if len2 > len1 * 1.3 and len(txt) > 1:
            # высокий узкий прямоугольник — вертикальная надпись (читается снизу вверх)
            d = (0.0, -1.0)
            height = len1
        else:
            d = _dir(e1) if len1 else (1.0, 0.0)
            height = len2
        bbox = (min(xs), min(ys), max(xs), max(ys))
        tl = TextLine(text=" ".join(txt.split()), page=pno, bbox=bbox, dir=d, size=height * 0.75,
                      origin=(pts[3][0], pts[3][1]), fonts=("ocr",), conf=float(score))
        lines.append(tl)
        lno = len(lines) - 1
        # слова — пропорционально числу символов вдоль строки
        parts = txt.split()
        total = max(1, len(txt))
        pos = 0
        for part in parts:
            idx = txt.find(part, pos)
            a, b = idx / total, (idx + len(part)) / total
            pos = idx + len(part)
            if d == (0.0, -1.0):
                wb = (bbox[0], bbox[3] - b * (bbox[3] - bbox[1]), bbox[2], bbox[3] - a * (bbox[3] - bbox[1]))
            else:
                wb = (bbox[0] + a * (bbox[2] - bbox[0]), bbox[1], bbox[0] + b * (bbox[2] - bbox[0]), bbox[3])
            words.append(Word(part, pno, wb, lno))
    return lines, words


def _pix_to_np(pix):
    import numpy as np
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    return arr[:, :, :3].copy()


def render_page_png(page: pymupdf.Page, out_path: str, dpi: int = 110) -> str:
    pix = page.get_pixmap(dpi=dpi)
    pix.save(out_path)
    return out_path


def read_pdf(path: str, drw: Drawing, img_dir: str | None, use_ocr: bool = True,
             ocr_dpi: int = 220) -> list[Word]:
    """Заполняет drw.pages / drw.lines; возвращает слова для разбора основной надписи."""
    doc = pymupdf.open(path)
    all_words: list[Word] = []
    try:
        for pno, page in enumerate(doc):
            w, h = page.rect.width * PT, page.rect.height * PT
            pi = PageInfo(pno, w, h)
            lines, words = extract_vector_lines(page, pno)
            if lines:
                curves: list = []
                drw.facts.setdefault("_segments", {})[pno] = extract_segments(page, curves)
                drw.facts.setdefault("_curves", {})[pno] = curves
            nchars = sum(len(l.text) for l in lines)
            if nchars < 25:
                pi.scanned = True
                if use_ocr and ocr_available():
                    pix = page.get_pixmap(dpi=ocr_dpi)
                    lines, words = ocr_image(_pix_to_np(pix), pno, 25.4 / ocr_dpi)
                    drw.ocr = True
            if img_dir:
                pi.image = render_page_png(page, os.path.join(img_dir, f"p{pno + 1}.png"))
            drw.pages.append(pi)
            base = len(drw.lines)
            for w in words:
                w.line_no += base
            drw.lines.extend(lines)
            all_words.extend(words)
    finally:
        doc.close()
    if drw.pages and all(p.scanned for p in drw.pages):
        drw.kind = "pdf-scan"
    return all_words


def read_image(path: str, drw: Drawing, img_dir: str | None, use_ocr: bool = True) -> list[Word]:
    """Растровый файл (PNG/JPG/TIF): текст — через OCR.

    Физический масштаб берётся из DPI файла (по умолчанию 300 dpi) и затем уточняется
    по основной надписи (см. titleblock.calibrate_scale)."""
    pix = pymupdf.Pixmap(path)
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    if pix.n != 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    dpi = pix.xres if pix.xres and pix.xres > 50 else 300
    mm_px = 25.4 / dpi
    pi = PageInfo(0, pix.w * mm_px, pix.h * mm_px, scanned=True)
    if img_dir:
        k = min(1.0, 1400 / max(pix.w, pix.h))
        prev = pymupdf.Pixmap(pix, int(pix.w * k), int(pix.h * k), None) if k < 1 else pix
        pi.image = os.path.join(img_dir, "p1.png")
        prev.save(pi.image)
    words: list[Word] = []
    if use_ocr and ocr_available():
        k = min(1.0, 220 / dpi)
        work = pymupdf.Pixmap(pix, int(pix.w * k), int(pix.h * k), None) if k < 1 else pix
        lines, words = ocr_image(_pix_to_np(work), 0, mm_px / k)
        drw.lines.extend(lines)
        drw.ocr = True
    drw.pages.append(pi)
    return words
