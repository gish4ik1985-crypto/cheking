"""Веб-интерфейс проверки чертежей.  Запуск: run.bat  (или  .venv\\Scripts\\python app.py)"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
import uuid
import webbrowser
import zipfile

from urllib.parse import quote

from flask import (Flask, Response, abort, jsonify, redirect, render_template, request, send_file,
                   send_from_directory, session)

from checking import admin, catalog, custom, equipment, expert, feedback, users
from checking.config import DEFAULTS, load_config, save_config, write_default_config
from checking import norms, stdclauses, stdreg
from checking.normdata import OBSOLETE_STANDARDS
from checking.completeness import completeness
from checking.engine import SUPPORTED, check_file, check_job, collect_dxf, collect_files
from checking.exceptions import add_rule, apply_to_dict, delete_rule, load_rules
from checking.remarks import build_docx
from checking.report import drawing_to_dict, save_excel
from checking.dxf import DxfIndex
from checking.process import PROCESS_EXT, check_process_file, link_to_drawings
from checking.spec import ItemSpec, Spec
from checking.textnorm import nfc

from checking.config import ROOT, RES, DATA, backup_data
WORK = os.path.join(DATA, "work")
PORT = int(os.environ.get("CHECKING_PORT", "8765"))
HOST = os.environ.get("CHECKING_HOST", "127.0.0.1")
API_TOKEN = os.environ.get("CHECKING_API_TOKEN", "")

app = Flask(__name__, template_folder=os.path.join(RES, "web", "templates"),
            static_folder=os.path.join(RES, "web", "static"))
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 ** 3
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0      # стили и скрипты не кэшировать — обновления видны сразу
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.secret_key = admin.secret_key()

# Интерфейс — одностраничное приложение (React + shadcn/ui), собранное в frontend/dist (npm run build в папке frontend).
# Если сборки нет, работают прежние страницы из web/templates.
UI_DIST = os.path.join(RES, "frontend", "dist")


def _spa():
    """index.html нового интерфейса или None, если интерфейс не собран."""
    idx = os.path.join(UI_DIST, "index.html")
    if not os.path.isfile(idx):
        return None
    resp = send_file(idx, mimetype="text/html", max_age=0)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/favicon.svg")
def ui_favicon():
    return send_from_directory(UI_DIST, "favicon.svg", max_age=86400)


@app.get("/assets/<path:sub>")
def ui_assets(sub):
    return send_from_directory(os.path.join(UI_DIST, "assets"), sub, max_age=31536000)
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()


def _safe_name(name: str) -> str:
    name = nfc(os.path.basename(name.replace("\\", "/")))
    return "".join(c for c in name if c not in '<>:"|?*').strip() or "file"


class _Seen:
    """Одинаковые по содержимому файлы одной проверки принимаются один раз: повторный экземпляр пропускается."""

    def __init__(self):
        self.by_hash: dict[str, tuple[str, str]] = {}

    def duplicate_of(self, path: str, shown: str) -> tuple[str, str] | None:
        """(имя, путь) уже принятого файла с тем же содержимым или None (тогда файл запоминается)."""
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        key = f"{os.path.getsize(path)}:{h.hexdigest()}"
        first = self.by_hash.get(key)
        if first is None:
            self.by_hash[key] = (shown, path)
        return first


def _unzip(path: str, dest: str) -> list[str]:
    out = []
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir() or "__MACOSX" in info.filename:
                continue
            raw = info.filename
            if not info.flag_bits & 0x800:          # имена в cp866 (архиваторы Windows)
                try:
                    raw = raw.encode("cp437").decode("cp866")
                except UnicodeError:
                    pass
            name = _safe_name(raw)
            if os.path.splitext(name)[1].lower() not in SUPPORTED | {".dxf"}:
                continue
            target = os.path.join(dest, name)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            out.append(target)
    return out


def _run_job(job_id: str, files: list[tuple[str, str]], spec_path: str | None, use_ocr: bool,
             dxf_paths: list[str] | None = None, process_files: list[tuple[str, str]] | None = None,
             spec_docs: list[str] | None = None):
    job = JOBS[job_id]
    jdir = os.path.join(WORK, job_id)
    try:
        cfg = load_config()
        cfg["ocr"] = use_ocr
        cfg["_force_spec"] = {os.path.abspath(p) for p in spec_docs or []} | set(spec_docs or [])
        dxf_index = DxfIndex(dxf_paths or [])
        if len(dxf_index):
            job["dxf"] = len(dxf_index)
        for p, err in dxf_index.errors.items():
            job["warnings"].append(f"DXF не прочитан: {os.path.basename(p)} — {err}")
        spec = None
        if spec_path:
            try:
                spec = Spec(spec_path)
                job["spec"] = {"name": os.path.basename(spec_path), "items": len(spec)}
            except Exception as e:
                job["warnings"].append(f"Спецификация не прочитана: {e}")
        drawings = []
        for i, (path, shown) in enumerate(files):
            job["current"] = shown
            img_dir = os.path.join(jdir, "img", str(i))
            for d in check_file(path, cfg, spec, img_dir=img_dir, display_name=shown, dxf_index=dxf_index,
                                apply_profile=False):
                drawings.append(d)
                dd = drawing_to_dict(d)
                for p in dd["pages"]:
                    if p.get("image"):
                        p["image"] = "/work/" + job_id + "/" + os.path.relpath(p["image"], jdir).replace("\\", "/")
                dd["id"] = len(job["results"])
                job["results"].append(dd)
            job["done"] = i + 1
        for j, (path, shown) in enumerate(process_files or []):        # маршрутные карты и технологические процессы
            job["current"] = shown
            d = check_process_file(path, cfg, os.path.join(jdir, "img", f"p{j}"), shown)
            drawings.append(d)
            dd = drawing_to_dict(d)
            for p in dd["pages"]:
                if p.get("image"):
                    p["image"] = "/work/" + job_id + "/" + os.path.relpath(p["image"], jdir).replace("\\", "/")
            dd["id"] = len(job["results"])
            job["results"].append(dd)
            job["done"] = len(files) + j + 1
        changed = check_job(drawings, cfg, spec, apply_profile=False)     # сверка документов между собой
        link_to_drawings(drawings)
        for i, d in enumerate(drawings):
            job["results"][i]["facts"]["mass_parts"] = d.facts.get("mass_parts")
            if d.facts.get("process"):
                job["results"][i]["facts"]["process"] = d.facts["process"]
            if i in changed:
                job["results"][i]["findings"] = [f.to_dict() for f in d.findings]
                job["results"][i]["counts"] = d.counts
        if spec is not None:                        # сама спецификация — отдельный документ отчёта (ГОСТ 2.106)
            try:
                from checking.specdoc import check_spec_document
                sd = drawing_to_dict(check_spec_document(spec, cfg))
                sd["id"] = len(job["results"])
                job["results"].append(sd)
            except Exception as e:
                job["warnings"].append(f"Спецификация не проверена по ГОСТ 2.106: {e}")
        with open(os.path.join(jdir, "report.json"), "w", encoding="utf-8") as f:
            json.dump(job["results"], f, ensure_ascii=False, default=str)
        with open(os.path.join(jdir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({"spec_path": spec_path, "spec": job.get("spec"), "warnings": job["warnings"],
                       "dxf": job.get("dxf"), "owner": job.get("owner"), "started": job.get("started")},
                      f, ensure_ascii=False)
        job["state"] = "done"
    except Exception as e:
        job["state"] = "error"
        job["error"] = f"{e}\n{traceback.format_exc()}"
    finally:
        job["finished"] = time.time()


@app.get("/")
def index():
    return _spa() or render_template("index.html")


@app.post("/api/jobs")
def create_job():
    job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    jdir = os.path.join(WORK, job_id)
    up = os.path.join(jdir, "uploads")
    os.makedirs(up, exist_ok=True)
    files: list[tuple[str, str]] = []
    dxf_paths: list[str] = []
    warnings: list[str] = []
    seen = _Seen()

    def fresh(path: str, shown: str, remove: bool = True) -> bool:
        """False — такой файл (по содержимому) уже принят: дубликат пропускается и убирается из загрузки."""
        first = seen.duplicate_of(path, shown)
        if first is None:
            return True
        warnings.append(f"Пропущен дубликат «{shown}»: такой же файл уже загружен («{first[0]}»)")
        if remove:
            try:
                os.remove(path)
            except OSError:
                pass
        return False

    for fs in request.files.getlist("files"):
        if not fs.filename:
            continue
        name = _safe_name(fs.filename)
        target = os.path.join(up, name)
        stem, ext = os.path.splitext(name)
        k = 2
        while os.path.exists(target):
            name = f"{stem} ({k}){ext}"
            target = os.path.join(up, name)
            k += 1
        fs.save(target)
        if name.lower().endswith(".zip"):
            for p in _unzip(target, up):
                if not fresh(p, os.path.basename(p)):
                    continue
                if p.lower().endswith(".dxf"):
                    dxf_paths.append(p)
                else:
                    files.append((p, os.path.basename(p)))
        elif name.lower().endswith(".dxf"):
            if fresh(target, name):
                dxf_paths.append(target)
        elif os.path.splitext(name)[1].lower() in SUPPORTED:
            if fresh(target, name):
                files.append((target, name))
    folder = (request.form.get("folder") or "").strip().strip('"')
    if folder:
        if not os.path.isdir(folder):
            return jsonify(error=f"Папка не найдена: {folder}"), 400
        for p in collect_files([folder]):
            if fresh(p, os.path.relpath(p, folder), remove=False):      # файлы папки не трогаем
                files.append((p, os.path.relpath(p, folder)))
        dxf_paths += [p for p in collect_dxf([folder]) if fresh(p, os.path.relpath(p, folder), remove=False)]
    spec_path, spec_docs = None, []
    for sf in request.files.getlist("spec"):                   # Excel (ERP) и спецификации КОМПАС (PDF/SPW)
        if not sf.filename:
            continue
        name = _safe_name(sf.filename)
        ext = os.path.splitext(name)[1].lower()
        if ext in (".xlsx", ".xlsm", ".xls"):
            if spec_path:
                warnings.append(f"Excel-спецификация «{name}» пропущена: в проверке используется одна — "
                                f"«{os.path.basename(spec_path)}»")
                continue
            spec_path = os.path.join(jdir, name)
            sf.save(spec_path)
            if not fresh(spec_path, name):
                spec_path = None
        elif ext == ".pdf":
            target = os.path.join(up, name)
            k, stem = 2, os.path.splitext(name)[0]
            while os.path.exists(target):
                target = os.path.join(up, f"{stem} ({k}){ext}")
                k += 1
            sf.save(target)
            dup = seen.duplicate_of(target, os.path.basename(target))
            if dup is None:
                files.append((target, os.path.basename(target)))
                spec_docs.append(target)
            else:                                    # та же спецификация уже есть среди загруженных файлов
                os.remove(target)
                if dup[1] not in spec_docs and any(p == dup[1] for p, _ in files):
                    spec_docs.append(dup[1])
                warnings.append(f"Спецификация «{name}» уже загружена («{dup[0]}») — повторно не добавлена")
        else:
            warnings.append(f"Спецификация «{name}» пропущена: нужен Excel (xlsx/xls) или PDF по форме 1 ГОСТ 2.106")
    process_files: list[tuple[str, str]] = []
    pdir = os.path.join(up, "process")
    for pf in request.files.getlist("process"):               # маршрутные карты и технологические процессы
        if not pf.filename:
            continue
        name = _safe_name(pf.filename)
        if os.path.splitext(name)[1].lower() not in PROCESS_EXT:
            warnings.append(f"Документ технологии «{name}» пропущен: форматы PDF, Excel (xlsx/xls), Word (docx)")
            continue
        os.makedirs(pdir, exist_ok=True)
        target = os.path.join(pdir, name)
        k, stem, ext = 2, os.path.splitext(name)[0], os.path.splitext(name)[1]
        while os.path.exists(target):
            target = os.path.join(pdir, f"{stem} ({k}){ext}")
            k += 1
        pf.save(target)
        if fresh(target, os.path.basename(target)):
            process_files.append((target, os.path.basename(target)))
    if not files and not process_files:
        return jsonify(error="Не выбрано ни одного документа (чертежи: PDF, CDW, DFT, PNG/JPG/TIF или ZIP; "
                             "спецификации; маршрутные карты)"), 400
    use_ocr = request.form.get("ocr", "1") == "1"
    JOBS[job_id] = {"id": job_id, "state": "running", "total": len(files) + len(process_files), "done": 0, "current": "",
                    "results": [], "warnings": warnings, "spec": None, "started": time.time(), "owner": _user()["name"]}
    feedback.log(_user()["name"], "Новая проверка", {"job": job_id, "files": len(files), "process": len(process_files),
                                                      "names": [n for _, n in files][:20]})
    threading.Thread(target=_run_job, args=(job_id, files, spec_path, use_ocr, dxf_paths, process_files, spec_docs),
                     daemon=True).start()
    return jsonify(job_id=job_id)


def _job(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if job is None:
        path = os.path.join(WORK, job_id, "report.json")
        if not os.path.exists(path):
            abort(404)
        with open(path, encoding="utf-8") as f:
            results = json.load(f)
        meta = {}
        mp = os.path.join(WORK, job_id, "meta.json")
        if os.path.exists(mp):
            with open(mp, encoding="utf-8") as f:
                meta = json.load(f)
        job = {"id": job_id, "state": "done", "total": len(results), "done": len(results), "current": "",
               "results": results, "warnings": meta.get("warnings", []), "spec": meta.get("spec"),
               "dxf": meta.get("dxf"), "owner": meta.get("owner"), "started": meta.get("started")}
        JOBS[job_id] = job
    u = _user()
    if u and u["role"] != "admin" and job.get("owner") != u["name"]:
        abort(403)                        # чужие отчёты видит только администратор
    return job


def _view(job: dict) -> tuple[list[dict], dict | None]:
    """Результаты с учётом настроек правил (/admin), исключений «не ошибка» и комплектность по спецификации."""
    rules = load_rules()
    cfg = load_config()
    results = [apply_to_dict(catalog.apply_to_dict(custom.apply_to_dict(d, cfg), cfg), rules) for d in job["results"]]
    comp = None
    if job.get("state") == "done":
        mp = os.path.join(WORK, job["id"], "meta.json")
        if os.path.exists(mp):
            with open(mp, encoding="utf-8") as f:
                sp = json.load(f).get("spec_path")
            if sp and os.path.exists(sp):
                try:
                    comp = completeness(Spec(sp), results)
                except Exception:
                    comp = None
    return results, comp


@app.get("/api/jobs/<job_id>")
def job_status(job_id):
    job = _job(job_id)
    full = request.args.get("full") == "1"
    out = {k: v for k, v in job.items() if k != "results"}
    if full:
        out["results"], out["completeness"] = _view(job)
    else:
        out["ready"] = len(job["results"])
    return jsonify(out)


@app.get("/job/<job_id>")
def job_page(job_id):
    job = _job(job_id)
    feedback.log(_user()["name"], "Открыт отчёт", {"job": job_id, "owner": job.get("owner")})
    return _spa() or render_template("report.html", job_id=job_id)


@app.get("/api/jobs/<job_id>/excel")
def job_excel(job_id):
    job = _job(job_id)
    results, comp = _view(job)
    feedback.log(_user()["name"], "Выгружен Excel", {"job": job_id})
    path = save_excel(results, os.path.join(WORK, job_id, "Отчёт проверки чертежей.xlsx"), comp)
    return send_file(path, as_attachment=True, download_name=f"Проверка чертежей {job_id[:15]}.xlsx")


@app.get("/api/jobs/<job_id>/remarks.docx")
def job_remarks(job_id):
    """Перечень замечаний (Word): весь пакет или один документ (?doc=N); ?info=1 — с замечаниями-информацией."""
    job = _job(job_id)
    results, _ = _view(job)
    doc = request.args.get("doc")
    if doc is not None:
        results = [d for d in results if str(d.get("id")) == doc]
        if not results:
            abort(404)
    name = (results[0]["title"]["designation"] or results[0]["file"]) if doc is not None else job_id[:15]
    path = os.path.join(WORK, job_id, f"remarks_{doc or 'all'}.docx")
    build_docx(results, path, include_info=request.args.get("info") == "1")
    return send_file(path, as_attachment=True, download_name=f"Замечания {_safe_name(name)}.docx")


@app.get("/api/exceptions")
def exceptions_list():
    return jsonify(load_rules())


@app.post("/api/exceptions")
def exceptions_add():
    _need_admin()
    data = request.get_json(force=True) or {}
    if data.get("scope") not in ("drawing", "global") or not data.get("code"):
        return jsonify(error="scope (drawing|global) и code обязательны"), 400
    rule = {k: data.get(k) for k in ("scope", "code", "message", "designation", "file", "pattern", "comment")}
    feedback.log(_user()["name"], "Замечание отмечено «не ошибка»", {k: rule[k] for k in ("scope", "code", "designation")})
    return jsonify(add_rule(rule))


@app.delete("/api/exceptions/<rule_id>")
def exceptions_delete(rule_id):
    _need_admin()
    return jsonify(deleted=delete_rule(rule_id))


# ------------------------------------------------------------------ вход, профиль, пользователи ----
PUBLIC_PREFIXES = ("/login", "/api/login", "/static/", "/assets/", "/favicon.svg", "/api/v1/")


def _user() -> dict | None:
    """Текущий пользователь (проверяется по users.json — удалённый пользователь теряет доступ сразу)."""
    name = session.get("user")
    return users.get(name) if name else None


@app.before_request
def _gate():
    p = request.path
    if p.startswith(PUBLIC_PREFIXES):
        return None
    if _user():
        return None
    session.pop("user", None)
    if p.startswith(("/api/", "/work/")):
        return jsonify(error="Требуется вход"), 401
    return redirect("/login?next=" + quote(request.full_path.rstrip("?"), safe="/"))


@app.get("/login")
def login_page():
    return _spa() or render_template("login.html")


@app.post("/api/login")
def api_login():
    users.ensure_default()
    data = request.get_json(force=True) or {}
    u = users.verify(data.get("name", ""), data.get("password", ""))
    if not u:
        feedback.log(None, "Неудачный вход", {"name": (data.get("name") or "")[:40]})
        return jsonify(error="Неверное имя или пароль"), 403
    session["user"] = u["name"]
    session.permanent = True
    feedback.log(u["name"], "Вход")
    return jsonify(ok=True, user=u)


@app.post("/api/logout")
def api_logout():
    u = _user()
    if u:
        feedback.log(u["name"], "Выход")
    session.pop("user", None)
    return jsonify(ok=True)


@app.get("/api/me")
def api_me():
    from checking.version import APP_VERSION
    u = _user()
    return jsonify({**u, "version": APP_VERSION} if u else u)


@app.get("/profile")
def profile_page():
    return _spa() or render_template("profile.html")


@app.post("/api/profile/password")
def profile_password():
    u = _user()
    data = request.get_json(force=True) or {}
    if not users.verify(u["name"], data.get("old", "")):
        return jsonify(error="Текущий пароль указан неверно"), 403
    err = users.set_password(u["name"], data.get("new", ""))
    if err:
        return jsonify(error=err), 400
    feedback.log(u["name"], "Смена пароля")
    return jsonify(ok=True)


@app.get("/api/profile/activity")
def profile_activity():
    u = _user()
    who = request.args.get("user") if _is_admin() else u["name"]
    return jsonify(feedback.actions(who or None, 300))


# ------------------------------------------------------------------ профиль оборудования ----
@app.get("/api/admin/equipment")
def equipment_get():
    _need_admin()
    return jsonify(equipment.api_view(load_config()))


@app.post("/api/admin/equipment")
def equipment_save():
    _need_admin()
    data = request.get_json(force=True) or {}
    items = equipment.clean_items(data.get("items"))
    if not items:
        return jsonify(error="Список оборудования пуст"), 400
    save_config({"equipment": {"items": items}})
    feedback.log(_user()["name"], "Сохранён профиль оборудования", {"станков": len(items)})
    return jsonify(equipment.api_view(load_config()))


@app.post("/api/admin/equipment/preview")
def equipment_preview():
    """Как программа разберёт новую запись (вид и параметры по обозначению модели) — без сохранения."""
    _need_admin()
    data = request.get_json(force=True) or {}
    return jsonify(items=equipment.clean_items(data.get("items")))


@app.post("/api/admin/equipment/reset")
def equipment_reset():
    """Вернуть перечень из ERP (встроенный снимок)."""
    _need_admin()
    save_config({"equipment": {"items": None}})
    feedback.log(_user()["name"], "Профиль оборудования сброшен к перечню ERP")
    return jsonify(equipment.api_view(load_config()))


@app.get("/api/admin/users")
def admin_users():
    _need_admin()
    return jsonify(users.listing())


@app.post("/api/admin/users")
def admin_user_create():
    _need_admin()
    data = request.get_json(force=True) or {}
    err = users.create(data.get("name", ""), data.get("password", ""), data.get("role", "user"))
    if err:
        return jsonify(error=err), 400
    feedback.log(_user()["name"], "Создан пользователь", {"name": data.get("name"), "role": data.get("role", "user")})
    return jsonify(users.listing())


@app.patch("/api/admin/users/<name>")
def admin_user_update(name):
    _need_admin()
    data = request.get_json(force=True) or {}
    err = None
    if data.get("password"):
        err = users.set_password(name, data["password"])
        feedback.log(_user()["name"], "Сброшен пароль пользователя", {"name": name})
    if not err and data.get("role"):
        err = users.set_role(name, data["role"])
        feedback.log(_user()["name"], "Изменена роль", {"name": name, "role": data["role"]})
    if err:
        return jsonify(error=err), 400
    return jsonify(users.listing())


@app.delete("/api/admin/users/<name>")
def admin_user_delete(name):
    _need_admin()
    if name.lower() == _user()["name"]:
        return jsonify(error="Нельзя удалить самого себя"), 400
    err = users.delete(name)
    if err:
        return jsonify(error=err), 400
    feedback.log(_user()["name"], "Удалён пользователь", {"name": name})
    return jsonify(users.listing())


@app.get("/api/admin/actions")
def admin_actions():
    _need_admin()
    return jsonify(feedback.actions(request.args.get("user") or None, 1000))


@app.get("/api/admin/feedback")
def admin_feedback():
    _need_admin()
    return jsonify(feedback.summary())


@app.get("/api/admin/expert-notes")
def expert_notes_list():
    _need_admin()
    return jsonify(notes=expert.by_rule(), statuses=expert.STATUSES, reviews=expert.reviews())


@app.post("/api/admin/rule-review")
def rule_review():
    """Отметка «правило утверждено» — общая для всех администраторов; снять может любой из них."""
    _need_admin()
    data = request.get_json(force=True) or {}
    code = (data.get("code") or "").strip()
    if code not in {r[0] for r in catalog.all_rules(load_config())}:
        return jsonify(error="Такого правила нет"), 400
    from checking.rule_docs import rev_of
    u = _user()
    on = bool(data.get("reviewed"))
    rec = expert.set_review(code, on, u["name"], rev_of(code))
    feedback.log(u["name"], "Правило отмечено как утверждённое" if on else "Отметка «утверждено» снята", {"code": code})
    return jsonify(code=code, review=rec)


@app.post("/api/admin/expert-notes")
def expert_notes_add():
    _need_admin()
    data = request.get_json(force=True) or {}
    code = (data.get("code") or "").strip()
    if code not in {r[0] for r in catalog.all_rules(load_config())}:
        return jsonify(error="Такого правила нет"), 400
    from checking.rule_docs import rev_of
    from checking.version import APP_VERSION
    u = _user()
    n = expert.add(code, data.get("text"), u["name"], rev_of(code), APP_VERSION)
    if isinstance(n, str):
        return jsonify(error=n), 400
    feedback.log(u["name"], "Мнение эксперта по правилу", {"code": code, "text": n["text"][:200]})
    return jsonify(n)


@app.delete("/api/admin/expert-notes/<note_id>")
def expert_notes_delete(note_id):
    _need_admin()
    u = _user()
    if not expert.delete(note_id, u["name"], _is_admin()):
        return jsonify(error="Удалить можно только неразобранное мнение"), 400
    return jsonify(ok=True)


@app.get("/api/admin/export.zip")
def admin_export():
    _need_admin()
    data = feedback.export_zip(WORK, users.listing(), request.args.get("all") == "1")
    feedback.log(_user()["name"], "Выгрузка для разработки", {"bytes": len(data)})
    return Response(data, mimetype="application/zip", headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote("Выгрузка проверки чертежей "
                                                                       + time.strftime("%Y-%m-%d %H%M") + ".zip")})


# ------------------------------------------------------------------ отметки тестировщика ----
@app.get("/api/jobs/<job_id>/feedback")
def job_feedback(job_id):
    _job(job_id)
    u = _user()
    return jsonify(feedback.entries(job_id, None if _is_admin() else u["name"]))


@app.post("/api/jobs/<job_id>/feedback")
def job_feedback_add(job_id):
    _job(job_id)
    data = request.get_json(force=True) or {}
    u = _user()
    if data.get("type") == "comment" and not _is_admin():
        abort(403)                                   # комментарии к замечаниям — только администратор
    e = feedback.add(job_id, u["name"], data)
    if isinstance(e, str):
        return jsonify(error=e), 400
    feedback.log(u["name"], {"finding": "Отметка замечания", "missed": "Отмечен пропуск", "parse": "Ошибка разбора",
                             "comment": "Комментарий к замечанию"}[e["type"]],
                 {k: e.get(k) for k in ("job", "designation", "code", "verdict", "group", "comment") if e.get(k)})
    return jsonify(e)


@app.delete("/api/jobs/<job_id>/feedback/<fid>")
def job_feedback_delete(job_id, fid):
    _job(job_id)
    u = _user()
    if not feedback.remove(job_id, u["name"], fid, _is_admin()):
        abort(404)
    feedback.log(u["name"], "Удалена отметка", {"job": job_id, "id": fid})
    return jsonify(ok=True)


@app.get("/api/feedback/meta")
def feedback_meta():
    return jsonify(groups=feedback.GROUPS)


# ------------------------------------------------------------------ настройки (администратор) ----
PARAM_KEYS = ("mass", "laser", "tight_it", "coarse_it", "thread_min_turns", "hardness_min_range_hrc", "ocr")
LIST_KEYS = ("org_codes", "general_tolerance_refs", "obsolete_standards")


def _is_admin() -> bool:
    u = _user()
    return bool(u and u["role"] == "admin")


def _need_admin():
    if not _user():
        abort(401)
    if not _is_admin():
        abort(403)


# ------------------------------------------------------------------ нормативы (PDF стандартов) ----
@app.get("/api/admin/standards/detail")
def standards_detail():
    """Пункты загруженного стандарта: какие проверки на них ссылаются, отметки администратора."""
    _need_admin()
    d = stdclauses.detail(load_config(), request.args.get("id", ""))
    if not d:
        return jsonify(error="Файл не найден"), 404
    return jsonify(d)


@app.get("/api/admin/standards/marks")
def standards_marks():
    _need_admin()
    st = request.args.get("status")
    return jsonify([m for m in stdclauses.load_marks() if not st or m["status"] == st])


@app.post("/api/admin/standards/marks")
def standards_mark_add():
    """Отметка пункта стандарта: по нему нужно сделать проверку (заявка на правило)."""
    _need_admin()
    data = request.get_json(force=True) or {}
    it = norms.get(data.get("file_id", ""))
    if not it:
        return jsonify(error="Файл стандарта не найден"), 404
    try:
        m = stdclauses.add_mark(_user()["name"], it["id"], it["designation"], str(data.get("clause", "")), data.get("text", ""), data.get("comment", ""))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    feedback.log(_user()["name"], "Отмечен пункт стандарта", {"std": it["designation"], "clause": m["clause"]})
    return jsonify(m)


@app.patch("/api/admin/standards/marks/<mark_id>")
def standards_mark_update(mark_id):
    _need_admin()
    data = request.get_json(force=True) or {}
    m = stdclauses.update_mark(mark_id, data.get("status"), data.get("comment"), data.get("code"))
    if not m:
        return jsonify(error="Отметка не найдена"), 404
    return jsonify(m)


@app.delete("/api/admin/standards/marks/<mark_id>")
def standards_mark_delete(mark_id):
    _need_admin()
    if not stdclauses.delete_mark(mark_id):
        return jsonify(error="Отметка не найдена"), 404
    return jsonify(deleted=True)


@app.get("/api/admin/standards/registry")
def standards_registry():
    _need_admin()
    return jsonify(stdreg.build(load_config()))


@app.post("/api/admin/standards/upload")
def standards_upload():
    """Несколько PDF сразу; обозначение — из имени файла или первой страницы (для одного файла можно передать в форме)."""
    _need_admin()
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        return jsonify(error="Не переданы файлы PDF"), 400
    forced = request.form.get("designation", "").strip()
    titles = {stdreg._key(e["designation"]): e["title"] for e in stdreg.ENTRIES}
    out = []
    for fs in files:
        name = _safe_name(fs.filename)
        data = fs.read()
        try:
            first = ""
            if data.startswith(b"%PDF"):
                try:
                    import pymupdf
                    with pymupdf.open(stream=data, filetype="pdf") as d:
                        first = d[0].get_text() if len(d) else ""
                except Exception:
                    first = ""
            des = forced if (forced and len(files) == 1) else stdreg.detect_designation(name, first)
            title = titles.get(stdreg._key(des), "") if des else ""
            it = norms.add(name, data, title, des)
            fixed, why = stdreg.reconcile(it["path"], it["designation"])          # обозначение из текста важнее имени файла
            if why and fixed != it["designation"]:
                it = norms.update(it["id"], it["title"], fixed) or it
            out.append({"file": name, "ok": True, "designation": it["designation"], "recognized": bool(des), "title": it["title"],
                        "corrected": why, "check": stdreg.verify(it["path"], it["designation"], it["title"])})
            feedback.log(_user()["name"], "Добавлен норматив", {"file": it["id"]})
        except ValueError as e:
            out.append({"file": name, "ok": False, "error": str(e)})
    return jsonify(results=out)


@app.get("/api/admin/norms")
def norms_list():
    _need_admin()
    return jsonify(norms.public(norms.listing()))


@app.post("/api/admin/norms")
def norms_add():
    _need_admin()
    fs = request.files.get("file")
    if not fs or not fs.filename:
        return jsonify(error="Не передан файл PDF"), 400
    try:
        it = norms.add(_safe_name(fs.filename), fs.read(), request.form.get("title", ""), request.form.get("designation", ""))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    feedback.log(_user()["name"], "Добавлен норматив", {"file": it["id"]})
    return jsonify({k: v for k, v in it.items() if k != "path"})


@app.patch("/api/admin/norms/<path:norm_id>")
def norms_update(norm_id):
    _need_admin()
    data = request.get_json(force=True) or {}
    it = norms.update(norm_id, data.get("title", ""), data.get("designation", ""))
    if not it:
        return jsonify(error="Менять можно только добавленные администраторами файлы"), 400
    return jsonify({k: v for k, v in it.items() if k != "path"})


@app.delete("/api/admin/norms/<path:norm_id>")
def norms_delete(norm_id):
    _need_admin()
    if not norms.delete(norm_id):
        return jsonify(error="Удалить можно только добавленные администраторами файлы"), 400
    feedback.log(_user()["name"], "Удалён норматив", {"file": norm_id})
    return jsonify(deleted=True)


@app.get("/api/admin/norms/search")
def norms_search():
    _need_admin()
    return jsonify(norms.search(request.args.get("q", "")))


@app.get("/api/admin/norms/lookup")
def norms_lookup():
    """Норматив и страница по ссылке из замечания («ГОСТ Р 2.316-2023 п. 6.5»)."""
    _need_admin()
    return jsonify(norms.lookup(request.args.get("std", "")))


@app.get("/api/admin/norms/page")
def norms_page():
    _need_admin()
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    text = norms.page_text(request.args.get("id", ""), page)
    if text is None:
        return jsonify(error="Страница не найдена"), 404
    return jsonify(text=text)


@app.get("/norms/<path:norm_id>")
def norms_file(norm_id):
    """PDF норматива (открывается в браузере; к адресу можно добавить #page=N)."""
    _need_admin()
    it = norms.get(norm_id)
    if not it:
        abort(404)
    return send_file(it["path"], mimetype="application/pdf", download_name=it["file"], as_attachment=False)


@app.get("/admin")
def admin_page():
    spa = _spa()
    if spa is not None:                     # приложение само покажет «Нет доступа»; код 403 — как у прежней страницы
        if not _is_admin():
            spa.status_code = 403
        return spa
    if not _is_admin():
        return render_template("denied.html"), 403
    return render_template("admin.html")


@app.get("/api/admin/state")
def admin_state():
    _need_admin()
    auth = {"user": _user()["name"]}
    cfg = load_config()
    lists = {k: cfg.get(k) for k in LIST_KEYS}
    if not lists["obsolete_standards"]:
        lists["obsolete_standards"] = [{"old": o, "new": n} for o, n in OBSOLETE_STANDARDS]
    kinds = {"kinds": custom.KINDS, "where": custom.WHERE, "fields": custom.FIELDS, "checks": custom.FIELD_CHECKS,
             "list_what": custom.LIST_WHAT, "limit_what": custom.LIMIT_WHAT, "applies": custom.APPLIES}
    return jsonify(auth=auth, groups=catalog.catalog_view(cfg), sections=catalog.sections_view(cfg), standards=catalog.standards_index(cfg), params={k: cfg.get(k) for k in PARAM_KEYS},
                   custom_rules=cfg.get("custom_rules") or [], custom_meta=kinds,
                   defaults={k: DEFAULTS.get(k) for k in PARAM_KEYS}, lists=lists,
                   default_obsolete=[{"old": o, "new": n} for o, n in OBSOLETE_STANDARDS])


@app.post("/api/admin/settings")
def admin_save():
    _need_admin()
    data = request.get_json(force=True) or {}
    upd = {}
    feedback.log(_user()["name"], "Сохранены настройки", {k: (list(v)[:30] if isinstance(v, dict) else "…")
                                                          for k, v in data.items()})
    if isinstance(data.get("rules"), dict):
        rules = {}
        known = {r[0]: r for r in catalog.all_rules(load_config())}
        for code, st in data["rules"].items():
            meta = known.get(code)
            if not meta or meta[1] in catalog.LOCKED_GROUPS or not isinstance(st, dict):
                continue
            entry = {}
            if bool(st.get("enabled")) != meta[3]:
                entry["enabled"] = bool(st.get("enabled"))
            if st.get("severity") in ("error", "warning", "info"):
                entry["severity"] = st["severity"]
            if entry:
                rules[code] = entry
        upd["rules"] = rules
    if isinstance(data.get("modules"), dict):
        upd["modules"] = {k: bool(v) for k, v in data["modules"].items() if k in catalog.MODULES}
    for k in PARAM_KEYS:
        if k in (data.get("params") or {}):
            upd[k] = data["params"][k]
    for k in LIST_KEYS:
        if k in (data.get("lists") or {}):
            v = data["lists"][k]
            if k == "obsolete_standards":
                v = [{"old": str(r.get("old", "")).strip(), "new": str(r.get("new", "")).strip()}
                     for r in v if r.get("old") and r.get("new")]
                if v == [{"old": o, "new": n} for o, n in OBSOLETE_STANDARDS]:
                    v = []                          # совпадает со встроенным — хранить не нужно
            else:
                v = [str(x).strip() for x in v if str(x).strip()]
            upd[k] = v
    cfg = save_config(upd)
    return jsonify(ok=True, groups=catalog.catalog_view(cfg), sections=catalog.sections_view(cfg))


CUSTOM_KEYS = ("title", "kind", "severity", "applies", "material_contains", "designation_prefix", "message", "ref",
               "pattern", "match", "where", "field", "check", "value", "what", "values", "when_tt")


def _clean_custom(data: dict) -> dict:
    r = {k: data.get(k) for k in CUSTOM_KEYS if data.get(k) not in (None, "")}
    if isinstance(r.get("values"), str):
        r["values"] = [x.strip() for x in re.split(r"[\n;]", r["values"]) if x.strip()]
    return r


@app.post("/api/admin/custom")
def admin_custom_save():
    """Создать или изменить правило предприятия (code в теле — изменить существующее)."""
    _need_admin()
    data = request.get_json(force=True) or {}
    rule = _clean_custom(data)
    errs = custom.validate(rule)
    if errs:
        return jsonify(error="; ".join(errs)), 400
    cfg = load_config()
    rules = list(cfg.get("custom_rules") or [])
    code = data.get("code")
    if code and any(r.get("code") == code for r in rules):
        rules = [({**rule, "code": code, "created": r.get("created")} if r.get("code") == code else r) for r in rules]
    else:
        code = custom.next_code(rules)
        rules.append({**rule, "code": code, "created": time.strftime("%Y-%m-%d %H:%M")})
    cfg = save_config({"custom_rules": rules})
    return jsonify(ok=True, code=code, custom_rules=cfg.get("custom_rules"), groups=catalog.catalog_view(cfg))


@app.delete("/api/admin/custom/<code>")
def admin_custom_delete(code):
    _need_admin()
    cfg = load_config()
    rules = [r for r in cfg.get("custom_rules") or [] if r.get("code") != code]
    overrides = {k: v for k, v in (cfg.get("rules") or {}).items() if k != code}
    cfg = save_config({"custom_rules": rules, "rules": overrides})
    return jsonify(ok=True, custom_rules=cfg.get("custom_rules"), groups=catalog.catalog_view(cfg))


@app.post("/api/admin/custom/test")
def admin_custom_test():
    """Пробная проверка правила (ещё не сохранённого) на документах сохранённого отчёта."""
    _need_admin()
    data = request.get_json(force=True) or {}
    rule = _clean_custom(data.get("rule") or {})
    errs = custom.validate(rule)
    if errs:
        return jsonify(error="; ".join(errs)), 400
    rule["code"] = (data.get("rule") or {}).get("code") or "U??"
    job = _job(data.get("job_id") or "")
    out, checked = [], 0
    for d in job["results"]:
        checked += 1
        for f in custom.evaluate(d, rule):
            out.append({"file": d.get("file"), "designation": (d.get("title") or {}).get("designation"),
                        "severity": f["severity"], "message": f["message"]})
    return jsonify(checked=checked, hits=out[:200], total=len(out))


@app.post("/api/admin/rule")
def admin_rule():
    """Быстрое включение/выключение одного правила (кнопка «отключить правило» в отчёте)."""
    _need_admin()
    data = request.get_json(force=True) or {}
    code = data.get("code")
    cfg = load_config()
    meta = {r[0]: r for r in catalog.all_rules(cfg)}.get(code)
    if not meta or meta[1] in catalog.LOCKED_GROUPS:
        return jsonify(error="Неизвестное или служебное правило"), 400
    rules = dict(cfg.get("rules") or {})
    entry = dict(rules.get(code) or {})
    entry.pop("enabled", None)
    if bool(data.get("enabled")) != meta[3]:
        entry["enabled"] = bool(data.get("enabled"))
    if entry:
        rules[code] = entry
    else:
        rules.pop(code, None)
    save_config({"rules": rules})
    return jsonify(ok=True, code=code, enabled=bool(data.get("enabled")))


@app.delete("/api/admin/exceptions/<rule_id>")
def admin_exception_delete(rule_id):
    _need_admin()
    return jsonify(deleted=delete_rule(rule_id))


@app.get("/work/<path:sub>")
def work_files(sub):
    _job(sub.split("/")[0])               # доступ к изображениям листов — как к самому отчёту
    return send_from_directory(WORK, sub)


# ------------------------------------------------------------------ API для ERP ----
def _check_token():
    token = API_TOKEN or load_config().get("api_token", "")
    if token and request.headers.get("X-Api-Token") != token:
        abort(401)


@app.get("/api/v1/health")
def api_health():
    from checking.pdfreader import ocr_available
    return jsonify(status="ok", ocr=ocr_available())


@app.post("/api/v1/check")
def api_check():
    """Синхронная проверка одного чертежа.

    multipart/form-data: file (PDF/CDW/DFT/PNG…), dxf (необязательно) и поля карточки изделия ERP:
    designation, sku, name, mass, material, grade, base_size, blank_size, dxf_length, dxf_width.
    Одновременно можно передать спецификацию сборки: spec (PDF по форме 1 — проверяется вместе с чертежом, можно
    несколько полей spec; Excel — для сверки) и маршрутные карты / техпроцессы: process (PDF, xlsx, xls, docx).
    Ответ: {"success": true, "drawings": [...]} — формат как в report.json (без картинок листов)."""
    _check_token()
    fs = request.files.get("file")
    if not fs or not fs.filename:
        return jsonify(success=False, error="Не передан файл чертежа (поле file)"), 400
    name = _safe_name(fs.filename)
    if os.path.splitext(name)[1].lower() not in SUPPORTED:
        return jsonify(success=False, error=f"Формат файла не поддерживается: {name}"), 400
    tmp = os.path.join(WORK, "api", uuid.uuid4().hex)
    os.makedirs(tmp, exist_ok=True)
    try:
        path = os.path.join(tmp, name)
        fs.save(path)
        dxf_index = None
        dx = request.files.get("dxf")
        if dx and dx.filename:
            dpath = os.path.join(tmp, _safe_name(dx.filename))
            dx.save(dpath)
            dxf_index = DxfIndex([dpath])
        item = {k: request.form.get(k) for k in ("designation", "sku", "name", "mass", "material", "grade",
                                                  "base_size", "blank_size", "dxf_length", "dxf_width")}
        spec = ItemSpec(item) if any(item.values()) else None
        cfg = load_config()
        cfg["ocr"] = request.form.get("ocr", "1") == "1"
        extra: list[tuple[str, str]] = []
        for i, sf in enumerate(request.files.getlist("spec")):
            if not sf.filename:
                continue
            sname = _safe_name(sf.filename)
            sext = os.path.splitext(sname)[1].lower()
            sp = os.path.join(tmp, f"spec{i}_{sname}")
            if sext not in (".xlsx", ".xlsm", ".xls", ".pdf"):
                return jsonify(success=False, error=f"Формат спецификации не поддерживается: {sname}"), 400
            sf.save(sp)
            if sext == ".pdf":
                extra.append((sp, sname))
            elif spec is None:
                try:
                    spec = Spec(sp)
                except Exception as e:
                    return jsonify(success=False, error=f"Спецификация {sname} не прочитана: {e}"), 400
        cfg["_force_spec"] = {p for p, _ in extra}
        drawings = check_file(path, cfg, spec, img_dir=None, display_name=name, dxf_index=dxf_index)
        for sp, sname in extra:
            drawings += check_file(sp, cfg, spec, img_dir=None, display_name=sname)
        for i, pf in enumerate(request.files.getlist("process")):
            if not pf.filename:
                continue
            pname = _safe_name(pf.filename)
            if os.path.splitext(pname)[1].lower() not in PROCESS_EXT:
                return jsonify(success=False, error=f"Формат документа технологии не поддерживается: {pname}"), 400
            pp = os.path.join(tmp, f"proc{i}_{pname}")
            pf.save(pp)
            drawings.append(check_process_file(pp, cfg, None, pname))
        check_job(drawings, cfg, spec)                    # пакет PDF: сборка и её составные части
        link_to_drawings(drawings)
        out = []
        for d in drawings:
            dd = drawing_to_dict(d)
            dd.pop("pages", None)
            out.append(dd)
        return jsonify(success=True, drawings=out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.get("/api/history")
def history():
    out = []
    cfg = load_config()
    if os.path.isdir(WORK):
        for jid in sorted(os.listdir(WORK), reverse=True)[:200]:
            rp = os.path.join(WORK, jid, "report.json")
            if os.path.exists(rp):
                try:
                    with open(rp, encoding="utf-8") as f:
                        res = json.load(f)
                except Exception:
                    continue
                res = [catalog.apply_to_dict(custom.apply_to_dict(r, cfg), cfg) for r in res]
                owner = None
                try:
                    with open(os.path.join(WORK, jid, "meta.json"), encoding="utf-8") as f:
                        owner = json.load(f).get("owner")
                except Exception:
                    pass
                if not _is_admin() and owner != _user()["name"]:
                    continue
                out.append({"id": jid, "owner": owner, "count": len(res),
                            "errors": sum(r["counts"]["error"] for r in res),
                            "warnings": sum(r["counts"]["warning"] for r in res)})
    return jsonify(out)


if __name__ == "__main__":
    write_default_config()
    backup_data(DATA)
    users.ensure_default()
    os.makedirs(WORK, exist_ok=True)
    url = f"http://127.0.0.1:{PORT}/"
    if "--no-browser" not in sys.argv and HOST != "127.0.0.1":
        sys.argv.append("--no-browser")
    print(f"Проверка чертежей: {url}  (Ctrl+C — остановить)")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        from waitress import serve
        serve(app, host=HOST, port=PORT, threads=8)
    except ImportError:
        app.run(host=HOST, port=PORT, debug=False)
