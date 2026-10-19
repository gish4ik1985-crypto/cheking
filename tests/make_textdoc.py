"""Синтетические текстовые документы (А4, Times New Roman) для проверки ГОСТ Р 2.105 (checking/textdoc.py).

doc = TextDoc(); doc.title_page(...); doc.h1("1 Общие положения"); doc.para("..."); doc.save(path)
Положение — в мм от левого верхнего угла; левое поле 20 мм (рамка), абзацный отступ 12,5 мм, шрифт 14 пт,
полуторный интервал."""
from __future__ import annotations

import os

import pymupdf

FONTS = r"C:\Windows\Fonts"
REG = os.path.join(FONTS, "times.ttf")
BOLD = os.path.join(FONTS, "timesbd.ttf")
ITAL = os.path.join(FONTS, "timesi.ttf")
ARIAL = os.path.join(FONTS, "arial.ttf")
COUR = os.path.join(FONTS, "cour.ttf")
AVAILABLE = os.path.exists(REG) and os.path.exists(BOLD) and os.path.exists(ARIAL)
MM = 72 / 25.4


class TextDoc:
    def __init__(self, size=14.0, spacing=1.72, indent=12.5, left=25.0, font=None):
        self.doc = pymupdf.open()
        self.size, self.spacing, self.indent, self.left = size, spacing, indent, left
        self.font = font or REG
        self.page = None
        self.y = 0.0
        self.new_page()

    # --- страницы
    def new_page(self):
        self.page = self.doc.new_page(width=210 * MM, height=297 * MM)
        for name, f in (("tnr", self.font), ("tnrb", BOLD), ("tnri", ITAL), ("ar", ARIAL)):
            self.page.insert_font(fontname=name, fontfile=f)
        self.y = 25.0
        return self.page

    def _ensure(self, h):
        if self.y + h > 255:
            self.new_page()

    # --- текст
    def line(self, text, x=None, size=None, bold=False, font=None, y=None, italic=False):
        size = size or self.size
        x = self.left if x is None else x
        fn = font or ("tnrb" if bold else "tnri" if italic else "tnr")
        yy = self.y if y is None else y
        self.page.insert_text((x * MM, yy * MM + size * 0.8), text, fontname=fn, fontsize=size)
        return yy

    def _wrap(self, text, width_mm, size, fontfile=None):
        font = pymupdf.Font(fontfile=fontfile or self.font)
        words, lines, cur = text.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if font.text_length(t, fontsize=size) / MM <= width_mm:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def para(self, text, size=None, indent=None, first=True, italic=False, bold=False, x=None, width=None):
        size = size or self.size
        indent = self.indent if indent is None else indent
        x = self.left if x is None else x
        width = width or (200 - x)
        ff = BOLD if bold else self.font
        lines = self._wrap(text, width - (indent if first else 0), size, ff)
        step = size * 0.3528 * self.spacing
        for i, ln in enumerate(lines):
            self._ensure(step)
            self.line(ln, x=x + (indent if (i == 0 and first) else 0), size=size, bold=bold, italic=italic)
            self.y += step
        self.y += 1.0

    def h1(self, text, size=None):
        self.y += 3
        self._ensure(14)
        self.line(text, x=self.left + self.indent, size=size or self.size + 2, bold=True)
        self.y += (size or self.size + 2) * 0.3528 * 2.2

    def h2(self, text):
        self.y += 1
        self._ensure(12)
        self.line(text, x=self.left + self.indent, size=self.size, bold=True)
        self.y += self.size * 0.3528 * 2.0

    def center(self, text, size=None, bold=False, y=None):
        size = size or self.size
        font = pymupdf.Font(fontfile=BOLD if bold else REG)
        w = font.text_length(text, fontsize=size) / MM
        self.line(text, x=(20 + 205) / 2 - w / 2, size=size, bold=bold, y=y)

    def number_right(self, text, y=None):
        font = pymupdf.Font(fontfile=REG)
        w = font.text_length(text, fontsize=self.size) / MM
        self.line(text, x=203 - w, y=y)

    def save(self, path):
        self.doc.save(path)
        self.doc.close()
        return path


