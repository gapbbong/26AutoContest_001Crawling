import os
import sys
import io
import time
import socket
import threading
import queue
import webbrowser
import subprocess
import pathlib
from datetime import datetime

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.log")

# 콘솔이 없는 pythonw 실행 환경에서도 안전하게: 있으면 UTF-8/줄단위 flush로 감싸고,
# 없으면(sys.stdout이 None) 그대로 둔다 - 이후 코드는 print()에 의존하지 않는다.
if sys.platform == "win32" and sys.stdout is not None:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass


def log(msg: str):
    """콘솔이 있으면 출력하고, 항상 run.log에도 남긴다 (사후 진단용)."""
    try:
        if sys.stdout:
            print(msg)
    except Exception:
        pass
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%H:%M:%S}] {msg}\n")
    except Exception:
        pass


def ensure_streamlit_credentials():
    """사용자 홈 디렉토리의 .streamlit/credentials.toml 설정으로 이메일 질문 원천 차단"""
    try:
        home = pathlib.Path.home()
        streamlit_home_dir = home / ".streamlit"
        streamlit_home_dir.mkdir(parents=True, exist_ok=True)

        cred_file = streamlit_home_dir / "credentials.toml"
        if not cred_file.exists():
            cred_file.write_text('[general]\nemail = ""\n', encoding="utf-8")

        config_file = streamlit_home_dir / "config.toml"
        if not config_file.exists():
            config_file.write_text('[browser]\ngatherUsageStats = false\n', encoding="utf-8")
    except Exception:
        pass


def check_dependencies():
    """실행 전 필수 패키지 설치 여부를 확인한다. 누락 시 (모듈 목록, pip 명령) 튜플을 반환."""
    missing = []
    for module_name, pip_name in [
        ("streamlit", "streamlit"),
        ("bs4", "beautifulsoup4"),
        ("requests", "requests"),
        ("PIL", "Pillow"),
    ]:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(pip_name)
    return missing


class Splash:
    """
    콘솔 없이(pythonw) 실행돼도 사용자가 진행 상황을 볼 수 있게 하는 작은 로딩 창.
    tkinter는 파이썬 표준 라이브러리라 별도 설치가 필요 없다.
    """

    def __init__(self, on_close=None):
        import tkinter as tk
        from tkinter import ttk
        self.tk = tk
        self.ttk = ttk
        self.on_close = on_close

        self.root = tk.Tk()
        self.root.title("2026 부산교육청 업무자동화")
        self.root.configure(bg="#0f172a")
        self.root.resizable(False, False)

        width, height = 440, 230
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x, y = (sw - width) // 2, (sh - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        tk.Label(self.root, text="기출 문제 크롤링 및 단원별 기출정리집",
                 font=("맑은 고딕", 13, "bold"), bg="#0f172a", fg="white").pack(pady=(26, 4))
        tk.Label(self.root, text="부산광역시교육청 업무자동화 프로그램 개발대회",
                 font=("맑은 고딕", 9), bg="#0f172a", fg="#94a3b8").pack(pady=(0, 18))

        self.status_var = tk.StringVar(value="잠시만 기다려 주세요...")
        tk.Label(self.root, textvariable=self.status_var, font=("맑은 고딕", 10, "bold"),
                 bg="#0f172a", fg="#e2e8f0", wraplength=380, justify="center").pack(pady=(0, 6))

        self.reason_var = tk.StringVar(value="")
        tk.Label(self.root, textvariable=self.reason_var, font=("맑은 고딕", 9),
                 bg="#0f172a", fg="#64748b", wraplength=380, justify="center").pack(pady=(0, 14))

        self.progress = ttk.Progressbar(self.root, mode="indeterminate", length=320)
        self.progress.pack(pady=(0, 16))
        self.progress.start(12)

        self.close_btn = tk.Button(self.root, text="닫기", command=self._on_close_click,
                                    bg="#1e293b", fg="white", relief="flat", padx=16, pady=4)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close_click)
        self._closed_by_user = False

    def set_status(self, status: str, reason: str = ""):
        self.status_var.set(status)
        self.reason_var.set(reason)

    def show_error(self, reason: str):
        self.progress.stop()
        self.progress.pack_forget()
        self.status_var.set("문제가 발생했습니다")
        self.reason_var.set(reason)
        self.close_btn.pack(pady=(4, 18))

    def enter_running_mode(self):
        """
        서버가 정상적으로 떴을 때: 로딩창을 없애지 않고 '실행 중' 상태로 바꿔 작업표시줄로
        내려보낸다. 프로그램을 끝내려면 사용자가 작업표시줄에서 이 창을 다시 열어 닫으면 된다
        (자동 감지가 아닌 명시적 종료 - 탭 재활용/재실행 시 오작동 위험을 피하기 위함).
        """
        self.progress.stop()
        self.progress.pack_forget()
        self.status_var.set("프로그램이 실행 중입니다")
        self.reason_var.set("브라우저에서 계속 사용하세요.\n프로그램을 끝내려면 작업표시줄에서 이 창을 열어 닫아 주세요.")
        self.close_btn.config(text="프로그램 종료")
        self.close_btn.pack(pady=(4, 18))
        self.root.iconify()

    def _on_close_click(self):
        self._closed_by_user = True
        if self.on_close:
            try:
                self.on_close()
            except Exception:
                pass
        self.root.destroy()

    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


