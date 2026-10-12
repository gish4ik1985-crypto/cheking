"""Прямая сверка с базой ERP ЯСТ (PostgreSQL), только чтение.

Включается в config.json → "erp_db": {"enabled": true, "host": ..., "dbname": ..., "user": ..., "password": ...}.
Нужен пакет psycopg:  .venv\\Scripts\\python -m pip install "psycopg[binary]"

Поля берутся из таблиц products (карточка продукции) и technologies (материал активной технологии) —
по описанию модели в репозитории erp-yarst (Product::$decimal_number, $sku, $mass, $thickness,
$blank_length/$blank_width, Technology::$material_id, $is_default).
"""
from __future__ import annotations

SQL = """
SELECT p.sku, p.decimal_number, p.name, p.mass, p.thickness, p.length, p.width,
       p.blank_length, p.blank_width, m.name AS material_name, t.blank_base_size, t.blank_main_size
FROM products p
LEFT JOIN LATERAL (
    SELECT t.material_id, t.blank_base_size, t.blank_main_size
    FROM technologies t
    WHERE t.product_id = p.id AND t.deleted_at IS NULL
    ORDER BY t.is_default DESC, t.id DESC
    LIMIT 1
) t ON TRUE
LEFT JOIN products m ON m.id = t.material_id
WHERE p.deleted_at IS NULL AND (p.decimal_number = %(des)s OR p.sku = %(sku)s)
ORDER BY (p.decimal_number = %(des)s) DESC
LIMIT 1
"""


class ErpDb:
    def __init__(self, cfg: dict):
        import psycopg  # noqa: F401  — ошибка импорта = пакет не установлен
        self.cfg = cfg
        self._conn = None
        self.path = f"ERP {cfg.get('host')}/{cfg.get('dbname')}"

    def _connect(self):
        import psycopg
        if self._conn is None:
            c = self.cfg
            self._conn = psycopg.connect(host=c["host"], port=c.get("port", 5432), dbname=c["dbname"],
                                         user=c["user"], password=c.get("password", ""), connect_timeout=8,
                                         autocommit=True)
            self._conn.read_only = True
        return self._conn

    def find(self, designation: str, sku: str | None = None) -> dict | None:
        if not designation and not sku:
            return None
        with self._connect().cursor() as cur:
            cur.execute(SQL, {"des": designation or "", "sku": sku or ""})
            row = cur.fetchone()
        if not row:
            return None
        (sku_, des, name, mass, thick, length, width, bl, bw, mat, base, main) = row
        blank = main or (f"{bl:g}×{bw:g}" if bl and bw else (f"{bl:g}" if bl else ""))
        return {"designation": des or "", "sku": sku_ or "", "name": name or "", "mass": float(mass) if mass else None,
                "material": mat or "", "grade": "", "base_size": base or (f"{thick:g}" if thick else ""),
                "blank_size": blank, "blank_type": "", "section": "", "dxf_length": length, "dxf_width": width}

    def __len__(self):
        return 0
