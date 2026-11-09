# -*- coding: utf-8 -*-
"""
Module: native_dialogs.py
Deep module for 3-tier Windows native file/folder dialogs (In-process Tkinter,
PowerShell STA WinForms UTF-8, and ctypes Comdlg32/Shell32) and Unicode-safe
cross-machine path resolution.
"""

import base64
import os
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


_last_opened_folders: Dict[str, float] = {}


def _ctypes_pick_folder(title: str) -> str:
    """Windows-native folder picker via Shell32 ctypes."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        import ctypes.wintypes as wt

        class BROWSEINFO(ctypes.Structure):
            _fields_ = [
                ("hwndOwner",      wt.HWND),
                ("pidlRoot",       ctypes.c_void_p),
                ("pszDisplayName", ctypes.c_wchar_p),
                ("lpszTitle",      ctypes.c_wchar_p),
                ("ulFlags",        wt.UINT),
                ("lpfn",           ctypes.c_void_p),
                ("lParam",         wt.LPARAM),
                ("iImage",         ctypes.c_int),
            ]

        shell32 = ctypes.windll.shell32
        ole32   = ctypes.windll.ole32
        try:
            ole32.CoInitialize(0)
        except Exception:
            pass

        disp_buf = ctypes.create_unicode_buffer(32768)
        bi = BROWSEINFO()
        bi.pszDisplayName = ctypes.cast(disp_buf, ctypes.c_wchar_p)
        bi.lpszTitle      = title
        bi.ulFlags        = 0x0001   # BIF_RETURNONLYFSDIRS

        shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
        pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))

        result = ""
        if pidl:
            path_buf = ctypes.create_unicode_buffer(32768)
            shell32.SHGetPathFromIDListW(ctypes.c_void_p(pidl), path_buf)
            ole32.CoTaskMemFree(ctypes.c_void_p(pidl))
            result = path_buf.value
        try:
            ole32.CoUninitialize()
        except Exception:
            pass
        return result
    except Exception as exc:
        print(f"[dialog] ctypes folder picker: {exc}")
        return ""


def _ctypes_pick_files(title: str, filter_pairs: list, multi: bool = True) -> list[str]:
    """Windows-native file picker via comdlg32 ctypes."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        import ctypes.wintypes as wt

        # Build null-delimited filter string: "Name\0*.ext\0Name2\0*.ext2\0\0"
        filter_raw = "".join(f"{name}\0{pat}\0" for name, pat in filter_pairs) + "\0\0"
        filter_buf = ctypes.create_unicode_buffer(len(filter_raw) + 4)
        for i, c in enumerate(filter_raw):
            filter_buf[i] = c

        BUF      = 1 << 20   # 1 MB — enough for hundreds of long paths
        file_buf = ctypes.create_unicode_buffer(BUF)

        class OPENFILENAMEW(ctypes.Structure):
            _fields_ = [
                ("lStructSize",       wt.DWORD),
                ("hwndOwner",         wt.HWND),
                ("hInstance",         wt.HINSTANCE),
                ("lpstrFilter",       ctypes.c_void_p),
                ("lpstrCustomFilter", ctypes.c_void_p),
                ("nMaxCustFilter",    wt.DWORD),
                ("nFilterIndex",      wt.DWORD),
                ("lpstrFile",         ctypes.c_void_p),
                ("nMaxFile",          wt.DWORD),
                ("lpstrFileTitle",    ctypes.c_void_p),
                ("nMaxFileTitle",     wt.DWORD),
                ("lpstrInitialDir",   ctypes.c_wchar_p),
                ("lpstrTitle",        ctypes.c_wchar_p),
                ("Flags",             wt.DWORD),
                ("nFileOffset",       wt.WORD),
                ("nFileExtension",    wt.WORD),
                ("lpstrDefExt",       ctypes.c_wchar_p),
                ("lCustData",         wt.LPARAM),
                ("lpfnHook",          ctypes.c_void_p),
                ("lpTemplateName",    ctypes.c_wchar_p),
                ("pvReserved",        ctypes.c_void_p),
                ("dwReserved",        wt.DWORD),
                ("FlagsEx",           wt.DWORD),
            ]

        OFN_ALLOWMULTISELECT = 0x00000200
        OFN_EXPLORER         = 0x00080000
        OFN_FILEMUSTEXIST    = 0x00001000
        OFN_HIDEREADONLY     = 0x00000004

        ofn = OPENFILENAMEW()
        ofn.lStructSize  = ctypes.sizeof(OPENFILENAMEW)
        ofn.lpstrFilter  = ctypes.cast(filter_buf, ctypes.c_void_p)
        ofn.nFilterIndex = 1
        ofn.lpstrFile    = ctypes.cast(file_buf, ctypes.c_void_p)
        ofn.nMaxFile     = BUF
        ofn.lpstrTitle   = title
        ofn.Flags        = OFN_HIDEREADONLY | OFN_FILEMUSTEXIST | OFN_EXPLORER
        if multi:
            ofn.Flags |= OFN_ALLOWMULTISELECT

        comdlg32 = ctypes.windll.comdlg32
        if not comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            return []

        raw_str = ""
        for i in range(BUF):
            ch = file_buf[i]
            if ch == '\x00':
                if i + 1 < BUF and file_buf[i + 1] == '\x00':
                    break
                raw_str += '\x00'
            else:
                raw_str += ch

        parts = [p for p in raw_str.split('\x00') if p]
        if not parts:
            return []
        if not multi or len(parts) == 1:
            return parts
        directory = Path(parts[0])
        return [str(directory / name) for name in parts[1:]]
    except Exception as exc:
        print(f"[dialog] ctypes file picker error: {exc}")
        return []


