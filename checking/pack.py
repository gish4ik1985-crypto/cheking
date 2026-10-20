"""Каркас «пакетных» правил: описание правила (для каталога, справки и панели) пишется рядом с проверкой одним
вызовом R(...), а замечание выдаётся через emit(drw, "КОД", текст, …) — серьёзность, категория и стандарт берутся
из описания. Коды пакетных правил — буква и три цифры (C101, I201, U301…); их собирает каталог.

Модуль не импортирует каталог и другие проверки, чтобы не создавать циклов."""
from __future__ import annotations

from .model import (Drawing, ERROR, WARNING, INFO, CAT_DIM, CAT_GDT, CAT_HEAT, CAT_GEAR, CAT_WELD, CAT_EL, CAT_TB,
                    CAT_TT, CAT_VIEW, CAT_REFS, CAT_FILE, CAT_SPEC, CAT_TECH)

REG: dict[str, dict] = {}

GROUP_CAT = {"fits": CAT_DIM, "dims": CAT_DIM, "gentol": CAT_DIM, "series": CAT_DIM, "threads": CAT_DIM,
             "gdt": CAT_GDT, "rough": CAT_DIM, "heat": CAT_HEAT, "gears": CAT_GEAR, "elements": CAT_EL,
             "welds": CAT_WELD, "title": CAT_TB, "tt": CAT_TT, "views": CAT_VIEW, "refs": CAT_REFS,
             "forge": CAT_TT, "cast": CAT_TT, "tapholes": CAT_DIM, "spec": CAT_SPEC, "capab": CAT_TECH,
             "classifier": CAT_TB}
SEV = {"error": ERROR, "warning": WARNING, "info": INFO}
SKIP_DEFAULT = "Если на чертеже нет нужных данных (размера, обозначения, строки ТТ), правило молчит."


def R(code: str, group: str, title: str, std: str, what: str, how: str, example: str, skip: str = "",
      default: bool = True, sev: str = "warning") -> None:
    """Описание правила: код, группа каталога, краткое название, стандарт (с пунктом), что проверяет, как находит,
    пример замечания, когда пропускает, включено ли по умолчанию, серьёзность."""
    assert code not in REG, f"повтор кода {code}"
    assert sev in SEV and group in GROUP_CAT, code
    REG[code] = {"code": code, "group": group, "title": title, "std": std, "what": what, "how": how,
                 "example": example, "skip": skip or SKIP_DEFAULT, "default": default, "sev": sev}


def emit(drw: Drawing, code: str, msg: str, page=None, bbox=None, std: str | None = None) -> None:
    r = REG[code]
    drw.add(SEV[r["sev"]], code, GROUP_CAT[r["group"]], msg, page, bbox, std or r["std"])


def once(drw: Drawing, seen: set, code: str, key, msg: str, page=None, bbox=None) -> bool:
    """Выдаёт замечание один раз на (код, ключ) — чтобы одна и та же запись не засоряла отчёт."""
    k = (code, key)
    if k in seen:
        return False
    seen.add(k)
    emit(drw, code, msg, page, bbox)
    return True


def run_all(drw: Drawing, fns) -> None:
    for fn in fns:
        try:
            fn(drw)
        except Exception as e:               # одна неудачная проверка не должна ронять остальные
            drw.add(WARNING, "F07", CAT_FILE, f"Проверка «{fn.__name__}» не выполнена: {type(e).__name__}: {e}")
