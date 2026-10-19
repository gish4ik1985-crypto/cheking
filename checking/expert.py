"""Мнения экспертов по правилам (feedback/expert_notes.json).

Эксперт в «Настройки → Проверки по стандартам → i» пишет, что и как должна проверять проверка и как на неё реагировать.
Разработчик разбирает мнения по списку (python tools/expert_notes.py), перепроверяет их по стандарту и коду, при
необходимости меняет правило и отвечает на мнение: статус и комментарий видны эксперту под его записью.

Статусы: new — не разобрано; accepted — принято, правило будет изменено; rejected — отклонено (с причиной);
applied — правило изменено (указана ревизия правила после изменения)."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

from .config import DATA

PATH = os.path.join(DATA, "feedback", "expert_notes.json")
REVIEWS_PATH = os.path.join(DATA, "feedback", "rule_reviews.json")
_LOCK = threading.Lock()
STATUSES = {"new": "Не разобрано", "accepted": "Принято, будет учтено", "rejected": "Отклонено", "applied": "Учтено"}
MAX_LEN = 4000


def _load(path: str | None = None) -> list[dict]:
    path = path or PATH
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("notes", [])
    except Exception:
        return []


def _save(notes: list[dict], path: str | None = None) -> None:
    path = path or PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def listing(code: str | None = None, status: str | None = None, path: str | None = None) -> list[dict]:
    return [n for n in _load(path) if (not code or n["code"] == code) and (not status or n.get("status") == status)]


def by_rule(path: str | None = None) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for n in _load(path):
        out.setdefault(n["code"], []).append(n)
    for lst in out.values():
        lst.sort(key=lambda n: n["ts"], reverse=True)
    return out


def add(code: str, text: str, user: str, rev: int = 1, app: str = "", path: str | None = None) -> dict | str:
    """Возвращает запись или текст ошибки."""
    text = (text or "").strip()
    if not code:
        return "Не указан код правила"
    if not text:
        return "Напишите, что и как должно проверяться"
    if len(text) > MAX_LEN:
        return f"Слишком длинное мнение (не более {MAX_LEN} знаков)"
    note = {"id": uuid.uuid4().hex[:10], "code": code, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "user": user,
            "rev": rev, "app": app, "text": text, "status": "new"}
    with _LOCK:
        notes = _load(path)
        notes.append(note)
        _save(notes, path)
    if path is None and code in reviews():
        set_review(code, False, user)                      # новое мнение — правило снова обсуждается
    return note


def delete(note_id: str, user: str, is_admin: bool, path: str | None = None) -> bool:
    """Удалить можно только неразобранное мнение (автор или администратор)."""
    with _LOCK:
        notes = _load(path)
        keep = [n for n in notes if not (n["id"] == note_id and n.get("status") == "new"
                                         and (is_admin or n["user"] == user))]
        if len(keep) == len(notes):
            return False
        _save(keep, path)
    return True


def reply(note_id: str, status: str, comment: str, rev_after: int | None = None, path: str | None = None) -> dict | str:
    """Ответ разработчика на мнение: статус, комментарий (что проверено и что сделано), ревизия правила после правки."""
    if status not in STATUSES or status == "new":
        return "Статус: accepted, rejected или applied"
    if not (comment or "").strip():
        return "Напишите комментарий: что проверено и что сделано"
    with _LOCK:
        notes = _load(path)
        n = next((x for x in notes if x["id"] == note_id), None)
        if n is None:
            return "Мнение не найдено"
        n["status"] = status
        n["dev"] = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "comment": comment.strip()}
        if rev_after:
            n["dev"]["rev_after"] = rev_after
        _save(notes, path)
        return n


# ---- отметки «правило утверждено» (общие для всех администраторов) --------------------------------------
def reviews(path: str | None = None) -> dict[str, dict]:
    """код правила → {"user", "ts", "rev"}: кто и когда отметил правило как утверждённое и согласованное."""
    path = path or REVIEWS_PATH
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def set_review(code: str, reviewed: bool, user: str, rev: int = 1, path: str | None = None) -> dict | None:
    """Поставить или снять отметку; возвращает запись отметки (или None, если снята)."""
    path = path or REVIEWS_PATH
    with _LOCK:
        data = reviews(path)
        if reviewed:
            data[code] = {"user": user, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "rev": rev}
        else:
            data.pop(code, None)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return data.get(code)