def run_backend(splash_queue: "queue.Queue", state: dict):
    """
    실제 구동 로직 (백그라운드 스레드) - Tkinter 메인루프와 분리해서
    무거운 작업(패키지 확인/서버 기동/포트 대기) 중에도 로딩창이 얼어붙지 않게 한다.
    splash_queue로 ('status', text, reason) / ('error', reason) / ('done',) 메시지를 보낸다.
    state["proc"]에 구동 중인 Streamlit 서버 프로세스를 기록해서, 로딩창을 사용자가
    중간에 직접 닫아도(성공 전) 그 프로세스를 함께 정리할 수 있게 한다.
    """
    ensure_streamlit_credentials()

    splash_queue.put(("status", "필수 패키지 확인 중...", ""))
    missing = check_dependencies()
    if missing:
        pkg_list = ", ".join(missing)
        splash_queue.put(("error",
            f"다음 패키지가 설치되어 있지 않습니다: {pkg_list}\n\n"
            f"'{sys.executable} -m pip install -r requirements.txt' 실행 후 다시 시작해 주세요."))
        return

    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(base_dir, "ui", "app.py")
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

    cmd = [
        sys.executable, "-m", "streamlit", "run", app_path,
        "--server.port=8501",
        "--server.address=localhost",
        "--browser.gatherUsageStats=false",
        "--server.headless=true",
    ]

    splash_queue.put(("status", "웹 서버를 준비하고 있습니다...",
                       "Python 라이브러리 로딩과 서버 구동에\n처음 실행 시 5~15초 정도 걸릴 수 있습니다."))

    try:
        proc = subprocess.Popen(cmd)
    except FileNotFoundError as e:
        splash_queue.put(("error", f"프로그램 실행에 실패했습니다: {e}\nPython 설치 경로 또는 PATH 설정을 확인해 주세요."))
        return

    state["proc"] = proc

    ready = False
    start = time.time()
    while time.time() - start < 40:
        if proc.poll() is not None:
            break
        try:
            with socket.create_connection(("localhost", 8501), timeout=0.5):
                ready = True
                break
        except OSError:
            time.sleep(0.5)

    if not ready:
        splash_queue.put(("error", "서버가 시간 내에 준비되지 않았습니다.\nrun.log 파일을 확인해 주세요."))
        return

    time.sleep(0.5)  # 서버가 막 listen을 시작한 직후라 첫 요청을 놓치는 경우 대비
    try:
        webbrowser.open("http://localhost:8501")
    except Exception:
        pass

    splash_queue.put(("status", "준비 완료! 브라우저가 열렸습니다.", ""))
    splash_queue.put(("done",))

    # 로딩창은 작업표시줄로 내려가지만, 사용자가 직접 닫기 전까지 프로세스는 계속 살아있어야 한다.
    try:
        returncode = proc.wait()
    except Exception:
        return

    if returncode not in (0, None) and returncode > 0:
        log(f"[오류] 웹 서버가 비정상 종료되었습니다 (종료 코드: {returncode}). run.log를 확인하세요.")

    os._exit(0)  # 남아있는 데몬 스레드와 무관하게 프로세스를 확실히 종료


def main():
    state = {"proc": None}

    def handle_manual_close():
        """로딩창을 사용자가 직접 닫았을 때 - 이미 떠 있을 수 있는 서버 프로세스를 정리하고 완전히 종료한다."""
        proc = state.get("proc")
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        threading.Timer(0.3, lambda: os._exit(0)).start()

    try:
        splash = Splash(on_close=handle_manual_close)
    except Exception as e:
        # tkinter를 쓸 수 없는 극히 예외적인 환경 - 콘솔이 있으면 최소한 로그라도 남긴다
        log(f"[오류] 로딩창을 생성하지 못했습니다: {e}")
        return

    q = queue.Queue()
    # daemon=False: 로딩창(mainloop)이 닫힌 뒤에도 이 스레드는 계속 살아서
    # 브라우저 탭 종료 감지를 이어가야 하므로, 메인 스레드 종료와 무관하게 유지되어야 한다.
    threading.Thread(target=run_backend, args=(q, state), daemon=False).start()

    def poll_queue():
        try:
            while True:
                item = q.get_nowait()
                kind = item[0]
                if kind == "status":
                    _, status, reason = item
                    splash.set_status(status, reason)
                    log(status)
                elif kind == "error":
                    _, reason = item
                    splash.show_error(reason)
                    log(f"[오류] {reason}")
                    return  # 에러 상태에서는 더 이상 폴링하지 않음 (사용자가 닫기 버튼으로 종료)
                elif kind == "done":
                    splash.root.after(900, splash.enter_running_mode)
        except queue.Empty:
            pass
        splash.root.after(150, poll_queue)

    splash.root.after(150, poll_queue)
    splash.root.mainloop()


if __name__ == "__main__":
    main()
