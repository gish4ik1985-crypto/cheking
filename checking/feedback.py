"""Журнал действий и отметки тестировщиков (папка feedback рядом с программой).

* feedback/actions.jsonl — действия пользователей (вход, проверка, отметки, настройки);
* feedback/reviews/<проверка>.json — отметки по отчёту: верно / ложное замечание, пропущено программой,
  неверно прочитано.
Выгрузка для разработки — ZIP с отметками, журналом, отчётами и самими чертежами."""
from __future__ import annotations

import io
import json
import os
import threading
import time
import uuid
import zipfile
from collections import Counter, defaultdict

from .config import DATA
from .rule_docs import rev_of
from .version import APP_VERSION

DIR = os.path.join(DATA, "feedback")
_LOCK = threading.Lock()
TYPES = ("finding", "missed", "parse", "comment")        # comment — комментарий администратора к замечанию
VERDICTS = ("ok", "false", "inexact")
GROUPS = ["Размеры", "Допуски и посадки", "Шероховатость", "Допуски формы и расположения", "Резьбы",
          "Технические требования", "Основная надпись", "Масса", "Материал", "Сборка / спецификация",
          "Сварка", "Зубчатые колёса", "Оформление листа", "Другое"]


def _reviews_dir() -> str:
    d = os.path.join(DIR, "reviews")
    os.makedirs(d, exist_ok=True)
    return d


