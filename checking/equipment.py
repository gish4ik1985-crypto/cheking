"""Профиль оборудования предприятия: что производство умеет делать и какие размеры берёт.

Профиль хранится в config.json → "equipment": {"items": [...]}; пока там пусто, берётся перечень из ERP
(equipment_data.ERP_EQUIPMENT). Каждая запись — станок или установка:
    {"id": 63, "workshop": "301", "type": "...", "model": "LM3512HGP", "year": 2024, "kind": "laser_sheet",
     "qty": 1, "active": true, "params": {"laser_kw": 20, "bed_l": 3500, "bed_w": 1200, ...},
     "src": {"laser_kw": "type", "bed_l": "model", ...}}
Источник параметра: «model» — выведен из обозначения модели, «type» — из названия типа, «estimate» — ориентир по таблице
(мощность лазера → предельная толщина), «passport» — внесён по паспорту, «manual» — введён вручную. Всё, что не «passport»,
нужно уточнить по паспорту станка: правила блока «Возможности производства» пользуются теми же числами.

Профиль только описывает возможности. Если параметр не задан, проверки по нему молчат (не угадывают)."""
from __future__ import annotations

import copy
import re

from .equipment_data import ERP_EQUIPMENT

# вид оборудования → название
KINDS: dict[str, str] = {
    "lathe": "Токарно-винторезный станок", "lathe_cnc": "Токарный станок с ЧПУ", "lathe_carousel": "Токарно-карусельный станок",
    "mill_v": "Вертикально-фрезерный станок", "mill_h": "Горизонтально-фрезерный станок", "mill_cnc": "Фрезерный станок с ЧПУ",
    "drill": "Сверлильный станок", "drill_radial": "Радиально-сверлильный станок", "boring_h": "Горизонтально-расточной станок",
    "boring_coord": "Координатно-расточной станок", "slotter": "Долбёжный станок",
    "gear_hob": "Зубофрезерный станок", "gear_shaper": "Зубодолбёжный станок", "spline_hob": "Шлицефрезерный станок",
    "grind_round": "Круглошлифовальный станок", "grind_flat": "Плоскошлифовальный станок",
    "grind_rough": "Обдирочно-шлифовальный, заточной станок", "edm_wire": "Электроэрозионный проволочно-вырезной станок",
    "laser_sheet": "Лазерная резка листа", "laser_tube": "Лазерный труборез", "laser_weld": "Лазерная сварка / чистка",
    "saw_band": "Ленточнопильный станок", "press_brake": "Листогибочный станок", "rolls": "Вальцы (листогибочная машина)",
    "shear": "Ножницы гильотинные", "press": "Пресс", "furnace": "Электропечь (термообработка)",
    "induction": "Генератор ТВЧ (закалка токами высокой частоты)", "injection": "Литьевая машина",
    "thread_manip": "Резьбонарезной манипулятор", "tester": "Испытательная машина",
    # виды, которых в списке ERP нет: профиль показывает, чего не хватает (правила молчат, пока записей нет)
    "gear_grind": "Зубошлифовальный станок", "lapping": "Притирочный, хонинговальный станок (доводка)",
    "plating": "Гальваника, химическое покрытие", "other": "Прочее",
}

# параметр → (название, единица)
PARAMS: dict[str, tuple[str, str]] = {
    "swing": ("Наибольший диаметр обработки (над станиной, планшайба)", "мм"),
    "length_max": ("Наибольшая длина обрабатываемой детали", "мм"),
    "table_l": ("Стол: длина", "мм"), "table_w": ("Стол: ширина", "мм"),
    "drill_d": ("Наибольший диаметр сверления", "мм"), "spindle_d": ("Диаметр шпинделя", "мм"),
    "gear_d": ("Наибольший диаметр нарезаемого колеса", "мм"), "gear_m": ("Наибольший модуль", "мм"),
    "laser_kw": ("Мощность лазера", "кВт"), "bed_l": ("Рабочее поле: длина", "мм"), "bed_w": ("Рабочее поле: ширина", "мм"),
    "t_steel": ("Предельная толщина: углеродистая сталь", "мм"), "t_stainless": ("Предельная толщина: нержавеющая сталь", "мм"),
    "t_alu": ("Предельная толщина: алюминий", "мм"),
    "tube_l": ("Труба: наибольшая длина", "мм"), "tube_d": ("Труба: наибольший диаметр", "мм"),
    "roll_w": ("Вальцы: ширина листа", "мм"), "roll_t": ("Вальцы: наибольшая толщина", "мм"),
    "brake_l": ("Листогиб: длина гиба", "мм"), "brake_t": ("Листогиб: наибольшая толщина", "мм"),
}

