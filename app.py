"""Веб-интерфейс проверки чертежей.  Запуск: run.bat  (или  .venv\\Scripts\\python app.py)"""
from __future__ import annotations

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

from flask import Flask, abort, jsonify, render_template, request, send_file, send_from_directory, session

from checking import admin, catalog, custom
from checking.config import DEFAULTS, load_config, save_config, write_default_config
from checking.normdata import OBSOLETE_STANDARDS
from checking.completeness import completeness
from checking.engine import SUPPORTED, check_file, check_job, collect_dxf, collect_files
from checking.exceptions import add_rule, apply_to_dict, delete_rule, load_rules
from checking.remarks import build_docx
from checking.report import drawing_to_dict, save_excel
from checking.dxf import DxfIndex
from checking.spec import ItemSpec, Spec
from checking.textnorm import nfc

from checking.config import ROOT, RES
WORK = os.path.join(ROOT, "work")
PORT = int(os.environ.get("CHECKING_PORT", "8765"))
HOST = os.environ.get("CHECKING_HOST", "127.0.0.1")
API_TOKEN = os.environ.get("CHECKING_API_TOKEN", "")

app = Flask(__name__, template_folder=os.path.join(RES, "web", "templates"),
            static_folder=os.path.join(RES, "web", "static"))
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 ** 3
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0      # стили и скрипты не кэшировать — обновления видны сразу
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.secret_key = admin.secret_key()
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()


def _safe_name(name: str) -> str:
    name = nfc(os.path.basename(name.replace("\\", "/")))
    return "".join(c for c in name if c not in '<>:"|?*').strip() or "file"


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
             dxf_paths: list[str] | None = None):
    job = JOBS[job_id]
    jdir = os.path.join(WORK, job_id)
    try:
        cfg = load_config()
        cfg["ocr"] = use_ocr
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
        changed = check_job(drawings, cfg, spec, apply_profile=False)     # сверка документов между собой
        for i, d in enumerate(drawings):
            job["results"][i]["facts"]["mass_parts"] = d.facts.get("mass_parts")
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
                       "dxf": job.get("dxf")}, f, ensure_ascii=False)
        job["state"] = "done"
    except Exception as e:
        job["state"] = "error"
        job["error"] = f"{e}\n{traceback.format_exc()}"
    finally:
        job["finished"] = time.time()


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/jobs")
def create_job():
    job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    jdir = os.path.join(WORK, job_id)
    up = os.path.join(jdir, "uploads")
    os.makedirs(up, exist_ok=True)
    files: list[tuple[str, str]] = []
    dxf_paths: list[str] = []
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
                if p.lower().endswith(".dxf"):
                    dxf_paths.append(p)
                else:
                    files.append((p, os.path.basename(p)))
        elif name.lower().endswith(".dxf"):
            dxf_paths.append(target)
        elif os.path.splitext(name)[1].lower() in SUPPORTED:
            files.append((target, name))
    folder = (request.form.get("folder") or "").strip().strip('"')
    if folder:
        if not os.path.isdir(folder):
            return jsonify(error=f"Папка не найдена: {folder}"), 400
        for p in collect_files([folder]):
            files.append((p, os.path.relpath(p, folder)))
        dxf_paths += collect_dxf([folder])
    if not files:
        return jsonify(error="Не выбрано ни одного чертежа (PDF, CDW, DFT, PNG/JPG/TIF или ZIP)"), 400
    spec_path = None
    sf = request.files.get("spec")
    if sf and sf.filename:
        spec_path = os.path.join(jdir, _safe_name(sf.filename))
        sf.save(spec_path)
    use_ocr = request.form.get("ocr", "1") == "1"
    JOBS[job_id] = {"id": job_id, "state": "running", "total": len(files), "done": 0, "current": "",
                    "results": [], "warnings": [], "spec": None, "started": time.time()}
    threading.Thread(target=_run_job, args=(job_id, files, spec_path, use_ocr, dxf_paths), daemon=True).start()
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
               "dxf": meta.get("dxf")}
        JOBS[job_id] = job
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
    _job(job_id)
    return render_template("report.html", job_id=job_id)


@app.get("/api/jobs/<job_id>/excel")
def job_excel(job_id):
    job = _job(job_id)
    results, comp = _view(job)
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
    data = request.get_json(force=True) or {}
    if data.get("scope") not in ("drawing", "global") or not data.get("code"):
        return jsonify(error="scope (drawing|global) и code обязательны"), 400
    rule = {k: data.get(k) for k in ("scope", "code", "message", "designation", "file", "pattern", "comment")}
    return jsonify(add_rule(rule))


