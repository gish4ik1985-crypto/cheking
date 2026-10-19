"""Работа разработчика с мнениями экспертов по правилам (feedback/expert_notes.json).

    python tools/expert_notes.py                  # неразобранные мнения: правило, как оно описано сейчас, мнение
    python tools/expert_notes.py --all            # все мнения со статусами
    python tools/expert_notes.py reply ID applied "Что проверено и что сделано" [--rev 2]
    python tools/expert_notes.py reply ID rejected "Почему не принято"
    python tools/expert_notes.py reply ID accepted "Что будет сделано"

Порядок: прочитать мнение → перепроверить по тексту стандарта (docs/norms/) и коду правила → при необходимости изменить
правило, увеличить его ревизию (checking/rule_docs.py: REV) и описание → ответить на мнение. Ответ виден эксперту в панели.
Подробно — docs/EXPERT_NOTES.md."""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from checking import catalog, expert, rule_docs  # noqa: E402


def show(n: dict) -> None:
    r = catalog.RULE_INDEX.get(n["code"])
    d = rule_docs.RULE_DOCS.get(n["code"]) or {}
    print("=" * 100)
    print(f"{n['id']}  [{expert.STATUSES.get(n.get('status'), n.get('status'))}]  {n['ts']}  {n['user']}  "
          f"правило {n['code']} ревизия {n.get('rev', 1)} (сейчас {rule_docs.rev_of(n['code'])}), версия {n.get('app') or '—'}")
    print(f"Правило: {r[2] if r else '(нет в этой версии программы)'}")
    if d:
        print(f"Как работает сейчас: {d['how']}")
    print(f"МНЕНИЕ ЭКСПЕРТА:\n{n['text']}")
    if n.get("dev"):
        print(f"Ответ разработчика ({n['dev']['ts']}): {n['dev']['comment']}"
              + (f" [ревизия после правки {n['dev']['rev_after']}]" if n["dev"].get("rev_after") else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    ap.add_argument("--all", action="store_true", help="показать и разобранные мнения")
    rp = sub.add_parser("reply")
    rp.add_argument("id")
    rp.add_argument("status", choices=["accepted", "rejected", "applied"])
    rp.add_argument("comment")
    rp.add_argument("--rev", type=int, default=None, help="ревизия правила после правки")
    a = ap.parse_args()
    if a.cmd == "reply":
        res = expert.reply(a.id, a.status, a.comment, a.rev)
        print(res if isinstance(res, str) else f"Ответ записан: {res['id']} → {expert.STATUSES[res['status']]}")
        return
    notes = expert.listing() if a.all else expert.listing(status="new")
    if not notes:
        print("Неразобранных мнений нет." if not a.all else "Мнений нет.")
    for n in sorted(notes, key=lambda x: (x["code"], x["ts"])):
        show(n)


if __name__ == "__main__":
    main()
