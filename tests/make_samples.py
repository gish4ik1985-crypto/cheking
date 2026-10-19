"""Генерирует тестовые PDF-чертежи с заведомыми ошибками в допусках/посадках.

Раскладка повторяет вывод КОМПАС-3D: номинал шрифтом 3,5 мм, отклонения — отдельными строками
меньшим шрифтом справа (верхнее над нижним), основная надпись формы 1 в правом нижнем углу.
Запуск:  python tests/make_samples.py  -> samples/test/*.pdf
"""
from __future__ import annotations

import os

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "samples", "test")
FONT = r"C:\Windows\Fonts\GOST_AU.ttf"
if not os.path.exists(FONT):
    FONT = r"C:\Windows\Fonts\arial.ttf"
MM = 72 / 25.4


def _t(page, x, y, text, h=3.5, rotate=0):
    """Текст: (x, y) — левый нижний угол (базовая линия) в мм; h — высота шрифта в мм."""
    page.insert_text((x * MM, y * MM), text, fontsize=h * MM * 1.4, fontname="gost", fontfile=FONT,
                     rotate=rotate)


def _dim(page, x, y, nominal, up=None, lo=None, h=3.5, vertical=False):
    """Размер с отклонениями в два яруса (как КОМПАС)."""
    if not vertical:
        _t(page, x, y, nominal, h)
        w = len(nominal) * h * 0.75 + 1.0
        if up is not None:
            _t(page, x + w, y - h * 0.55, up, h * 0.7)
        if lo is not None:
            _t(page, x + w, y + h * 0.15, lo, h * 0.7)
    else:  # надпись повёрнута на 90° (читается снизу вверх)
        _t(page, x, y, nominal, h, rotate=90)
        w = len(nominal) * h * 0.75 + 1.0
        if up is not None:
            _t(page, x - h * 0.55, y - w, up, h * 0.7, rotate=90)
        if lo is not None:
            _t(page, x + h * 0.15, y - w, lo, h * 0.7, rotate=90)


def _title_block(page, pw, ph, des, name, material, mass, scale="1:1", fmt="A4", rotated=True):
    x0, y0 = pw - 190, ph - 60
    shape = page.new_shape()
    shape.draw_rect(pymupdf.Rect(20 * MM, 5 * MM, (pw - 5) * MM, (ph - 5) * MM))
    shape.draw_rect(pymupdf.Rect(x0 * MM, y0 * MM, (x0 + 185) * MM, (y0 + 55) * MM))
    shape.finish(width=0.7, color=(0, 0, 0))
    shape.commit()
    lab = 2.5
    for text, dx, dy in (("Изм.", 1, 21), ("Разраб.", 1, 26), ("Пров.", 1, 31), ("Т.контр.", 1, 36),
                         ("Н.контр.", 1, 46), ("Утв.", 1, 51), ("Лит.", 139.1, 16), ("Масса", 153.1, 16),
                         ("Масштаб", 168, 16), ("Лист", 136.9, 36), ("Листов", 157.9, 36)):
        _t(page, x0 + dx, y0 + dy + lab, text, lab)
    _t(page, x0 + 18, y0 + 26 + lab, "Иванов", lab)
    _t(page, x0 + 75, y0 + 10, des, 5)
    _t(page, x0 + 75, y0 + 30, name, 5)
    if " / " in material:
        a, b = material.split(" / ")
        _t(page, x0 + 70, y0 + 46, a, 3.5)
        _t(page, x0 + 75, y0 + 52, b, 3.5)
    else:
        _t(page, x0 + 70, y0 + 49, material, 3.5)
    _t(page, x0 + 153, y0 + 29, mass, 3.5)
    _t(page, x0 + 172, y0 + 29, scale, 3.5)
    _t(page, x0 + 180, y0 + 39.5, "1", lab)
    _t(page, x0 + 140, ph - 1.5, "Формат", lab)
    _t(page, x0 + 165, ph - 1.5, fmt, lab)
    if rotated:
        _t(page, 90, 12, des, 5, rotate=180)


