"""Исключения «не ошибка»: замечание, отмеченное пользователем, больше не показывается.

Хранятся в exceptions.json в корне программы:
* scope="drawing" — конкретное замечание конкретного чертежа (код + текст + обозначение/файл);
* scope="global"  — правило (код) отключено везде, опционально только для замечаний, содержащих pattern.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

from .config import DATA
from .textnorm import norm_designation

PATH = os.path.join(DATA, "exceptions.json")
_LOCK = threading.Lock()


def load_rules(path: str | None = None) -> list[dict]:
    path = path or PATH
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("rules", [])
    except Exception:
        return []


def _save(rules: list[dict], path: str | None = None) -> None:
    path = path or PATH
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"rules": rules}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def add_rule(rule: dict, path: str | None = None) -> dict:
    with _LOCK:
        rules = load_rules(path)
        rule = {**rule, "id": uuid.uuid4().hex[:10], "created": time.strftime("%Y-%m-%d %H:%M")}
        rules.append(rule)
        _save(rules, path)
    return rule


def delete_rule(rule_id: str, path: str | None = None) -> bool:
    with _LOCK:
        rules = load_rules(path)
        left = [r for r in rules if r.get("id") != rule_id]
        _save(left, path)
    return len(left) != len(rules)


def match(rule: dict, designation: str, filename: str, code: str, message: str) -> bool:
    if rule.get("code") and rule["code"] != code:
        return False
    if rule.get("scope") == "global":
        pat = (rule.get("pattern") or "").strip().lower()
        return not pat or pat in message.lower()
    if rule.get("message") != message:
        return False
    rd, rf = rule.get("designation") or "", rule.get("file") or ""
    if rd and designation:
        return norm_designation(rd) == norm_designation(designation)
    return bool(rf) and rf == filename


def apply_to_dict(d: dict, rules: list[dict]) -> dict:
    """Переносит отмеченные замечания из findings в suppressed и пересчитывает counts (на копии)."""
    out = dict(d)
    des = (d.get("title") or {}).get("designation") or ""
    keep, hidden = [], []
    for f in d.get("findings", []) + d.get("suppressed", []):
        f = {k: v for k, v in f.items() if k != "rule_id"}
        r = next((r for r in rules if match(r, des, d.get("file", ""), f["code"], f["message"])), None)
        if r:
            hidden.append({**f, "rule_id": r["id"], "rule_scope": r.get("scope")})
        else:
            keep.append(f)
    out["findings"], out["suppressed"] = keep, hidden
    out["counts"] = {s: sum(1 for f in keep if f["severity"] == s) for s in ("error", "warning", "info")}
    return out


def apply_to_drawing(drw, rules: list[dict]) -> None:
    if not rules:
        return
    keep = []
    for f in drw.findings:
        if any(match(r, drw.title.designation, drw.filename, f.code, f.message) for r in rules):
            drw.suppressed.append(f)
        else:
            keep.append(f)
    drw.findings = keep