def _safe_resolve_path(p_str: str, app_state_ref: Any = None) -> Optional[Path]:
    """Resolve file path handling Unicode normalization (NFC/NFD) and Windows path separators."""
    if not p_str or not isinstance(p_str, str):
        return None
    raw = p_str.strip().strip('"').strip("'")
    if not raw:
        return None
    p = Path(raw)
    if p.exists():
        return p
    # Try Unicode NFC normalization
    try:
        p_nfc = Path(unicodedata.normalize("NFC", raw))
        if p_nfc.exists():
            return p_nfc
    except Exception:
        pass
    # Try Unicode NFD normalization
    try:
        p_nfd = Path(unicodedata.normalize("NFD", raw))
        if p_nfd.exists():
            return p_nfd
    except Exception:
        pass
    # Try standard normalized path
    try:
        p_norm = Path(os.path.normpath(raw))
        if p_norm.exists():
            return p_norm
    except Exception:
        pass
    # Cross-machine fallback: check if file with same name exists in output/raw_cuts/cwd
    try:
        filename = p.name
        if filename:
            candidate_dirs = []
            try:
                st_obj = app_state_ref
                if st_obj is None and "server" in sys.modules:
                    st_obj = getattr(sys.modules["server"], "app_state", None)
                if st_obj is not None:
                    out_folder = st_obj.get_current_output_folder()
                    if out_folder:
                        p_out = Path(out_folder)
                        candidate_dirs.extend([p_out, p_out / "raw_cuts"])
                    cfg_out = st_obj.config.get("output_folder")
                    if cfg_out:
                        p_cfg = Path(cfg_out)
                        candidate_dirs.extend([p_cfg, p_cfg / "raw_cuts"])
                    for b in st_obj.batches.values():
                        b_out = b.get("output_folder")
                        if b_out:
                            p_b = Path(b_out)
                            candidate_dirs.extend([p_b, p_b / "raw_cuts"])
            except Exception:
                pass
            candidate_dirs.extend([
                Path.cwd(),
                Path.cwd() / "output_clips",
                Path.cwd() / "output_clips" / "raw_cuts",
                Path.cwd() / "raw_cuts",
            ])
            for c_dir in candidate_dirs:
                try:
                    c_file = c_dir / filename
                    if c_file.is_file():
                        return c_file
                except Exception:
                    pass
    except Exception:
        pass
    return p if p.exists() else None


def _py_pick_files(title: str, filetypes: list, multi: bool = True) -> list[str]:
    """Robust Windows-native file picker with explicit UTF-8 encoding.
    
    Order of execution:
    1. Direct in-process Tkinter in worker thread (bundled inside PyInstaller EXE)
    2. Native Windows PowerShell OpenFileDialog (100% reliable on every Windows PC without Python)
    3. Direct Win32 comdlg32 GetOpenFileNameW via ctypes
    """
    # 1. Try in-process Tkinter (bundled inside .exe)
    try:
        res_list = []
        err = []
        def _tk_work():
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                root.focus_force()
                if multi:
                    r = filedialog.askopenfilenames(title=title, filetypes=filetypes)
                else:
                    r = filedialog.askopenfilename(title=title, filetypes=filetypes)
                root.destroy()
                if r:
                    if isinstance(r, (list, tuple)):
                        res_list.extend(r)
                    else:
                        res_list.append(r)
            except Exception as e:
                err.append(e)

        th = threading.Thread(target=_tk_work, daemon=True)
        th.start()
        th.join(timeout=120)
        if not err and (res_list or not th.is_alive()):
            return [str(p) for p in res_list if p]
    except Exception:
        pass

    # 2. Fallback: Native PowerShell OpenFileDialog (pre-installed on 100% of Windows 7/8/10/11)
    try:
        filter_parts = []
        if filetypes:
            for name, pat in filetypes:
                clean_pat = pat.replace(";", ";")
                filter_parts.append(f"{name} ({clean_pat})|{clean_pat}")
        else:
            filter_parts.append("All Files (*.*)|*.*")
        filter_str = "|".join(filter_parts).replace("'", "''")
        multis = "$true" if multi else "$false"

        ps_code = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
            "[Console]::InputEncoding  = [System.Text.Encoding]::UTF8\n"
            "$OutputEncoding          = [System.Text.Encoding]::UTF8\n"
            "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null\n"
            "$f = New-Object System.Windows.Forms.OpenFileDialog\n"
            f"$f.Title = '{title}'\n"
            f"$f.Filter = '{filter_str}'\n"
            f"$f.Multiselect = {multis}\n"
            "$f.RestoreDirectory = $true\n"
            "$f.AutoUpgradeEnabled = $true\n"
            "$res = $f.ShowDialog()\n"
            "if ($res -eq [System.Windows.Forms.DialogResult]::OK) {\n"
            "    $f.FileNames | ForEach-Object { [Console]::WriteLine($_) }\n"
            "}\n"
        )
        enc = base64.b64encode(ps_code.encode("utf-16le")).decode("ascii")
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-EncodedCommand", enc],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if res.stdout:
            out_lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
            if out_lines:
                return out_lines
    except Exception as e:
        print(f"[dialog] PowerShell file picker error: {e}")

    # 3. Final Fallback: Direct ctypes comdlg32 GetOpenFileNameW
    try:
        pairs = [(name, pat.replace(";", ";")) for name, pat in filetypes]
        return _ctypes_pick_files(title, pairs, multi=multi)
    except Exception as e:
        print(f"[dialog] ctypes file picker error: {e}")
        return []


