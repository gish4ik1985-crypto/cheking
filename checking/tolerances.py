"""Допуски и посадки по ГОСТ 25346-2013 / ГОСТ 25347-2013 (ISO 286-1/-2).

Все табличные величины — в микрометрах, наружу функции отдают миллиметры.
Основные отклонения полностью покрыты для размеров до 500 мм;
поля H/h/JS/js — до 3150 мм (для них нужен только квалитет).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --- Квалитеты IT1..IT18 (ГОСТ 25346-2013, табл. 1), мкм -------------------
IT_RANGES = [3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500,
             630, 800, 1000, 1250, 1600, 2000, 2500, 3150]
IT_TABLE = [
    # IT1  IT2  IT3  IT4  IT5  IT6  IT7  IT8  IT9  IT10 IT11  IT12  IT13  IT14  IT15  IT16   IT17   IT18
    [0.8, 1.2, 2, 3, 4, 6, 10, 14, 25, 40, 60, 100, 140, 250, 400, 600, 1000, 1400],
    [1, 1.5, 2.5, 4, 5, 8, 12, 18, 30, 48, 75, 120, 180, 300, 480, 750, 1200, 1800],
    [1, 1.5, 2.5, 4, 6, 9, 15, 22, 36, 58, 90, 150, 220, 360, 580, 900, 1500, 2200],
    [1.2, 2, 3, 5, 8, 11, 18, 27, 43, 70, 110, 180, 270, 430, 700, 1100, 1800, 2700],
    [1.5, 2.5, 4, 6, 9, 13, 21, 33, 52, 84, 130, 210, 330, 520, 840, 1300, 2100, 3300],
    [1.5, 2.5, 4, 7, 11, 16, 25, 39, 62, 100, 160, 250, 390, 620, 1000, 1600, 2500, 3900],
    [2, 3, 5, 8, 13, 19, 30, 46, 74, 120, 190, 300, 460, 740, 1200, 1900, 3000, 4600],
    [2.5, 4, 6, 10, 15, 22, 35, 54, 87, 140, 220, 350, 540, 870, 1400, 2200, 3500, 5400],
    [3.5, 5, 8, 12, 18, 25, 40, 63, 100, 160, 250, 400, 630, 1000, 1600, 2500, 4000, 6300],
    [4.5, 7, 10, 14, 20, 29, 46, 72, 115, 185, 290, 460, 720, 1150, 1850, 2900, 4600, 7200],
    [6, 8, 12, 16, 23, 32, 52, 81, 130, 210, 320, 520, 810, 1300, 2100, 3200, 5200, 8100],
    [7, 9, 13, 18, 25, 36, 57, 89, 140, 230, 360, 570, 890, 1400, 2300, 3600, 5700, 8900],
    [8, 10, 15, 20, 27, 40, 63, 97, 155, 250, 400, 630, 970, 1550, 2500, 4000, 6300, 9700],
    [9, 11, 16, 22, 32, 44, 70, 110, 175, 280, 440, 700, 1100, 1750, 2800, 4400, 7000, 11000],
    [10, 13, 18, 25, 36, 50, 80, 125, 200, 320, 500, 800, 1250, 2000, 3200, 5000, 8000, 12500],
    [11, 15, 21, 28, 40, 56, 90, 140, 230, 360, 560, 900, 1400, 2300, 3600, 5600, 9000, 14000],
    [13, 18, 24, 33, 47, 66, 105, 165, 260, 420, 660, 1050, 1650, 2600, 4200, 6600, 10500, 16500],
    [15, 21, 29, 39, 55, 78, 125, 195, 310, 500, 780, 1250, 1950, 3100, 5000, 7800, 12500, 19500],
    [18, 25, 35, 46, 65, 92, 150, 230, 370, 600, 920, 1500, 2300, 3700, 6000, 9200, 15000, 23000],
    [22, 30, 41, 55, 78, 110, 175, 280, 440, 700, 1100, 1750, 2800, 4400, 7000, 11000, 17500, 28000],
    [26, 36, 50, 68, 96, 135, 210, 330, 540, 860, 1350, 2100, 3300, 5400, 8600, 13500, 21000, 33000],
]

# --- Основные отклонения (ГОСТ 25346-2013, табл. 2, 3), мкм ----------------
# 25 интервалов до 500 мм с промежуточными подынтервалами
SUB_RANGES = [3, 6, 10, 14, 18, 24, 30, 40, 50, 65, 80, 100, 120, 140, 160, 180,
              200, 225, 250, 280, 315, 355, 400, 450, 500]
# соответствие подынтервала основному интервалу (13 интервалов до 500 мм)
_SUB_TO_MAIN = [0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 8, 9, 9, 9, 10, 10, 11, 11, 12, 12]

N = None
# верхние отклонения es валов a..h (для отверстий A..H: EI = -es)
SHAFT_ES = {
    "a": [-270, -270, -280, -290, -290, -300, -300, -310, -320, -340, -360, -380, -410, -460, -520,
          -580, -660, -740, -820, -920, -1050, -1200, -1350, -1500, -1650],
    "b": [-140, -140, -150, -150, -150, -160, -160, -170, -180, -190, -200, -220, -240, -260, -280,
          -310, -340, -380, -420, -480, -540, -600, -680, -760, -840],
    "c": [-60, -70, -80, -95, -95, -110, -110, -120, -130, -140, -150, -170, -180, -200, -210,
          -230, -240, -260, -280, -300, -330, -360, -400, -440, -480],
    "cd": [-34, -46, -56] + [N] * 22,
    "d": [-20, -30, -40, -50, -50, -65, -65, -80, -80, -100, -100, -120, -120, -145, -145,
          -145, -170, -170, -170, -190, -190, -210, -210, -230, -230],
    "e": [-14, -20, -25, -32, -32, -40, -40, -50, -50, -60, -60, -72, -72, -85, -85,
          -85, -100, -100, -100, -110, -110, -125, -125, -135, -135],
    "ef": [-10, -14, -18] + [N] * 22,
    "f": [-6, -10, -13, -16, -16, -20, -20, -25, -25, -30, -30, -36, -36, -43, -43,
          -43, -50, -50, -50, -56, -56, -62, -62, -68, -68],
    "fg": [-4, -6, -8] + [N] * 22,
    "g": [-2, -4, -5, -6, -6, -7, -7, -9, -9, -10, -10, -12, -12, -14, -14,
          -14, -15, -15, -15, -17, -17, -18, -18, -20, -20],
    "h": [0] * 25,
}

# нижние отклонения ei валов j..zc; по 13 основным интервалам там, где подынтервалы не различаются
_MAIN13 = {
    "j5": [-2, -2, -2, -3, -4, -5, -7, -9, -11, -13, -16, -18, -20],
    "j6": [-2, -2, -2, -3, -4, -5, -7, -9, -11, -13, -16, -18, -20],
    "j7": [-4, -4, -5, -6, -8, -10, -12, -15, -18, -21, -26, -28, -32],
    "j8": [-6] + [N] * 12,
    "k": [0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5],          # для IT4..IT7; иначе 0
    "m": [2, 4, 6, 7, 8, 9, 11, 13, 15, 17, 20, 21, 23],
    "n": [4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40],
    "p": [6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68],
}
SHAFT_EI = {k: [v[_SUB_TO_MAIN[i]] for i in range(25)] for k, v in _MAIN13.items()}
SHAFT_EI.update({
    "r": [10, 15, 19, 23, 23, 28, 28, 34, 34, 41, 43, 51, 54, 63, 65, 68, 77, 80, 84, 94, 98, 108, 114, 126, 132],
    "s": [14, 19, 23, 28, 28, 35, 35, 43, 43, 53, 59, 71, 79, 92, 100, 108, 122, 130, 140, 158, 170, 190, 208, 232, 252],
    "t": [N, N, N, N, N, N, 41, 48, 54, 66, 75, 91, 104, 122, 134, 146, 166, 180, 196, 218, 240, 268, 294, 330, 360],
    "u": [18, 23, 28, 33, 33, 41, 48, 60, 70, 87, 102, 124, 144, 170, 190, 210, 236, 258, 284, 315, 350, 390, 435, 490, 540],
    "v": [N, N, N, N, 39, 47, 55, 68, 81, 102, 120, 146, 172, 202, 228, 252, 284, 310, 340, 385, 425, 475, 530, 595, 660],
    "x": [20, 28, 34, 40, 45, 54, 64, 80, 97, 122, 146, 178, 210, 248, 280, 310, 350, 385, 425, 475, 525, 590, 660, 740, 820],
    "y": [N, N, N, N, N, 63, 75, 94, 114, 144, 174, 214, 254, 300, 340, 380, 425, 470, 520, 580, 650, 730, 820, 920, 1000],
    "z": [26, 35, 42, 50, 60, 73, 88, 112, 136, 172, 210, 258, 310, 365, 415, 465, 520, 575, 640, 710, 790, 900, 1000, 1100, 1250],
    "za": [32, 42, 52, 64, 77, 98, 118, 148, 180, 226, 274, 335, 400, 470, 535, 600, 670, 740, 820, 920, 1000, 1150, 1300, 1450, 1600],
    "zb": [40, 50, 67, 90, 108, 136, 160, 200, 242, 300, 360, 445, 525, 620, 700, 780, 880, 960, 1050, 1200, 1300, 1500, 1650, 1850, 2100],
    "zc": [60, 80, 97, 130, 150, 188, 218, 274, 325, 405, 480, 585, 690, 800, 900, 1000, 1150, 1250, 1350, 1550, 1700, 1900, 2100, 2400, 2600],
})

# верхние отклонения ES отверстий J6..J8 (по 13 основным интервалам)
HOLE_J_ES = {
    6: [2, 5, 5, 6, 8, 10, 13, 16, 18, 22, 25, 29, 33],
    7: [4, 6, 8, 10, 12, 14, 18, 22, 26, 30, 36, 39, 43],
    8: [6, 10, 12, 15, 20, 24, 28, 34, 41, 47, 55, 60, 66],
}

SHAFT_LETTERS = ["a", "b", "c", "cd", "d", "e", "ef", "f", "fg", "g", "h", "js", "j", "k", "m", "n",
                 "p", "r", "s", "t", "u", "v", "x", "y", "z", "za", "zb", "zc"]
HOLE_LETTERS = [x.upper() for x in SHAFT_LETTERS]

# Ряды полей допусков ГОСТ 25347-2013 (ISO 286-2): буква -> (мин. квалитет, макс. квалитет)
SHAFT_GRADE_SPAN = {
    "a": (9, 13), "b": (8, 13), "c": (8, 12), "cd": (5, 10), "d": (5, 13), "e": (5, 10), "ef": (3, 10),
    "f": (3, 10), "fg": (3, 10), "g": (3, 10), "h": (1, 18), "js": (1, 18), "j": (5, 8), "k": (3, 13),
    "m": (3, 9), "n": (3, 9), "p": (3, 10), "r": (3, 10), "s": (3, 10), "t": (5, 8), "u": (5, 9),
    "v": (5, 8), "x": (5, 10), "y": (6, 10), "z": (6, 11), "za": (6, 11), "zb": (7, 11), "zc": (7, 11),
}
HOLE_GRADE_SPAN = {
    "A": (9, 13), "B": (8, 13), "C": (8, 13), "CD": (6, 10), "D": (6, 13), "E": (5, 10), "EF": (3, 10),
    "F": (3, 10), "FG": (3, 10), "G": (3, 10), "H": (1, 18), "JS": (1, 18), "J": (6, 8), "K": (3, 10),
    "M": (3, 10), "N": (3, 11), "P": (3, 10), "R": (3, 10), "S": (3, 10), "T": (5, 8), "U": (5, 10),
    "V": (5, 8), "X": (5, 10), "Y": (6, 10), "Z": (6, 11), "ZA": (6, 11), "ZB": (7, 11), "ZC": (7, 11),
}

# Предпочтительные поля и посадки (ГОСТ 25347-2013, выделенные в таблицах)
PREFERRED_SHAFTS = {"d9", "d11", "e8", "f7", "g6", "h6", "h7", "h8", "h9", "h11",
                    "js6", "k6", "n6", "p6", "r6", "s6"}
PREFERRED_HOLES = {"D10", "E9", "F8", "G7", "H7", "H8", "H9", "H11", "JS7", "K7", "N7", "P7"}
PREFERRED_FITS = {
    # система отверстия
    "H7/e8", "H7/f7", "H7/g6", "H7/h6", "H7/js6", "H7/k6", "H7/n6", "H7/p6", "H7/r6", "H7/s6",
    "H8/d9", "H8/e8", "H8/f7", "H8/h7", "H8/h8", "H9/d9", "H9/h9", "H11/d11", "H11/h11",
    # система вала
    "E9/h8", "F8/h6", "F8/h7", "G7/h6", "JS7/h6", "K7/h6", "N7/h6", "P7/h6", "H8/h6", "D10/h9", "E9/h9",
}

_FIELD_RE = re.compile(r"^(?P<letter>[A-Za-z]{1,2})(?P<grade>0?1|\d{1,2})$")


class ToleranceError(ValueError):
    """Поле допуска не может быть вычислено (нет такого поля/интервала)."""


@dataclass
class Field:
    letter: str
    grade: int
    is_hole: bool

    @property
    def code(self) -> str:
        return f"{self.letter}{self.grade}"


def parse_field(code: str) -> Field:
    code = code.strip()
    m = _FIELD_RE.match(code)
    if not m:
        raise ToleranceError(f"«{code}» — не обозначение поля допуска")
    letter, grade_s = m.group("letter"), m.group("grade")
    if grade_s in ("0", "01"):
        raise ToleranceError(f"Квалитет IT{grade_s} практически не применяется в машиностроении")
    grade = int(grade_s)
    if not 1 <= grade <= 18:
        raise ToleranceError(f"Квалитета IT{grade} не существует (допустимы IT01, IT0, IT1…IT18)")
    if letter.isupper() and letter in HOLE_LETTERS:
        return Field(letter, grade, True)
    if letter.islower() and letter in SHAFT_LETTERS:
        return Field(letter, grade, False)
    if letter.lower() in SHAFT_LETTERS:
        raise ToleranceError(
            f"«{letter}» — смешанный регистр: отверстия обозначают прописными, валы строчными буквами")
    raise ToleranceError(f"Основного отклонения «{letter}» не существует (ГОСТ 25346-2013)")


def _main_index(size: float) -> int:
    if size <= 0:
        raise ToleranceError("Номинальный размер должен быть больше 0")
    for i, b in enumerate(IT_RANGES):
        if size <= b + 1e-9:
            return i
    raise ToleranceError(f"Размер {fmt(size)} мм больше 3150 мм — вне ГОСТ 25346")


def _sub_index(size: float) -> int:
    for i, b in enumerate(SUB_RANGES):
        if size <= b + 1e-9:
            return i
    raise ToleranceError(f"Для размеров свыше 500 мм основное отклонение не табулировано в программе")


def it_value(size: float, grade: int) -> float:
    """Допуск квалитета, мкм."""
    if not 1 <= grade <= 18:
        raise ToleranceError(f"IT{grade} вне таблицы")
    if size <= 1 and grade >= 14:
        raise ToleranceError("Квалитеты IT14…IT18 не применяются для размеров до 1 мм")
    return IT_TABLE[_main_index(size)][grade - 1]


def _delta(size: float, grade: int) -> float:
    """Δ = ITn − IT(n−1) для правила отверстий K…ZC (ГОСТ 25346, п. 7.2)."""
    if size <= 3 or grade < 3 or grade > 8:
        return 0.0
    row = IT_TABLE[_main_index(size)]
    return row[grade - 1] - row[grade - 2]


def _shaft_limits_um(size: float, letter: str, grade: int) -> tuple[float, float]:
    it = it_value(size, grade)
    if letter == "h":
        return 0.0, -it
    if letter == "js":
        half = it / 2
        return half, -half
    i = _sub_index(size)
    if letter in SHAFT_ES:
        es = SHAFT_ES[letter][i]
        if es is None:
            raise ToleranceError(f"Поле {letter}{grade} не установлено для размера {fmt(size)} мм")
        return es, es - it
    if letter == "j":
        key = f"j{grade}"
        if key not in SHAFT_EI or SHAFT_EI[key][i] is None:
            raise ToleranceError(f"Поле j{grade} не установлено стандартом для размера {fmt(size)} мм")
        ei = SHAFT_EI[key][i]
        return ei + it, ei
    if letter == "k":
        ei = SHAFT_EI["k"][i] if 4 <= grade <= 7 else 0
        return ei + it, ei
    if letter in SHAFT_EI:
        ei = SHAFT_EI[letter][i]
        if ei is None:
            raise ToleranceError(f"Поле {letter}{grade} не установлено для размера {fmt(size)} мм")
        return ei + it, ei
    raise ToleranceError(f"Неизвестное основное отклонение «{letter}»")


def _hole_limits_um(size: float, letter: str, grade: int) -> tuple[float, float]:
    it = it_value(size, grade)
    low = letter.lower()
    if letter == "H":
        return it, 0.0
    if letter == "JS":
        half = it / 2
        return half, -half
    i = _sub_index(size)
    if low in SHAFT_ES:                       # A..G: EI = -es
        es = SHAFT_ES[low][i]
        if es is None:
            raise ToleranceError(f"Поле {letter}{grade} не установлено для размера {fmt(size)} мм")
        ei_hole = -es
        return ei_hole + it, ei_hole
    if letter == "J":
        if grade not in HOLE_J_ES:
            raise ToleranceError(f"Поле J{grade} не установлено стандартом (есть J6, J7, J8)")
        es = HOLE_J_ES[grade][_SUB_TO_MAIN[i]]
        return es, es - it
    if letter == "K":
        if grade <= 8:
            # для K ≤ IT8: ES = −ei(k) + Δ, где ei(k) — табличное значение для IT4…IT7
            es = -SHAFT_EI["k"][i] + _delta(size, grade)
        else:
            es = 0.0
        return es, es - it
    if letter == "M":
        m_ei = SHAFT_EI["m"][i]
        es = -m_ei + _delta(size, grade) if grade <= 8 else -m_ei
        return es, es - it
    if letter == "N":
        n_ei = SHAFT_EI["n"][i]
        if grade <= 8:
            es = -n_ei + _delta(size, grade)
        else:
            es = -4.0 if size <= 3 else 0.0
        return es, es - it
    if low in SHAFT_EI:                       # P..ZC
        ei_shaft = SHAFT_EI[low][i]
        if ei_shaft is None:
            raise ToleranceError(f"Поле {letter}{grade} не установлено для размера {fmt(size)} мм")
        es = -ei_shaft + (_delta(size, grade) if grade <= 7 else 0.0)
        return es, es - it
    raise ToleranceError(f"Неизвестное основное отклонение «{letter}»")


def limits(size: float, code: str) -> tuple[float, float]:
    """Предельные отклонения (верхнее, нижнее) в мм для поля допуска, например limits(20, 'H7')."""
    f = parse_field(code)
    if f.is_hole:
        up, lo = _hole_limits_um(size, f.letter, f.grade)
    else:
        up, lo = _shaft_limits_um(size, f.letter, f.grade)
    return round(up / 1000, 4), round(lo / 1000, 4)


def in_standard_series(code: str) -> bool:
    f = parse_field(code)
    span = (HOLE_GRADE_SPAN if f.is_hole else SHAFT_GRADE_SPAN).get(f.letter)
    return bool(span and span[0] <= f.grade <= span[1])


def equivalent_grade(size: float, tolerance_mm: float) -> int | None:
    """Ближайший квалитет, допуск которого не превышает заданный (для оценки «жёсткости»)."""
    try:
        row = IT_TABLE[_main_index(size)]
    except ToleranceError:
        return None
    t_um = tolerance_mm * 1000
    best = None
    for g, v in enumerate(row, start=1):
        if v <= t_um * 1.0001:
            best = g
    return best if best is not None else 0


@dataclass
class FitInfo:
    hole: str
    shaft: str
    kind: str            # зазор / переходная / натяг
    smax: float          # мм; отрицательный = натяг
    smin: float
    hole_limits: tuple[float, float]
    shaft_limits: tuple[float, float]


def fit_info(size: float, hole: str, shaft: str) -> FitInfo:
    hl = limits(size, hole)
    sl = limits(size, shaft)
    smax = round(hl[0] - sl[1], 4)
    smin = round(hl[1] - sl[0], 4)
    if smin >= 0:
        kind = "с зазором"
    elif smax <= 0:
        kind = "с натягом"
    else:
        kind = "переходная"
    return FitInfo(hole, shaft, kind, smax, smin, hl, sl)


def fmt(v: float | None, sign: bool = False) -> str:
    """Число в стиле ЕСКД: запятая, без лишних нулей."""
    if v is None:
        return "—"
    s = f"{v:+.4f}" if sign else f"{v:.4f}"
    s = s.rstrip("0").rstrip(".")
    if s in ("+0", "-0"):
        s = "0"
    return s.replace(".", ",")
