"""Структуры данных: извлечённое содержимое чертежа и замечания проверки."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

ERROR, WARNING, INFO = "error", "warning", "info"
SEVERITY_RU = {ERROR: "Ошибка", WARNING: "Предупреждение", INFO: "Замечание"}
SEVERITY_ORDER = {ERROR: 0, WARNING: 1, INFO: 2}

CAT_DIM = "Размеры, допуски и посадки"
CAT_TECH = "Технологичность"
CAT_TT = "Технические требования"
CAT_TB = "Основная надпись и масса"
CAT_ERP = "Сверка с ERP / спецификацией"
CAT_DXF = "Сверка с DXF (развёртка)"
CAT_WELD = "Сварка"
CAT_FILE = "Файл"
CAT_GDT = "Допуски формы и расположения"
CAT_VIEW = "Изображения и обозначения"
CAT_REFS = "Ссылки на стандарты"
CAT_HEAT = "Термообработка и покрытия"
CAT_GEAR = "Зубчатые колёса и шлицы"
CAT_EL = "Элементы деталей и соединения"
CAT_ASM = "Сборочный чертёж и спецификация"
CAT_SPEC = "Спецификация"
CAT_CUSTOM = "Правила предприятия"
CAT_TD = "Текстовые документы"
CATEGORY_ORDER = [CAT_SPEC, CAT_DIM, CAT_GDT, CAT_EL, CAT_GEAR, CAT_ASM, CAT_TECH, CAT_WELD, CAT_HEAT, CAT_TT, CAT_REFS,
                  CAT_VIEW, CAT_TD, CAT_CUSTOM, CAT_DXF, CAT_TB, CAT_ERP, CAT_FILE]

Box = tuple[float, float, float, float]   # мм, от левого верхнего угла листа


@dataclass
class TextLine:
    """Строка текста на листе (координаты в мм, y вниз)."""
    text: str
    page: int
    bbox: Box
    dir: tuple[float, float]      # направление письма (1,0) — горизонтально
    size: float                   # высота шрифта, мм
    origin: tuple[float, float]   # точка базовой линии в начале строки, мм
    fonts: tuple[str, ...] = ()
    conf: float = 1.0             # уверенность (для OCR)
    used: bool = False

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2


@dataclass
class Word:
    text: str
    page: int
    bbox: Box
    line_no: int = -1             # индекс строки в Drawing.lines

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2


@dataclass
class Dimension:
    raw: str
    page: int
    bbox: Box
    kind: str = "linear"           # linear diameter radius sphere square thickness thread chamfer angle
    nominal: float | None = None
    field: str | None = None       # поле допуска размера (H7 / g6)
    fit_hole: str | None = None    # посадка H7/g6
    fit_shaft: str | None = None
    upper: float | None = None     # мм
    lower: float | None = None
    upper_raw: str | None = None
    lower_raw: str | None = None
    symmetric: bool = False        # указано через ±
    reference: str = ""            # "*" / "**"
    count: int | None = None       # «4 отв.»
    pitch: float | None = None     # резьба: шаг; фаска: катет
    thread_tol: str | None = None
    angle: float | None = None
    vertical: bool = False         # размерная надпись повёрнута
    cyrillic_in_field: bool = False
    decimal_point: bool = False    # использована точка вместо запятой
    g_size: str | None = None      # трубная резьба G: «1 1/2»
    chain: int | None = None       # «n×p=L»: число интервалов
    source: str = "pdf"

    @property
    def has_tolerance(self) -> bool:
        return bool(self.field or self.fit_hole or self.upper is not None or self.lower is not None)

    def label(self) -> str:
        return self.raw


@dataclass
class TitleBlock:
    found: bool = False
    origin: tuple[float, float] | None = None
    designation: str = ""
    name: str = ""
    material: str = ""
    organization: str = ""
    mass_raw: str = ""
    mass: float | None = None
    scale: str = ""
    sheet: str = ""
    sheets: str = ""
    format: str = ""
    litera: str = ""
    people: dict = field(default_factory=dict)        # роль -> фамилия
    dates: dict = field(default_factory=dict)
    changes: list = field(default_factory=list)       # [{'num','sheet','doc','date'}]
    rotated_designation: str = ""                      # графа 26
    revision: str = ""                                 # «Вер.» в шаблонах Solid Edge
    first_use: str = ""                                # перв. примен.
    bboxes: dict = field(default_factory=dict)         # поле -> bbox


@dataclass
class Finding:
    severity: str
    code: str
    category: str
    message: str
    page: int | None = None
    bbox: Box | None = None
    standard: str | None = None
    hint: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity_ru"] = SEVERITY_RU[self.severity]
        return d


@dataclass
class PageInfo:
    number: int
    width: float
    height: float
    image: str | None = None      # путь к PNG предпросмотра
    scanned: bool = False


@dataclass
class Drawing:
    path: str
    filename: str
    kind: str = ""                    # pdf / pdf-scan / image / cdw / dft
    pages: list[PageInfo] = field(default_factory=list)
    lines: list[TextLine] = field(default_factory=list)
    title: TitleBlock = field(default_factory=TitleBlock)
    dims: list[Dimension] = field(default_factory=list)
    tt: list[str] = field(default_factory=list)
    tt_lines: list[TextLine] = field(default_factory=list)
    roughness: list[dict] = field(default_factory=list)   # {'param','value','general','page','bbox'}
    findings: list[Finding] = field(default_factory=list)
    suppressed: list[Finding] = field(default_factory=list)    # отмечены пользователем «не ошибка»
    facts: dict = field(default_factory=dict)              # вычисленные сведения (габариты, материал...)
    ocr: bool = False
    error: str | None = None

    def page_info(self, number: int) -> PageInfo | None:
        for p in self.pages:
            if p.number == number:
                return p
        return None

    @property
    def first_page(self) -> int:
        return self.pages[0].number if self.pages else 0

    def add(self, severity, code, category, message, page=None, bbox=None, standard=None, hint=None):
        self.findings.append(Finding(severity, code, category, message, page, bbox, standard, hint))

    @property
    def counts(self) -> dict:
        c = {ERROR: 0, WARNING: 0, INFO: 0}
        for f in self.findings:
            c[f.severity] += 1
        return c
