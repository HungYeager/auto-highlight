# -*- coding: utf-8 -*-
"""
OpenCut Studio - Smart Bootstrapper Launcher
=============================================
A lightweight, modern standalone launcher (~10MB) for OpenCut Bodycam Studio.
Checks for updates from GitHub Releases, downloads updates with a progress bar,
preserves user configurations, and launches the Web Studio automatically.
"""

import os
import sys
import json
import time
import shutil
import zipfile
import socket
import threading
import subprocess
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox

# ── Defaults ──────────────────────────────────────────────────────────────────
APP_NAME = "OpenCut Bodycam Studio"
DEFAULT_GITHUB_REPO = "https://github.com/hunghoang/auto-highlight"
TIMEOUT_CHECK = 3

# File & Thư mục được bảo vệ, tuyệt đối không ghi đè khi cập nhật
PROTECTED_ITEMS = {
    "config.json",
    "cookies.txt",
    "session_data.json",
    ".venv",
    ".git",
    "output_clips",
    "temp_uploads",
    "raw_cuts",
    "test_out"
}


def get_base_dir() -> str:
    """Xác định thư mục cài đặt app.
    Nếu chạy cùng thư mục với server.py -> Portable mode.
    Nếu là file exe độc lập của khách -> %LOCALAPPDATA%\\OpenCutStudio.
    """
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    if os.path.exists(os.path.join(exe_dir, "server.py")):
        return exe_dir
    local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    target = os.path.join(local_app_data, "OpenCutStudio")
    os.makedirs(target, exist_ok=True)
    return target


def parse_semver(v_str: str):
    try:
        clean = str(v_str).strip().lstrip("vV")
        return tuple(int(x) for x in clean.split(".") if x.isdigit())
    except Exception:
        return (0, 0, 0)


def get_local_version(app_dir: str) -> str:
    v_file = os.path.join(app_dir, "version.json")
    if os.path.exists(v_file):
        try:
            with open(v_file, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "1.0.0")
        except Exception:
            pass
    return "0.0.0"


def get_repo_url(app_dir: str) -> str:
    # 1. Tìm trong _MEIPASS (khi đóng gói vào file .exe độc lập)
    meipass = getattr(sys, "_MEIPASS", "")
    candidates = [
        os.path.join(meipass, "updater_config.json") if meipass else "",
        os.path.join(app_dir, "updater_config.json"),
        os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "updater_config.json")
    ]
    for cfg_file in candidates:
        if cfg_file and os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    url = json.load(f).get("github_repo", "").strip()
                    if url:
                        return url.rstrip("/")
            except Exception:
                pass
    return DEFAULT_GITHUB_REPO


class LauncherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.app_dir = get_base_dir()
        self.local_version = get_local_version(self.app_dir)
        self.github_repo = get_repo_url(self.app_dir)

        # Cấu hình cửa sổ
        self.title(APP_NAME)
        self.geometry("420x220")
        self.resizable(False, False)
        self.configure(bg="#0c0d16")

        # Căn giữa màn hình
        self.center_window(420, 220)

        # Giao diện Dark theme hiện đại
        self.setup_ui()

        # Bắt đầu luồng kiểm tra & khởi động ngầm
        threading.Thread(target=self.bootstrap_thread, daemon=True).start()

    def center_window(self, w, h):
        ws = self.winfo_screenwidth()
        hs = self.winfo_screenheight()
        x = (ws // 2) - (w // 2)
        y = (hs // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def setup_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Cyan.Horizontal.TProgressbar",
            troughcolor="#16192b",
            background="#6366f1",
            thickness=6,
            borderwidth=0
        )

        # Header Title
        title_lbl = tk.Label(
            self,
            text=APP_NAME,
            font=("Segoe UI", 13, "bold"),
            fg="#f8fafc",
            bg="#0c0d16"
        )
        title_lbl.pack(pady=(22, 2))

        sub_lbl = tk.Label(
            self,
            text="AI-Powered Video Highlight & Subtitle Studio",
            font=("Segoe UI", 8),
            fg="#94a3b8",
            bg="#0c0d16"
        )
        sub_lbl.pack()

        # Status text
        self.status_lbl = tk.Label(
            self,
            text="Đang kiểm tra kết nối...",
            font=("Segoe UI", 9),
            fg="#cbd5e1",
            bg="#0c0d16"
        )
        self.status_lbl.pack(pady=(28, 8))

        # Progress bar
        self.progress = ttk.Progressbar(
            self,
            style="Cyan.Horizontal.TProgressbar",
            orient="horizontal",
            length=350,
            mode="determinate"
        )
        self.progress.pack(pady=4)

        # Footer info (Version)
        ver_text = f"v{self.local_version}" if self.local_version != "0.0.0" else "Cài đặt lần đầu"
        self.footer_lbl = tk.Label(
            self,
            text=ver_text,
            font=("Consolas", 8),
            fg="#64748b",
            bg="#0c0d16"
        )
        self.footer_lbl.pack(side="bottom", pady=8)

    def set_status(self, text, pct=None):
        def _update():
            self.status_lbl.config(text=text)
            if pct is not None:
                self.progress["value"] = pct
        self.after(0, _update)

    def bootstrap_thread(self):
        time.sleep(0.3)
        has_server = os.path.exists(os.path.join(self.app_dir, "server.py"))

        # 1. Kiểm tra cập nhật từ GitHub
        remote_data = None
        if "YOUR_USERNAME" not in self.github_repo:
            self.set_status("Đang kiểm tra bản cập nhật mới...", 15)
            remote_data = self.fetch_remote_version()

        need_download = False
        remote_ver = self.local_version
        download_url = None

        if remote_data:
            remote_ver = remote_data.get("version", self.local_version)
            download_url = remote_data.get("download_url")
            # Tự động suy ra link main.zip nếu không khai báo
            if not download_url and "github.com" in self.github_repo:
                download_url = f"{self.github_repo}/archive/refs/heads/main.zip"

            if parse_semver(remote_ver) > parse_semver(self.local_version):
                need_download = True
            elif not has_server:
                need_download = True

        if not has_server and not need_download and not remote_data:
            self.set_status("Lỗi: Không thể tải mã nguồn lần đầu do mất mạng.", 0)
            messagebox.showerror(
                "Lỗi kết nối",
                "Chưa tìm thấy OpenCut Studio trên máy và không có kết nối Internet.\n\nVui lòng kiểm tra lại mạng và mở lại ứng dụng."
            )
            self.quit()
            return

        # 2. Tải bản cập nhật hoặc cài đặt mới
        if need_download and download_url:
            self.set_status(f"Đang tải bản cập nhật v{remote_ver}...", 25)
            success = self.download_and_extract(download_url, remote_ver, remote_data)
            if not success and not has_server:
                self.set_status("Cài đặt thất bại.", 0)
                messagebox.showerror("Lỗi tải bản cài đặt", "Không thể hoàn tất tải ứng dụng từ máy chủ.")
                self.quit()
                return

        # 3. Khởi động ứng dụng
        self.set_status("Đang khởi động Web Studio...", 90)
        self.launch_studio()

    def fetch_remote_version(self):
        try:
            # Chuyển link https://github.com/user/repo -> https://raw.githubusercontent.com/user/repo/main/version.json
            repo_clean = self.github_repo.replace("https://github.com/", "").replace("http://github.com/", "")
            raw_url = f"https://raw.githubusercontent.com/{repo_clean}/main/version.json"
            req = urllib.request.Request(raw_url, headers={"User-Agent": "OpenCutLauncher/2.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_CHECK) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def download_and_extract(self, download_url: str, new_ver: str, remote_data: dict) -> bool:
        temp_dir = os.path.join(self.app_dir, "temp_uploads")
        os.makedirs(temp_dir, exist_ok=True)
        zip_path = os.path.join(temp_dir, "update_payload.zip")

        try:
            req = urllib.request.Request(download_url, headers={"User-Agent": "OpenCutLauncher/2.0"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(zip_path, "wb") as out_f:
                total_size = resp.getheader("Content-Length")
                total_bytes = int(total_size) if total_size and total_size.isdigit() else 0
                downloaded = 0
                block_size = 64 * 1024

                while True:
                    chunk = resp.read(block_size)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    downloaded += len(chunk)
                    if total_bytes > 0:
                        pct = 25 + int((downloaded / total_bytes) * 60)
                        mb = downloaded / (1024 * 1024)
                        total_mb = total_bytes / (1024 * 1024)
                        self.set_status(f"Đang tải v{new_ver}: {mb:.1f}MB / {total_mb:.1f}MB ({pct}%)", pct)
                    else:
                        mb = downloaded / (1024 * 1024)
                        self.set_status(f"Đang tải v{new_ver}: {mb:.1f}MB...", 50)

            self.set_status("Đang cài đặt file cập nhật...", 88)
            with zipfile.ZipFile(zip_path, "r") as zf:
                namelist = zf.namelist()
                prefix = ""
                if namelist and "/" in namelist[0]:
                    prefix = namelist[0].split("/")[0] + "/"

                for member in zf.infolist():
                    rel_path = member.filename
                    if prefix and rel_path.startswith(prefix):
                        rel_path = rel_path[len(prefix):]
                    if not rel_path or rel_path.endswith("/"):
                        continue

                    first_part = rel_path.replace("\\", "/").split("/")[0]
                    if first_part in PROTECTED_ITEMS or rel_path in PROTECTED_ITEMS:
                        continue

                    target = os.path.join(self.app_dir, rel_path)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            # Cập nhật version.json cục bộ
            ver_path = os.path.join(self.app_dir, "version.json")
            with open(ver_path, "w", encoding="utf-8") as f:
                json.dump({
                    "version": new_ver,
                    "release_date": (remote_data or {}).get("release_date", ""),
                    "changelog": (remote_data or {}).get("changelog", ""),
                    "download_url": download_url
                }, f, indent=2, ensure_ascii=False)

            # Khởi tạo config.json từ config.example.json nếu máy mới tinh
            cfg_p = os.path.join(self.app_dir, "config.json")
            cfg_ex = os.path.join(self.app_dir, "config.example.json")
            if not os.path.exists(cfg_p) and os.path.exists(cfg_ex):
                try:
                    shutil.copy(cfg_ex, cfg_p)
                except Exception:
                    pass

            return True
        except Exception as e:
            print(f"[Launcher] Download error: {e}")
            return False
        finally:
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except Exception:
                    pass

    def launch_studio(self):
        # Dọn dẹp tiến trình treo cổng 8000
        try:
            for port in [8000]:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    if s.connect_ex(("127.0.0.1", port)) == 0:
                        subprocess.run(
                            ["powershell", "-Command", f"Get-Process -Id (Get-NetTCPConnection -LocalPort {port}).OwningProcess -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"],
                            capture_output=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                        )
        except Exception:
            pass

        # Tìm python exe phù hợp
        py_exe = sys.executable
        venv_py = os.path.join(self.app_dir, ".venv", "Scripts", "python.exe")
        if os.path.exists(venv_py):
            py_exe = venv_py

        # Khởi chạy server.py
        server_py = os.path.join(self.app_dir, "server.py")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        try:
            subprocess.Popen(
                [py_exe, "-X", "utf8", server_py],
                cwd=self.app_dir,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        except Exception as e:
            messagebox.showerror("Lỗi khởi động", f"Không thể khởi động server: {e}")
            self.quit()
            return

        # Chờ server mở cổng và bật trình duyệt
        self.set_status("Đang mở trình duyệt...", 100)
        time.sleep(1.8)

        url = "http://127.0.0.1:8000"
        try:
            subprocess.Popen(
                ["msedge.exe", f"--app={url}", "--window-size=1440,900"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        except Exception:
            try:
                subprocess.Popen(
                    ["chrome.exe", f"--app={url}", "--window-size=1440,900"],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
            except Exception:
                import webbrowser
                webbrowser.open(url)

        # Đóng launcher
        time.sleep(1.0)
        self.destroy()


if __name__ == "__main__":
    app = LauncherApp()
    app.mainloop()