def good_document(path, pages_extra=0):
    """Документ без нарушений: титульный лист, содержание, разделы, таблица, рисунок, формула, приложение А."""
    d = TextDoc()
    d.center("СТАНОК ГОРИЗОНТАЛЬНЫЙ", bold=True, y=60)
    d.center("Технические условия", y=75)
    d.center("ДТМЛ.123456.001ТУ", y=95)
    d.new_page()
    d.y = 25
    d.center("Содержание", bold=True, y=25)
    d.y = 40
    for t in ("1 Общие положения", "2 Технические требования", "Приложение А Пример расчёта"):
        d.line(t + " " + "." * 20 + " 3", x=25)
        d.y += 8
    d.new_page()
    d.h1("1 Общие положения")
    d.para("Настоящие технические условия распространяются на станок горизонтальный и устанавливают требования к "
           "изготовлению, приёмке и испытаниям изделия в нормальных условиях, указанных в таблице 1 и на рисунке 1.")
    d.para("Допускаемые значения приведены в приложении А и в формуле (1), температура от 10 до 40 °С.")
    d.line("Таблица 1 — Основные параметры", x=25)
    d.y += 8
    d.para("Рисунок 1 — Общий вид изделия", indent=0)
    d.line("m = ρ · V", x=60)
    d.line("(1)", x=191)
    d.y += 8
    d.para("где ρ — плотность, кг/м3; V — объём, м3.", indent=0)
    d.h1("2 Технические требования")
    d.para("Изделие должно соответствовать требованиям настоящих технических условий. Масса не более 25 кг.")
    d.new_page()
    d.center("Приложение А", y=25)
    d.center("(справочное)", y=33)
    d.center("Пример расчёта", bold=True, y=41)
    d.y = 52
    d.para("А.1 Расчёт выполняют по формуле (1).")
    return d.save(path)


def bad_document(path):
    """Документ с намеренными нарушениями ГОСТ Р 2.105 (по одному на правило L…)."""
    d = TextDoc()
    d.center("СТАНОК ГОРИЗОНТАЛЬНЫЙ", bold=True, y=60)
    d.center("ДТМЛ.123456.001ТУ ЛУ", y=75)
    d.new_page()
    d.line("1. Общие положения.", x=37.5, bold=True, size=16)
    d.y += 12
    d.para("Диаметр отверстия Ø20 мм, температура –5 °С и более, при значении > нормы изделие принимают по ТУ без номера, "
           "нагрузку задают в кгс и указывают в мм для всех деталей изделия.")
    d.para("Допуск от 5 мм до 10 мм, зазор 5–10 мм, масса 0.5 кг, дата 12.05.19, нужны 3 детали для проверки по рис. 2 и "
           "по табл. 4, а также по ГОСТ 2.316 п. 4.17 и по ГОСТ 1234 для всех случаев применения.")
    d.para("Зазор не должен превышать 10")
    d.line("мм", x=d.left)
    d.y += 8
    d.para("• первая позиция перечисления в тексте документа достаточно длинная для проверки")
    d.para("а) первый вариант записи перечисления в тексте документа достаточно длинный")
    d.para("б) второй вариант записи перечисления в тексте документа достаточно длинный")
    d.para("г) третий вариант записи перечисления в тексте документа достаточно длинный")
    d.line("Таблица 1 - Параметры", x=25)
    d.y += 8
    d.line("Таблица 3 — Размеры", x=25)
    d.y += 8
    d.line("№ п/п", x=25)
    d.y += 8
    d.line("Рисунок 1 Общий вид", x=25)
    d.y += 8
    d.line("m = ρ · V", x=60)
    d.line("(1)", x=191)
    d.y += 8
    d.line("m2 = ρ2 · V", x=60)
    d.line("(3)", x=191)
    d.y += 8
    d.para("по формуле 2 вычисляют значение, где:", indent=0)
    d.para("Примечание: масса изделия указана справочно, изделие должно быть окрашено.", indent=0)
    d.para("Пример: окраска в два слоя.", indent=0)
    d.para("Сокращения АБВГ, АБВГ, АБВГ, ДЕЖЗ, ДЕЖЗ, ДЕЖЗ, КЛМН, КЛМН, КЛМН применены в документе без перечня.", indent=0)
    d.h1("3 Методы испытаний")
    d.new_page()
    d.center("Приложение Ё", y=25)
    d.center("Пример расчёта", bold=True, y=41)
    d.y = 52
    d.para("Б.1 Расчёт выполняют по формуле (1).")
    return d.save(path)


