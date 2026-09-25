import os
import sys
import re
import time
import json
import shutil
import base64
import zipfile
import io
import threading
from datetime import datetime
import streamlit as st

# 프로젝트 루트 경로 등록
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
# 실행 데이터(수집 DB·설정·출력물)를 두는 위치. 단일 exe로 배포했을 때는 읽기 전용 리소스 폴더가 아니라
# exe가 있는 폴더를 쓰도록 main.py가 APP_DATA_DIR 환경변수로 알려준다(소스 실행 시에는 프로젝트 폴더).
DATA_ROOT = os.environ.get("APP_DATA_DIR") or PARENT_DIR
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

import importlib
import database.db_manager
import generator.hwpx_builder
import generator.template_manager
import crawler.portal_downloader
import crawler.exam_splitter
import crawler.ebsi_crawler
importlib.reload(database.db_manager)
importlib.reload(generator.hwpx_builder)
importlib.reload(generator.template_manager)
importlib.reload(crawler.portal_downloader)
importlib.reload(crawler.exam_splitter)
importlib.reload(crawler.ebsi_crawler)  # 코드 수정 후 앱을 껐다 켜지 않아도 최신 크롤러 로직이 바로 반영되도록
from database.db_manager import QuestionDB
from crawler.ebsi_crawler import EBSiCrawler
from crawler.login_required import list_sources as list_login_required_sources
from crawler.login_required import get_source as get_login_required_source
from generator.template_manager import TemplateManager

# 페이지 기본 설정 (와이드 레이아웃)
st.set_page_config(
    page_title="공공 기출문제 실시간 수집기 | 부산교육청 업무자동화",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 부산시교육청 로고 이미지 Base64 인코딩 로드
logo_path = os.path.join(PARENT_DIR, "assets", "busan_edu_logo.png")
logo_b64 = ""
if os.path.exists(logo_path):
    with open(logo_path, "rb") as img_f:
        logo_b64 = base64.b64encode(img_f.read()).decode("utf-8")

# 글래스모피즘, 폰트 확대 및 본고딕(Noto Sans KR) 테마 CSS
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800;900&display=swap');
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

/* 불필요한 기본 요소 숨김 */
#MainMenu {visibility: hidden !important;}
footer {visibility: hidden !important;}
header {display: none !important;}
.stDeployButton {display: none !important;}
[data-testid="stSidebar"] {display: none !important;}
[data-testid="stSidebarCollapsedControl"] {display: none !important;}

.block-container {
    padding-top: 0.1rem !important;
    padding-bottom: 1.5rem !important;
}

/* Streamlit이 세로로 쌓이는 블록 사이에 기본 flex gap(약 1rem)을 자동으로 넣기 때문에,
   위 헤더 div 자체의 margin-bottom을 아무리 줄여도 이 gap 때문에 여백이 그대로 보인다. */
div[data-testid="stVerticalBlock"] {
    gap: 0.6rem !important;
}

/* "📋 수집 조건 확인" 팝업을 화면 세로 중앙에 오도록 - Streamlit 기본값은 다이얼로그
   오버레이가 위쪽 정렬(align-items: flex-start)이라 화면 상단에 붙어서 뜬다. */
div[data-testid="stDialog"] {
    align-items: center !important;
}

/* 팝업 제목(h3)이 우측 상단 닫기(X) 버튼보다 한참 아래에서 시작해 어색해 보이던 것을 줄인다.
   실측해보니 진짜 원인은 Streamlit이 다이얼로그 title(" " 같은 공백 문자열)을 담아 자동으로
   만드는 h2 태그의 위/아래 padding(24.75px/12.375px)이었다 - 우리가 직접 그리는 콘텐츠는
   그 h2 "다음" div에 들어간다. h2 padding을 확 줄이고, 그 아래 콘텐츠 div의 padding-top도
   최소로 눌러서 전체 위쪽 여백을 처음의 약 1/3 수준으로 좁혔다(2026-09-19 실측/조정).*/
section[role="dialog"] > h2 {
    padding-top: 6px !important;
    padding-bottom: 4px !important;
}
section[role="dialog"] > div {
    padding-top: 2px !important;
}

/* 전체 UI 본고딕(Noto Sans KR) 및 프리텐다드 서체 적용 (아이콘 제외) */
html, body, p, label, input, button, select, textarea, h1, h2, h3, h4, .stMarkdown, .stSelectbox, .stButton {
    font-family: 'Noto Sans KR', 'Pretendard', 'Malgun Gothic', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
    font-size: 16.5px !important;
    letter-spacing: -0.2px !important;
}

/* Streamlit 기본 Material 아이콘 폰트 복원 및 보호 */
[data-testid="stIcon"], [data-testid="stExpanderToggleIcon"], [data-testid="stExpanderIcon"], .material-symbols-rounded, .material-icons, [translate="no"], [data-testid="stExpanderToggleIcon"] span {
    font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
    font-size: 20px !important;
    visibility: visible !important;
}

/* 탭 네비게이션 스타일: 밑줄 제거, 세련된 모던 세그먼트 컨트롤/필 탭 */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px !important;
    margin-bottom: 18px !important;
    background: #f1f5f9 !important;
    padding: 6px !important;
    border-radius: 12px !important;
    border: 1.5px solid #e2e8f0 !important;
    display: flex !important;
    width: 100% !important;
    box-sizing: border-box !important;
}
.stTabs [data-baseweb="tab-border"] {
    display: none !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    display: none !important;
}
.stTabs [data-baseweb="tab"] {
    flex: 1 !important;
    text-align: center !important;
    justify-content: center !important;
    font-size: 16.5px !important;
    font-weight: 700 !important;
    padding: 11px 20px !important;
    border-radius: 9px !important;
    color: #64748b !important;
    background-color: transparent !important;
    border: none !important;
    border-bottom: none !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #1e3a8a !important;
    background-color: rgba(255, 255, 255, 0.7) !important;
}
.stTabs [aria-selected="true"] {
    background: #ffffff !important;
    color: #1e40af !important;
    font-weight: 800 !important;
    box-shadow: 0 3px 12px rgba(30, 58, 138, 0.12), 0 1px 3px rgba(0,0,0,0.06) !important;
    border: 1px solid #cbd5e1 !important;
    border-bottom: 1px solid #cbd5e1 !important;
}

/* 라벨 및 제목 폰트 크기 강화 */
label[data-testid="stWidgetLabel"] p {
    font-size: 16.5px !important;
    font-weight: 700 !important;
    color: #0f172a !important;
}

/* 체크박스 스타일: 깔끔한 여백과 줄 맞춤 */
div[data-testid="stCheckbox"] {
    margin-bottom: 2px !important;
    padding-top: 1px !important;
    padding-bottom: 1px !important;
    padding-left: 2px !important;
}
div[data-testid="stCheckbox"] label p {
    font-size: 14.5px !important;
    font-weight: 600 !important;
    color: #1e293b !important;
    line-height: 1.35 !important;
}

/* 셀렉트박스 내부 글자 */
.stSelectbox div[data-baseweb="select"] {
    font-size: 16px !important;
}

/* 세련된 딥 로열블루 그라데이션 시작 버튼 (18px) */
button[kind="primary"] {
    background: linear-gradient(135deg, #1e40af 0%, #2563eb 50%, #3b82f6 100%) !important;
    color: #ffffff !important;
    font-size: 18px !important;
    font-weight: 800 !important;
    padding: 13px 18px !important;
    border-radius: 10px !important;
    border: 1px solid rgba(255, 255, 255, 0.3) !important;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.38) !important;
    transition: all 0.2s ease-in-out !important;
    letter-spacing: -0.2px !important;
}
button[kind="primary"] p {
    font-size: 18px !important;
    font-weight: 800 !important;
}
button[kind="primary"]:hover {
    background: linear-gradient(135deg, #1e3a8a 0%, #1d4ed8 50%, #2563eb 100%) !important;
    box-shadow: 0 6px 20px rgba(30, 58, 138, 0.5) !important;
    transform: translateY(-1px) !important;
}

h3 {
    font-size: 19px !important;
    font-weight: 800 !important;
}
h4 {
    font-size: 17px !important;
    font-weight: 700 !important;
}

/* 체크박스 내부 공공기관 링크 스타일 */
.stCheckbox a {
    color: #1e40af !important;
    text-decoration: none !important;
    font-weight: 600 !important;
}
.stCheckbox a:hover {
    color: #2563eb !important;
    text-decoration: underline !important;
}
</style>
""", unsafe_allow_html=True)

# 마지막으로 사용한 수집 조건 로컬 저장/복원 (다음 실행 시 그 조건이 기본 선택되도록)
PREFS_PATH = os.path.join(DATA_ROOT, "data", "user_prefs.json")

def load_prefs() -> dict:
    try:
        with open(PREFS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _pref_list(prefs: dict, key: str) -> list:
    """
    prefs[key]를 항상 리스트로 정규화해서 돌려준다 - 예전 버전은 마지막으로 체크한 항목
    하나만 단일 값으로 저장했어서(다중 선택 중 1개만 복원됨), 지금은 리스트로 저장하지만
    옛 prefs.json 파일과의 하위 호환을 위해 단일 값도 리스트로 감싸서 처리한다.
    """
    val = prefs.get(key)
    if val is None:
        return []
    return val if isinstance(val, list) else [val]

def save_prefs(prefs: dict):
    try:
        os.makedirs(os.path.dirname(PREFS_PATH), exist_ok=True)
        with open(PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _get_or_build_t2_files(meta: dict) -> dict:
    """선택된 조건(meta)에 해당하는 hwpx 3종을 만들어 캐시해둔다. 같은 조건이면 다시 만들지
    않고 캐시를 그대로 돌려줘서, 다운로드 버튼이 클릭 한 번에 바로 저장되도록(생성 대기 없이)
    한다. 조건이 바뀌면(제목/문항수 변경) 자동으로 새로 만든다."""
    cache_key = f"{meta['title']}|{len(meta['questions'])}"
    cache = st.session_state.get("t2_files_cache")
    if cache and cache.get("key") == cache_key:
        return cache["files"]
    gen_files = template_mgr.generate_all_packages(
        title=meta["title"], subtitle=meta["subtitle"],
        questions=meta["questions"], header_meta=meta["header_meta"]
    )
    file_bytes = {}
    for key in ["student", "teacher", "solution"]:
        f_path = gen_files.get(key, "")
        if f_path and os.path.exists(f_path):
            with open(f_path, "rb") as bf:
                file_bytes[key] = {"bytes": bf.read(), "filename": os.path.basename(f_path)}
    st.session_state["t2_files_cache"] = {"key": cache_key, "files": file_bytes}
    return file_bytes


def _get_or_build_t2_zip(meta: dict) -> dict:
    """학생용/교사용/해설 hwpx 3개를 zip 하나로 묶어 캐시해둔다. 버튼 하나로 3개 파일을
    한 번에(브라우저 다운로드 1건) 받을 수 있도록 하기 위함 — 브라우저는 사용자 클릭 없이
    여러 파일을 한꺼번에 자동저장하는 걸 보안상 막기 때문에, 진짜로 한 번에 받게 하려면
    zip으로 묶는 것이 유일하게 확실한 방법이다."""
    file_bytes = _get_or_build_t2_files(meta)
    cache_key = f"{meta['title']}|{len(meta['questions'])}"
    cache = st.session_state.get("t2_zip_cache")
    if cache and cache.get("key") == cache_key:
        return cache["zip"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for info in file_bytes.values():
            zf.writestr(info["filename"], info["bytes"])
    clean_title = "".join(c for c in meta["title"] if c.isalnum() or c in (' ', '_', '-')).strip()
    zip_result = {"bytes": buf.getvalue(), "filename": f"{clean_title}_[학생용_교사용_해설].zip"}
    st.session_state["t2_zip_cache"] = {"key": cache_key, "zip": zip_result}
    return zip_result


def _pick_folder_dialog(initial_dir: str = "") -> str:
    """네이티브 OS 폴더 선택 창을 띄운다. 이 앱은 사용자 PC에서 직접 실행되는 로컬
    프로그램이라(브라우저는 화면만 보여줄 뿐) 서버 쪽 파이썬 코드가 곧 사용자 PC에서
    직접 도는 것과 같아서, tkinter로 진짜 OS 폴더 선택창을 띄울 수 있다. 취소하면 빈 문자열."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        folder = filedialog.askdirectory(initialdir=initial_dir or None, title="hwpx 저장 폴더 선택")
    finally:
        root.destroy()
    return folder or ""


def _save_files_to_folder(file_bytes_dict: dict, folder: str) -> list:
    saved = []
    for info in file_bytes_dict.values():
        path = os.path.join(folder, info["filename"])
        with open(path, "wb") as f:
            f.write(info["bytes"])
        saved.append(path)
    return saved


def _render_local_folder_save(file_bytes_dict: dict, widget_key: str, lead=None, tabs=None) -> None:
    """저장 영역 한 줄 구성: [학생용][교사용][해설] 개별 저장 + [3개 파일 한 번에 저장], 그 아래
    저장 폴더 경로와 폴더 열기/변경. 폴더는 한 번 고르면 data/user_prefs.json에 저장해 두고
    다음부터는 묻지 않고 그 폴더에 hwpx 3개를 압축 없이 그대로 써 넣는다(브라우저 저장소가 아니라
    로컬 설정 파일이라 브라우저를 바꿔도 유지된다)."""
    saved_folder = prefs.get("save_folder", "")
    _row = st.container(key=f"out_row_{widget_key}")
    with _row:
        if lead and tabs:
            c_p, c_tabs, c_mid, c_all = st.columns(4, vertical_alignment="center")
            with c_p:
                lead()
            with c_tabs:
                tabs()
        elif lead:
            c_p, c_mid, c_all = st.columns(3, vertical_alignment="center")
            with c_p:
                lead()
        else:
            c_mid, c_all = st.columns(2, vertical_alignment="center")
    # 저장 폴더 칩: 미리보기 - [저장 폴더 · 열기 · 변경] - 저장 분할 버튼을 한 줄에 배치
    with c_mid:
        with st.container(border=True, key=f"folder_chip_{widget_key}"):
            col_info, col_open, col_change = st.columns([6, 1.15, 1.15], vertical_alignment="center", gap="small")
            with col_info:
                if saved_folder:
                    _esc = saved_folder.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
                    st.markdown(f"<div title=\"{_esc}\" style='font-size:14px; font-weight:600; color:#1e293b; line-height:30px; height:30px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>📁 {_esc}</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div style='font-size:14px; color:#475569; line-height:30px; height:30px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>📁 저장 폴더 미지정</div>", unsafe_allow_html=True)
            with col_open:
                if saved_folder and st.button("열기", type="tertiary", help="저장 폴더 열기", key=f"open_folder_{widget_key}", use_container_width=True):
                    if os.path.isdir(saved_folder):
                        os.startfile(saved_folder)
                    else:
                        st.warning("⚠️ 저장 폴더가 없어졌습니다. '변경'으로 다시 지정해 주세요.")
            with col_change:
                if st.button("변경" if saved_folder else "지정", type="tertiary", help="저장 폴더 변경" if saved_folder else "저장 폴더 지정", key=f"change_folder_{widget_key}", use_container_width=True):
                    picked = _pick_folder_dialog(saved_folder)
                    if picked:
                        prefs["save_folder"] = picked
                        save_prefs(prefs)
                        st.rerun()
    # 분할 버튼: 왼쪽 = 3개 한 번에 저장, 오른쪽 ▾ = 개별 파일(학생용/교사용/해설) 저장 메뉴
    with c_all:
        with st.container(key=f"split_{widget_key}"):
            c_main, c_drop = st.columns([5, 1], gap="small", vertical_alignment="center")
            with c_main:
                save_clicked = st.button("3개 파일 한 번에 저장", icon=":material/save:", key=f"save_local_{widget_key}", type="primary", use_container_width=True)
            with c_drop:
                with st.popover(" ", type="primary", use_container_width=True, help="개별 파일 저장"):
                    for _k, _label in (("student", "학생용 파일 저장"), ("teacher", "교사용 파일 저장"), ("solution", "해설 파일 저장")):
                        if _k in file_bytes_dict:
                            st.download_button(
                                _label, icon=":material/description:", data=file_bytes_dict[_k]["bytes"], file_name=file_bytes_dict[_k]["filename"],
                                mime="application/haansofthwpx", use_container_width=True, key=f"t2_quick_dl_{_k}_{widget_key}"
                            )

    if save_clicked:
        folder = prefs.get("save_folder", "")
        if not folder or not os.path.isdir(folder):
            picked = _pick_folder_dialog()
            if not picked:
                st.warning("⚠️ 폴더를 선택하지 않아 저장이 취소되었습니다.")
                return
            folder = picked
            prefs["save_folder"] = folder
            save_prefs(prefs)
        saved_paths = _save_files_to_folder(file_bytes_dict, folder)
        st.success(f"✅ {len(saved_paths)}개 파일을 저장했습니다 → {folder}")


def _option_index(options: list, value, default: int = 0) -> int:
    try:
        return options.index(value)
    except ValueError:
        return default

def _checkbox_group_fix_state(options: list, default_list: list, key_prefix: str,
                              all_value: str = "전체", all_mode: str = "select_all") -> None:
    """
    _checkbox_group()의 "전체" 상태 보정 로직만 떼어낸 부분 - 체크박스를 실제로 두 개 이상의
    st.columns에 나눠서 그려야 할 때(예: 항목이 많은 "5. 과목"), 렌더링 전에 전체 옵션
    목록을 대상으로 한 번만 호출해두면 이후 _checkbox_group_render()를 여러 컬럼에 나눠
    호출해도 "전체" 토글이 옵션 전체를 대상으로 올바르게 동작한다.
    all_mode: "select_all"(학년/연도) 또는 "exclusive"(시험구분/과목) - _checkbox_group 참고.
    """
    other_opts = [o for o in options if o != all_value]
    all_key = f"{key_prefix}_{all_value}"
    prev_all_key = f"{key_prefix}__prev_all"
    other_keys = [f"{key_prefix}_{opt}" for opt in other_opts]

    all_checked = st.session_state.get(all_key, all_value in default_list)
    prev_all_checked = st.session_state.get(prev_all_key, all_value in default_list)

    if all_mode == "select_all":
        # "전체"를 체크/해제하는 순간에만 개별 항목을 일괄 동기화한다. 개별 항목을 하나
        # 나중에 따로 해제해도 "전체" 체크 자체는 건드리지 않는다 - 예전에는 "전체가 켜진
        # 상태에서 개별 항목이 하나라도 꺼지면 전체도 같이 끈다"는 규칙이 있었는데, 이게
        # "전체"를 막 체크해서 전부 켜진 바로 다음 실행에서 무엇을 막 껐는지와 상관없이
        # 오작동해 방금 체크한 항목들이 다시 풀려버리는 문제가 있어 제거했다 (2026-09-18).
        if all_checked and not prev_all_checked:
            for k in other_keys:
                st.session_state[k] = True
        elif not all_checked and prev_all_checked:
            for k in other_keys:
                st.session_state[k] = False
    else:  # "exclusive"
        other_checked = any(
            st.session_state.get(k, opt in default_list)
            for k, opt in zip(other_keys, other_opts)
        )
        if all_checked and other_checked:
            if not prev_all_checked:
                for k in other_keys:
                    st.session_state[k] = False
            else:
                st.session_state[all_key] = False
                all_checked = False

    st.session_state[prev_all_key] = all_checked


def _dim_css_html(options: list, dim_options: set, index_source: list, key_prefix: str) -> str:
    """
    dim_options에 걸리는 옵션들의 opacity/gap CSS를 하나의 <style> 문자열로 모아서 돌려준다.
    이 문자열을 호출부가 "이미 그릴 예정이던" 다른 markdown(예: 섹션 제목)에 얹어서 함께
    출력하면, CSS만을 위한 별도 st.markdown() 호출이 flex 목록에 새 자식으로 끼어들어
    부모의 기본 gap(~10px)만큼 전체 목록이 아래로 밀리는 현상을 막을 수 있다
    (2026-09-18 실측: "5. 과목"에서 출처를 하나만 선택해 일부가 흐릿해질 때마다 목록 전체가
    아래로 살짝 밀리던 문제).
    """
    parts = []
    for opt in options:
        if opt in dim_options:
            row_key = f"{key_prefix}__dim{index_source.index(opt)}"
            parts.append(
                f"div.st-key-{row_key} label {{ opacity: 0.55; }} "
                f"div.st-key-{row_key} {{ gap: 0 !important; }}"
            )
    return f"<style>{' '.join(parts)}</style>" if parts else ""


def _checkbox_group_render(options: list, format_func, default_list: list, key_prefix: str,
                           all_value: str = "전체", all_mode: str = "select_all",
                           auto_uncheck_all: bool = False, dim_options: set | None = None,
                           global_options: list | None = None, disable_all: bool = False,
                           disable_options: set | None = None, emit_dim_css: bool = True) -> list:
    """
    _checkbox_group_fix_state()로 상태를 미리 보정해둔 뒤, 옵션의 일부(또는 전체)를 그린다.
    st.checkbox(value=...)는 key가 있어도 st.dialog를 여는 st.rerun() 직후의 실행에서
    session_state를 무시하고 value로 되돌아가는 경우가 있어(2026-09-18 실측 확인),
    value 파라미터 없이 session_state.setdefault()로만 초기값을 넣는다.

    dim_options: 이 집합에 포함된 옵션은 체크박스를 흐릿하게(opacity) 표시한다 - 예를 들어
    "5. 과목"에서 현재 체크된 공공 출처로는 나올 수 없는 과목을 시각적으로 구분할 때 쓴다.
    한글이 섞인 key는 Streamlit이 CSS 클래스로 만들 때 전부 "-"로 뭉개져서(예: "생활과 윤리"
    -> "------") 서로 다른 과목끼리 클래스가 충돌할 수 있어, 여기서는 옵션의 "전체 목록 기준
    위치 번호"(ASCII 숫자)로 별도의 래퍼 컨테이너 key를 만들어 충돌을 피한다.
    global_options: 여러 컬럼에 나눠 그릴 때(예: "5. 과목" 두 컬럼) 각 옵션의 위치 번호를
    부분 목록이 아닌 전체 목록 기준으로 계산하기 위한 참조용 리스트.
    disable_options: 이 집합에 포함된 옵션은 아예 클릭 못 하게 비활성화한다(예: "2. 학년"에서
    KICE만 선택했을 때 KICE가 못 주는 고1/고2) - dim_options는 시각적으로만 흐리게 하고 여전히
    클릭 가능한 반면, 이건 진짜 선택 불가로 만든다. 비활성화 직전에 세션 값을 강제로 꺼서
    "화면엔 회색인데 예전에 체크해 둔 값이 세션에 남아 실제 수집 조합에는 계속 끼어드는" 사고를
    막는다 - "전체" 옵션 자체는 대상에서 제외한다.
    """
    index_source = global_options if global_options is not None else options
    # 완전히 비활성화(disable_options)되는 항목도 시각적으로 흐릿하게 보여야 사용자가
    # "선택이 안 되는 항목"임을 한눈에 알 수 있다 - Streamlit 기본 disabled 스타일만으로는
    # 색 차이가 너무 미묘해서 눈에 잘 안 띈다는 피드백(2026-09-18)에 따라, dim_options와
    # disable_options를 합쳐서 같은 흐림 처리를 적용한다.
    _effective_dim = set(dim_options or set()) | {o for o in (disable_options or set()) if o != all_value}

    # emit_dim_css=False면 호출부가 이 CSS를 자기가 이미 그릴 다른 markdown에 얹어서
    # 대신 출력한다는 뜻이다 (_dim_css_html 참고) - 별도 st.markdown() 호출을 새로 만들지
    # 않아야 목록 전체가 밀리지 않는다.
    if _effective_dim and emit_dim_css:
        _dim_css = _dim_css_html(options, _effective_dim, index_source, key_prefix)
        if _dim_css:
            st.markdown(_dim_css, unsafe_allow_html=True)

    selected = []
    for opt in options:
        key = f"{key_prefix}_{opt}"
        st.session_state.setdefault(key, opt in default_list)
        is_disabled = bool(disable_all or (opt != all_value and disable_options and opt in disable_options))
        if is_disabled and opt != all_value:
            st.session_state[key] = False
        if opt in _effective_dim:
            row_key = f"{key_prefix}__dim{index_source.index(opt)}"
            with st.container(key=row_key):
                checked = st.checkbox(format_func(opt), key=key, disabled=is_disabled)
        else:
            checked = st.checkbox(format_func(opt), key=key, disabled=is_disabled)
        if checked and not (auto_uncheck_all and all_mode == "select_all" and opt == all_value):
            selected.append(opt)
    return selected


def _checkbox_group(options: list, format_func, default_list: list, key_prefix: str,
                    auto_uncheck_all: bool = False, all_value: str = "전체",
                    all_mode: str = "select_all", disable_options: set | None = None,
                    emit_dim_css: bool = True) -> list:
    """
    "1. 공공 출처"처럼 각 항목 앞에 체크박스를 두고 전부 펼쳐서 보여주는 다중 선택 위젯.
    st.multiselect(태그 입력형)와 달리 옵션이 처음부터 전부 눈에 보이고 클릭 한 번으로 체크된다.
    auto_uncheck_all=True일 때 all_mode로 "전체" 동작 방식을 고른다:
    - "select_all" (학년/연도처럼 크롤러가 값 하나씩만 조회 가능한 경우): "전체"를 체크하면
      나머지 개별 항목이 전부 같이 체크되고, 해제하면 같이 해제된다. 개별 항목이 하나라도
      풀리면 "전체" 체크도 자동으로 풀린다.
    - "exclusive" (시험구분/과목처럼 크롤러의 "전체" 자체가 이미 "필터 없음 = 전부"로 동작하는
      경우): "전체"와 개별 항목을 동시에 체크하는 게 무의미하므로 서로 반대쪽을 자동으로
      끈다 - 방금 "전체"를 체크했으면 개별 항목이 풀리고, 개별 항목을 체크했으면 "전체"가 풀린다.
    """
    if auto_uncheck_all:
        _checkbox_group_fix_state(options, default_list, key_prefix, all_value, all_mode)
    return _checkbox_group_render(options, format_func, default_list, key_prefix, all_value, all_mode, auto_uncheck_all,
                                  disable_options=disable_options, emit_dim_css=emit_dim_css)


_ALL_REAL_GRADES = [4, 5, 6]
_ALL_REAL_YEARS = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]
_BASELINE_PORTAL_LATENCY = 0.3  # 초 - 원래 고정 2~6초 추정의 기준이 됐던 응답시간