KIND_PARAMS: dict[str, list[str]] = {
    "lathe": ["swing", "length_max"], "lathe_cnc": ["swing", "length_max"], "lathe_carousel": ["swing"],
    "mill_v": ["table_l", "table_w"], "mill_h": ["table_l", "table_w"], "mill_cnc": ["table_l", "table_w"],
    "grind_flat": ["table_l", "table_w"], "grind_round": ["swing", "length_max"],
    "drill": ["drill_d"], "drill_radial": ["drill_d"], "boring_h": ["spindle_d"],
    "gear_hob": ["gear_d", "gear_m"], "gear_shaper": ["gear_d", "gear_m"], "spline_hob": ["gear_d", "gear_m"],
    "laser_sheet": ["laser_kw", "bed_l", "bed_w", "t_steel", "t_stainless", "t_alu"],
    "laser_tube": ["tube_l", "tube_d"], "rolls": ["roll_w", "roll_t"], "press_brake": ["brake_l", "brake_t"],
}

# порядок проверки названия типа: более конкретные признаки — раньше
_KIND_RX: list[tuple[str, str]] = [
    ("laser_tube", r"лазерный труборез|труборез"), ("laser_weld", r"лазерной сварки|лазерной чистки"),
    ("laser_sheet", r"лазерной резки|лазерный станок"), ("edm_wire", r"электроэрозион"),
    ("lathe_cnc", r"токарн\w*(?:-винторезн\w*)?\s+с\s+чпу"), ("lathe_carousel", r"карусельн"), ("lathe", r"токарн"),
    ("boring_coord", r"координатно-расточн|кординатно"), ("boring_h", r"горизонтально-расточн|горизонтально расточн"),
    ("mill_cnc", r"фрезерн\w*\s+с\s+чпу"), ("mill_h", r"горизонтально-фрезерн"), ("mill_v", r"вертикально-фрезерн"),
    ("gear_grind", r"зубошлифовальн"), ("gear_hob", r"зубофрезерн"), ("gear_shaper", r"зубодолбежн|зубодолбёжн"),
    ("spline_hob", r"шлицефрезерн"), ("grind_round", r"круглошлифовальн|кругло\s*шлифовальн"),
    ("grind_flat", r"плоскошлифовальн|плоско\s*шлифовальн"), ("grind_rough", r"обдирочно-шлифовальн|точильно-шлифовальн|заточн"),
    ("rolls", r"вальцы|\(вальцы\)"), ("press_brake", r"листогибочн|листогиб"), ("shear", r"ножницы"),
    ("drill_radial", r"радиально-сверлильн|радиально сверлильн"), ("drill", r"сверлильн"), ("slotter", r"долбежн|долбёжн"),
    ("saw_band", r"ленточн\w*\s*-?\s*(?:пильн|отрезн)|лентопильн"), ("press", r"пресс"), ("furnace", r"электропечь|печь"),
    ("induction", r"высокочастотн|твч"), ("injection", r"литьев"), ("thread_manip", r"резьбонарезн"),
    ("tester", r"разрывн|испытательн"), ("lapping", r"притирочн|хонинговальн"), ("plating", r"гальваническ"),
    ("mill_v", r"фрезерн"),
]


def classify(type_text: str, model: str = "") -> str:
    """Вид оборудования по названию типа (и модели, если тип пустой)."""
    t = f"{type_text or ''} {model or ''}".lower().replace("ё", "е")
    for kind, rx in _KIND_RX:
        if re.search(rx, t.replace("ё", "е")):
            return kind
    return "other"


# --------------------------------------------------------------- параметры по обозначению модели
# Таблица «мощность лазера → практический предел качественной резки, мм»: (кВт, сталь, нержавейка, алюминий).
# ОРИЕНТИР по данным производителей волоконных лазеров, не паспорт: уточнить у технолога.
LASER_THICKNESS = [(1.0, 6, 3, 3), (1.5, 8, 4, 3), (2.0, 10, 5, 4), (3.0, 16, 8, 6), (6.0, 20, 16, 12),
                   (10.0, 30, 25, 20), (12.0, 40, 30, 25), (20.0, 40, 30, 25), (30.0, 50, 40, 40)]


