"""Учётные записи программы: users.json в корне (хэши паролей). При первом запуске создаётся администратор
admin / admin — пароль нужно сменить в «Профиле». Роли: admin (все отчёты, настройки, журнал) и user."""
from __future__ import annotations

import json
import os
import re
import threading
import time

from werkzeug.security import check_password_hash, generate_password_hash

from .config import DATA

PATH = os.path.join(DATA, "users.json")
_LOCK = threading.Lock()
NAME_RE = re.compile(r"^[\w .\-@А-Яа-яЁё]{2,40}$")
MIN_PASSWORD = 4


def _load() -> dict:
    if os.path.exists(PATH):
        try:
            with open(PATH, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data.get("users"), dict):
                return data
        except Exception:
            pass
    return {"users": {}}


def _save(data: dict) -> None:
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def ensure_default() -> None:
    with _LOCK:
        data = _load()
        if not any(u.get("role") == "admin" for u in data["users"].values()):
            data["users"]["admin"] = {"hash": generate_password_hash("admin"), "role": "admin",
                                      "created": time.strftime("%Y-%m-%d %H:%M"), "default_password": True}
            _save(data)


def _key(name: str) -> str:
    return (name or "").strip().lower()


def get(name: str) -> dict | None:
    u = _load()["users"].get(_key(name))
    return None if u is None else {"name": _key(name), "role": u.get("role", "user"),
                                   "default_password": bool(u.get("default_password")),
                                   "created": u.get("created", "")}


def verify(name: str, password: str) -> dict | None:
    u = _load()["users"].get(_key(name))
    if u and check_password_hash(u["hash"], password or ""):
        return get(name)
    return None


def listing() -> list[dict]:
    return [{"name": k, "role": v.get("role", "user"), "created": v.get("created", ""),
             "default_password": bool(v.get("default_password"))} for k, v in sorted(_load()["users"].items())]


def create(name: str, password: str, role: str = "user") -> str | None:
    """None — создано, иначе текст ошибки."""
    name = _key(name)
    if not NAME_RE.match(name):
        return "Имя: 2–40 символов (буквы, цифры, пробел, точка, дефис)"
    if len(password or "") < MIN_PASSWORD:
        return f"Пароль слишком короткий (минимум {MIN_PASSWORD} символа)"
    with _LOCK:
        data = _load()
        if name in data["users"]:
            return "Пользователь с таким именем уже есть"
        data["users"][name] = {"hash": generate_password_hash(password), "role": "admin" if role == "admin" else "user",
                               "created": time.strftime("%Y-%m-%d %H:%M")}
        _save(data)
    return None


def set_password(name: str, new: str) -> str | None:
    if len(new or "") < MIN_PASSWORD:
        return f"Пароль слишком короткий (минимум {MIN_PASSWORD} символа)"
    with _LOCK:
        data = _load()
        u = data["users"].get(_key(name))
        if u is None:
            return "Пользователь не найден"
        u["hash"] = generate_password_hash(new)
        u.pop("default_password", None)
        _save(data)
    return None


def set_role(name: str, role: str) -> str | None:
    with _LOCK:
        data = _load()
        u = data["users"].get(_key(name))
        if u is None:
            return "Пользователь не найден"
        if role != "admin" and u.get("role") == "admin" and sum(
                1 for x in data["users"].values() if x.get("role") == "admin") < 2:
            return "Нельзя снять права у последнего администратора"
        u["role"] = "admin" if role == "admin" else "user"
        _save(data)
    return None


def delete(name: str) -> str | None:
    with _LOCK:
        data = _load()
        u = data["users"].get(_key(name))
        if u is None:
            return "Пользователь не найден"
        if u.get("role") == "admin" and sum(1 for x in data["users"].values() if x.get("role") == "admin") < 2:
            return "Нельзя удалить последнего администратора"
        del data["users"][_key(name)]
        _save(data)
    return None
