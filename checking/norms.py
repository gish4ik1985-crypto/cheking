"""Нормативы: PDF-тексты стандартов, на которых основаны правила. Для администраторов: просмотр, поиск по тексту,
выдержки к замечаниям.

Два каталога: «standards» в составе программы (обновляется вместе с ней) и «data/standards» — файлы, добавленные
администраторами (при обновлении программы не затрагиваются). Описания (название, обозначение) — в index.json каждого каталога."""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
from functools import lru_cache

from .config import DATA, RES

BUNDLED = os.path.join(RES, "standards")
USER = os.path.join(DATA, "standards")
_lock = threading.Lock()

_DESIG = re.compile(r"((?:ГОСТ|ОСТ)(?:\s*Р)?)\s*([\d]+(?:\.[\d]+)*)(?:\s*[-—–]\s*(\d{2,4}))?", re.I)


def _read_index(d: str) -> dict:
    try:
        with open(os.path.join(d, "index.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_index(d: str, data: dict) -> None:
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_designation(text: str) -> tuple[str, bool, str, str] | None:
    """(вид, национальный «Р», номер, год) из «ГОСТ Р 2.316-2023 п. 6.5»; год может быть пустым."""
    m = _DESIG.search(text or "")
    if not m:
        return None
    kind = "ОСТ" if m.group(1).upper().startswith("ОСТ") else "ГОСТ"
    return kind, bool(re.search(r"Р$", m.group(1), re.I)), m.group(2), (m.group(3) or "")[-2:]


def _clause(text: str) -> str | None:
    m = re.search(r"\bп(?:п)?\.?\s*(\d+(?:\.\d+)*)", text or "")
    return m.group(1) if m else None


@lru_cache(maxsize=64)
def _pages_text(path: str, mtime: float) -> tuple[str, ...]:
    import pymupdf
    with pymupdf.open(path) as d:
        return tuple(p.get_text() for p in d)


def pages_text(path: str) -> tuple[str, ...]:
    return _pages_text(path, os.path.getmtime(path))


def _norm_id(fn: str) -> str:
    return os.path.basename(fn)


_META_CACHE: dict[str, tuple] = {}


def _quick_meta(path: str) -> tuple[int, bool]:
    """(число страниц, есть ли текст) без чтения всего файла: по первым десяти страницам; результат помнится в памяти и в
    файле .meta.json рядом с PDF (ключ — размер и время изменения), поэтому список нормативов открывается быстро."""
    st = os.stat(path)
    key = f"{st.st_size}:{int(st.st_mtime)}"
    hit = _META_CACHE.get(path)
    if hit and hit[0] == key:
        return hit[1], hit[2]
    mp = os.path.join(os.path.dirname(path), ".meta.json")
    try:
        with open(mp, encoding="utf-8") as f:
            disk = json.load(f)
    except (OSError, ValueError):
        disk = {}
    ent = disk.get(os.path.basename(path))
    if ent and ent.get("k") == key:
        _META_CACHE[path] = (key, ent["pages"], ent["text"])
        return ent["pages"], ent["text"]
    try:
        import pymupdf
        with pymupdf.open(path) as d:
            n = len(d)
            chars = sum(len(d[i].get_text()) for i in range(min(n, 10)))
        has_text = chars >= 50 * min(n, 10)
    except Exception:
        n, has_text = 0, False
    _META_CACHE[path] = (key, n, has_text)
    disk[os.path.basename(path)] = {"k": key, "pages": n, "text": has_text}
    try:
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(disk, f, ensure_ascii=False)
    except OSError:
        pass
    return n, has_text


def listing() -> list[dict]:
    """Все нормативы: программа + добавленные администраторами (одноимённый файл администратора заменяет файл программы)."""
    items: dict[str, dict] = {}
    for source, d in (("program", BUNDLED), ("user", USER)):
        if not os.path.isdir(d):
            continue
        idx = _read_index(d)
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith(".pdf"):
                continue
            path = os.path.join(d, fn)
            meta = idx.get(fn, {})
            n_pages, has_text = _quick_meta(path)
            des = meta.get("designation") or os.path.splitext(fn)[0]
            items[fn] = {"id": fn, "title": meta.get("title") or "", "designation": des, "file": fn, "source": source,
                         "pages": n_pages, "size": os.path.getsize(path), "has_text": has_text, "path": path}
    return sorted(items.values(), key=lambda x: x["designation"])


def public(items: list[dict]) -> list[dict]:
    return [{k: v for k, v in it.items() if k != "path"} for it in items]


def get(norm_id: str) -> dict | None:
    fn = _norm_id(norm_id)
    return next((x for x in listing() if x["id"] == fn), None)


def add(filename: str, data: bytes, title: str = "", designation: str = "") -> dict:
    """Сохраняет PDF в каталог администраторов; название и обозначение — из полей или из имени файла."""
    fn = _norm_id(filename)
    if not fn.lower().endswith(".pdf"):
        raise ValueError("нужен файл PDF")
    if not data.startswith(b"%PDF"):
        raise ValueError("файл не похож на PDF")
    with _lock:
        os.makedirs(USER, exist_ok=True)
        with open(os.path.join(USER, fn), "wb") as f:
            f.write(data)
        idx = _read_index(USER)
        idx[fn] = {"title": title.strip(), "designation": designation.strip() or os.path.splitext(fn)[0]}
        _write_index(USER, idx)
    return get(fn)


def update(norm_id: str, title: str, designation: str) -> dict | None:
    it = get(norm_id)
    if not it or it["source"] != "user":
        return None
    with _lock:
        idx = _read_index(USER)
        idx[it["id"]] = {"title": title.strip(), "designation": designation.strip() or os.path.splitext(it["id"])[0]}
        _write_index(USER, idx)
    return get(norm_id)


def delete(norm_id: str) -> bool:
    """Удаляет только файлы, добавленные администраторами; файлы программы удалить нельзя."""
    fn = _norm_id(norm_id)
    path = os.path.join(USER, fn)
    if not os.path.isfile(path):
        return False
    with _lock:
        os.remove(path)
        idx = _read_index(USER)
        idx.pop(fn, None)
        _write_index(USER, idx)
    return True


def search(query: str, limit: int = 40) -> list[dict]:
    """Поиск фразы по тексту всех нормативов: [{id, designation, page, snippet}]."""
    q = re.sub(r"\s+", " ", (query or "").strip().lower())
    if len(q) < 3:
        return []
    out = []
    for it in listing():
        for n, text in enumerate(pages_text(it["path"]), 1):
            flat = re.sub(r"\s+", " ", text)
            i = flat.lower().find(q)
            while i != -1:
                out.append({"id": it["id"], "designation": it["designation"], "title": it["title"], "page": n,
                            "snippet": flat[max(0, i - 80): i + len(q) + 120].strip()})
                if len(out) >= limit:
                    return out
                i = flat.lower().find(q, i + len(q))
    return out


def page_text(norm_id: str, page: int) -> str | None:
    it = get(norm_id)
    if not it:
        return None
    pages = pages_text(it["path"])
    return pages[page - 1] if 1 <= page <= len(pages) else None


def _match_norm(des: tuple[str, bool, str, str]) -> dict | None:
    kind, nat, num, year = des
    cands = []
    for it in listing():
        d = parse_designation(it["designation"]) or parse_designation(it["id"])
        if d and d[0] == kind and d[2] == num and not (year and d[3] and year != d[3]):
            score = (d[1] == nat) * 2 + (bool(year) and d[3] == year)
            cands.append((score, it))
    return max(cands, key=lambda c: c[0])[1] if cands else None


def clause_page(path: str, clause: str) -> int | None:
    """Номер страницы, где с начала строки стоит пункт «6.5 …» (строки оглавления с многоточием пропускаются)."""
    rx = re.compile(rf"(?m)^\s*{re.escape(clause)}(?=[\s.)]|$)[^\n]*")
    for n, text in enumerate(pages_text(path), 1):
        for m in rx.finditer(text):
            if not re.search(r"\.{4,}|…", m.group(0)):
                return n
    return None


def lookup(std: str) -> dict | None:
    """Норматив и страница по ссылке вида «ГОСТ Р 2.316-2023 п. 6.5»: {id, designation, title, page, clause} или None."""
    des = parse_designation(std)
    if not des:
        return None
    it = _match_norm(des)
    if not it:
        return None
    clause = _clause(std)
    page = clause_page(it["path"], clause) if clause else None
    return {"id": it["id"], "designation": it["designation"], "title": it["title"], "page": page, "clause": clause}
