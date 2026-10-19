"""Заявки на проверки: пункты стандартов, отмеченные администратором во вкладке «Реестр стандартов».
Запуск: python tools/std_marks.py [open|done|rejected|all]  — печатает заявки с текстом пункта, чтобы по ним писать правила."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from checking import stdclauses  # noqa: E402

st = sys.argv[1] if len(sys.argv) > 1 else "open"
for m in stdclauses.load_marks():
    if st != "all" and m["status"] != st:
        continue
    print(f"[{m['status']}] {m['std']} п. {m['clause']} ({m['author']}, {m['created']}) id={m['id']}" + (f" правило {m['code']}" if m["code"] else ""))
    print(f"    текст: {m['text']}")
    if m["comment"]:
        print(f"    что проверить: {m['comment']}")
