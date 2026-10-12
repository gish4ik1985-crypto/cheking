"""Изображения и буквенные обозначения (ГОСТ 2.305-2008, ГОСТ 2.316-2008 пп. 4.17–4.18, ГОСТ 2.302-68)
и рамки допусков формы и расположения (ГОСТ 2.308-2011, ГОСТ 24643-81)."""
from __future__ import annotations

import re
from collections import Counter

from .model import Drawing, TextLine, ERROR, WARNING, INFO, CAT_DIM, CAT_VIEW, CAT_GDT
from .normdata import (FORBIDDEN_LETTERS, FORBIDDEN_LATIN, CYR_ALPHABET, SCALES, GDT_SERIES_UM, GDT_KIND,
                       GDT_NEEDS_BASE)
from .standards import fmtn
from .textnorm import to_float
from .titleblock import excluded

STD_VIEWS = "ГОСТ 2.305-2008"
STD_LETTERS = "ГОСТ 2.316-2008"
STD_GDT = "ГОСТ 2.308-2011"

LETTER = r"[А-ЯЁA-Z]\d?"
WORDS = r"(?P<w>(?:Вид|Разрез|Сечение)\s+)?"
SECTION_RE = re.compile(rf"^{WORDS}(?P<a>{LETTER})\s*-\s*(?P<b>{LETTER})\s*(?:\((?P<sc>[^)]*)\))?\s*⟲?$")
VIEW_RE = re.compile(rf"^{WORDS}(?P<a>{LETTER})\s*(?:\((?P<sc>[^)]*)\))?\s*⟲?$")
FRAME_RE = re.compile(r"^(?P<sym>[◎↗⌖∥⊥∠⌯⌰⏥○⌭⏤])\s*(?P<dia>S?⌀)?\s*(?P<val>\d+(?:[.,]\d+)?)\s*"
                      r"(?P<mod>[ⓂⓅ])?\s*(?P<bases>(?:[А-ЯЁA-Z]\s*){0,3})$")


def _norm(text: str) -> str:
    t = text.replace("–", "-").replace("—", "-").replace("‑", "-")
    t = re.sub(r"\(\s*", "(", t)
    t = re.sub(r"\s*\)", ")", t)
    t = re.sub(r"\s*:\s*", ":", t)
    return re.sub(r"\s+", " ", t).strip()


def _similar(a: TextLine, b: TextLine) -> bool:
    return 0.75 < (a.size or 1) / (b.size or 1) < 1.33


def _isolated(ln: TextLine, lines: list[TextLine]) -> bool:
    """Одиночная буква не входит в более длинную надпись: рядом на той же строке нет текста того же шрифта
    (кроме других буквенных надписей — стрелка «Г» рядом с надписью «Г-Г»)."""
    h = max(ln.bbox[3] - ln.bbox[1], 2.0)
    for o in lines:
        if o is ln or o.page != ln.page or not _similar(o, ln):
            continue
        if SECTION_RE.match(_norm(o.text)) or VIEW_RE.match(_norm(o.text)):
            continue
        if abs(o.cy - ln.cy) > 0.6 * h:
            continue
        gap = max(o.bbox[0] - ln.bbox[2], ln.bbox[0] - o.bbox[2])
        if gap < 0.9 * h:
            return False
    return True


def collect(drw: Drawing) -> dict:
    """Надписи изображений, одиночные буквы (стрелки, секущие плоскости, базы) и рамки допусков."""
    from .extract import _table_value          # подпись слева в той же строке → ячейка таблицы
    tt_ids = {id(x) for x in drw.tt_lines}
    pool = [ln for ln in drw.lines if not excluded(drw, ln) and id(ln) not in tt_ids]
    labels_txt = [ln for ln in drw.lines if len(re.findall(r"[А-Яа-я]", ln.text)) >= 3 and not excluded(drw, ln)]
    sections, views, marks, frames = [], [], [], []
    for ln in pool:
        t = _norm(ln.text)
        m = FRAME_RE.match(t)
        if m:
            frames.append({"sym": m.group("sym"), "dia": bool(m.group("dia")), "val_raw": m.group("val"),
                           "val": to_float(m.group("val")), "mod": m.group("mod"),
                           "bases": re.sub(r"\s", "", m.group("bases") or ""), "line": ln})
            continue
        m = SECTION_RE.match(t)
        if m and m.group("a") == m.group("b"):
            sections.append({"letter": m.group("a"), "word": (m.group("w") or "").strip(), "scale": m.group("sc"),
                             "line": ln})
            continue
        m = VIEW_RE.match(t)
        if not m:
            continue
        if m.group("sc") is not None or m.group("w"):
            views.append({"letter": m.group("a"), "word": (m.group("w") or "").strip(), "scale": m.group("sc"),
                          "line": ln})
        elif (_isolated(ln, drw.lines) and not re.fullmatch(r"[MМ]\d", t)
              and not _table_value(ln, [x for x in labels_txt if _similar(x, ln)])):
            marks.append({"letter": m.group("a"), "line": ln})
    return {"sections": sections, "views": views, "marks": marks, "frames": frames}