def _estimate_collection_combos(selected_grades, selected_years, selected_exam_types, selected_subjects, selected_portals):
    """
    실제로 몇 건이 수집될지(조합 수) 계산한다. 학년/연도의 "전체"는 크롤러가 값을 하나씩만
    조회할 수 있어 실제 학년/연도 목록으로 펼쳐지지만, 시험구분/과목의 "전체"는 API가
    "필터 없음"으로 한 번에 처리하므로 펼치지 않는다(진행 팝업의 조합 계산 로직과 동일).
    """
    _grades = selected_grades or ["전체"]
    if _grades == ["전체"]:
        _grades = _ALL_REAL_GRADES
    _years = selected_years or ["전체"]
    if _years == ["전체"]:
        _years = _ALL_REAL_YEARS
    _exam_types = selected_exam_types or ["전체"]
    _subjects = selected_subjects or ["전체"]
    return len(_grades) * len(_years) * len(_exam_types) * len(_subjects) * max(len(selected_portals), 1)


def _estimate_collection_minutes(combo_count: int) -> tuple:
    """
    조합 수 기준 예상 소요 시간을 (하한, 상한, 안내문구) 분 단위로 계산한다. 세션에 방금
    실측해 둔 사이트 응답 속도(portal_latency_probe)가 있으면 그 배율을 반영하고, 없으면
    (예: 아직 확인 팝업을 한 번도 안 띄워봤을 때) 기본 추정치를 그대로 쓴다 - 이 함수 자체는
    네트워크 요청을 하지 않는다(메인 화면이 리렌더링될 때마다 매번 사이트에 핑을 보내면
    안 되므로, 실측은 확인 팝업을 열 때만 한다).
    """
    _probe = st.session_state.get("portal_latency_probe")
    if _probe and _probe.get("latencies"):
        _measured = [v for v in _probe["latencies"].values() if v is not None]
    else:
        _measured = []
    if _measured:
        _avg_latency = sum(_measured) / len(_measured)
        _scale = max(0.3, min(_avg_latency / _BASELINE_PORTAL_LATENCY, 15))
        _speed_note = f"방금 실측한 사이트 응답 속도 기준, 평균 {_avg_latency:.2f}초"
    else:
        _scale = 1.0
        _speed_note = "사이트 응답 속도 미실측 - 기본 추정치"
    return (
        round(combo_count * 2 * _scale / 60, 1),
        round(combo_count * 6 * _scale / 60, 1),
        _speed_note,
    )


