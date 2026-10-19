"""Доступ к настройкам: пароль администратора (хэш) и ключ сессий хранятся в admin.json в корне программы.
Пока пароль не задан, настройки может менять любой пользователь программы."""
from __future__ import annotations

import json
import os
import secrets
import threading

from werkzeug.security import check_password_hash, generate_password_hash

from .config import DATA

PATH = os.path.join(DATA, "admin.json")
_LOCK = threading.Lock()


def _load(path: str | None = None) -> dict:
    path = path or PATH
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save(data: dict, path: str | None = None) -> None:
    path = path or PATH
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def secret_key(path: str | None = None) -> str:
    with _LOCK:
        data = _load(path)
        if not data.get("secret_key"):
            data["secret_key"] = secrets.token_hex(32)
            _save(data, path)
        return data["secret_key"]


def password_set(path: str | None = None) -> bool:
    return bool(_load(path).get("password_hash"))


def check_password(password: str, path: str | None = None) -> bool:
    h = _load(path).get("password_hash")
    return bool(h) and check_password_hash(h, password or "")


def set_password(new: str | None, path: str | None = None) -> None:
    """new=None/"" — снять пароль."""
    with _LOCK:
        data = _load(path)
        if new:
            data["password_hash"] = generate_password_hash(new)
        else:
            data.pop("password_hash", None)
        _save(data, path)
