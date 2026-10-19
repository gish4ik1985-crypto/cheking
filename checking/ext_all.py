"""Сборка пакетных правил: импорт модулей наполняет реестр pack.REG, check_ext запускает все проверки."""
from __future__ import annotations

from . import ext_coat, ext_elements, ext_equip, ext_mfg, ext_misc, ext_series, ext_spec, ext_threads, ext_title, ext_tol, ext_ttlang, ext_weld
from .model import Drawing
from .pack import REG, run_all  # noqa: F401  (REG используют каталог и справка)

CHECKS = (ext_threads.check_threads_ext, ext_elements.check_elements_ext,
          ext_series.check_series_ext, ext_tol.check_tol_ext,
          ext_weld.check_weld_ext, ext_title.check_title_pack, ext_misc.check_misc_ext, ext_coat.check_coat_ext,
          ext_mfg.check_mfg_ext, ext_ttlang.check_ttlang_ext)


def check_ext(drw: Drawing, cfg: dict) -> None:
    run_all(drw, CHECKS)

    def check_equipment_profile(d: Drawing) -> None:          # профиль оборудования зависит от настроек (cfg)
        ext_equip.check_equip_ext(d, cfg)
    run_all(drw, [check_equipment_profile])