def _format_minutes(total_minutes: float) -> str:
    """60분이 넘어가면 '시간 분' 표기로 바꿔서 두 자리 세 자리 숫자를 그대로 보여주지 않는다."""
    if total_minutes < 60:
        return f"{total_minutes:.1f}분"
    hours = int(total_minutes // 60)
    minutes = round(total_minutes % 60)
    if minutes == 60:  # round() 결과 60분이 되는 경계값 보정
        hours += 1
        minutes = 0
    return f"{hours}시간 {minutes}분"


prefs = load_prefs()

# DB 및 모듈 인스턴스 초기화
db_path = os.path.join(DATA_ROOT, "data", "questions.db")
output_dir = os.path.join(DATA_ROOT, "output")
db = QuestionDB(db_path=db_path)
crawler = EBSiCrawler()
template_mgr = TemplateManager(output_dir=output_dir)

# 앱을 처음 열자마자(로컬호스트가 뜬 직후) 조용히 백그라운드 스레드에서 EBSi·평가원
# 응답 속도를 한 번 재둔다 - 화면 렌더링은 막지 않고, 나중에 수집 확인 팝업에서 "예상
# 소요 시간"을 보여줄 때 이 값을 재사용해서 매번 새로 재느라 기다리는 일이 없게 한다.
# @st.cache_resource라 프로세스(서버)당 딱 한 번만 스레드를 띄운다 - 세션이 여러 개
# 열려도, 같은 조합에 대해 중복으로 요청을 보내지 않는다.
@st.cache_resource
def _get_latency_probe_store():
    return {"lock": threading.Lock(), "data": {}, "started": set()}


def _kick_off_background_latency_probe(crawler_instance, portals):
    store = _get_latency_probe_store()
    key = tuple(sorted(portals))
    with store["lock"]:
        if key in store["started"]:
            return
        store["started"].add(key)

    def _worker():
        try:
            latencies = crawler_instance.measure_portal_latency(portals)
        except Exception:
            latencies = {p: None for p in portals}
        with store["lock"]:
            store["data"][key] = {
                "portals": list(key),
                "measured_at": time.time(),
                "latencies": latencies,
            }

    threading.Thread(target=_worker, daemon=True).start()


_kick_off_background_latency_probe(crawler, ["EBSi", "한국교육과정평가원"])

# "빠르다/느리다" 기준: 원래 조합당 2~6초 추정의 기준이 됐던 응답시간(_BASELINE_PORTAL_LATENCY,
# 0.3초)의 약 3배인 1.0초를 문턱으로 잡는다 - 평소보다 눈에 띄게(3배 이상) 느려졌을 때만
# 빨강으로 보여주고, 그 안쪽이면(원래도 사이트마다 0.3~1초 정도는 오갈 수 있으므로) 파랑으로
# "원활"하다고 본다. 응답 실패(타임아웃 등)는 무조건 빨강 처리한다.
_PORTAL_SPEED_FAST_SEC = 1.0


def _get_portal_speed_dot(portal_name: str) -> str:
    """
    출처(EBSi/한국교육과정평가원) 이름 옆에 붙일 응답 속도 표시 점(●)을 HTML로 돌려준다.
    앱을 열 때 조용히 백그라운드에서 재둔 값 중 이 출처를 포함하는 가장 최근 값을 쓰고,
    5분 넘게 지났거나 아직 한 번도 측정되지 않았으면 "확인 중" 회색 점을 보여준다.
    """
    store = _get_latency_probe_store()
    with store["lock"]:
        entries = list(store["data"].values())
    _fresh = None
    for _entry in entries:
        if portal_name in _entry.get("latencies", {}):
            if _fresh is None or _entry["measured_at"] > _fresh["measured_at"]:
                _fresh = _entry

    if _fresh is None or (time.time() - _fresh["measured_at"]) > 300:
        return "<span title='응답 속도 확인 중...' style='color:#94a3b8; font-size:11px;'>●</span>"

    _lat = _fresh["latencies"].get(portal_name)
    if _lat is None:
        return "<span title='응답 없음(타임아웃/오류)' style='color:#dc2626; font-size:11px;'>●</span>"
    if _lat <= _PORTAL_SPEED_FAST_SEC:
        return f"<span title='응답 원활 ({_lat:.2f}초)' style='color:#2563eb; font-size:11px;'>●</span>"
    return f"<span title='응답 느림 ({_lat:.2f}초)' style='color:#dc2626; font-size:11px;'>●</span>"

filter_opts = db.get_filter_options()

def get_header_html(latest_time_str: str, total_q_count: int = 0) -> str:
    logo_html = f"""<div style="background: rgba(255, 255, 255, 0.96); padding: 5px 12px; border-radius: 8px; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 8px rgba(0,0,0,0.12); flex-shrink: 0;"><img src="data:image/png;base64,{logo_b64}" style="height: 38px; object-fit: contain;" alt="부산광역시교육청 로고"/></div>""" if logo_b64 else ""
    return f"""<div style="background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); border-radius: 12px; padding: 12px 22px; color: white; margin-bottom: 4px; box-shadow: 0 4px 16px rgba(30, 58, 138, 0.2); display: flex; align-items: center; gap: 16px; width: 100%; box-sizing: border-box;">
<div style="display: flex; align-items: center; gap: 16px; flex: 1 1 0; min-width: 0;">
{logo_html}
<div style="min-width: 0; flex: 1 1 0;">
<div style="font-size: 18px; font-weight: 800; letter-spacing: -0.3px; display: flex; align-items: center; gap: 8px; white-space: nowrap; min-width: 0;">
<span style="background: rgba(255,255,255,0.22); padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 700; white-space: nowrap; flex-shrink: 0;">2026 공모전 [교육-001]</span>
<span style="overflow: hidden; text-overflow: ellipsis; min-width: 0;">기출 문제 크롤링 및 단원별 기출정리집 문서 자동 생성</span>
</div>
<div style="font-size: 13.5px; margin-top: 3px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
EBSi·평가원 공공 포털 실시간 기출 수집 & 단원별 기출정리집 문서 자동 생성
</div>
</div>
</div>
<div style="text-align: right; flex: 0 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; line-height: 1.55; white-space: nowrap;">
<div style="font-size: 15.5px; color: #fff; font-weight: 600;">최근 수집 <span style="font-size: 15.5px; color: #fff; font-weight: 800;">{latest_time_str}</span></div>
<div style="font-size: 15.5px; color: #fff; font-weight: 600;">총 <span style="font-size: 15.5px; color: #fff; font-weight: 800;">{total_q_count:,}</span>문항 수집됨</div>
</div>
</div>"""

# 최근 생성일 및 DB 총 문항 수 안전 동기화
if "latest_gen_time" not in st.session_state:
    try:
        st.session_state["latest_gen_time"] = db.get_latest_generation_time()
    except Exception:
        st.session_state["latest_gen_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")

try:
    st.session_state["total_question_count"] = db.get_total_question_count()
except Exception:
    st.session_state["total_question_count"] = 0

header_placeholder = st.empty()
header_placeholder.markdown(get_header_html(st.session_state["latest_gen_time"], st.session_state["total_question_count"]), unsafe_allow_html=True)

# ==============================================================================
# 메인 2단 레이아웃 (좌측: 세로 설정 패널, 우측: 실시간 결과 및 미리보기)
# ==============================================================================
if "app_mode" not in st.session_state:
    st.session_state["app_mode"] = "문항 수집"

# 키보드 단축키 (숫자키 1, 2) 메인 윈도우 직접 바인딩
st.components.v1.html("""
<script>
(function() {
    const pDoc = window.parent.document;
    const keyHandler = function(e) {
        var tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (e.target && e.target.isContentEditable)) {
            return;
        }
        
        if (e.key === '1' || e.code === 'Digit1' || e.code === 'Numpad1') {
            var btns = pDoc.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                var txt = (btns[i].innerText || '').trim();
                if (txt.includes('문항 수집')) {
                    btns[i].click();
                    break;
                }
            }
        } else if (e.key === '2' || e.code === 'Digit2' || e.code === 'Numpad2') {
            var btns = pDoc.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                var txt = (btns[i].innerText || '').trim();
                if (txt === '🖨️ 인쇄' || txt === '🖨️ 출력' || (txt.startsWith('🖨️') && !txt.includes('한글') && !txt.includes('다운로드'))) {
                    btns[i].click();
                    break;
                }
            }
        }
    };

    if (window.parent._tabShortcutHandler) {
        window.parent.document.removeEventListener('keydown', window.parent._tabShortcutHandler, true);
    }
    window.parent._tabShortcutHandler = keyHandler;
    window.parent.document.addEventListener('keydown', keyHandler, true);
})();
</script>
""", height=0)

# 팝업(st.dialog) 창을 마우스로 드래그해서 옮길 수 있게 - Streamlit 다이얼로그 자체에는
# 이동 기능이 없어서, 부모 문서에 MutationObserver를 심어 다이얼로그가 뜰 때마다
# 제목 표시줄(맨 위 영역)을 드래그 핸들로 만든다.
st.components.v1.html("""
<script>
(function() {
    const pDoc = window.parent.document;

    function makeDraggable(box) {
        if (box.dataset.dragInit) return;
        box.dataset.dragInit = "1";
        box.style.position = "fixed";

        let dragging = false, startX = 0, startY = 0, startLeft = 0, startTop = 0;

        const onDown = function(e) {
            // 버튼/입력/체크박스 등 실제 조작 요소를 클릭했을 땐 드래그를 시작하지 않는다.
            if (e.target.closest('button, input, a, label, [role="button"]')) return;
            const rect = box.getBoundingClientRect();
            dragging = true;
            startX = e.clientX;
            startY = e.clientY;
            startLeft = rect.left;
            startTop = rect.top;
            box.style.margin = "0";
            box.style.transition = "none";
            e.preventDefault();
        };
        const onMove = function(e) {
            if (!dragging) return;
            box.style.left = (startLeft + (e.clientX - startX)) + "px";
            box.style.top = (startTop + (e.clientY - startY)) + "px";
        };
        const onUp = function() { dragging = false; };

        box.style.cursor = "move";
        box.addEventListener("mousedown", onDown);
        pDoc.addEventListener("mousemove", onMove);
        pDoc.addEventListener("mouseup", onUp);
    }

    const observer = new MutationObserver(function() {
        const overlay = pDoc.querySelector('div[data-testid="stDialog"]');
        if (overlay) {
            const box = overlay.querySelector('div[role="dialog"]') || overlay.firstElementChild;
            if (box) makeDraggable(box);
        }
    });
    observer.observe(pDoc.body, { childList: true, subtree: true });
})();
</script>
""", height=0)

st.markdown("""
<style>
/* 보이지 않는 스크립트 iframe 및 컴포넌트 여백 완전 제거 */
iframe[height="0"], div[data-testid="stCustomComponentV1"]:has(iframe[height="0"]), div[data-testid="element-container"]:has(iframe[height="0"]) {
    display: none !important;
    height: 0px !important;
    margin: 0px !important;
    padding: 0px !important;
}

/* 상단/하단 모드 전환 탭 버튼 (문항 수집 / 출력) 완전한 수직/수평 중앙 정렬 및 고정 높이 44px */
div.st-key-btn_mode_collect button,
div.st-key-btn_mode_output button,
div.st-key-btn_mode_bottom_output button,
div.st-key-btn_mode_collect button[kind="primary"],
div.st-key-btn_mode_output button[kind="primary"],
div.st-key-btn_mode_bottom_output button[kind="primary"],
div.st-key-btn_mode_collect button[kind="secondary"],
div.st-key-btn_mode_output button[kind="secondary"],
div.st-key-btn_mode_bottom_output button[kind="secondary"] {
    height: 44px !important;
    min-height: 44px !important;
    max-height: 44px !important;
    padding: 0px 14px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-sizing: border-box !important;
    margin-top: 0px !important;
    margin-bottom: 0px !important;
}

div.st-key-btn_mode_collect button div[data-testid="stMarkdownContainer"],
div.st-key-btn_mode_output button div[data-testid="stMarkdownContainer"],
div.st-key-btn_mode_bottom_output button div[data-testid="stMarkdownContainer"],
div.st-key-btn_mode_collect button div,
div.st-key-btn_mode_output button div,
div.st-key-btn_mode_bottom_output button div {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    height: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
}

div.st-key-btn_clear_all button p {
    font-size: 13px !important;
    font-weight: 800 !important;
    color: #dc2626 !important;
}

div.st-key-btn_mode_top_preview button:disabled,
div.st-key-btn_mode_bottom_preview button:disabled {
    opacity: 0.4 !important;
    cursor: not-allowed !important;
}

div.st-key-btn_mode_collect button p,
div.st-key-btn_mode_output button p,
div.st-key-btn_mode_bottom_output button p {
    font-size: 16px !important;
    font-weight: 700 !important;
    line-height: 1 !important;
    margin: 0 !important;
    padding: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}

button[kind="secondary"] {
    background: #f1f5f9 !important;
    color: #475569 !important;
    font-size: 16.5px !important;
    font-weight: 700 !important;
    border-radius: 10px !important;
    border: 1.5px solid #cbd5e1 !important;
    box-shadow: none !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}
button[kind="secondary"]:hover {
    background: #e2e8f0 !important;
    color: #1e3a8a !important;
    border-color: #94a3b8 !important;
}

/* 상단 모드 전환 버튼 전용: 버튼 바로 아래에 나타나는 깔끔한 하단 툴팁 */
div.st-key-btn_mode_collect, div.st-key-btn_mode_output, div.st-key-btn_mode_bottom_output, div[data-testid="column"] {
    position: relative !important;
    overflow: visible !important;
}

div.st-key-btn_mode_collect button, div.st-key-btn_mode_output button, div.st-key-btn_mode_bottom_output button {
    position: relative !important;
    overflow: visible !important;
}

div.st-key-btn_mode_collect button:hover::after {
    content: "단축키: 숫자키 1" !important;
    position: absolute !important;
    top: calc(100% + 7px) !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    background: #ffffff !important;
    color: #0f172a !important;
    font-size: 11.5px !important;
    font-weight: 700 !important;
    padding: 3px 8px !important;
    border-radius: 6px !important;
    border: 1.5px solid #cbd5e1 !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
    white-space: nowrap !important;
    z-index: 99999 !important;
    pointer-events: none !important;
    line-height: 1.4 !important;
}

div.st-key-btn_mode_output button:hover::after,
div.st-key-btn_mode_bottom_output button:hover::after {
    content: "단축키: 숫자키 2" !important;
    position: absolute !important;
    top: calc(100% + 7px) !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    background: #ffffff !important;
    color: #0f172a !important;
    font-size: 11.5px !important;
    font-weight: 700 !important;
    padding: 3px 8px !important;
    border-radius: 6px !important;
    border: 1.5px solid #cbd5e1 !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
    white-space: nowrap !important;
    z-index: 99999 !important;
    pointer-events: none !important;
    line-height: 1.4 !important;
}

/* 동그라미 물음표 및 위젯 툴팁 안내 팝업 글자 크기 (기존보다 1 작게 설정) */
div[data-baseweb="tooltip"],
div[data-baseweb="popover"],
div[role="tooltip"],
div[data-testid="stTooltipContent"],
.stTooltipContent {
    font-size: 12.5px !important;
    line-height: 1.5 !important;
}
div[data-baseweb="tooltip"] *,
div[data-baseweb="popover"] *,
div[role="tooltip"] *,
div[data-testid="stTooltipContent"] * {
    font-size: 12.5px !important;
    line-height: 1.5 !important;
}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 상단 헤더 바 (좌측: 모드 전환 탭 44px, 우측: 수집 통계 배너 44px)
# ==============================================================================
col_top_banner, col_collapse_toggle, col_reset_cond, col_collect, col_more = st.columns([0.62, 2.3, 1.55, 1.0, 0.36], gap="small", vertical_alignment="center")

st.session_state.setdefault("filter_panel_collapsed", False)
with col_collapse_toggle:
    _collapsed_now = st.session_state["filter_panel_collapsed"]
    if st.button(
        "펼치기" if _collapsed_now else "접기",
        icon=":material/keyboard_double_arrow_down:" if _collapsed_now else ":material/keyboard_double_arrow_up:",
        type="tertiary", use_container_width=True, key="btn_toggle_filter_panel",
        help="조건 패널 펼치기" if _collapsed_now else "조건 패널 접기",
    ):
        st.session_state["filter_panel_collapsed"] = not _collapsed_now
        st.rerun()

with col_reset_cond:
    _rc_col1, _rc_col2 = st.columns(2, gap="small")
    with _rc_col1:
        if st.button("전체 선택", type="secondary", icon=":material/done_all:", use_container_width=True, key="btn_select_all_filters"):
            st.session_state["t1_ebsi"] = True
            st.session_state["t1_kice"] = True
            st.session_state["t1_grade_전체"] = True
            st.session_state["t1_year_전체"] = True
            st.session_state["t1_exam_type_전체"] = True
            st.session_state["t1_subject_전체"] = True
            st.rerun()
    with _rc_col2:
        if st.button("초기화", type="secondary", icon=":material/restart_alt:", use_container_width=True, key="btn_reset_filters"):
            for _k in list(st.session_state.keys()):
                if _k.startswith("t1_"):
                    st.session_state[_k] = False
            st.rerun()

with col_collect:
    if st.button(
        "문항 수집",
        type="primary",
        icon=":material/download:",
        use_container_width=True,
        key="btn_mode_collect"
    ):
        st.session_state["app_mode"] = "문항 수집"
        # "다음부터 이 팝업 열지 않고 바로 수집 시작하기"를 체크해뒀으면 확인 팝업을 건너뛰고
        # 바로 크롤링 진행 팝업으로 간다.
        st.session_state["collect_stage"] = "running" if prefs.get("skip_confirm_popup") else "confirm"
        # 여기서 st.rerun()을 부르면 이 스크립트 실행이 즉시 중단되어, 아직 한 번도
        # 렌더링되지 않은 아래쪽 체크박스들의 session_state가 지워져 예전 기본값으로
        # 되돌아가는 버그가 있었다(2026-09-18). rerun 없이 끝까지 흘려보낸다.

with col_more:
    with st.popover(":material/more_horiz:", use_container_width=True, help="더보기"):
        st.caption("수집해 둔 모든 문항이 삭제되며 되돌릴 수 없습니다.")
        if st.button("수집 문항 모두 지우기", type="secondary", icon=":material/delete:", use_container_width=True, key="btn_clear_all"):
            db.clear_database()
            st.rerun()

with col_top_banner:
    stats = db.get_collection_statistics()
    total_collected = stats["total_questions"]
    latest_time = st.session_state.get("latest_gen_time", datetime.now().strftime("%Y-%m-%d %H:%M"))

    # 제목 옆에 "현재 조건에 맞는 문항 수"를 크게 보여주기 위해 자리만 잡아두고,
    # 5개 조건이 모두 정해진 뒤(아래 필터 패널 렌더링 끝)에 실제 값을 채운다.
    _cond_title_slot = st.empty()
    _COND_TITLE_HTML = "<span style='font-size:17px; font-weight:800; color:#0f172a;'>조건 선택</span>"
    _cond_title_slot.markdown(f"<div style='white-space:nowrap;'>{_COND_TITLE_HTML}</div>", unsafe_allow_html=True)

if st.session_state.get("just_collected"):
    last_portals = st.session_state.get("last_crawl_portals", [])
    st.markdown(f"""
    <div style="background: #eff6ff; border: 1.5px solid #3b82f6; border-radius: 10px; padding: 0 16px; height: 44px; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center; box-sizing: border-box;">
        <div style="display: flex; align-items: center; gap: 8px; overflow: hidden; white-space: nowrap;">
            <span style="font-size: 17.5px; font-weight: 700; color: #1e40af;">🎉 총 {len(last_portals)}개 공공 포털 수집 및 DB 인덱싱 완료</span>
            <span style="font-size: 17.5px; color: #3b82f6; font-weight: 500;">(수집 일시: {latest_time})</span>
        </div>
        <div style="text-align: right; flex-shrink: 0;">
            <span style="font-size: 17.5px; font-weight: 800; color: #1d4ed8;">총 {total_collected:,}문항</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# 조합이 많아 오래 걸릴 수 있다는 경고를 상단(항상 보이는 버튼 줄 바로 아래)에 고정해
# 둘 자리 - 실제 내용은 5. 과목까지 다 그려진 뒤에야 계산되므로(st.empty()로 미리 자리만
# 잡아두고) 나중에 그 내용을 채워 넣는다. 원래 필터 그리드 맨 아래에 있어서 스크롤해야
# 보였던 것을, 스크롤 없이 바로 보이게 옮긴 것(2026-09-19 피드백).
_combo_warning_placeholder = st.empty()

# ==============================================================================
# 조건 필터 (가로 배치) - 세로로 길어지는 것을 막기 위해 좌측 패널에서 분리해
# 화면 상단에 4개 항목을 한 줄로 펼친다.
# ==============================================================================
_fp_state = (
    "max-height:0 !important; opacity:0; margin-top:0 !important; margin-bottom:0 !important; "
    "padding-top:0 !important; padding-bottom:0 !important; border-width:0 !important; pointer-events:none;"
    if st.session_state["filter_panel_collapsed"] else "max-height:720px; opacity:1;"
)
# 접힌 상태에서는 높이 0인 패널이 남기는 위아래 간격(요소 사이 gap)을 줄여 툴바와 구분선 사이 여백을 좁힌다
_fp_gap_fix = (
    "div[data-testid='stLayoutWrapper']:has(> .st-key-filter_panel_wrapper) { margin-top:-9.9px; } "
    if st.session_state["filter_panel_collapsed"] else ""
)
st.markdown(
    "<style>" + _fp_gap_fix +
    "div.st-key-filter_panel_wrapper { overflow:hidden; "
    "transition: max-height .45s cubic-bezier(.4,0,.2,1), opacity .3s ease, padding .45s ease, margin .45s ease; "
    + _fp_state + " }"
    # 헤더 버튼 공통 스타일: 보조(secondary)=연한 테두리 40px, 접기 토글=아이콘 정사각형
    "div.st-key-btn_select_all_filters button, div.st-key-btn_reset_filters button, div.st-key-btn_clear_all button "
    "{ height:40px; min-height:40px; border-radius:10px; border:1px solid #94a3b8; background:#fff; color:#0f172a; "
    "font-weight:700; font-size:14px; padding:0 8px; transition: background .15s, border-color .15s; }"
    "div.st-key-btn_select_all_filters button:hover, div.st-key-btn_reset_filters button:hover "
    "{ background:#f1f5f9; border-color:#94a3b8; color:#0f172a; }"
    "div.st-key-btn_clear_all button { color:#dc2626; border-color:#fecaca; } "
    "div.st-key-btn_clear_all button:hover { background:#fef2f2; border-color:#f87171; }"
    "div.st-key-btn_mode_collect button { height:40px !important; min-height:40px !important; border-radius:10px !important; }"
    "div.st-key-btn_toggle_filter_panel button { height:36px; width:100%; min-height:40px; border-radius:10px; "
    "border:1px solid #94a3b8; background:#fff; color:#0f172a; padding:0; transition: background .15s, transform .2s; }"
    "div.st-key-btn_toggle_filter_panel button:hover { background:#f1f5f9; }"
    "div.st-key-btn_select_all_filters button p, div.st-key-btn_reset_filters button p, "
    "div[class*='st-key-btn_mode_bottom_preview'] button p, div[class*='st-key-btn_mode_top_preview'] button p "
    "{ font-weight:800 !important; }"
    "div.st-key-filter_panel_wrapper [data-testid='stCheckbox'] label p { color:#0f172a; font-weight:600; }"
    "div.st-key-btn_toggle_filter_panel button span[data-testid='stIconMaterial'] { font-size:22px; } div.st-key-btn_toggle_filter_panel button p { font-weight:700; font-size:14px; }"
    "div[class*='st-key-btn_mode_bottom_preview'] button, div[class*='st-key-t2_quick_dl_'] button, div[class*='st-key-btn_mode_top_preview'] button "
    "{ height:40px; min-height:40px; border-radius:10px; border:1px solid #94a3b8; background:#fff; color:#0f172a; font-weight:700; font-size:14px; }"
    "div[class*='st-key-btn_mode_bottom_preview'] button:hover, div[class*='st-key-t2_quick_dl_'] button:hover { background:#f1f5f9; border-color:#94a3b8; color:#0f172a; }"
    "div[class*='st-key-save_local_'] button { height:44px; min-height:44px; border-radius:10px; font-weight:700; font-size:15.5px; }"
    "div[class*='st-key-out_row_'] > div > [data-testid='stHorizontalBlock'], div[class*='st-key-out_row_'] [data-testid='stHorizontalBlock'] { justify-content:flex-start !important; }"
    "div[class*='st-key-out_row_'] [data-testid='stHorizontalBlock'] > [data-testid='stColumn'] { flex:0 0 auto !important; min-width:0 !important; margin-left:auto; width:calc(0.1252 * (100% - 66px)) !important; }"
    "div[class*='st-key-out_row_'] [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:first-child { margin-left:0; }"
    "div[class*='st-key-out_row_'] > div > [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:nth-child(2):nth-last-child(3) { flex:0 0 223px !important; width:223px !important; margin:0 0 0 calc(((50% + 7.7px - 0.1252 * (100% - 66px)) - 223px) / 2 - 16.5px) !important; }"
    "div[class*='st-key-out_row_'] > div > [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:nth-child(3):nth-last-child(2) { margin-left:calc((50% + 7.7px - 0.1252 * (100% - 66px)) / 2 - 128px) !important; }"
    "div[class*='st-key-out_row_'] [data-testid='stButtonGroup'] button { background:#fff; border:1px solid #94a3b8; color:#0f172a; }"
    "div[class*='st-key-out_row_'] [data-testid='stButtonGroup'] button[aria-checked='true'] { background:#dbeafe !important; border-color:#3b82f6 !important; color:#1d4ed8 !important; }"
    "div[class*='st-key-out_row_'] [data-testid='stButtonGroup'] button[aria-checked='true'] p { color:#1d4ed8 !important; font-weight:800 !important; }"
    "div[class*='st-key-out_row_'] [data-testid='stButtonGroup'] button { height:36px !important; min-height:36px !important; font-weight:700; font-size:14px; }"
    "div[class*='st-key-out_row_'] [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:last-child { width:calc(0.1695 * (100% - 66px)) !important; margin-right:calc(0.05 * (100% - 66px) + 16.5px); margin-left:auto !important; }"
    "div[class*='st-key-out_row_'] > div > [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:nth-last-child(2) { flex:0 0 auto !important; width:calc(27.31% - 21.4px) !important; margin-left:calc(50% + 7.7px - 0.1252 * (100% - 66px) - 16.5px) !important; margin-right:0 !important; }"
    "div[class*='st-key-split_'] [data-testid='stHorizontalBlock'] { gap:1px !important; flex-wrap:nowrap !important; }"
    "div[class*='st-key-split_'] [data-testid='stColumn']:first-child button { padding:0 6px !important; gap:4px !important; }"
    "div[class*='st-key-split_'] [data-testid='stColumn']:first-child button p { font-size:14.5px !important; white-space:nowrap !important; overflow:visible !important; text-overflow:clip !important; }"
    "div[class*='st-key-out_row_'] div[class*='st-key-split_'] [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:first-child { flex:1 1 0 !important; width:auto !important; margin:0 !important; }"
    "div[class*='st-key-out_row_'] div[class*='st-key-split_'] [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:last-child { flex:0 0 40px !important; width:40px !important; margin:0 !important; }"
    "div[class*='st-key-split_'] [data-testid='stColumn']:first-child button { border-radius:10px 0 0 10px !important; }"
    "div[class*='st-key-split_'] [data-testid='stPopover'] button { justify-content:center !important; padding:0 !important; }"
    "div[class*='st-key-split_'] [data-testid='stPopover'] button > div > div:first-child { display:none !important; }"
    "div[class*='st-key-split_'] [data-testid='stPopover'] button > div[aria-hidden='true'] { margin:0 !important; position:static !important; }"
    "div[class*='st-key-split_'] [data-testid='stColumn']:last-child button { border-radius:0 10px 10px 0 !important; height:40px !important; min-height:40px !important; }"
    "div[class*='st-key-folder_chip_'] { background:#f8fafc; border:1px solid #cbd5e1; border-radius:10px; padding:0 12px !important; box-sizing:border-box; height:40px !important; min-height:40px !important; display:flex; align-items:center; }"
    "div[class*='st-key-folder_chip_'] > div { gap:0 !important; }"
    "div[class*='st-key-folder_chip_'] [data-testid='stHorizontalBlock'] { flex-wrap:nowrap !important; gap:4px !important; align-items:center !important; transform:translateY(4px); } div[class*='st-key-folder_chip_'] [data-testid='stColumn'] { min-width:0 !important; } div[class*='st-key-folder_chip_'] [data-testid='stColumn']:first-child { overflow:hidden; }"
    "div[class*='st-key-out_row_'] div[class*='st-key-folder_chip_'] [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:first-child { flex:1 1 0 !important; width:auto !important; margin:0 !important; overflow:visible; transform:translateY(-8.25px); }"
    "div[class*='st-key-out_row_'] div[class*='st-key-folder_chip_'] [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:not(:first-child) { flex:0 0 44px !important; width:44px !important; margin:0 !important; }"
    "div[class*='st-key-open_folder_'] button p, div[class*='st-key-change_folder_'] button p { font-weight:800 !important; font-size:14.5px !important; color:#0f172a !important; }"
    "div[class*='st-key-open_folder_'] button, div[class*='st-key-change_folder_'] button { height:30px !important; min-height:30px !important; width:100% !important; padding:0 4px; font-weight:700; font-size:13.5px; margin-left:auto; color:#334155 !important; border-radius:8px; }"
    "div[class*='st-key-open_folder_'] button:hover, div[class*='st-key-change_folder_'] button:hover { background:#e2e8f0 !important; }"
    "div[class*='st-key-open_folder_'] button, div[class*='st-key-change_folder_'] button { height:32px; min-height:32px; font-size:13px; color:#1e293b; font-weight:600; }"
    "/* 통일 규칙: 보조=흰 배경+진한 테두리 40px, 주요=파란 채움 40px, 접기=텍스트 */"
    "div.st-key-btn_select_all_filters button, div.st-key-btn_reset_filters button, div[class*='st-key-btn_mode_bottom_preview'] button, div[class*='st-key-btn_mode_top_preview'] button, div[class*='st-key-t2_quick_dl_'] button { height:40px !important; min-height:40px !important; border-radius:10px !important; background:#fff !important; border:1px solid #94a3b8 !important; color:#0f172a !important; }"
    "div.st-key-btn_select_all_filters button:hover, div.st-key-btn_reset_filters button:hover, div[class*='st-key-btn_mode_bottom_preview'] button:hover, div[class*='st-key-btn_mode_top_preview'] button:hover, div[class*='st-key-t2_quick_dl_'] button:hover { background:#f1f5f9 !important; border-color:#64748b !important; }"
    "div.st-key-btn_select_all_filters button p, div.st-key-btn_reset_filters button p, div[class*='st-key-btn_mode_bottom_preview'] button p, div[class*='st-key-btn_mode_top_preview'] button p, div[class*='st-key-t2_quick_dl_'] button p { font-weight:700 !important; font-size:15px !important; color:#0f172a !important; }"
    "div.st-key-btn_mode_collect button, div.st-key-btn_mode_collect button[kind=\"primary\"], div[class*='st-key-save_local_'] button, div[class*='st-key-save_local_'] button p { height:40px !important; min-height:40px !important; border-radius:10px !important; font-weight:700 !important; font-size:14px !important; box-shadow:0 2px 6px rgba(37,99,235,.28) !important; }"
    "div.st-key-btn_mode_collect button p, div[class*='st-key-save_local_'] button p { height:auto !important; min-height:0 !important; font-weight:700 !important; font-size:14.5px !important; box-shadow:none !important; }"
    "div[data-testid='stMarkdownContainer'] hr { margin-top:0 !important; margin-bottom:1rem !important; }"
    "div.st-key-btn_toggle_filter_panel { display:flex; justify-content:center; } div.st-key-btn_toggle_filter_panel > div { width:auto !important; } div.st-key-btn_toggle_filter_panel button { width:auto !important; padding:0 16px !important; height:40px !important; border:none !important; background:transparent !important; box-shadow:none !important; color:#0f172a !important; }"
    "div.st-key-btn_toggle_filter_panel button:hover { background:#f1f5f9 !important; }"
    "</style>",
    unsafe_allow_html=True,
)

# 하위 항목 옆에 표시할 "현재 DB에 수집되어 있는 문항 수" 괄호 표기용 집계 - stats는
# 위쪽 col_top_banner에서 이미 계산돼 있어 재사용한다 (재조회 방지).
_cnt_by_portal = {r["name"]: r["cnt"] for r in stats["by_portal"]}
_cnt_by_grade = {r["grade"]: r["cnt"] for r in stats["by_grade"]}
_cnt_by_year = {r["year"]: r["cnt"] for r in stats["by_year"]}
_cnt_by_exam_type = {r["exam_type"]: r["cnt"] for r in stats["by_exam_type"]}
_cnt_by_subject = {r["subject_name"]: r["cnt"] for r in stats["by_subject"]}
# DB에는 중복 정리 시 "대학수학능력시험 (수능)" -> "수능"으로 표준화되어 저장된다.
_exam_type_db_key = {"대학수학능력시험 (수능)": "수능"}

with st.container(border=True, key="filter_panel_wrapper"):
    # "1. 공공 출처"는 링크 텍스트 + 문항 수가 길어 다른 칸과 동일 너비로 나누면 숫자가
    # 잘려 보인다(2026-09-19 실측) - 이 칸만 조금 더 넓게 배분한다.
    filt_col0, filt_col2, filt_col3, filt_col4a, filt_col4b = st.columns([1.3, 1, 1, 1, 1], gap="medium")

    with filt_col0:
        st.markdown("**1. 공공 출처**")
        _n_ebsi = _cnt_by_portal.get("EBSi 국가 교육 포털", 0)
        _n_kice = _cnt_by_portal.get("한국교육과정평가원 (KICE)", 0)
        st.session_state.setdefault("t1_ebsi", prefs.get("cb_ebsi", False))
        st.session_state.setdefault("t1_kice", prefs.get("cb_kice", False))
        # 체크박스 라벨 안의 링크는 클릭이 체크 토글에 먹혀 이동이 안 되므로, 체크박스는 라벨 없이
        # 두고 이름+문항수는 옆에 일반 링크로 따로 그린다(링크 클릭은 체크 상태를 바꾸지 않는다).
        with st.container(key="portal_rows"):
            _pc1, _pc2 = st.columns([1, 9], vertical_alignment="center")
            with _pc1:
                cb_kice = st.checkbox("한국교육과정평가원", key="t1_kice", label_visibility="collapsed")
            with _pc2:
                st.markdown(
                    f"{_get_portal_speed_dot('한국교육과정평가원')} [한국교육과정평가원 (KICE)](https://www.kice.re.kr) ({_n_kice:,}문항)",
                    unsafe_allow_html=True,
                )
            _pc3, _pc4 = st.columns([1, 9], vertical_alignment="center")
            with _pc3:
                cb_ebsi = st.checkbox("EBSi 국가 교육 포털", key="t1_ebsi", label_visibility="collapsed")
            with _pc4:
                st.markdown(
                    f"{_get_portal_speed_dot('EBSi')} [EBSi 국가 교육 포털](https://www.ebsi.co.kr) ({_n_ebsi:,}문항)",
                    unsafe_allow_html=True,
                )
        # EBSi를 체크했을 때만 아래에 해설 자동 수집 영역이 활성화된다(내용은 필터 값이 다
        # 만들어진 뒤 아래쪽에서 이 자리에 채워 넣는다).
        ebsi_solution_slot = st.container(key="ebsi_solution_slot")
        st.markdown(
            "<style>div.st-key-ebsi_solution_slot [data-testid='stExpander'],"
            "div.st-key-ebsi_solution_slot [data-testid='stExpander'] details"
            " { border: none !important; box-shadow: none !important; }"
            "div.st-key-ebsi_solution_slot summary span:has(> [data-testid='stIconMaterial']),"
            "div.st-key-ebsi_solution_slot summary [data-testid='stIconMaterial']"
            " { display: none !important; }"
            # 로그인 안내 캡션: 제목의 "EBSi" 글자 시작 위치(자물쇠 이모지 폭만큼, 실측 37px)에 맞추고 더 작게
            "div.st-key-ebsi_solution_slot .ebsi-login-note"
            " { padding-left: 1.4px; margin-top: -13.4px; font-size: 13px; color:#475569; }"
            # 체크박스 열은 폭을 24px로 고정하고 열 사이 간격을 없애, 체크박스와 제목 글자 사이
            # 간격(예전 27.5px)을 약 1/4(6.9px)로 줄인다. 화면 폭이 달라도 같은 간격이 유지된다.
            "div.st-key-ebsi_solution_slot [data-testid='stHorizontalBlock'] { column-gap: 0 !important; gap: 0 !important; }"
            "div.st-key-ebsi_solution_slot [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:first-child"
            " { flex: 0 0 24px !important; width: 24px !important; min-width: 24px !important; }"
            "div.st-key-ebsi_solution_slot [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:last-child"
            " { flex: 1 1 0 !important; width: auto !important; min-width: 0 !important; }"
            "div.st-key-ebsi_solution_slot summary { padding-left: 1.4px !important; }"
            # 포털 줄과 해설 수집 줄 사이 간격(실측 18.9px)을 절반으로
            # 해설 수집 체크박스를 위 포털 이름의 첫 글자("E") 밑으로 들여쓰기(실측 37px)
            "div.st-key-ebsi_solution_slot { margin-top: -9.4px; padding-left: 25.4px; }"
            # KICE / EBSi 출처 줄도 같은 방식으로 체크박스와 이름 사이 간격을 좁힌다(글자 시작 위치 25.4px).
            # 필터 패널 전체 열 묶음까지 잡지 않도록 출처 줄만 담은 전용 컨테이너(portal_rows) 안에만 적용한다.
            "div.st-key-portal_rows [data-testid='stHorizontalBlock'] { column-gap: 0 !important; gap: 0 !important; }"
            "div.st-key-portal_rows [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:first-child"
            " { flex: 0 0 25.4px !important; width: 25.4px !important; min-width: 25.4px !important; }"
            "div.st-key-portal_rows [data-testid='stHorizontalBlock'] > [data-testid='stColumn']:last-child"
            " { flex: 1 1 0 !important; width: auto !important; min-width: 0 !important; }</style>",
            unsafe_allow_html=True,
        )

        selected_portals = []
        if cb_kice: selected_portals.append("한국교육과정평가원")
        if cb_ebsi: selected_portals.append("EBSi")

        st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

        # 로그인 필요 출처 확장 슬롯 (현재 등록된 출처 없음 — crawler/login_required/__init__.py 참고)
        login_selected_sources = []

        st.markdown("<div style='margin-top: 4px; margin-bottom: 4px; border-top: 1px solid #e2e8f0;'></div>", unsafe_allow_html=True)
        # 2. 학년 (고3 ~ 고1 역순 배치) — EBSi/KICE 모두 초등학교·중학교 기출문항을
        # 제공하지 않아(coverage: EBSi 고1~고3, KICE 고3 수능) 초·중등 학년 옵션은 제외한다.
        grade_options = [
            "전체",
            6, 5, 4,
        ]
        grade_labels = {
            "전체": "전체 (고1 ~ 고3)",
            4: "고등학교 1학년 (고1)",
            5: "고등학교 2학년 (고2)",
            6: "고등학교 3학년 (고3)"
        }
        # 문서 머리말처럼 한 줄로 짧게 표기해야 하는 자리에서 "고등학교 3학년 (고3)" 같은
        # 중복 표기 대신 "고3"만 쓰기 위한 축약형 (체크박스 라벨용 grade_labels는 그대로 유지)
        grade_labels_short = {
            "전체": "고1~고3 전체",
            4: "고1",
            5: "고2",
            6: "고3"
        }
        # KICE는 고3 수능 자료만 다뤄(고1/고2 자료 없음) - 체크된 출처로는 절대 안 나올
        # 학년은 아예 선택 못 하게 막는다. 출처를 하나도 안 골랐으면 전부 막는다.
        _EBSI_GRADE_SET = {4, 5, 6}
        _KICE_GRADE_SET = {6}
        # 출처를 아직 하나도 안 골랐을 때는 "아직 뭐가 되는지 모른다"일 뿐이지 "아무것도
        # 안 된다"가 아니다 - 첫 화면부터 2번을 전부 비활성화해버리면 화면이 고장난 것처럼
        # 보인다는 피드백(2026-09-19)에 따라, 출처를 하나라도 고른 뒤에만 실제로 안 되는
        # 학년을 걸러낸다.
        _grade_disable_set = set()
        if cb_ebsi or cb_kice:
            for _g in grade_options:
                if _g == "전체":
                    continue
                _from_ebsi = cb_ebsi and _g in _EBSI_GRADE_SET
                _from_kice = cb_kice and _g in _KICE_GRADE_SET
                if not (_from_ebsi or _from_kice):
                    _grade_disable_set.add(_g)
        # 선택 가능한 학년이 KICE만 체크했을 때의 고3처럼 딱 하나로 좁혀지면, 매번 손으로
        # 체크하지 않아도 되도록 그 하나를 자동으로 체크해준다.
        _grade_enabled = [g for g in grade_options if g != "전체" and g not in _grade_disable_set]
        if len(_grade_enabled) == 1:
            st.session_state[f"t1_grade_{_grade_enabled[0]}"] = True
        # 비활성화되는 항목의 흐림 CSS를 제목에 얹어서 함께 출력한다 - 별도 markdown
        # 호출을 새로 만들면 그 자체가 flex 목록에 끼어들어 목록 전체가 밀린다
        # (2026-09-18 "5. 과목"에서 실측 확인, 2. 학년/4. 시험 구분에도 동일 적용).
        st.markdown(f"<strong>2. 학년 (복수 선택 가능)</strong>{_dim_css_html(grade_options, _grade_disable_set, grade_options, 't1_grade')}", unsafe_allow_html=True)
        _saved_grades = _pref_list(prefs, "grade")
        selected_grades = _checkbox_group(
            grade_options,
            format_func=lambda x: f"{grade_labels.get(x, f'{x}학년')} ({total_collected if x == '전체' else _cnt_by_grade.get(x, 0):,}문항)",
            default_list=[g for g in _saved_grades if g in grade_options],
            key_prefix="t1_grade",
            disable_options=_grade_disable_set,
            auto_uncheck_all=True,
            emit_dim_css=False,
        )
        selected_grade = selected_grades[0] if selected_grades else "전체"

    with filt_col2:
        # 3. 시험 연도
        year_options = ["전체", 2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]
        year_labels = {
            "전체": "전체 (2018 ~ 2026년)",
            2026: "2026년",
            2025: "2025년",
            2024: "2024년",
            2023: "2023년",
            2022: "2022년",
            2021: "2021년",
            2020: "2020년",
            2019: "2019년",
            2018: "2018년"
        }
        st.markdown("**3. 시험 연도 (복수 선택 가능)**")
        _saved_years = _pref_list(prefs, "year")
        selected_years = _checkbox_group(
            year_options,
            format_func=lambda x: f"{year_labels.get(x, f'{x}년')} ({total_collected if x == '전체' else _cnt_by_year.get(x, 0):,}문항)",
            default_list=[y for y in _saved_years if y in year_options],
            key_prefix="t1_year",
            auto_uncheck_all=True,
        )
        selected_year = selected_years[0] if selected_years else "전체"

    with filt_col3:
        # 4. 시험 구분
        # "1학기/2학기 총괄·단원평가"는 EBSi·KICE 어느 출처에서도 실시간 크롤러가 만들어내지
        # 않는 항목(초·중등용 옛 목업 데이터 전용)이라 완전히 제거했다 - 실제로 고를 수 있는
        # 옵션만 남긴다(2026-09-18).
        exam_types = [
            "전체",
            "대학수학능력시험 (수능)",
            "6월 모의평가",
            "9월 모의평가",
            "3월 전국연합학력평가",
            "4월 전국연합학력평가",
            "7월 전국연합학력평가",
            "10월 전국연합학력평가",
        ]
        exam_type_labels = {
            "전체": "전체 (수능/모평/학평)",
        }
        # KICE는 실제로는 수능만 내려준다(모의평가 게시판이 따로 없어 크롤러가 항상
        # exam_type="수능"으로 저장함 - crawler/ebsi_crawler.py의 _save_kice_exam 등 참고).
        # EBSi는 수능/6·9월 모의평가/학력평가를 전부 제공한다.
        _EBSI_EXAM_TYPES = {"대학수학능력시험 (수능)", "6월 모의평가", "9월 모의평가",
                            "3월 전국연합학력평가", "4월 전국연합학력평가",
                            "7월 전국연합학력평가", "10월 전국연합학력평가"}
        _KICE_EXAM_TYPES = {"대학수학능력시험 (수능)"}
        # 학년과 마찬가지로, 출처를 아직 안 골랐으면 전부 비활성화하지 않고 그대로 둔다.
        _exam_type_disable_set = set()
        if cb_ebsi or cb_kice:
            for _e in exam_types:
                if _e == "전체":
                    continue
                _from_ebsi = cb_ebsi and _e in _EBSI_EXAM_TYPES
                _from_kice = cb_kice and _e in _KICE_EXAM_TYPES
                if not (_from_ebsi or _from_kice):
                    _exam_type_disable_set.add(_e)
        # 선택 가능한 시험 구분이 KICE만 체크했을 때의 수능처럼 딱 하나로 좁혀지면, 매번
        # 손으로 체크하지 않아도 되도록 그 하나를 자동으로 체크해준다.
        _exam_type_enabled = [e for e in exam_types if e != "전체" and e not in _exam_type_disable_set]
        if len(_exam_type_enabled) == 1:
            st.session_state[f"t1_exam_type_{_exam_type_enabled[0]}"] = True
        st.markdown(f"<strong>4. 시험 구분 (복수 선택 가능)</strong>{_dim_css_html(exam_types, _exam_type_disable_set, exam_types, 't1_exam_type')}", unsafe_allow_html=True)
        _saved_exam_types = _pref_list(prefs, "exam_type")
        selected_exam_types = _checkbox_group(
            exam_types,
            format_func=lambda x: f"{exam_type_labels.get(x, str(x))} ({total_collected if x == '전체' else _cnt_by_exam_type.get(_exam_type_db_key.get(x, x), 0):,}문항)",
            default_list=[e for e in _saved_exam_types if e in exam_types],
            key_prefix="t1_exam_type",
            disable_options=_exam_type_disable_set,
            auto_uncheck_all=True,
            emit_dim_css=False,
        )
        selected_exam_type = selected_exam_types[0] if selected_exam_types else "전체"

    # 5. 과목 (선택된 학년에 따른 맞춤 과목 구성) - 항목 수가 많아 두 컬럼(filt_col4a/4b)에
    # 나눠서 그린다. KICE_ZIP_SUBJECT_MEMBERS(crawler/ebsi_crawler.py)와 동일한 사회탐구
    # 9과목 / 과학탐구 8과목 - DB에는 개별 과목명으로 저장되므로 필터에도 전부 올려야
    # 통계 카운트 합계가 실제 수집 총량과 어긋나지 않는다.
    _tamgu_society = ["생활과 윤리", "윤리와 사상", "한국지리", "세계지리", "동아시아사",
                       "세계사", "경제", "정치와 법", "사회·문화"]
    _tamgu_science = ["물리학Ⅰ", "화학Ⅰ", "생명과학Ⅰ", "지구과학Ⅰ",
                       "물리학Ⅱ", "화학Ⅱ", "생명과학Ⅱ", "지구과학Ⅱ"]
    # EBSi는 사회탐구/과학탐구/제2외국어를 개별 과목명이 아니라 "사탐"/"과탐"/"제2외국어"
    # 대분류로만 제공한다(KICE만 개별 과목명을 준다) - 그래서 이 대분류 라벨도 별도
    # 옵션으로 올려둔다. (실제 DB에서 subject_name='제2외국어' 270건 확인, 2026-09-18)
    _tamgu_coarse = ["사탐", "과탐", "제2외국어"]
    # KICE는 국어/수학을 통으로 주지 않고 선택과목(화작/언매, 확통/미적분/기하)별로
    # 나눠서 제공한다 (crawler/ebsi_crawler.py의 KICE_CHOICE_LAYOUT 참고, 2026-09-18 신설).
    _kice_choice_tracks = ["국어(화법과 작문)", "국어(언어와 매체)",
                           "수학(확률과 통계)", "수학(미적분)", "수학(기하)"]
    if selected_grade in (101, 102, 103, 104, 105, 106, 1, 2, 3, 4):
        # 초3 ~ 중3, 고1: 공통 '과학', '사회' 표기
        subjects = ["전체", "국어", "영어", "수학", "과학", "사회", "한국사"]
    elif selected_grade in (5, 6):
        # 고2 ~ 고3: 탐구 선택과목 세부 과목 전체 표기
        subjects = ["전체", "국어", "영어", "수학", "한국사"] + _tamgu_coarse + _kice_choice_tracks + _tamgu_society + _tamgu_science
    else:
        # 전체 (초1 ~ 고3)
        subjects = ["전체", "국어", "영어", "수학", "과학", "사회", "한국사"] + _tamgu_coarse + _kice_choice_tracks + _tamgu_society + _tamgu_science

    subject_labels = {
        "전체": "전체 (전과목)"
    }
    _saved_subjects = _pref_list(prefs, "subject")
    _subject_default_list = [s for s in _saved_subjects if s in subjects]
    _subject_format_func = lambda x: f"{subject_labels.get(x, str(x))} ({total_collected if x == '전체' else _cnt_by_subject.get(x, 0):,}문항)"

    # 1번(공공 출처)에서 지금 체크된 곳으로는 절대 안 나오는 과목을 흐릿하게 표시한다.
    # EBSi는 사회탐구/과학탐구를 "사탐"/"과탐" 대분류로만 주고, KICE는 반대로 개별
    # 과목명만 주고 "사탐"/"과탐"/"제2외국어" 대분류나 국어/수학은 아예 안 준다
    # (crawler/ebsi_crawler.py의 KICE_SUPPORTED_SUBJECTS·KICE_ZIP_SUBJECT_MEMBERS 참고).
    _EBSI_SUBJECTS = {"국어", "영어", "수학", "한국사", "과학", "사회"} | set(_tamgu_coarse)
    _KICE_SUBJECTS = {"영어", "한국사"} | set(_tamgu_society) | set(_tamgu_science) | set(_kice_choice_tracks)
    _subject_dim_set = set()
    # 공공 출처를 하나도 안 골랐으면 아무것도 안 나올 게 확실하므로 "5. 과목" 전체를 비활성화한다.
    _subject_disable_all = not (cb_ebsi or cb_kice)
    if cb_ebsi or cb_kice:
        for _s in subjects:
            if _s == "전체":
                continue
            _from_ebsi = cb_ebsi and _s in _EBSI_SUBJECTS
            _from_kice = cb_kice and _s in _KICE_SUBJECTS
            if not (_from_ebsi or _from_kice):
                _subject_dim_set.add(_s)

    # 항목이 많은 "5. 과목"만 두 컬럼에 걸쳐 그리므로, 렌더링 전에 "전체" 상태 보정을
    # 옵션 전체 목록 기준으로 한 번만 해둔다 (그래야 어느 컬럼에서 체크하든 일관되게 동작).
    _checkbox_group_fix_state(subjects, _subject_default_list, "t1_subject")
    _subject_half = (len(subjects) + 1) // 2
    _subjects_first, _subjects_second = subjects[:_subject_half], subjects[_subject_half:]

    # 흐릿하게 표시할 과목들의 CSS를 "5. 과목" 제목에 얹어서 함께 출력한다 - CSS만을
    # 위한 별도 st.markdown() 호출을 새로 만들면 그 자체가 flex 목록의 새 자식으로
    # 끼어들어 목록 전체가 아래로 밀려 보이는 문제가 있었다(2026-09-18 실측 확인).
    _subject_dim_css = _dim_css_html(subjects, _subject_dim_set, subjects, "t1_subject")
    with filt_col4a:
        st.markdown(f"<strong>5. 과목 (복수 선택 가능)</strong>{_subject_dim_css}", unsafe_allow_html=True)
        selected_subjects_1 = _checkbox_group_render(
            _subjects_first, _subject_format_func, _subject_default_list, "t1_subject", auto_uncheck_all=True,
            dim_options=_subject_dim_set, global_options=subjects, disable_all=_subject_disable_all,
            disable_options=_subject_dim_set, emit_dim_css=False,
        )
    with filt_col4b:
        st.markdown("<p style='visibility:hidden;'><strong>5. 과목 (복수 선택 가능)</strong></p>", unsafe_allow_html=True)
        selected_subjects_2 = _checkbox_group_render(
            _subjects_second, _subject_format_func, _subject_default_list, "t1_subject", auto_uncheck_all=True,
            dim_options=_subject_dim_set, global_options=subjects, disable_all=_subject_disable_all,
            disable_options=_subject_dim_set, emit_dim_css=False,
        )
    selected_subjects = selected_subjects_1 + selected_subjects_2
    selected_subject = selected_subjects[0] if selected_subjects else "전체"

    # 현재 선택한 조건(5개 항목의 교집합)에 해당하는 DB 문항 수 - 조건 선택 제목 옆에 크게 표시
    try:
        if not (selected_portals or selected_grades or selected_years or selected_exam_types or selected_subjects):
            _cond_count_html = ""
        else:
            _cond_matched = db.search_questions(
                subject_name=selected_subjects or None, grade=selected_grades or None,
                years=selected_years or None, exam_type=selected_exam_types or None,
                source_portal=selected_portals or None,
            )
            _n = len(_cond_matched)
            _cond_color = "#2563eb" if _n else "#dc2626"
            _cond_count_html = (f"<span style='font-size:22px; font-weight:800; color:{_cond_color}; margin-left:14px;'>{_n:,}</span>"
                                f"<span style='font-size:15px; font-weight:700; color:#475569; margin-left:3px;'>문항</span>")
    except Exception:
        _cond_count_html = ""
    _cond_title_slot.markdown(f"<div style='white-space:nowrap; overflow:visible;'>{_COND_TITLE_HTML}{_cond_count_html}</div>", unsafe_allow_html=True)

    # 학년/연도/시험구분(1~4번 조건) 중 하나라도 2개 이상 선택되면 안내 - 조건이 유지되는 동안 매번 노출.
    # 학년·연도의 "전체"는 수집 시 실제 학년/연도 목록으로 펼쳐져 여러 번 반복 조회되므로 마찬가지로 안내한다.
    # 과목(5번)만 여러 개 선택한 경우는(사용자 요청에 따라) 안내 대상에서 제외한다.
    if ((len(selected_grades) > 1 or len(selected_years) > 1
            or len(selected_exam_types) > 1
            or selected_grades == ["전체"] or selected_years == ["전체"])
            and not prefs.get("hide_combo_warning")):
        _top_combo_count = _estimate_collection_combos(
            selected_grades, selected_years, selected_exam_types, selected_subjects, selected_portals
        )
        _top_est_low, _top_est_high, _top_speed_note = _estimate_collection_minutes(_top_combo_count)
        # 30건 문턱을 "이번에 막 넘었을 때"만 토스트로 한 번 짚어준다 - 매번 리렌더링될 때마다
        # 뜨면 시끄러우니, 이전 값과 비교해 아래→위로 넘어가는 순간에만 띄운다.
        _prev_combo_count = st.session_state.get("_last_combo_count", 0)
        if _prev_combo_count < 30 <= _top_combo_count:
            st.toast(f"⚠️ 조합이 많아졌어요 - 예상 {_top_combo_count:,}건", icon="⏱️")
        st.session_state["_last_combo_count"] = _top_combo_count
        with _combo_warning_placeholder.container():
            st.warning(
                "⚠️ 다학년·다교과·여러 시험연도처럼 조건을 여러 개 선택하거나 학년/연도를 '전체'로 두면 "
                "그 조합 수만큼 반복 수집되어 시간이 오래 걸릴 수 있습니다.\n\n"
                f"예상 조합 수: **{_top_combo_count:,}건**, 대략 **{_format_minutes(_top_est_low)}~{_format_minutes(_top_est_high)}** 예상됩니다 ({_top_speed_note}).\n\n"
                "조합이 너무 많으면 EBSi·평가원 사이트에서 일시적으로 접속을 막거나(차단), "
                "그 사이 브라우저 연결이 끊길 수도 있습니다."
            )
            # 안내 맨 끝 오른쪽에 붙이는 "다시 보지 않기" - prefs.json에 저장해 다음
            # 실행에도(세션이 끝나도) 계속 숨겨진 채로 유지되게 한다(skip_confirm_popup과
            # 같은 패턴).
            _dismiss_col_spacer, _dismiss_col_btn = st.columns([5, 2])
            with _dismiss_col_btn:
                if st.button("이 메시지 다시 보지 않기", type="tertiary", use_container_width=True,
                             key="btn_dismiss_combo_warning"):
                    _dismiss_prefs = load_prefs()
                    _dismiss_prefs["hide_combo_warning"] = True
                    save_prefs(_dismiss_prefs)
                    _combo_warning_placeholder.empty()
                    st.rerun()
    else:
        st.session_state["_last_combo_count"] = 0
        _combo_warning_placeholder.empty()

# ==============================================================================
# 메인 작업 영역
# ==============================================================================
start_btn = st.session_state.get("collect_stage") == "running"
main_display_area = st.container()

with main_display_area:
    # -------------------------------------------------------------
    # [우측 패널] 수집 모드: 공공 출처/학년/연도/시험구분/수집과목별 상세 수집 현황 대시보드
    # -------------------------------------------------------------
    if st.session_state.get("collect_stage") == "confirm":
        def _on_dismiss_reset_collect_stage():
            # 팝업을 "취소" 버튼이 아니라 X/ESC/바깥 클릭으로 닫으면 st.dialog는 기본적으로
            # 아무 것도 하지 않는다(on_dismiss="ignore") - collect_stage가 "confirm"으로
            # 그대로 남아있어서, 그 뒤 아무 체크박스나 하나만 눌러도(예: 학년/연도) 스크립트가
            # 다시 실행되면서 collect_stage가 여전히 "confirm"이라 이 팝업이 또 떠버리는
            # 버그가 있었다(2026-09-18 실제 재현 확인). "취소"를 누른 것과 동일하게 꺼준다.
            st.session_state["collect_stage"] = None
            st.session_state.pop("confirm_ebsi_mirror", None)
            st.session_state.pop("confirm_kice_mirror", None)

        @st.dialog(" ", width="small", on_dismiss=_on_dismiss_reset_collect_stage)
        def _confirm_collection_dialog():
            st.markdown("<h3 style='padding-top: 3px; margin: 0;'>📋 아래 조건으로 수집을 시작할까요?</h3>", unsafe_allow_html=True)

            # 팝업 안에서도 공공 출처를 바로 바꿀 수 있게 한다 - 본 페이지의 "1. 공공 출처"
            # 체크박스(t1_ebsi/t1_kice)와 별개의 key를 쓰되, 값이 실제로 바뀌면 그 즉시
            # 본 페이지 키에 반영하고 전체 스크립트를 다시 돌려서(st.rerun()) 2~5번의
            # 자동 선택/비활성화 로직까지 전부 새로 계산된 상태로 이 팝업을 다시 띄운다.
            # (다이얼로그는 fragment라 위젯 조작이 보통 이 함수만 다시 그리는데, st.rerun()을
            # 명시적으로 불러 전체 스크립트를 다시 돌리는 방식으로 우회한다.)
            # setdefault만 쓴다 - 여기서 무조건 대입해버리면, 체크박스를 클릭해서 이
            # 다이얼로그(fragment)만 다시 그려질 때 방금 누른 새 값이 이 줄에서 곧바로
            # 예전 값(cb_ebsi)으로 덮어써져 클릭이 씹힌 것처럼 보이는 버그가 있었다
            # (2026-09-19 실제 재현 확인). 대신 닫을 때(취소/수집 시작/X)마다 이 두 키를
            # 지워서, 다음에 팝업을 새로 열 때는 항상 그 시점의 실제 값으로 다시 초기화되게 한다.
            st.session_state.setdefault("confirm_ebsi_mirror", cb_ebsi)
            st.session_state.setdefault("confirm_kice_mirror", cb_kice)
            _mirror_col_a, _mirror_col_b = st.columns(2)
            with _mirror_col_a:
                _mirror_ebsi = st.checkbox("EBSi 국가 교육 포털", key="confirm_ebsi_mirror")
            with _mirror_col_b:
                _mirror_kice = st.checkbox("한국교육과정평가원 (KICE)", key="confirm_kice_mirror")
            if _mirror_ebsi != cb_ebsi or _mirror_kice != cb_kice:
                st.session_state["t1_ebsi"] = _mirror_ebsi
                st.session_state["t1_kice"] = _mirror_kice
                st.rerun()

            if not selected_portals:
                st.error("⚠️ 공공 출처(1번)를 최소 1개 이상 선택해 주세요.")
                if st.button("닫기", use_container_width=True, key="confirm_close_invalid_btn"):
                    st.session_state["collect_stage"] = None
                    st.session_state.pop("confirm_ebsi_mirror", None)
                    st.session_state.pop("confirm_kice_mirror", None)
                    st.rerun()
                return

            # 2~5번을 하나도 안 골라서 "전체"로 자동 적용된 항목은 옅은 주황색 안내를
            # 붙여 눈에 띄게 한다 - "전체" 체크박스를 실제로 눌러서 전체가 된 경우와
            # 헷갈리지 않도록, 아무것도 선택 안 한 경우에만 붙인다.
            _auto_all_note = " <span style='color:#d97706; font-size:0.85em;'>(선택 안 함 → 전체 적용)</span>"

            st.markdown(f"- **1. 공공 출처**: {', '.join(selected_portals)}")
            st.markdown(
                f"- **2. 학년**: {', '.join(grade_labels.get(g, f'{g}학년') for g in selected_grades) if selected_grades else '전체' + _auto_all_note}",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"- **3. 시험 연도**: {', '.join(str(y) for y in selected_years) if selected_years else '전체' + _auto_all_note}",
                unsafe_allow_html=True,
            )
            _exam_type_display = selected_exam_types if selected_exam_types else ["전체"]
            _exam_type_lines = [', '.join(_exam_type_display[i:i + 2]) for i in range(0, len(_exam_type_display), 2)]
            if not selected_exam_types:
                # 2·3·5번처럼 "전체" 바로 옆에 안내가 붙도록 새 줄로 따로 빼지 않는다.
                _exam_type_lines[-1] += _auto_all_note
            _exam_type_rows = "".join(f"<div style='margin-left: 15px;'>{_line}</div>" for _line in _exam_type_lines)
            st.markdown(f"- **4. 시험 구분**:{_exam_type_rows}", unsafe_allow_html=True)
            st.markdown(
                f"- **5. 과목**: {', '.join(selected_subjects) if selected_subjects else '전체' + _auto_all_note}",
                unsafe_allow_html=True,
            )

            # 실제로 몇 건이나 수집될지 미리 계산해서 보여준다 - _estimate_collection_combos()의
            # 학년/연도 "전체" 펼침 규칙은 진행 팝업의 조합 계산 로직과 동일하다.
            _combo_count = _estimate_collection_combos(
                selected_grades, selected_years, selected_exam_types, selected_subjects, selected_portals
            )
            if _combo_count >= 30:
                # 조합 1건당 소요 시간은 "인터넷이 빠른가"가 아니라 "지금 이 사이트가
                # 얼마나 빨리 응답하는가"에 좌우된다 - 그래서 고정 2~6초 대신, 선택된
                # 출처에 실제 크롤링과 같은 모양의 요청을 한 번 보내 응답 시간을 재고,
                # 원래 2~6초 추정의 기준이 됐던 응답시간(0.3초)과 비교한 배율로 범위를
                # 다시 계산한다. 실측에 실패하면(사이트 다운·타임아웃) 원래 고정 범위로
                # 조용히 폴백한다 - 실패를 지어낸 값으로 덮지 않는다.
                _BASELINE_LATENCY = _BASELINE_PORTAL_LATENCY
                _probe_key = "portal_latency_probe"
                _probe = st.session_state.get(_probe_key)
                _probe_stale = (
                    not _probe
                    or _probe.get("portals") != sorted(selected_portals)
                    or (time.time() - _probe.get("measured_at", 0)) > 300
                )

                if _probe_stale:
                    # 매번 새로 재기 전에, 앱을 열 때 백그라운드에서 조용히 미리 재둔 값이
                    # 있는지부터 확인한다(선택한 출처를 모두 포함하고 5분 이내에 잰 것이면
                    # 그대로 재사용) - 있으면 사용자를 기다리게 하지 않는다.
                    _bg_store = _get_latency_probe_store()
                    with _bg_store["lock"]:
                        _bg_entries = list(_bg_store["data"].values())
                    _fresh_bg = None
                    for _entry in _bg_entries:
                        if (time.time() - _entry.get("measured_at", 0)) <= 300 and all(
                            p in _entry.get("latencies", {}) for p in selected_portals
                        ):
                            if _fresh_bg is None or _entry["measured_at"] > _fresh_bg["measured_at"]:
                                _fresh_bg = _entry

                    if _fresh_bg is not None:
                        _probe = {
                            "portals": sorted(selected_portals),
                            "measured_at": _fresh_bg["measured_at"],
                            "latencies": _fresh_bg["latencies"],
                        }
                        st.session_state[_probe_key] = _probe
                        _probe_stale = False

                if _probe_stale:
                    with st.spinner("사이트 응답 속도 확인 중..."):
                        _latencies = crawler.measure_portal_latency(selected_portals)
                    _probe = {
                        "portals": sorted(selected_portals),
                        "measured_at": time.time(),
                        "latencies": _latencies,
                    }
                    st.session_state[_probe_key] = _probe

                _measured_values = [_probe["latencies"].get(p) for p in selected_portals]
                _measured_values = [v for v in _measured_values if v is not None]
                if _measured_values:
                    _avg_latency = sum(_measured_values) / len(_measured_values)
                    _scale = max(0.3, min(_avg_latency / _BASELINE_LATENCY, 15))
                    _speed_note = f"방금 실측한 사이트 응답 속도 기준, 평균 {_avg_latency:.2f}초"
                else:
                    _scale = 1.0
                    _speed_note = "사이트 응답 속도 실측에 실패해 기본 추정치를 사용합니다"

                _est_min_low = round(_combo_count * 2 * _scale / 60, 1)
                _est_min_high = round(_combo_count * 6 * _scale / 60, 1)
                st.warning(
                    f"⏱️ 예상 조합 수: **{_combo_count:,}건** — 대략 **{_format_minutes(_est_min_low)}~{_format_minutes(_est_min_high)}** 정도 걸릴 수 있습니다 ({_speed_note}).\n\n"
                    "조합이 너무 많으면 EBSi·평가원 사이트에서 일시적으로 접속을 막거나(차단), "
                    "그 사이 브라우저 연결이 끊길 수도 있습니다.\n\n"
                    "꼭 필요한 게 아니라면 학년·연도·시험구분·과목을 좁혀서 나눠 수집하는 것을 권장합니다."
                )

            st.markdown("""
            <style>
            /* "수집 시작"이 전역 primary 버튼 스타일(18px, 큰 패딩) 대신
               "취소" 버튼과 같은 높이가 되도록 이 팝업 안에서만 되돌린다. */
            div.st-key-confirm_start_btn button[kind="primary"] {
                padding: 4.125px 12.375px !important;
                font-size: 16.5px !important;
            }
            div.st-key-confirm_start_btn button[kind="primary"] p {
                font-size: 16.5px !important;
                font-weight: 700 !important;
            }
            </style>
            """, unsafe_allow_html=True)

            col_confirm_a, col_confirm_b = st.columns(2)
            with col_confirm_a:
                if st.button("취소", use_container_width=True, key="confirm_cancel_btn"):
                    st.session_state["collect_stage"] = None
                    st.session_state.pop("confirm_ebsi_mirror", None)
                    st.session_state.pop("confirm_kice_mirror", None)
                    st.rerun()
            with col_confirm_b:
                if st.button("🚀 수집 시작", type="primary", use_container_width=True, key="confirm_start_btn"):
                    st.session_state["collect_stage"] = "running"
                    st.session_state.pop("confirm_ebsi_mirror", None)
                    st.session_state.pop("confirm_kice_mirror", None)
                    st.rerun()

            st.session_state.setdefault("confirm_skip_popup_cb", prefs.get("skip_confirm_popup", False))
            _skip_popup = st.checkbox(
                "다음부터 이 팝업 열지 않고 바로 수집 시작하기",
                key="confirm_skip_popup_cb"
            )
            if _skip_popup != prefs.get("skip_confirm_popup", False):
                _skip_prefs = load_prefs()
                _skip_prefs["skip_confirm_popup"] = _skip_popup
                save_prefs(_skip_prefs)

        _confirm_collection_dialog()

    if start_btn:
        _prefs_to_save = load_prefs()  # 저장된 즐겨찾기 프리셋(presets)을 덮어쓰지 않도록 병합 저장
        _prefs_to_save.update({
            "cb_ebsi": cb_ebsi, "cb_kice": cb_kice,
            "grade": selected_grades, "year": selected_years,
            "exam_type": selected_exam_types, "subject": selected_subjects,
        })
        save_prefs(_prefs_to_save)
        if not selected_portals:
            st.error("수집 대상 공공 출처를 최소 1개 이상 체크해 주세요.")
        else:
            def _on_dismiss_reset_progress_stage():
                # "✅ 확인" 버튼이 아니라 X/ESC/바깥 클릭으로 닫아도 "확인"을 누른 것과
                # 같은 상태로 정리한다 - 안 그러면 collect_stage가 "running"으로 남아
                # 체크박스를 하나만 건드려도 이 팝업이 또 뜬다(확인 팝업과 동일한 버그,
                # 2026-09-18 실제 재현 확인).
                st.session_state["_crawl_run_done"] = False
                st.session_state["collect_stage"] = None

            @st.dialog("  ", width="small", on_dismiss=_on_dismiss_reset_progress_stage)
            def _collection_progress_dialog():
                st.markdown("<h3 style='padding-top: 3px; margin: 0;'>📡 실시간 크롤링(수집) 진행 상태</h3>", unsafe_allow_html=True)
                st.caption("💾 수집 도중 탭을 닫아도 그때까지 모은 문항은 안전하게 저장됩니다.")
                # _fragment(다이얼로그) 특성상 안의 위젯(예: "확인" 버튼)을 클릭하면 이 함수
                # 전체가 처음부터 다시 실행된다 - 크롤링 루프를 매번 다시 돌리지 않도록,
                # 이번 다이얼로그가 뜬 뒤 딱 한 번만 실제로 수집하도록 플래그로 막는다
                # (2026-09-18 파일 로그로 "확인" 클릭 시 PROGRESS_DIALOG_CALLED가 다시
                # 찍히며 크롤링이 재시작되는 것을 확인).
                if not st.session_state.get("_crawl_run_done"):
                    status_box = st.status("공공 교육 포털 접속 및 기출 데이터 수집 중...", expanded=True)
                    all_logs = []
                    # 이번 수집으로 과목별/전체로 몇 문항이 "새로" 늘었는지 보여주기 위해
                    # 수집 시작 전 스냅샷을 떠 둔다 - 끝난 뒤 값과 빼면 순수 증가분만 나온다.
                    _before_stats = db.get_collection_statistics()
                    _before_total = _before_stats["total_questions"]
                    _before_by_subject = {r["subject_name"]: r["cnt"] for r in _before_stats["by_subject"]}

                    with status_box:
                        progress_bar = st.progress(5)
                        progress_label = st.empty()

                        import itertools
                        # crawl_ebsi_real/crawl_kice_real은 학년/연도를 한 번에 하나씩만 조회할 수 있는
                        # API라서, "전체"를 그대로 넘기면 내부적으로 고3·2026년 등 기본값 하나로만
                        # 수렴해버린다 - 진짜로 전체를 수집하려면 실제 학년/연도 목록으로 펼쳐서
                        # 각각 별도 조합으로 반복 조회해야 한다. (시험구분/과목의 "전체"는 API가 자체적으로
                        # "필터 없음"으로 처리해 한 번의 호출로 전부 가져오므로 펼칠 필요가 없다.)
                        _ALL_REAL_GRADES = [4, 5, 6]
                        _ALL_REAL_YEARS = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]

                        _combo_grades = selected_grades or ["전체"]
                        if _combo_grades == ["전체"]:
                            _combo_grades = _ALL_REAL_GRADES
                        _combo_years = selected_years or ["전체"]
                        if _combo_years == ["전체"]:
                            _combo_years = _ALL_REAL_YEARS
                        _combo_exam_types = selected_exam_types or ["전체"]
                        _combo_subjects = selected_subjects or ["전체"]
                        _combos = list(itertools.product(_combo_grades, _combo_years, _combo_exam_types, _combo_subjects))

                        # 조합 x 출처를 합친 전체 단계 수 기준으로 진행률을 계산 - 조합이 여러 개여도
                        # 진행률이 매 조합마다 초기화되지 않고 끝까지 누적해서 올라가도록 한다.
                        _total_steps = max(len(_combos) * len(selected_portals), 1)
                        _steps_done = 0

                        for _combo_i, (selected_grade, selected_year, selected_exam_type, selected_subject) in enumerate(_combos, start=1):
                            for idx, portal_name in enumerate(selected_portals, start=1):
                                time.sleep(0.3)

                                # 이 출처(포털) 1건이 전체 진행률에서 차지하는 구간 [step_base%, step_base+step_span%).
                                # 실제 문항/시험지를 몇 건 처리했는지에 따라 그 구간 안에서 세밀하게 움직인다.
                                step_span = 80 / _total_steps
                                step_base = 5 + _steps_done * step_span

                                def _make_progress_cb(_base, _span, _portal, _idx):
                                    def _cb(done, total):
                                        frac = (done / total) if total else 1.0
                                        pct = min(int(_base + frac * _span), 95)
                                        progress_bar.progress(pct)
                                        progress_label.caption(f"📶 전체 진행률: {pct}%")
                                    return _cb

                                progress_cb = _make_progress_cb(step_base, step_span, portal_name, idx)
                                progress_bar.progress(int(step_base))
                                progress_label.caption(f"📶 전체 진행률: {int(step_base)}%")

                                crawl_year = 2026 if selected_year == "전체" else selected_year
                                crawl_grade = 6 if selected_grade == "전체" else selected_grade
                                crawl_type = "수능" if selected_exam_type in ("전체", "대학수학능력시험 (수능)", "수능") else selected_exam_type

                                # EBSi monthList 필터 매핑 - 시험 구분을 고르면 해당 월만 조회해 응답 범위를 좁힌다
                                EBSI_EXAM_TYPE_TO_MONTH = {
                                    "대학수학능력시험 (수능)": "11",
                                    "6월 모의평가": "06",
                                    "9월 모의평가": "09",
                                    "3월 전국연합학력평가": "03",
                                    "4월 전국연합학력평가": "04",
                                    "7월 전국연합학력평가": "07",
                                    "10월 전국연합학력평가": "10",
                                }
                                ebsi_month_list = EBSI_EXAM_TYPE_TO_MONTH.get(
                                    selected_exam_type, "03,04,05,06,07,08,09,10,11,12"
                                )

                                if portal_name == "한국교육과정평가원":
                                    # 평가원은 실시간 크롤링(목업 아님) - suneung.re.kr 게시판 실호출
                                    # ※ 이 게시판은 "대학수학능력시험"만 제공(모의평가 없음), 현재 영어/한국사만 지원
                                    portal_res = crawler.crawl_kice_real(db, crawl_year, crawl_grade, selected_subject, max_exams=10, max_pages=5, progress_callback=progress_cb)
                                elif portal_name == "부산광역시교육청":
                                    portal_res = crawler.crawl_live_exam(db, "부산광역시교육청 학력개발원", crawl_year, crawl_grade, crawl_type, selected_subject)
                                elif "에듀넷" in portal_name or "KERIS" in portal_name:
                                    portal_res = crawler.crawl_live_exam(db, "에듀넷 티-클리어 (KERIS / 한국교육학술정보원)", crawl_year, crawl_grade, crawl_type, selected_subject)
                                elif "기초학력" in portal_name or "KEDI" in portal_name:
                                    portal_res = crawler.crawl_live_exam(db, "국가기초학력지원센터 (KICE/KEDI)", crawl_year, crawl_grade, crawl_type, selected_subject)
                                else:
                                    # EBSi는 실시간 크롤링(목업 아님) - previousPaperListAjax.ajax 실호출 + 실제 PDF 다운로드/파싱
                                    # 사용자가 고른 연도/시험구분/과목으로 조회 범위를 좁히고, PDF는 캐싱 + 병렬 다운로드
                                    # 조합이 아주 많은(전체 선택 등) 큰 수집일수록 동시 연결 수를 줄여서
                                    # 사이트 차단 위험을 낮춘다 - 작은 수집은 그대로 빠르게(4), 아주 큰 수집은
                                    # 더 예의 있게(2) 진행한다.
                                    _ebsi_max_workers = 2 if _total_steps >= 100 else 4
                                    portal_res = crawler.crawl_ebsi_real(
                                        db, crawl_year, crawl_grade, selected_subject,
                                        month_list=ebsi_month_list, max_exams=30, max_pages=15, max_workers=_ebsi_max_workers,
                                        progress_callback=progress_cb
                                    )
                                all_logs.extend(portal_res.get("logs", []))

                                _steps_done += 1
                                step_progress = min(5 + int(_steps_done * step_span), 95)
                                progress_bar.progress(step_progress)
                                progress_label.caption(f"📶 전체 진행률: {step_progress}%")

                        # 로그인 필요 출처 (선택된 경우에만) — Edge 브라우저 창을 열어 사용자가 직접 로그인
                        login_sources_cfg = list_login_required_sources()
                        for key in login_selected_sources:
                            cfg = login_sources_cfg[key]
                            source = cfg["class"]()
                            st.write(f"🔒 **[{cfg['name']}]** Edge 브라우저 로그인 창을 여는 중... (최대 5분간 로그인 대기)")
                            try:
                                source.login_interactively(timeout_sec=300, browser="edge")
                                st.write(f"　↳ ✅ [{cfg['name']}] 로그인 세션 확보 완료")
                                try:
                                    source.fetch_exam_list(crawl_year, crawl_grade)
                                except NotImplementedError:
                                    st.caption(f"　↳ ⚠️ 로그인은 완료됐지만 자료 조회/파싱 로직은 아직 미구현입니다 (구현 예정 지점: crawler/login_required/{key}.py)")
                            except Exception as e:
                                st.error(f"[{cfg['name']}] 로그인 실패 또는 취소: {e}")

                        progress_bar.progress(95)
                        progress_label.caption("📶 전체 진행률: 95%")
                        st.write("📝 수집된 기출문항 분류 체계 인덱싱 및 로컬 DB 최적화 중...")
                        db.deduplicate_questions()

                        now_time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                        date_db_filename = f"questions_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
                        shutil.copyfile(db_path, os.path.join(DATA_ROOT, "data", date_db_filename))

                        total_cnt = db.get_total_question_count()
                        # 화면 아래쪽 "공공 출처별/학년별/..." 현황판이 이 값들을 그대로 재사용하므로,
                        # 방금 끝난 수집 결과가 반영되도록 여기서 다시 계산해 둔다 (안 하면 이번 실행분이
                        # 빠진 수집 전 스냅샷이 그대로 보여서 "완료됐다는데 0문항"처럼 보이는 버그가 생김).
                        stats = db.get_collection_statistics()
                        total_collected = stats["total_questions"]
                        # 과목별 증가분 = 수집 후 문항 수 - 수집 전 문항 수 (0 이하는 이번에
                        # 새로 추가된 게 없다는 뜻이라 목록에서 뺀다 - 지어내지 않고 실제 DB
                        # 값 차이만 보여준다).
                        _after_by_subject = {r["subject_name"]: r["cnt"] for r in stats["by_subject"]}
                        _subject_deltas = {
                            subj: cnt - _before_by_subject.get(subj, 0)
                            for subj, cnt in _after_by_subject.items()
                        }
                        _subject_deltas = {s: d for s, d in _subject_deltas.items() if d > 0}
                        st.session_state["last_crawl_total_added"] = total_collected - _before_total
                        st.session_state["last_crawl_subject_deltas"] = _subject_deltas
                        st.session_state["latest_gen_time"] = now_time_str
                        st.session_state["total_question_count"] = total_cnt
                        st.session_state["just_collected"] = True
                        st.session_state["last_crawl_portals"] = selected_portals
                        st.session_state["last_crawl_logs"] = all_logs
                        header_placeholder.markdown(get_header_html(now_time_str, total_cnt), unsafe_allow_html=True)

                        progress_bar.progress(100)
                        progress_label.caption("📶 전체 진행률: 100%")
                        status_box.update(label="🎉 실시간 크롤링 및 DB 인덱싱 완료!", state="complete", expanded=False)
                        time.sleep(1)
                    st.session_state["_crawl_run_done"] = True
                else:
                    st.success("🎉 실시간 크롤링 및 DB 인덱싱 완료!")

                # 이번 수집으로 실제로 늘어난 문항 수를 과목별로 보여준다 - 조건을 넓게 잡아도
                # 실제로 뭐가 얼마나 들어왔는지 한눈에 확인할 수 있게 한다.
                _added_total = st.session_state.get("last_crawl_total_added")
                _added_by_subject = st.session_state.get("last_crawl_subject_deltas")
                if _added_total is not None:
                    st.markdown(f"**📈 이번 수집으로 새로 추가된 문항: {_added_total:,}건**")
                    if _added_by_subject:
                        _sorted_deltas = sorted(_added_by_subject.items(), key=lambda kv: kv[1], reverse=True)
                        _delta_lines = "\n".join(f"- {subj}: {cnt:,}문항" for subj, cnt in _sorted_deltas)
                        st.markdown(_delta_lines)
                    elif _added_total == 0:
                        st.caption("이번 조건으로는 새로 추가된 문항이 없습니다 (이미 수집돼 있거나, 조건에 맞는 자료를 찾지 못했습니다).")

                if st.button("✅ 확인", type="primary", use_container_width=True, key="collect_done_confirm_btn"):
                    st.session_state["_crawl_run_done"] = False
                    st.session_state["collect_stage"] = None
                    st.rerun()

            _collection_progress_dialog()


    if st.session_state.get("last_crawl_logs"):
        _log_exp_col, _ = st.columns([1, 3])
        with _log_exp_col:
            with st.expander("📋 상세 크롤링 시스템 로그 보기"):
                for l in st.session_state["last_crawl_logs"]:
                    st.caption(f"`{l}`")


    # ==============================================================================
    # EBSi 해설 자동 수집 (베타) — 로그인 회원만 받을 수 있는 해설 PDF를 자동으로 가져와
    # 선택된 연도/학년/과목 조합의 questions.solution_text를 채워 넣는다.
    # ==============================================================================
    with ebsi_solution_slot:
        # 포털 체크 상태가 바뀌면(체크/해제 모두) 해설 수집은 "선택 안 함"으로 초기화한다.
        # 포털을 체크하면 해설 수집 체크박스가 눌릴 수 있게 되고, 켜는 건 사용자가 직접 한다.
        if st.session_state.get("_ebsi_portal_prev") != cb_ebsi:
            st.session_state["t1_ebsi_solution"] = False
            st.session_state["_ebsi_portal_prev"] = cb_ebsi
        _sc1, _sc2 = st.columns([1, 9])
        with _sc1:
            cb_ebsi_sol = st.checkbox("EBSi 해설 수집", key="t1_ebsi_solution", disabled=not cb_ebsi, label_visibility="collapsed")
        _ebsi_sol_on = bool(cb_ebsi and cb_ebsi_sol)
        if not _ebsi_sol_on:
            st.markdown(
                "<style>div.st-key-ebsi_solution_slot { opacity: 0.55; }</style>",
                unsafe_allow_html=True,
            )
        with _sc2:
            with st.expander("EBSi 해설 수집", expanded=False):
                if not _ebsi_sol_on:
                    st.caption("위에서 'EBSi 국가 교육 포털'과 'EBSi 해설 수집'을 모두 체크하면 사용할 수 있습니다.")
                st.caption(
                    "EBSi 로그인 회원만 받을 수 있는 정답 및 해설 PDF를 자동으로 가져와 해설집에 채워 넣습니다. "
                    "왼쪽에서 선택한 연도·학년·과목 조합마다 시도합니다. 실행하면 Edge 브라우저 창이 열리니 "
                    "그 창에서 EBSi 계정으로 직접 로그인해 주세요(아이디/비밀번호는 이 프로그램에 저장되지 않습니다)."
                )
                if st.button("🔑 EBSi 로그인 후 해설 수집 시작", key="btn_ebsi_solution_collect", disabled=not _ebsi_sol_on):
                    if not selected_years or not selected_subjects:
                        st.warning("먼저 왼쪽에서 연도와 과목을 최소 1개씩 선택해 주세요.")
                    else:
                        ebsi_source = get_login_required_source("ebsi_solution")
                        logged_in = False
                        with st.spinner("Edge 브라우저 로그인 창을 여는 중... (최대 5분간 로그인 대기)"):
                            try:
                                ebsi_source.login_interactively(timeout_sec=300, browser="edge")
                                logged_in = ebsi_source.is_logged_in()
                            except Exception as e:
                                st.error(f"로그인 실패 또는 취소: {e}")

                        if logged_in:
                            st.write("✅ EBSi 로그인 세션 확보 완료 — 해설 수집을 시작합니다.")
                            grades_to_try = selected_grades if selected_grades else [6]
                            # 체크박스 값은 "대학수학능력시험 (수능)" 같은 표시용 라벨이라, DB에 저장된
                            # 정규화 값("수능")으로 변환해야 update_solution_texts의 exam_type 매칭이 된다.
                            exam_types_to_try = (
                                [_exam_type_db_key.get(e, e) for e in selected_exam_types]
                                if selected_exam_types else ["수능"]
                            )
                            total_updated = 0
                            results_log = []
                            with st.spinner("과목별 해설 PDF 다운로드 및 반영 중..."):
                                for yr in selected_years:
                                    for gr in grades_to_try:
                                        for subj in selected_subjects:
                                            keyword_m = re.search(r'\(([^)]+)\)', subj)
                                            subject_keyword = keyword_m.group(1) if keyword_m else subj
                                            try:
                                                solutions = ebsi_source.collect_solutions_for_subject(
                                                    year=yr, grade=gr, subject_keyword=subject_keyword
                                                )
                                            except Exception as e:
                                                results_log.append(f"❌ {yr} {subj}: {e}")
                                                continue
                                            if not solutions:
                                                results_log.append(f"⚠️ {yr} {subj}: EBSi에서 일치하는 해설을 찾지 못했습니다.")
                                                continue
                                            for et in exam_types_to_try:
                                                updated = db.update_solution_texts(
                                                    year=yr, grade=gr, exam_type=et, subject_name=subj, solutions=solutions
                                                )
                                                if updated:
                                                    total_updated += updated
                                                    results_log.append(f"✅ {yr} {subj} ({et}): {updated}문항 해설 반영")
                                                else:
                                                    results_log.append(
                                                        f"⚠️ {yr} {subj} ({et}): EBSi 해설은 {len(solutions)}문항 받았지만 "
                                                        f"DB에서 일치하는 문항을 못 찾아 반영된 게 없습니다."
                                                    )
                            if total_updated:
                                st.success(f"총 {total_updated}문항에 해설을 채워 넣었습니다.")
                            else:
                                st.warning("반영된 해설이 없습니다 — 아래 로그를 확인해 주세요.")
                            for line in results_log:
                                st.caption(line)
                            st.caption(
                                "⚠️ 국어처럼 '국어(화법과 작문)'같은 트랙별 과목명 문항에는 정확히 반영되지만, "
                                "공통 지문에 해당하는 '국어' 단독 표기 문항에는 반영되지 않을 수 있습니다."
                            )
            st.markdown('<div class="ebsi-login-note">(EBSi 개인 계정 로그인 필요)</div>', unsafe_allow_html=True)

    # ==============================================================================
    # 맞춤형 한글(HWPX) 3종 문서 다운로드 및 2단 시험지 미리보기 영역
    # ==============================================================================
    if "t2_generated_result" in st.session_state:
        t2_res = st.session_state["t2_generated_result"]
        t2_fb = t2_res.get("file_bytes", {})

        st.markdown("---")
        if t2_res.get("applied_conditions"):
            st.info(f"📌 **적용된 인쇄 조건:** {t2_res['applied_conditions']}")

        def _t2_search_and_meta_top():
            query_subjects = selected_subjects if selected_subjects else None
            query_grades = selected_grades if selected_grades else None
            query_years = selected_years if selected_years else None
            query_exam_types = selected_exam_types if selected_exam_types else None
            query_portals = selected_portals if selected_portals else None

            matched_questions = db.search_questions(
                subject_name=query_subjects,
                grade=query_grades,
                years=query_years,
                exam_type=query_exam_types,
                source_portal=query_portals,
            )
            if not matched_questions:
                return None

            grade_str = ", ".join(grade_labels.get(g, f"{g}학년") for g in selected_grades) if selected_grades else ""
            year_str = ", ".join(f"{y}학년도" for y in selected_years) if selected_years else ""
            exam_str = ", ".join(selected_exam_types) if selected_exam_types else ""
            subj_str = ", ".join(selected_subjects) if selected_subjects else "전과목"
            count_str = f"[{len(matched_questions)}문항]"

            title_parts = [p for p in [year_str, grade_str, subj_str, count_str] if p]
            t2_exam_title = " ".join(title_parts)
            t2_exam_sub = ""
            grade_str_short = ", ".join(grade_labels_short.get(g, f"{g}학년") for g in selected_grades) if selected_grades else ""
            t2_header_meta = " ".join(p for p in [year_str, grade_str_short, exam_str, subj_str, count_str] if p)

            portal_str = ", ".join(selected_portals) if selected_portals else "공공 출처 전체"
            grade_str_full = ", ".join(grade_labels.get(g, f"{g}학년") for g in selected_grades) if selected_grades else "고1~고3 전체"
            year_str_full = ", ".join(str(y) for y in selected_years) + "년" if selected_years else "2018~2026년 전체"
            exam_str_full = ", ".join(selected_exam_types) if selected_exam_types else "수능/모평/학평 전체"
            applied_conditions_str = f"공공 출처: {portal_str}, 학년: {grade_str_full}, 시험 연도: {year_str_full}, 시험 구분: {exam_str_full}, 과목: {subj_str}"

            return {
                "questions": matched_questions,
                "title": t2_exam_title,
                "subtitle": t2_exam_sub,
                "header_meta": t2_header_meta,
                "applied_conditions": applied_conditions_str,
            }

        # (제목 "맞춤형 한글(HWPX) 3종 세트 즉시 다운로드"는 화면 정리를 위해 제거)
        def _top_preview_button(disabled=False):
            if st.button("미리보기", icon=":material/visibility:", use_container_width=True, key="btn_mode_top_preview",
                         disabled=disabled, help="수집된 문항이 없어 미리볼 수 없습니다." if disabled else None):
                meta = _t2_search_and_meta_top()
                if meta is None:
                    st.warning("⚠️ 선택하신 검색 조건에 부합하는 기출문제가 없습니다. 조건을 조금 더 넓혀보세요!")
                else:
                    st.session_state["filter_panel_collapsed"] = True
                    prev_file_bytes = st.session_state.get("t2_generated_result", {}).get("file_bytes", {})
                    st.session_state["t2_generated_result"] = {
                        "questions_count": len(meta["questions"]),
                        "file_bytes": prev_file_bytes,
                        "exam_title": meta["title"],
                        "subtitle": meta["subtitle"],
                        "applied_conditions": meta["applied_conditions"],
                        "questions": meta["questions"]
                    }
                    st.rerun()

        _PREVIEW_MODE_LABELS = {"student": "학생용", "teacher": "교사용", "solution": "해설"}
        if "t2_preview_mode" not in st.session_state:
            st.session_state["t2_preview_mode"] = "teacher"

        def _top_mode_tabs():
            _rev = {v: k for k, v in _PREVIEW_MODE_LABELS.items()}
            picked = st.segmented_control(
                "미리보기 종류", list(_PREVIEW_MODE_LABELS.values()),
                default=_PREVIEW_MODE_LABELS[st.session_state["t2_preview_mode"]],
                selection_mode="single", key="t2_preview_mode_seg", label_visibility="collapsed",
            )
            if picked and _rev[picked] != st.session_state["t2_preview_mode"]:
                st.session_state["t2_preview_mode"] = _rev[picked]
                st.rerun()

        # 현재 선택된 조건의 hwpx 3종을 미리 만들어 캐시해두고(조건이 안 바뀌면 재생성 안 함),
        # [미리보기] [저장 폴더 · 열기 · 변경] [3개 파일 한 번에 저장 ▾] 를 한 줄로 보여준다.
        _top_meta = _t2_search_and_meta_top()
        if _top_meta is not None:
            _top_fb = _get_or_build_t2_files(_top_meta)
            _render_local_folder_save(_top_fb, "top", lead=_top_preview_button, tabs=_top_mode_tabs)
        else:
            _top_preview_button(disabled=st.session_state.get("total_question_count", 0) == 0)

        d_col1, d_col2, d_col3 = st.columns(3)

        with d_col1:
            if "student" in t2_fb:
                st.download_button(
                    label="📄 [학생용] 맞춤 문제지 (.hwpx)",
                    data=t2_fb["student"]["bytes"],
                    file_name=t2_fb["student"]["filename"],
                    mime="application/haansofthwpx",
                    use_container_width=True,
                    key="t2_dl_student"
                )

        with d_col2:
            if "teacher" in t2_fb:
                st.download_button(
                    label="📄 [교사용] 정답/배점포함 (.hwpx)",
                    data=t2_fb["teacher"]["bytes"],
                    file_name=t2_fb["teacher"]["filename"],
                    mime="application/haansofthwpx",
                    use_container_width=True,
                    key="t2_dl_teacher"
                )

        with d_col3:
            if "solution" in t2_fb:
                st.download_button(
                    label="📄 [해설집] 정답 및 상세해설집 (.hwpx)",
                    data=t2_fb["solution"]["bytes"],
                    file_name=t2_fb["solution"]["filename"],
                    mime="application/haansofthwpx",
                    use_container_width=True,
                    key="t2_dl_solution"
                )

        # 2. 실시간 2단 시험지 조판 미리보기
        if "t2_preview_mode" not in st.session_state:
            st.session_state["t2_preview_mode"] = "teacher"

        # (제목 "선택된 기출문항 실시간 2단 시험지 조판 미리보기"는 화면 정리를 위해 제거)
        # 미리보기 창 세로 높이 선택 - 주석 처리(기본 1200px 고정)
        # prev_h_col1, prev_h_col2 = st.columns([3, 1])
        # with prev_h_col2:
        #     preview_height_opt = st.selectbox(
        #         "미리보기 창 세로 높이",
        #         options=["기본 (900px)", "세로 모니터 맞춤 (1200px)", "최대 확장 (1600px)", "콤팩트 (600px)"],
        #         index=1,
        #         key="t2_preview_height_sel"
        #     )
        #     h_map = {"기본 (900px)": 900, "세로 모니터 맞춤 (1200px)": 1200, "최대 확장 (1600px)": 1600, "콤팩트 (600px)": 600}
        #     target_preview_height = h_map.get(preview_height_opt, 1200)
        target_preview_height = 1200

        preview_title = t2_res["exam_title"]
        preview_sub = t2_res["subtitle"]
        preview_questions = t2_res.get("questions", [])

        try:
            t2_preview_html = template_mgr.render_html_preview(
                preview_title,
                preview_sub,
                preview_questions,
                mode=st.session_state["t2_preview_mode"]
            )
            st.components.v1.html(t2_preview_html, height=target_preview_height, scrolling=True)
        except Exception as preview_err:
            import traceback
            err_trace = traceback.format_exc()
            st.error(f"❌ **미리보기 조판 중 오류가 발생했습니다:** {preview_err}")
            with st.expander("🔍 상세 오류 로그(Traceback) 확인"):
                st.code(err_trace, language="python")

        # 3. 검색된 문항 리스트 상세 조회 (아코디언 / 카드 뷰)
        st.markdown("---")
        with st.expander(f"📋 맞춤 기출문항 개별 상세 보기 (총 {len(preview_questions)}문항)"):
            for idx, q in enumerate(preview_questions[:30], start=1):
                source_tag = q.get('source_url', '공공 기출')
                exam_title_str = q.get('exam_title', '')
                major_ch = q.get('major_chapter', '')
                ch_display = f" - {major_ch}" if major_ch and major_ch != '단원 미분류' else ""
                st.markdown(f"**문항 {idx}.** [{q.get('subject_name')}] {exam_title_str}{ch_display} (배점: {q.get('score', 2)}점 / 정답률: {q.get('correct_rate', 80.0)}%)")
                q_raw_text = q.get('question_text', '').strip()
                has_jimum = '[지문]' in q_raw_text
                has_bogi = bool(re.search(r'^[<\[]\s*보\s*기\s*[>\]]\s*$', q_raw_text, re.MULTILINE))

                parsed_card = template_mgr.hwpx_builder._parse_question_text(
                    text=q_raw_text,
                    score=q.get('score', 2),
                    idx=idx,
                    mode="student"
                )

                card_head_html = "<br/>".join([f"<div>{h}</div>" for h in parsed_card["header_lines"]])
                
                # 공통 지문 및 보기 상자 분리 렌더링
                # 지문 안내 헤더([ ~ ] 다음 글을 읽고 물음에 답하시오)는 네모 박스 위, 지문 본문은 네모 박스 안, <보기>는 발문 뒤에 배치
                card_jimum_header_html = ""
                card_jimum_box_html = ""
                if parsed_card.get("jimum_header"):
                    card_jimum_header_html = f"<div style='font-weight:700; color:#1e3a8a; margin: 4px 0 6px 0; font-size:14px;'>{parsed_card['jimum_header']}</div>"

                if parsed_card.get("jimum_lines"):
                    j_paras = []
                    for jl in parsed_card["jimum_lines"]:
                        if re.match(r'^\([가-하A-Za-z0-9]\)$', jl):
                            j_paras.append(f"<div style='font-weight:700; color:#2563eb; margin:6px 0 2px 0;'>{jl}</div>")
                        else:
                            j_paras.append(f"<div style='margin-bottom:6px; text-align:justify;'>{jl}</div>")
                    j_inner = "".join(j_paras)
                    card_jimum_box_html = f"""<div style="border: 1.5px solid #64748b; border-radius: 4px; padding: 10px 14px; margin: 0 0 10px 0; background: #f8fafc; font-size: 13.5px; line-height: 1.7; color: #1e293b;"><div style="font-weight:700; color:#3b82f6; margin-bottom:4px; font-size:12px;">[공통 지문]</div>{j_inner}</div>"""
                
                card_bogi_html = ""
                if parsed_card["bogi_lines"]:
                    b_lines = parsed_card["bogi_lines"]
                    title_html = ""
                    c_start = 0
                    if b_lines and "< 보 기 >" in b_lines[0]:
                        title_html = "<div style='text-align: center; font-weight: 700; margin-bottom: 8px; letter-spacing: 2px;'>&lt; 보 기 &gt;</div>"
                        c_start = 1
                    b_paras = []
                    for bl in b_lines[c_start:]:
                        b_paras.append(f"<div style='margin-bottom:4px; text-align:justify;'>{bl}</div>")
                    b_inner = "".join(b_paras)
                    card_bogi_html = f"""<div style="border: 1.5px solid #334155; border-radius: 4px; padding: 10px 14px; margin: 10px 0; background: #ffffff; font-size: 13.5px; line-height: 1.7; color: #1e293b;">{title_html}{b_inner}</div>"""

                card_foot_html = "<br/>".join([f"<div style='font-weight:600; margin:6px 0;'>{f}</div>" for f in parsed_card["footer_lines"]])
                card_choices_html = "<br/>".join([f"<div>{c}</div>" for c in parsed_card["choice_items"]])

                card_disp_html = f"<div style='font-size:14.5px; line-height:1.7; margin-bottom:8px;'><b>[문제 본문]</b><br/>{card_jimum_header_html}{card_jimum_box_html}{card_head_html}{card_bogi_html}{card_foot_html}{card_choices_html}</div>"
                st.markdown(card_disp_html, unsafe_allow_html=True)
                st.markdown(f"**[정답]** `{q.get('answer', '')}` | **[배점]** `{q.get('score', 2)}점`")
                if q.get('solution_text'):
                    st.markdown(f"**[상세 해설]**  \n{q.get('solution_text')}")
                mid_ch = q.get('middle_chapter', '')
                mid_ch_str = f" | 중단원: {mid_ch}" if mid_ch and mid_ch != '단원 미분류' else ""
                st.caption(f"출처 포털: {source_tag} | 과목: {q.get('subject_name')}{mid_ch_str}")
                st.markdown("<hr style='margin:6px 0;'>", unsafe_allow_html=True)


# ==============================================================================
# 화면 맨 아래(푸터) 출력/인쇄 버튼
# ==============================================================================
def _t2_search_and_meta_bottom():
    query_subjects = selected_subjects if selected_subjects else None
    query_grades = selected_grades if selected_grades else None
    query_years = selected_years if selected_years else None
    query_exam_types = selected_exam_types if selected_exam_types else None
    query_portals = selected_portals if selected_portals else None

    matched_questions = db.search_questions(
        subject_name=query_subjects,
        grade=query_grades,
        years=query_years,
        exam_type=query_exam_types,
        source_portal=query_portals,
    )
    if not matched_questions:
        return None

    # 사용자 요청: 학년도, 학년, 과목명, 기출 문항수만 깔끔하게 단일 출력
    grade_str = ", ".join(grade_labels.get(g, f"{g}학년") for g in selected_grades) if selected_grades else ""
    year_str = ", ".join(f"{y}학년도" for y in selected_years) if selected_years else ""
    exam_str = ", ".join(selected_exam_types) if selected_exam_types else ""
    subj_str = ", ".join(selected_subjects) if selected_subjects else "전과목"
    count_str = f"[{len(matched_questions)}문항]"
    title_parts = [p for p in [year_str, grade_str, subj_str, count_str] if p]
    t2_exam_title = " ".join(title_parts)
    t2_exam_sub = ""
    grade_str_short = ", ".join(grade_labels_short.get(g, f"{g}학년") for g in selected_grades) if selected_grades else ""
    t2_header_meta = " ".join(p for p in [year_str, grade_str_short, exam_str, subj_str, count_str] if p)

    portal_str = ", ".join(selected_portals) if selected_portals else "공공 출처 전체"
    grade_str_full = ", ".join(grade_labels.get(g, f"{g}학년") for g in selected_grades) if selected_grades else "고1~고3 전체"
    year_str_full = ", ".join(str(y) for y in selected_years) + "년" if selected_years else "2018~2026년 전체"
    exam_str_full = ", ".join(selected_exam_types) if selected_exam_types else "수능/모평/학평 전체"

    # 사용자가 선택한 모든 조건 목록 (, 로 구분)
    applied_conditions_str = f"공공 출처: {portal_str}, 학년: {grade_str_full}, 시험 연도: {year_str_full}, 시험 구분: {exam_str_full}, 과목: {subj_str}"

    return {
        "questions": matched_questions,
        "title": t2_exam_title,
        "subtitle": t2_exam_sub,
        "header_meta": t2_header_meta,
        "applied_conditions": applied_conditions_str,
    }


st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
def _bottom_preview_button(disabled=False):
    if st.button("미리보기", icon=":material/visibility:", use_container_width=True, key="btn_mode_bottom_preview",
                 disabled=disabled, help="수집된 문항이 없어 미리볼 수 없습니다." if disabled else None):
        meta = _t2_search_and_meta_bottom()
        if meta is None:
            st.warning("⚠️ 선택하신 검색 조건에 부합하는 기출문제가 없습니다. 조건을 조금 더 넓혀보세요!")
        else:
            st.session_state["filter_panel_collapsed"] = True
            prev_file_bytes = st.session_state.get("t2_generated_result", {}).get("file_bytes", {})
            st.session_state["t2_generated_result"] = {
                "questions_count": len(meta["questions"]),
                "file_bytes": prev_file_bytes,
                "exam_title": meta["title"],
                "subtitle": meta["subtitle"],
                "applied_conditions": meta["applied_conditions"],
                "questions": meta["questions"]
            }
            st.rerun()


# 현재 선택된 조건의 hwpx 3종을 미리 만들어 캐시해두고, 압축 없이 각 파일을 그대로
# 저장할 수 있도록 버튼을 3개 둔다(브라우저 보안 정책상 클릭 하나로 여러 파일을 동시에
# 자동저장할 수는 없어서, 원본 그대로 받으려면 파일별로 한 번씩 클릭이 필요하다).
# (Chrome/Edge라면 위의 "폴더 선택" 버튼으로 압축 없이 3개를 한 번에 저장할 수도 있다.)
_bottom_meta = _t2_search_and_meta_bottom()
if _bottom_meta is not None:
    _bottom_fb = _get_or_build_t2_files(_bottom_meta)
    _render_local_folder_save(_bottom_fb, "bottom", lead=_bottom_preview_button)
else:
    _bottom_preview_button(disabled=st.session_state.get("total_question_count", 0) == 0)
