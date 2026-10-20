# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [("web", "web"), ("standards", "standards"), ("classifier", "classifier"), ("frontend/dist", "frontend/dist")], [], []
for pkg in ("rapidocr", "onnxruntime", "pymupdf", "ezdxf", "docx", "openpyxl", "xlrd", "waitress"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h
hiddenimports += collect_submodules("checking") + ["win32com.client", "pythoncom", "olefile"]

a = Analysis(["app.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=["pytest", "tkinter", "matplotlib", "scipy", "pandas"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ПроверкаЧертежей", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="ПроверкаЧертежей")
