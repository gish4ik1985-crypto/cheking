"""Тесты: таблицы допусков, разбор размеров, правила на тестовых и реальных чертежах.

Запуск:  .venv\\Scripts\\python -m pytest -q
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from checking import tolerances as T  # noqa: E402
from checking.dimparse import parse_dimension  # noqa: E402
from checking.engine import check_file  # noqa: E402
from checking.material import parse_material  # noqa: E402
from checking.spec import Spec  # noqa: E402
from checking.standards import check_metric_thread  # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")


# --- ГОСТ 25346 / ISO 286: контрольные значения из таблиц ISO 286-2 ----------
@pytest.mark.parametrize("size,code,up,lo", [
    (20, "H7", 0.021, 0), (20, "g6", -0.007, -0.020), (20, "f7", -0.020, -0.041), (50, "k6", 0.018, 0.002),
    (40, "p6", 0.042, 0.026), (25, "r6", 0.041, 0.028), (100, "s6", 0.093, 0.071), (30, "K7", 0.006, -0.015),
    (30, "N7", -0.007, -0.028), (30, "P7", -0.014, -0.035), (30, "M7", 0, -0.021), (60, "e8", -0.060, -0.106),
    (80, "d9", -0.100, -0.174), (10, "js6", 0.0045, -0.0045), (50, "F8", 0.064, 0.025), (40, "G7", 0.034, 0.009),
    (100, "S7", -0.058, -0.093), (160, "d11", -0.145, -0.395), (200, "t6", 0.195, 0.166), (20, "K6", 0.002, -0.011),
    (20, "N9", 0, -0.052), (20, "M8", 0.004, -0.029), (20, "J7", 0.012, -0.009), (2, "N7", -0.004, -0.014),
    (35, "u6", 0.076, 0.060), (15, "x7", 0.063, 0.045), (120, "H7", 0.035, 0), (1000, "h9", 0, -0.230),
])
def test_limits(size, code, up, lo):
    got = T.limits(size, code)
    assert got == pytest.approx((up, lo), abs=1e-6)


def test_fit_kinds():
    assert T.fit_info(20, "H7", "g6").kind == "с зазором"
    assert T.fit_info(25, "H7", "k6").kind == "переходная"
    assert T.fit_info(40, "H7", "s6").kind == "с натягом"


@pytest.mark.parametrize("code", ["Js7", "H19", "Q7", "h0"])
def test_bad_fields(code):
    with pytest.raises(T.ToleranceError):
        T.limits(30, code)


def test_field_not_defined_for_size():
    with pytest.raises(T.ToleranceError):
        T.limits(12, "t6")          # t начинается с 24 мм


# --- резьба --------------------------------------------------------------------
def test_threads():
    assert check_metric_thread(18, None)[0]
    assert check_metric_thread(20, 1.5)[0]
    assert not check_metric_thread(13, None)[0]
    assert not check_metric_thread(20, 1.25)[0]
    assert not check_metric_thread(40, None)[0]      # М40 — только мелкий шаг


# --- разбор текста размеров ------------------------------------------------------
@pytest.mark.parametrize("text,kind,nom,extra", [
    ("⌀20H7", "diameter", 20, {"field": "H7"}),
    ("⌀40H7/g6", "diameter", 40, {"fit_hole": "H7", "fit_shaft": "g6"}),
    ("110±1", "linear", 110, {"upper": 1, "lower": -1, "symmetric": True}),
    ("⌀20H7(+0,021)", "diameter", 20, {"field": "H7", "upper": 0.021, "lower": 0}),
    ("M18×1,5-6g", "thread", 18, {"pitch": 1.5, "thread_tol": "6g"}),
    ("2×45°", "chamfer", 2, {"angle": 45}),
    ("4 отв. ⌀10", "diameter", 10, {"count": 4}),
    ("16*", "linear", 16, {"reference": "*"}),
    ("R3**", "radius", 3, {"reference": "**"}),
    ("s3*", "thickness", 3, {"reference": "*"}),
    ("⌀45 Н7", "diameter", 45, {"field": "H7", "cyrillic_in_field": True}),
])
def test_parse_dimension(text, kind, nom, extra):
    d = parse_dimension(text)
    assert d and d["kind"] == kind and d["nominal"] == pytest.approx(nom)
    for k, v in extra.items():
        assert d.get(k) == (pytest.approx(v) if isinstance(v, float) else v), k


@pytest.mark.parametrize("text", ["1:2", "19.08.24", "3-2025", "301321.001", "01.2025", "Ст3сп", "А-А", "Ra 6,3"])
def test_not_dimension(text):
    assert parse_dimension(text) is None


def test_material():
    m = parse_material("Лист Б-ПН-О-16х1500х6000 ГОСТ 19903-2015 / Ст3сп-5-ГС ГОСТ 14637-2024")
    assert (m["sortament"], m["size"], m["grade"]) == ("Лист", 16, "Ст3сп")
    m = parse_material("Профиль 200х120х6 ГОСТ 30245-2003 / 345-14-09Г2С ГОСТ 19281-2014")
    assert m["grade"] == "09Г2С"
    m = parse_material("Круг В1-IV-НД-100 ГОСТ 2590-2006/20-2ГП-М1-ТВ1 ГОСТ 1050-2013")
    assert (m["size"], m["grade"]) == (100, "20")


# --- тестовые чертежи с заложенными ошибками ------------------------------------
@pytest.fixture(scope="module")
def generated():
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "make_samples.py")], check=True,
                   capture_output=True)
    return os.path.join(SAMPLES, "test")


def _codes(path, spec=None):
    ds = check_file(path, spec=spec)
    assert len(ds) == 1
    return ds[0], {f.code for f in ds[0].findings}


def test_errors_drawing(generated):
    d, codes = _codes(os.path.join(generated, "ДТМЛ.741111.900 - Планка тестовая.pdf"))
    for c in ("D01", "D03", "D04", "D05", "D06", "D08", "D11", "D13", "D14", "D15", "D29", "T01", "T02", "T03",
              "D10", "B03"):
        assert c in codes, c
    msgs = " ".join(f.message for f in d.findings)
    assert "+0,021 / 0" in msgs                          # правильные отклонения для ⌀20H7
    assert "H7/g6" in msgs                               # подсказка для перевёрнутой посадки


def test_clean_drawing(generated):
    d, codes = _codes(os.path.join(generated, "ДТМЛ.715123.901 - Вал.pdf"))
    errors = [f for f in d.findings if f.severity == "error"]
    assert not errors, [f.message for f in errors]
    assert "D10" not in codes                            # общие допуски указаны в ТТ


# --- реальные чертежи КОМПАС + спецификация ---------------------------------------
REAL = os.path.join(SAMPLES, "drawings")


@pytest.mark.skipif(not os.path.isdir(REAL), reason="нет образцов")
def test_real_mass_error_found():
    spec = Spec(os.path.join(SAMPLES, "СП Опора пассивная.xls"))
    d, codes = _codes(os.path.join(REAL, "ДТМЛ.741224.002 - Фиксатор изм.2.pdf"), spec)
    assert "B02" in codes                                # 0,05 кг в штампе против 0,118 кг в СП


@pytest.mark.skipif(not os.path.isdir(REAL), reason="нет образцов")
def test_real_clean_drawings_have_no_errors():
    spec = Spec(os.path.join(SAMPLES, "СП Опора пассивная.xls"))
    for name in ("ДТМЛ.741214.001 - Пластина изм.1.pdf", "ДТМЛ.741228.001 - Основание.pdf",
                 "ДТМЛ.711111.001 - Кольцо.pdf", "ДТМЛ.715111.001 - Шпилька.pdf"):
        d, _ = _codes(os.path.join(REAL, name), spec)
        errors = [f.message for f in d.findings if f.severity == "error"]
        assert not errors, (name, errors)
        assert d.title.designation.startswith("ДТМЛ.")


@pytest.mark.skipif(not os.path.isdir(REAL), reason="нет образцов")
def test_real_dimension_between_extension_lines():
    # «25» и «20*» между выносными линиями под контуром — размеры, а не ячейки таблицы;
    # знак × в «5×45°» без ToUnicode в шрифте GOSTTypeA
    d, codes = _codes(os.path.join(REAL, "ДТМЛ.741124.068 - Пластина.pdf"))
    raws = {x.raw: x for x in d.dims}
    assert "25" in raws and raws["20*"].reference == "*" and raws["5×45°"].kind == "chamfer"
    assert "D09" not in codes


# --- реальные чертежи Solid Edge (редуктор), найденные ошибки подтверждены по изображению ----
RED = os.path.join(SAMPLES, "reductor")


def _find(d, code, text):
    return [f for f in d.findings if f.code == code and text in f.message]


@pytest.mark.skipif(not os.path.isdir(RED), reason="нет образцов редуктора")
def test_reductor_real_findings():
    d, _ = _codes(os.path.join(RED, "201-000571 Палец сателлита диам 30 мм версия 2.pdf"))
    assert d.title.designation == "201-000571"
    assert _find(d, "D04", "«30 -0,2 / -0,1»") and _find(d, "D04", "⌀28,5")       # отклонения перепутаны
    assert _find(d, "D14", "h6")                                                   # h6 при общей Ra 6,3
    d, _ = _codes(os.path.join(RED, "280-000091 Водило 2 ступени версия 4.pdf"))
    assert _find(d, "D04", "⌀168")                                                 # −0,05 / −0,05
    assert _find(d, "D03", "74H8")                                                 # +0,05 вместо +0,046
    d, _ = _codes(os.path.join(RED, "280-000092 Водило 3 ступени версия 4.pdf"))
    assert _find(d, "D04", "⌀100 +1 / +1,5")


@pytest.mark.skipif(not os.path.isdir(RED), reason="нет образцов редуктора")
def test_reductor_layout():
    # страница с /Rotate 90 и основная надпись «Си Джи Эм» с графами Рев./Вер.
    d, codes = _codes(os.path.join(RED, "204-000255 Сателлит водила  2 ступени.pdf"))
    assert d.title.designation == "204-000255" and d.title.mass == 2.31
    # ТТ под таблицей спецификации на сборочном чертеже
    d, codes = _codes(os.path.join(RED, "120-001422 Сателлит 3 ступени в сборе с иголч подш.pdf"))
    assert "D10" not in codes
    # числа из таблицы параметров зубчатого венца — не размеры
    d, _ = _codes(os.path.join(RED, "280-000059 Зубчатый венец m3 z75.pdf"))
    assert not [x for x in d.dims if x.raw in ("5.176", "8.69")]


# --- DXF -----------------------------------------------------------------------
def test_dxf_compare(generated):
    from checking.dxf import DxfIndex
    idx = DxfIndex([os.path.join(generated, "ДТМЛ.741111.900 - Планка тестовая_12мм.dxf"),
                    os.path.join(generated, "ДТМЛ.741214.001 Пластина_16мм.dxf")])
    ds = check_file(os.path.join(generated, "ДТМЛ.741111.900 - Планка тестовая.pdf"), dxf_index=idx)
    msgs = [f.message for f in ds[0].findings if f.code.startswith("X")]
    assert any("4 отв., в DXF 3" in m for m in msgs)
    assert any("⌀12,5 — 2 шт." in m for m in msgs)
    ds = check_file(os.path.join(REAL, "ДТМЛ.741214.001 - Пластина изм.1.pdf"), dxf_index=idx)
    assert [f.code for f in ds[0].findings if f.code.startswith("X")] == ["X00"]


# --- HTTP API для ERP -------------------------------------------------------------
@pytest.mark.skipif(not os.path.isdir(REAL), reason="нет образцов")
def test_api_check_with_erp_card():
    import app as webapp
    client = webapp.app.test_client()
    assert client.get("/api/v1/health").json["status"] == "ok"
    with open(os.path.join(REAL, "ДТМЛ.741224.002 - Фиксатор изм.2.pdf"), "rb") as f:
        r = client.post("/api/v1/check", data={
            "file": (f, "ДТМЛ.741224.002 - Фиксатор изм.2.pdf"), "designation": "ДТМЛ.741224.002",
            "mass": "0.1178", "material": "Лист 5 ГОСТ 19903-2015 / Ст3сп ГОСТ 14637-89", "ocr": "0"},
            content_type="multipart/form-data")
    assert r.status_code == 200 and r.json["success"]
    d = r.json["drawings"][0]
    assert any(f["code"] == "B02" and "карточке ERP" in f["message"] for f in d["findings"])


# --- комплектность, сварка, исключения, перечень замечаний ---------------------
@pytest.mark.skipif(not os.path.isdir(REAL), reason="нет образцов")
def test_completeness():
    from checking.completeness import completeness
    from checking.engine import collect_files
    spec = Spec(os.path.join(SAMPLES, "СП Опора пассивная.xls"))
    ds = [d for f in collect_files([REAL]) for d in check_file(f, spec=spec)]
    c = completeness(spec, ds)
    missing = {r["designation"] for r in c["rows"] if r["status"] == "missing"}
    assert "ДТМЛ.715123.001" in missing and "ДТМЛ.741214.001" not in missing   # Вал — нет, Пластина — есть
    assert any(r["designation"] == "ДТМЛ.741224.002" and r["status"] == "errors" for r in c["rows"])


def test_weld_parse():
    from checking.welds import _parse
    w = _parse("ГОСТ 14771-76-Т3-ИП-⊿5")
    assert (w["std"], w["type"], w["num"], w["leg"]) == ("14771", "Т", 3, 5.0)
    assert _parse("У5-⊿")["leg"] is None
    assert _parse("С17") is None


def test_exceptions_roundtrip(tmp_path):
    from checking import exceptions as ex
    p = str(tmp_path / "ex.json")
    d = {"file": "a.pdf", "title": {"designation": "ДТМЛ.1"},
         "findings": [{"code": "D10", "message": "m1", "severity": "warning"},
                      {"code": "B01", "message": "m2", "severity": "warning"}]}
    r = ex.add_rule({"scope": "drawing", "code": "D10", "message": "m1", "designation": "ДТМЛ.1"}, p)
    out = ex.apply_to_dict(d, ex.load_rules(p))
    assert [f["code"] for f in out["findings"]] == ["B01"] and out["counts"]["warning"] == 1
    ex.add_rule({"scope": "global", "code": "B01"}, p)
    assert ex.apply_to_dict(d, ex.load_rules(p))["findings"] == []
    assert ex.delete_rule(r["id"], p)


def test_remarks_docx(tmp_path, generated):
    from docx import Document
    from checking.remarks import build_docx
    from checking.report import drawing_to_dict
    ds = check_file(os.path.join(generated, "ДТМЛ.741111.900 - Планка тестовая.pdf"))
    path = build_docx([drawing_to_dict(d) for d in ds], str(tmp_path / "r.docx"))
    rows = Document(path).tables[0].rows
    assert len(rows) > 10 and "ДТМЛ.741111.900" in rows[1].cells[1].text


# --- проверки по остальным ГОСТам на реальных чертежах (находки подтверждены по изображениям) -----
def _red(name):
    return check_file(os.path.join(RED, name))[0]


@pytest.mark.skipif(not os.path.isdir(RED), reason="нет образцов редуктора")
def test_gost_findings_reductor():
    d = _red("201-000571 Палец сателлита диам 30 мм версия 2.pdf")
    assert _find(d, "K01", "С4")                                     # форма C — только d 8, 12, 20…
    assert _find(d, "P04", "IT14/2")                                 # без «±»
    d = _red("280-000060 Зубчатый венец редуктора Прево 2 ступени.pdf")
    assert _find(d, "G01", "«Г»")                                    # база Г = разрез Г-Г, база — Д
    assert _find(d, "G04", "«Д»")
    assert _find(d, "N01", "13755-81") and _find(d, "Z04", "8C")
    assert not [f for f in d.findings if f.code == "H02"]            # «слоя 0.4...0.5 HRC 52...58» — не твёрдость
    d = _red("204-000255 Сателлит водила  2 ступени.pdf")
    assert _find(d, "M01", "Круг") and _find(d, "Z05", "ГОСТ 1643")
    assert not [f for f in d.findings if f.code == "N02"]            # номер стандарта перенесён на строку ниже
    d = _red("280-000091 Водило 2 ступени версия 4.pdf")
    assert _find(d, "K04", "6033-88")
    d = _red("280-000092 Водило 3 ступени версия 4.pdf")
    assert _find(d, "K04", "6333-80") and not [f for f in d.findings if f.code == "Z02"]   # таблица шлицев
    d = _red("280-000059 Зубчатый венец m3 z75.pdf")
    assert d.facts["gear"][0]["m"] == "3" and not [f for f in d.findings if f.code in ("Z03", "G01")]


@pytest.mark.skipif(not os.path.isdir(REAL), reason="нет образцов")
def test_gost_findings_kompas():
    d, codes = _codes(os.path.join(REAL, "ДТМЛ.711111.001 - Кольцо.pdf"))
    assert _find(d, "H04", "Ц6.хр")
    d, codes = _codes(os.path.join(REAL, "ДТМЛ.741124.068 - Пластина.pdf"))
    t01 = [f for f in d.findings if f.code == "T01"]
    assert t01 and t01[0].severity == "info" and "М16" in t01[0].message   # ⌀17 — под крепёж ГОСТ 11284


def test_special_threads_parse():
    p = parse_dimension("Tr40×7-7H")
    assert (p["kind"], p["nominal"], p["pitch"]) == ("thread_tr", 40, 7)
    assert parse_dimension("Tr20x8(P4)")["pitch"] == 4
    assert parse_dimension("G1 1/2-A")["g_size"] == "1 1/2"
    p = parse_dimension("М6-7Н")
    assert p["thread_tol"] == "7H" and p["cyrillic_in_field"]


def _synthetic(tt=(), lines=(), material=""):
    from checking.model import Drawing, PageInfo, TextLine
    d = Drawing("x.pdf", "x.pdf", kind="pdf")
    d.pages = [PageInfo(0, 420, 297)]
    y = 40
    for t in lines:
        d.lines.append(TextLine(t, 0, (60, y, 60 + 3 * len(t), y + 5), (1, 0), 5, (60, y + 5)))
        y += 12
    d.tt = list(tt)
    d.title.material = material
    from checking.material import parse_material as pm
    d.facts["material"] = pm(material)
    return d


def test_text_rules_synthetic():
    from checking.config import load_config
    from checking.textreq import check_tt_text, check_heat, check_refs
    from checking.matcheck import check_material
    from checking.elements import check_elements
    cfg = load_config()
    d = _synthetic(tt=["1. Деталь закалить. HRC 45", "3. Цементировать, HRC 58...62", "4. Общие допуски по ГОСТ 30893.1-x"],
                   lines=["Отв. центр. B3,15 ГОСТ 14034-74", "d-8×36×40H7/f7×6"])
    for fn in (check_tt_text, check_heat, check_refs, check_elements):
        fn(d, cfg)
    codes = {f.code for f in d.findings}
    assert {"P01", "H01", "H06", "P05", "K03"} <= codes and "K01" not in codes
    d = _synthetic(material="Круг 40 ГОСТ 19903-74 / 40Х ГОСТ 1050-88")
    check_material(d, cfg)
    check_refs(d, cfg)
    codes = [f.code for f in d.findings]
    assert "M03" in codes and "M02" in codes and codes.count("N01") == 2


def test_catalog_profile():
    from checking import catalog
    cfg = {"rules": {"D11": {"enabled": False}, "D03": {"severity": "warning"}}, "check_title_people": True}
    assert catalog.rule_settings(cfg, "D11") == (False, None)
    assert catalog.rule_settings(cfg, "D03") == (True, "warning")
    assert catalog.rule_settings(cfg, "B09")[0] is True             # старый ключ config.json
    assert catalog.rule_settings({}, "D23")[0] is False              # по умолчанию выключено
    assert catalog.rule_settings({"rules": {"F00": {"enabled": False}}}, "F00")[0] is True   # служебное
    d = {"findings": [{"code": "D11", "severity": "info", "message": "a", "category": "x"},
                      {"code": "D03", "severity": "error", "message": "b", "category": "x"}], "suppressed": []}
    out = catalog.apply_to_dict(d, cfg)
    assert [f["code"] for f in out["findings"]] == ["D03"] and out["counts"]["warning"] == 1
    assert {r[0] for r in catalog.RULES} >= {"G01", "V03", "N01", "H04", "M02", "Z03", "K01", "D24"}


def test_admin_api(tmp_path, monkeypatch):
    import app as webapp
    from checking import admin, config
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(admin, "PATH", str(tmp_path / "admin.json"))
    c = webapp.app.test_client()
    st = c.get("/api/admin/state").json
    assert st["auth"]["password_set"] is False and any(g["key"] == "gdt" for g in st["groups"])
    r = c.post("/api/admin/settings", json={"rules": {"D11": {"enabled": False}, "D23": {"enabled": True},
                                                      "D03": {"enabled": True, "severity": "warning"}},
                                            "params": {"tight_it": 4}})
    assert r.status_code == 200
    saved = config.load_config()
    assert saved["rules"] == {"D11": {"enabled": False}, "D23": {"enabled": True}, "D03": {"severity": "warning"}}
    assert saved["tight_it"] == 4
    assert c.post("/api/admin/rule", json={"code": "D11", "enabled": True}).status_code == 200
    assert "D11" not in config.load_config()["rules"]
    assert c.post("/api/admin/password", json={"new": "secret1"}).json["password_set"]
    anon = webapp.app.test_client()
    assert anon.get("/api/admin/state").status_code == 401
    assert anon.post("/api/admin/rule", json={"code": "D11", "enabled": False}).status_code == 401
    assert anon.post("/api/admin/login", json={"password": "bad"}).status_code == 403
    assert anon.post("/api/admin/login", json={"password": "secret1"}).status_code == 200
    assert anon.get("/api/admin/state").status_code == 200


def test_every_rule_code_in_catalog():
    """Каждый код замечания, который выдаёт программа, есть в каталоге — его можно выключить в /admin."""
    import glob
    import re as _re
    from checking import catalog
    used = set()
    for f in glob.glob(os.path.join(ROOT, "checking", "*.py")):
        used |= set(_re.findall(r'add\(\s*(?:ERROR|WARNING|INFO|sev|[a-z_]+)\s*,\s*"([A-Z]\d{2})"', open(f, encoding="utf-8").read()))
    missing = sorted(used - set(catalog.RULE_INDEX))
    assert not missing, missing
    assert len(used) > 100


@pytest.mark.skipif(not os.path.isdir(os.path.join(SAMPLES, "assembly")), reason="нет сборочных чертежей")
def test_assembly_drawings():
    ASM = os.path.join(SAMPLES, "assembly")
    pack = check_file(os.path.join(ASM, "ОН-0020.000 СБ Полный пакет.pdf"))
    opora = pack[2]
    t = opora.facts["tables"][0]
    assert t["kind"] == "spec" and [i["pos"] for i in t["items"] if i["pos"]] == [1, 2, 3, 4, 5, 6]
    assert _find(opora, "A08", "Позиция 6")                          # у поз. 6 не указано количество
    assert not [f for f in opora.findings if f.code in ("A01", "A02")]   # позиции 1–6 на чертеже есть
    assert not [x for x in opora.tt if "Балка (1:4)" in x or "40х40х2" in x]   # таблица и надписи видов — не ТТ
    sb = pack[0]
    assert sorted({p["n"] for p in sb.facts["positions"]}) == [1, 2, 5, 8, 9, 10, 11, 14]
    assert not [f for f in sb.findings if f.code in ("A01", "A02", "A07")]   # резервные номера допустимы
    kol, = check_file(os.path.join(ASM, "Р 38.02 СБ Колонна.pdf"))
    assert not [f for f in kol.findings if f.code == "B01"]          # масса «см. табл.»
    assert kol.tt[0].startswith("1. Конструкция сварная. Конструктивные элементы")
    d = _red("120-001423 Водило 3 ступени в сборе с Иг пошш.pdf")
    assert sorted(p["n"] for p in d.facts["positions"]) == list(range(1, 10))
    assert _find(d, "A05", "нет размеров") and _find(d, "A11", "А4")
    d = _red("120-001427 Водило 2 ступени в сборе с Иг пошш.pdf")
    assert _find(d, "A01", ": 6")


@pytest.mark.skipif(not os.path.isdir(os.path.join(SAMPLES, "assembly")), reason="нет сборочных чертежей")
def test_assembly_mass_across_documents():
    from checking.engine import check_job
    pack = check_file(os.path.join(SAMPLES, "assembly", "ОН-0020.000 СБ Полный пакет.pdf"), apply_profile=False)
    sb, opora, platik = pack[0], pack[2], pack[3]
    check_job(pack, apply_profile=False)
    # реальная ошибка пакета: ОН-0020.011 — «Профиль … L = 650 мм» в Опоре и «Платик … 60х60 мм» в Платике в сборе
    assert _find(platik, "A17", "Одно обозначение присвоено разным изделиям")
    assert sb.facts["mass_parts"] == {"known": 162.64, "parts": 3, "unknown": 5}   # 7×10 + 12×2,38 + 24×2,67
    assert not [f for f in sb.findings if f.code in ("A13", "A15")]                # остальное — крепёж
    assert opora.facts["mass_parts"]["known"] == 7.77                              # «Метал наплавленный 1 | кг»

    pack = check_file(os.path.join(SAMPLES, "assembly", "ОН-0020.000 СБ Полный пакет.pdf"), apply_profile=False)
    sb, opora = pack[0], pack[2]
    sb.title.mass, sb.title.mass_raw = 100.0, "100"
    items = opora.facts["tables"][0]["items"]
    items[5]["qty"] = "1"                                   # поз. 6 с количеством — массы всех частей известны
    items[0]["note"] = "0,5 кг"                             # поз. 1 ОН-0020.010: в чертеже 0,09 кг
    opora.title.mass, opora.title.mass_raw = 14.0, "14"
    changed = check_job(pack, apply_profile=False)
    assert {0, 2} <= changed
    assert _find(sb, "A15", "меньше суммы масс составных частей — 190,64 кг")   # 7×14 + 28,56 + 64,08
    assert _find(opora, "A16", "масса в спецификации 0,5 кг, в чертеже ОН-0020.010 СБ — 0,09 кг")
    assert _find(opora, "A13", "сумма масс всех составных частей 10,01 кг")


@pytest.mark.skipif(not os.path.isdir(os.path.join(SAMPLES, "reductor")), reason="нет чертежей редуктора")
def test_mass_by_view_size():
    d = _red("120-001427 Водило 2 ступени в сборе с Иг пошш.pdf")
    assert _find(d, "B15", "122379,23 кг больше массы сплошного стального бруса")
    for name in ("120-001425 Водило 1 ступени в сборе с Иг пошш.pdf", "280-000036 Водило 1 ступени версия 2.pdf",
                 "280-000092 Водило 3 ступени версия 4.pdf"):
        d = _red(name)
        assert d.facts["mass_view"] and not [f for f in d.findings if f.code == "B15"], name
    for name in ("ДТМЛ.333333.001 СБ - Кронштейн изм.1.pdf",):
        d, = check_file(os.path.join(SAMPLES, "assembly", name))
        assert d.facts["mass_view"]["bound"] > 10 * d.title.mass          # запас ~13 раз


# --- спецификация по ГОСТ 2.106 -----------------------------------------------------------------------
def test_spec_document_kompas_report():
    from checking.specdoc import check_spec_document, children_for
    spec = Spec(os.path.join(SAMPLES, "СП Опора пассивная.xls"))
    d = check_spec_document(spec)
    assert d.kind == "spec" and d.title.designation == "ДТМЛ.301321.001"
    assert _find(d, "S02", "Гайка М18-6H.5.016 ГОСТ 5915-70 — 12 строк")      # повтор вместо общего количества
    assert _find(d, "S01", "Каток") and _find(d, "S03", "Детали")
    assert not [f for f in d.findings if f.code == "S12"]                    # массы сходятся (подшипники учтены)
    ch = children_for(spec, "ДТМЛ.301563.001 СБ")
    assert [c["name"] for c in ch] == ["Труба", "Пластина"]


@pytest.mark.skipif(not os.path.isdir(os.path.join(SAMPLES, "spec")), reason="нет выгрузок СП")
def test_spec_document_erp_and_solid():
    from checking.specdoc import check_spec_document
    d = check_spec_document(Spec(os.path.join(SAMPLES, "spec", "СП_Опора_пассивная_ERP.xlsx")))
    assert _find(d, "S01", "Опора пассивная") and _find(d, "S04", "Шпилька")
    assert not [f for f in d.findings if f.code == "S12"]   # детали с краской — не сборки; у сборок массы сходятся
    d = check_spec_document(Spec(os.path.join(SAMPLES, "spec", "СП_F001-13_Solid.xlsx")))
    s06 = [f for f in d.findings if f.code == "S06"]
    assert s06 and "артикул" in s06[0].message and len(s06) < 20       # одно замечание на сборку, а не на строку


def test_spec_rules_on_drawing_tables():
    d = _red("120-001423 Водило 3 ступени в сборе с Иг пошш.pdf")
    assert _find(d, "S04", "Шайба") and _find(d, "S06", "артикул")
    pack = check_file(os.path.join(SAMPLES, "assembly", "ОН-0020.000 СБ Полный пакет.pdf"))
    assert _find(pack[3], "A14", "ОН-0020.010 СБ")


# --- правила предприятия --------------------------------------------------------------------------------
def test_custom_rules_evaluate():
    from checking import custom
    from checking.report import drawing_to_dict
    d = drawing_to_dict(check_file(os.path.join(REAL, "ДТМЛ.741124.068 - Пластина.pdf"))[0])
    rules = [
        {"code": "U01", "title": "Марки", "kind": "allowed", "what": "grade", "values": ["09Г2С", "45"],
         "severity": "warning", "applies": "parts"},
        {"code": "U02", "title": "Кромки", "kind": "text_required", "where": "tt", "match": "contains",
         "pattern": "Острые кромки притупить", "severity": "info"},
        {"code": "U03", "title": "Организация", "kind": "field", "field": "organization", "check": "contains",
         "value": "Беретта", "severity": "warning"},
        {"code": "U04", "title": "Лист", "kind": "limit", "what": "thickness_max", "value": "16", "severity": "error",
         "message": "Лист {value} мм толще 16"},
        {"code": "U05", "title": "Только для СП", "kind": "text_forbidden", "pattern": "Пластина", "severity": "info",
         "applies": "spec"},
        {"code": "U06", "title": "Сборки", "kind": "text_required", "pattern": "xyz", "severity": "info",
         "applies": "parts", "material_contains": "09Г2С"},
    ]
    for r in rules:
        assert not custom.validate(r), (r["code"], custom.validate(r))
    hits = {r["code"]: custom.evaluate(d, r) for r in rules}
    assert "Ст3сп" in hits["U01"][0]["message"]                     # марки нет в перечне
    assert hits["U02"] and not hits["U03"]                           # в ТТ нет «Острые кромки…»; ООО «Беретта» есть
    assert hits["U04"][0]["message"] == "Лист 20 мм толще 16" and hits["U04"][0]["severity"] == "error"
    assert not hits["U05"] and not hits["U06"]                       # не тот тип документа / материал
    assert custom.validate({"kind": "text_required", "title": "x", "severity": "info", "match": "regex",
                            "pattern": "("})                         # битое регулярное выражение
    cfg = {"custom_rules": rules, "rules": {"U02": {"enabled": False}}}
    from checking import catalog
    out = catalog.apply_to_dict(custom.apply_to_dict(d, cfg), cfg)
    codes = {f["code"] for f in out["findings"]}
    assert {"U01", "U04"} <= codes and "U02" not in codes            # U02 выключено в списке правил


def test_custom_rules_api(tmp_path, monkeypatch):
    import app as webapp
    from checking import admin, config
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(admin, "PATH", str(tmp_path / "admin.json"))
    c = webapp.app.test_client()
    bad = c.post("/api/admin/custom", json={"title": "", "kind": "allowed", "severity": "info"})
    assert bad.status_code == 400 and "Перечень пуст" in bad.json["error"]
    r = c.post("/api/admin/custom", json={"title": "Марки", "kind": "allowed", "what": "grade", "severity": "warning",
                                          "values": "Ст3сп\n09Г2С"})
    assert r.status_code == 200 and r.json["code"] == "U01"
    assert any(g["key"] == "custom" and g["rules"][0]["code"] == "U01" for g in r.json["groups"])
    assert c.post("/api/admin/rule", json={"code": "U01", "enabled": False}).status_code == 200
    assert config.load_config()["rules"]["U01"] == {"enabled": False}
    r = c.post("/api/admin/custom", json={"code": "U01", "title": "Марки 2", "kind": "allowed", "what": "grade",
                                          "severity": "info", "values": ["45"]})
    assert r.json["code"] == "U01" and config.load_config()["custom_rules"][0]["title"] == "Марки 2"
    assert c.delete("/api/admin/custom/U01").json["custom_rules"] == []
    assert "U01" not in (config.load_config().get("rules") or {})


def test_graphic_roughness_sign_not_reported_as_missing():
    d, = check_file(os.path.join(SAMPLES, "drawings", "ДТМЛ.715311.003 - Палец нижний.pdf"))
    assert d.facts["rough_signs"] >= 1                       # знак «без обработки» нарисован графикой, без текста
    assert not [f for f in d.findings if f.code == "R02"]
    d, = check_file(os.path.join(SAMPLES, "drawings", "ДТМЛ.711111.001 - Кольцо.pdf"))
    assert [f for f in d.findings if f.code == "R02"]        # здесь знаков на изображении действительно нет


def test_dimension_layout(tmp_path):
    import pymupdf
    k = 72 / 25.4
    doc = pymupdf.open()
    pg = doc.new_page(width=297 * k, height=210 * k)

    def line(x1, y1, x2, y2):
        pg.draw_line((x1 * k, y1 * k), (x2 * k, y2 * k), width=0.5)

    def text(x, y, t, size=14):
        pg.insert_text((x * k, y * k), t, fontsize=size, fontname="helv")
    pg.draw_rect(pymupdf.Rect(20 * k, 5 * k, 292 * k, 205 * k), width=1)
    pg.draw_rect(pymupdf.Rect(60 * k, 60 * k, 160 * k, 120 * k), width=1)
    line(60, 58, 60, 52); line(160, 58, 160, 52); line(60, 55, 160, 55); text(100, 53.5, "100")   # 5 мм от контура
    line(60, 122, 60, 146); line(160, 122, 160, 134); line(60, 132, 160, 132); text(100, 130.5, "100")
    line(110, 122, 110, 146); line(60, 136, 110, 136); text(75, 134.5, "50")                      # 4 мм от соседней
    line(58, 60, 42, 60); line(58, 120, 42, 120); line(45, 60, 45, 120)                            # 15 мм — норма
    pg.insert_text((43 * k, 95 * k), "60", fontsize=14, fontname="helv", rotate=90)
    text(200, 100, "Size 45 mm"); text(203, 103, "Tolerance 7 um")                                 # наложение
    text(30, 180, "Технические требования проверка расположения размеров на листе чертежа", 10)
    p = tmp_path / "layout.pdf"
    doc.save(str(p))
    d, = check_file(str(p))
    got = {(f.code, f.message.split("»")[0]) for f in d.findings if f.code in ("D31", "D32", "D33")}
    assert any(c == "D32" and "«100" in m for c, m in got)
    assert [f for f in d.findings if f.code == "D33" and "«100» и «50»" in f.message]
    assert [f for f in d.findings if f.code == "D31"]
    assert not [f for f in d.findings if f.code == "D32" and "«60»" in f.message]


@pytest.mark.skipif(not os.path.isdir(RED), reason="нет образцов редуктора")
def test_vertical_dimension_tolerances_not_stolen_by_neighbour():
    d = _red("280-000060 Зубчатый венец редуктора Прево 2 ступени.pdf")
    raws = [x.raw for x in d.dims]
    assert raws.count("⌀335 -0,1 / -0,2") == 2 and raws.count("⌀295,7 +0,1") == 2
    assert not [r for r in raws if r.startswith("⌀295,7") and "-0,1" in r]
