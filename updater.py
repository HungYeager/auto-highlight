# -*- coding: utf-8 -*-
"""
OpenCut Bodycam Studio - Auto-Updater
=====================================
Checks for updates from GitHub on startup, downloads the latest code,
and updates the local installation while strictly preserving user data
(config.json, cookies.txt, session_data.json, output clips, .venv).
"""

import os
import sys
import json
import shutil
import zipfile
import subprocess
import urllib.request
import urllib.error

# ── Configuration ─────────────────────────────────────────────────────────────
# Thay đổi URL này thành link raw GitHub repository của bạn sau khi tạo repo:
# Ví dụ: "https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/version.json"
UPDATE_SERVER_URL = "https://raw.githubusercontent.com/hunghoang/auto-highlight/main/version.json"

# Timeout tối đa (giây). Quá thời gian này sẽ bỏ qua update và mở app ngay
CHECK_TIMEOUT = 3

# Các file / thư mục cá nhân TUYỆT ĐỐI KHÔNG GHI ĐÈ khi cập nhật
PROTECTED_ITEMS = {
    "config.json",
    "cookies.txt",
    "session_data.json",
    ".venv",
    ".git",
    "output_clips",
    "temp_uploads",
    "raw_cuts",
    "test_out",
    "dist",
    "build"
}

def parse_version(v_str: str):
    """Chuyển chuỗi version '2.8.6' thành tuple số (2, 8, 6) để so sánh."""
    try:
        clean = str(v_str).strip().lstrip("vV")
        return tuple(int(x) for x in clean.split(".") if x.isdigit())
    except Exception:
        return (0, 0, 0)