def make_errors():
    """Деталь из листа с набором ошибок в размерах и допусках."""
    doc = pymupdf.open()
    pw, ph = 210, 297
    page = doc.new_page(width=pw * MM, height=ph * MM)
    _title_block(page, pw, ph, "ДТМЛ.741111.900", "Планка тестовая",
                 "Лист 12 ГОСТ 19903-2015 / Ст3сп ГОСТ 14637-89", "99")
    y = 30
    _dim(page, 30, y, "⌀20H7"); y += 12                                  # норма
    _dim(page, 30, y, "⌀20H7(+0,025)"); y += 12                          # D03 неверные отклонения
    _dim(page, 30, y, "⌀35", "+0,1", "-0,05"); y += 12                   # D06 разное число знаков
    _dim(page, 30, y, "50", "+0,2", "-0,2"); y += 12                     # D05 надо ±
    _dim(page, 30, y, "40", "-0,1", "+0,1"); y += 12                     # D04 перепутаны
    _dim(page, 30, y, "⌀12", "+0,003", "-0,002"); y += 12                # T02 очень жёстко
    _dim(page, 30, y, "60*", "+0,1", "-0,1"); y += 12                    # D08 справочный с допуском
    _dim(page, 30, y, "⌀40g6/H7"); y += 12                               # D13 перепутаны отв./вал
    _dim(page, 30, y, "⌀25H7/k6"); y += 12                               # посадка — инфо
    _dim(page, 30, y, "⌀30Js7"); y += 12                                 # D01 регистр
    _dim(page, 30, y, "⌀30H19"); y += 12                                 # D01 нет квалитета
    _dim(page, 30, y, "12t6"); y += 12                                   # D01 нет поля для размера
    _dim(page, 30, y, "⌀18,5H7"); y += 12                                # D11 не Ra40
    _dim(page, 30, y, "M13"); y += 12                                    # D15 нет диаметра
    _dim(page, 30, y, "M20×1,25"); y += 12                               # D15 шаг
    _dim(page, 30, y, "R1,7"); y += 12                                   # D17 ряд радиусов
    _dim(page, 110, 30, "⌀8")                                            # T01 отверстие < s=12
    _t(page, 110, 36, "4 отв.")
    _dim(page, 110, 50, "250"); _dim(page, 150, 90, "180", vertical=True)
    _dim(page, 120, 110, "45,5", "+0,05", "-0,02", vertical=True)       # вертикальный, T03 на листе
    _t(page, 150, 22, "Ra 6,3 (")
    _t(page, 175, 22, ")")
    _t(page, 100, 160, "1 * Размеры для справок.")
    _t(page, 100, 167, "2 Острые кромки притупить.")
    doc.save(os.path.join(OUT, "ДТМЛ.741111.900 - Планка тестовая.pdf"))


def make_clean():
    """Вал без ошибок: посадки, стандартная резьба, ТТ с неуказанными отклонениями."""
    doc = pymupdf.open()
    pw, ph = 210, 297
    page = doc.new_page(width=pw * MM, height=ph * MM)
    _title_block(page, pw, ph, "ДТМЛ.715123.901", "Вал", "Круг 42 ГОСТ 2590-2006 / 45 ГОСТ 1050-2013", "1,33")
    _dim(page, 30, 40, "⌀40k6")
    _dim(page, 30, 52, "⌀35", "-0,025", "-0,050")       # 35f7 записан отклонениями — верно
    _dim(page, 30, 64, "⌀40H7/k6")
    _dim(page, 30, 76, "M24×2-6g")
    _dim(page, 30, 88, "130")
    _dim(page, 30, 100, "1×45°")
    _dim(page, 30, 112, "R1")
    _t(page, 150, 22, "Ra 3,2 (")
    _t(page, 175, 22, ")")
    _t(page, 40, 130, "Ra 0,8")
    _t(page, 100, 160, "1 Неуказанные предельные отклонения размеров: H14, h14, ±IT14/2.")
    _t(page, 100, 167, "2 Острые кромки притупить.")
    doc.save(os.path.join(OUT, "ДТМЛ.715123.901 - Вал.pdf"))


def make_dxf():
    """DXF: к тестовой планке — с расхождениями; к реальной «Пластине» ДТМЛ.741214.001 — совпадающий."""
    import ezdxf
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (250, 0), (250, 180), (0, 180)], close=True, dxfattribs={"layer": "Outer_Loop"})
    for x in (30, 60, 90):                                   # на чертеже «⌀8 4 отв.» — в DXF только 3
        msp.add_circle((x, 30), 4, dxfattribs={"layer": "Interior_Loops"})
    msp.add_circle((150, 90), 10, dxfattribs={"layer": "Interior_Loops"})      # ⌀20H7
    for x in (200, 220):                                     # лишние ⌀12,5
        msp.add_circle((x, 150), 6.25, dxfattribs={"layer": "Interior_Loops"})
    msp.add_text("КОД-ЯСТ", dxfattribs={"layer": "Up_Etch"})
    doc.saveas(os.path.join(OUT, "ДТМЛ.741111.900 - Планка тестовая_12мм.dxf"))

    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (180, 0), (180, 350), (0, 350)], close=True, dxfattribs={"layer": "Outer_Loop"})
    for x, y in ((30, 30), (150, 30), (30, 320), (150, 320)):
        msp.add_arc((x, y), 10, 0, 180, dxfattribs={"layer": "Interior_Loops"})  # окружность из двух дуг
        msp.add_arc((x, y), 10, 180, 360, dxfattribs={"layer": "Interior_Loops"})
    doc.saveas(os.path.join(OUT, "ДТМЛ.741214.001 Пластина_16мм.dxf"))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    make_errors()
    make_clean()
    make_dxf()
    print("готово:", OUT)
