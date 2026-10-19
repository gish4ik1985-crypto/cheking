"""Переносит «не ошибка» из exceptions.json (старая версия программы) в отметки тестировщиков новой версии.

Запуск из папки программы:
    python tools/import_exceptions.py [путь к exceptions.json]

Исключения продолжают действовать как раньше (exceptions.json не меняется); в «Настройки → Отметки тестеров»
дополнительно появятся записи «ложное» по соответствующим правилам (ревизия 1, версия «legacy»).
Повторный запуск дубли не создаёт."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from checking import exceptions, feedback  # noqa: E402


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else exceptions.PATH
    rules = exceptions.load_rules(path)
    added = feedback.import_exceptions(rules)
    print(f"{path}: записей {len(rules)}, перенесено новых {added}")


if __name__ == "__main__":
    main()