def bad_document2(path):
    """Ещё нарушения: повтор таблиц и рисунков, продолжение, «где:», годы ссылок, звёздочки, содержание, формат ЛУ, порядок."""
    d = TextDoc()
    d.center("ТОРМОЗ ДИСКОВЫЙ", bold=True, y=60)
    d.center("ДТМЛ.123456.002ПЗ", y=75)
    d.new_page()
    d.line("Приложение А", x=90, size=14)
    d.line("(справочное)", x=90, size=14, y=33)
    d.y = 45
    d.para("Текст страницы для заполнения листа, чтобы страница не считалась сканом при чтении документа.", indent=0)
    d.new_page()
    d.center("СОДЕРЖАНИЕ", y=25)
    d.y = 40
    d.line("1 Общие положения .......... 3", x=25)
    d.y += 10
    d.line("Раздел без отточия", x=25)
    d.y += 8
    d.para("Текст страницы для заполнения листа, чтобы страница не считалась сканом при чтении документа.", indent=0)
    d.new_page()
    d.h1("1 Общие положения")
    d.h1("2 Расчёты")
    d.line("Таблица 1 — Параметры", x=25)
    d.y += 8
    d.line("Таблица 1 — Параметры", x=25)
    d.y += 8
    d.line("Продолжение таблицы 7", x=25)
    d.y += 8
    d.line("Рисунок 1 — Вид", x=25)
    d.y += 8
    d.line("Рисунок 3 — Вид", x=25)
    d.y += 8
    d.para("См. рисунок 5, таблицу 1 и ГОСТ 2.316-68 для определения параметров изделия в полном объёме.")
    d.line("где: m — масса", x=25)
    d.y += 8
    d.para("Сноска **** внизу страницы приведена для проверки правила о звёздочках в тексте документа.")
    d.para("Ссылочные нормативные документы", indent=0, bold=True)
    d.para("ГОСТ 2.316-2008 Единая система конструкторской документации", indent=0)
    p = d.doc.new_page(width=297 * MM, height=420 * MM)
    p.insert_font(fontname="tnr", fontfile=REG)
    p.insert_text((60 * MM, 40 * MM), "Лист утверждения", fontname="tnr", fontsize=14)
    p.insert_text((60 * MM, 60 * MM), "Страница формата А3 для проверки формата листа утверждения.", fontname="tnr", fontsize=14)
    return d.save(path)


def bad_typography(path):
    """Текст шрифтом Courier New 10 пт с одинарным интервалом и малым абзацным отступом."""
    d = TextDoc(size=10, spacing=1.0, indent=6.0, left=21.0, font=COUR)
    d.center("ЗАГОЛОВОК ДОКУМЕНТА", bold=True, y=60)
    d.center("ДТМЛ.123456.003РЭ", y=75)
    d.new_page()
    d.y = 25
    text = ("Изделие предназначено для работы в нормальных условиях эксплуатации и должно обслуживаться персоналом, "
            "прошедшим обучение. Эксплуатацию изделия выполняют в соответствии с настоящим руководством по эксплуатации. ")
    for _ in range(14):
        d.para(text)
    return d.save(path)


def long_document(path, pages=26):
    d = TextDoc()
    d.center("ИЗДЕЛИЕ ДЛЯ ПРОВЕРКИ ОБЪЁМА", bold=True, y=60)
    d.center("Пояснительная записка", y=68)
    d.center("ДТМЛ.123456.004ПЗ", y=75)
    for i in range(pages):
        d.new_page()
        d.y = 25
        d.para(f"Страница {i + 1}. Текст расчётной части документа, который не содержит заголовков и структурных элементов.")
    return d.save(path)
