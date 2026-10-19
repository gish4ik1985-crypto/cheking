"""Собирает из исходников, на какие стандарты ссылается каждая проверка (последний аргумент drw.add(...)),
и записывает checking/rule_standards.py.
Запуск: python tools/gen_rule_standards.py
Тест test_rule_standards_fresh следит, чтобы файл не устарел.

Понимает вызовы: drw.add(sev, "КОД", кат, текст, стр, рамка, стандарт), _flag(doc, sev, "КОД", текст, …, std=…) и
hit("КОД", …, std), seq_check(items, текст, "КОД", std) из checking/textdoc.py; стандарт — строка, константа модуля или S("6.5.4") (ГОСТ Р 2.105-2019 п. …)."""
from __future__ import annotations

import ast
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "checking", "rule_standards.py")
CODE = re.compile(r"[A-Z]\d{2}")
STD = re.compile(r"^(ГОСТ|ОСТ|СТО|ISO)")


def _code_and_rest(n: ast.Call):
    """(код, остальные аргументы) для поддерживаемых вызовов или None."""
    kw = [k.value for k in n.keywords]
    f = n.func
    if isinstance(f, ast.Attribute) and f.attr in ("add", "_add") and len(n.args) >= 2:
        return n.args[1], n.args[2:] + kw
    if isinstance(f, ast.Name) and f.id == "_flag" and len(n.args) >= 3:
        return n.args[2], n.args[3:] + kw
    if isinstance(f, ast.Name) and f.id == "hit" and n.args:
        return n.args[0], n.args[1:] + kw
    if isinstance(f, ast.Name) and f.id == "seq_check" and len(n.args) >= 4:
        return n.args[2], n.args[3:] + kw
    return None


def collect() -> dict[str, list[str]]:
    res: dict[str, set[str]] = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "checking", "*.py"))):
        if os.path.basename(f) == "rule_standards.py":
            continue
        tree = ast.parse(open(f, encoding="utf-8").read())
        consts = {}
        for n in tree.body:
            if (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                    and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)):
                consts[n.targets[0].id] = n.value.value

        def value(a):
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                return a.value
            if isinstance(a, ast.Name):
                return consts.get(a.id)
            if (isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id == "S" and len(a.args) == 1
                    and isinstance(a.args[0], ast.Constant) and "STD" in consts):
                p = str(a.args[0].value)
                return f"{consts['STD']} п. {p}" if p[:1].isdigit() else f"{consts['STD']} {p}"
            return None

        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            got = _code_and_rest(n)
            fn = n.func
            # спецификация: add(sev, "S01", текст, …) и hit(sev, "S06", …) — стандарт задан константой модуля STD
            if (isinstance(fn, ast.Name) and fn.id in ("add", "hit") and len(n.args) >= 2 and "STD" in consts
                    and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str)
                    and CODE.fullmatch(n.args[1].value)):
                res.setdefault(n.args[1].value, set()).add(consts["STD"])
                continue
            if got is None:
                continue
            c, rest = got
            if not (isinstance(c, ast.Constant) and isinstance(c.value, str) and CODE.fullmatch(c.value)):
                continue
            for a in rest:
                v = value(a)
                if v and STD.match(v):
                    res.setdefault(c.value, set()).add(v)
    return {k: sorted(v) for k, v in sorted(res.items())}


def render(data: dict[str, list[str]]) -> str:
    lines = ['"""Стандарты, на которые ссылается каждая проверка. Файл создаётся скриптом tools/gen_rule_standards.py."""',
             "RULE_STANDARDS = {"]
    for k, v in data.items():
        lines.append(f"    {k!r}: {v!r},")
    lines.append("}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    text = render(collect())
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"{OUT}: {text.count(chr(10)) - 3} проверок")