def _py_pick_folder(title: str) -> str:
    """Robust Windows-native folder picker with explicit UTF-8 encoding.
    
    Order of execution:
    1. Direct in-process Tkinter in worker thread (bundled inside PyInstaller EXE)
    2. Native Windows PowerShell FolderBrowserDialog (100% reliable on every Windows PC)
    3. Direct Win32 Shell32 via ctypes
    """
    # 1. Try in-process Tkinter (bundled inside .exe)
    try:
        res_val = []
        err = []
        def _tk_work():
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                root.focus_force()
                r = filedialog.askdirectory(title=title)
                root.destroy()
                if r:
                    res_val.append(r)
            except Exception as e:
                err.append(e)

        th = threading.Thread(target=_tk_work, daemon=True)
        th.start()
        th.join(timeout=120)
        if not err and (res_val or not th.is_alive()):
            return str(res_val[0]) if res_val else ""
    except Exception:
        pass

    # 2. Fallback: Native PowerShell FolderBrowserDialog
    try:
        ps_code = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
            "[Console]::InputEncoding  = [System.Text.Encoding]::UTF8\n"
            "$OutputEncoding          = [System.Text.Encoding]::UTF8\n"
            "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null\n"
            "$f = New-Object System.Windows.Forms.FolderBrowserDialog\n"
            f"$f.Description = '{title}'\n"
            "$f.ShowNewFolderButton = $true\n"
            "$res = $f.ShowDialog()\n"
            "if ($res -eq [System.Windows.Forms.DialogResult]::OK) {\n"
            "    [Console]::WriteLine($f.SelectedPath)\n"
            "}\n"
        )
        enc = base64.b64encode(ps_code.encode("utf-16le")).decode("ascii")
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-EncodedCommand", enc],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if res.stdout:
            out = res.stdout.strip()
            if out:
                return out
    except Exception as e:
        print(f"[dialog] PowerShell folder picker error: {e}")

    # 3. Final Fallback: Direct ctypes Shell32 SHBrowseForFolderW
    try:
        return _ctypes_pick_folder(title)
    except Exception as e:
        print(f"[dialog] ctypes folder picker error: {e}")
        return ""


def _reveal_folder_in_explorer(folder_path: str, log_fn: Optional[Callable[[str, str], None]] = None) -> str:
    """Reliably open a folder in Windows Explorer without opening duplicate windows."""
    target = os.path.normpath(os.path.abspath(folder_path))
    try:
        os.makedirs(target, exist_ok=True)
    except Exception as e:
        if log_fn:
            log_fn(f"⚠️ Could not create directory: {e}", "warn")

    now = time.time()
    last_time = _last_opened_folders.get(target, 0.0)
    if now - last_time < 1.0:
        return target
    _last_opened_folders[target] = now

    if len(_last_opened_folders) > 20:
        for k in list(_last_opened_folders.keys()):
            if now - _last_opened_folders[k] > 60:
                _last_opened_folders.pop(k, None)

    opened = False
    try:
        os.startfile(target)
        opened = True
    except Exception:
        pass

    if not opened:
        try:
            subprocess.Popen(["explorer.exe", target])
        except Exception as e:
            if log_fn:
                log_fn(f"⚠️ Failed to open explorer for {target}: {e}", "warn")

    return target