def log(user: str | None, action: str, detail: dict | str | None = None) -> None:
    os.makedirs(DIR, exist_ok=True)
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "user": user or "—", "action": action, "detail": detail or ""}
    with _LOCK, open(os.path.join(DIR, "actions.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def actions(user: str | None = None, limit: int = 500) -> list[dict]:
    p = os.path.join(DIR, "actions.jsonl")
    out: list[dict] = []
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if user is None or r.get("user") == user:
                    out.append(r)
    return out[-limit:][::-1]


def _path(job: str) -> str:
    return os.path.join(_reviews_dir(), os.path.basename(job) + ".json")


def entries(job: str, user: str | None = None) -> list[dict]:
    p = _path(job)
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    return [e for e in data if user is None or e.get("user") == user]


def add(job: str, user: str, rec: dict) -> dict | str:
    """Возвращает запись или текст ошибки."""
    t = rec.get("type")
    if t not in TYPES:
        return "Неизвестный тип отметки"
    if t == "finding":
        if rec.get("verdict") not in VERDICTS:
            return "Не указан вердикт"
    elif not (rec.get("comment") or "").strip():
        return "Опишите, что именно не так"
    e = {"id": uuid.uuid4().hex[:10], "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "user": user, "job": job, "type": t,
         "app": APP_VERSION}
    if t == "finding" and rec.get("code"):
        e["rev"] = rev_of(rec["code"])          # ревизия правила в момент отметки (см. checking/rule_docs.py)
    for k in ("doc", "file", "designation", "code", "message", "page", "point", "bbox", "verdict", "reason", "comment",
              "group", "dim", "expected"):
        if rec.get(k) not in (None, ""):
            e[k] = rec[k]
    with _LOCK:
        data = entries(job)
        if t == "finding":       # у одного пользователя на одно замечание — одна отметка
            data = [x for x in data if not (x["type"] == "finding" and x["user"] == user and x.get("doc") == e.get("doc")
                                            and x.get("code") == e.get("code") and x.get("message") == e.get("message"))]
        data.append(e)
        tmp = _path(job) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _path(job))
    return e


def remove(job: str, user: str, fid: str, is_admin: bool = False) -> bool:
    with _LOCK:
        data = entries(job)
        keep = [x for x in data if not (x["id"] == fid and (is_admin or x["user"] == user))]
        if len(keep) == len(data):
            return False
        with open(_path(job), "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False, indent=1)
    return True


def all_jobs() -> list[str]:
    d = _reviews_dir()
    return [f[:-5] for f in sorted(os.listdir(d)) if f.endswith(".json")]


def summary() -> dict:
    """Сводка по всем отметкам: по правилам (верно / ложное), пропуски по группам, ошибки разбора."""
    from .catalog import RULE_INDEX
    rules: dict[str, Counter] = defaultdict(Counter)
    old_rules: dict[str, Counter] = defaultdict(Counter)       # отметки по прежним ревизиям правила
    example: dict[str, str] = {}
    missed, parse, comments, users = [], [], [], Counter()
    for job in all_jobs():
        for e in entries(job):
            users[e["user"]] += 1
            if e["type"] == "finding":
                code = e.get("code", "?")
                # отметки старых версий программы без поля rev относятся к первой ревизии правила
                (rules if e.get("rev", 1) == rev_of(code) else old_rules)[code][e["verdict"]] += 1
                example.setdefault(code, e.get("message", ""))
            elif e["type"] == "missed":
                missed.append(e)
            elif e["type"] == "comment":
                comments.append(e)
            else:
                parse.append(e)
    rows = []
    for code in sorted(set(rules) | set(old_rules)):
        c, o = rules.get(code, Counter()), old_rules.get(code, Counter())
        n = sum(c.values())
        meta = RULE_INDEX.get(code)
        rows.append({"code": code, "title": meta[2] if meta else "", "known": bool(meta), "rev": rev_of(code),
                     "ok": c["ok"], "false": c["false"], "inexact": c["inexact"], "total": n,
                     "false_share": round(c["false"] / n, 2) if n else 0, "example": example.get(code, ""),
                     "old": {"ok": o["ok"], "false": o["false"], "inexact": o["inexact"], "total": sum(o.values())}})
    rows.sort(key=lambda r: (-r["false"], r["code"]))
    by_group = Counter(e.get("group") or "Другое" for e in missed)
    return {"rules": rows, "missed": missed[::-1][:200], "missed_groups": by_group.most_common(),
            "parse": parse[::-1][:200], "comments": comments[::-1][:300], "users": users.most_common()}


def export_zip(work_dir: str, users: list[dict], with_all_jobs: bool = False) -> bytes:
    """ZIP для разработки: журнал, отметки, отчёты проверок с отметками и загруженные чертежи."""
    buf = io.BytesIO()
    jobs = set(all_jobs())
    if with_all_jobs and os.path.isdir(work_dir):
        jobs |= {j for j in os.listdir(work_dir) if os.path.exists(os.path.join(work_dir, j, "report.json"))}
    reviewed = set(all_jobs())
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", "Выгрузка программы проверки чертежей\n"
                   "actions.jsonl — журнал действий; users.json — пользователи (без паролей);\n"
                   "summary.json — сводка отметок; expert_notes.json — мнения экспертов по правилам; jobs/<проверка>/ — отчёт (report.json), отметки (reviews.json), "
                   "чертежи (uploads/).\n")
        z.writestr("users.json", json.dumps(users, ensure_ascii=False, indent=1))
        z.writestr("summary.json", json.dumps(summary(), ensure_ascii=False, indent=1))
        p = os.path.join(DIR, "actions.jsonl")
        if os.path.exists(p):
            z.write(p, "actions.jsonl")
        from .expert import PATH as EXPERT_PATH
        if os.path.exists(EXPERT_PATH):
            z.write(EXPERT_PATH, "expert_notes.json")        # мнения экспертов по правилам
        for job in sorted(jobs):
            base = os.path.join(work_dir, os.path.basename(job))
            if job in reviewed:
                z.writestr(f"jobs/{job}/reviews.json", json.dumps(entries(job), ensure_ascii=False, indent=1))
            if not os.path.isdir(base):
                continue
            for name in ("report.json", "meta.json"):
                if os.path.exists(os.path.join(base, name)):
                    z.write(os.path.join(base, name), f"jobs/{job}/{name}")
            up = os.path.join(base, "uploads")
            if os.path.isdir(up):
                for root, _, files in os.walk(up):
                    for fn in files:
                        full = os.path.join(root, fn)
                        z.write(full, f"jobs/{job}/uploads/{os.path.relpath(full, up)}")
            for fn in os.listdir(base):
                if fn.lower().endswith((".xls", ".xlsx", ".xlsm")) and not fn.startswith("Отчёт"):
                    z.write(os.path.join(base, fn), f"jobs/{job}/{fn}")
    return buf.getvalue()


LEGACY_JOB = "legacy-exceptions"


def import_exceptions(rules: list[dict]) -> int:
    """Переносит отметки «не ошибка» из exceptions.json старой версии программы в отметки тестировщиков
    (verdict «ложное», ревизия 1, версия «legacy»). Повторный запуск не создаёт дублей. Возвращает число новых записей."""
    with _LOCK:
        data = entries(LEGACY_JOB)
        have = {e.get("legacy_id") for e in data}
        added = 0
        for r in rules:
            rid = r.get("id")
            if not rid or rid in have or not r.get("code"):
                continue
            where = "правило отключено везде" + (f" для замечаний с «{r['pattern']}»" if r.get("pattern") else "") \
                if r.get("scope") == "global" else "скрыто для чертежа"
            e = {"id": uuid.uuid4().hex[:10], "ts": r.get("created") or time.strftime("%Y-%m-%d %H:%M:%S"),
                 "user": "—", "job": LEGACY_JOB, "type": "finding", "verdict": "false", "code": r["code"],
                 "rev": 1, "app": "legacy", "legacy_id": rid,
                 "comment": "Перенесено из «не ошибка»: " + where + (f". {r['comment']}" if r.get("comment") else "")}
            for k in ("message", "designation", "file"):
                if r.get(k):
                    e[k] = r[k]
            data.append(e)
            added += 1
        if added:
            tmp = _path(LEGACY_JOB) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, _path(LEGACY_JOB))
    return added