def laser_thickness(kw: float) -> tuple[float, float, float] | None:
    best = None
    for row in LASER_THICKNESS:
        if kw + 1e-9 >= row[0]:
            best = row
    return (best[1], best[2], best[3]) if best else None


# Размеры, сообщённые заказчиком (не паспорт, но точнее, чем вывод по обозначению модели): модель → параметры.
KNOWN_MODELS: dict[str, dict[str, float]] = {
    "LM3512HGP": {"bed_l": 12000, "bed_w": 3000},      # лазер 20 кВт: рабочая поверхность 3×12 м (сообщено 19.10.2026)
}


def _norm(model: str) -> str:
    return re.sub(r"\s+", "", (model or "").upper().replace("-", ""))


def decode_model(kind: str, model: str, type_text: str = "") -> tuple[dict, dict]:
    """(параметры, источники) по обозначению модели и названию типа. Только то, что выводится надёжно по системе
    обозначений станков (ЕНИМС) и устойчивым записям моделей; остальное остаётся пустым — для паспорта."""
    m, raw = _norm(model), (model or "").upper()
    p: dict[str, float] = {}
    src: dict[str, str] = {}

    def put(key: str, val: float, how: str = "model"):
        p[key] = val
        src[key] = how

    if kind in ("lathe",):
        r = re.match(r"^16[А-Я]*(\d{2})$", m)                  # 16К20, 16К25: две цифры — высота центров /10
        if r:
            put("swing", 2 * int(r.group(1)) * 10)
        else:
            r = re.match(r"^1[А-Я]?6([2-5])(?!\d)", m)         # 1К62, 1М63Н, 1М65: размер 2–5 → высота центров 200–500
            if r:
                put("swing", 2 * {2: 200, 3: 315, 4: 400, 5: 500}[int(r.group(1))])
    elif kind in ("drill", "drill_radial"):
        r = re.match(r"^2[А-Я]?-?(\d)(\d{2})(?!\d)", raw.replace(" ", ""))   # 2Н135, 2А125, 2С125-04, 2М112: две цифры — Ø сверления
        if r and r.group(1) == "1":
            put("drill_d", int(r.group(2)))
        elif m.startswith("2М55"):
            put("drill_d", 50)
    elif kind in ("mill_v", "mill_h"):
        r = re.match(r"^6[МРТ]1([23])", m) or re.match(r"^6[МРТ]8([23])", m)
        if r:
            put("table_w", {"2": 320, "3": 400}[r.group(1)])
            put("table_l", {"2": 1250, "3": 1600}[r.group(1)])
        elif m.startswith("ВМ127"):
            put("table_w", 400)
            put("table_l", 1600)
    elif kind in ("gear_hob",):
        if re.match(r"^5[КЕ]32", m):
            put("gear_d", 320)
        elif m.startswith("53А50"):
            put("gear_d", 500)
    elif kind == "grind_flat" and m.startswith("3Г71"):
        put("table_l", 630)
        put("table_w", 200)
    elif kind == "boring_h":
        if m.startswith("2620"):
            put("spindle_d", 90)
        elif m.startswith("2А614"):
            put("spindle_d", 110)
    elif kind == "laser_sheet":
        r = re.search(r"(\d+(?:[.,]\d+)?)\s*к[WwВв]", type_text or "", flags=re.I)
        if r:
            kw = float(r.group(1).replace(",", "."))
            put("laser_kw", kw, "type")
            th = laser_thickness(kw)
            if th:
                put("t_steel", th[0], "estimate")
                put("t_stainless", th[1], "estimate")
                put("t_alu", th[2], "estimate")
        r = re.search(r"(?<!\d)(\d{2})(\d{2})(?!\d)", raw)     # LM3512, SF6015, USI-3015: длина и ширина поля в сотнях мм
        if r:
            put("bed_l", int(r.group(1)) * 100)
            put("bed_w", int(r.group(2)) * 100)
        for key, val in KNOWN_MODELS.get(re.sub(r"\s+", "", raw), {}).items():
            put(key, val, "manual")
    elif kind == "laser_tube":
        r = re.search(r"(?<!\d)(\d{2})(\d{2})(?!\d)", raw)     # SF6035T: длина 6000, диаметр до 350
        if r:
            put("tube_l", int(r.group(1)) * 100)
            put("tube_d", int(r.group(2)) * 10)
    elif kind == "rolls":
        r = re.search(r"(\d{4})\s*[*×X]\s*(\d{1,2})", raw)     # ST2500*20: ширина 2500, толщина 20
        if r:
            put("roll_w", int(r.group(1)))
            put("roll_t", int(r.group(2)))
    return p, src


