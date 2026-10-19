"""Разбор выгрузки обратной связи (ZIP из «Настройки → Отметки тестеров → Выгрузить для разработки» или папка feedback/).

    python tools/review_digest.py путь\\к\\выгрузке.zip            # сводка: что отметили по каждому правилу и что написали
    python tools/review_digest.py путь\\к\\папке\\feedback           # то же из папки feedback рядом с exe
    python tools/review_digest.py выгрузка.zip --code E01          # подробно по одному правилу (все замечания, комментарии, чертежи)
    python tools/review_digest.py выгрузка.zip --comments          # только комментарии администраторов

Показывает по каждому правилу: сколько отметок «верно / ложное / неточно», тексты замечаний и пояснения тестеров, комментарии
администраторов («как должно быть»), пропуски и ошибки разбора. По этой сводке разработчик проверяет правило по тексту
стандарта (docs/norms/) и меняет его (с повышением ревизии REV)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

VERD = {"ok": "верно", "false": "ЛОЖНОЕ", "inexact": "неточно"}


def load(path: str) -> tuple[list[dict], list[dict]]:
    """(отметки по замечаниям, мнения экспертов). Каждая отметка дополнена полем job."""
    marks: list[dict] = []
    notes: list[dict] = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.endswith("/reviews.json"):
                    job = name.split("/")[1]
                    for e in json.loads(z.read(name).decode("utf-8")):
                        marks.append({**e, "job": e.get("job") or job})
                elif name == "expert_notes.json":
                    notes = json.loads(z.read(name).decode("utf-8"))
        return marks, notes
    base = path
    rdir = os.path.join(base, "reviews") if os.path.isdir(os.path.join(base, "reviews")) else base
    for fn in sorted(os.listdir(rdir)):
        if fn.endswith(".json") and fn not in ("rule_reviews.json", "expert_notes.json"):
            with open(os.path.join(rdir, fn), encoding="utf-8") as f:
                for e in json.load(f):
                    marks.append({**e, "job": e.get("job") or fn[:-5]})
    p = os.path.join(base, "expert_notes.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            notes = json.load(f)
    return marks, notes


def _line(e: dict) -> str:
    where = e.get("designation") or e.get("file") or e.get("job")
    bits = [f"{e.get('ts', '')[:16]} {e.get('user', '')}", f"чертёж {where}" if where else "", f"версия {e.get('app', '—')}"]
    return " · ".join(b for b in bits if b)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--code")
    ap.add_argument("--comments", action="store_true")
    a = ap.parse_args()
    marks, notes = load(a.path)
    from checking import catalog, rule_docs
    by_code: dict[str, list] = defaultdict(list)
    for e in marks:
        if e["type"] in ("finding", "comment") and e.get("code"):
            by_code[e["code"]].append(e)

    def title(code: str) -> str:
        r = catalog.RULE_INDEX.get(code)
        return r[2] if r else "(нет в этой версии программы)"

    if a.comments:
        for e in [m for m in marks if m["type"] == "comment"]:
            print("=" * 100)
            print(f"{e.get('code')}  {_line(e)}\n  замечание: {e.get('message')}\n  КОММЕНТАРИЙ: {e.get('comment')}"
                  + (f"\n  КАК ДОЛЖНО БЫТЬ: {e['expected']}" if e.get("expected") else ""))
        return
    if a.code:
        print(f"{a.code}: {title(a.code)}  (ревизия правила сейчас {rule_docs.rev_of(a.code)})")
        for e in by_code.get(a.code, []):
            kind = "КОММЕНТАРИЙ АДМИНИСТРАТОРА" if e["type"] == "comment" else VERD.get(e.get("verdict"), "?")
            print("-" * 100)
            print(f"[{kind}] {_line(e)} · ревизия правила при отметке {e.get('rev', '—')}")
            print(f"  замечание: {e.get('message')}")
            if e.get("comment"):
                print(f"  пояснение: {e['comment']}")
            if e.get("expected"):
                print(f"  как должно быть: {e['expected']}")
        for n in notes:
            if n.get("code") == a.code:
                print("-" * 100)
                print(f"[МНЕНИЕ ЭКСПЕРТА · {n.get('status')}] {n.get('user')} {n.get('ts', '')[:16]}: {n.get('text')}")
        return
    rows = []
    for code, es in by_code.items():
        c = Counter(e.get("verdict") for e in es if e["type"] == "finding")
        rows.append((code, c["false"], c["inexact"], c["ok"], sum(1 for e in es if e["type"] == "comment")))
    rows.sort(key=lambda r: (-(r[1] + r[2] + r[4]), r[0]))
    print(f"Отметок: {len(marks)} · мнений экспертов: {len(notes)}\n")
    print(f"{'Код':6}{'Ложных':>8}{'Неточно':>9}{'Верно':>7}{'Коммент.':>10}  Правило")
    for code, f, i, o, cm in rows:
        print(f"{code:6}{f:>8}{i:>9}{o:>7}{cm:>10}  {title(code)[:80]}")
    miss = [e for e in marks if e["type"] == "missed"]
    parse = [e for e in marks if e["type"] == "parse"]
    print(f"\nПропущено программой: {len(miss)} · ошибок разбора: {len(parse)}")
    for e in miss[:30]:
        print(f"  [пропуск · {e.get('group', '')}] {_line(e)}: {e.get('comment')}")
    for e in parse[:30]:
        print(f"  [разбор] {_line(e)}: прочитано «{e.get('dim', '')}», должно быть «{e.get('expected', '')}» {e.get('comment', '')}")
    print("\nПодробно по правилу:  python tools/review_digest.py <выгрузка> --code КОД")


if __name__ == "__main__":
    main()