@app.delete("/api/exceptions/<rule_id>")
def exceptions_delete(rule_id):
    return jsonify(deleted=delete_rule(rule_id))


# ------------------------------------------------------------------ настройки (администратор) ----
PARAM_KEYS = ("mass", "laser", "tight_it", "coarse_it", "thread_min_turns", "hardness_min_range_hrc", "ocr")
LIST_KEYS = ("org_codes", "general_tolerance_refs", "obsolete_standards")


def _is_admin() -> bool:
    return not admin.password_set() or bool(session.get("admin"))


def _need_admin():
    if not _is_admin():
        abort(401)


@app.get("/admin")
def admin_page():
    return render_template("admin.html")


@app.get("/api/admin/state")
def admin_state():
    auth = {"password_set": admin.password_set(), "logged_in": _is_admin()}
    if not _is_admin():
        return jsonify(auth=auth), 401
    cfg = load_config()
    lists = {k: cfg.get(k) for k in LIST_KEYS}
    if not lists["obsolete_standards"]:
        lists["obsolete_standards"] = [{"old": o, "new": n} for o, n in OBSOLETE_STANDARDS]
    kinds = {"kinds": custom.KINDS, "where": custom.WHERE, "fields": custom.FIELDS, "checks": custom.FIELD_CHECKS,
             "list_what": custom.LIST_WHAT, "limit_what": custom.LIMIT_WHAT, "applies": custom.APPLIES}
    return jsonify(auth=auth, groups=catalog.catalog_view(cfg), params={k: cfg.get(k) for k in PARAM_KEYS},
                   custom_rules=cfg.get("custom_rules") or [], custom_meta=kinds,
                   defaults={k: DEFAULTS.get(k) for k in PARAM_KEYS}, lists=lists,
                   default_obsolete=[{"old": o, "new": n} for o, n in OBSOLETE_STANDARDS])


@app.post("/api/admin/settings")
def admin_save():
    _need_admin()
    data = request.get_json(force=True) or {}
    upd = {}
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
    return jsonify(ok=True, groups=catalog.catalog_view(cfg))


CUSTOM_KEYS = ("title", "kind", "severity", "applies", "material_contains", "designation_prefix", "message", "ref",
               "pattern", "match", "where", "field", "check", "value", "what", "values")


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


@app.post("/api/admin/login")
def admin_login():
    data = request.get_json(force=True) or {}
    if admin.check_password(data.get("password", "")):
        session["admin"] = True
        session.permanent = True
        return jsonify(ok=True)
    return jsonify(error="Неверный пароль"), 403


@app.post("/api/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return jsonify(ok=True)


@app.post("/api/admin/password")
def admin_password():
    _need_admin()
    data = request.get_json(force=True) or {}
    new = (data.get("new") or "").strip()
    if admin.password_set() and not admin.check_password(data.get("old", "")):
        return jsonify(error="Текущий пароль указан неверно"), 403
    if new and len(new) < 4:
        return jsonify(error="Пароль слишком короткий (минимум 4 символа)"), 400
    admin.set_password(new or None)
    session["admin"] = bool(new)
    return jsonify(ok=True, password_set=bool(new))


@app.delete("/api/admin/exceptions/<rule_id>")
def admin_exception_delete(rule_id):
    _need_admin()
    return jsonify(deleted=delete_rule(rule_id))


@app.get("/work/<path:sub>")
def work_files(sub):
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
        drawings = check_file(path, cfg, spec, img_dir=None, display_name=name, dxf_index=dxf_index)
        check_job(drawings, cfg, spec)                    # пакет PDF: сборка и её составные части
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
        for jid in sorted(os.listdir(WORK), reverse=True)[:30]:
            rp = os.path.join(WORK, jid, "report.json")
            if os.path.exists(rp):
                try:
                    with open(rp, encoding="utf-8") as f:
                        res = json.load(f)
                except Exception:
                    continue
                res = [catalog.apply_to_dict(custom.apply_to_dict(r, cfg), cfg) for r in res]
                out.append({"id": jid, "count": len(res),
                            "errors": sum(r["counts"]["error"] for r in res),
                            "warnings": sum(r["counts"]["warning"] for r in res)})
    return jsonify(out)


if __name__ == "__main__":
    write_default_config()
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