def get_local_version() -> str:
    """Đọc version hiện tại từ version.json cục bộ."""
    if os.path.exists("version.json"):
        try:
            with open("version.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("version", "1.0.0")
        except Exception:
            pass
    return "1.0.0"

def get_repo_urls():
    """Lấy link version.json và link tải zip từ updater_config.json hoặc UPDATE_SERVER_URL."""
    server_url = UPDATE_SERVER_URL
    download_url = None
    if os.path.exists("updater_config.json"):
        try:
            with open("updater_config.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)
                repo_url = cfg.get("github_repo", "").strip().rstrip("/")
                if repo_url and "github.com" in repo_url:
                    parts = repo_url.replace("https://github.com/", "").replace("http://github.com/", "").split("/")
                    if len(parts) >= 2:
                        user, repo = parts[0], parts[1]
                        server_url = f"https://raw.githubusercontent.com/{user}/{repo}/main/version.json"
                        download_url = f"https://github.com/{user}/{repo}/archive/refs/heads/main.zip"
                elif cfg.get("update_url"):
                    server_url = cfg.get("update_url")
        except Exception:
            pass
    return server_url, download_url

def get_python_exe() -> str:
    """Lấy đường dẫn python của virtualenv hoặc sys.executable."""
    venv_py = os.path.join(".venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable

def check_and_apply_update():
    server_url, auto_download_url = get_repo_urls()

    if not server_url or "YOUR_USERNAME" in server_url:
        print("[Update] Chua cau hinh link GitHub repo. Bo qua kiem tra ban moi.")
        return

    local_ver = get_local_version()
    print(f"[Update] Phien ban hien tai: v{local_ver}")
    print("[Update] Dang kiem tra ban cap nhat...", end=" ", flush=True)

    try:
        req = urllib.request.Request(
            server_url,
            headers={"User-Agent": "OpenCutStudio-Updater/2.0"}
        )
        with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT) as resp:
            remote_data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        print("Bo qua (Khong co mang hoac server khong phan hoi).")
        return

    remote_ver = remote_data.get("version", local_ver)
    if parse_version(remote_ver) <= parse_version(local_ver):
        print("He thong dang o phien ban moi nhat.")
        return

    print(f"\n" + "=" * 60)
    print(f"  [!] CO BAN CAP NHAT MOI: v{remote_ver} (Hien tai: v{local_ver})")
    changelog = remote_data.get("changelog", "")
    if changelog:
        print(f"  Noi dung moi:\n{changelog}")
    print("=" * 60)

    download_url = remote_data.get("download_url") or auto_download_url
    if not download_url:
        if "raw.githubusercontent.com" in server_url:
            parts = server_url.replace("https://raw.githubusercontent.com/", "").split("/")
            if len(parts) >= 2:
                user, repo = parts[0], parts[1]
                download_url = f"https://github.com/{user}/{repo}/archive/refs/heads/main.zip"

    if not download_url:
        print("[Update] Khong tim thay link tai ban cap nhat. Bo qua.")
        return

    print(f"[Update] Dang tai ban cap nhat tu GitHub...")
    os.makedirs("temp_uploads", exist_ok=True)
    temp_zip = os.path.join("temp_uploads", "update_payload.zip")

    try:
        req_dl = urllib.request.Request(
            download_url,
            headers={"User-Agent": "OpenCutStudio-Updater/2.0"}
        )
        with urllib.request.urlopen(req_dl, timeout=30) as dl_resp, open(temp_zip, "wb") as out_f:
            shutil.copyfileobj(dl_resp, out_f)

        if not zipfile.is_zipfile(temp_zip):
            print("[Update] File tai ve khong hop le. Bo qua.")
            return

        print("[Update] Dang giai nen va cap nhat file...")
        with zipfile.ZipFile(temp_zip, "r") as zf:
            # GitHub archive zip luôn có thư mục gốc dạng: repo-main/...
            namelist = zf.namelist()
            prefix = ""
            if namelist and "/" in namelist[0]:
                prefix = namelist[0].split("/")[0] + "/"

            req_txt_before = None
            if os.path.exists("requirements.txt"):
                try:
                    with open("requirements.txt", "rb") as f:
                        req_txt_before = f.read()
                except Exception:
                    pass

            for member in zf.infolist():
                rel_path = member.filename
                if prefix and rel_path.startswith(prefix):
                    rel_path = rel_path[len(prefix):]

                if not rel_path or rel_path.endswith("/"):
                    continue

                # Kiểm tra danh sách bảo vệ
                first_dir = rel_path.replace("\\", "/").split("/")[0]
                if first_dir in PROTECTED_ITEMS or rel_path in PROTECTED_ITEMS:
                    continue

                target_path = os.path.abspath(rel_path)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with zf.open(member) as src_f, open(target_path, "wb") as dst_f:
                    shutil.copyfileobj(src_f, dst_f)

        # Nếu máy mới chưa có config.json, khởi tạo từ config.example.json
        if not os.path.exists("config.json") and os.path.exists("config.example.json"):
            try:
                shutil.copy("config.example.json", "config.json")
            except Exception:
                pass

        # Cập nhật version.json cục bộ
        with open("version.json", "w", encoding="utf-8") as f:
            json.dump({
                "version": remote_ver,
                "release_date": remote_data.get("release_date", ""),
                "changelog": changelog,
                "download_url": download_url
            }, f, indent=2, ensure_ascii=False)

        # Kiểm tra requirements.txt có gói mới không
        if os.path.exists("requirements.txt"):
            try:
                with open("requirements.txt", "rb") as f:
                    req_txt_after = f.read()
                if req_txt_before != req_txt_after:
                    print("[Update] Phat hien thu vien moi, dang tu dong cai dat qua pip...")
                    py_exe = get_python_exe()
                    subprocess.run([py_exe, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"], check=False)
            except Exception as e:
                print(f"[Update] Canh bao cai dat thu vien: {e}")

        print(f"[Update] >> CAP NHAT LEN v{remote_ver} THANH CONG! <<\n")

    except Exception as e:
        print(f"[Update] Loi trong qua trinh cap nhat: {e}. Vao app bang phien ban hien tai.")
    finally:
        if os.path.exists(temp_zip):
            try:
                os.remove(temp_zip)
            except Exception:
                pass

if __name__ == "__main__":
    check_and_apply_update()