def make_item(num, workshop, typ: str, model: str, year=None) -> dict:
    kind = classify(typ, model)
    params, src = decode_model(kind, model, typ)
    return {"id": num, "workshop": "" if workshop is None else str(workshop), "type": typ, "model": model, "year": year,
            "kind": kind, "qty": 1, "active": True, "params": params, "src": src}


def default_items() -> list[dict]:
    return [make_item(*row) for row in ERP_EQUIPMENT]


def items(cfg: dict | None) -> list[dict]:
    """Действующий профиль: из config.json, а если там пусто — перечень из ERP."""
    raw = ((cfg or {}).get("equipment") or {}).get("items")
    if isinstance(raw, list) and raw:
        return raw
    return default_items()


def is_custom(cfg: dict | None) -> bool:
    raw = ((cfg or {}).get("equipment") or {}).get("items")
    return isinstance(raw, list) and bool(raw)


def clean_items(raw) -> list[dict]:
    """Проверка и приведение списка от интерфейса. Неизвестный вид определяется по названию типа."""
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        typ = str(r.get("type") or "").strip()
        model = str(r.get("model") or "").strip()
        if not typ and not model:
            continue
        kind = r.get("kind") if r.get("kind") in KINDS else classify(typ, model)
        params, src = {}, {}
        for k, v in (r.get("params") or {}).items():
            if k not in PARAMS or v in (None, ""):
                continue
            try:
                params[k] = float(str(v).replace(",", "."))
            except ValueError:
                continue
            if params[k] == int(params[k]):
                params[k] = int(params[k])
            s = (r.get("src") or {}).get(k)
            src[k] = s if s in ("model", "type", "estimate", "passport", "manual") else "manual"
        if not params:                           # параметры не заданы — заполняем по обозначению модели и типу
            params, src = decode_model(kind, model, typ)
        try:
            qty = max(1, int(r.get("qty") or 1))
        except (TypeError, ValueError):
            qty = 1
        year = r.get("year")
        try:
            year = int(year) if year not in (None, "") else None
        except (TypeError, ValueError):
            year = None
        out.append({"id": r.get("id"), "workshop": str(r.get("workshop") or "").strip(), "type": typ, "model": model,
                    "year": year, "kind": kind, "qty": qty, "active": bool(r.get("active", True)),
                    "params": params, "src": src})
    return out


class Profile:
    """Запросы к профилю для правил: наличие вида оборудования, наибольшее значение параметра, неизвестные значения."""

    def __init__(self, cfg: dict | None):
        self.items = [i for i in items(cfg) if i.get("active", True)]

    def of(self, *kinds: str) -> list[dict]:
        return [i for i in self.items if i.get("kind") in kinds]

    def has(self, *kinds: str) -> bool:
        return bool(self.of(*kinds))

    def best(self, kinds, key: str):
        """(наибольшее значение, станок с ним, есть ли станки этого вида без значения параметра)."""
        top, who, unknown = None, None, False
        for i in self.of(*kinds):
            v = (i.get("params") or {}).get(key)
            if v is None:
                unknown = True
            elif top is None or v > top:
                top, who = v, i
        return top, who, unknown


def label(i: dict) -> str:
    return f"{i.get('model') or i.get('type')}"


def api_view(cfg: dict) -> dict:
    return {"items": copy.deepcopy(items(cfg)), "custom": is_custom(cfg), "kinds": KINDS,
            "params": {k: {"label": v[0], "unit": v[1]} for k, v in PARAMS.items()}, "kind_params": KIND_PARAMS,
            "laser_thickness": [{"kw": r[0], "steel": r[1], "stainless": r[2], "alu": r[3]} for r in LASER_THICKNESS]}
