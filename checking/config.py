"""Настройки проверки. Переопределяются файлом config.json в корне программы."""
from __future__ import annotations

import copy
import json
import os

import sys

FROZEN = bool(getattr(sys, "frozen", False))
# ROOT — где лежат данные пользователя (config.json, admin.json, work); у exe — папка с exe.
# RES — ресурсы программы (web), у exe — внутри пакета.
ROOT = os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = getattr(sys, "_MEIPASS", ROOT) if FROZEN else ROOT
CONFIG_PATH = os.path.join(ROOT, "config.json")

DEFAULTS = {
    # коды организаций-разработчиков в обозначениях (ГОСТ 2.201)
    "org_codes": ["ДТМЛ", "ЮМЛТ"],
    # ссылки в ТТ, которые закрывают «неуказанные предельные отклонения»
    "general_tolerance_refs": ["ГОСТ 30893", "ГОСТ 25670", "H14", "h14", "IT14", "IT 14", "ГОСТ 23118",
                               "Неуказанные предельные отклонения", "ОСТ4 ГО.070.014",
                               "13920", "Общие допуски по"],
    "mass": {
        "rel_tol": 0.03,           # допустимое отличие массы от спецификации/ERP, доля
        "abs_tol": 0.005,          # кг — плюс погрешность округления в штампе
        "min_fill": 0.12,          # масса < 12% от массы габаритного параллелепипеда — подозрительно
    },
    "laser": {
        "hole_min_ratio": 1.0,     # отверстие ⌀ меньше k·s на листовой детали — предупреждение
        "it_limit": 11,            # допуск точнее IT11 на листовой детали — нужна мехобработка
    },
    "tight_it": 5,                 # допуск точнее этого квалитета — «очень жёсткий»
    "coarse_it": 17,               # грубее — подозрительно
    "thread_min_turns": 3,         # минимум витков резьбы в листе толщиной s
    "hardness_min_range_hrc": 4,   # диапазон твёрдости HRC уже — замечание по технологичности
    # включение/важность правил: {"D11": {"enabled": false}, "D03": {"severity": "warning"}} — см. /admin
    "rules": {},
    # замены редакций стандартов [{"old": "ГОСТ 13755-81", "new": "ГОСТ 13755-2015"}]; пусто — встроенный список
    "obsolete_standards": [],
    "ocr": True,
    "erp_db": {
        "enabled": False,
        "host": "s.yarst.ru", "port": 5432, "dbname": "erp_yarst", "user": "", "password": "",
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | None = None) -> dict:
    path = path or CONFIG_PATH
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return _merge(DEFAULTS, json.load(f))
    return copy.deepcopy(DEFAULTS)


LEGACY_KEYS = ("check_ra40", "check_fillet_series", "check_roughness_vs_it", "check_title_people")


def save_config(updates: dict, path: str | None = None) -> dict:
    """Записывает изменения в config.json (остальные ключи файла сохраняются). Старые переключатели
    проверок удаляются — их заменил раздел "rules"."""
    path = path or CONFIG_PATH
    current = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            current = json.load(f)
    for k, v in updates.items():
        if isinstance(v, dict) and isinstance(current.get(k), dict) and k != "rules":
            current[k] = _merge(current[k], v)
        else:
            current[k] = v
    if "rules" in updates:
        for k in LEGACY_KEYS:
            current.pop(k, None)
        if isinstance(current.get("laser"), dict):
            current["laser"].pop("enabled", None)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return load_config(path)


def write_default_config(path: str | None = None) -> str:
    path = path or CONFIG_PATH
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)
    return path
