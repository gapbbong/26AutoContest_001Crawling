# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 설정: 단일 exe(ExamCollector.exe)로 묶는다. 빌드: build_exe.bat
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

datas, binaries, hiddenimports = [], [], []

# Streamlit 서버/프런트엔드, Selenium(드라이버 관리자 포함), PyMuPDF는 정적 분석만으로는 리소스가 빠지므로 통째로 포함
for pkg in ("streamlit", "selenium", "pymupdf", "fitz"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass
for pkg in ("streamlit", "requests", "bs4", "PIL", "altair", "pandas", "numpy", "pyarrow", "tornado", "click", "watchdog"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

# ui/app.py는 Streamlit이 실행 시 읽는 스크립트라 PyInstaller가 import를 추적하지 못한다 -> 프로젝트 패키지를 직접 지정
for pkg in ("crawler", "database", "generator"):
    hiddenimports += collect_submodules(pkg)
hiddenimports += ["tkinter", "tkinter.filedialog", "sqlite3", "bs4", "lxml", "PIL.Image"]

datas += [
    ("ui/app.py", "ui"),
    ("assets", "assets"),
    ("generator/base_header.xml", "generator"),
    ("generator/base_prv_image.png", "generator"),
    ("generator/base_prv_image.b64", "generator"),
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "IPython", "jupyter", "notebook", "pytest", "scipy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ExamCollector",
    console=False,          # 콘솔 창 없이 실행(로딩창 + 브라우저)
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ExamCollector")
