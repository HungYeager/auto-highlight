# -*- coding: utf-8 -*-
"""
OpenCut Studio - Smart Bootstrapper Launcher (Engine Release Downloader)
=======================================================================
A standalone launcher (~11MB) for end users.
Downloads the packaged standalone engine from GitHub Releases on first launch,
automatically checks for updates, and launches the desktop studio without
requiring Python, Git, or any dependencies on the client machine.
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

APP_NAME = "OpenCut Bodycam Studio"
DEFAULT_GITHUB_REPO = "https://github.com/HungYeager/auto-highlight"
TIMEOUT_CHECK = 10


def get_install_dir() -> str:
    """Thư mục cài đặt cố định trên máy khách: %LOCALAPPDATA%\\OpenCutStudio."""
    local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    target = os.path.join(local_app_data, "OpenCutStudio")
    os.makedirs(target, exist_ok=True)
    return target


def get_repo_url(install_dir: str) -> str:
    """Lấy link GitHub repository từ file cấu hình nhúng hoặc file cục bộ."""
    meipass = getattr(sys, "_MEIPASS", "")
    candidates = [
        os.path.join(meipass, "updater_config.json") if meipass else "",
        os.path.join(install_dir, "updater_config.json"),
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


def parse_semver(v_str: str):
    try:
        clean = str(v_str).strip().lstrip("vV")
        return tuple(int(x) for x in clean.split(".") if x.isdigit())
    except Exception:
        return (0, 0, 0)


def find_engine_exe(app_dir: str) -> str:
    """Tìm file OpenCutStudio.exe (Engine đóng gói) trong thư mục app."""
    # 1. Kiểm tra trực tiếp trong app_dir/app/OpenCutStudio.exe
    primary = os.path.join(app_dir, "app", "OpenCutStudio.exe")
    if os.path.exists(primary):
        return primary

    # 2. Kiểm tra trực tiếp trong app_dir/OpenCutStudio.exe (nếu không dùng thư mục con)
    # Lưu ý: Không trỏ nhầm vào chính file launcher hiện tại sys.argv[0]!
    current_launcher = os.path.abspath(sys.argv[0])
    direct = os.path.join(app_dir, "OpenCutStudio.exe")
    if os.path.exists(direct) and os.path.abspath(direct).lower() != current_launcher.lower():
        return direct

    # 3. Quét đệ quy tìm file OpenCutStudio.exe trong app_dir
    for root, _, files in os.walk(os.path.join(app_dir, "app")):
        for f in files:
            if f.lower() == "opencutstudio.exe":
                found = os.path.join(root, f)
                if os.path.abspath(found).lower() != current_launcher.lower():
                    return found
    return ""


class LauncherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.install_dir = get_install_dir()
        self.github_repo = get_repo_url(self.install_dir)
        self.version_file = os.path.join(self.install_dir, "version.txt")

        # Cấu hình cửa sổ Launcher
        self.title(APP_NAME)
        self.geometry("440x230")
        self.resizable(False, False)
        self.configure(bg="#0c0d16")

        self.center_window(440, 230)
        self.setup_ui()

        # Bắt đầu luồng xử lý
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
            "Indigo.Horizontal.TProgressbar",
            troughcolor="#16192b",
            background="#6366f1",
            thickness=8,
            borderwidth=0
        )

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
            text="Standalone AI Video Clipper & Subtitle Engine",
            font=("Segoe UI", 8),
            fg="#94a3b8",
            bg="#0c0d16"
        )
        sub_lbl.pack()

        self.status_lbl = tk.Label(
            self,
            text="Đang kết nối hệ thống...",
            font=("Segoe UI", 9),
            fg="#cbd5e1",
            bg="#0c0d16"
        )
        self.status_lbl.pack(pady=(25, 8))

        self.progress = ttk.Progressbar(
            self,
            style="Indigo.Horizontal.TProgressbar",
            orient="horizontal",
            length=370,
            mode="determinate"
        )
        self.progress.pack(pady=4)

        local_ver = self.get_local_version()
        ver_text = f"v{local_ver}" if local_ver != "0.0.0" else "Khởi tạo lần đầu"
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

    def get_local_version(self) -> str:
        # 1. Đọc từ version.txt trong thư mục install
        if os.path.exists(self.version_file):
            try:
                with open(self.version_file, "r", encoding="utf-8") as f:
                    v = f.read().strip()
                    if v and v != "0.0.0":
                        return v
            except Exception:
                pass

        # 2. Đọc dự phòng từ app/version.json
        app_vjson = os.path.join(self.install_dir, "app", "version.json")
        if os.path.exists(app_vjson):
            try:
                with open(app_vjson, "r", encoding="utf-8") as f:
                    v = json.load(f).get("version", "").strip()
                    if v:
                        return v
            except Exception:
                pass

        return "0.0.0"

    def set_local_version(self, v_str: str):
        v_clean = v_str.strip().lstrip("vV")
        try:
            with open(self.version_file, "w", encoding="utf-8") as f:
                f.write(v_clean)
        except Exception:
            pass
        try:
            app_vjson = os.path.join(self.install_dir, "app", "version.json")
            if os.path.exists(app_vjson):
                with open(app_vjson, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["version"] = v_clean
                with open(app_vjson, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def fetch_latest_release(self):
        """Lấy thông tin Release mới nhất từ GitHub API (chống cache CDN và sắp xếp semver chuẩn)."""
        repo_clean = self.github_repo.replace("https://github.com/", "").replace("http://github.com/", "").rstrip("/")
        headers = {
            "User-Agent": "OpenCutLauncher/2.1",
            "Accept": "application/vnd.github.v3+json",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache"
        }

        # 1. Thử lấy danh sách releases có timestamp chống CDN cache
        try:
            ts = int(time.time())
            api_url = f"https://api.github.com/repos/{repo_clean}/releases?per_page=10&_t={ts}"
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT_CHECK) as resp:
                releases = json.loads(resp.read().decode("utf-8"))
                if isinstance(releases, list) and releases:
                    valid = [r for r in releases if not r.get("draft", False)]
                    if valid:
                        valid.sort(key=lambda r: parse_semver(r.get("tag_name", "")), reverse=True)
                        return valid[0]
        except Exception as e:
            print(f"[Launcher] Releases list fetch error: {e}")

        # 2. Fallback sang /releases/latest nếu danh sách lỗi
        try:
            api_url = f"https://api.github.com/repos/{repo_clean}/releases/latest"
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT_CHECK) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[Launcher] Release latest fetch error: {e}")
            return None

    def bootstrap_thread(self):
        time.sleep(0.3)
        engine_exe = find_engine_exe(self.install_dir)
        has_engine = bool(engine_exe and os.path.exists(engine_exe))
        local_ver = self.get_local_version()

        self.set_status("Đang kiểm tra bản phát hành trên GitHub...", 10)
        release_info = self.fetch_latest_release()

        need_download = False
        target_asset = None
        remote_tag = local_ver

        if release_info:
            remote_tag = release_info.get("tag_name", "").lstrip("vV")
            assets = release_info.get("assets", [])
            # Tìm asset zip (ưu tiên file zip chứa OpenCut hoặc Core)
            for a in assets:
                name = a.get("name", "").lower()
                if name.endswith(".zip"):
                    target_asset = a
                    break

            if not has_engine:
                need_download = True
            elif target_asset and parse_semver(remote_tag) > parse_semver(local_ver):
                need_download = True

        # Nếu chưa có Engine mà không thể kết nối GitHub
        if not has_engine and (not release_info or not target_asset):
            self.set_status("Lỗi: Không tìm thấy gói Engine trên GitHub.", 0)
            messagebox.showerror(
                "Chưa có bản phát hành",
                "Chưa tìm thấy gói cài đặt Engine trên GitHub Releases.\n\n"
                f"Vui lòng tạo Release trên GitHub: {self.github_repo}/releases "
                "và đính kèm file zip đóng gói của Studio."
            )
            self.quit()
            return

        # Tải Engine đóng gói hoặc Cập nhật
        if need_download and target_asset:
            download_url = target_asset.get("browser_download_url")
            asset_size = target_asset.get("size", 0)
            asset_name = target_asset.get("name", "Engine.zip")

            if has_engine and parse_semver(remote_tag) > parse_semver(local_ver):
                self.set_status(f"Phát hiện bản mới v{remote_tag}! Đang tải gói cập nhật...", 15)
                self.after(0, lambda: self.footer_lbl.config(text=f"Nâng cấp: v{local_ver} ➔ v{remote_tag}"))
            else:
                self.set_status(f"Đang chuẩn bị tải gói Studio v{remote_tag}...", 15)
                self.after(0, lambda: self.footer_lbl.config(text=f"Cài đặt mới: v{remote_tag}"))

            success = self.download_and_extract_engine(download_url, asset_size, remote_tag)
            if not success and not has_engine:
                messagebox.showerror("Lỗi tải Engine", "Quá trình tải gói Engine thất bại. Vui lòng kiểm tra kết nối mạng.")
                self.quit()
                return

        # Tìm lại engine_exe sau khi giải nén
        engine_exe = find_engine_exe(self.install_dir)
        if not engine_exe or not os.path.exists(engine_exe):
            self.set_status("Không tìm thấy file OpenCutStudio.exe sau khi giải nén.", 0)
            messagebox.showerror("Lỗi cài đặt", "Không tìm thấy file OpenCutStudio.exe trong gói giải nén.")
            self.quit()
            return

        # Khởi chạy Engine
        self.set_status("Đang khởi động OpenCut Studio Engine...", 95)
        self.launch_engine(engine_exe)

    def download_and_extract_engine(self, url: str, total_bytes: int, tag_version: str) -> bool:
        temp_dir = os.path.join(self.install_dir, "temp_downloads")
        os.makedirs(temp_dir, exist_ok=True)
        zip_path = os.path.join(temp_dir, "engine_download.zip")

        # 1. Kiểm tra nếu có file zip cục bộ trong cùng thư mục launcher (người dùng copy qua USB/Zalo)
        launcher_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        local_candidates = [
            os.path.join(launcher_dir, f"OpenCutStudio_v{tag_version}.zip"),
            os.path.join(launcher_dir, f"OpenCutStudio_{tag_version}.zip"),
            os.path.join(launcher_dir, "OpenCutStudio.zip"),
        ]
        local_zip = None
        for cand in local_candidates:
            if os.path.exists(cand) and os.path.getsize(cand) > 10 * 1024 * 1024:
                local_zip = cand
                break

        if not local_zip:
            try:
                clean_tag = tag_version.lstrip("vV")
                for f in os.listdir(launcher_dir):
                    name_lower = f.lower()
                    if name_lower.endswith(".zip") and "opencut" in name_lower and clean_tag in name_lower:
                        full_f = os.path.join(launcher_dir, f)
                        if os.path.getsize(full_f) > 50 * 1024 * 1024:
                            local_zip = full_f
                            break
            except Exception:
                pass

        # 2. Nếu có file zip cục bộ, bỏ qua việc tải từ internet
        target_zip_to_extract = zip_path
        if local_zip:
            self.set_status("Phát hiện gói Engine cục bộ trong thư mục, đang giải nén...", 85)
            target_zip_to_extract = local_zip
        else:
            # 3. Tải từ GitHub Releases có hỗ trợ TẢI TIẾP (Resume) nếu bị ngắt giữa chừng
            try:
                existing_bytes = 0
                if os.path.exists(zip_path):
                    existing_bytes = os.path.getsize(zip_path)
                    # Nếu file cũ đã đủ kích thước, kiểm tra xem zip có toàn vẹn không
                    if total_bytes > 0 and existing_bytes >= total_bytes:
                        try:
                            with zipfile.ZipFile(zip_path, "r") as test_zf:
                                if test_zf.testzip() is None:
                                    existing_bytes = total_bytes
                        except Exception:
                            existing_bytes = 0

                req_headers = {"User-Agent": "OpenCutLauncher/2.0"}
                file_mode = "wb"
                downloaded = 0

                if 0 < existing_bytes < total_bytes:
                    req_headers["Range"] = f"bytes={existing_bytes}-"
                    file_mode = "ab"
                    downloaded = existing_bytes

                if downloaded < total_bytes or total_bytes == 0:
                    req = urllib.request.Request(url, headers=req_headers)
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        resp_code = getattr(resp, "status", getattr(resp, "code", 200))
                        if resp_code == 200 and existing_bytes > 0 and downloaded > 0:
                            file_mode = "wb"
                            downloaded = 0

                        with open(zip_path, file_mode) as out_f:
                            block_size = 256 * 1024
                            start_t = time.time()
                            last_ui_t = start_t
                            bytes_since_ui = 0

                            if downloaded > 0:
                                mb_done = downloaded / (1024 * 1024)
                                self.set_status(f"Tiếp tục tải từ {mb_done:.1f}MB...", 20)

                            while True:
                                chunk = resp.read(block_size)
                                if not chunk:
                                    break
                                out_f.write(chunk)
                                downloaded += len(chunk)
                                bytes_since_ui += len(chunk)

                                now = time.time()
                                if now - last_ui_t >= 0.35:
                                    dt = now - last_ui_t
                                    speed_mb = (bytes_since_ui / (1024 * 1024)) / dt if dt > 0 else 0
                                    bytes_since_ui = 0
                                    last_ui_t = now

                                    if total_bytes > 0:
                                        pct = 20 + int((downloaded / total_bytes) * 65)
                                        mb = downloaded / (1024 * 1024)
                                        total_mb = total_bytes / (1024 * 1024)
                                        rem_mb = max(0.0, total_mb - mb)
                                        eta_s = int(rem_mb / speed_mb) if speed_mb > 0.05 else 0
                                        eta_str = f"{eta_s//60}p{eta_s%60:02d}s" if eta_s >= 60 else f"{eta_s}s"
                                        self.set_status(
                                            f"Đang tải v{tag_version}: {mb:.1f}MB/{total_mb:.1f}MB ({pct}%) • {speed_mb:.1f}MB/s • Còn ~{eta_str}",
                                            pct
                                        )
                                    else:
                                        mb = downloaded / (1024 * 1024)
                                        self.set_status(f"Đang tải: {mb:.1f}MB...", 50)
            except Exception as e:
                print(f"[Launcher] Download error: {e}")
                return False

        # 4. Đóng mọi tiến trình OpenCutStudio cũ đang chạy để tránh lỗi Permission denied khi ghi đè
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "OpenCutStudio.exe", "/T"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            time.sleep(0.5)
        except Exception:
            pass

        # 5. Giải nén Engine vào thư mục app
        self.set_status(f"Đang giải nén bộ Engine v{tag_version}... Vui lòng đợi trong giây lát!", 88)
        app_dir = os.path.join(self.install_dir, "app")
        os.makedirs(app_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(target_zip_to_extract, "r") as zf:
                namelist = zf.namelist()
                prefix = ""
                parts = namelist[0].replace("\\", "/").split("/")
                if len(parts) > 1 and parts[0] and all(n.startswith(parts[0] + "/") for n in namelist if n.strip()):
                    prefix = parts[0] + "/"

                for member in zf.infolist():
                    rel = member.filename
                    if prefix and rel.startswith(prefix):
                        rel = rel[len(prefix):]
                    if not rel or rel.endswith("/"):
                        continue

                    # Giữ nguyên cấu hình người dùng cũ
                    if rel in ["config.json", "cookies.txt", "session_data.json"]:
                        user_cfg = os.path.join(app_dir, rel)
                        if os.path.exists(user_cfg):
                            continue

                    target = os.path.join(app_dir, rel)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            self.set_local_version(tag_version)
            self.set_status(f"Cài đặt hoàn tất! Đang khởi động v{tag_version}...", 98)
            self.after(0, lambda: self.footer_lbl.config(text=f"v{tag_version}"))
            return True
        except Exception as e:
            print(f"[Launcher] Extract error: {e}")
            return False
        finally:
            if not local_zip and os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except Exception:
                    pass

    def launch_engine(self, engine_exe: str):
        """Khởi động file OpenCutStudio.exe (Engine độc lập mã máy)."""
        engine_dir = os.path.dirname(engine_exe)

        # Dọn port 8000 nếu đang có process cũ chiếm giữ
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", 8000)) == 0:
                    subprocess.run(
                        ["powershell", "-Command", "Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"],
                        capture_output=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    )
        except Exception:
            pass

        try:
            # Khởi chạy engine_exe trong thư mục của nó
            subprocess.Popen(
                [engine_exe],
                cwd=engine_dir,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        except Exception as e:
            messagebox.showerror("Lỗi khởi động Engine", f"Không thể bật engine: {e}")
            self.quit()
            return

        # Chờ port 8000 sẵn sàng và mở giao diện
        self.set_status("Đang mở giao diện Studio...", 100)
        time.sleep(2.5)

        # Mở Edge/Chrome ở dạng cửa sổ Desktop app
        url = "http://127.0.0.1:8000"
        try:
            subprocess.Popen(["msedge.exe", f"--app={url}", "--window-size=1440,900"],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            try:
                subprocess.Popen(["chrome.exe", f"--app={url}", "--window-size=1440,900"],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception:
                import webbrowser
                webbrowser.open(url)

        time.sleep(1.0)
        self.destroy()


if __name__ == "__main__":
    app = LauncherApp()
    app.mainloop()
