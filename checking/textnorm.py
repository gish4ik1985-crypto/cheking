"""Нормализация текста: перекодировка символьных шрифтов КОМПАС, похожие буквы, числа."""
from __future__ import annotations

import re
import unicodedata

# Символы шрифтов КОМПАС в PDF выводятся «чужими» кодами
FONT_REMAP = {
    "symbol_a": {"Ç": "⌀", "Å": "°", "ì": "⊿", "±": "±", "Ñ": "⌀"},
    "symbol_b": {"Ç": "⌀", "Å": "°", "ì": "⊿"},
    "gosttypea": {"•": "×"},
    "gosttypeb": {"•": "×"},
    "gost type a": {"•": "×"},
    # Solid Edge: значки размеров и рамок допусков выводятся символьным шрифтом (сверено по листам)
    "solidedgeansi1symbols": {"O": "⌀", "v": "°", "n": "⌀", "Ø": "⌀", "a": "◎", "^": "↗", "l": "⌖", "M": "Ⓜ"},
    "solidedgeansigdtsymbols": {"‘": "⟲"},          # знак «повёрнуто» у надписи вида
    "solidedgeiso1symbols": {"O": "⌀", "v": "°", "n": "⌀"},
}

LAT_TO_CYR = str.maketrans("ABCEHKMOPTXaceopxy", "АВСЕНКМОРТХасеорху")
CYR_TO_LAT = str.maketrans("АВСЕНКМОРТХасеорхуЈ", "ABCEHKMOPTXaceopxyJ")


def remap_char(ch: str, font: str) -> str:
    f = font.lower()
    for key, table in FONT_REMAP.items():
        if key in f:
            return table.get(ch, ch)
    return ch


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


_DIAM_OCR = re.compile(r"(?:(?<=^)|(?<=\s))[φΦØø∅$Ф](?=\s?\d)")


def normalize_dim(s: str) -> str:
    """Приводит текст размера к канону: ⌀, ×, «-», без лишних пробелов."""
    s = nfc(s).replace(" ", " ")
    s = _DIAM_OCR.sub("⌀", s)
    s = s.replace("Ø", "⌀").replace("∅", "⌀").replace("ø", "⌀")
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = s.replace("•", "×")
    s = re.sub(r"(?<=[\d)])\s*[xXхХ]\s*(?=\d)", "×", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def to_float(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip().replace(" ", "").replace(",", ".")
    if s in ("", "+", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def norm_designation(s: str) -> str:
    """Канон обозначения для сравнения: верхний регистр, кириллица, без пробелов."""
    s = nfc(s or "").upper().translate(LAT_TO_CYR)
    s = re.sub(r"\s+", "", s)
    return s


def norm_words(s: str) -> str:
    s = nfc(s or "").lower().replace("ё", "е")
    s = re.sub(r"[^\w]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --- исправление типовых ошибок OCR в русском тексте -------------------------
_OCR_LAT = str.maketrans("ABCEHKMOPTXaceopxyBmnu", "АВСЕНКМОРТХасеорхуВтпи")
_LAT_WORDS = {"DIN", "EN", "ISO", "AISI", "RAL", "PRODECOR", "SKF", "LH", "PP", "PE", "PA6"}
_SORT_WORDS = ["Лист", "Полоса", "Круг", "Пруток", "Квадрат", "Шестигранник", "Труба", "Профиль", "Уголок",
               "Швеллер", "Двутавр", "Лента", "Проволока", "Плита", "ГОСТ", "Масса", "Масштаб"]


def ocr_fix(text: str) -> str:
    """«Луст 5,0 Г0CТ 19903» → «Лист 5,0 ГОСТ 19903», «Cm3cn» → «Ст3сп»."""
    import difflib
    out = []
    for tok in text.split(" "):
        core = tok.strip("\"'«»()")
        if not core or core.upper() in _LAT_WORDS or re.fullmatch(r"[\d.,\-–/×x*]+", core):
            out.append(tok)
            continue
        has_cyr = bool(re.search(r"[А-Яа-яЁё]", core))
        latin_only_lookalike = bool(re.fullmatch(r"[ABCEHKMOPTXaceopxyBmnu0-9\-]+", core)) and re.search(r"\d", core)
        if has_cyr or latin_only_lookalike:
            t = tok.translate(_OCR_LAT)
            t = re.sub(r"(?<=[А-Яа-я])0|0(?=[А-Яа-я])", "О", t)
            letters = re.sub(r"[^А-Яа-я]", "", t)
            if 3 <= len(letters) <= 12 and not re.search(r"\d", t):
                m = difflib.get_close_matches(t.strip("\"'«»().,"), _SORT_WORDS, n=1, cutoff=0.74)
                if m:
                    t = t.replace(t.strip("\"'«»().,"), m[0])
            tok = t
        out.append(tok)
    return " ".join(out)


def ref_key(s: str) -> str:
    """Ключ для нечёткого поиска ссылок на стандарты: «ОСТ4 Го.о70.014» ≈ «ОСТ4 ГО.070.014»."""
    s = nfc(s or "").upper().translate(LAT_TO_CYR)
    s = s.replace("О", "0")
    return re.sub(r"[\s.,\-–]", "", s)