def _dim_size(drw: Drawing) -> float | None:
    sizes = sorted(ln.size for ln in drw.lines if not excluded(drw, ln) and re.fullmatch(r"[⌀R]?\d+(?:,\d+)?", ln.text.strip()))
    return sizes[len(sizes) // 2] if sizes else None


def check_views(drw: Drawing, cfg: dict) -> None:
    if drw.ocr:
        return
    c = collect(drw)
    drw.facts["views"] = {
        "sections": [s["letter"] for s in c["sections"]], "views": [v["letter"] for v in c["views"]],
        "marks": [m["letter"] for m in c["marks"]],
        "frames": [f"{f['sym']} {'⌀' if f['dia'] else ''}{f['val_raw']} {f['bases']}".strip() for f in c["frames"]],
        "scales": [x["scale"].replace(" ", "") for x in c["sections"] + c["views"] if x["scale"]]}
    labelled = {s["letter"]: s for s in c["sections"]} | {v["letter"]: v for v in c["views"]}
    mark_cnt = Counter(m["letter"] for m in c["marks"])
    frame_bases = Counter(ch for f in c["frames"] for ch in f["bases"])

    # слова «Вид», «Разрез», «Сечение»
    for x in c["sections"] + c["views"]:
        if x["word"]:
            ln = x["line"]
            drw.add(WARNING, "V04", CAT_VIEW, f"Надпись «{ln.text.strip()}»: слова «{x['word']}» над изображением "
                    f"не пишут — достаточно «{x['letter']}{'-' + x['letter'] if x in c['sections'] else ''}»",
                    ln.page, ln.bbox, STD_VIEWS)
    # масштаб изображения
    for x in c["sections"] + c["views"]:
        sc = (x["scale"] or "").replace(" ", "")
        if sc and sc not in SCALES and re.fullmatch(r"\d+(?:,\d+)?:\d+(?:,\d+)?", sc):
            ln = x["line"]
            drw.add(WARNING, "V05", CAT_VIEW, f"Масштаб «{sc}» в надписи «{ln.text.strip()}» не из ряда ГОСТ 2.302-68",
                    ln.page, ln.bbox, "ГОСТ 2.302-68")
    # повтор надписей
    seen = Counter(s["letter"] for s in c["sections"]) + Counter(v["letter"] for v in c["views"])
    for letter, n in seen.items():
        if n > 1:
            ln = labelled[letter]["line"]
            drw.add(ERROR, "V02", CAT_VIEW, f"Буквенное обозначение «{letter}» присвоено {n} изображениям — буквы "
                    f"не повторяют", ln.page, ln.bbox, STD_LETTERS)
    # запрещённые буквы
    used = [(x["letter"], x["line"]) for x in c["sections"] + c["views"] + c["marks"]]
    used += [(ch, f["line"]) for f in c["frames"] for ch in f["bases"]]
    reported = set()
    for letter, ln in used:
        ch = letter[0]
        if (ch in FORBIDDEN_LETTERS or ch in FORBIDDEN_LATIN) and ch not in reported:
            reported.add(ch)
            drw.add(WARNING, "V01", CAT_VIEW, f"Буква «{ch}» в обозначении «{ln.text.strip()}» не применяется "
                    f"(исключены Ё, З, Й, О, Ч, Х, Ъ, Ы, Ь и латинские I, O)", ln.page, ln.bbox,
                    "ГОСТ 2.316-2008 п. 4.17")
    # обозначение на изображении у разрезов и выносных элементов
    for x in c["sections"] + c["views"]:
        letter = x["letter"]
        if mark_cnt[letter] == 0 and letter not in frame_bases:
            ln = x["line"]
            kind = "секущей плоскости" if x in c["sections"] else "направления взгляда / выносного элемента"
            drw.add(WARNING, "V03", CAT_VIEW, f"Изображение «{ln.text.strip()}»: на чертеже нет обозначения "
                    f"{kind} с буквой «{letter}»", ln.page, ln.bbox, STD_VIEWS)

    # --- рамки допусков формы и расположения
    base_marks = {m["letter"] for m in c["marks"] if m["letter"] not in labelled}
    big = _dim_size(drw)
    missing: dict[str, list] = {}
    for f in c["frames"]:
        for ch in dict.fromkeys(f["bases"]):
            if ch not in base_marks:
                missing.setdefault(ch, []).append(f)
    for ch, fl in missing.items():
        ln = fl[0]["line"]
        names = list(dict.fromkeys(_norm(x["line"].text) for x in fl))
        frames_txt = ", ".join(f"«{n}»" for n in names) + (f" ({len(fl)} рамки)" if len(fl) > 1 else "")
        if ch in labelled:
            lab = labelled[ch]["line"].text.strip()
            drw.add(ERROR, "G01", CAT_GDT, f"Рамки {frames_txt} ссылаются на базу «{ch}», но знак базы «{ch}» на "
                    f"чертеже не обозначен — буква «{ch}» обозначает изображение «{lab}». Обозначенные базы: "
                    f"{', '.join(sorted(base_marks)) or 'нет'}", ln.page, ln.bbox, STD_GDT)
        else:
            drw.add(ERROR, "G01", CAT_GDT, f"Рамки {frames_txt} ссылаются на базу «{ch}», которая на чертеже не "
                    f"обозначена", ln.page, ln.bbox, STD_GDT)
    seen_frames = set()
    for f in c["frames"]:
        ln = f["line"]
        kind = GDT_KIND.get(f["sym"], "допуск")
        if _norm(ln.text) in seen_frames:
            continue
        seen_frames.add(_norm(ln.text))
        if f["val"] is not None and not any(abs(f["val"] * 1000 - x) < 1e-6 for x in GDT_SERIES_UM):
            near = sorted(GDT_SERIES_UM, key=lambda x: abs(x - f["val"] * 1000))[:2]
            drw.add(WARNING, "G02", CAT_GDT, f"Допуск {f['val_raw']} в рамке «{ln.text.strip()}» не из ряда "
                    f"ГОСТ 24643-81 (ближайшие: {', '.join(fmtn(x / 1000) for x in sorted(near))})",
                    ln.page, ln.bbox, "ГОСТ 24643-81")
        if "." in f["val_raw"]:
            drw.add(WARNING, "D07", CAT_DIM, f"В рамке допуска «{ln.text.strip()}» дробная часть отделена точкой — "
                    f"по ЕСКД используют запятую", ln.page, ln.bbox, "ГОСТ 2.308-2011")
        if f["sym"] in GDT_NEEDS_BASE and not f["bases"]:
            drw.add(WARNING, "G03", CAT_GDT, f"Рамка «{ln.text.strip()}»: {kind} задают относительно базы, а база "
                    f"не указана", ln.page, ln.bbox, STD_GDT)
    if c["frames"]:
        for m in c["marks"]:
            ch = m["letter"]
            ln = m["line"]
            if ch in labelled or ch in frame_bases:
                continue
            if big and ln.size > 1.5 * big:
                drw.add(WARNING, "V08", CAT_VIEW, f"Обозначение «{ch}» (стрелка/секущая плоскость) есть, а "
                        f"изображения «{ch}» или «{ch}-{ch}» на чертеже нет", ln.page, ln.bbox, STD_VIEWS)
            else:
                drw.add(INFO, "G04", CAT_GDT, f"База «{ch}» обозначена, но не используется ни в одной рамке "
                        f"допуска на этом чертеже", ln.page, ln.bbox, STD_GDT)

    # порядок букв и размер шрифта
    letters = sorted({x[0][0] for x in used if x[0][0] in CYR_ALPHABET}, key=CYR_ALPHABET.index)
    if letters:
        expected = CYR_ALPHABET[:CYR_ALPHABET.index(letters[-1]) + 1]
        missing = [ch for ch in expected if ch not in letters]
        if missing:
            drw.add(INFO, "V06", CAT_VIEW, f"Буквенные обозначения с пропусками: использованы "
                    f"{', '.join(letters)}; пропущены {', '.join(missing)}", None, None, "ГОСТ 2.316-2008 п. 4.17")
    if big:
        for x in c["sections"] + c["views"]:
            ln = x["line"]
            if ln.size < 1.35 * big:
                drw.add(INFO, "V07", CAT_VIEW, f"Надпись «{ln.text.strip()}»: шрифт буквенного обозначения "
                        f"({fmtn(round(ln.size, 1))}) должен быть примерно вдвое больше размерных чисел "
                        f"({fmtn(round(big, 1))})", ln.page, ln.bbox, "ГОСТ 2.316-2008 п. 4.18")
                break
