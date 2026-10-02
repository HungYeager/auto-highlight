# -*- coding: utf-8 -*-
"""
Viral US Police Bodycam Video Clipper & Title Generator
========================================================
Native Tkinter desktop tool v1.2 — no browser, no localhost.
Double-click run.bat to launch.

What's new in v1.2:
  - Dynamic API key rows — one key per row, + Add Key button
  - TRUE parallel bulk analysis — all videos analyzed simultaneously
  - Live status queue (Treeview) per video
  - Click any completed video to review candidates / cut

Dependencies:  pip install -r requirements.txt
FFmpeg must be installed and on PATH.
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from tkinter import (
    END, BOTH, X, Y, LEFT, RIGHT, TOP, BOTTOM, W, E, N, S, NW, NE, SW, SE,
    DISABLED, NORMAL, FLAT, WORD, SUNKEN, HORIZONTAL, VERTICAL,
    filedialog, messagebox, scrolledtext,
)
import tkinter as tk
from tkinter import ttk
from typing import Optional, Any, List, Dict, Tuple

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

APP_TITLE     = "Viral Bodycam Clipper"
APP_VERSION   = "v1.2"
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/username/repo/main/update_check.json"
MODEL_NAME    = "gemini-3.5-flash-lite"
CLIP_DURATION = 16
MIN_STORY_DUR = 30   # Story Mode: minimum scene duration (seconds)
MAX_STORY_DUR = 90   # Story Mode: maximum scene duration (seconds)
CONFIG_FILE   = "config.json"
SUPPORTED_EXT = {".mp4", ".mkv"}

# Local bundled fonts dir (relative to this file / PyInstaller _MEIPASS)
_HERE = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
FONTS_DIR = _HERE / "fonts"
PREVIEW_W, PREVIEW_H = 448, 252
# Editor canvas (Tab 2) — portrait preview at 35% of 1080×1920
EDIT_PREV_W    = 378
EDIT_PREV_H    = 672
EDIT_PREV_SCALE = EDIT_PREV_W / 1080   # ≈0.35

# Per-user font installation flag — set to True after first successful install
_BUNDLED_FONTS_INSTALLED = False


def _ensure_bundled_fonts_installed() -> None:
    """Install bundled TTF fonts into the Windows per-user Fonts directory.

    Per-user font installation (Windows 10 build 1809+) requires no admin
    privileges. After installation libass/DirectWrite discover fonts by their
    family name — no fontsdir or path escaping tricks needed.

    Called once per process on the first subtitle export that uses a bundled
    font. Subsequent calls are no-ops (guarded by _BUNDLED_FONTS_INSTALLED).
    """
    global _BUNDLED_FONTS_INSTALLED
    if _BUNDLED_FONTS_INSTALLED:
        return

    import shutil as _sh
    import winreg as _wr

    # %LOCALAPPDATA%\Microsoft\Windows\Fonts  (no admin needed, Win10+)
    user_fonts_dir = Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts"
    user_fonts_dir.mkdir(parents=True, exist_ok=True)

    # Map: registry display name → source TTF path
    # Registry name format: "{Family} {Style} (TrueType)" — must match actual TTF name table
    _INSTALL_MAP: dict[str, Path] = {
        "Montserrat Bold (TrueType)":          FONTS_DIR / "Montserrat-Bold.ttf",
        "Luckiest Guy Regular (TrueType)":     FONTS_DIR / "LuckiestGuy-Regular.ttf",
        "Nunito Light (TrueType)":             FONTS_DIR / "Nunito-ExtraBold.ttf",  # TTF family = "Nunito Light"
        "Permanent Marker Regular (TrueType)": FONTS_DIR / "PermanentMarker-Regular.ttf",
    }


    _REG_PATH = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
    try:
        _reg = _wr.OpenKey(_wr.HKEY_CURRENT_USER, _REG_PATH, 0,
                           _wr.KEY_READ | _wr.KEY_SET_VALUE)
    except OSError:
        _reg = None

    for reg_name, src in _INSTALL_MAP.items():
        if not src.exists():
            continue
        dst = user_fonts_dir / src.name
        try:
            if not dst.exists():
                _sh.copy2(src, dst)
            if _reg:
                _wr.SetValueEx(_reg, reg_name, 0, _wr.REG_SZ, str(dst))
        except OSError:
            pass  # silently skip if copy/registry fails

    if _reg:
        _reg.Close()

    # Broadcast WM_FONTCHANGE so running apps (including ffmpeg child process)
    # can discover the newly-registered fonts without restarting.
    try:
        import ctypes as _ct
        _ct.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001D, 0, 0, 0x0002, 500, None)  # HWND_BROADCAST, WM_FONTCHANGE
    except Exception:
        pass

    _BUNDLED_FONTS_INSTALLED = True


def _find_tool(name: str) -> str:
    """Resolve the path to ffmpeg / ffplay / ffprobe.

    Search order (highest priority first):
    1. sys._MEIPASS (PyInstaller onefile temp extraction dir)
    2. Same directory as the running EXE (PyInstaller --onedir root)
    3. _internal subfolder in running EXE directory (PyInstaller 6 layout)
    4. Directory containing this script (source / dev mode)
    5. ffmpeg/bin or bin subfolder relative to script / exe
    6. Current working directory and cwd/ffmpeg/bin
    7. Well-known Windows paths (C:\\ffmpeg\\bin, D:\\ffmpeg\\bin, etc.)
    8. PATH environment variable via shutil.which

    When a valid executable is found, its parent folder is automatically injected
    into os.environ["PATH"] so external libraries (whisper, stable-ts, subprocesses)
    can locate ffmpeg without [Errno 2] No such file or directory.
    """
    exe_name = f"{name}.exe" if sys.platform == "win32" else name

    search_dirs = []

    # 1. PyInstaller _MEIPASS (onefile extraction directory)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        search_dirs.append(Path(meipass))
        search_dirs.append(Path(meipass) / "bin")
        search_dirs.append(Path(meipass) / "_internal")

    # 2. Executable parent & _internal
    exe_dir = Path(sys.executable).parent
    search_dirs.append(exe_dir)
    search_dirs.append(exe_dir / "_internal")
    search_dirs.append(exe_dir / "bin")
    search_dirs.append(exe_dir / "ffmpeg" / "bin")

    # 3. Script directory
    try:
        script_dir = Path(__file__).resolve().parent
        search_dirs.append(script_dir)
        search_dirs.append(script_dir / "bin")
        search_dirs.append(script_dir / "ffmpeg" / "bin")
    except Exception:
        pass

    # 4. Current working directory
    try:
        cwd = Path.cwd()
        search_dirs.append(cwd)
        search_dirs.append(cwd / "bin")
        search_dirs.append(cwd / "ffmpeg" / "bin")
    except Exception:
        pass

    # 5. Common Windows install locations
    if sys.platform == "win32":
        search_dirs.extend([
            Path(r"C:\ffmpeg\bin"),
            Path(r"C:\ffmpeg"),
            Path(r"D:\ffmpeg\bin"),
            Path(r"D:\ffmpeg"),
            Path(r"C:\Program Files\ffmpeg\bin"),
            Path(r"C:\Program Files (x86)\ffmpeg\bin"),
        ])

    for d in search_dirs:
        try:
            candidate = d / exe_name
            if candidate.is_file():
                tool_path = str(candidate.resolve())
                tool_dir = str(candidate.parent.resolve())
                current_path = os.environ.get("PATH", "")
                if tool_dir.lower() not in current_path.lower():
                    os.environ["PATH"] = f"{tool_dir}{os.pathsep}{current_path}"
                return tool_path
        except Exception:
            continue

    # Fall back to whatever is on PATH
    which_found = shutil.which(name) or shutil.which(exe_name)
    if which_found:
        tool_dir = str(Path(which_found).parent.resolve())
        current_path = os.environ.get("PATH", "")
        if tool_dir.lower() not in current_path.lower():
            os.environ["PATH"] = f"{tool_dir}{os.pathsep}{current_path}"
        return which_found

    return name


FFMPEG = _find_tool("ffmpeg")
FFPLAY = _find_tool("ffplay")
FFPROBE = _find_tool("ffprobe")

# Encoders that are actually installed on this machine.
# Populated at startup by _probe_encoders(). libx264 always assumed available.
AVAILABLE_ENCODERS: set[str] = {"libx264"}
# Best encoder auto-detected at startup: h264_nvenc > h264_qsv > h264_amf > libx264
BEST_ENCODER: str = "libx264"

def _probe_encoders() -> None:
    """Detect available GPU encoders by actually encoding a 1-frame test.

    Simply grepping `ffmpeg -encoders` output is unreliable — the encoder
    can be listed but fail at runtime if the GPU driver is missing or wrong.
    We do a real encode so the result is guaranteed accurate.
    """
    global AVAILABLE_ENCODERS, BEST_ENCODER

    # CPU encoders: trust the ffmpeg list (no hardware dependency)
    try:
        out = subprocess.run(
            [FFMPEG, "-encoders", "-v", "quiet"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        found: set[str] = {"libx264"}  # always available
        for enc in ("libx265", "h264_mf"):
            if enc in out:
                found.add(enc)
    except Exception:
        found = {"libx264"}

    # Hardware encoders: test by actually encoding 1 dummy frame (< 1 s)
    # 320x240 satisfies NVENC minimum resolution (~145px); 0.5s is enough to init.
    hw_priority = [
        "h264_nvenc",   # NVIDIA
        "h264_qsv",     # Intel
        "h264_amf",     # AMD
        "hevc_nvenc",
        "hevc_qsv",
        "hevc_amf",
    ]
    for enc in hw_priority:
        try:
            r = subprocess.run(
                [FFMPEG, "-f", "lavfi", "-i", "nullsrc=s=320x240:d=0.5",
                 "-c:v", enc, "-f", "null", "-"],
                capture_output=True, timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if r.returncode == 0:
                found.add(enc)
        except Exception:
            pass

    AVAILABLE_ENCODERS = found

    # Pick best encoder: prefer NVENC > QSV > AMF > CPU
    for preferred in ("h264_nvenc", "h264_qsv", "h264_amf", "libx264"):
        if preferred in found:
            BEST_ENCODER = preferred
            break


def _gpu_decode_flags() -> list[str]:
    """Return FFmpeg input flags for GPU-accelerated decode.

    NOTE: '-hwaccel cuda -hwaccel_output_format yuv420p' causes color matrix
    corruption (green tint) in the filter graph because CUDA NV12 output
    strips BT.709 metadata during forced yuv420p conversion.
    The NVENC *encode* path (already used in cut_clip_exact / render_reup)
    is the dominant speedup (5-10x). GPU decode adds only ~10-15% extra
    and is not worth the color corruption risk.
    Kept as a hook for future hwaccel improvements.
    """
    return []  # disabled — NVENC encode-only is safe and fast enough


class KeyRotator:
    """Thread-safe API key selector — Least Connections + Cooldown.

    Selection algorithm (per acquire() call):
      1. Exclude keys currently in cooldown (penalized for rate-limit / TCP errors).
      2. Among available keys, pick the one with the fewest in-flight requests.
      3. If ALL keys are in cooldown, pick the earliest-expiring one as a last
         resort (graceful degradation — let the API call fail, not us).

    Usage contract:
        key = rotator.acquire()
        try:
            ... use key ...
        except RateLimitError:
            rotator.penalize(key, KeyRotator.COOLDOWN_RATE_LIMIT)
        except TcpError:
            rotator.penalize(key, KeyRotator.COOLDOWN_TCP)
        except Exception:
            rotator.penalize(key, KeyRotator.COOLDOWN_GENERIC)
        finally:
            rotator.release(key)   # ALWAYS release, even on success
    """

    COOLDOWN_RATE_LIMIT = 60.0   # 429 / quota exhausted → back off a full minute
    COOLDOWN_TCP        = 10.0   # WinError 10053/10054 → OS needs to clear socket
    COOLDOWN_GENERIC    =  2.0   # any other failure → steer next retry to diff key

    def __init__(self, keys: list[str]):
        if not keys:
            raise ValueError("KeyRotator requires at least one key")
        self._keys     = list(keys)
        self._lock     = threading.Lock()
        n              = len(self._keys)
        self._active   = [0]   * n   # in-flight request count per key
        self._cooldown = [0.0] * n   # monotonic timestamp until key is usable

    def __len__(self) -> int:
        return len(self._keys)

    def acquire(self) -> str:
        """Atomically select the least-loaded available key and increment its counter."""
        with self._lock:
            now   = time.monotonic()
            n     = len(self._keys)
            avail = [i for i in range(n) if now >= self._cooldown[i]]
            if avail:
                # Least connections: fewest active requests wins
                idx = min(avail, key=lambda i: self._active[i])
            else:
                # All keys cooling — pick the one expiring soonest (best bad option)
                idx = min(range(n), key=lambda i: self._cooldown[i])
            self._active[idx] += 1
            return self._keys[idx]

    def release(self, key: str) -> None:
        """Decrement the active counter. MUST be called in a finally block."""
        with self._lock:
            try:
                idx = self._keys.index(key)
                self._active[idx] = max(0, self._active[idx] - 1)
            except ValueError:
                pass  # unknown key — safe to ignore

    def penalize(self, key: str, seconds: float) -> None:
        """Put key in cooldown, preventing it from being acquired for `seconds`.

        Extends from max(now, existing_cooldown) so concurrent penalize() calls
        from multiple threads don't accidentally under-count the cooldown.
        """
        with self._lock:
            try:
                idx = self._keys.index(key)
                now = time.monotonic()
                self._cooldown[idx] = max(now, self._cooldown[idx]) + seconds
            except ValueError:
                pass

    def status(self) -> list[dict]:
        """Snapshot of per-key load — useful for debugging log lines."""
        with self._lock:
            now = time.monotonic()
            return [
                {
                    "key":       f"…{k[-6:]}",
                    "active":    self._active[i],
                    "cooldown":  round(max(0.0, self._cooldown[i] - now), 1),
                }
                for i, k in enumerate(self._keys)
            ]

    # ── Backward compatibility ─────────────────────────────────────────────────
    def next(self) -> str:
        """Legacy alias for acquire(). Prefer acquire()/release() pair."""
        return self.acquire()

    def peek_all(self) -> list[str]:
        return list(self._keys)




# Status constants
ST_QUEUED    = "queued"
ST_UPLOADING = "uploading"
ST_ANALYZING = "analyzing"
ST_DONE      = "done"
ST_ERROR     = "error"

ST_LABEL = {
    ST_QUEUED:    "🕐  Queued",
    ST_UPLOADING: "⬆️  Uploading…",
    ST_ANALYZING: "🔍  Analyzing…",
    ST_DONE:      "✅  Done",
    ST_ERROR:     "❌  Error",
}

# Palette — layered depth system for premium dark theme
CLR_BG        = "#0f0f14"      # deepest background
CLR_SURFACE   = "#1a1a24"      # elevated cards / sections
CLR_PANEL     = "#22222e"      # side panels
CLR_BORDER    = "#2a2a3a"      # subtle borders
CLR_ACCENT    = "#7c5cfc"      # primary brand purple
CLR_ACCENT_H  = "#9b7dff"      # hover state
CLR_ACCENT_D  = "#5a3ec8"      # pressed state
CLR_FG        = "#e4e4ef"      # primary text (slightly warm white)
CLR_FG2       = "#9898b0"      # secondary / dimmed text
CLR_SUCCESS   = "#34d399"      # modern emerald
CLR_WARN      = "#fbbf24"      # amber
CLR_ERROR     = "#f87171"      # soft red
CLR_HEADER    = "#a78bfa"      # section headers (lighter purple)
CLR_DIM       = "#6b6b88"      # disabled / hint text
CLR_INPUT_BG  = "#14141e"      # input field wells


# ──────────────────────────────────────────────────────────────────────────────
# Premium UI Widget Classes
# ──────────────────────────────────────────────────────────────────────────────

class ToolTip:
    """Hover tooltip — shows after 400ms delay, hides immediately on leave."""

    def __init__(self, widget, text: str, delay: int = 500):
        self._widget   = widget
        self._text     = text
        self._delay    = delay
        self._tw: Optional[tk.Toplevel] = None
        self._after_id = None
        widget.bind("<Enter>",       self._schedule,   add="+")
        widget.bind("<Leave>",       self._hide,       add="+")
        widget.bind("<ButtonPress>", self._hide,       add="+")
        widget.bind("<Destroy>",     self._on_destroy, add="+")

    def _cancel_pending(self):
        if self._after_id:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _schedule(self, _event=None):
        self._cancel_pending()  # reset timer if cursor re-enters quickly
        try:
            self._after_id = self._widget.after(self._delay, self._show)
        except Exception:
            pass

    def _show(self):
        self._after_id = None
        if self._tw:
            return
        try:
            x = self._widget.winfo_rootx() + 20
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        except Exception:
            return
        self._tw = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        # Hide if cursor enters the tooltip window itself
        tw.bind("<Enter>", self._hide)
        frame = tk.Frame(tw, bg="#2d2d40", bd=1, relief="solid",
                         highlightbackground=CLR_BORDER, highlightthickness=1)
        frame.pack()
        tk.Label(frame, text=self._text, bg="#2d2d40", fg="#d4d4e8",
                 font=("Segoe UI", 8), padx=8, pady=4,
                 wraplength=280, justify="left").pack()

    def _hide(self, _event=None):
        self._cancel_pending()
        if self._tw:
            try:
                self._tw.destroy()
            except Exception:
                pass
            self._tw = None

    def _on_destroy(self, _event=None):
        """Widget is being destroyed — clean up without referencing it."""
        self._after_id = None   # can't cancel, widget gone
        if self._tw:
            try:
                self._tw.destroy()
            except Exception:
                pass
            self._tw = None

    def update_text(self, text: str):
        self._text = text



class Toast:
    """Slide-in notification overlay — auto-dismisses after a timeout."""

    _active: list = []   # class-level stack of visible toasts

    def __init__(self, parent: tk.Tk, message: str,
                 kind: str = "info", duration: int = 3500):
        colors = {
            "info":    (CLR_ACCENT,  "#1e1b3a"),
            "success": (CLR_SUCCESS, "#0f2a1f"),
            "warning": (CLR_WARN,    "#2a2000"),
            "error":   (CLR_ERROR,   "#2a0f0f"),
        }
        fg, bg = colors.get(kind, colors["info"])
        icons  = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✕"}

        # Stack offset so multiple toasts don't overlap
        stack_offset = len(Toast._active) * 52

        self._frame = tk.Frame(parent, bg=bg, highlightbackground=fg,
                               highlightthickness=1, padx=12, pady=8)
        self._frame.place(relx=1.0, rely=1.0, anchor="se",
                          x=-16, y=-(16 + stack_offset))

        tk.Label(self._frame, text=f"{icons.get(kind, 'ℹ')}  {message}",
                 bg=bg, fg=fg, font=("Segoe UI", 9, "bold")).pack(side=LEFT)

        Toast._active.append(self)
        parent.after(duration, self._dismiss)

    def _dismiss(self):
        try:
            Toast._active.remove(self)
        except ValueError:
            pass
        try:
            self._frame.destroy()
        except Exception:
            pass


class PremiumScale(tk.Canvas):
    """Custom-drawn slider replacing the ugly default tk.Scale.

    Features:
    - Rounded track with accent fill
    - Circular thumb with hover glow
    - Value label that follows the thumb
    """

    def __init__(self, parent, variable, from_=0, to=100, resolution=1,
                 orient=HORIZONTAL, command=None, value_format=None,
                 width=None, **kw):
        h = 36
        super().__init__(parent, height=h, bg=CLR_BG, highlightthickness=0,
                         cursor="hand2")
        if width:
            self.configure(width=width)

        self._var       = variable
        self._from      = float(from_)
        self._to        = float(to)
        self._res       = float(resolution)
        self._cmd       = command
        self._fmt       = value_format  # e.g. "{:.1f}" or "{:.0f}°"
        self._dragging  = False
        self._hover     = False

        # Layout constants
        self._pad    = 14          # horizontal padding
        self._track_y = h // 2     # vertical center
        self._track_h = 4          # track thickness
        self._thumb_r = 7          # thumb radius

        self.bind("<Configure>", self._on_resize)
        self.bind("<Button-1>",  self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))

        # Redraw when variable changes externally
        self._var.trace_add("write", lambda *_: self._draw())

    def _set_hover(self, h):
        self._hover = h
        self._draw()

    def _val_to_x(self, val):
        w = self.winfo_width() or 200
        track_w = w - 2 * self._pad
        frac = (val - self._from) / max(self._to - self._from, 1e-9)
        return self._pad + frac * track_w

    def _x_to_val(self, x):
        w = self.winfo_width() or 200
        track_w = w - 2 * self._pad
        frac = max(0.0, min(1.0, (x - self._pad) / max(track_w, 1)))
        raw = self._from + frac * (self._to - self._from)
        # Snap to resolution
        if self._res > 0:
            raw = round(raw / self._res) * self._res
        return max(self._from, min(self._to, raw))

    def _on_resize(self, _e=None):
        self._draw()

    def _on_click(self, e):
        self._dragging = True
        val = self._x_to_val(e.x)
        self._var.set(val)
        self._fire_command(val)

    def _on_drag(self, e):
        if self._dragging:
            val = self._x_to_val(e.x)
            self._var.set(val)
            self._fire_command(val)

    def _on_release(self, _e):
        self._dragging = False
        self._draw()

    def _fire_command(self, val):
        if self._cmd:
            try:
                self._cmd(str(val))
            except Exception:
                pass

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or 200
        y = self._track_y
        pad = self._pad
        track_w = w - 2 * pad

        try:
            val = float(self._var.get())
        except (ValueError, tk.TclError):
            val = self._from

        frac = (val - self._from) / max(self._to - self._from, 1e-9)
        frac = max(0.0, min(1.0, frac))
        thumb_x = pad + frac * track_w

        # Track background (dark rounded rect)
        self._round_rect(pad, y - 2, w - pad, y + 2, 2, CLR_BORDER, CLR_BORDER)
        # Track fill (accent)
        if thumb_x > pad + 2:
            self._round_rect(pad, y - 2, thumb_x, y + 2, 2, CLR_ACCENT, CLR_ACCENT)

        # Thumb
        r = self._thumb_r + (2 if self._hover or self._dragging else 0)
        # Outer glow on hover
        if self._hover or self._dragging:
            self.create_oval(thumb_x - r - 3, y - r - 3,
                             thumb_x + r + 3, y + r + 3,
                             fill="", outline=CLR_ACCENT_H, width=1)
        # Thumb circle
        self.create_oval(thumb_x - r, y - r, thumb_x + r, y + r,
                         fill=CLR_ACCENT if not self._dragging else CLR_ACCENT_H,
                         outline="", width=0)
        # Inner dot
        self.create_oval(thumb_x - 2, y - 2, thumb_x + 2, y + 2,
                         fill="#ffffff", outline="")

        # Value label above thumb
        if self._fmt:
            txt = self._fmt.format(val)
        else:
            txt = f"{val:g}"
        self.create_text(thumb_x, y - r - 8, text=txt,
                         fill=CLR_FG2, font=("Segoe UI", 7), anchor="s")

    def _round_rect(self, x1, y1, x2, y2, r, fill, outline):
        """Draw a small rounded rectangle (for the track)."""
        self.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=0)


class AccentButton(tk.Button):
    """Primary action button — gradient-like accent fill, glow on hover."""

    def __init__(self, parent, text="", command=None, icon="", **kw):
        display = f"{icon}  {text}" if icon else text
        font  = kw.pop("font",  ("Segoe UI", 11, "bold"))
        pady  = kw.pop("pady",  9)
        padx  = kw.pop("padx",  16)
        super().__init__(
            parent, text=display, command=command,
            bg=CLR_ACCENT, fg="white", activebackground=CLR_ACCENT_D,
            activeforeground="white", font=font,
            relief=FLAT, cursor="hand2", pady=pady, padx=padx, bd=0,
            **kw,
        )
        self.bind("<Enter>", lambda e: self.config(bg=CLR_ACCENT_H) if self["state"] != "disabled" else None)
        self.bind("<Leave>", lambda e: self.config(bg=CLR_ACCENT) if self["state"] != "disabled" else None)


class SecondaryButton(tk.Button):
    """Secondary action button — subtle outlined style."""

    _BG = "#1e1e2e"
    _BG_H = "#2a2a3e"

    def __init__(self, parent, text="", command=None, icon="", **kw):
        display = f"{icon}  {text}" if icon else text
        font  = kw.pop("font",  ("Segoe UI", 10, "bold"))
        pady  = kw.pop("pady",  7)
        padx  = kw.pop("padx",  12)
        super().__init__(
            parent, text=display, command=command,
            bg=self._BG, fg=CLR_FG, activebackground=self._BG_H,
            activeforeground=CLR_FG, font=font,
            relief=FLAT, cursor="hand2", pady=pady, padx=padx, bd=0,
            highlightbackground=CLR_BORDER, highlightthickness=1,
            **kw,
        )
        self.bind("<Enter>", lambda e: self.config(bg=self._BG_H) if self["state"] != "disabled" else None)
        self.bind("<Leave>", lambda e: self.config(bg=self._BG) if self["state"] != "disabled" else None)


class DangerButton(tk.Button):
    """Destructive action button — red-tinted."""

    _BG   = "#2a1215"
    _BG_H = "#3d1a1e"

    def __init__(self, parent, text="", command=None, icon="", **kw):
        display = f"{icon}  {text}" if icon else text
        font  = kw.pop("font",  ("Segoe UI", 10, "bold"))
        pady  = kw.pop("pady",  7)
        padx  = kw.pop("padx",  12)
        super().__init__(
            parent, text=display, command=command,
            bg=self._BG, fg=CLR_ERROR, activebackground=self._BG_H,
            activeforeground="#fca5a5", font=font,
            relief=FLAT, cursor="hand2", pady=pady, padx=padx, bd=0,
            **kw,
        )
        self.bind("<Enter>", lambda e: self.config(bg=self._BG_H) if self["state"] != "disabled" else None)
        self.bind("<Leave>", lambda e: self.config(bg=self._BG) if self["state"] != "disabled" else None)


class SuccessButton(tk.Button):
    """Success / positive action button — green-tinted."""

    _BG   = "#0a2a1e"
    _BG_H = "#0f3d2a"

    def __init__(self, parent, text="", command=None, icon="", **kw):
        display = f"{icon}  {text}" if icon else text
        font  = kw.pop("font",  ("Segoe UI", 10, "bold"))
        pady  = kw.pop("pady",  7)
        padx  = kw.pop("padx",  12)
        super().__init__(
            parent, text=display, command=command,
            bg=self._BG, fg=CLR_SUCCESS, activebackground=self._BG_H,
            activeforeground="#6ee7b7", font=font,
            relief=FLAT, cursor="hand2", pady=pady, padx=padx, bd=0,
            **kw,
        )
        self.bind("<Enter>", lambda e: self.config(bg=self._BG_H) if self["state"] != "disabled" else None)
        self.bind("<Leave>", lambda e: self.config(bg=self._BG) if self["state"] != "disabled" else None)


class SectionCard(tk.Frame):
    """Visual grouping card with accent-bar header and optional collapse."""

    def __init__(self, parent, title: str, collapsible: bool = True, **kw):
        super().__init__(parent, bg=CLR_SURFACE, highlightbackground=CLR_BORDER,
                         highlightthickness=1, padx=0, pady=0, **kw)

        self._collapsed = False
        self._collapsible = collapsible

        # Header row
        hdr = tk.Frame(self, bg=CLR_SURFACE, padx=10, pady=6)
        hdr.pack(fill=X)

        # Accent bar (left edge)
        tk.Frame(hdr, bg=CLR_ACCENT, width=3).pack(side=LEFT, fill=Y, padx=(0, 8))

        self._chevron_lbl = tk.Label(
            hdr, text="▾" if not self._collapsed else "▸",
            bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 9),
            cursor="hand2" if collapsible else "",
        )
        if collapsible:
            self._chevron_lbl.pack(side=LEFT, padx=(0, 4))

        tk.Label(hdr, text=title.upper(), bg=CLR_SURFACE, fg=CLR_HEADER,
                 font=("Segoe UI", 9, "bold")).pack(side=LEFT)

        if collapsible:
            hdr.bind("<Button-1>", self._toggle)
            for child in hdr.winfo_children():
                child.bind("<Button-1>", self._toggle)

        # Content area
        self._content = tk.Frame(self, bg=CLR_SURFACE, padx=12)
        self._content.pack(fill=X, pady=(0, 10))

    @property
    def content(self) -> tk.Frame:
        """Return the inner frame where controls should be packed."""
        return self._content

    def _toggle(self, _e=None):
        if not self._collapsible:
            return
        self._collapsed = not self._collapsed
        self._chevron_lbl.config(text="▸" if self._collapsed else "▾")
        if self._collapsed:
            self._content.pack_forget()
        else:
            self._content.pack(fill=X)


# ──────────────────────────────────────────────────────────────────────────────
# Logo / Subtitle Detection Utilities  (adapted from logo_v2.py)
# ──────────────────────────────────────────────────────────────────────────────

def clamp_bbox(x: int, y: int, w: int, h: int, width: int, height: int):
    """Clamp bbox to frame bounds with 2px margin and enforce even dimensions
    (required by FFmpeg yuv420p for delogo filter)."""
    margin = 2
    x = max(margin, int(x))
    y = max(margin, int(y))
    w = min(width  - margin - x, int(w))
    h = min(height - margin - y, int(h))
    x -= x % 2;  y -= y % 2
    w -= w % 2;  h -= h % 2
    return (x, y, w, h) if w > 0 and h > 0 else None


def detect_logo_bbox(video_path: str, sample_frames: int = 40,
                     corner_bias: bool = True):
    """
    Detect a static logo / watermark region using temporal variance.
    Low-variance pixels (barely changing across many frames) = logo.
    Corner bias prioritises regions near the four frame corners.
    Returns (x, y, w, h) or None.
    """
    import cv2; import numpy as np  # noqa: lazy import — cv2 not at module scope
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if total <= 0 or width <= 0 or height <= 0:
        cap.release(); return None

    idxs = np.linspace(0, max(total - 1, 0),
                       num=min(sample_frames, total), dtype=int)
    frames = []
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok: continue
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32))
    cap.release()

    if len(frames) < 5:
        return None

    std_map = np.std(np.stack(frames, axis=0), axis=0)
    norm    = cv2.normalize(std_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    inv     = 255 - norm                              # low std → high value

    thresh_val = np.percentile(inv, 92)
    mask = (inv >= thresh_val).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.dilate(mask, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    candidates = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < 400 or area > 0.25 * width * height:
            continue
        score = area
        if corner_bias:
            cx, cy = x + w / 2, y + h / 2
            corners = [(0, 0), (width, 0), (0, height), (width, height)]
            dist = min(((cx - cx2) ** 2 + (cy - cy2) ** 2) ** 0.5
                       for cx2, cy2 in corners)
            dist_norm = dist / ((width ** 2 + height ** 2) ** 0.5)
            score = area * (1.0 - dist_norm) ** 2
        candidates.append((score, x, y, w, h))

    if not candidates:
        return None

    _, x, y, w, h = max(candidates, key=lambda t: t[0])
    pad = max(14, int(0.12 * max(w, h)))
    return clamp_bbox(x - pad, y - pad, w + 2 * pad, h + 2 * pad, width, height)


def detect_subtitle_region(video_path: str, band_pct: float = 0.22,
                            sample_frames: int = 60):
    """Detect where burned-in subtitles appear and WHEN they first appear in the video.

    Uses RapidOCR AI detection if tracks exist, mapping normalized bbox to pixel coordinates.

    Returns (x, y, w, h, start_time_seconds) or None.
    """
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    if width <= 0 or height <= 0:
        return None

    tracks = auto_detect_subtitle_tracks(video_path, band_pct=band_pct)
    if tracks:
        first = tracks[0]
        nb = first.get("bbox", [0, 1.0 - band_pct, 1.0, band_pct])
        ox = int(nb[0] * width)
        oy = int(nb[1] * height)
        ow = int(nb[2] * width)
        oh = int(nb[3] * height)
        st_t = first.get("start", 0.0)
        clamped = clamp_bbox(ox, oy, ow, oh, width, height)
        return (*clamped, st_t) if clamped else None

    band_y = int(height * (1.0 - band_pct))
    clamped = clamp_bbox(0, band_y, width, height - band_y, width, height)
    return (*clamped, 0.0) if clamped else None


def _auto_detect_subtitle_tracks_legacy(video_path: str,
                                         band_pct: float = 0.22,
                                         sample_interval_s: float = 0.10) -> list:
    import cv2; import numpy as np
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if total <= 0 or width <= 0 or height <= 0:
        cap.release()
        return []
    band_y  = int(height * (1.0 - band_pct))
    step    = max(1, int(fps * sample_interval_s))
    scores: list[tuple[float, float]] = []
    frame_num = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_num % step == 0:
            t = frame_num / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            band = gray[band_y:, :]
            lap  = cv2.Laplacian(band, cv2.CV_64F)
            scores.append((t, float(np.mean(np.abs(lap)))))
        frame_num += 1
    cap.release()
    if not scores: return []
    n_base   = max(3, len(scores) // 10)
    baseline = float(np.median([s for _, s in scores[:n_base]]))
    threshold = max(baseline * 2.0, baseline + 8.0)
    events: list[tuple[float, bool]] = [(t, score > threshold) for t, score in scores]
    raw_segs: list[dict] = []
    in_sub = False
    seg_start = 0.0
    for t, active in events:
        if active and not in_sub:
            in_sub = True; seg_start = t
        elif not active and in_sub:
            in_sub = False; raw_segs.append({"start": seg_start, "end": t})
    if in_sub:
        raw_segs.append({"start": seg_start, "end": scores[-1][0]})
    MERGE_GAP = 0.5
    merged: list[dict] = []
    for seg in raw_segs:
        if merged and seg["start"] - merged[-1]["end"] <= MERGE_GAP:
            merged[-1]["end"] = seg["end"]
        else:
            merged.append(dict(seg))
    merged = [s for s in merged if s["end"] - s["start"] >= 0.2]
    bx = 0.0
    by = round(1.0 - band_pct, 4)
    bw = 1.0
    bh = round(band_pct, 4)
    for seg in merged:
        seg["bbox"] = [bx, by, bw, bh]
    return merged


# ── OCR Engine Singleton (GPU CUDA Accelerated + Automatic CPU Fallback) ──────
# Cached at module level: avoids 0.5-1s re-init on every call.
# Tries GPU (CUDA) first for 3-8× faster inference; falls back to CPU silently.
_RAPIDOCR_INSTANCE = None
_RAPIDOCR_DEVICE = "CPU"
_OCR_INIT_LOCK = threading.Lock()

def _setup_cuda_dlls():
    """Ensure PyTorch CUDA & cuDNN DLLs (e.g. cudnn64_9.dll) are accessible by onnxruntime on Windows."""
    try:
        import torch
        t_lib = os.path.join(os.path.dirname(torch.__file__), 'lib')
        if os.path.isdir(t_lib):
            if t_lib not in os.environ.get('PATH', ''):
                os.environ['PATH'] = t_lib + os.pathsep + os.environ.get('PATH', '')
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(t_lib)
                except Exception:
                    pass
    except Exception:
        pass

def get_ocr_device() -> str:
    """Return 'GPU (CUDA)' or 'CPU' indicating active OCR engine device."""
    global _RAPIDOCR_DEVICE
    if _RAPIDOCR_INSTANCE is None:
        _get_ocr_engine()
    return _RAPIDOCR_DEVICE

def _get_ocr_engine():
    """Return cached RapidOCR engine; tries GPU (CUDA) first for ~4-8x faster inference, then CPU."""
    global _RAPIDOCR_INSTANCE, _RAPIDOCR_DEVICE
    if _RAPIDOCR_INSTANCE is not None:
        return _RAPIDOCR_INSTANCE

    with _OCR_INIT_LOCK:
        if _RAPIDOCR_INSTANCE is not None:
            return _RAPIDOCR_INSTANCE

        # 1. Try initializing with GPU (CUDA)
        try:
            _setup_cuda_dlls()
            import onnxruntime as ort
            try:
                ort.set_default_logger_severity(3)
            except Exception:
                pass

            import rapidocr_onnxruntime.rapid_ocr_api as api
            orig_read_yaml = api.read_yaml
            def patched_yaml(path):
                cfg = orig_read_yaml(path)
                cfg['Det']['use_cuda'] = True
                cfg['Rec']['use_cuda'] = True
                cfg['Cls']['use_cuda'] = True
                return cfg
            api.read_yaml = patched_yaml

            instance = api.RapidOCR()
            det_sess = getattr(getattr(instance.text_detector, 'infer', None), 'session', None)
            providers = det_sess.get_providers() if det_sess else []
            if 'CUDAExecutionProvider' in providers:
                # Warmup dummy inference to verify cuDNN DLLs link cleanly
                import numpy as np
                dummy = np.zeros((64, 128, 3), dtype=np.uint8)
                instance(dummy)
                _RAPIDOCR_INSTANCE = instance
                _RAPIDOCR_DEVICE = "GPU (CUDA)"
                print(f"[OCR] RapidOCR GPU (CUDA) initialized successfully. Providers: {providers}", flush=True)
                return _RAPIDOCR_INSTANCE
            else:
                print(f"[OCR] CUDAExecutionProvider not active ({providers}), falling back to CPU.", flush=True)
        except Exception as e:
            print(f"[OCR] GPU init failed ({e}), falling back to CPU.", flush=True)

        # 2. Fallback to CPU
        try:
            from rapidocr_onnxruntime import RapidOCR
            _RAPIDOCR_INSTANCE = RapidOCR()
            _RAPIDOCR_DEVICE = "CPU"
            print("[OCR] Using CPU RapidOCR engine.", flush=True)
        except Exception as e2:
            print(f"[WARN] RapidOCR init failed completely: {e2}", flush=True)
            _RAPIDOCR_INSTANCE = None
            _RAPIDOCR_DEVICE = "Unavailable"

        return _RAPIDOCR_INSTANCE


def auto_detect_subtitle_tracks(video_path: str,
                                 band_pct: float = 0.35,
                                 sample_interval_s: float = 0.3) -> list[dict]:
    """AI Universal Subtitle Detection (Multi-Channel LAB CLAHE + RapidOCR Line-by-Line Tracking).

    Optimizations applied:
    - Phase 1 / #2: Frame downscaled 50% before OCR → ~2-3× faster inference
    - Phase 1 / #1: Seek-based sampling (cap.set POS_MSEC) → decode only needed frames
    - Phase 2:      GPU CUDA OCR (det/rec_use_cuda=True) with auto CPU fallback
    - Singleton OCR engine (cached at module level) → skip 0.5-1s re-init overhead

    Returns:
        List of dicts: [{"start": float, "end": float, "bbox": [x, y, w, h], "text": str}]
        where bbox values are normalized 0.0-1.0 relative to original video size.
    """
    import cv2, numpy as np

    ocr_engine = _get_ocr_engine()
    print(f"[OCR] Subtitle detection on {Path(video_path).name} using {_RAPIDOCR_DEVICE}...", flush=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if total <= 0 or width <= 0 or height <= 0:
        cap.release()
        return []

    dur = total / fps
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))

    # Phase 1 / #2: Downscale factor — 50% → RapidOCR works on half-res frames
    SCALE = 0.5
    inv_scale = 1.0 / SCALE  # used to map coordinates back to original resolution

    raw_events: list[dict] = []

    # Phase 1 / #1: Seek-based sampling — only decode the frames we actually need
    sample_times = [round(i * sample_interval_s, 3)
                    for i in range(int(dur / sample_interval_s) + 2)
                    if i * sample_interval_s <= dur]

    try:
        for t in sample_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                continue

            # Phase 1 / #2: Downscale before CLAHE + OCR
            small = cv2.resize(frame, (0, 0), fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)

            # Multi-Channel LAB CLAHE Contrast Enhancement (on downscaled frame)
            lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
            l_chan, a_chan, b_chan = cv2.split(lab)
            l_enh = clahe.apply(l_chan)
            a_enh = clahe.apply(a_chan)
            b_enh = clahe.apply(b_chan)
            enh_bgr = cv2.cvtColor(cv2.merge((l_enh, a_enh, b_enh)), cv2.COLOR_LAB2BGR)
            rgb = cv2.cvtColor(enh_bgr, cv2.COLOR_BGR2RGB)

            if ocr_engine is not None:
                try:
                    res, _ = ocr_engine(rgb)
                except Exception as e:
                    print(f"[OCR] Inference warning on frame at {t:.2f}s: {e}", flush=True)
                    res = None

                if res:
                    for box, text, score in res:
                        try:
                            sc = float(score)
                        except Exception:
                            sc = 0.5
                        if sc < 0.25:
                            continue

                        xs = [p[0] for p in box]
                        ys = [p[1] for p in box]
                        x_min, y_min = min(xs), min(ys)
                        w_box, h_box = max(xs) - min(xs), max(ys) - min(ys)

                        # Scale coordinates back to original full resolution
                        x_min_orig = x_min * inv_scale
                        y_min_orig = y_min * inv_scale
                        w_box_orig = w_box * inv_scale
                        h_box_orig = h_box * inv_scale

                        # Filter Axon Bodycam top-right HUD timestamp (y < 15% and x > 50%)
                        if y_min_orig < height * 0.15 and x_min_orig > width * 0.5:
                            continue
                        if w_box_orig < 15 or h_box_orig < 8:
                            continue

                        # TIGHT BOX: minimal 6px horizontal & 4px vertical padding around exact text
                        nx = max(0.0, round((x_min_orig - 6.0) / width, 4))
                        ny = max(0.0, round((y_min_orig - 4.0) / height, 4))
                        nw = min(1.0 - nx, round((w_box_orig + 12.0) / width, 4))
                        nh = min(1.0 - ny, round((h_box_orig + 8.0) / height, 4))

                        raw_events.append({
                            'nx': nx, 'ny': ny, 'nw': nw, 'nh': nh,
                            'cy': ny + nh / 2.0, 'cx': nx + nw / 2.0,
                            't': t, 'text': text
                        })
    finally:
        cap.release()

    if not raw_events:
        return _auto_detect_subtitle_tracks_legacy(video_path, band_pct, sample_interval_s)

    # STRICT PER-LINE CLUSTERING: Never merge vertically separated text lines!
    clusters: list[list[dict]] = []
    for ev in raw_events:
        added = False
        for c in clusters:
            avg_cy = sum(e['cy'] for e in c) / len(c)
            avg_cx = sum(e['cx'] for e in c) / len(c)
            t_max = max(e['t'] for e in c)

            # Check vertical distance between line centers (must be < 4% of screen height)
            dy_center = abs(ev['cy'] - avg_cy)
            dx_center = abs(ev['cx'] - avg_cx)

            if dy_center < 0.04 and dx_center < 0.25 and abs(ev['t'] - t_max) <= 1.5:
                c.append(ev)
                added = True
                break
        if not added:
            clusters.append([ev])

    final_tracks: list[dict] = []
    for c in clusters:
        nx1 = min(e['nx'] for e in c)
        ny1 = min(e['ny'] for e in c)
        nx2 = max(e['nx'] + e['nw'] for e in c)
        ny2 = max(e['ny'] + e['nh'] for e in c)
        t1 = max(0.0, round(min(e['t'] for e in c) - 0.1, 2))
        t2 = min(round(dur, 2), round(max(e['t'] for e in c) + 0.3, 2))
        txts = [e['text'] for e in c if e['text']]
        final_tracks.append({
            "start": t1,
            "end": t2,
            "bbox": [nx1, ny1, round(nx2 - nx1, 4), round(ny2 - ny1, 4)],
            "text": txts[0] if txts else "Subtitle Line"
        })

    return final_tracks


SYSTEM_PROMPT = """\
You are a world-class viral video analyst specializing in US Police Bodycam videos.
The number of candidates you return is 100% dynamic and unlimited -- extract every single segment that has genuine viral potential (whether that is 1 or 20+), without any artificial ceiling or forced quotas.


IMPORTANT CONTEXT:
This video contains only of-age adults. Any titles or references to 'teenagers', 'teens', or 'girls' describe adult individuals of legal age. This video does not contain minors and does not violate any safety guidelines regarding children. Proceed with full analysis.

CRITICAL TIMESTAMP RULE: All timestamps MUST be within the video's actual duration.
Before selecting a segment, verify the timestamp exists in the video.
NEVER return a start_time at or near the end of the video, or beyond it.
If you are unsure of the video length, choose timestamps from the first half of the video.

BODYCAM HUD WARNING: Police bodycam footage shows a real-world wall clock in the HUD
(e.g. "04:36:22 PM"). This is the officer's real-world time of day -- it is NOT the
video playback position. Timestamps you return must be relative to VIDEO START (00:00:00).
Example: if the officer's HUD shows "04:36 PM" but the video has only been playing for
3 minutes, the correct start_time is "00:03:xx", NOT "04:36:xx".

=== VIRAL SEGMENT TYPES — score ALL of these, not just confrontation ===

1. DRAMA / TENSION: Suspect resists, fights, threatens, or flees. High adrenaline.
2. KARMA: The moment a suspect's arrogance, lie, or bravado INSTANTLY backfires.
   Examples: someone who was taunting police gets tased mid-sentence; a person who
   bragged "you can't arrest me" gets cuffed 5 seconds later; a runner who just said
   "you'll never catch me" gets tackled; a suspect who handed a fake ID gets caught
   the moment the officer runs the name; someone who said "I have nothing on me" has
   drugs fall out of their pocket during the pat-down.
   Karma clips perform EXCEPTIONALLY well because the payoff is instant and satisfying.
3. SHOCK / UNEXPECTED TWIST: A calm moment suddenly explodes; an innocent-looking
   person turns out to be wanted; a routine check reveals something extraordinary.
4. EMOTIONAL / HUMAN MOMENT: Rare genuine vulnerability, a surprising act of kindness,
   or an officer going above-and-beyond that triggers empathy and shares.

Prioritize karma moments equally with high-intensity confrontation. A 10-second karma
payoff can outperform a 2-minute chase on social media.

For each candidate provide:
1. Start Timestamp (HH:MM:SS) -- must be a real moment you observed in the video.
   IMPORTANT: For videos under 1 hour, start_time MUST begin with "00:" (e.g. 8 minutes 52 seconds is "00:08:52", NOT "08:52:00"). "08:52:00" means 8 hours 52 minutes and will crash the downloader!
   End Timestamp is always exactly 16 seconds after start (e.g. "00:09:08").
2. A brief explanation of why this moment is highly viral (mention the segment type).
3. Exactly 5 viral English titles.

=== TITLE RULES (read carefully) ===

SPECIFICITY IS MANDATORY:
Each title MUST reference concrete, specific details you actually observed in THIS video:
  - What exactly did the suspect do or say?
  - What specific action did the officer take?
  - What was the specific reason for the confrontation or arrest?
  - What specific object, location, or situation was involved?
A title that could apply to ANY bodycam video is WRONG. Each title must be unique
to this specific incident.

FORBIDDEN -- NEVER use these generic phrases or any variation of them:
  X "attitude went from zero to one hundred"
  X "the exact second his/her plan completely falls apart"
  X "the shocking truth he/she tries to hide"
  X "behavior went from calm to pure panic"
  X "a routine [X] turned into chaos"
  X "wait until you see what happens next"
  X any phrase that works for ANY bodycam video

FORMAT:
  - 100% ENGLISH -- sensational, clickbaity, suspenseful, slightly rage-baiting.
  - Structure: "[Specific thing the suspect did/said in THIS video], but wait until you see [the specific shocking outcome, reason, or consequence in THIS video]!"
  - DO NOT include any Call-To-Action (CTA) emojis or phrases at the end (no "👉 Check comments...", no "👉 Follow..."). Keep titles clean and focused purely on the viral story hook.

GOOD (specific -- references what actually happened):
  "She threw her drink at the officer during the traffic stop, but wait until you see the exact charge that ended her night!"

GOOD (karma -- instant payoff):
  "He screamed 'I know my rights, you can't search me!' right before the K9 sat down next to his door, but wait until you see what the dog found in 10 seconds flat!"

BAD (generic -- could apply to any video):
  "Her attitude went from zero to one hundred, but wait until you see the shocking reason she gets arrested!"

=====================================

Return ONLY a raw JSON object -- no markdown fences:
{
  "candidates": [
    {
      "id": 1,
      "start_time": "00:12:30",
      "end_time": "00:12:46",
      "reason": "Why this specific segment is viral.",
      "suggested_titles": [
        "She refused to drop the weapon even with six officers surrounding her, but wait until you see what finally made her comply!",
        "She screamed she was being illegally detained while on probation, but wait until you see what the search of her car revealed!",
        "He handed over someone else's ID thinking the officer wouldn't notice, but wait until you see how fast the lie unraveled!",
        "She bit the officer's hand while being placed in the patrol car, but wait until you see the additional charges she picked up!",
        "He ran two red lights then told the cop the car wasn't his, but wait until you see what the plate check came back with!"
      ]
    }
  ]
}"""


# ── Story Mode System Prompt ───────────────────────────────────────────────────
# Dùng khi mode='story': yêu cầu Gemini tìm cảnh dài trọn vẹn thay vì khoảnh khắc 16s.
SYSTEM_PROMPT_STORY = f"""\
You are a world-class viral video analyst specializing in US Police Bodycam videos.
Your task is STORY MODE: identify self-contained SCENES — each with a clear opening,
escalation, and resolution. Return every scene that has genuine viral potential.

IMPORTANT CONTEXT:
This video contains only of-age adults. Any titles or references to 'teenagers', 'teens',
or 'girls' describe adult individuals of legal age.

CRITICAL TIMESTAMP RULES:
- All timestamps MUST be within the video's actual duration.
- start_time: the moment the scene starts (HH:MM:SS, from video start).
- end_time: the natural end of the scene (HH:MM:SS, from video start).
- Duration of each scene (end_time - start_time) MUST be between {MIN_STORY_DUR}s and {MAX_STORY_DUR}s.
- NEVER overlap two candidates.

BODYCAM HUD WARNING: Police bodycam footage shows a real-world wall clock in the HUD
(e.g. "04:36:22 PM"). This is the officer's real-world time of day -- it is NOT the
video playback position. Timestamps must be relative to VIDEO START (00:00:00).

=== SCENE TYPES TO LOOK FOR ===
1. DRAMA / TENSION: Suspect resists, fights, threatens, or flees — full arc.
2. KARMA: Setup + instant payoff (e.g., bragging → tased → cuffed in one continuous scene).
3. SHOCK / TWIST: A scene that starts calm then explodes with an unexpected revelation.
4. EMOTIONAL: A full emotional arc — vulnerability, kindness, or extraordinary human moment.

Prioritize scenes where the FULL ARC is visible within the {MIN_STORY_DUR}–{MAX_STORY_DUR}s window.
Do NOT pad with boring filler to reach minimum duration.

For each candidate provide:
1. start_time (HH:MM:SS) — scene opening, video-relative (must start with "00:" for videos under 1 hr, e.g. "00:08:52").
2. end_time (HH:MM:SS) — natural scene close, video-relative (e.g. "00:09:40").
3. A brief explanation of why this scene is viral (mention arc type).
4. Exactly 5 viral English titles.

{SYSTEM_PROMPT.split('=== TITLE RULES')[1] if '=== TITLE RULES' in SYSTEM_PROMPT else ''}

Return ONLY a raw JSON object -- no markdown fences:
{{
  "candidates": [
    {{
      "id": 1,
      "start_time": "00:05:10",
      "end_time": "00:06:05",
      "reason": "Why this specific scene is viral.",
      "suggested_titles": [
        "Title 1",
        "Title 2",
        "Title 3",
        "Title 4",
        "Title 5"
      ]
    }}
  ]
}}"""



# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except Exception as exc:
        print(f"Could not save config: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# Logger
# ──────────────────────────────────────────────────────────────────────────────

class ToolLogger:
    def __init__(self, widget: scrolledtext.ScrolledText):
        self.widget = widget
        self._log_path = f"clipper_log_{datetime.date.today():%Y%m%d}.txt"
        widget.tag_configure("info",    foreground=CLR_FG)
        widget.tag_configure("success", foreground=CLR_SUCCESS)
        widget.tag_configure("warning", foreground=CLR_WARN)
        widget.tag_configure("error",   foreground=CLR_ERROR)
        widget.tag_configure("header",  foreground=CLR_HEADER,
                             font=("Consolas", 9, "bold"))
        widget.tag_configure("dim",     foreground=CLR_DIM)

    def log(self, msg: str, level: str = "info") -> None:
        ts   = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.widget.configure(state=NORMAL)
        self.widget.insert(END, line, level)
        self.widget.see(END)
        self.widget.configure(state=DISABLED)
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def info(self, m):   self.log(m, "info")
    def ok(self, m):     self.log(f"✅ {m}", "success")
    def warn(self, m):   self.log(f"⚠️  {m}", "warning")
    def error(self, m):  self.log(f"❌ {m}", "error")
    def header(self, m): self.log(m, "header")
    def dim(self, m):    self.log(m, "dim")
    def write(self, msg: str):
        if msg.strip(): self.info(msg.strip())
    def flush(self): pass


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────

def sanitize(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)


def ts_to_seconds(ts: str) -> float:
    parts = ts.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except (ValueError, IndexError):
        return 0.0


def extract_json(text: str) -> Optional[dict]:
    if not text or not isinstance(text, str):
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned.strip())
    for attempt in (text, cleaned):
        try:
            return json.loads(attempt.strip())
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


# Regex for conversational preamble Gemini sometimes includes inside title strings,
# e.g. "Here's the sensational headline: BREAKING: ..."
#      "Suggested Title 1: She threw her drink..."
_TITLE_PREAMBLE_RE = re.compile(
    r"^(?:"
    r"sure[!.,]?\s+"                                    # "Sure! " starter
    r"|here['\u2019]?s\s+(?:\w+\s+){0,8}"              # "Here's the ... :"
    r"|here\s+is\s+(?:\w+\s+){0,8}"                    # "Here is the ... :"
    r"|here\s+are\s+(?:\w+\s+){0,5}"                   # "Here are ..."
    r"|(?:suggested\s+)?(?:title|headline|hook|option)\s*\d*\s*"  # "Title 1:"
    r")"
    r"(?:[\w\s,]+?)"                                    # allow extra words ("best fits the video context")
    r":\s*",
    re.IGNORECASE | re.DOTALL,
)

# Common meta/filler words used in Gemini preamble sentences
_META_WORDS = frozenset({
    "here", "is", "are", "the", "a", "an", "title", "headline", "best",
    "fits", "context", "video", "sure", "suggested", "for", "you", "most",
    "suitable", "that", "this", "captures", "following", "my", "your",
    "one", "hook", "option", "perfect", "ideal", "great", "viral",
    "fitting", "would", "be", "could", "with", "of", "in", "to", "it",
})


def _clean_title_str(raw: str) -> str:
    """Strip preamble labels that Gemini adds before the actual title text.

    Handles:
      "Here's the sensational headline: BREAKING: ..."
      "Sure! Here is the title that best fits the video context: BREAKING: ..."
      "Title 1: She refused to drop the weapon..."
      "Suggested headline: He ran two red lights..."

    Does NOT strip legitimate title colons like "BREAKING:" or "He said 'X':".
    """
    if not raw:
        return ""
    # Collapse multi-line titles into a single line
    s = " ".join(line.strip() for line in raw.splitlines() if line.strip())
    # Primary: strip via named preamble regex
    s = _TITLE_PREAMBLE_RE.sub("", s).strip()

    # Secondary fallback: colon-split heuristic
    # If there's a ": " in the string, check if the prefix looks like meta-commentary
    if ": " in s:
        colon_pos = s.index(": ")
        prefix = s[:colon_pos]
        rest   = s[colon_pos + 2:].strip()
        prefix_words = re.findall(r"[a-z''\u2019]+", prefix.lower())
        # All-caps words (e.g., BREAKING, SHOCKING) = real title content
        caps_words = re.findall(r"\b[A-Z]{2,}\b", prefix)
        meta_count = sum(1 for w in prefix_words if w in _META_WORDS)
        # Strip prefix if: ≤15 words, ≥2 meta words, no ALL-CAPS (title) words
        if len(prefix_words) <= 15 and meta_count >= 2 and not caps_words and rest:
            s = rest

    return s.strip()


def check_ffmpeg() -> bool:
    # Use the resolved path; also works when ffmpeg.exe lives next to our exe
    return shutil.which(FFMPEG) is not None or Path(FFMPEG).is_file()


def copy_to_clipboard(root: tk.Tk, text: str) -> None:
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()


# ──────────────────────────────────────────────────────────────────────────────
# Gemini API
# ──────────────────────────────────────────────────────────────────────────────

def build_client(api_key: str):
    try:
        from google import genai
        return genai.Client(api_key=api_key), "new"
    except ImportError:
        pass
    try:
        import google.generativeai as g
        g.configure(api_key=api_key)
        return g, "legacy"
    except ImportError:
        pass
    raise ImportError("google-genai not installed. Run: pip install google-genai")


def _reinterpret_mmss(candidates: list, vid_dur: float) -> list:
    """Rescue timestamps Gemini formatted as MM:SS:00 or MM:SS instead of HH:MM:SS.

    For short videos (< 1 hour), Gemini sometimes writes '08:52:00' meaning
    '8 minutes 52 seconds' (video-relative) but standard HH:MM:SS parsers read it as
    '8 hours 52 minutes'. If treating the HH field as minutes and MM field as
    seconds yields a valid position within vid_dur, patch the candidate in-place.
    Returns the list of successfully rescued candidates.
    """
    rescued = []
    if not vid_dur or vid_dur <= 0:
        return rescued

    for c in candidates:
        raw_start = str(c.get("start_time", "")).strip()
        parts = raw_start.split(":")
        dur = float(c.get("clip_duration") or CLIP_DURATION)
        max_valid = max(0.0, vid_dur - dur)

        t_alt = None
        if len(parts) == 3:
            try:
                # E.g. "08:52:00" -> 8 minutes 52 seconds
                t_alt = int(parts[0]) * 60 + int(parts[1]) + float(parts[2]) / 60.0
            except (ValueError, IndexError):
                continue
        elif len(parts) == 2:
            try:
                # E.g. "08:52" -> 8 minutes 52 seconds
                t_alt = int(parts[0]) * 60 + float(parts[1])
            except (ValueError, IndexError):
                continue

        if t_alt is not None and (0.0 <= t_alt <= max_valid or (t_alt <= vid_dur)):
            t_final = min(t_alt, max_valid)
            h = int(t_final // 3600)
            m = int((t_final % 3600) // 60)
            s = int(t_final % 60)
            end = min(vid_dur, t_final + dur)
            eh = int(end // 3600)
            em = int((end % 3600) // 60)
            es = int(end % 60)
            c["start_time"] = f"{h:02d}:{m:02d}:{s:02d}"
            c["end_time"]   = f"{eh:02d}:{em:02d}:{es:02d}"
            c["clip_duration"] = dur
            rescued.append(c)
    return rescued


def _ascii_safe_path(path: Path) -> tuple:
    """Return an ASCII-safe path for the old Gemini SDK upload.

    The old SDK passes the file path to `requests` multipart upload, which
    encodes the filename as ASCII and raises UnicodeEncodeError on any
    non-ASCII character (accented chars, CJK, Vietnamese, etc.).

    If the filename is already ASCII, returns (original_path, False).
    Otherwise creates a hardlink with an ASCII name (zero extra disk space),
    or falls back to a copy if hardlinks are unsupported.
    Returns (upload_path, cleanup_needed).
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: '{path.name}'")
    if path.name.isascii():
        return path, False
    safe_stem = re.sub(
        r"[^A-Za-z0-9_\-]", "_",
        path.stem.encode("ascii", errors="replace").decode("ascii")
    )[:40] or "video"
    # Thread ID makes the name unique across parallel uploads
    tmp_path = path.parent / f"_upltmp_{threading.current_thread().ident}_{safe_stem}{path.suffix}"
    try:
        os.link(str(path), str(tmp_path))      # hardlink — no data copy
    except OSError:
        shutil.copy2(str(path), str(tmp_path)) # fallback: actual copy
    return tmp_path, True


# Gemini processes video at ~1fps internally. A 90-minute video at 1fps =
# ~5400 frames ≈ 1.4M tokens, exceeding the model's context window and causing
# 400 INVALID_ARGUMENT. For videos over this threshold, we re-encode at 1fps/480p
# (audio preserved) so the model call succeeds while still seeing all key moments.
_LONG_VIDEO_THRESHOLD_S = 3600   # 60 minutes


def _win_short_path(path: Path) -> str:
    """Return the Windows 8.3 short path (always ASCII) via GetShortPathNameW.

    ffmpeg on Windows can't open files whose *full* path contains non-ASCII
    characters (e.g. Vietnamese folder names like F:\\Hùng\\...) even when the
    filename itself is ASCII.  The Win32 short-path API returns a pure-ASCII
    8.3 alias that ffmpeg can read without issue.
    Falls back to str(path) if the API is unavailable or fails.
    """
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf))
        if n > 0:
            return buf.value
    except Exception:
        pass
    return str(path)


def _downsample_for_upload(path: Path, log: ToolLogger) -> tuple[Path, bool, float]:
    """If video is >60 min, return a sped-up timelapse version under 55 minutes.

    Gemini has a hard 1-hour video duration limit.  We solve this by creating a
    TRUE timelapse (setpts speedup) so the output duration is always ≤55 minutes.

    Optimisations for speed:
    - GPU NVENC encode (5-10x faster than CPU libx264 ultrafast).
    - 360p output — sufficient for Gemini visual analysis.
    - No audio track (-an) — Gemini doesn't need audio for visual action detection.

    Returns (upload_path, cleanup_needed, speedup_factor).
    - cleanup_needed: caller must unlink upload_path when True.
    - speedup_factor: multiply Gemini's returned timestamps by this value to
      recover the correct position in the original video.
    """
    dur  = get_video_duration(path)
    size = path.stat().st_size if path.exists() else 0

    needs_timelapse = dur is not None and dur > _LONG_VIDEO_THRESHOLD_S
    # Also compress short but large files (e.g. 17-min 4K raw bodycam ≈ 2 GB)
    # to avoid WinError 10053 TCP aborts on large uploads.
    needs_proxy     = not needs_timelapse and size > 200 * 1_048_576  # >200 MB

    if not needs_timelapse and not needs_proxy:
        return path, False, 1.0


    import tempfile as _tmp
    safe_stem = re.sub(r"[^A-Za-z0-9_\-]", "_", path.stem[:30]) or "video"
    tmp_path = Path(_tmp.gettempdir()) / f"_ds_{threading.current_thread().ident}_{safe_stem}.mp4"

    if needs_timelapse:
        # Long video (>60min): speed up to fit under Gemini's 1-hour limit
        TARGET_S = 3300.0
        speedup  = dur / TARGET_S       # e.g. 98min / 55min ≈ 1.78
        pts_val  = 1.0 / speedup        # setpts factor (< 1 = faster)
        # 240p @ 4fps: Gemini needs scene detection, not smooth playback
        vf = f"setpts={pts_val:.6f}*PTS,scale=-2:240,fps=4"
        dur_min = int(dur // 60)
        out_min = int(TARGET_S // 60)
        log.info(
            f"[{path.name}] Video is {dur_min}m — creating {speedup:.1f}x timelapse "
            f"({out_min}m, 240p/4fps) for Gemini upload…"
        )
    else:
        # Short but large file: just re-encode at 480p to shrink the upload size.
        # No speedup needed — speedup_factor stays 1.0.
        speedup = 1.0
        pts_val = 1.0
        size_mb = size / 1_048_576
        vf = "scale=-2:480"             # 480p, original fps, no PTS change
        log.info(
            f"[{path.name}] Large file ({size_mb:.0f} MB) — creating 480p proxy "
            f"for reliable Gemini upload…"
        )

    # Build atempo chain for audio speedup — each stage capped at 2.0x (FFmpeg limit).
    # e.g. speedup=1.78 → atempo=1.78 | speedup=2.5 → atempo=2.0,atempo=1.25
    # For proxy (speedup=1.0), atempo=1.0 is a no-op passthrough.
    s = speedup
    atempo_parts: list[str] = []
    while s > 2.0:
        atempo_parts.append("atempo=2.0")
        s /= 2.0
    atempo_parts.append(f"atempo={s:.6f}")
    atempo_chain = ",".join(atempo_parts)

    def _run(video_extra: list[str], hw_decode_flags: list[str] | None = None) -> bool:
        """Run ffmpeg with given video codec args; return True on success."""
        decode_flags = hw_decode_flags or []
        cmd = [
            FFMPEG, "-y", *decode_flags, "-i", path.name,
            "-vf", vf,
            "-af", atempo_chain,        # speed up audio to match timelapse (no-op for proxy)
            *video_extra,
            "-c:a", "aac", "-b:a", "48k", "-ac", "1",   # mono 48kbps — small + Gemini can hear speech
            "-movflags", "+faststart",
            str(tmp_path),
        ]
        # BELOW_NORMAL_PRIORITY_CLASS (0x4000): analysis is background work — preview
        # requests (normal priority) should never be starved by proxy encode processes.
        _NO_WIN  = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # 0x08000000
        _LOW_PRI = 0x00004000                                    # BELOW_NORMAL_PRIORITY_CLASS
        try:
            r = subprocess.run(
                cmd, cwd=str(path.parent),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=1200,
                creationflags=_NO_WIN | _LOW_PRI,
            )
            return r.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 1000
        except Exception:
            return False

    # Attempt 1: NVENC encode + CUDA hw-decode → GPU handles decode AND encode, CPU near-idle.
    # Color accuracy irrelevant — this proxy is only used for Gemini timestamp detection.
    ok = _run(
        ["-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll", "-cq", "38"],
        hw_decode_flags=["-hwaccel", "cuda", "-hwaccel_output_format", "nv12"],
    )

    # Attempt 2: NVENC encode without hw-decode (CUDA init may fail on some driver versions)
    if not ok:
        ok = _run(["-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll", "-cq", "38"])

    # Attempt 3: CPU libx264 — THREAD-LIMITED to 4 cores so machine stays responsive.
    # Without -threads N, FFmpeg claims all logical cores → 100% CPU spike on every proxy encode.
    if not ok:
        log.info(f"[{path.name}] NVENC unavailable — CPU encode (max 4 threads)…")
        ok = _run(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "32", "-threads", "4"])


    if ok:
        size_mb = tmp_path.stat().st_size / 1_048_576
        log.ok(
            f"[{path.name}] Timelapse ready: {size_mb:.1f} MB "
            f"(speedup={speedup:.2f}x) — uploading…"
        )
        return tmp_path, True, speedup

    log.warn(f"[{path.name}] Timelapse failed — uploading original.")
    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception:
        pass
    return path, False, 1.0





def upload_video(client, sdk: str, path: Path,
                 log: ToolLogger, stop: threading.Event) -> object:
    log.info(f"⬆️  [{path.name}] Uploading to Gemini…")
    # Use a generic display_name to bypass strict filename/metadata policy filters
    # (e.g. "Teen Girl", "DUI Arrest" in the name can trigger false positive PROHIBITED_CONTENT blocks)
    generic_display = "source_video.mp4"

    # Both the new SDK (httpx) and old SDK (requests) encode the file path in
    # multipart Content-Disposition headers as ASCII and raise UnicodeEncodeError
    # on filenames containing curly apostrophes (\u2019), Vietnamese chars, etc.
    # Apply the ASCII-safe hardlink for ALL SDK versions.
    upload_path, tmp_created = _ascii_safe_path(path)
    try:
        if sdk == "new":
            remote = client.files.upload(file=str(upload_path),
                                         config={"display_name": generic_display})
        else:
            remote = client.upload_file(path=str(upload_path),
                                        display_name=generic_display)
    finally:
        if tmp_created:
            try:
                upload_path.unlink(missing_ok=True)
            except Exception:
                pass

    polls = 0
    while True:
        if stop.is_set():
            raise InterruptedError("Stopped by user.")
        state = getattr(remote.state, "name", str(remote.state))
        if state == "ACTIVE":
            break
        if state == "FAILED":
            raise RuntimeError(f"Gemini upload FAILED for '{path.name}'.")
        polls += 1
        log.dim(f"   [{path.name}] Waiting ACTIVE (poll #{polls})…")
        time.sleep(5)
        remote = (client.files.get(name=remote.name) if sdk == "new"
                  else client.get_file(name=remote.name))
    log.ok(f"[{path.name}] ACTIVE on Gemini.")
    return remote


def analyze_video(client, sdk: str, remote, video_name: str,
                  log: ToolLogger, stop: threading.Event,
                  vid_duration: Optional[float] = None,
                  rejected_timestamps: Optional[list] = None,
                  model_name: Optional[str] = None,
                  include_cta: bool = False,
                  mode: str = "short") -> dict:
    """Analyze a video for viral highlights.

    mode='short' : find 16-second peak moments (legacy default behaviour).
    mode='story' : find self-contained scenes between MIN_STORY_DUR and MAX_STORY_DUR.
    """
    target_model = model_name or MODEL_NAME
    if stop.is_set():
        raise InterruptedError("Stopped by user.")
    log.header(f"🔍 [{video_name}] Sending to {target_model}…")

    # Sanitize video_name for the old SDK which encodes request body as ASCII.
    safe_name = video_name.encode("ascii", errors="replace").decode("ascii")

    # Build a concrete duration constraint for the user prompt.
    # A specific, per-video range is far more reliable than a system-level rule
    # because it gives Gemini an exact number it cannot ignore or hallucinate past.
    # Scale candidate count to video length.
    # min_c: minimum to return (1 per 5 min). max_c: upper bound (1 per 2.5 min), capped at 8.
    # Gemini may return fewer than max_c if fewer moments are genuinely viral.
    # Scale candidate count to video length (1 per ~2 minutes), up to 30 candidates for long videos.
    if vid_duration is not None:
        min_c = max(1, int(vid_duration / 300))
        max_c = max(min_c + 2, min(30, int(vid_duration / 100)))
    else:
        min_c, max_c = 1, 15


    # Chọn min duration theo mode để tính max_start hợp lệ
    _min_dur = MIN_STORY_DUR if mode == "story" else CLIP_DURATION

    duration_hint = ""
    if vid_duration is not None and vid_duration > _min_dur:
        max_start = vid_duration - _min_dur
        dur_h  = int(vid_duration // 3600)
        dur_m  = int((vid_duration % 3600) // 60)
        dur_s  = int(vid_duration % 60)
        max_h  = int(max_start // 3600)
        max_m  = int((max_start % 3600) // 60)
        max_s  = int(max_start % 60)
        if mode == "story":
            duration_hint = (
                f"\n\nVIDEO DURATION CONSTRAINT (strictly enforced):\n"
                f"  - Total length : {dur_h:02d}:{dur_m:02d}:{dur_s:02d}\n"
                f"  - Valid start_time range: 00:00:05 to {max_h:02d}:{max_m:02d}:{max_s:02d}\n"
                f"  - Each scene duration (end_time - start_time) MUST be {MIN_STORY_DUR}s to {MAX_STORY_DUR}s.\n"
                "REMINDER: Timestamps are VIDEO-RELATIVE (from 00:00:00), NOT the HUD wall clock."
            )
        else:
            duration_hint = (
                f"\n\nVIDEO DURATION CONSTRAINT (strictly enforced):\n"
                f"  - Total length : {dur_h:02d}:{dur_m:02d}:{dur_s:02d}\n"
                f"  - Valid start_time range: 00:00:05 to {max_h:02d}:{max_m:02d}:{max_s:02d}\n"
                "REMINDER: This video contains a bodycam HUD that shows the officer's "
                "real-world wall clock (e.g. '04:36 PM'). That wall clock is NOT the "
                "video playback time. Your start_time values must be in the range above "
                "(measured from video start), NOT based on the time shown on the HUD. "
                "Any timestamp outside the valid range will be rejected."
            )

    # Correction feedback: show Gemini exactly what it returned previously and why
    # it was wrong. This is the most direct way to break the HUD-clock confusion loop.
    rejection_context = ""
    if rejected_timestamps and vid_duration is not None:
        rejected_str = ", ".join(f'"{t}"' for t in rejected_timestamps)
        dur_h  = int(vid_duration // 3600)
        dur_m  = int((vid_duration % 3600) // 60)
        dur_s  = int(vid_duration % 60)
        max_start = vid_duration - CLIP_DURATION
        max_h  = int(max_start // 3600)
        max_m  = int((max_start % 3600) // 60)
        max_s  = int(max_start % 60)
        rejection_context = (
            f"\n\nCORRECTION REQUIRED - YOUR PREVIOUS RESPONSE WAS REJECTED:\n"
            f"You returned these timestamps: {rejected_str}\n"
            f"They are ALL invalid because the video is only {dur_h:02d}:{dur_m:02d}:{dur_s:02d} long.\n"
            "The most likely reason: you read the real-world wall clock visible in the bodycam HUD "
            "(e.g., '04:36:22 PM') and mistakenly used it as the video timestamp. "
            "That clock shows the officer's time of day, NOT the video playback position.\n"
            f"Video timestamps start at 00:00:00 and end at {dur_h:02d}:{dur_m:02d}:{dur_s:02d}.\n"
            f"You MUST return start_time values between 00:00:05 and {max_h:02d}:{max_m:02d}:{max_s:02d}. "
            "Analyze the video again and return completely different, valid timestamps."
        )

    # CTA override: appended AFTER the system-prompt's "no CTA" rule so Gemini
    # treats this as the final, authoritative instruction for this specific call.
    cta_override = (
        "\n\nCTA INSTRUCTION (MANDATORY — overrides format rules above): "
        "At the very end of EVERY title — after the final '!' — append exactly this phrase: "
        "' 👉 Follow for more!'"
        "\nFinal title format: \"[Hook story here]! 👉 Follow for more!\""
    ) if include_cta else ""

    if mode == "story":
        user_prompt = (
            f"Analyze the police bodycam video thoroughly and identify EVERY self-contained SCENE "
            f"with genuine viral potential. Each scene must have a natural arc (opening, escalation, resolution) "
            f"and its duration MUST be between {MIN_STORY_DUR}s and {MAX_STORY_DUR}s.\n\n"
            "DYNAMIC CANDIDATE SELECTION (No artificial limits):\n"
            "- Return ONLY scenes with genuine viral potential. Do NOT pad with boring filler.\n"
            "- If a video has many compelling scenes, return ALL of them.\n"
            "- Each candidate MUST include both start_time AND end_time (HH:MM:SS).\n"
            "Return raw JSON only."
            f"{duration_hint}"
            f"{rejection_context}"
        )
        _system = SYSTEM_PROMPT_STORY
    else:
        user_prompt = (
            "Analyze the police bodycam video thoroughly and identify EVERY SINGLE 16-second segment "
            "that has genuine viral potential (drama, tension, karma backfire, shock, unexpected twist, or intense confrontation).\n\n"
            "DYNAMIC CANDIDATE SELECTION (No artificial limits):\n"
            "- There is NO fixed quota, minimum, or maximum limit on the number of candidates.\n"
            "- If a video is quiet with only 1 or 2 viral moments, return ONLY those 1 or 2 candidates. Do NOT pad with mediocre/boring moments.\n"
            "- If a video is action-packed with many viral moments (10, 15, 20+), return ALL of them. Do NOT omit any genuinely high-engagement moment.\n"
            "- Quality, hook intensity, and viral payoff are the ONLY criteria.\n"
            "Return raw JSON only."
            f"{duration_hint}"
            f"{rejection_context}"
            f"{cta_override}"
        )
        _system = SYSTEM_PROMPT

    if sdk == "new":
        from google.genai import types
        safety = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
        ]
        if isinstance(remote, str):
            video_part = types.Part.from_uri(file_uri=remote, mime_type="video/mp4")
        else:
            video_part = types.Part.from_uri(file_uri=remote.uri,
                                             mime_type=remote.mime_type or "video/mp4")
        resp = client.models.generate_content(
            model=target_model,
            contents=[types.Content(role="user", parts=[
                video_part,
                types.Part.from_text(text=user_prompt),
            ])],
            config=types.GenerateContentConfig(
                system_instruction=_system,   # short → SYSTEM_PROMPT, story → SYSTEM_PROMPT_STORY
                temperature=0.4, max_output_tokens=4096,
                safety_settings=safety,
            ),
        )
        raw = resp.text
    else:
        # Old SDK may fail on any non-ASCII in the prompt text.
        # Sanitize the entire user_prompt as a final safety net.
        safe_prompt = user_prompt.encode("ascii", errors="replace").decode("ascii")
        safe_sys    = SYSTEM_PROMPT.encode("ascii", errors="replace").decode("ascii")
        safety_old = [
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        safe_sys_use = _system.encode("ascii", errors="replace").decode("ascii")
        model = client.GenerativeModel(model_name=target_model,
                                       system_instruction=safe_sys_use)
        resp = model.generate_content(
            [remote, safe_prompt],
            generation_config={"temperature": 0.4, "max_output_tokens": 4096},
            safety_settings=safety_old,
        )
        raw = resp.text

    log.ok(f"[{video_name}] Analysis complete.")
    if raw is None:
        msg = "None (Possible safety block or empty response)"
        try:
            if hasattr(resp, "candidates") and resp.candidates:
                cand = resp.candidates[0]
                finish_reason = getattr(cand, "finish_reason", None)
                if finish_reason and str(finish_reason) != "STOP":
                    msg = f"Blocked by Gemini: {finish_reason}"
            elif hasattr(resp, "prompt_feedback") and resp.prompt_feedback:
                msg = f"Blocked: {resp.prompt_feedback}"
        except Exception:
            pass
        raise ValueError(f"No candidates in response: {msg}")

    parsed = extract_json(raw)
    if not parsed or not parsed.get("candidates"):
        snippet = (raw[:400] if raw else "None")
        raise ValueError(f"No candidates in response:\n{snippet}")
    # Strip preamble labels Gemini sometimes adds inside title strings
    for idx, cand in enumerate(parsed.get("candidates", [])):
        if "suggested_titles" in cand:
            cand["suggested_titles"] = [
                _clean_title_str(t) for t in cand["suggested_titles"] if t
            ]
            cand["suggested_titles"] = [t for t in cand["suggested_titles"] if t]

        # Ensure candidate has a default title
        if not cand.get("title") and cand.get("suggested_titles"):
            cand["title"] = cand["suggested_titles"][0]

        # Tính clip_duration cho từng candidate từ end_time - start_time (Story Mode)
        # Short Mode: fallback về CLIP_DURATION (16s)
        if mode == "story" and "end_time" in cand and "start_time" in cand:
            try:
                end_sec   = ts_to_seconds(cand["end_time"])
                start_sec = ts_to_seconds(cand["start_time"])
                dur_calc  = end_sec - start_sec
                cand["clip_duration"] = int(max(MIN_STORY_DUR, min(MAX_STORY_DUR, dur_calc))) \
                    if dur_calc > 0 else (MIN_STORY_DUR + MAX_STORY_DUR) // 2
            except Exception:
                cand["clip_duration"] = (MIN_STORY_DUR + MAX_STORY_DUR) // 2
        else:
            cand.setdefault("clip_duration", CLIP_DURATION)

        # Normalize start_time and end_time into standard HH:MM:SS
        dur = float(cand.get("clip_duration") or CLIP_DURATION)
        raw_start = str(cand.get("start_time", "00:00:00")).strip()
        parts = raw_start.split(":")
        start_sec = ts_to_seconds(raw_start)

        # Timestamp self-healing: if Gemini outputs MM:SS:00 (e.g. 08:52:00 instead of 00:08:52)
        if vid_duration and vid_duration > 0:
            if start_sec > vid_duration:
                if len(parts) == 3:
                    try:
                        alt_sec = int(parts[0]) * 60 + int(parts[1]) + float(parts[2]) / 60.0
                        if alt_sec <= vid_duration:
                            start_sec = alt_sec
                    except (ValueError, IndexError):
                        pass
                elif len(parts) == 2:
                    try:
                        alt_sec = int(parts[0]) * 60 + float(parts[1])
                        if alt_sec <= vid_duration:
                            start_sec = alt_sec
                    except (ValueError, IndexError):
                        pass
            start_sec = max(0.0, min(start_sec, max(0.0, vid_duration - dur)))

        h = int(start_sec // 3600)
        m = int((start_sec % 3600) // 60)
        s = int(start_sec % 60)
        cand["start_time"] = f"{h:02d}:{m:02d}:{s:02d}"

        end_sec = start_sec + dur
        if vid_duration and vid_duration > 0:
            end_sec = min(vid_duration, end_sec)
        eh = int(end_sec // 3600)
        em = int((end_sec % 3600) // 60)
        es = int(end_sec % 60)
        cand["end_time"] = f"{eh:02d}:{em:02d}:{es:02d}"

    return parsed



def delete_remote(client, sdk: str, remote, log: ToolLogger) -> None:
    if isinstance(remote, str):
        return  # Direct YouTube URL, no remote uploaded file to delete
    try:
        if sdk == "new":
            client.files.delete(name=remote.name)
        else:
            client.delete_file(name=remote.name)
        log.dim(f"   [{remote.display_name}] Cloud file deleted.")
    except Exception as exc:
        log.warn(f"Could not delete remote file: {exc}")


def get_yt_cookie_file(custom_path: Optional[str] = None) -> Optional[str]:
    """Find valid YouTube cookies.txt file from custom path or standard workspace root locations."""
    candidates = []
    if custom_path:
        candidates.append(Path(custom_path))
    candidates.extend([
        Path("cookies.txt"),
        Path("youtube_cookies.txt"),
        Path(__file__).parent / "cookies.txt",
        Path(__file__).parent / "youtube_cookies.txt",
    ])
    for cand in candidates:
        try:
            if cand.exists() and cand.is_file() and cand.stat().st_size > 10:
                return str(cand.resolve())
        except Exception:
            pass
    return None


def get_youtube_info(url: str, cookies_browser: Optional[str] = None, cookie_file: Optional[str] = None) -> dict:
    """Fetch YouTube video metadata (title, duration, thumbnail) without downloading media."""
    import yt_dlp
    import shutil

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'source_address': '0.0.0.0',
        'retries': 5,
        'socket_timeout': 15,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'tv_embedded', 'mweb']
            }
        },
    }

    c_file = cookie_file or get_yt_cookie_file()
    if c_file:
        ydl_opts['cookiefile'] = c_file
    elif cookies_browser:
        try:
            ydl_opts['cookiesfrombrowser'] = (cookies_browser,)
        except Exception:
            pass

    if shutil.which("node"):
        try:
            ydl_opts['js_runtimes'] = {'node': {}}
        except Exception:
            pass

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", ""),
                "duration": float(info.get("duration", 0) or 0),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", ""),
                "view_count": info.get("view_count", 0),
                "url": url,
            }
    except Exception as e:
        err_msg = str(e)
        if 'cookiefile' in ydl_opts or 'cookiesfrombrowser' in ydl_opts:
            ydl_opts_no_cookie = dict(ydl_opts)
            ydl_opts_no_cookie.pop('cookiefile', None)
            ydl_opts_no_cookie.pop('cookiesfrombrowser', None)
            try:
                with yt_dlp.YoutubeDL(ydl_opts_no_cookie) as ydl_retry:
                    info = ydl_retry.extract_info(url, download=False)
                    return {
                        "title": info.get("title", ""),
                        "duration": float(info.get("duration", 0) or 0),
                        "thumbnail": info.get("thumbnail", ""),
                        "uploader": info.get("uploader", ""),
                        "view_count": info.get("view_count", 0),
                        "url": url,
                    }
            except Exception as e_retry:
                err_msg = str(e_retry)

        if "Sign in to confirm" in err_msg or "bot" in err_msg.lower():
            raise RuntimeError(
                "YouTube yêu cầu xác minh bot hoặc đăng nhập tài khoản (Sign in to confirm you're not a bot). "
                "Vui lòng nạp file cookies.txt vào Studio để xử lý video này!"
            ) from e
        raise RuntimeError(err_msg) from e


def download_youtube_section(
    url: str,
    start_time: str,
    end_time: str,
    output_path: str,
    cookies_browser: Optional[str] = None,
    cookie_file: Optional[str] = None,
    log: Optional[Any] = None,
    vid_duration: Optional[float] = None,
) -> str:
    """Download only a specific time-slice of a YouTube video using HTTP range requests."""
    import yt_dlp
    import shutil

    def _safe_log(msg: str, level: str = "info"):
        if not log:
            return
        if callable(log):
            try:
                log(msg)
            except TypeError:
                try:
                    log(level, msg)
                except Exception:
                    pass
        elif hasattr(log, level) and callable(getattr(log, level)):
            try:
                getattr(log, level)(msg)
            except Exception:
                pass

    start_s = float(ts_to_seconds(start_time))
    end_s = float(ts_to_seconds(end_time))
    if end_s <= start_s:
        end_s = start_s + float(CLIP_DURATION)

    # Timestamp self-healing: Check if timestamp was formatted as MM:SS:00 (e.g. 08:52:00 meant 8m52s)
    parts = start_time.strip().split(":")
    if len(parts) == 3 and start_s > 3600:
        try:
            alt_s = int(parts[0]) * 60 + int(parts[1]) + float(parts[2]) / 60.0
            if vid_duration and start_s > vid_duration and alt_s <= vid_duration:
                dur = end_s - start_s
                start_s = alt_s
                end_s = start_s + dur
                _safe_log(f"⚡ Timestamp self-healing: {start_time} -> {int(start_s//60):02d}:{int(start_s%60):02d}", "info")
            elif not vid_duration and int(parts[0]) < 60 and int(parts[1]) < 60 and start_s > 7200:
                # Video duration unknown, but start_s is 2+ hours and parts look like MM:SS:00
                try:
                    meta = get_youtube_info(url, cookies_browser=cookies_browser, cookie_file=cookie_file)
                    v_dur = meta.get("duration")
                    if v_dur and start_s > v_dur and alt_s <= v_dur:
                        dur = end_s - start_s
                        start_s = alt_s
                        end_s = start_s + dur
                        vid_duration = float(v_dur)
                        _safe_log(f"⚡ Timestamp self-healing: {start_time} -> {int(start_s//60):02d}:{int(start_s%60):02d}", "info")
                except Exception:
                    pass
        except Exception:
            pass

    # Buffer 0.5s before/after so keyframes slice cleanly
    req_start = max(0.0, start_s - 0.5)
    req_end = end_s + 0.5
    if vid_duration and vid_duration > 0:
        req_start = min(req_start, max(0.0, vid_duration - 1.0))
        req_end = min(vid_duration, max(req_start + 1.0, req_end))

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    if out_p.exists():
        try:
            out_p.unlink()
        except Exception:
            pass

    _safe_log(f"⚡ Downloading YouTube section [{start_time} - {end_time}] to {out_p.name}...")

    ydl_opts = {
        'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'download_ranges': yt_dlp.utils.download_range_func(None, [(req_start, req_end)]),
        'force_keyframes_at_cuts': True,
        'outtmpl': str(out_p),
        'quiet': True,
        'no_warnings': True,
        'retries': 10,
        'fragment_retries': 10,
        'source_address': '0.0.0.0',  # Force IPv4 against Windows IPv6 connection reset drops
        'socket_timeout': 30,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'tv_embedded', 'mweb']
            }
        },
    }

    try:
        if FFMPEG and Path(FFMPEG).exists():
            ydl_opts['ffmpeg_location'] = str(Path(FFMPEG).resolve())
    except Exception:
        pass

    c_file = cookie_file or get_yt_cookie_file()
    if c_file:
        ydl_opts['cookiefile'] = c_file
    elif cookies_browser:
        try:
            ydl_opts['cookiesfrombrowser'] = (cookies_browser,)
        except Exception:
            pass

    if shutil.which("node"):
        try:
            ydl_opts['js_runtimes'] = {'node': {}}
        except Exception:
            pass

    def _safe_run_download(opts_dict: dict, max_tries: int = 2) -> bool:
        last_e = None
        for attempt in range(max_tries):
            try:
                with yt_dlp.YoutubeDL(opts_dict) as ydl_inst:
                    ydl_inst.download([url])
                if out_p.exists() and out_p.stat().st_size > 1024:
                    return True
            except Exception as ex:
                last_e = ex
                if attempt < max_tries - 1:
                    time.sleep(1.5)
        if last_e:
            raise last_e
        return False

    try:
        _safe_run_download(ydl_opts, max_tries=2)
    except Exception as e:
        err_msg = str(e)
        # Nếu cookie bị lỗi hoặc session cookie hỏng (ví dụ: "The page needs to be reloaded", "Requested format not available",...)
        # -> Tự động thử lại ngay mà không dùng cookie
        if 'cookiefile' in ydl_opts or 'cookiesfrombrowser' in ydl_opts:
            _safe_log("⚠️ Cookie YouTube bị lỗi hoặc hết hạn, đang tự động thử lại không dùng cookie...")
            ydl_opts_no_cookie = dict(ydl_opts)
            ydl_opts_no_cookie.pop('cookiefile', None)
            ydl_opts_no_cookie.pop('cookiesfrombrowser', None)
            try:
                _safe_run_download(ydl_opts_no_cookie, max_tries=2)
                if out_p.exists() and out_p.stat().st_size > 1024:
                    return str(out_p.resolve())
            except Exception as e_retry:
                err_msg = str(e_retry)

        if "Sign in to confirm" in err_msg or "bot" in err_msg.lower():
            raise RuntimeError(
                "YouTube yêu cầu xác minh tài khoản (Sign in to confirm you're not a bot). "
                "Vui lòng nạp lại file cookies.txt mới từ trình duyệt để tải video này!"
            ) from e
        raise RuntimeError(err_msg) from e

    if not out_p.exists():
        raise RuntimeError(f"Failed to download YouTube section: {url}")

    return str(out_p.resolve())


# ──────────────────────────────────────────────────────────────────────────────
# FFmpeg — exact 16-second clip
# ──────────────────────────────────────────────────────────────────────────────

def get_video_duration(src: Path) -> Optional[float]:
    """Return video duration in seconds via ffprobe, or None on failure."""
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json",
             "-show_format", str(src)],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
    except Exception:
        pass
    return None


def _get_video_stream_info(src: Path) -> dict:
    """Return first video stream info dict via ffprobe."""
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json",
             "-show_streams", "-select_streams", "v:0", str(src)],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            streams = json.loads(result.stdout).get("streams", [])
            return streams[0] if streams else {}
    except Exception:
        pass
    return {}


def has_audio_stream(src: Path) -> bool:
    """Return True if the media file contains at least one audio stream."""
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json",
             "-show_streams", "-select_streams", "a:0", str(src)],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            streams = json.loads(result.stdout).get("streams", [])
            return len(streams) > 0
    except Exception:
        pass
    return False


def get_video_width(src: Path) -> int:
    return int(_get_video_stream_info(src).get("width", 1080))


def get_video_height(src: Path) -> int:
    return int(_get_video_stream_info(src).get("height", 1920))


def map_tracked_box_to_canvas(box: dict, orig_w: int, orig_h: int, st: dict) -> tuple[int, int, int, int]:
    """Map a tracked/detected box (original video coordinates) → 1080×1920 canvas coordinates.

    Models the EXACT FFmpeg transform order used in render_reup:
        smart_zoom(optional) → scale → crop(top+bottom) → hflip → vflip → overlay on canvas

    Bugs fixed vs old version:
    - Canvas centering now uses cropped height (fg_h * remain), not full fg_h.
    - flip_v is applied AFTER crop (matching FFmpeg pipeline), not before.
    - source_mask_bottom (cpb) is now included in the remain calculation.
    - smart_zoom 2% crop is correctly propagated to coordinates.
    """
    W, H = 1080, 1920

    bx = float(box.get("x", 0))
    by = float(box.get("y", 0))
    bw = float(box.get("w", 100))
    bh = float(box.get("h", 100))

    vw_scale       = float(st.get("video_w_scale",       1.0))
    vh_scale       = float(st.get("video_h_scale",       1.0))
    video_x_offset = int(st.get("video_x",              0))
    video_y_offset = int(st.get("video_y",              0))
    cpt = max(0.0, min(0.48, float(st.get("crop_top",    st.get("source_mask_top",    0.0)))))
    cpb = max(0.0, min(0.48, float(st.get("crop_bottom", st.get("source_mask_bottom", 0.0)))))
    cpl = max(0.0, min(0.48, float(st.get("crop_left",   0.0))))
    cpr = max(0.0, min(0.48, float(st.get("crop_right",  0.0))))
    if cpt + cpb > 0.96:
        cpb = max(0.0, 0.96 - cpt)
    if cpl + cpr > 0.96:
        cpr = max(0.0, 0.96 - cpl)
    remain_h = max(0.01, 1.0 - cpt - cpb)
    remain_w = max(0.01, 1.0 - cpl - cpr)

    # ── Step 1: smart_zoom (crop=0.98*iw:0.98*ih BEFORE scale) ───────────────
    # Removes 1% from each edge; adjust box origin accordingly.
    if st.get("smart_zoom", False):
        zm = 0.01  # 1% each side → effective source becomes 0.98x
        bx = bx - zm * orig_w
        by = by - zm * orig_h
        orig_w_eff = orig_w * 0.98
        orig_h_eff = orig_h * 0.98
    else:
        orig_w_eff = float(orig_w)
        orig_h_eff = float(orig_h)

    # ── Step 2: Scale to canvas width ─────────────────────────────────────────
    # FFmpeg: scale='trunc(W*vw_scale/2)*2':'trunc(W*(ih/iw)*vh_scale/2)*2'
    fg_w = (int(W * vw_scale) // 2) * 2
    fg_h = (int(W * (orig_h_eff / orig_w_eff) * vh_scale) // 2) * 2

    scale_x = fg_w / orig_w_eff if orig_w_eff > 0 else 1.0
    scale_y = fg_h / orig_h_eff if orig_h_eff > 0 else 1.0

    bx_s = bx * scale_x
    by_s = by * scale_y
    bw_s = bw * scale_x
    bh_s = bh * scale_y

    # ── Step 3: Top/bottom/left/right crop ────────────────────────────────────
    fg_h_cropped = fg_h * remain_h
    by_in_crop   = by_s - cpt * fg_h
    fg_w_cropped = fg_w * remain_w
    bx_in_crop   = bx_s - cpl * fg_w

    # ── Step 4: Flips — applied AFTER crop in FFmpeg pipeline ─────────────────
    if st.get("flip_h", False):
        bx_in_crop = fg_w_cropped - bx_in_crop - bw_s

    if st.get("flip_v", False):
        by_in_crop = fg_h_cropped - by_in_crop - bh_s

    # ── Step 5: Place on 1080×1920 canvas ─────────────────────────────────────
    fg_x_origin = (W - fg_w) / 2 + fg_w * cpl + video_x_offset
    fg_y_origin = (H - fg_h) / 2 + fg_h * cpt + video_y_offset

    bx_c = fg_x_origin + bx_in_crop
    by_c = fg_y_origin + by_in_crop
    bw_c = bw_s
    bh_c = bh_s

    # ── Clamp to canvas bounds ────────────────────────────────────────────────
    bx_c  = max(0.0, min(bx_c,       float(W)))
    bx2_c = max(0.0, min(bx_c + bw_c, float(W)))
    by_c  = max(0.0, min(by_c,       float(H)))
    by2_c = max(0.0, min(by_c + bh_c, float(H)))

    return int(bx_c), int(by_c), int(bx2_c - bx_c), int(by2_c - by_c)


def map_canvas_box_to_orig_video(box: dict, orig_w: int, orig_h: int, st: dict) -> tuple[int, int, int, int]:
    """Map 1080x1920 canvas box coordinates to original video frame coordinates."""
    W, H = 1080, 1920
    cx = float(box.get("x", 0))
    cy = float(box.get("y", 0))
    cw = float(box.get("w", 100))
    ch = float(box.get("h", 100))

    if orig_w <= 0 or orig_h <= 0:
        return int(cx), int(cy), int(cw), int(ch)

    vw_scale = float(st.get("video_w_scale", 1.0))
    vh_scale = float(st.get("video_h_scale", 1.0))
    video_x = float(st.get("video_x", 0))
    video_y = float(st.get("video_y", 0))

    contain_scale = min(W / orig_w, H / orig_h)
    fg_w = orig_w * contain_scale * vw_scale
    fg_h = orig_h * contain_scale * vh_scale

    fg_x = (W - fg_w) / 2 + video_x
    fg_y = (H - fg_h) / 2 + video_y

    rel_x = cx - fg_x
    rel_y = cy - fg_y

    scale_x = orig_w / fg_w if fg_w > 0 else 1.0
    scale_y = orig_h / fg_h if fg_h > 0 else 1.0

    ox = int(round(rel_x * scale_x))
    oy = int(round(rel_y * scale_y))
    ow = int(round(cw * scale_x))
    oh = int(round(ch * scale_y))

    # Clamp to valid original video dimensions
    ox = max(0, min(ox, orig_w - 1))
    oy = max(0, min(oy, orig_h - 1))
    ow = max(2, min(ow, orig_w - ox))
    oh = max(2, min(oh, orig_h - oy))

    return (ox, oy, ow, oh)



def _apply_tracked_blur_pass(src: Path, track_file: Path,
                             st: dict, log: ToolLogger) -> Path:
    """Apply per-frame blur using OpenCV CSRT tracking data.

    Reads track.json, opens src with OpenCV, applies Gaussian blur at
    tracked coordinates per frame, writes a temp file, then muxes audio
    back from src. Replaces src in-place on success.
    """
    try:
        import cv2 as cv2, json as _json, tempfile as _tmp, shutil as _sh

        track = _json.loads(track_file.read_text(encoding="utf-8"))
        frame_data: dict[int, tuple] = {
            f["frame"]: (f["x"], f["y"], f["w"], f["h"])
            for f in track.get("frames", [])
        }
        if not frame_data:
            log.warn("Tracked blur: no frame data — skipping.")
            return src

        cap = cv2.VideoCapture(str(src))
        if not cap.isOpened():
            log.warn("Tracked blur: could not open video.")
            return src

        fps  = cap.get(cv2.CAP_PROP_FPS) or 30.0
        w    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        orig_vw = track.get("width", w)
        orig_vh = track.get("height", h)
        
        tmp_vid = Path(_tmp.gettempdir()) / f"_tracked_{src.stem}.mp4"

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(tmp_vid), fourcc, fps, (w, h))

        frame_idx = 0
        log.info(f"🎯 Applying tracked blur ({len(frame_data)} keyframes)…")
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_idx in frame_data:
                bx_orig, by_orig, bw_orig, bh_orig = frame_data[frame_idx]
                box_dict = {"x": bx_orig, "y": by_orig, "w": bw_orig, "h": bh_orig}
                bx, by, bw, bh = map_tracked_box_to_canvas(box_dict, orig_vw, orig_vh, st)
                
                if bw > 0 and bh > 0:
                    roi = frame[by:by+bh, bx:bx+bw]
                    if roi.size == 0:
                        pass  # empty slice (edge case) – skip
                    else:
                        # Pixelate then heavy Gaussian for a solid, opaque censor
                        scale = max(1, min(bw, bh) // 8)
                        small = cv2.resize(roi, (max(1, bw // scale), max(1, bh // scale)),
                                           interpolation=cv2.INTER_LINEAR)
                        pixelated = cv2.resize(small, (bw, bh), interpolation=cv2.INTER_NEAREST)
                        ksize = max(51, (bw | 1), (bh | 1))   # always odd, at least 51
                        ksize = ksize if ksize % 2 == 1 else ksize + 1
                        blurred = cv2.GaussianBlur(pixelated, (ksize, ksize), 0)
                        frame[by:by+bh, bx:bx+bw] = blurred
            out.write(frame)
            frame_idx += 1



        cap.release(); out.release()

        # Mux original audio back
        tmp_final = Path(_tmp.gettempdir()) / f"_tracked_final_{src.stem}.mp4"
        mux = subprocess.run([
            FFMPEG, "-y",
            "-i", str(tmp_vid),
            "-i", str(src),
            "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "copy", "-movflags", "+faststart",
            str(tmp_final),
        ], capture_output=True, timeout=300)

        try: tmp_vid.unlink(missing_ok=True)
        except Exception: pass

        if mux.returncode == 0 and tmp_final.exists() and tmp_final.stat().st_size > 512:
            _sh.move(str(tmp_final), str(src))
            log.ok(f"🎯 Tracked blur applied → {src.name}")
        else:
            log.warn("Tracked blur mux failed — kept original video.")
            try: tmp_final.unlink(missing_ok=True)
            except Exception: pass

    except Exception as exc:
        log.warn(f"Tracked blur error: {exc} — skipped.")

    return src


def _inpaint_temporal_median_fallback(
    clip_path: str,
    blur_boxes: list[dict],
    output_path: str,
    st: dict,
    progress_cb=None,
) -> dict:
    """CPU fallback: temporal median fill + OpenCV INPAINT_TELEA."""
    import cv2
    import numpy as np
    import tempfile

    inpaint_boxes = [b for b in blur_boxes if b.get("mode", "blur") == "inpaint"]
    if not inpaint_boxes:
        return {"error": "No inpaint boxes found."}

    src = Path(clip_path)
    if not src.exists():
        return {"error": f"Source not found: {clip_path}"}

    try:
        cap = cv2.VideoCapture(str(src))
        fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
        vw    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        vh    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if progress_cb: progress_cb(0.0, "Reading frames…")
        frames = []
        while True:
            ok, f = cap.read()
            if not ok: break
            frames.append(f)
        cap.release()

        N = len(frames)
        if not N:
            return {"error": "No frames decoded."}

        masks = [np.zeros((vh, vw), dtype=np.uint8) for _ in range(N)]
        for box in inpaint_boxes:
            ox, oy, ow, oh = map_canvas_box_to_orig_video(
                {"x": box["x"], "y": box["y"], "w": box["w"], "h": box["h"]}, vw, vh, st
            )
            x1, y1 = max(0, ox), max(0, oy)
            x2, y2 = min(vw, ox + ow), min(vh, oy + oh)
            sf = max(0, int((box.get("start_time") or 0.0) * fps))
            ef = min(N - 1, int((box.get("end_time") or float("inf")) * fps)) if box.get("end_time") else N - 1
            for fi in range(sf, ef + 1):
                masks[fi][y1:y2, x1:x2] = 255

        if progress_cb: progress_cb(0.05, "Temporal fill…")
        result_frames = [f.copy() for f in frames]
        RADIUS = 12
        for fi in range(N):
            mask = masks[fi]
            if not mask.any(): continue
            refs = []
            for d in range(1, RADIUS + 1):
                for s in (-1, 1):
                    ri = fi + s * d
                    if 0 <= ri < N:
                        ov = np.logical_and(mask > 0, masks[ri] > 0).sum()
                        if ov / max(1, (mask > 0).sum()) < 0.20:
                            refs.append(frames[ri])
                if len(refs) >= 8: break
            if refs:
                bg = np.median(np.stack(refs, 0).astype(np.float32), 0).astype(np.uint8)
                ys, xs = np.where(mask > 0)
                result_frames[fi][ys, xs] = bg[ys, xs]
            else:
                result_frames[fi] = cv2.inpaint(frames[fi], mask, 5, cv2.INPAINT_TELEA)
            if progress_cb and fi % max(1, N // 20) == 0:
                progress_cb(0.05 + 0.80 * fi / N, f"Frame {fi+1}/{N}…")

        if progress_cb: progress_cb(0.87, "Encoding…")
        tmp_vid = Path(tempfile.gettempdir()) / f"_inp_{src.stem}.mp4"
        tmp_out = Path(output_path)
        tmp_out.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(tmp_vid), cv2.VideoWriter_fourcc(*"mp4v"), fps, (vw, vh))
        for f in result_frames: writer.write(f)
        writer.release()

        mux = subprocess.run([
            FFMPEG, "-y", "-i", str(tmp_vid), "-i", str(src),
            "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "copy", "-movflags", "+faststart", str(tmp_out),
        ], capture_output=True, timeout=600)
        try: tmp_vid.unlink(missing_ok=True)
        except Exception: pass

        if mux.returncode != 0 or not tmp_out.exists() or tmp_out.stat().st_size < 512:
            return {"error": f"Mux failed: {(mux.stderr or b'').decode(errors='replace')[-300:]}"}

        if progress_cb: progress_cb(1.0, "Done.")
        return {"status": "done", "output_path": str(tmp_out)}

    except Exception as exc:
        import traceback
        return {"error": f"Fallback inpaint error: {exc}\n{traceback.format_exc()[-400:]}"}


def inpaint_video_region(
    clip_path: str,
    blur_boxes: list[dict],
    output_path: str,
    st: dict,
    progress_cb=None,
) -> dict:
    """Remove/inpaint moving objects using ProPainter GPU (RTX 3050+).

    Pipeline:
    1. Filter blur_boxes to mode='inpaint'.
    2. Decode source video → build per-frame binary mask PNGs in a temp dir.
    3. Launch propainter_inpaint.py as a subprocess (GPU process isolated from FastAPI).
    4. Stream stdout: parse PROGRESS:<pct>:<msg> / DONE:<path> / ERROR:<msg>.
    5. On success return the output path; on ProPainter unavailability fall back
       to _inpaint_temporal_median_fallback() (CPU, no CUDA required).

    Args:
        clip_path:   Path to source MP4/MOV.
        blur_boxes:  List of blur_box dicts (mode='inpaint', x/y/w/h canvas coords).
        output_path: Destination path for the inpainted video.
        st:          Edit-state dict for coordinate mapping.
        progress_cb: Optional callable(pct: float, msg: str).

    Returns:
        {"status": "done", "output_path": str} or {"error": str}.
    """
    import cv2
    import numpy as np
    import tempfile
    import shutil

    inpaint_boxes = [b for b in blur_boxes if b.get("mode", "blur") == "inpaint"]
    if not inpaint_boxes:
        return {"error": "No inpaint boxes found in blur_boxes list."}

    src = Path(clip_path)
    if not src.exists():
        return {"error": f"Source file not found: {clip_path}"}

    # Locate ProPainter directory (alongside app.py)
    pp_dir = Path(__file__).parent / "ProPainter"
    worker_script = Path(__file__).parent / "propainter_inpaint.py"

    if not pp_dir.exists() or not worker_script.exists():
        # ProPainter not installed — use CPU fallback
        if progress_cb:
            progress_cb(0.0, "ProPainter not found — using CPU temporal fill fallback…")
        return _inpaint_temporal_median_fallback(
            clip_path, blur_boxes, output_path, st, progress_cb
        )

    # ── Step 1: Decode video & build mask frames ──────────────────────────────
    if progress_cb:
        progress_cb(0.0, "Building mask frames…")

    try:
        cap = cv2.VideoCapture(str(src))
        if not cap.isOpened():
            return {"error": "Could not open video."}

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        vw  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        vh  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        cap.release()

        tmp_mask_dir = Path(tempfile.gettempdir()) / f"_pp_masks_{src.stem}"
        tmp_mask_dir.mkdir(parents=True, exist_ok=True)

        # Re-open to get frame count accurately
        cap = cv2.VideoCapture(str(src))
        frames_written = 0
        fi = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            # Build combined mask for this frame from all inpaint boxes
            mask = np.zeros((vh, vw), dtype=np.uint8)
            for box in inpaint_boxes:
                ox, oy, ow, oh = map_canvas_box_to_orig_video(
                    {"x": box["x"], "y": box["y"], "w": box["w"], "h": box["h"]},
                    vw, vh, st
                )
                x1, y1 = max(0, ox), max(0, oy)
                x2, y2 = min(vw, ox + ow), min(vh, oy + oh)
                start_t = box.get("start_time") or 0.0
                end_t   = box.get("end_time")
                sf = int(start_t * fps)
                ef = int(end_t * fps) if end_t else total
                if sf <= fi <= ef:
                    mask[y1:y2, x1:x2] = 255
            cv2.imwrite(str(tmp_mask_dir / f"{fi:06d}.png"), mask)
            fi += 1
            frames_written += 1
        cap.release()

        if frames_written == 0:
            return {"error": "No frames decoded from video."}

    except Exception as exc:
        import traceback
        return {"error": f"Mask build error: {exc}\n{traceback.format_exc()[-300:]}"}

    # ── Step 2: Determine output path ─────────────────────────────────────────
    out_path = output_path.strip() or str(src.with_name(f"{src.stem}_inpainted{src.suffix}"))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Step 3: Run ProPainter subprocess ────────────────────────────────────
    # subvideo_length=50 keeps VRAM under 6GB on RTX 3050
    python_exe = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = sys.executable  # fallback to current interpreter

    cmd = [
        str(python_exe), str(worker_script),
        "--video",           str(src),
        "--mask",            str(tmp_mask_dir),
        "--output",          out_path,
        "--propainter-dir",  str(pp_dir),
        "--subvideo-length", "50",   # conservative for 6GB VRAM
        "--neighbor-length", "10",
        "--ref-stride",      "10",
        "--mask-dilation",   "4",
        "--fp16",            # halve VRAM usage on RTX 3050 6GB
    ]

    sub_env = os.environ.copy()
    sub_env["PYTHONIOENCODING"] = "utf-8"
    sub_env["PYTHONUTF8"] = "1"

    if progress_cb:
        try: progress_cb(0.02, "Launching ProPainter GPU process...")
        except Exception: pass

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
            env=sub_env,
        )

        last_error = ""
        for line in proc.stdout:
            line = line.rstrip()
            if line.startswith("PROGRESS:"):
                _, rest = line.split(":", 1)
                pct_str, _, msg = rest.partition(":")
                try:
                    pct = float(pct_str)
                except ValueError:
                    pct = 0.0
                if progress_cb:
                    try: progress_cb(pct, msg)
                    except Exception: pass
            elif line.startswith("DONE:"):
                _, out_file = line.split(":", 1)
                proc.wait()
                # Cleanup temp masks
                try: shutil.rmtree(tmp_mask_dir, ignore_errors=True)
                except Exception: pass
                if progress_cb: progress_cb(1.0, "ProPainter done.")
                return {"status": "done", "output_path": out_file.strip()}
            elif line.startswith("ERROR:"):
                _, err_msg = line.split(":", 1)
                last_error = err_msg.strip()
            # else: debug / tqdm lines — ignore

        proc.wait()
        # Cleanup
        try: shutil.rmtree(tmp_mask_dir, ignore_errors=True)
        except Exception: pass

        if proc.returncode != 0:
            return {"error": f"ProPainter failed (rc={proc.returncode}): {last_error or 'unknown error'}"}

        # If we reach here without a DONE line, check if output exists
        if Path(out_path).exists() and Path(out_path).stat().st_size > 512:
            if progress_cb: progress_cb(1.0, "Done.")
            return {"status": "done", "output_path": out_path}

        return {"error": f"ProPainter finished but output missing. {last_error}"}

    except Exception as exc:
        import traceback
        try: shutil.rmtree(tmp_mask_dir, ignore_errors=True)
        except Exception: pass
        return {"error": f"Subprocess error: {exc}\n{traceback.format_exc()[-400:]}"}



def cut_clip_exact(src: Path, start_ts: str, dst: Path,
                   log: ToolLogger, duration: int = CLIP_DURATION) -> Path:
    vid_dur = get_video_duration(src) or 0.0
    start_sec = ts_to_seconds(start_ts)
    if vid_dur > 0 and (start_sec >= max(0.0, vid_dur - 1.0) or vid_dur <= duration + 2):
        if start_sec > 0:
            log.warn(f"Start time {start_ts} ({start_sec:.1f}s) exceeds video length ({vid_dur:.1f}s). Resetting start to 00:00:00.")
        start_ts = "00:00:00"
        start_sec = 0.0

    log.info(f"✂️  FFmpeg: {start_ts} → +{duration}s (cutting raw clip)…")
    dst.parent.mkdir(parents=True, exist_ok=True)

    gpu_ok = False
    _dec = _gpu_decode_flags()  # [-hwaccel cuda ...] when NVENC available, else []
    if BEST_ENCODER == "h264_nvenc":
        cmd_nvenc = [
            FFMPEG, "-y",
            *_dec,
            "-ss", f"{start_sec:.3f}",
            "-i", str(src),
            "-t", str(duration),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll",
            "-c:a", "aac", "-b:a", "128k",
            "-avoid_negative_ts", "make_zero",
            str(dst),
        ]
        try:
            r_gpu = subprocess.run(
                cmd_nvenc, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if r_gpu.returncode == 0 and dst.exists() and dst.stat().st_size >= 512:
                gpu_ok = True
        except Exception:
            gpu_ok = False

    if not gpu_ok:
        cmd_cpu = [
            FFMPEG, "-y",
            "-ss", f"{start_sec:.3f}",
            "-i", str(src),
            "-t", str(duration),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-avoid_negative_ts", "make_zero",
            str(dst),
        ]
        result = subprocess.run(
            cmd_cpu, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg exit {result.returncode}:\n{result.stderr[-1200:]}")

    if not dst.exists() or dst.stat().st_size < 512:
        raise RuntimeError(f"FFmpeg ran but output file is missing or empty ({dst.name}, dur: {vid_dur:.1f}s, start: {start_ts}).")

    mb = dst.stat().st_size / 1_048_576
    log.ok(f"Raw cut saved: {dst.name} ({mb:.2f} MB)")
    return dst

# Detect Whisper once at import time so the UI can show/grey the checkbox.
try:
    import whisper as _whisper_mod
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

REUP_W, REUP_H = 1080, 1920   # TikTok / Reels / Shorts portrait target


def _default_edit_state() -> dict:
    """Return a fresh edit state with sensible defaults for a new reup item."""
    return {
        "text_x":         0,      # horizontal position in 1080×1920 coords
        "text_y":         60,     # vertical position in 1080×1920 coords
        "font_name":      "impact",   # "impact" | "arialbd" | "arial"
        "font_size":      52,
        "font_bold":      False,
        "font_italic":    False,
        "text_color":     "white",    # "white" | "yellow" | "black"
        "text_color_hex": "#ffffff",
        "text_bg":        "box",      # "none" | "box" | "outline"
        "text_align":     "left",     # "left" | "center" | "right"
        "box_mode":       "frame",
        "box_radius":     40,
        "box_pad_x":      30,
        "box_pad_y":      20,
        "box_opacity":     90,
        "box_bg_color":   "custom",
        "box_bg_color_hex": "#222222",
        "stroke_width":   2,
        "stroke_color_hex": "#000000",
        "stroke_enabled": True,
        "video_x":        0,          # horizontal pixel offset from centered position
        "video_y":        0,          # pixel offset from centered position
        "video_w_scale":  1.0,        # scale multiplier for foreground width
        "video_h_scale":  1.0,        # scale multiplier for foreground height
        "crop_top":       0.0,        # normalized crop margin (0.0 - 0.48)
        "crop_bottom":    0.0,        # normalized crop margin (0.0 - 0.48)
        "crop_left":      0.0,        # normalized crop margin (0.0 - 0.48)
        "crop_right":     0.0,        # normalized crop margin (0.0 - 0.48)
        "color_grade":    False,
        "subtitles":      False,
        "source_mask_top": 0.0,
        "source_mask_bottom": 0.0,
        "title_wrap_pct":  1.0,   # 0.3-1.0: fraction of canvas width for text wrap
        "blur_boxes":      [],    # [{x,y,w,h} in full-res 1080×1920 coords]
        "bg_type":          "blur",   # "blur" | "image" | "video"
        "bg_image_path":    "",
        "bg_video_path":    "",
        "hue_shift":        0,        # -180 to +180 degrees
        "saturation":       1.0,      # 0.5 to 2.0
        "flip_h":           False,    # horizontal flip
        "flip_v":           False,    # vertical flip
        "watermark_text":   "",
        "watermark_pos":    "BR",     # TL|TC|TR|ML|MC|MR|BL|BC|BR
        "watermark_opacity": 50,      # 10-100
        "watermark_size":   28,
        "watermark_color":  "#FFFFFF",
        "add_grain":        False,    # film grain for fingerprint evasion
        "grain_strength":   3,        # 1-10
        "speed_tweak":      False,    # ±2% speed shift
        "sub_margin_v":     200,      # subtitle distance from bottom in full-res px
        "sub_x":            0,        # horizontal pixel offset from centered position (-500 to +500)
        "sub_offset_ms":    -500,      # -500ms default: Gemini timestamps lag 500-900ms behind phoneme onset
        "change_md5":       True,     # Auto-randomize MD5 hash
        "overlays":         [],       # Multitrack image/video overlay layers
        # Custom Audio & Voiceover Swapping
        "custom_audio_path":       "",
        "custom_audio_name":       "",
        "custom_audio_url":        "",
        "custom_audio_dur":        0.0,
        "custom_audio_offset":     0.0,   # seconds: timeline start position
        "custom_audio_trim_start": 0.0,   # seconds: in-point within audio file
        "custom_audio_trim_dur":   0.0,   # seconds: active trimmed duration of audio
        "video_trim_dur":          0.0,   # seconds: 0 = full video length, >0 = trimmed length
        "orig_volume":             100,   # 0-100%
        "custom_volume":           100,   # 0-200%
    }



def _make_title_image(title: str, width: int = REUP_W, height: int = REUP_H,
                      font_name: str = "impact",
                      font_size: int = 52,
                      text_color: str = "white",
                      text_bg: str = "none",
                      text_x: int = 40,
                      text_y: int = 60,
                      text_align: str = "left",
                      title_wrap_pct: float = 1.0,
                      box_radius: int = 0,
                      box_mode: str = "frame",
                      box_pad_x: int = 30,
                      box_pad_y: int = 20,
                      box_bg_color: str = "black",
                      box_bg_color_hex: str = "#222222",
                      box_opacity: int = 90,
                      box_x1_pct: float = -1.0,
                      box_x2_pct: float = -1.0,
                      font_bold: bool = False,
                      # OpenCut text features
                      letter_spacing: int = 0,
                      line_height: float = 1.2,
                      font_italic: bool = False,
                      text_decoration: str = "none",
                      text_opacity: int = 100,
                      text_rotation: float = 0.0,
                      text_color_hex: str = "",
                      stroke_width: int = 0,
                      stroke_color_hex: str = "#000000",
                      stroke_enabled: bool = True,
                      title_lines: Optional[list[str]] = None) -> Optional[Path]:
    """Render title text onto a full-size transparent RGBA canvas matching Web UI preview 100%.

    Uses 2x Lanczos Supersampling Anti-Aliasing, layered stroke rendering, and exact geometry
    to eliminate jagged/uneven text border artifacts ("chỗ đậm chỗ nhạt").
    """
    if not PIL_AVAILABLE or not title or not title.strip():
        return None
    from PIL import Image, ImageDraw, ImageFont
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    import tempfile

    # ── Font loading ────────────────────────────────────────────────────────
    # Bundled fonts take priority over Windows system fonts so they work
    # identically in both dev (run via Python) and packaged EXE modes.
    _fd = str(FONTS_DIR)
    REGULAR = {
        "impact":          "C:/Windows/Fonts/impact.ttf",
        "arialbd":         "C:/Windows/Fonts/arialbd.ttf",
        "arial":           "C:/Windows/Fonts/arial.ttf",
        "segoeuib":        "C:/Windows/Fonts/segoeuib.ttf",
        "calibrib":        "C:/Windows/Fonts/calibrib.ttf",
        "verdanab":        "C:/Windows/Fonts/verdanab.ttf",
        "comicbd":         "C:/Windows/Fonts/comicbd.ttf",
        "trebucbd":        "C:/Windows/Fonts/trebucbd.ttf",
        "bebas":           "C:/Windows/Fonts/BebasNeue.ttf",
        "anton":           "C:/Windows/Fonts/Anton-Regular.ttf",
        "ariblk":          "C:/Windows/Fonts/ariblk.ttf",
        "gothicb":         "C:/Windows/Fonts/GOTHICB.TTF",
        # ── Bundled fonts ─────────────────────────────────────────────────
        # Use str(Path / filename) to avoid mixed backslash+forwardslash on Windows
        "montserrat":      str(FONTS_DIR / "Montserrat-Bold.ttf"),
        "luckiestguy":     str(FONTS_DIR / "LuckiestGuy-Regular.ttf"),
        "nunito":          str(FONTS_DIR / "Nunito-ExtraBold.ttf"),
        "permanentmarker": str(FONTS_DIR / "PermanentMarker-Regular.ttf"),
    }
    ITALIC = {
        "arial":    "C:/Windows/Fonts/ariali.ttf",
        "arialbd":  "C:/Windows/Fonts/arialbi.ttf",
        "calibrib": "C:/Windows/Fonts/calibriz.ttf",
        "verdanab": "C:/Windows/Fonts/verdanai.ttf",
        "trebucbd": "C:/Windows/Fonts/trebucit.ttf",
    }
    fp = (ITALIC if font_italic else {}).get(font_name) or REGULAR.get(font_name, REGULAR["impact"])

    font = None
    for _fp in [fp, REGULAR.get("arialbd", ""), REGULAR.get("arial", "")]:
        if not _fp:
            continue
        try:
            font = ImageFont.truetype(_fp, font_size)
            break
        except Exception:
            pass
    if font is None:
        try:
            font = ImageFont.load_default()
        except Exception:
            return None

    # ── Color resolution ───────────────────────────────────────────────────
    if text_color_hex and len(text_color_hex) == 7 and text_color_hex.startswith("#"):
        try:
            fg_color = (int(text_color_hex[1:3], 16),
                        int(text_color_hex[3:5], 16),
                        int(text_color_hex[5:7], 16))
        except ValueError:
            fg_color = (255, 255, 255)
    else:
        fg_color = {"white": (255,255,255), "yellow": (255,240,0), "black": (0,0,0)}.get(text_color, (255,255,255))

    # ── Geometry matching Web Preview 100% ──────────────────────────────────
    if box_mode == "capcut" and (line_height is None or line_height == 1.2):
        line_height = 1.35

    margin_x = 26.67
    full_container_w = width - 2 * margin_x
    wrap_ratio = max(0.3, min(1.0, title_wrap_pct))
    box_w = full_container_w * wrap_ratio

    if box_mode in ("capcut", "badges"):
        # Matches Web Preview CSS box-decoration-break inside container
        l_pad_x = max(6.0, font_size * 0.35)
        pad_x = 20.0 + l_pad_x
        pad_y = max(2.0, font_size * 0.16)
        max_text_w = max(50.0, box_w - 2 * pad_x)
    else:
        pad_x = 40.0
        pad_y = 26.67
        max_text_w = max(50.0, box_w - 2 * pad_x)

    # ── Exact lines: use title_lines from preview if provided, else wrap with harmonized max_text_w ───
    if title_lines and len(title_lines) > 0:
        lines = [str(l) for l in title_lines]
    else:
        clean = title.replace("\r", "").strip()
        paragraphs = clean.split('\n')
        lines = []
        for para in paragraphs:
            words = para.split(' ')
            if not words or words == ['']:
                lines.append('')
                continue
            cur_line = []
            for word in words:
                test = ' '.join(cur_line + [word]) if cur_line else word
                try:
                    tw = font.getlength(test)
                except Exception:
                    tw = len(test) * (font_size * 0.55)
                if tw <= max_text_w:
                    cur_line.append(word)
                else:
                    if cur_line:
                        lines.append(' '.join(cur_line))
                        cur_line = [word]
                    else:
                        lines.append(word)
                        cur_line = []
            if cur_line:
                lines.append(' '.join(cur_line))

        if not lines:
            lines = [clean]

    # ── High-Resolution 2x Supersampling ────────────────────────────────────
    SCALE = 2
    w2, h2 = width * SCALE, height * SCALE

    font2 = None
    for _fp in [fp, REGULAR["arialbd"], REGULAR["arial"]]:
        try:
            font2 = ImageFont.truetype(_fp, font_size * SCALE)
            break
        except Exception:
            pass
    if font2 is None:
        font2 = font

    margin_x2 = margin_x * SCALE
    full_container_w2 = w2 - 2 * margin_x2
    box_w2 = full_container_w2 * wrap_ratio
    pad_x2 = pad_x * SCALE
    pad_y2 = pad_y * SCALE
    max_text_w2 = max(100.0, box_w2 - 2 * pad_x2)

    try:
        ascent2, descent2 = font2.getmetrics()
    except Exception:
        ascent2, descent2 = int(font_size * SCALE * 0.8), int(font_size * SCALE * 0.2)
    natural_lh2 = ascent2 + descent2
    pil_spacing2 = max(0, int(natural_lh2 * (line_height - 1.0)))
    total_lh2 = natural_lh2 + pil_spacing2

    text_block_h2 = len(lines) * natural_lh2 + max(0, len(lines) - 1) * pil_spacing2
    box_h2 = int(text_block_h2 + 2 * pad_y2)

    box_top2 = int((text_y * SCALE) - (box_h2 / 2))
    box_bottom2 = box_top2 + box_h2
    box_left2 = int((w2 - box_w2) / 2 + (text_x * SCALE))
    box_right2 = int(box_left2 + box_w2)
    text_top2 = int(box_top2 + pad_y2)

    layer2 = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
    draw2 = ImageDraw.Draw(layer2)

    # 1. Background Box
    _ch = box_bg_color_hex.lstrip("#")
    try:
        _rgb = (int(_ch[0:2], 16), int(_ch[2:4], 16), int(_ch[4:6], 16))
    except Exception:
        _rgb = (34, 34, 34)
    _alpha = max(0, min(255, int(box_opacity * 2.55)))
    _fill = (*_rgb, _alpha)
    _radius2 = max(0, int((box_radius if box_radius > 0 else 40) * SCALE))
    _lspc2 = int(letter_spacing * SCALE)

    if _alpha > 0 and text_bg != "none":
        if box_mode == "capcut":
            # 🎬 CapCut Continuous Merged Bubble (Hút chân không liền khối):
            # Draw overlapping rounded rectangles for all lines on a mask so they merge into
            # a single seamless continuous polygon with rounded corners like CapCut.
            cur_y_box2 = text_top2
            box_mask2 = Image.new("L", (w2, h2), 0)
            bm_draw2  = ImageDraw.Draw(box_mask2)

            for line in lines:
                if not line.strip():
                    cur_y_box2 += total_lh2
                    continue
                try:
                    if _lspc2 != 0 and len(line) > 1:
                        lw2 = sum(font2.getlength(ch) for ch in line) + _lspc2 * max(0, len(line) - 1)
                    else:
                        lw2 = font2.getlength(line)
                except Exception:
                    lw2 = len(line) * (font_size * SCALE * 0.55)

                if text_align == "center":
                    line_x2 = int(box_left2 + pad_x2 + (max_text_w2 - lw2) / 2)
                elif text_align == "right":
                    line_x2 = int(box_right2 - pad_x2 - lw2)
                else:
                    line_x2 = int(box_left2 + pad_x2)

                # Horizontal & vertical padding: vertical padding ensures adjacent lines
                # overlap slightly (merged together) eliminating any gaps like vacuum-sealed wrap
                l_pad_x2 = int(font_size * SCALE * 0.35)
                l_pad_y2 = int(natural_lh2 * 0.16 + pil_spacing2 / 2 + 1)

                l_box_left   = int(line_x2 - l_pad_x2)
                l_box_right  = int(line_x2 + lw2 + l_pad_x2)
                l_box_top    = int(cur_y_box2 - l_pad_y2)
                l_box_bottom = int(cur_y_box2 + natural_lh2 + l_pad_y2)
                l_rad2       = min(_radius2, int((l_box_bottom - l_box_top) * 0.30))

                if l_rad2 > 0:
                    bm_draw2.rounded_rectangle([l_box_left, l_box_top, l_box_right, l_box_bottom], radius=l_rad2, fill=255)
                else:
                    bm_draw2.rectangle([l_box_left, l_box_top, l_box_right, l_box_bottom], fill=255)

                cur_y_box2 += total_lh2

            # Composite the continuous merged box onto layer2 with the chosen color and opacity
            box_solid2 = Image.new("RGBA", (w2, h2), (*_rgb, _alpha))
            layer2.paste(box_solid2, (0, 0), box_mask2)

        elif box_mode == "badges":
            # 🏷️ Separate Badges mode (từng thanh rời có khe hở)
            cur_y_box2 = text_top2
            for line in lines:
                if not line.strip():
                    cur_y_box2 += total_lh2
                    continue
                try:
                    if _lspc2 != 0 and len(line) > 1:
                        lw2 = sum(font2.getlength(ch) for ch in line) + _lspc2 * max(0, len(line) - 1)
                    else:
                        lw2 = font2.getlength(line)
                except Exception:
                    lw2 = len(line) * (font_size * SCALE * 0.55)

                if text_align == "center":
                    line_x2 = int(box_left2 + pad_x2 + (max_text_w2 - lw2) / 2)
                elif text_align == "right":
                    line_x2 = int(box_right2 - pad_x2 - lw2)
                else:
                    line_x2 = int(box_left2 + pad_x2)

                l_pad_x2 = int(font_size * SCALE * 0.35)
                l_pad_y2 = int(natural_lh2 * 0.08)

                l_box_left   = int(line_x2 - l_pad_x2)
                l_box_right  = int(line_x2 + lw2 + l_pad_x2)
                l_box_top    = int(cur_y_box2 - l_pad_y2)
                l_box_bottom = int(cur_y_box2 + natural_lh2 + l_pad_y2)
                l_rad2       = min(_radius2, int((l_box_bottom - l_box_top) * 0.30))

                if l_rad2 > 0:
                    draw2.rounded_rectangle([l_box_left, l_box_top, l_box_right, l_box_bottom], radius=l_rad2, fill=_fill)
                else:
                    draw2.rectangle([l_box_left, l_box_top, l_box_right, l_box_bottom], fill=_fill)

                cur_y_box2 += total_lh2

        else:
            # ⬜ Frame mode: full rectangular box
            if _radius2 > 0:
                draw2.rounded_rectangle([box_left2, box_top2, box_right2, box_bottom2], radius=_radius2, fill=_fill)
            else:
                draw2.rectangle([box_left2, box_top2, box_right2, box_bottom2], fill=_fill)

    # 2. Text Mask Generation for CapCut-style Smooth Rounded Stroke
    text_mask2 = Image.new("L", (w2, h2), 0)
    tm_draw2 = ImageDraw.Draw(text_mask2)

    # Recalculate max_text_w2 in case box was resized
    max_text_w2 = max(100.0, (box_right2 - box_left2) - 2 * pad_x2)

    cur_y2 = text_top2
    for line in lines:
        # ── Measure line width (includes letter_spacing gaps) ──────────────
        try:
            if _lspc2 != 0 and len(line) > 1:
                lw2 = sum(font2.getlength(ch) for ch in line) + _lspc2 * max(0, len(line) - 1)
            else:
                lw2 = font2.getlength(line)
        except Exception:
            lw2 = len(line) * (font_size * SCALE * 0.55)

        if text_align == "center":
            line_x2 = int(box_left2 + pad_x2 + (max_text_w2 - lw2) / 2)
        elif text_align == "right":
            line_x2 = int(box_right2 - pad_x2 - lw2)
        else:
            line_x2 = int(box_left2 + pad_x2)


        # ── Draw: char-by-char when spacing ≠ 0, else fast single call ─────
        if _lspc2 != 0:
            cx = line_x2
            for ch in line:
                tm_draw2.text((cx, cur_y2), ch, font=font2, fill=255)
                try:
                    cx += int(font2.getlength(ch)) + _lspc2
                except Exception:
                    cx += int(font_size * SCALE * 0.55) + _lspc2
        else:
            tm_draw2.text((line_x2, cur_y2), line, font=font2, fill=255)

        cur_y2 += total_lh2

    # 3. Stroke: Dilate → Gaussian smooth → composite (round corners, CapCut style)
    _user_sw = int(stroke_width)
    if stroke_enabled and _user_sw > 0:
        stroke_r = max(1, _user_sw * SCALE)

        # Pass 1: morphological dilation → correct outer radius
        dilated = text_mask2.filter(ImageFilter.MaxFilter(2 * stroke_r + 1))

        # Pass 2: Gaussian blur to smooth diamond/square corner artifacts into round ones.
        # sigma at 40% of stroke_r rounds corners without shrinking overall stroke width.
        smooth_sigma = max(0.8, stroke_r * 0.4)
        stroke_mask2 = dilated.filter(ImageFilter.GaussianBlur(radius=smooth_sigma))

        # Ensure text interior stays fully covered (no center fading artifact)
        from PIL import ImageChops as _IC
        stroke_mask2 = _IC.lighter(stroke_mask2, text_mask2)

        try:
            _sc = stroke_color_hex.lstrip("#")
            _stroke_rgb = (int(_sc[0:2], 16), int(_sc[2:4], 16), int(_sc[4:6], 16)) if len(_sc) == 6 else (0, 0, 0)
        except Exception:
            _stroke_rgb = (0, 0, 0)

        stroke_layer2 = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
        stroke_layer2.paste((*_stroke_rgb, 255), (0, 0), stroke_mask2)
        layer2 = Image.alpha_composite(layer2, stroke_layer2)

    # 4. Render Text Fill — text_mask2 carries PIL's built-in TrueType sub-pixel AA
    #    (grayscale 0-255 coverage values at glyph edges); using it as alpha gives
    #    smooth anti-aliased fill without any extra processing.
    text_fill_layer2 = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
    text_fill_layer2.paste((*fg_color, 255), (0, 0), text_mask2)
    layer2 = Image.alpha_composite(layer2, text_fill_layer2)


    # 5. Rotation
    if text_rotation != 0:
        center_x2 = box_left2 + box_w2 / 2
        center_y2 = text_y * SCALE
        layer2 = layer2.rotate(-text_rotation, resample=Image.BICUBIC, center=(center_x2, center_y2))

    # 4. Downsample 2x -> 1x with Lanczos Anti-Aliasing for smooth, professional edges
    text_layer = layer2.resize((width, height), Image.Resampling.LANCZOS)

    # ── Save to temporary PNG file ──────────────────────────────────────────
    tmp = Path(tempfile.mktemp(suffix="_reup_title.png"))
    text_layer.save(str(tmp), "PNG")
    return tmp

def _extract_audio_wav(clip: Path, log: ToolLogger) -> Optional[Path]:
    """Extract mono 16kHz WAV from clip for audio-only Gemini transcription.

    Audio-only removes visual distractors (bodycam HUD clock, on-screen text)
    so Gemini focuses purely on the audio waveform for timestamp alignment.
    """
    import tempfile as _tmp
    # Strip non-ASCII chars (e.g. curly apostrophes in filenames) so the
    # temp path is always ASCII-safe for the old Gemini SDK upload.
    _safe_stem = re.sub(r"[^\x00-\x7F]", "_", clip.stem[:30])
    _uid = uuid.uuid4().hex[:8]
    wav = Path(_tmp.gettempdir()) / f"_transcribe_{_uid}_{_safe_stem}.wav"
    cmd = [
        FFMPEG, "-y", "-i", str(clip),
        "-vn",                      # no video
        "-acodec", "pcm_s16le",     # standard PCM
        "-ar", "16000",             # 16kHz — ideal for ASR
        "-ac", "1",                 # mono
        str(wav),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0 and wav.exists() and wav.stat().st_size > 100:
            return wav
        log.warn(f"Audio extraction failed (rc={result.returncode}) — using video file")
        return None
    except Exception as exc:
        log.warn(f"Audio extraction error: {exc} — using video file")
        return None


def _upload_audio(client, sdk: str, audio_path: Path,
                  log: ToolLogger, stop: threading.Event):
    """Upload audio file to Gemini Files API (same pattern as upload_video)."""
    log.info(f"⬆️  Uploading audio for transcription…")
    safe_name = audio_path.name.encode("ascii", errors="replace").decode("ascii")
    if sdk == "new":
        remote = client.files.upload(
            file=str(audio_path),
            config={"display_name": safe_name},
        )
    else:
        # Old SDK encodes the file path as ASCII in multipart headers —
        # use the same ASCII-safe hardlink pattern as upload_video.
        # Pass resumable=False to avoid 400 Bad Request chunk granularity error on small WAV files
        upload_path, tmp_created = _ascii_safe_path(audio_path)
        try:
            try:
                remote = client.upload_file(path=str(upload_path), display_name=safe_name, resumable=False)
            except TypeError:
                remote = client.upload_file(path=str(upload_path), display_name=safe_name)
        finally:
            if tmp_created:
                try:
                    upload_path.unlink(missing_ok=True)
                except Exception:
                    pass

    # Wait for ACTIVE state
    polls = 0
    while True:
        if stop.is_set():
            raise InterruptedError("Stopped by user.")
        state = getattr(remote.state, "name", str(remote.state))
        if state == "ACTIVE":
            break
        if state == "FAILED":
            raise RuntimeError("Gemini audio upload FAILED.")
        polls += 1
        log.dim(f"   Audio upload: waiting ACTIVE (poll #{polls})…")
        time.sleep(3)
        remote = (client.files.get(name=remote.name) if sdk == "new"
                  else client.get_file(name=remote.name))
    log.ok("Audio ACTIVE on Gemini.")
    return remote


def _build_anchored_words_from_cues(cues: list[dict]) -> list[dict]:
    """Derive millisecond-accurate word timestamps by interpolating words within phrase cues.

    Guarantees 0.000s cumulative drift regardless of video length because
    every word is strictly bounded by its parent phrase cue's audio start/end timestamps.
    Character lengths (phonetic weight) determine word duration distribution inside each phrase.
    """
    words = []
    for cue in cues:
        c_start = float(cue["start"])
        c_end   = float(cue["end"])
        text    = str(cue["text"]).strip()
        if not text:
            continue
        c_dur = max(0.1, c_end - c_start)
        raw_words = text.split()
        if not raw_words:
            continue

        weights = [max(1, len(w)) for w in raw_words]
        total_w = sum(weights)

        curr_t = c_start
        for i, w in enumerate(raw_words):
            if i == len(raw_words) - 1:
                next_t = c_end
            else:
                w_dur = c_dur * (weights[i] / total_w)
                next_t = round(curr_t + w_dur, 3)
                next_t = min(next_t, c_end - 0.02)

            words.append({
                "word": w,
                "start": round(curr_t, 3),
                "end": max(round(next_t, 3), round(curr_t + 0.04, 3))
            })
            curr_t = next_t
    return words


def _gemini_transcribe(clip: Path, client, sdk: str,
                       log: ToolLogger, stop: threading.Event,
                       word_level: bool = False,
                       model_name: Optional[str] = None,
                       edit_state: Optional[dict] = None) -> Optional[Path]:
    target_model = model_name or MODEL_NAME
    """Extract audio, upload to Gemini, produce millisecond-accurate SRT.

    Uses phrase-level prompt for 100% anchored timestamp stability, then generates
    phrase-anchored word timestamps when word_level=True.
    """
    def _fmt(t: float) -> str:
        h = int(t // 3600); m = int((t % 3600) // 60)
        s = int(t % 60);    ms = int(round((t % 1) * 1000))
        if ms >= 1000:
            s += 1; ms = 0
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    if not clip or not Path(clip).exists():
        log.warn(f"Clip not found for Gemini transcription: {clip}")
        return None

    dur = get_video_duration(clip) or 0.0
    wav_path: Optional[Path] = None
    ca_offset = 0.0

    custom_audio_path_str = edit_state.get("custom_audio_path", "") if edit_state else ""
    has_custom_audio = bool(custom_audio_path_str and Path(custom_audio_path_str).exists())

    try:
        if has_custom_audio:
            ca_path = Path(custom_audio_path_str)
            ca_offset     = max(0.0, float(edit_state.get("custom_audio_offset", 0.0)))
            ca_trim_start = max(0.0, float(edit_state.get("custom_audio_trim_start", 0.0)))
            ca_trim_dur   = float(edit_state.get("custom_audio_trim_dur", 0.0))
            ca_full_dur   = float(edit_state.get("custom_audio_dur", 0.0))
            if ca_full_dur <= 0:
                ca_full_dur = get_video_duration(ca_path) or 0.0

            if ca_trim_dur <= 0.0 or ca_trim_dur > (ca_full_dur - ca_trim_start):
                ca_trim_dur = max(0.5, ca_full_dur - ca_trim_start)

            dur = ca_trim_dur
            import tempfile as _tmp
            _safe_stem = re.sub(r"[^\x00-\x7F]", "_", ca_path.stem[:30])
            _uid = uuid.uuid4().hex[:8]
            wav_path = Path(_tmp.gettempdir()) / f"_transcribe_ca_{_uid}_{_safe_stem}.wav"
            _cmd = [
                FFMPEG, "-y",
                *(["-ss", f"{ca_trim_start:.3f}"] if ca_trim_start > 0 else []),
                "-t", f"{ca_trim_dur:.3f}",
                "-i", str(ca_path),
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                str(wav_path)
            ]
            log.info(f"🎙  Gemini: extracting custom audio ({ca_path.name}) for transcription [{ca_trim_start:.2f}s -> {ca_trim_start + ca_trim_dur:.2f}s, offset: {ca_offset:.2f}s]...")
            try:
                subprocess.run(_cmd, capture_output=True, check=True, timeout=60)
            except Exception as _e:
                log.warn(f"Failed to extract custom audio segment: {_e}")
                wav_path = None

            if wav_path and wav_path.exists():
                log.info("🎙  Gemini: uploading custom audio for transcription (audio-only)…")
                remote = _upload_audio(client, sdk, wav_path, log, stop)
                media_label = "audio recording"
            else:
                log.info("🎙  Gemini: uploading video for transcription…")
                remote = upload_video(client, sdk, clip, log, stop)
                media_label = "video"
        else:
            wav_path = _extract_audio_wav(clip, log)
            if wav_path:
                log.info("🎙  Gemini: uploading audio for transcription (audio-only)…")
                remote = _upload_audio(client, sdk, wav_path, log, stop)
                media_label = "audio recording"
            else:
                log.info("🎙  Gemini: uploading video for transcription…")
                remote = upload_video(client, sdk, clip, log, stop)
                media_label = "video"

        # Single high-accuracy phrase-level prompt — prevents Gemini token drift over long clips
        # NOTE: Do NOT use response_mime_type='application/json' — it causes Gemini to infer an
        # incomplete schema and return {start, end} objects WITHOUT the required 'text' field.
        # Free-text mode + _robust_parse JSON extraction is reliable and includes all fields.
        prompt = (
            "You are a professional subtitle transcriber with millisecond precision.\n\n"
            f"TASK: Transcribe every word spoken in this {media_label}.\n"
            f"AUDIO STARTS AT exactly 0.000 seconds and ends at {dur:.3f} seconds.\n\n"
            "STRICT RULES:\n"
            "1. ONE CUE PER BREATH / SHORT PHRASE (1\u20136 words max per cue).\n"
            "2. EVERY ENTRY MUST HAVE ALL THREE FIELDS: start, end, text.\n"
            "   - 'start' = instant the FIRST word of the cue begins (seconds, 3 decimal places).\n"
            "   - 'end'   = instant the LAST word of the cue finishes (seconds, 3 decimal places).\n"
            "   - 'text'  = the EXACT words spoken in the cue — THIS FIELD IS MANDATORY.\n"
            "   - Do NOT return entries without a 'text' field.\n"
            f"   - All time values in range 0.000 \u2013 {dur:.3f}.\n"
            "3. VERBATIM: write exactly what is spoken.\n"
            "4. Mark unclear speech as [inaudible].\n"
            "5. If NO speech at all, return: []\n\n"
            "OUTPUT \u2014 a JSON array of objects, each with EXACTLY these three keys:\n"
            '[{"start": 0.350, "end": 1.120, "text": "Get on the ground!"},\n'
            ' {"start": 1.200, "end": 2.050, "text": "Do not move!"}]\n\n'
            "Begin transcription now:"
        )

        if sdk == "new":
            from google.genai import types as _gt
            resp = client.models.generate_content(
                model=target_model,
                contents=[remote, prompt],
                config=_gt.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=8192,
                    # NO response_mime_type here — JSON mode causes Gemini to drop the 'text' field
                ),
            )
            raw = resp.text
        else:
            model = client.GenerativeModel(
                target_model,
                generation_config={
                    "temperature": 0.0,
                    "max_output_tokens": 8192,
                    # NO response_mime_type — JSON mode causes text field to be dropped
                },
            )
            raw = model.generate_content([remote, prompt]).text

        raw = (raw or "").strip()

        import json as _json, re as _re

        # Strip markdown fences aggressively
        raw = _re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=_re.IGNORECASE)
        raw = _re.sub(r"\s*```\s*$", "", raw.strip())
        raw = raw.strip()

        def _robust_parse(text: str) -> list:
            """Multi-strategy JSON extraction that survives Gemini quirks & preamble."""
            if not text:
                return []

            # Strategy 1: direct parse (happy path)
            try:
                val = _json.loads(text)
                if isinstance(val, list):
                    return val
            except Exception:
                pass

            # Strategy 2: find actual JSON array of objects starting with '[' followed by '{'
            match = _re.search(r"\[\s*\{", text)
            if match:
                start = match.start()
                depth = 0
                for i, ch in enumerate(text[start:], start):
                    if ch == "[":
                        depth += 1
                    elif ch == "]":
                        depth -= 1
                        if depth == 0:
                            try:
                                val = _json.loads(text[start : i + 1])
                                if isinstance(val, list):
                                    return val
                            except Exception:
                                pass
                            break

                # Strategy 3: truncate after last complete object (handles truncated response)
                try:
                    snippet = text[start:]
                    last_brace = snippet.rfind("}")
                    if last_brace != -1:
                        repaired = snippet[: last_brace + 1] + "\n]"
                        val = _json.loads(repaired)
                        if isinstance(val, list):
                            return val
                except Exception:
                    pass

            # Strategy 4: regex match all individual JSON objects {"word"...} or {"start"...}
            objects = []
            for obj_str in _re.findall(r"\{[^{}]*\}", text):
                try:
                    obj = _json.loads(obj_str)
                    if isinstance(obj, dict) and ("word" in obj or "text" in obj or "start" in obj):
                        objects.append(obj)
                except Exception:
                    pass

            if objects:
                return objects

            # Strategy 5: empty list if Gemini returned []
            if "[]" in text or text.strip() in ("", "[]"):
                return []

            raise ValueError("Cannot extract JSON array from Gemini response")


        segs = _robust_parse(raw)
        if not segs:
            log.warn("Gemini: no speech detected — subtitles skipped.")
            return None

        srt_p = clip.with_suffix(".srt")

        # Normalize segment dict keys (Gemini API sometimes names text as 'content', 'transcript', 'dialogue', 'speech', etc.)
        norm_segs = []
        for s in segs:
            if not isinstance(s, dict):
                continue
            start_v = s.get("start", s.get("s", s.get("begin", 0.0)))
            end_v   = s.get("end",   s.get("e", s.get("finish", 0.0)))
            text_v  = (
                s.get("text") or s.get("word") or s.get("content") or
                s.get("transcript") or s.get("dialogue") or s.get("speech") or
                s.get("sentence") or s.get("phrase") or s.get("t") or s.get("val") or ""
            )
            norm_segs.append({
                "start": start_v,
                "end": end_v,
                "text": str(text_v).strip()
            })

        _has_text = any(s["text"] for s in norm_segs)
        if not _has_text:
            log.info("Gemini returned timing-only segments — automatically using Stable Whisper for 100% accurate subtitles...")
            return None

        # Detect format: word-level has 'word' key; phrase-level has 'text' key
        _is_word_level = segs and "word" in segs[0] and "text" not in segs[0]

        if _is_word_level:
            # Gemini returned word-level despite phrase prompt — group into ~5-word phrases
            log.info("Gemini returned word-level format — grouping into phrase cues...")
            _all_words: list[dict] = []
            for w in segs:
                try:
                    ws = float(w.get("start", w.get("s", 0)))
                    we = float(w.get("end",   w.get("e", 0)))
                    wt = str(w.get("word", w.get("text", ""))).strip()
                except (ValueError, TypeError):
                    continue
                if not wt or wt in ("[?]", "[inaudible]"):
                    continue
                we = max(we, ws + 0.04)
                _all_words.append({"word": wt, "start": ws, "end": we})

            # Group into ~5-word phrase cues
            MAX_W = 5
            clean: list[dict] = []
            for _gi in range(0, len(_all_words), MAX_W):
                chunk = _all_words[_gi:_gi + MAX_W]
                text  = " ".join(w["word"] for w in chunk)
                clean.append({"start": chunk[0]["start"], "end": chunk[-1]["end"], "text": text})
        else:
            # Phrase-level format: {start, end, text}
            clean: list[dict] = []
            for seg in segs:
                try:
                    s = float(seg.get("start", seg.get("s", 0)))
                    e = float(seg.get("end",   seg.get("e", 0)))
                    t = str(seg.get("text", seg.get("word", ""))).strip()
                except (KeyError, ValueError, TypeError):
                    continue
                # Keep [inaudible] cues — they mark silences in the timeline
                # Only skip completely empty text
                if not t:
                    continue
                e = max(e, s + 0.05)
                if dur > 0:
                    s = min(max(s, 0.0), dur - 0.05)
                    e = min(e, dur)
                if clean and clean[-1]["text"] == t:
                    clean[-1]["end"] = max(clean[-1]["end"], e)
                    continue
                clean.append({"start": s, "end": e, "text": t})

        if not clean:
            _sample  = str(segs[:3])[:300] if segs else "(empty segs)"
            _raw_snip = raw[:300] if raw else "(empty raw)"
            log.warn(
                f"Gemini: no valid subtitle cues.\n"
                f"  segs[0..3]={_sample}\n"
                f"  raw[:300]={_raw_snip}"
            )
            return None

        # Drift correction: if last cue ends well before clip duration, rescale all timestamps
        if dur > 1.0 and len(clean) >= 2:
            reported_end = clean[-1]["end"]
            if reported_end > 0 and reported_end < dur * 0.88:
                scale = dur / reported_end
                log.info(f"🕐 Drift detected ({reported_end:.2f}s vs {dur:.2f}s). Rescaling ×{scale:.3f}")
                for seg in clean:
                    seg["start"] = min(round(seg["start"] * scale, 3), dur - 0.05)
                    seg["end"]   = min(round(seg["end"]   * scale, 3), dur)
                    seg["end"]   = max(seg["end"], seg["start"] + 0.05)

        # Shift timestamps by custom audio timeline offset
        if ca_offset > 0.005:
            for seg in clean:
                seg["start"] = round(seg["start"] + ca_offset, 3)
                seg["end"]   = round(seg["end"] + ca_offset, 3)

        # Write SRT file from anchored phrase cues
        srt_p.parent.mkdir(parents=True, exist_ok=True)
        with open(srt_p, "w", encoding="utf-8") as f:
            for i, seg in enumerate(clean, 1):
                f.write(f"{i}\n{_fmt(seg['start'])} --> {_fmt(seg['end'])}\n{seg['text']}\n\n")

        # Derive anchored word-level JSON for karaoke/highlight modes
        anchored_words = _build_anchored_words_from_cues(clean)
        words_p = clip.with_suffix(".words.json")
        words_p.parent.mkdir(parents=True, exist_ok=True)
        with open(words_p, "w", encoding="utf-8") as f:
            _json.dump(anchored_words, f, ensure_ascii=False, indent=2)

        log.ok(f"Subtitles (Gemini) → {srt_p.name}  ({len(clean)} cues, {len(anchored_words)} anchored words)")
        return srt_p

    except Exception as exc:
        log.error(f"Gemini transcription failed: {exc} — falling back to Whisper")
        return None

    finally:
        if wav_path:
            try: wav_path.unlink(missing_ok=True)
            except Exception: pass





def _whisper_transcribe(clip: Path, log: ToolLogger,
                        word_level: bool = False,
                        edit_state: Optional[dict] = None) -> Optional[Path]:
    """Transcribe audio with Whisper (stable-ts / openai-whisper) and write .srt + .words.json.

    Upgraded with stable-ts (Stable Whisper):
    • Uses energy-peak alignment for millisecond-accurate per-word timing.
    • Suppresses silent-gap hallucinations and timestamp drift.
    • Automatic VRAM/RAM memory cleanup on completion.
    """
    if not clip or not Path(clip).exists():
        log.warn(f"Clip not found for Whisper transcription: {clip}")
        return None

    if not WHISPER_AVAILABLE:
        log.warn("Whisper not installed — pip install openai-whisper stable-ts")
        return None

    import gc
    import json as _json

    # Try stable_whisper first for millisecond-accurate alignment, fallback to openai-whisper
    try:
        import stable_whisper as _sw
        STABLE_WHISPER_AVAILABLE = True
    except ImportError:
        import whisper as _w
        STABLE_WHISPER_AVAILABLE = False

    def _fmt(t: float) -> str:
        h = int(t // 3600); m = int((t % 3600) // 60)
        s = int(t % 60);    ms = int(round((t % 1) * 1000))
        if ms >= 1000: s += 1; ms = 0
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    model = None
    wav_path: Optional[Path] = None
    ca_offset = 0.0

    custom_audio_path_str = edit_state.get("custom_audio_path", "") if edit_state else ""
    has_custom_audio = bool(custom_audio_path_str and Path(custom_audio_path_str).exists())

    try:
        if has_custom_audio:
            ca_path = Path(custom_audio_path_str)
            ca_offset     = max(0.0, float(edit_state.get("custom_audio_offset", 0.0)))
            ca_trim_start = max(0.0, float(edit_state.get("custom_audio_trim_start", 0.0)))
            ca_trim_dur   = float(edit_state.get("custom_audio_trim_dur", 0.0))
            ca_full_dur   = float(edit_state.get("custom_audio_dur", 0.0))
            if ca_full_dur <= 0:
                ca_full_dur = get_video_duration(ca_path) or 0.0

            if ca_trim_dur <= 0.0 or ca_trim_dur > (ca_full_dur - ca_trim_start):
                ca_trim_dur = max(0.5, ca_full_dur - ca_trim_start)

            import tempfile as _tmp
            _safe_stem = re.sub(r"[^\x00-\x7F]", "_", ca_path.stem[:30])
            _uid = uuid.uuid4().hex[:8]
            wav_path = Path(_tmp.gettempdir()) / f"_transcribe_ca_{_uid}_{_safe_stem}.wav"
            _cmd = [
                FFMPEG, "-y",
                *(["-ss", f"{ca_trim_start:.3f}"] if ca_trim_start > 0 else []),
                "-t", f"{ca_trim_dur:.3f}",
                "-i", str(ca_path),
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                str(wav_path)
            ]
            log.info(f"🎙  Whisper: extracting custom audio ({ca_path.name}) for transcription [{ca_trim_start:.2f}s -> {ca_trim_start + ca_trim_dur:.2f}s, offset: {ca_offset:.2f}s]...")
            try:
                subprocess.run(_cmd, capture_output=True, check=True, timeout=60)
                transcribe_target = str(wav_path)
            except Exception as _e:
                log.warn(f"Failed to extract custom audio segment for Whisper: {_e}")
                transcribe_target = str(clip)
        else:
            transcribe_target = str(clip)

        import torch
        _device = "cuda" if (torch.cuda.is_available()) else "cpu"

        if STABLE_WHISPER_AVAILABLE:
            log.info(f"Stable Whisper (small on {_device}): transcribing with energy alignment...")
            try:
                model = _sw.load_model("small", device=_device)
            except Exception as _e_dev:
                if _device == "cuda":
                    log.warn(f"Whisper CUDA init failed ({_e_dev}), falling back to CPU...")
                    model = _sw.load_model("small", device="cpu")
                else:
                    raise
            # stable-ts transcribe with word alignment & silence suppression
            result = model.transcribe(
                transcribe_target,
                fp16=(_device == "cuda"),
                regroup=True,
                suppress_silence=True,
                no_speech_threshold=0.6,
                condition_on_previous_text=False,
                temperature=0.0,
            )
            # Extract word timestamp dicts from stable-ts result
            all_words: list[dict] = []
            try:
                for w in result.all_words():
                    wt = str(w.word).strip()
                    if not wt:
                        continue
                    ws = float(w.start)
                    we = float(w.end)
                    we = max(we, ws + 0.05)
                    all_words.append({"word": wt, "start": ws, "end": we})
            except Exception:
                # Fallback dictionary extraction if result format differs
                for seg in getattr(result, "segments", []):
                    for w in getattr(seg, "words", []):
                        wt = str(getattr(w, "word", w.get("word", "") if isinstance(w, dict) else "")).strip()
                        if not wt:
                            continue
                        ws = float(getattr(w, "start", w.get("start", 0) if isinstance(w, dict) else 0))
                        we = float(getattr(w, "end", w.get("end", ws + 0.1) if isinstance(w, dict) else ws + 0.1))
                        we = max(we, ws + 0.05)
                        all_words.append({"word": wt, "start": ws, "end": we})
        else:
            log.info(f"Whisper (small on {_device}): transcribing...")
            try:
                model = _w.load_model("small", device=_device)
            except Exception as _e_dev:
                if _device == "cuda":
                    log.warn(f"Whisper CUDA init failed ({_e_dev}), falling back to CPU...")
                    model = _w.load_model("small", device="cpu")
                else:
                    raise
            result = model.transcribe(
                transcribe_target,
                fp16=(_device == "cuda"),
                word_timestamps=True,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                logprob_threshold=-1.0,
                compression_ratio_threshold=2.4,
                temperature=0.0,
            )
            all_words = []
            for seg in result.get("segments", []):
                for w in seg.get("words", []):
                    wt = str(w.get("word", "")).strip()
                    if not wt:
                        continue
                    ws = float(w.get("start", 0.0))
                    we = float(w.get("end", ws + 0.1))
                    we = max(we, ws + 0.05)
                    all_words.append({"word": wt, "start": ws, "end": we})

        if not all_words:
            log.warn("Whisper: no words detected — subtitles skipped.")
            return None

        # Shift timestamps by custom audio timeline offset
        if ca_offset > 0.005:
            for w in all_words:
                w["start"] = round(w["start"] + ca_offset, 3)
                w["end"]   = round(w["end"] + ca_offset, 3)

        srt_p = clip.with_suffix(".srt")
        srt_p.parent.mkdir(parents=True, exist_ok=True)

        # ── Always save .words.json for millisecond-accurate karaoke & word pop ───
        words_p = clip.with_suffix(".words.json")
        try:
            words_p.parent.mkdir(parents=True, exist_ok=True)
            with open(words_p, "w", encoding="utf-8") as f:
                _json.dump(all_words, f, ensure_ascii=False, indent=2)
            try:
                log.ok(f"Word timestamps -> {words_p.name} ({len(all_words)} words)")
            except Exception:
                pass
        except Exception as _we_err:
            log.warn(f"Could not save .words.json: {_we_err}")

        # ── Write phrase-grouped SRT (CapCut-style: ≤4 words / ≤2.5 s) ──────
        MAX_WORDS = 4
        MAX_DUR   = 2.5
        with open(srt_p, "w", encoding="utf-8") as f:
            cue_idx  = 1
            i        = 0
            n        = len(all_words)
            while i < n:
                group: list[dict] = []
                while i < n:
                    w = all_words[i]
                    if group and (
                        len(group) >= MAX_WORDS or
                        w["end"] - group[0]["start"] > MAX_DUR
                    ):
                        break
                    group.append(w)
                    i += 1
                if not group:
                    break
                text = " ".join(ww["word"] for ww in group).strip()
                f.write(f"{cue_idx}\n")
                f.write(f"{_fmt(group[0]['start'])} --> {_fmt(group[-1]['end'])}\n")
                f.write(f"{text}\n\n")
                cue_idx += 1

        engine_name = "Stable Whisper" if STABLE_WHISPER_AVAILABLE else "Whisper"
        try:
            log.ok(f"Subtitles ({engine_name} small) -> {srt_p.name} ({cue_idx - 1} cues, {len(all_words)} words)")
        except Exception:
            pass
        return srt_p

    except Exception as exc:
        log.error(f"Whisper failed: {exc}")
        return None
    finally:
        # VRAM & RAM Memory Cleanup
        try:
            del model
        except Exception:
            pass
        if wav_path:
            try: wav_path.unlink(missing_ok=True)
            except Exception: pass
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass



def _parse_srt(srt_path: Path) -> list[dict]:
    """Parse SRT file → list of {start, end, text} in seconds."""
    import re as _re
    cues = []
    content = srt_path.read_text(encoding="utf-8", errors="replace")
    # Match SRT blocks: index, timestamps, text, blank line
    pattern = _re.compile(
        r"\d+\s*\n"
        r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n"
        r"([\s\S]*?)(?:\n\n|\Z)",
        _re.MULTILINE,
    )
    def _ts(s: str) -> float:
        s = s.replace(",", ".")
        h, m, rest = s.split(":")
        return int(h)*3600 + int(m)*60 + float(rest)

    for m in pattern.finditer(content):
        text = m.group(3).strip().replace("\n", " ")
        if text:
            cues.append({"start": _ts(m.group(1)),
                         "end":   _ts(m.group(2)),
                         "text":  text})
    return cues


def _sanitize_cues(cues: list[dict]) -> list[dict]:
    """Sort cues by start time and eliminate overlapping/invalid entries.

    ROOT FIX for 'multiple subtitle lines appearing simultaneously':
    Overlapping ASS Dialogue entries (caused by overlapping SRT timestamps
    from Gemini/Whisper output) make libass render multiple lines at once.
    This guarantees all Dialogue entries in the resulting ASS are strictly
    sequential and non-overlapping.
    """
    if not cues:
        return cues

    # 1. Sort by start time
    cues = sorted(cues, key=lambda c: c["start"])

    result: list[dict] = []
    for i, c in enumerate(cues):
        start = float(c["start"])
        end   = float(c["end"])

        # 2. Clamp end to next cue's start — prevents timeline overlap
        if i + 1 < len(cues):
            next_start = float(cues[i + 1]["start"])
            if end > next_start:
                end = next_start

        # 3. Skip degenerate cues (< 20 ms = transcriber noise)
        if end < start + 0.02:
            continue

        # 4. Cap very long cues so text doesn't hang on screen
        if end - start > 8.0:
            end = start + 8.0

        result.append({"start": start, "end": end, "text": c["text"]})

    return result


def _embed_font_in_ass(ass_content: str, font_key: str) -> str:
    """Embed a bundled TTF font as base64 in the ASS [Fonts] section.

    libass extracts the font family name from the embedded TTF data and uses it
    for rendering — no external paths or Windows GDI registration needed.
    Only bundled (non-system) fonts are embedded; system fonts are already
    available to libass through normal font discovery.
    """
    import base64 as _b64
    _BUNDLED_MAP: dict[str, Path] = {
        "montserrat":      FONTS_DIR / "Montserrat-Bold.ttf",
        "luckiestguy":     FONTS_DIR / "LuckiestGuy-Regular.ttf",
        "nunito":          FONTS_DIR / "Nunito-ExtraBold.ttf",
        "permanentmarker": FONTS_DIR / "PermanentMarker-Regular.ttf",
    }
    fp = _BUNDLED_MAP.get(font_key)
    if not fp or not fp.exists():
        return ass_content  # System font — no embedding needed

    encoded = _b64.b64encode(fp.read_bytes()).decode("ascii")
    # ASS spec: split encoded data into lines of max 80 chars
    lines = [encoded[i:i+80] for i in range(0, len(encoded), 80)]
    fonts_block = "[Fonts]\nfontname: " + fp.stem + "\n" + "\n".join(lines) + "\n\n"

    # Insert the [Fonts] section immediately before [Events]
    return ass_content.replace("[Events]\n", fonts_block + "[Events]\n", 1)


def _burn_subtitles_pass(src: Path, srt_path: Path, st: dict,
                         log: ToolLogger, progress_cb=None,
                         render_cfg: Optional[dict] = None,
                         words_json_path: Optional[Path] = None,
                         orig_clip: Optional[Path] = None) -> Path:
    """Second-pass subtitle burn-in — supports Normal, Word Pop, Highlight Line.

    Normal:         phrase cues, white text centred, libass smart wrap.
    Word Pop:       each word pops centred as spoken with acoustic timing from .words.json.
    Highlight Line: full phrase visible, spoken word highlighted in accent colour (karaoke).
    """
    import tempfile as _tmp, shutil as _sh, json as _json

    sub_style    = st.get("sub_style", "Normal")
    hl_color_hex = st.get("sub_highlight_color", "#FFD700")
    fontsize      = max(24, int(st.get("sub_font_size", 36)))
    _sub_margin_v = max(20, int(st.get("sub_margin_v", 200)))
    _sub_x        = int(st.get("sub_x", 0))
    _sub_pos      = f"{{\\pos({540 + _sub_x},{1920 - _sub_margin_v})}}"

    y_expr        = f"h-{_sub_margin_v}-(text_h/2)"

    # Subtitle timing offset — corrects systematic Gemini early-bias or any
    # A/V sync drift introduced during clip re-encoding.  User-adjustable.
    _offset_s = float(st.get("sub_offset_ms", 0)) / 1000.0

    # ── Sub font resolution ───────────────────────────────────────────────
    # sub_font_name maps to ASS Fontname (must match font family name registered
    # with Windows GDI — libass resolves fonts by GDI name, not file path).
    _SUB_FONT_MAP: dict[str, str] = {
        "arialbd":         "Arial Bold",
        "arial":           "Arial",
        "impact":          "Impact",
        "bebas":           "Bebas Neue",
        "anton":           "Anton",
        "ariblk":          "Arial Black",
        "gothicb":         "Century Gothic",
        "verdanab":        "Verdana Bold",
        # Bundled fonts — family names verified via fontTools from actual TTF name table
        "montserrat":      "Montserrat",
        "luckiestguy":     "Luckiest Guy",
        "nunito":          "Nunito Light",   # TTF reports family as "Nunito Light" not "Nunito"
        "permanentmarker": "Permanent Marker",
    }
    _sub_fn_key = st.get("sub_font_name", "arialbd")
    _sub_ass_fontname = _SUB_FONT_MAP.get(_sub_fn_key, "Arial Bold")
    _sub_uppercase    = bool(st.get("sub_uppercase", False))
    _sub_bold_val     = -1 if st.get("sub_bold", True)  else 0   # ASS: -1=bold, 0=normal
    _sub_italic_val   =  -1 if st.get("sub_italic", False) else 0

    # Ensure bundled fonts are installed in the Windows per-user Fonts directory
    # so libass can resolve them by family name (e.g. "Luckiest Guy", "Montserrat").
    _BUNDLED_KEYS = {"montserrat", "luckiestguy", "nunito", "permanentmarker"}
    if _sub_fn_key in _BUNDLED_KEYS:
        _ensure_bundled_fonts_installed()

    # Font file for drawtext (Windows needs explicit path)
    font_arg = ""
    for _f in ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"]:
        if Path(_f).exists():
            font_arg = "fontfile='" + _f[0] + "\\:" + _f[2:] + "':"
            break

    def _esc(t: str) -> str:
        return (t.replace("\\", "\\\\")
                 .replace("'",  "\u2019")
                 .replace(":",  "\\:")
                 .replace("%",  "\\%"))[:200]

    def _hex_to_ffmpeg_color(h: str) -> str:
        """#RRGGBB → 0xRRGGBB (FFmpeg colour syntax)."""
        h = h.lstrip("#")
        return f"0x{h.upper()}" if len(h) == 6 else "0xFFD700"

    hl_ffcol = _hex_to_ffmpeg_color(hl_color_hex)

    # Check libass availability — the `subtitles=` filter requires it.
    try:
        import subprocess as _sp2
        _probe = _sp2.run(
            [FFMPEG, "-filters"],
            capture_output=True, text=True, timeout=10
        )
        if "subtitles" not in _probe.stdout:
            log.warn(
                "⚠️  FFmpeg build does NOT support the 'subtitles' filter (libass missing). "
                "Subtitle burn will be skipped. Re-install FFmpeg with libass support "
                "or use the bundled build that ships with libass."
            )
            return src
    except Exception as _pe:
        log.warn(f"⚠️  Could not probe FFmpeg filters: {_pe}")

    # Load phrase cues from SRT and sanitize (sort + de-overlap)
    srt_cues = _sanitize_cues(_parse_srt(srt_path))
    if not srt_cues:
        log.warn("SRT has no valid cues after sanitization — subtitle pass skipped.")
        return src

    # ── Try to locate and load acoustic word timestamps (.words.json) ─────────
    real_words: Optional[list[dict]] = None
    candidate_words_paths: list[Path] = []
    if words_json_path:
        candidate_words_paths.append(Path(words_json_path))
    if srt_path:
        candidate_words_paths.extend([
            srt_path.with_suffix(".words.json"),
            srt_path.parent / (srt_path.stem + ".words.json"),
            srt_path.parent.parent / "json" / (srt_path.stem.replace("_reup", "") + ".words.json"),
            srt_path.parent.parent / "json" / (srt_path.stem + ".words.json"),
            srt_path.parent / (srt_path.stem.replace("_reup", "") + ".words.json"),
        ])
    if orig_clip:
        candidate_words_paths.extend([
            orig_clip.with_suffix(".words.json"),
            orig_clip.parent / (orig_clip.stem + ".words.json"),
            orig_clip.parent.parent / "json" / (orig_clip.stem + ".words.json"),
        ])
    if src:
        candidate_words_paths.extend([
            src.with_suffix(".words.json"),
            src.parent / (src.stem + ".words.json"),
            src.parent.parent / "json" / (src.stem.replace("_reup", "") + ".words.json"),
        ])

    for cp in candidate_words_paths:
        if cp.exists() and cp.is_file():
            try:
                loaded = _json.loads(cp.read_text(encoding="utf-8"))
                if isinstance(loaded, list) and loaded and isinstance(loaded[0], dict) and "word" in loaded[0]:
                    real_words = [
                        {
                            "word": str(w.get("word", "")).strip(),
                            "start": float(w.get("start", 0)),
                            "end": float(w.get("end", 0))
                        }
                        for w in loaded if str(w.get("word", "")).strip()
                    ]
                    log.info(f"Loaded {len(real_words)} acoustic word timestamps from {cp.name}")
                    break
            except Exception as _e_load:
                log.warn(f"Could not load words from {cp}: {_e_load}")

    def _rgb_to_ass(hex_color: str, alpha: int = 0) -> str:
        """#RRGGBB → &HAABBGGRR. alpha: 0x00=opaque, 0xFF=transparent."""
        h = hex_color.lstrip("#")
        try:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except Exception:
            r, g, b = 255, 215, 0
        return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"

    def _to_ass_ts(secs: float) -> str:
        """Float seconds → ASS timestamp H:MM:SS.cc"""
        h_  = int(secs // 3600)
        m_  = int((secs % 3600) // 60)
        s_  = secs % 60
        cs_ = int(round((s_ % 1) * 100))
        return f"{h_}:{m_:02d}:{int(s_):02d}.{cs_:02d}"

    def _esc_ass(t: str) -> str:
        return t.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")

    _dim_hex = st.get("sub_dim_color", "#FFFFFF")
    dim_clr = _rgb_to_ass(_dim_hex, alpha=0x00)
    hl_clr  = _rgb_to_ass(hl_color_hex)

    # CapCut-style opaque background box (BorderStyle=4 in libass)
    _sub_bg_box     = bool(st.get("sub_bg_box", False))
    _sub_bg_box_hex = st.get("sub_bg_box_color", "#000000")
    _sub_bg_opacity = max(0, min(100, int(st.get("sub_bg_box_opacity", 80))))
    _sub_bg_alpha   = max(0, 255 - round(_sub_bg_opacity / 100 * 255))
    _sub_back_clr   = _rgb_to_ass(_sub_bg_box_hex, alpha=_sub_bg_alpha) if _sub_bg_box else "&HA0000000"
    _border_style   = 3 if _sub_bg_box else 1
    _outline_val    = 0 if _sub_bg_box else 3
    _shadow_val     = 0 if _sub_bg_box else 1

    dt_parts: list[str] = []

    if sub_style in ("Word Pop", "Viral Bounce"):
        is_bounce = (sub_style == "Viral Bounce")
        if real_words:
            log.info(f"🎤 {'Viral Bounce' if is_bounce else 'Word Pop'} mode (Acoustic timestamps from .words.json) — {len(real_words)} words")
            words = real_words
        else:
            log.info(f"🎤 {'Viral Bounce' if is_bounce else 'Word Pop'} mode (interpolated cues) — {len(srt_cues)} phrase cues")
            words = _build_anchored_words_from_cues(srt_cues)

        _cur_outline = max(4, _outline_val) if is_bounce else _outline_val
        _cur_shadow  = max(2, _shadow_val) if is_bounce else _shadow_val

        ass_buf = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
            "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
            "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
            "Alignment,MarginL,MarginR,MarginV,Encoding",
            f"Style: WordPop,{_sub_ass_fontname},{fontsize},{hl_clr},{hl_clr},"
            f"&H00000000,{_sub_back_clr},{_sub_bold_val},{_sub_italic_val},0,0,100,100,0,0,{_border_style},{_cur_outline},{_cur_shadow},2,"
            f"80,80,{_sub_margin_v},0",
            "",
            "[Events]",
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
        ]
        for idx_w, w in enumerate(words):
            wt = _esc_ass(w["word"].upper() if _sub_uppercase else w["word"])
            ws = max(0.0, w["start"] + _offset_s)
            we = max(ws + 0.05, w["end"] + _offset_s)
            # Smooth transition between rapid consecutive words
            if idx_w < len(words) - 1:
                next_ws = max(0.0, words[idx_w + 1]["start"] + _offset_s)
                if next_ws > we and (next_ws - we) <= 0.25:
                    we = next_ws
            # Viral Bounce: dynamic scale-up pop transform tag (118% -> 100%) for instant punchiness
            bounce_tag = r"{\t(0,70,\fscx118\fscy118)\t(70,140,\fscx100\fscy100)}" if is_bounce else ""
            ass_buf.append(
                f"Dialogue: 0,{_to_ass_ts(ws)},{_to_ass_ts(we)},WordPop,,0,0,0,,{_sub_pos}{bounce_tag}{wt}"
            )

        ass_content = _embed_font_in_ass("\n".join(ass_buf) + "\n", _sub_fn_key)
        _safe_stem = re.sub(r"[^A-Za-z0-9._\-]", "_", src.stem[:30])
        _uid = uuid.uuid4().hex[:8]
        ass_path = Path(_tmp.gettempdir()) / f"wordpop_{_uid}_{_safe_stem}.ass"
        Path(ass_path).write_text(ass_content, encoding="utf-8-sig")

        ass_esc = str(ass_path).replace("\\", "/").replace(":", "\\:")
        dt_parts.append(f"subtitles='{ass_esc}'")

    elif sub_style == "Highlight Line":
        if real_words:
            log.info(f"✨ Highlight Line mode (Acoustic ASS Karaoke with .words.json) — {len(real_words)} words")
        else:
            log.info(f"✨ Highlight Line mode (Phrase-Anchored ASS Karaoke) — {len(srt_cues)} phrase lines")

        ass_buf = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "WrapStyle: 1",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
            "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
            "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
            "Alignment,MarginL,MarginR,MarginV,Encoding",
            f"Style: Karaoke,{_sub_ass_fontname},{fontsize},{hl_clr},{dim_clr},"
            f"&H00000000,{_sub_back_clr},{_sub_bold_val},{_sub_italic_val},0,0,100,100,0,0,{_border_style},{_outline_val},{_shadow_val},2,"
            f"80,80,{_sub_margin_v},0",
            "",
            "[Events]",
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
        ]

        MAX_WORDS_PER_LINE = 5  # max words shown at once on screen

        for cue in srt_cues:
            c_start = max(0.0, cue["start"] + _offset_s)
            c_end   = max(0.0, cue["end"]   + _offset_s)
            if c_end <= c_start:
                continue

            if real_words:
                c_start_raw = cue["start"]
                c_end_raw   = cue["end"]
                cue_words = [
                    w for w in real_words
                    if (c_start_raw - 0.25) <= ((w["start"] + w["end"]) / 2.0) <= (c_end_raw + 0.25)
                ]
                if not cue_words:
                    cue_words = _build_anchored_words_from_cues([cue])
            else:
                cue_words = _build_anchored_words_from_cues([cue])

            if not cue_words:
                continue

            # Split long cue into ≤5-word sub-groups
            sub_groups: list[list[dict]] = [
                cue_words[i:i + MAX_WORDS_PER_LINE]
                for i in range(0, len(cue_words), MAX_WORDS_PER_LINE)
            ]
            n_grps = len(sub_groups)

            for gi, grp in enumerate(sub_groups):
                if not grp:
                    continue

                if real_words:
                    w_first_s = max(0.0, grp[0]["start"] + _offset_s)
                    w_last_e  = max(w_first_s + 0.05, grp[-1]["end"] + _offset_s)

                    if gi == 0:
                        grp_start = min(w_first_s, c_start)
                    else:
                        grp_start = w_first_s

                    if gi < n_grps - 1:
                        next_first_s = max(0.0, sub_groups[gi + 1][0]["start"] + _offset_s)
                        grp_end = min(next_first_s, max(w_last_e, next_first_s - 0.05))
                    else:
                        grp_end = max(w_last_e, c_end)

                    grp_end = max(grp_start + 0.1, grp_end)
                else:
                    cue_dur  = c_end - c_start
                    slot_dur = cue_dur / n_grps
                    grp_start = c_start + gi       * slot_dur
                    grp_end   = c_start + (gi + 1) * slot_dur

                parts = []
                first_w_s = max(grp_start, min(grp[0]["start"] + _offset_s, grp_end))
                pre_gap_cs = max(0, int(round((first_w_s - grp_start) * 100)))
                if pre_gap_cs > 0:
                    parts.append(f"{{\\k{pre_gap_cs}}}")

                for i, w in enumerate(grp):
                    wt = _esc_ass(w["word"].upper() if _sub_uppercase else w["word"])
                    w_s = max(grp_start, min(w["start"] + _offset_s, grp_end))
                    if i < len(grp) - 1:
                        w_next_s = max(w_s, min(grp[i+1]["start"] + _offset_s, grp_end))
                        dur_cs   = max(1, int(round((w_next_s - w_s) * 100)))
                        parts.append(f"{{\\k{dur_cs}}}{wt} ")
                    else:
                        dur_cs = max(1, int(round((grp_end - w_s) * 100)))
                        parts.append(f"{{\\k{dur_cs}}}{wt}")

                ass_buf.append(
                    f"Dialogue: 0,{_to_ass_ts(grp_start)},{_to_ass_ts(grp_end)},"
                    f"Karaoke,,0,0,0,,{_sub_pos}{''.join(parts)}"
                )

        ass_content = _embed_font_in_ass("\n".join(ass_buf) + "\n", _sub_fn_key)
        _safe_stem = re.sub(r"[^A-Za-z0-9._\-]", "_", src.stem[:30])
        _uid = uuid.uuid4().hex[:8]
        ass_path = Path(_tmp.gettempdir()) / f"karaoke_{_uid}_{_safe_stem}.ass"
        Path(ass_path).write_text(ass_content, encoding="utf-8-sig")
        log.info(f"📄  ASS Karaoke file: {ass_path}  ({len(ass_buf) - 13} dialogue lines)")

        ass_esc = str(ass_path).replace("\\", "/").replace(":", "\\:")
        dt_parts.append(f"subtitles='{ass_esc}'")




    else:
        # Normal mode — phrase cues from SRT → rendered via ASS/libass so that
        # long lines wrap automatically (WrapStyle: 1 = smart end-of-line wrap).
        # The old drawtext approach had no wrapping, causing text to overflow.
        cues = _sanitize_cues(_parse_srt(srt_path))
        if not cues:
            log.warn("SRT has no cues — subtitle pass skipped.")
            return src
        log.info(f"🔤  Burning {len(cues)} subtitle cues (Normal, ASS wrap)…")

        def _to_ass_ts_n(secs: float) -> str:
            h_  = int(secs // 3600)
            m_  = int((secs % 3600) // 60)
            s_  = secs % 60
            cs_ = int(round((s_ % 1) * 100))
            return f"{h_}:{m_:02d}:{int(s_):02d}.{cs_:02d}"

        def _esc_ass_n(t: str) -> str:
            return t.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")

        # Normal text colour: use sub_dim_color if set, else default white
        _ntxt_hex = st.get("sub_dim_color", "#FFFFFF").lstrip("#")
        try:
            _nr, _ng, _nb = int(_ntxt_hex[0:2], 16), int(_ntxt_hex[2:4], 16), int(_ntxt_hex[4:6], 16)
            _norm_clr = f"&H00{_nb:02X}{_ng:02X}{_nr:02X}"
        except Exception:
            _norm_clr = "&H00FFFFFF"

        _normal_ass: list[str] = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "WrapStyle: 1",           # ← smart word-wrap; prevents overflow
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
            "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
            "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
            "Alignment,MarginL,MarginR,MarginV,Encoding",
            # Alignment=2 → bottom-centre; MarginL/R=80 gives 80px safe zone each side
            f"Style: Normal,{_sub_ass_fontname},{fontsize},{_norm_clr},{_norm_clr},"
            f"&H00000000,{_sub_back_clr},{_sub_bold_val},{_sub_italic_val},0,0,100,100,0,0,{_border_style},{_outline_val},{_shadow_val},2,"
            f"80,80,{_sub_margin_v},0",
            "",
            "[Events]",
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
        ]

        for cue in cues:
            s   = max(0.0, cue["start"] + _offset_s)
            e   = max(0.0, cue["end"]   + _offset_s)
            txt_raw = cue["text"].upper() if _sub_uppercase else cue["text"]
            txt = _esc_ass_n(txt_raw)
            _normal_ass.append(
                f"Dialogue: 0,{_to_ass_ts_n(s)},{_to_ass_ts_n(e)},"
                f"Normal,,0,0,0,,{_sub_pos}{txt}"
            )

        ass_content_n = _embed_font_in_ass("\n".join(_normal_ass) + "\n", _sub_fn_key)
        _safe_stem_n  = re.sub(r"[^A-Za-z0-9._\-]", "_", src.stem[:30])
        _uid_n        = uuid.uuid4().hex[:8]
        ass_path_n    = Path(_tmp.gettempdir()) / f"normal_sub_{_uid_n}_{_safe_stem_n}.ass"
        ass_path_n.write_text(ass_content_n, encoding="utf-8-sig")

        ass_esc_n = str(ass_path_n).replace("\\", "/").replace(":", "\\:")
        dt_parts.append(f"subtitles='{ass_esc_n}'")




    if not dt_parts:
        log.warn("No subtitle cues generated — skipping burn.")
        return src

    # Use script file to avoid Windows command line character limits (8191 chars)
    _uid_flt  = uuid.uuid4().hex[:8]
    _safe_flt = re.sub(r"[^A-Za-z0-9._\-]", "_", src.stem[:30])
    # IMPORTANT: normalize video PTS to t=0 before applying subtitles.
    # Some clips (especially bodycam footage re-encoded via cut_clip_exact) have a
    # non-zero video stream start_time (e.g. 0.12 s or even 1.5 s). FFmpeg's
    # `subtitles` filter keys off video PTS — so ASS t=5.0 appears when video
    # PTS=5.0.  But Gemini timestamps are relative to AUDIO t=0.  If video starts
    # at PTS=1.5 while audio starts at PTS=0, ASS t=5.0 appears 1.5 s late.
    # `setpts=PTS-STARTPTS` shifts all video PTS so the first frame is at t=0,
    # making the subtitle time-base identical to the audio time-base.
    vf_chain  = "[0:v]setpts=PTS-STARTPTS," + ",".join(dt_parts) + "[outv]"

    script_p  = Path(_tmp.gettempdir()) / f"reup_sub_flt_{_uid_flt}_{_safe_flt}.txt"
    script_p.write_text(vf_chain, encoding="utf-8")

    tmp_out = Path(_tmp.gettempdir()) / f"reup_sub_{_uid_flt}_{_safe_flt}.mp4"

    # Resolve encoder settings for subtitle pass — use same GPU encoder as main pass
    _rcfg     = render_cfg or {}
    _sub_vc   = _rcfg.get("vcodec", "libx264")
    _sub_crf  = int(_rcfg.get("crf", 20))
    _sub_pst  = _rcfg.get("preset", "fast")
    # Map CPU preset names → GPU equivalent (same logic as render_reup)
    _CPU_TO_NVENC_SUB = {"ultrafast": "p1", "superfast": "p1", "veryfast": "p2",
                         "faster": "p2", "fast": "p3", "medium": "p4",
                         "slow": "p5", "slower": "p6", "veryslow": "p7", "placebo": "p7"}
    if _sub_vc in {"h264_nvenc", "hevc_nvenc"}:
        _sub_pst = _CPU_TO_NVENC_SUB.get(_sub_pst, "p3")
        _sub_quality = ["-cq", str(_sub_crf)]
    elif _sub_vc in {"h264_qsv", "hevc_qsv"}:
        _sub_quality = ["-global_quality", str(_sub_crf)]
    elif _sub_vc in {"h264_amf", "hevc_amf"}:
        _sub_pst = "balanced"
        _sub_quality = ["-rc", "cqp", "-qp_i", str(_sub_crf), "-qp_p", str(_sub_crf)]
    else:
        _sub_quality = ["-crf", str(_sub_crf)]

    # subtitle filter outputs yuva → force yuv420p for GPU encoders that reject RGBA
    _sub_fc_prefix = ""
    if _sub_vc in {"h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv"}:
        _sub_fc_prefix = "format=yuv420p,"

    # Rewrite filter chain to add pix_fmt conversion if needed
    if _sub_fc_prefix:
        vf_chain = vf_chain.replace("[0:v]setpts=PTS-STARTPTS,",
                                    f"[0:v]setpts=PTS-STARTPTS,{_sub_fc_prefix}")
        script_p.write_text(vf_chain, encoding="utf-8")

    # BT.709 color tags: safe for CPU; skip for NVENC/QSV (some drivers reject them)
    _is_gpu_enc = _sub_vc not in {"libx264", "libx265", "h264_mf"}
    _color_tags = ([
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-colorspace", "bt709",
        "-color_range", "tv",
    ] if not _is_gpu_enc else [])

    cmd = [
        FFMPEG, "-y", "-i", str(src),
        "-filter_complex_script", str(script_p),
        "-map", "[outv]", "-map", "0:a?",
        "-c:v", _sub_vc, "-preset", _sub_pst, *_sub_quality,
        *_color_tags,
        "-c:a", "copy",
        "-map_metadata", "-1",
        "-map_metadata:s:v", "-1",
        "-map_metadata:s:a", "-1",
        "-movflags", "+faststart",
        str(tmp_out),
    ]

    dur = get_video_duration(src) or 0.0
    stderr_lines: list[str] = []

    def _read_err(proc):
        import re as _re2
        _tp = _re2.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
        for raw in proc.stderr:
            line = raw.rstrip()
            stderr_lines.append(line)
            if progress_cb and dur > 0:
                m = _tp.search(line)
                if m:
                    t = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
                    progress_cb(0.5 + min(t / dur, 0.49))

    import threading as _thr
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace")
        _t = _thr.Thread(target=_read_err, args=(proc,), daemon=True)
        _t.start()
        proc.wait(timeout=600)
        _t.join(timeout=5)

        if proc.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 512:
            import shutil as _sh
            _sh.move(str(tmp_out), str(src))
            log.ok(f"✅  Subtitles burned ({sub_style}) → {src.name}")
            return src
        else:
            # Verbose failure — surface the full FFmpeg stderr so user can diagnose
            stderr_tail = "\n".join(stderr_lines[-20:])
            log.warn(
                f"⚠️  Subtitle burn FAILED (ffmpeg rc={proc.returncode}, style={sub_style}).\n"
                f"Video exported WITHOUT subtitles.\n"
                f"--- FFmpeg stderr (last 20 lines) ---\n{stderr_tail}\n"
                f"ASS file: {ass_path if 'ass_path' in dir() else 'N/A'}"
            )
            try: tmp_out.unlink(missing_ok=True)
            except Exception: pass
            return src
    except Exception as exc:
        log.warn(
            f"⚠️  Subtitle burn error ({sub_style}): {exc}\n"
            f"Video exported WITHOUT subtitles."
        )
        try: tmp_out.unlink(missing_ok=True)
        except Exception: pass
        return src
    finally:
        try: script_p.unlink(missing_ok=True)
        except Exception: pass


def _run_ffmpeg_render(
    cmd: list,
    stop_event,
    n_blur: int,
    vid_dur_secs: float,
    progress_cb,
    title_img: "Path | None",
    log: "ToolLogger",
    stderr_out: "list[str] | None" = None,
) -> int:
    """Run an FFmpeg render command with cancellation, timeout, and progress reporting.

    Parses ``time=HH:MM:SS.ms`` from stderr to drive *progress_cb* (0.0 → 1.0).
    Cleans up *title_img* temp file on exit regardless of outcome.

    Returns the FFmpeg process return-code.
    Raises:
        InterruptedError: if *stop_event* is set while FFmpeg is running.
        RuntimeError:     if the render exceeds the dynamic timeout.
    """
    stderr_lines: list[str] = []

    def _read_stderr(proc):
        import re as _re
        _tp = _re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
        for raw in proc.stderr:
            line = raw.rstrip()
            stderr_lines.append(line)
            if stderr_out is not None:
                stderr_out.append(line)
            if progress_cb and vid_dur_secs > 0:
                m = _tp.search(line)
                if m:
                    t = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
                    progress_cb(min(t / vid_dur_secs, 0.99))

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
        import threading as _thr
        _st = _thr.Thread(target=_read_stderr, args=(proc,), daemon=True)
        _st.start()

        # Dynamic timeout: scale with duration and blur boxes.
        # With single-blur-stream optimization, even 30+ blur boxes render in seconds,
        # but ensure a generous minimum of 30 min (1800s) to prevent any premature timeout.
        timeout_secs = max(1800, min(3600, 1200 + int(vid_dur_secs * 10) + (n_blur // 5) * 60))
        deadline = time.time() + timeout_secs
        while proc.poll() is None:
            if stop_event is not None and stop_event.is_set():
                proc.kill()
                raise InterruptedError("Render cancelled by user.")
            if time.time() > deadline:
                proc.kill()
                raise RuntimeError(
                    f"FFmpeg render timed out (blur_boxes={n_blur}, "
                    f"timeout={timeout_secs // 60}min). "
                    "Reduce blur boxes or use GPU encoder."
                )
            time.sleep(0.3)
        _st.join(timeout=5)
        return proc.returncode
    finally:
        # title_img here is always a PIL-generated temp file (None when browser overlay is used)
        if title_img:
            try:
                title_img.unlink(missing_ok=True)
            except Exception:
                pass




def render_reup(clip: Path, dst: Path, title: str,
                color_grade: bool, srt_path: Optional[Path],
                log: ToolLogger,
                edit_state: Optional[dict] = None,
                render_cfg: Optional[dict] = None,
                progress_cb=None,
                stop_event=None,
                title_overlay_path: Optional[Path] = None,
                words_json_path: Optional[Path] = None) -> Path:
    """Render a portrait video ready for TikTok/Reels/Shorts.
    When edit_state is provided (from Tab 2 editor), its values override defaults.
    When render_cfg is provided, encoding parameters (resolution, encoder, fps…)
    override the built-in defaults.

    Layout:
      • Blurred, cropped background fills the full frame
      • Original footage scaled to frame width, centered vertically
      • Title card (PNG from PIL) overlaid at the top
      • Optional: cinematic colour grade on the foreground layer
      • Optional: subtitles burned at 200 px from the bottom
    """
    st = edit_state or {}
    effective_grade = st.get("color_grade", color_grade)
    video_x_offset  = int(st.get("video_x", 0))
    video_y_offset  = int(st.get("video_y", 0))

    # ── Encoding configuration (from Export Settings panel) ──────────────────
    rcfg   = render_cfg or {}
    W      = int(rcfg.get("width",   REUP_W))
    H      = int(rcfg.get("height",  REUP_H))
    vcodec = rcfg.get("vcodec",  "libx264")
    acodec = rcfg.get("acodec",  "aac")
    crf    = int(rcfg.get("crf",    20))
    preset = rcfg.get("preset",  "fast")
    fps    = rcfg.get("fps",     None)   # None = keep source FPS

    # NVENC/QSV use different preset names — map CPU preset → GPU equivalent
    # CPU:   ultrafast | fast | medium | slow
    # NVENC: p1(fastest)…p7(slowest)  — p4=balanced, p1=fastest/streaming
    _CPU_TO_NVENC = {"ultrafast": "p1", "superfast": "p1", "veryfast": "p2",
                     "faster": "p2", "fast": "p3", "medium": "p4",
                     "slow": "p5", "slower": "p6", "veryslow": "p7",
                     "placebo": "p7"}
    _CPU_TO_QSV   = {"ultrafast": "veryfast", "superfast": "veryfast",
                     "veryfast": "veryfast", "faster": "faster",
                     "fast": "fast", "medium": "medium",
                     "slow": "slow", "slower": "slower",
                     "veryslow": "veryslow", "placebo": "veryslow"}
    if vcodec in {"h264_nvenc", "hevc_nvenc"}:
        preset = _CPU_TO_NVENC.get(preset, "p4")  # default to balanced
        _quality_flag = ["-cq", str(crf)]
    elif vcodec in {"h264_qsv", "hevc_qsv"}:
        preset = _CPU_TO_QSV.get(preset, "medium")
        _quality_flag = ["-global_quality", str(crf)]
    elif vcodec in {"h264_amf", "hevc_amf"}:
        preset = "balanced"  # AMF uses: quality | balanced | speed
        _quality_flag = ["-rc", "cqp", "-qp_i", str(crf), "-qp_p", str(crf)]
    else:
        _quality_flag = ["-crf", str(crf)]

    log.info(f"📱 Rendering reup → {dst.name}")
    dst.parent.mkdir(parents=True, exist_ok=True)

    # ── Build filter_complex incrementally ───────────────────────────────────

    # Source-mask / 4-edge crop fractions: top (cpt), bottom (cpb), left (cpl), right (cpr)
    cpt = max(0.0, min(0.48, float(st.get("crop_top",    st.get("source_mask_top",    0.0)))))
    cpb = max(0.0, min(0.48, float(st.get("crop_bottom", st.get("source_mask_bottom", 0.0)))))
    cpl = max(0.0, min(0.48, float(st.get("crop_left",   0.0))))
    cpr = max(0.0, min(0.48, float(st.get("crop_right",  0.0))))
    if cpt + cpb > 0.96:
        cpb = max(0.0, 0.96 - cpt)
    if cpl + cpr > 0.96:
        cpr = max(0.0, 0.96 - cpl)
    rem_h = max(0.04, 1.0 - cpt - cpb)
    rem_w = max(0.04, 1.0 - cpl - cpr)

    bg_type       = st.get("bg_type", "blur")
    bg_image_path = st.get("bg_image_path", "")
    bg_video_path = st.get("bg_video_path", "")

    inputs = [FFMPEG, "-y", "-thread_queue_size", "512", *_gpu_decode_flags(), "-i", str(clip)]
    inp_idx = 1

    # ── Background layer ─────────────────────────────────────────────────────
    # Three modes: blurred source (default), static image, looping video.
    # -shortest / -t ensures FFmpeg stops when the SHORTEST input ends (= main video)
    # without it, -loop 1 on an image or -stream_loop -1 on a video would run forever.
    use_shortest = False
    _VID_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".ts", ".m4v", ".flv", ".wmv"}
    _IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}

    _effective_bg_path = None
    _is_bg_video = False

    if bg_type == "image" and bg_image_path and Path(bg_image_path).exists():
        _effective_bg_path = bg_image_path
        _is_bg_video = Path(bg_image_path).suffix.lower() in _VID_EXTS
    elif bg_type == "video" and bg_video_path and Path(bg_video_path).exists():
        _effective_bg_path = bg_video_path
        _is_bg_video = Path(bg_video_path).suffix.lower() not in _IMG_EXTS
    elif bg_image_path and Path(bg_image_path).exists():
        _effective_bg_path = bg_image_path
        _is_bg_video = Path(bg_image_path).suffix.lower() in _VID_EXTS
    elif bg_video_path and Path(bg_video_path).exists():
        _effective_bg_path = bg_video_path
        _is_bg_video = Path(bg_video_path).suffix.lower() not in _IMG_EXTS

    if _effective_bg_path:
        if _is_bg_video:
            inputs += ["-thread_queue_size", "512", "-stream_loop", "-1", "-i", str(_effective_bg_path)]
        else:
            inputs += ["-thread_queue_size", "512", "-loop", "1", "-i", str(_effective_bg_path)]
        bg_filter = (
            f"[{inp_idx}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1[bg]"
        )
        inp_idx += 1
        use_shortest = True   # loop has infinite duration; need -shortest / -t
    else:
        # Default: blurred source video as background
        if cpt > 0 or cpb > 0 or cpl > 0 or cpr > 0:
            bg_filter = (
                f"[0:v]crop=in_w*(1-{cpl:.4f}-{cpr:.4f}):in_h*(1-{cpt:.4f}-{cpb:.4f}):in_w*{cpl:.4f}:in_h*{cpt:.4f},"
                f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},boxblur=luma_radius=25:luma_power=5:chroma_radius=12:chroma_power=5[bg]"
            )
        else:
            bg_filter = (
                f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},boxblur=luma_radius=25:luma_power=5:chroma_radius=12:chroma_power=5[bg]"
            )

    # ── Copyright evasion transforms applied to fg ───────────────────────────
    # Flip (most effective evasion — changes video hash completely)
    vw_scale = float(st.get("video_w_scale", 1.0))
    vh_scale = float(st.get("video_h_scale", 1.0))

    fg_stages = []
    if st.get("smart_zoom", False):
        fg_stages.append("crop=0.98*iw:0.98*ih")
    fg_stages.append(f"scale='trunc({W}*{vw_scale}/2)*2':'trunc({W}*(ih/iw)*{vh_scale}/2)*2'")
    if effective_grade:
        fg_stages.append("eq=contrast=1.08:saturation=1.18:brightness=0.02")
        fg_stages.append("unsharp=5:5:0.6:5:5:0")
    if cpt > 0 or cpb > 0 or cpl > 0 or cpr > 0:
        fg_stages.append(f"crop='iw*{rem_w:.4f}':'ih*{rem_h:.4f}':'iw*{cpl:.4f}':'ih*{cpt:.4f}'")
    if st.get("flip_h", False):
        fg_stages.append("hflip")
    if st.get("flip_v", False):
        fg_stages.append("vflip")
    if st.get("micro_rotate", False):
        fg_stages.append("rotate=1.2*PI/180:ow=iw:oh=ih:c=black@0")

    hue_shift = int(st.get("hue_shift", 0))
    sat       = float(st.get("saturation", 1.0))
    if hue_shift != 0 or abs(sat - 1.0) > 0.01:
        fg_stages.append(f"hue=h={hue_shift}:s={sat:.3f}")
    if st.get("vignette", False):
        # Soft Gaussian vignette — mirrors the CV2 preview formula in server.py exactly.
        # vignette_strength (5–100) controls σ: smaller → tighter bright center → darker corners.
        _vs  = max(5, min(100, int(st.get("vignette_strength", 50))))
        _sig = 0.80 - (_vs / 100.0) * 0.51  # maps 5→0.7745, 50→0.5450, 100→0.29
        # geq mask = gaussian_2d^amp, clamped to [min_lum, 1.0].
        # The pow exponent flattens the center so it stays bright.
        _amp     = round(1.0 + (_vs / 100.0) * 0.5, 3)
        _min_lum = round(max(0.0, 1.0 - (_vs / 100.0) * 0.75), 3)
        # σ_x = W*_sig/2, σ_y = H*_sig/2 to match getGaussianKernel(cols, cols*_sig)
        _sx = f"W*{_sig:.4f}/2"
        _sy = f"H*{_sig:.4f}/2"
        _gauss = (
            f"exp(-((X-W/2)*(X-W/2))/(2*({_sx})*({_sx})))"
            f"*exp(-((Y-H/2)*(Y-H/2))/(2*({_sy})*({_sy})))"
        )
        _vig = (
            "geq="
            f"lum='clip(lum(X\\,Y)*"
            f"pow({_gauss},{_amp})"
            f"*{1.0 + (_vs / 100.0) * 0.5:.3f}"  # amp factor matching _amp in CV2
            f"/1.0"  # normalise: max of gaussian_2d at center = 1.0
            f",{_min_lum}*lum(X\\,Y),255)':"
            "cb='cb(X,Y)':"
            "cr='cr(X,Y)'"
        )
        fg_stages.append(_vig)


    if st.get("add_grain", False):
        grain_s = max(1, min(10, int(st.get("grain_strength", 3))))
        fg_stages.append(f"noise=alls={grain_s}:allf=t+u")

    fg_filter = f"[0:v]{','.join(fg_stages)}[fg]"

    vx_expr = f"+({video_x_offset})" if video_x_offset else ""
    vy_expr = f"+({video_y_offset})" if video_y_offset else ""
    if cpt > 0 or cpb > 0 or cpl > 0 or cpr > 0:
        comp = (
            f"[bg][fg]overlay=((W-w/{rem_w:.4f})/2{vx_expr}+w*{cpl/rem_w:.4f}):"
            f"((H-h/{rem_h:.4f})/2{vy_expr}+h*{cpt/rem_h:.4f})[comp0]"
        )
    else:
        comp = f"[bg][fg]overlay=((W-w)/2{vx_expr}):((H-h)/2{vy_expr})[comp0]"


    parts   = [bg_filter, fg_filter, comp]
    current = "comp0"

    # ── 1. Blur / Delogo boxes (watermark / logo concealment on source video) ─
    # MUST be applied directly to video BEFORE stickers, title, and subtitles!
    # Layer order: Video -> Blur -> Stickers -> Title -> Watermark -> Subtitles
    valid_blur_boxes = []
    delogo_boxes = []
    for _bi, _box in enumerate(st.get("blur_boxes", [])):
        if _box.get("tracked"):
            continue  # SKIP tracked boxes in static pass — they are applied in Pass 3!
        if _box.get("video_rel"):
            # v2: video-local fractions — convert to output-frame pixels using fg geometry
            _vw_src = int(_box.get("_vw", 1920))
            _vh_src = int(_box.get("_vh", 1080))
            _fg_w = int(round(W * vw_scale / 2) * 2)
            _fg_h = int(round(W * (_vh_src / _vw_src) * vh_scale / 2) * 2)
            _fg_x = (W - _fg_w) // 2 + video_x_offset
            _fg_y = (H - _fg_h) // 2 + video_y_offset
            _bx = max(0, int(_fg_x + _box.get("x", 0) * _fg_w))
            _by = max(0, int(_fg_y + _box.get("y", 0) * _fg_h))
            _bw = max(2, int(_box.get("w", 0.1) * _fg_w))
            _bh = max(2, int(_box.get("h", 0.1) * _fg_h))
        else:
            # v1 legacy: direct 1080×1920 output-frame pixels
            _bx = max(0, int(_box.get("x", 0)))
            _by = max(0, int(_box.get("y", 0)))
            _bw = max(2, int(_box.get("w", 100)))
            _bh = max(2, int(_box.get("h", 100)))
        # Clamp to frame dimensions — out-of-bounds crop kills FFmpeg
        _bw = min(_bw, W - _bx)
        _bh = min(_bh, H - _by)
        if _bw < 2 or _bh < 2:
            continue  # skip degenerate / fully-out-of-bounds boxes

        _mode     = _box.get("mode", "blur")
        _st_time  = float(_box.get("start_time", 0.0) or 0.0)
        _end_time = float(_box.get("end_time", 0.0) or 0.0)

        # Enable expression for timed blurring/delogo
        _enable_expr = ""
        if _st_time > 0.05 or _end_time > 0.05:
            if _end_time > _st_time + 0.05:
                _enable_expr = f":enable='between(t,{_st_time:.3f},{_end_time:.3f})'"
            else:
                _enable_expr = f":enable='gte(t,{_st_time:.3f})'"

        if _mode == "delogo":
            # delogo inpaints the region using surrounding pixel interpolation.
            # Delogo requires a minimum 1px gap from all frame edges (strict bounds).
            _bx = max(2, _bx)
            _by = max(2, _by)
            _bw = min(_bw, W - _bx - 2)
            _bh = min(_bh, H - _by - 2)
            if _bw >= 2 and _bh >= 2:
                delogo_boxes.append((_bx, _by, _bw, _bh, _enable_expr))
        else:
            valid_blur_boxes.append((_bx, _by, _bw, _bh, _enable_expr))

    if valid_blur_boxes:
        # High-performance single-pass blur:
        # Scale 4x down -> boxblur -> scale back up.
        # This reduces boxblur computation by 16x per frame AND produces smoother,
        # natural privacy censor blur. Then split and overlay crops onto base video.
        parts.append(f"[{current}]split=2[v_base_blr][v_src_blr]")
        parts.append(
            f"[v_src_blr]scale={W//4}:{H//4},"
            f"boxblur=luma_radius=6:luma_power=2:chroma_radius=3:chroma_power=2,"
            f"scale={W}:{H}[v_full_blurred]"
        )
        _n_b = len(valid_blur_boxes)
        if _n_b == 1:
            parts.append(f"[v_full_blurred]copy[b_blr_0]")
        else:
            _b_tags = "".join(f"[b_blr_{_i}]" for _i in range(_n_b))
            parts.append(f"[v_full_blurred]split={_n_b}{_b_tags}")

        current = "v_base_blr"
        for _bi, (_bx, _by, _bw, _bh, _enable_expr) in enumerate(valid_blur_boxes):
            _c_tag = f"blr_crop_{_bi}"
            _o_tag = f"blr_done_{_bi}"
            parts.append(f"[b_blr_{_bi}]crop={_bw}:{_bh}:{_bx}:{_by}[{_c_tag}]")
            parts.append(f"[{current}][{_c_tag}]overlay={_bx}:{_by}{_enable_expr}:eof_action=repeat[{_o_tag}]")
            current = _o_tag

    for _di, (_bx, _by, _bw, _bh, _enable_expr) in enumerate(delogo_boxes):
        _d_tag = f"delogo_{_di}"
        parts.append(f"[{current}]delogo=x={_bx}:y={_by}:w={_bw}:h={_bh}{_enable_expr}[{_d_tag}]")
        current = _d_tag

    # ── 2. Multitrack Overlay Layers (Stickers / Cutouts / Images & Videos) ──
    # Rendered ON TOP of video + blur layer!
    for _oi, _ovl in enumerate(st.get("overlays", [])):
        if not _ovl.get("enabled", True):
            continue
        _ovl_path_str = _ovl.get("remove_bg_path") if (_ovl.get("remove_bg") and _ovl.get("remove_bg_path")) else _ovl.get("path", "")
        if not _ovl_path_str or not Path(_ovl_path_str).exists():
            continue
        
        _type    = _ovl.get("type", "image")
        _ox      = int(_ovl.get("x", 0))
        _oy      = int(_ovl.get("y", 0))
        _ow      = max(10, int(_ovl.get("w", 300)))
        _oh      = max(10, int(_ovl.get("h", 300)))
        _opacity = max(0.0, min(1.0, float(_ovl.get("opacity", 100)) / 100.0))
        _rot     = float(_ovl.get("rotation", 0.0))
        _st_t    = float(_ovl.get("start_time", 0.0) or 0.0)
        _end_t   = float(_ovl.get("end_time", 0.0) or 0.0)

        # Input source
        _is_vid_ovl = (Path(_ovl_path_str).suffix.lower() in _VID_EXTS)
        _is_gif_ovl = (Path(_ovl_path_str).suffix.lower() == ".gif")
        if _is_gif_ovl:
            inputs += ["-thread_queue_size", "512", "-ignore_loop", "0", "-i", str(_ovl_path_str)]
            use_shortest = True
        elif _type == "image" and not _is_vid_ovl:
            inputs += ["-thread_queue_size", "512", "-loop", "1", "-i", str(_ovl_path_str)]
            use_shortest = True
        elif _is_vid_ovl:
            inputs += ["-thread_queue_size", "512", "-stream_loop", "-1", "-i", str(_ovl_path_str)]
            use_shortest = True
        else:
            inputs += ["-thread_queue_size", "512", "-i", str(_ovl_path_str)]

        # Scaling & Opacity & Rotation filter for overlay stream
        _ovl_stages = [f"scale={_ow}:{_oh}", "format=rgba"]
        if abs(_opacity - 1.0) > 0.01:
            _ovl_stages.append(f"colorchannelmixer=aa={_opacity:.3f}")
        if abs(_rot) > 0.1:
            _ovl_stages.append(f"rotate={_rot}*PI/180:ow='hypot(iw,ih)':oh='hypot(iw,ih)':c=none")

        _ovl_tag = f"ovl_{_oi}"
        parts.append(f"[{inp_idx}:v]{','.join(_ovl_stages)}[{_ovl_tag}]")

        # Enable expression for timeline bounds
        _enable_ovl = ""
        if _st_t > 0.01 or _end_t > 0.01:
            if _end_t > _st_t + 0.01:
                _enable_ovl = f":enable='between(t,{_st_t:.3f},{_end_t:.3f})'"
            else:
                _enable_ovl = f":enable='gte(t,{_st_t:.3f})'"

        _comp_tag = f"comp_ovl_{_oi}"
        parts.append(f"[{current}][{_ovl_tag}]overlay={_ox}:{_oy}{_enable_ovl}:format=auto:eof_action=repeat[{_comp_tag}]")
        current = _comp_tag
        inp_idx += 1

    # ── 3. Title card overlay (Tiêu đề) ──────────────────────────────────────
    # Rendered ON TOP of video, blur, and stickers!
    # ── Priority 1: Browser-rendered PNG (WYSIWYG) ─────────────────────────────────────
    # If frontend sent a canvas-rendered PNG at export time, use it directly.
    # This guarantees Preview == Export: same font, same word-wrap, same stroke.
    # ── Priority 2: Fallback — PIL _make_title_image ─────────────────────────────
    effective_title = (title or st.get("title") or "").strip()
    if title_overlay_path and title_overlay_path.exists():
        title_img = title_overlay_path
        _browser_overlay = True   # caller owns this file — do NOT delete it
    elif effective_title:
        _browser_overlay = False
        _render_title = effective_title.upper() if st.get("title_uppercase", False) else effective_title
        title_img = _make_title_image(
            _render_title,
            font_name        = st.get("font_name",         "impact"),
            font_size        = st.get("font_size",          52),
            text_color       = st.get("text_color",        "white"),
            text_bg          = st.get("text_bg",           "box"),
            text_x           = st.get("text_x",            0),
            text_y           = st.get("text_y",            60),
            text_align       = st.get("text_align",        "left"),
            title_wrap_pct   = float(st.get("title_wrap_pct",  1.0)),
            box_radius       = int(st.get("box_radius",    40)),
            box_mode         = st.get("box_mode",          "frame"),
            box_pad_x        = int(st.get("box_pad_x",     30)),
            box_pad_y        = int(st.get("box_pad_y",     20)),
            box_bg_color     = st.get("box_bg_color",      "custom"),
            box_bg_color_hex = st.get("box_bg_color_hex",  "#222222"),
            box_opacity      = int(st.get("box_opacity",   90)),
            box_x1_pct       = float(st.get("box_x1_pct", -1.0)),
            box_x2_pct       = float(st.get("box_x2_pct", -1.0)),
            font_bold        = bool(st.get("font_bold",    False)),
            letter_spacing   = int(st.get("letter_spacing", 0)),
            line_height      = float(st.get("line_height",  1.2)),
            font_italic      = bool(st.get("font_italic",   False)),
            text_decoration  = st.get("text_decoration",   "none"),
            text_opacity     = int(st.get("text_opacity",   100)),
            text_rotation    = float(st.get("text_rotation", 0.0)),
            text_color_hex   = st.get("text_color_hex",    "#ffffff"),
            stroke_width     = int(st.get("stroke_width",   2)),
            stroke_color_hex = st.get("stroke_color_hex",  "#000000"),
            stroke_enabled   = bool(st.get("stroke_enabled", True)),
            title_lines      = st.get("title_lines"),
        )
    else:
        title_img = None
        _browser_overlay = False

    if title_img and title_img.exists():
        inputs  += ["-thread_queue_size", "512", "-i", str(title_img)]
        # IMPORTANT: eof_action=repeat ensures the title PNG frame repeats for every frame of the video!
        parts.append(f"[{current}][{inp_idx}:v]overlay=0:0:format=auto:eof_action=repeat[comp_title]")
        current  = "comp_title"
        inp_idx += 1
    elif effective_title:
        # PIL unavailable — use drawtext with ASCII-only stripped title
        safe = re.sub(r"[^A-Za-z0-9 '!?,.:;@#$%&*()-]", "", effective_title)
        safe = safe.replace("'", r"\'").replace(":", r"\:")[:120]
        parts.append(
            f"[{current}]drawtext=text='{safe}'"
            ":fontfile='C\\:/Windows/Fonts/impact.ttf':fontsize=52"
            ":fontcolor=white:borderw=4:bordercolor=black"
            f":x=(w-text_w)/2:y=50[comp_title]"
        )
        current = "comp_title"

    # Subtitles are burned in a SECOND pass after the main render (see below).
    # This avoids the libass dependency that subtitles= requires.

    # ── Watermark overlay ────────────────────────────────────────────────────
    wm_text = st.get("watermark_text", "").strip()
    if wm_text:
        # Sanitize for FFmpeg drawtext: escape backslash, colon, quote, apostrophe
        _wm_safe = (wm_text
                    .replace("\\", "\\\\")
                    .replace("'",  "\u2019")    # replace curly apostrophe (safe)
                    .replace(":",  "\\:")
                    .replace("%",  "\\%"))[:80]

        # Map position code → (x_expr, y_expr) in FFmpeg coordinates
        _WM_PAD = 30
        _pos_map = {
            "TL": (f"{_WM_PAD}",            f"{_WM_PAD}"),
            "TC": ("(W-text_w)/2",           f"{_WM_PAD}"),
            "TR": (f"W-text_w-{_WM_PAD}",   f"{_WM_PAD}"),
            "ML": (f"{_WM_PAD}",            "(H-text_h)/2"),
            "MC": ("(W-text_w)/2",           "(H-text_h)/2"),
            "MR": (f"W-text_w-{_WM_PAD}",  "(H-text_h)/2"),
            "BL": (f"{_WM_PAD}",            f"H-text_h-{_WM_PAD}"),
            "BC": ("(W-text_w)/2",           f"H-text_h-{_WM_PAD}"),
            "BR": (f"W-text_w-{_WM_PAD}",  f"H-text_h-{_WM_PAD}"),
        }
        _wx, _wy = _pos_map.get(st.get("watermark_pos", "BR"),
                                (f"W-text_w-{_WM_PAD}", f"H-text_h-{_WM_PAD}"))
        _wm_hex   = st.get("watermark_color", "#FFFFFF").lstrip("#")
        _wm_alpha = max(0.05, min(1.0, int(st.get("watermark_opacity", 50)) / 100))
        _wm_size  = max(12, min(120, int(st.get("watermark_size", 28))))
        parts.append(
            f"[{current}]drawtext="
            f"text='{_wm_safe}'"
            f":fontfile='C\\:/Windows/Fonts/arialbd.ttf'"
            f":fontsize={_wm_size}"
            f":fontcolor=#{_wm_hex}@{_wm_alpha:.2f}"
            f":borderw=2:bordercolor=black@{min(_wm_alpha+0.2, 1.0):.2f}"
            f":x={_wx}:y={_wy}[wm_done]"
        )
        current = "wm_done"

    # ── Deep Audio Evasion (Speed tweak, Pitch shift +3%, Spectrum EQ) ────────
    speed_tweak = st.get("speed_tweak", False)
    if speed_tweak:
        parts.append(f"[{current}]setpts=0.98*PTS[spd_done]")
        current = "spd_done"

    af_parts = []
    if speed_tweak:
        af_parts.append("atempo=1.0204")
    if st.get("audio_pitch", False):
        af_parts.append("asetrate=44100*1.03,aresample=44100")
    if st.get("audio_eq", False):
        af_parts.append("equalizer=f=1000:width_type=h:width=200:g=-2,highpass=f=40,lowpass=f=15500")

    # ── Custom Audio & Voiceover Swapping ─────────────────────────────────────
    # ── Video and Audio Trimming & Voiceover Swapping ─────────────────────────
    vid_dur_secs = get_video_duration(clip) or 0.0
    video_trim_dur = float(st.get("video_trim_dur", 0.0))
    if 0.5 <= video_trim_dur < vid_dur_secs:
        effective_video_dur = video_trim_dur
        parts.append(f"[{current}]trim=duration={effective_video_dur:.3f},setpts=PTS-STARTPTS[vtrimmed]")
        current = "vtrimmed"
    else:
        effective_video_dur = vid_dur_secs

    custom_audio_path_str = st.get("custom_audio_path", "")
    has_custom_audio = bool(custom_audio_path_str and Path(custom_audio_path_str).exists())
    custom_audio_map = None
    target_render_dur = effective_video_dur

    if has_custom_audio:
        ca_path = Path(custom_audio_path_str)
        ca_inp_idx = inp_idx
        inputs += ["-thread_queue_size", "512", "-i", str(ca_path)]
        inp_idx += 1

        ca_full_dur = float(st.get("custom_audio_dur", 0.0))
        if ca_full_dur <= 0:
            ca_full_dur = get_video_duration(ca_path) or 0.0

        ca_offset     = max(0.0, float(st.get("custom_audio_offset", 0.0)))
        ca_trim_start = max(0.0, float(st.get("custom_audio_trim_start", 0.0)))
        ca_trim_dur   = float(st.get("custom_audio_trim_dur", 0.0))
        if ca_trim_dur <= 0.0 or ca_trim_dur > (ca_full_dur - ca_trim_start):
            ca_trim_dur = max(0.5, ca_full_dur - ca_trim_start)

        orig_vol = float(st.get("orig_volume", 0)) / 100.0
        cust_vol = float(st.get("custom_volume", 100)) / 100.0

        effective_audio_end = ca_offset + ca_trim_dur
        target_render_dur = max(effective_video_dur, effective_audio_end)

        # Build custom audio filter chain: atrim -> asetpts -> adelay -> volume
        ca_filter_stages = [f"atrim=start={ca_trim_start:.3f}:duration={ca_trim_dur:.3f},asetpts=PTS-STARTPTS"]
        if ca_offset > 0.005:
            adelay_ms = int(round(ca_offset * 1000))
            ca_filter_stages.append(f"adelay={adelay_ms}|{adelay_ms}")
        if abs(cust_vol - 1.0) > 0.01:
            ca_filter_stages.append(f"volume={cust_vol:.2f}")

        ca_tag = "cust_a"
        parts.append(f"[{ca_inp_idx}:a]{','.join(ca_filter_stages)}[{ca_tag}]")

        # Mix with original video audio if orig_vol > 0.01
        clip_has_audio = has_audio_stream(clip)
        if orig_vol > 0.01 and clip_has_audio:
            if effective_video_dur < vid_dur_secs:
                parts.append(f"[0:a]atrim=duration={effective_video_dur:.3f},asetpts=PTS-STARTPTS,volume={orig_vol:.2f}[orig_a]")
            else:
                parts.append(f"[0:a]volume={orig_vol:.2f}[orig_a]")
            parts.append(f"[orig_a][{ca_tag}]amix=inputs=2:duration=longest:dropout_transition=0[final_a]")
            custom_audio_map = "[final_a]"
        else:
            custom_audio_map = f"[{ca_tag}]"

        # Check duration padding: if audio extends past video duration, pad black screen
        if effective_audio_end > effective_video_dur:
            pad_dur = effective_audio_end - effective_video_dur
            parts.append(f"[{current}]tpad=stop_mode=add:stop_duration={pad_dur:.3f}:color=black[tpad_done]")
            current = "tpad_done"
            use_shortest = False
        else:
            use_shortest = True
    else:
        clip_has_audio = has_audio_stream(clip)
        # No custom audio: if video was trimmed, trim original audio too
        if effective_video_dur < vid_dur_secs and clip_has_audio:
            parts.append(f"[0:a]atrim=duration={effective_video_dur:.3f},asetpts=PTS-STARTPTS[orig_a_trim]")
            custom_audio_map = "[orig_a_trim]"

    # ── Deep Audio Evasion in filter_complex ──────────────────────────────────
    # Note: Simple (-af) and complex (-filter_complex) filtering cannot be used
    # together for the same stream in FFmpeg. All audio evasion filters must be
    # attached directly to the audio branch in filter_complex.
    if af_parts:
        if custom_audio_map:
            in_tag = custom_audio_map.strip("[]")
            parts.append(f"[{in_tag}]{','.join(af_parts)}[final_a_evaded]")
            custom_audio_map = "[final_a_evaded]"
        elif clip_has_audio:
            parts.append(f"[0:a]{','.join(af_parts)}[final_a_evaded]")
            custom_audio_map = "[final_a_evaded]"

    # Audio mapping & options:
    audio_mapping = []
    if custom_audio_map:
        audio_mapping = ["-map", custom_audio_map, "-c:a", acodec, "-b:a", "192k"]
    elif clip_has_audio:
        audio_mapping = ["-map", "0:a?", "-c:a", acodec, "-b:a", "192k"]
    else:
        audio_mapping = ["-an"]

    # ── NVENC/QSV: force yuv420p AFTER all filter stages ──────────────────────
    # RGBA title PNG overlays output yuva420p which NVENC/QSV rejects.
    # This must come AFTER blur boxes, watermark, and speed_tweak are built.
    if vcodec in {"h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv"}:
        parts.append(f"[{current}]format=yuv420p[final_pix]")
        current = "final_pix"

    # Write full filter_complex to a temp debug file for diagnosis
    _fc_str = ";".join(parts)
    try:
        import tempfile as _tmpmod
        _dbg = Path(_tmpmod.gettempdir()) / f"reup_fc_{dst.stem[:40]}.txt"
        _dbg.write_text(_fc_str, encoding="utf-8")
        log.info(f"[DBG] FC ({len(parts)} parts, {len(_fc_str)} chars) → {_dbg}")
        log.info(f"[DBG] vcodec={vcodec} preset={preset} map=[{current}]")
    except Exception:
        pass

    # BT.709 color tags: CPU encoders only.
    # NVENC / QSV on many driver versions silently reject -color_primaries /
    # -colorspace → falls back to software encode, defeating GPU speedup.
    _is_gpu_vcodec = vcodec not in {"libx264", "libx265", "h264_mf"}
    _main_color_tags = [] if _is_gpu_vcodec else [
        "-color_primaries", "bt709",
        "-color_trc",       "bt709",
        "-colorspace",      "bt709",
        "-color_range",     "tv",
    ]

    cmd = inputs + [
        "-filter_complex", _fc_str,
        "-map", f"[{current}]",
        "-c:v", vcodec, "-preset", preset, *_quality_flag,
        *(["-r", str(fps)] if fps else []),
        *_main_color_tags,
        *audio_mapping,
        "-max_muxing_queue_size", "1024",
        *(["-t", f"{target_render_dur:.3f}"] if target_render_dur else (["-shortest"] if use_shortest else [])),
        "-map_metadata", "-1",
        "-map_metadata:s:v", "-1",
        "-map_metadata:s:a", "-1",
        "-movflags", "+faststart",
        str(dst),
    ]

    # ── Launch FFmpeg and wait for completion ────────────────────────────────
    n_blur       = len(st.get("blur_boxes", []))
    effective_render_dur = target_render_dur or vid_dur_secs

    stderr_lines: list[str] = []
    result_rc = _run_ffmpeg_render(
        cmd          = cmd,
        stop_event   = stop_event,
        n_blur       = n_blur,
        vid_dur_secs = effective_render_dur,
        progress_cb  = progress_cb,
        # Don't pass browser overlay to _run_ffmpeg_render — caller in server.py owns cleanup.
        # Pass PIL-generated title_img only so the function can delete it after FFmpeg finishes.
        title_img    = None if _browser_overlay else title_img,
        log          = log,
        stderr_out   = stderr_lines,
    )

    if progress_cb:
        progress_cb(1.0)

    if result_rc != 0:
        raise RuntimeError(f"FFmpeg exit {result_rc}:\n{''.join(stderr_lines[-40:])[-1500:]}")
    if not dst.exists() or dst.stat().st_size < 512:
        raise RuntimeError("FFmpeg ran but reup output file is missing.")

    # ── Second pass: apply tracked blur (OpenCV per-frame) BEFORE burning subtitles ──
    tracked_boxes = [b for b in st.get("blur_boxes", []) if b.get("tracked")]
    for tb in tracked_boxes:
        tf = Path(tb.get("track_file", ""))
        if tf.exists():
            dst = _apply_tracked_blur_pass(dst, tf, st, log)

    # ── Third pass: burn subtitles via drawtext (on top of blur & video) ─────
    if srt_path and srt_path.exists():
        dst = _burn_subtitles_pass(dst, srt_path, st, log, progress_cb,
                                   render_cfg=render_cfg,
                                   words_json_path=words_json_path,
                                   orig_clip=clip)

    # ── Final pass: Auto-randomize video file MD5 Hash ───────────────────────
    if st.get("change_md5", True):
        try:
            import random
            with open(dst, "ab") as f:
                f.write(os.urandom(random.randint(8, 32)))
            log.ok(f"MD5 Hash randomized for {dst.name}")
        except Exception as _e:
            log.warn(f"MD5 randomization note: {_e}")

    mb = dst.stat().st_size / 1_048_576
    log.ok(f"Reup saved: {dst.name}  ({mb:.2f} MB)")
    return dst




# ──────────────────────────────────────────────────────────────────────────────
# Video Player — FFmpeg pipe → PIL → Canvas (no OpenCV needed)
# ──────────────────────────────────────────────────────────────────────────────

PLAYBACK_FPS = 24          # frames per second for preview playback
PLAYBACK_VF  = (
    f"scale={PREVIEW_W}:{PREVIEW_H}:"
    "force_original_aspect_ratio=decrease,"
    f"pad={PREVIEW_W}:{PREVIEW_H}:(ow-iw)/2:(oh-ih)/2:color=black,"
    "format=rgb24"
)


class VideoPlayer:
    """
    Plays a [start, start+duration) window of a video on a tk.Canvas by
    piping raw RGB24 frames from FFmpeg into PIL ImageTk at PLAYBACK_FPS.
    Loops video+audio indefinitely until stop() is called.

    Audio: ffplay subprocess (-nodisp, looped in a daemon thread).
    Video: raw RGB24 frames piped to PIL Canvas on the Tk main thread.
    """

    def __init__(self, canvas: tk.Canvas, width: int, height: int,
                 on_state_change=None):
        self._canvas      = canvas
        self._w           = width
        self._h           = height
        self._on_state    = on_state_change   # callback(playing: bool)
        self._stop_evt    = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._photo_ref   = None              # keep ImageTk ref alive
        self._audio_proc: Optional[subprocess.Popen] = None
        self._audio_lock  = threading.Lock()
        self._audio_thread: Optional[threading.Thread] = None
        # Track the active FFmpeg decode pipe so stop() can kill it to
        # unblock the blocking proc.stdout.read() in _run.
        self._video_proc: Optional[subprocess.Popen] = None
        self._video_proc_lock = threading.Lock()
        # Monotonic counter — incremented each play(); old _audio_loops bail.
        self._audio_gen  = 0
        # Event set when the first video frame is decoded; audio waits on this
        # so that both streams start from the same wall-clock moment.
        self._first_frame_evt = threading.Event()

    # ── Public API ─────────────────────────────────────────────────────────

    def play(self, video_path: Path, start_sec: float,
             duration: float = CLIP_DURATION):
        """Stop any running playback then start fresh (video + audio)."""
        self.stop()
        self._stop_evt.clear()
        self._first_frame_evt.clear()   # reset sync gate for this play()
        self._thread = threading.Thread(
            target=self._run,
            args=(video_path, start_sec, duration),
            daemon=True,
        )
        self._thread.start()
        # Start audio ONLY after the first video frame is ready so both
        # streams begin from the same perceived moment (A/V sync fix).
        def _sync_audio():
            self._first_frame_evt.wait(timeout=3.0)   # max 3s for first frame
            if not self._stop_evt.is_set():
                self._start_audio(video_path, start_sec, duration)
        threading.Thread(target=_sync_audio, daemon=True).start()
        if self._on_state:
            self._canvas.after(0, lambda: self._on_state(True))

    def stop(self):
        self._stop_evt.set()
        self._first_frame_evt.set()   # unblock any waiting _sync_audio thread
        self._stop_audio()
        # Kill the FFmpeg decode pipe so proc.stdout.read() in _run unblocks.
        # Without this, each stop() leaks a thread + process indefinitely.
        with self._video_proc_lock:
            vp, self._video_proc = self._video_proc, None
        if vp and vp.poll() is None:
            try:
                vp.kill()
            except Exception:
                pass
        # Do NOT join — called from Tk main thread; join would freeze UI.
        self._thread = None
        if self._on_state:
            try:
                self._canvas.after(0, lambda: self._on_state(False))
            except Exception:
                pass

    # ── Audio (ffplay — ships with FFmpeg, no extra pip deps) ─────────────

    def _start_audio(self, video_path: Path, start_sec: float,
                     duration: float):
        """
        Play audio via ffplay hidden subprocess.
        A daemon thread loops ffplay each time the 16s segment ends.
        """
        self._stop_audio()  # kill any previous audio first

        # Bump gen BEFORE clearing _stop_evt so that any old _audio_loop
        # that wakes from proc.wait() sees a stale gen and exits instead of
        # restarting a new ffplay (the race that doubled audio processes).
        self._audio_gen += 1
        my_audio_gen = self._audio_gen

        # CREATE_NO_WINDOW keeps the console hidden on Windows.
        NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        def _make_proc():
            try:
                return subprocess.Popen(
                    [
                        FFPLAY,
                        "-nodisp", "-autoexit",
                        "-loglevel", "quiet",
                        "-ss", str(start_sec),
                        "-t",  str(duration),
                        str(video_path),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=NO_WIN,
                )
            except Exception:
                return None

        def _audio_loop():
            # Guard against the play() race: stop() sets _stop_evt, then
            # play() clears it; old loop would restart without this check.
            while not self._stop_evt.is_set() and my_audio_gen == self._audio_gen:
                proc = _make_proc()
                if proc is None:
                    break
                with self._audio_lock:
                    self._audio_proc = proc
                proc.wait()     # blocks until 16s segment ends
                with self._audio_lock:
                    self._audio_proc = None
                # Immediately loop back

        self._audio_thread = threading.Thread(
            target=_audio_loop, daemon=True)
        self._audio_thread.start()

    def _stop_audio(self):
        """Terminate ffplay immediately."""
        with self._audio_lock:
            proc = self._audio_proc
            self._audio_proc = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass



    @property
    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Worker ─────────────────────────────────────────────────────────────

    def _run(self, video_path: Path, start_sec: float, duration: float):
        frame_size   = self._w * self._h * 3          # RGB24 bytes per frame
        frame_delay  = 1.0 / PLAYBACK_FPS

        while not self._stop_evt.is_set():
            proc = self._open_pipe(video_path, start_sec, duration)
            if proc is None:
                break

            # Register so stop() can kill this proc to unblock the read
            with self._video_proc_lock:
                self._video_proc = proc

            session_start = None
            frame_idx = 0
            try:
                while not self._stop_evt.is_set():
                    # Read one full frame — loop because Windows pipes
                    # may return fewer bytes than requested in a single call.
                    raw  = b""
                    need = frame_size
                    while need > 0 and not self._stop_evt.is_set():
                        chunk = proc.stdout.read(need)
                        if not chunk:
                            need = -1   # pipe closed / EOF (or proc killed)
                            break
                        raw  += chunk
                        need -= len(chunk)

                    if len(raw) < frame_size:
                        # Segment finished, pipe closed, or stop() killed proc
                        break

                    # Signal audio thread that first frame is ready (A/V sync).
                    # Only set once per play() call; subsequent frames skip this.
                    if not self._first_frame_evt.is_set():
                        session_start = time.monotonic()
                        self._first_frame_evt.set()

                    if session_start is None:
                        session_start = time.monotonic()

                    # Calculate ideal display time for this frame
                    ideal_elapsed = frame_idx * frame_delay
                    actual_elapsed = time.monotonic() - session_start
                    wait_time = ideal_elapsed - actual_elapsed

                    # If this frame is too late (e.g. lagging behind by more than 2 frames),
                    # skip rendering it to catch up with the audio.
                    if wait_time < -2 * frame_delay:
                        frame_idx += 1
                        continue

                    img = Image.frombuffer("RGB", (self._w, self._h), raw)

                    # IMPORTANT: ImageTk.PhotoImage must be created on the
                    # Tk main thread. Pass the PIL Image via after() and
                    # construct the PhotoImage inside that callback.
                    def _draw(i=img):
                        p = ImageTk.PhotoImage(i)   # ← main thread ✓
                        self._photo_ref = p
                        self._canvas.delete("all")
                        self._canvas.create_image(
                            self._w // 2, self._h // 2,
                            image=p, anchor="center",
                        )
                    self._canvas.after(0, _draw)

                    if wait_time > 0:
                        time.sleep(wait_time)

                    frame_idx += 1

            finally:
                with self._video_proc_lock:
                    if self._video_proc is proc:
                        self._video_proc = None
                try:
                    proc.stdout.close()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    def _open_pipe(self, video_path: Path, start_sec: float,
                   duration: float) -> Optional[subprocess.Popen]:
        """Start an FFmpeg process that outputs raw RGB24 to stdout."""
        cmd = [
            FFMPEG, "-loglevel", "quiet",
            "-ss", str(start_sec),
            "-i",  str(video_path),
            "-t",  str(duration),
            "-vf", PLAYBACK_VF,
            "-r",  str(PLAYBACK_FPS),
            "-f",  "rawvideo",
            "-pix_fmt", "rgb24",
            "pipe:1",
        ]
        try:
            return subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except Exception:
            return None



# ──────────────────────────────────────────────────────────────────────────────
# Main Application
# ──────────────────────────────────────────────────────────────────────────────

class CliperApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE}  {APP_VERSION}")
        self.geometry("1200x920")
        self.minsize(1020, 760)
        self.configure(bg=CLR_BG)
        self.resizable(True, True)

        self._cfg          = load_config()
        self._stop         = threading.Event()
        self._key_rows: list[dict]   = []
        self._video_files: list[Path] = []
        # per-video results: path_str -> {status, candidates, error}
        self._video_results: dict[str, dict] = {}
        self._active_threads: list[threading.Thread] = []
        self._selected_video: Optional[Path] = None
        self._preview_ref    = None          # PIL ImageTk ref
        self._running_count  = 0             # threads still working
        self._last_cut_path: Optional[Path] = None
        self._selected_title_for_reup: str  = ""
        # Tab 2 editor state
        self._edit_queue:    list            = []   # list of {clip_path, title, state}
        self._edit_sel_idx:  int             = -1
        self._frame_cache:   dict            = {}   # str(clip_path) → PIL.Image
        self._edit_bg_cache: dict            = {}   # (key, video_y) → PIL.Image
        self._edit_photo_ref = None                 # keep ImageTk ref alive
        self._edit_drag_origin: tuple        = (0, 0)
        self._drag_text_origin: tuple        = (0, 0)
        # Must be an instance (not class) Lock so it works before _build_ui
        self._preview_proc_lock = threading.Lock()
        self._import_sem = threading.Semaphore(5)

        self._build_styles()
        # Probe available encoders BEFORE building the UI so the encoder
        # combobox in Tab 2 already shows NVENC/QSV if the hardware is present.
        # Takes ~100ms — negligible compared to Tk widget construction time.
        _probe_encoders()
        self._build_ui()
        self._check_deps()
        self._bind_shortcuts()
        self.update_idletasks()
        self._setup_drag_and_drop()
        threading.Thread(target=self._check_for_updates, daemon=True).start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _toast(self, message: str, kind: str = "info", duration: int = 3500):
        """Show a floating toast notification on the main window."""
        Toast(self, message, kind=kind, duration=duration)

    def _bind_shortcuts(self):
        """Register global keyboard shortcuts."""
        self.bind_all("<Control-Shift-A>",
                      lambda e: self._start_analyze() if self._btn_analyze["state"] != "disabled" else None)
        self.bind_all("<Control-Shift-KeyRelease-A>", lambda e: None)  # absorb keyup
        self.bind_all("<Control-Shift-S>",
                      lambda e: self._stop_work() if self._btn_stop["state"] != "disabled" else None)
        self.bind_all("<Escape>", self._on_escape)
        # KeyRelease (not KeyPress) so auto-repeat doesn't toggle ON→OFF→ON rapidly.
        self.bind_all("<KeyRelease-d>", self._on_d_key)
        self.bind_all("<KeyRelease-D>", self._on_d_key)

    def _on_d_key(self, event):
        """Toggle draw mode with D key — only when Tab 2 is active and no text widget is focused."""
        # Don't intercept D while the user is typing in an Entry, Text, or Spinbox
        focused = self.focus_get()
        if isinstance(focused, (tk.Entry, tk.Text, tk.Spinbox)):
            return
        try:
            tab_idx = self._tab_notebook.index("current")
        except Exception:
            return
        if tab_idx == 1:   # 0 = Analyze, 1 = Edit
            self._toggle_draw_mode()

    def _on_escape(self, _event=None):
        """Escape key: cancel draw mode if active, else unfocus current widget."""
        if getattr(self, "_draw_mode_on", False):
            self._toggle_draw_mode()

    def _on_close(self):
        """Persist config before exit."""
        try:
            self._save_config()
        except Exception:
            pass
        self.destroy()


    # ── Styles ─────────────────────────────────────────────────────────────

    def _build_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame",           background=CLR_BG)
        s.configure("Panel.TFrame",     background=CLR_PANEL)
        s.configure("Surface.TFrame",   background=CLR_SURFACE)
        s.configure("TLabel",           background=CLR_BG, foreground=CLR_FG,
                    font=("Segoe UI", 10))
        s.configure("Panel.TLabel",     background=CLR_PANEL, foreground=CLR_FG,
                    font=("Segoe UI", 10))
        s.configure("Surface.TLabel",   background=CLR_SURFACE, foreground=CLR_FG,
                    font=("Segoe UI", 10))
        s.configure("Section.TLabel",   background=CLR_PANEL, foreground=CLR_HEADER,
                    font=("Segoe UI", 10, "bold"))
        s.configure("BgSection.TLabel", background=CLR_BG,    foreground=CLR_HEADER,
                    font=("Segoe UI", 10, "bold"))
        s.configure("Title.TLabel",     background=CLR_BG,    foreground=CLR_ACCENT,
                    font=("Segoe UI", 16, "bold"))
        s.configure("Status.TLabel",    background=CLR_BG,    foreground=CLR_SUCCESS,
                    font=("Segoe UI", 10, "bold"))
        s.configure("TButton",          font=("Segoe UI", 10),
                    background=CLR_SURFACE, foreground=CLR_FG, borderwidth=0)
        s.map("TButton", background=[("active", CLR_ACCENT)])
        s.configure("TEntry",           fieldbackground=CLR_INPUT_BG,
                    foreground=CLR_FG, insertcolor=CLR_FG,
                    borderwidth=1, relief="flat")
        s.configure("TCombobox",        fieldbackground=CLR_INPUT_BG,
                    foreground=CLR_FG, background=CLR_PANEL,
                    arrowcolor=CLR_FG2)
        s.map("TCombobox", fieldbackground=[("readonly", CLR_INPUT_BG)])
        s.configure("TProgressbar",     troughcolor=CLR_SURFACE,
                    background=CLR_ACCENT, thickness=6)
        s.configure("TSeparator",       background=CLR_BORDER)
        s.configure("Queue.Treeview",   background=CLR_INPUT_BG,
                    foreground=CLR_FG,   fieldbackground=CLR_INPUT_BG,
                    borderwidth=0,       rowheight=30, font=("Segoe UI", 9))
        s.configure("Queue.Treeview.Heading", background=CLR_PANEL,
                    foreground=CLR_DIM,  font=("Segoe UI", 9, "bold"),
                    borderwidth=0)
        s.map("Queue.Treeview", background=[("selected", CLR_ACCENT_D)])
        # Scrollbar — minimal dark style
        s.configure("Vertical.TScrollbar",
                    background=CLR_SURFACE, troughcolor=CLR_BG,
                    arrowcolor=CLR_DIM, borderwidth=0)
        s.map("Vertical.TScrollbar",
              background=[("active", CLR_BORDER), ("pressed", CLR_ACCENT)])

    # ── UI Build ───────────────────────────────────────────────────────────

    def _build_ui(self):
        # Title bar
        top = ttk.Frame(self, padding=(20, 12, 20, 0))
        top.pack(fill=X)
        ttk.Label(top, text=f"🚔  {APP_TITLE}", style="Title.TLabel").pack(side=LEFT)
        self._status_lbl = ttk.Label(top, text="● Ready", style="Status.TLabel")
        self._status_lbl.pack(side=RIGHT)
        ttk.Separator(self, orient=HORIZONTAL).pack(fill=X, padx=20, pady=8)

        # Update banner frame (hidden until update check finds a newer version)
        self._update_banner = ttk.Frame(self, style="Panel.TFrame")

        # Body: left config panel + right main panel
        body = ttk.Frame(self, padding=(20, 0, 20, 0))
        body.pack(fill=BOTH, expand=True)

        # ── Left Panel (scrollable, fixed width 400) ────────────────────
        left_outer = ttk.Frame(body, style="Panel.TFrame")
        left_outer.pack(side=LEFT, fill=Y, expand=False)
        left_outer.configure(width=400)
        left_outer.pack_propagate(False)

        left_canvas = tk.Canvas(left_outer, bg=CLR_PANEL,
                                highlightthickness=0, width=384)
        left_sb = ttk.Scrollbar(left_outer, orient=VERTICAL,
                                command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_sb.set)
        left_sb.pack(side=RIGHT, fill=Y)
        left_canvas.pack(side=LEFT, fill=BOTH, expand=True)

        left_inner = ttk.Frame(left_canvas, style="Panel.TFrame", padding=14)
        self._left_canvas = left_canvas   # saved for scroll-to-bottom on key add
        self._left_win_id = left_canvas.create_window(
            (0, 0), window=left_inner, anchor="nw")
        left_inner.bind("<Configure>",
            lambda e: left_canvas.configure(
                scrollregion=left_canvas.bbox("all")))
        left_canvas.bind("<Configure>",
            lambda e: left_canvas.itemconfig(self._left_win_id, width=e.width))
        left_canvas.bind_all("<MouseWheel>",
            lambda e: left_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._build_left(left_inner)

        # ── Right Panel ─────────────────────────────────────────────────
        right = ttk.Frame(body, padding=(12, 0, 0, 0))
        right.pack(side=RIGHT, fill=BOTH, expand=True)
        self._build_right(right)

        # Progress bar
        foot = ttk.Frame(self, padding=(20, 6, 20, 10))
        foot.pack(fill=X)
        self._prog_var = tk.DoubleVar()
        ttk.Progressbar(foot, variable=self._prog_var, maximum=100,
                        style="TProgressbar").pack(fill=X)
        self._prog_lbl = ttk.Label(foot, text="", font=("Segoe UI", 8),
                                   foreground=CLR_DIM)
        self._prog_lbl.pack(anchor=E, pady=(2, 0))

    # ── Left Panel ─────────────────────────────────────────────────────────

    def _build_left(self, p):
        # ── API KEYS ───────────────────────────────────────────────────────
        api_card = SectionCard(p, "API Keys", collapsible=False)
        api_card.pack(fill=X, pady=(0, 8))
        c = api_card.content

        ttk.Label(c, text="Round-robin load balancing across all keys.",
                  background=CLR_SURFACE, foreground=CLR_DIM,
                  font=("Segoe UI", 8)).pack(anchor=W, pady=(0, 6))

        # Container for dynamic key rows
        self._keys_container = tk.Frame(c, bg=CLR_SURFACE)
        self._keys_container.pack(fill=X, pady=(0, 4))

        # Restore saved keys
        saved_keys = self._cfg.get("api_keys", [])
        if isinstance(saved_keys, str):
            saved_keys = [k.strip() for k in saved_keys.splitlines() if k.strip()]
        if not saved_keys:
            saved_keys = [self._cfg.get("api_key", "")]
        for key in saved_keys:
            self._add_key_row(value=key)
        if not self._key_rows:
            self._add_key_row()

        SecondaryButton(c, text="Add API Key", icon="＋",
                        command=self._add_key_row,
                        font=("Segoe UI", 9, "bold"), pady=4).pack(
            anchor=W, pady=(0, 2))

        # ── AI MODEL ───────────────────────────────────────────────────────
        model_card = SectionCard(p, "AI Model", collapsible=False)
        model_card.pack(fill=X, pady=(0, 8))
        mc = model_card.content

        _model_opts = [
            ("gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite (Recommended)"),
            ("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite"),
        ]
        self._model_label_to_id = {lbl: mid for mid, lbl in _model_opts}
        self._model_id_to_label = {mid: lbl for mid, lbl in _model_opts}

        saved_model = self._cfg.get("model_name", "gemini-3.5-flash-lite")
        default_label = self._model_id_to_label.get(saved_model, "Gemini 3.5 Flash Lite (Recommended)")

        self._model_var = tk.StringVar(value=default_label)

        m_row = tk.Frame(mc, bg=CLR_SURFACE)
        m_row.pack(fill=X, pady=(0, 4))
        tk.Label(m_row, text="Model:", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 9, "bold"), width=7, anchor=W).pack(side=LEFT)

        model_cb = ttk.Combobox(
            m_row, textvariable=self._model_var,
            values=[lbl for _, lbl in _model_opts],
            state="readonly", font=("Segoe UI", 9)
        )
        model_cb.pack(side=LEFT, fill=X, expand=True)

        # ── CTA Toggle ─────────────────────────────────────────────────────
        self._cta_var = tk.BooleanVar(value=bool(self._cfg.get("include_cta", False)))
        cta_row = tk.Frame(mc, bg=CLR_SURFACE)
        cta_row.pack(fill=X, pady=(2, 0))
        tk.Checkbutton(
            cta_row,
            text="CTA cuối tiêu đề  (👉 Follow for more!)",
            variable=self._cta_var,
            bg=CLR_SURFACE, fg=CLR_FG2,
            selectcolor=CLR_SURFACE,
            activebackground=CLR_SURFACE, activeforeground=CLR_FG,
            font=("Segoe UI", 8),
            command=self._save_config,   # auto-save on toggle
        ).pack(side=LEFT)

        # ── INPUT VIDEOS ───────────────────────────────────────────────────
        vid_card = SectionCard(p, "Input Videos", collapsible=False)
        vid_card.pack(fill=X, pady=(0, 8))
        c = vid_card.content

        sel_row = tk.Frame(c, bg=CLR_SURFACE)
        sel_row.pack(fill=X, pady=(0, 6))
        SecondaryButton(sel_row, text="Select Files…", icon="📂",
                        command=self._pick_video_files,
                        font=("Segoe UI", 9, "bold"), pady=4).pack(side=LEFT)
        DangerButton(sel_row, text="Clear", icon="✕",
                     command=self._clear_video_files,
                     font=("Segoe UI", 9, "bold"), pady=4).pack(side=RIGHT)

        list_frame = tk.Frame(c, bg=CLR_INPUT_BG,
                              highlightbackground=CLR_BORDER, highlightthickness=1)
        list_frame.pack(fill=X, pady=(0, 4))
        self._file_listbox = tk.Listbox(
            list_frame, height=6,
            bg=CLR_INPUT_BG, fg=CLR_FG,
            selectbackground=CLR_ACCENT_D,
            font=("Segoe UI", 9), borderwidth=0, highlightthickness=0,
            activestyle="none",
            selectmode="extended",  # enables Shift+Click, Ctrl+Click multi-select
        )
        lb_sb = ttk.Scrollbar(list_frame, orient=VERTICAL,
                              command=self._file_listbox.yview)
        self._file_listbox.configure(yscrollcommand=lb_sb.set)
        lb_sb.pack(side=RIGHT, fill=Y)
        self._file_listbox.pack(fill=X, expand=True)
        # Hotkeys: Delete removes selected; Ctrl+A selects all
        self._file_listbox.bind("<Delete>",  lambda _e: self._remove_selected_files())
        self._file_listbox.bind("<Control-a>", lambda _e: self._file_listbox.select_set(0, END))

        self._file_count_lbl = tk.Label(c, text="No files selected.",
                                        bg=CLR_SURFACE, fg=CLR_DIM,
                                        font=("Segoe UI", 8))
        self._file_count_lbl.pack(anchor=W, pady=(0, 2))

        # Restore saved file list
        saved_files = self._cfg.get("video_files", [])
        if saved_files:
            existing = [Path(f) for f in saved_files if Path(f).exists()]
            if existing:
                self._video_files = existing
                self._refresh_file_listbox()

        # ── OUTPUT FOLDER ──────────────────────────────────────────────────
        out_card = SectionCard(p, "Output Folder", collapsible=False)
        out_card.pack(fill=X, pady=(0, 8))
        c = out_card.content

        out_row = tk.Frame(c, bg=CLR_SURFACE)
        out_row.pack(fill=X, pady=(0, 4))
        self._output_var = tk.StringVar(value=self._cfg.get("output_folder", ""))
        tk.Entry(out_row, textvariable=self._output_var,
                 bg=CLR_INPUT_BG, fg=CLR_FG, insertbackground=CLR_FG,
                 font=("Segoe UI", 9), relief=FLAT, bd=1,
                 highlightbackground=CLR_BORDER, highlightthickness=1).pack(
            side=LEFT, fill=X, expand=True)
        SecondaryButton(out_row, text="📂",
                        command=lambda: self._pick_folder(self._output_var),
                        font=("Segoe UI", 10), pady=2, padx=6).pack(
            side=RIGHT, padx=(4, 0))

        tk.Label(c, text=f"Clip duration constraint: {CLIP_DURATION}s",
                 bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))

        # ── ACTION BUTTONS ─────────────────────────────────────────────────
        tk.Frame(p, bg=CLR_BORDER, height=1).pack(fill=X, pady=10)

        self._btn_analyze = AccentButton(
            p, text="ANALYZE ALL", icon="▶",
            command=self._start_analyze,
        )
        self._btn_analyze.pack(fill=X, pady=(0, 6))
        ToolTip(self._btn_analyze, "Analyze all loaded videos in parallel  (Ctrl+Shift+A)")

        self._btn_stop = tk.Button(
            p, text="⏹  STOP ALL",
            bg="#3d0f0f", fg=CLR_ERROR, activebackground="#5a1515",
            activeforeground="#fca5a5",
            font=("Segoe UI", 11, "bold"), relief=FLAT,
            cursor="hand2", pady=9, state=DISABLED,
            command=self._stop_work,
        )
        self._btn_stop.pack(fill=X, pady=(0, 6))

        self._btn_retry = tk.Button(
            p, text="🔄  RETRY ERRORS",
            bg="#2a1800", fg=CLR_WARN, activebackground="#3d2200",
            activeforeground="#fde68a",
            font=("Segoe UI", 10, "bold"), relief=FLAT,
            cursor="hand2", pady=7, state=DISABLED,
            command=self._retry_errors,
        )
        self._btn_retry.pack(fill=X)
        ToolTip(self._btn_retry, "Re-analyze all videos that returned an error")


    # ── Right Panel (Notebook with 2 tabs) ──────────────────────────────────────

    def _build_right(self, p):
        self._tab_notebook = ttk.Notebook(p)
        self._tab_notebook.pack(fill=BOTH, expand=True)

        tab1 = ttk.Frame(self._tab_notebook)
        self._tab_notebook.add(tab1, text="  📋  Analyze & Select  ")

        tab2 = ttk.Frame(self._tab_notebook)
        self._tab_notebook.add(tab2, text="  ✏️  Edit & Export  ")

        self._build_tab1(tab1)
        self._build_tab2(tab2)

    # ── Tab 1: Analyze & Select ───────────────────────────────────────────────

    def _build_tab1(self, p):
        p.configure(padding=(14, 8, 0, 14))

        # ── Scrollable upper section ─────────────────────────────────────────
        # Holds: VIDEO QUEUE, RESULTS, Titles, and Action Buttons.
        # CLIP PREVIEW + LOG are kept fixed at the bottom (always visible).
        upper_outer = ttk.Frame(p)
        upper_outer.pack(fill=BOTH, expand=True)

        upper_canvas = tk.Canvas(upper_outer, bg=CLR_BG, highlightthickness=0)
        upper_sb = ttk.Scrollbar(upper_outer, orient=VERTICAL, command=upper_canvas.yview)
        upper_canvas.configure(yscrollcommand=upper_sb.set)
        upper_sb.pack(side=RIGHT, fill=Y)
        upper_canvas.pack(side=LEFT, fill=BOTH, expand=True)

        scroll_content = ttk.Frame(upper_canvas)
        scroll_win = upper_canvas.create_window((0, 0), window=scroll_content, anchor="nw")

        scroll_content.bind("<Configure>",
            lambda e: upper_canvas.configure(scrollregion=upper_canvas.bbox("all")))
        upper_canvas.bind("<Configure>",
            lambda e: upper_canvas.itemconfig(scroll_win, width=e.width))

        # Mousewheel only active when hovering over this panel
        def _mw(e): upper_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        upper_canvas.bind("<Enter>",  lambda e: upper_canvas.bind_all("<MouseWheel>", _mw))
        upper_canvas.bind("<Leave>",  lambda e: upper_canvas.unbind_all("<MouseWheel>"))

        # All top-section widgets go into scroll_content, aliased as p_top
        p_top = scroll_content

        # ── VIDEO QUEUE (Treeview) ───────────────────────────────────────
        ttk.Label(p_top, text="VIDEO QUEUE", style="BgSection.TLabel").pack(
            anchor=W, pady=(0, 4))

        queue_frame = ttk.Frame(p_top)
        queue_frame.pack(fill=X, pady=(0, 8))

        self._queue = ttk.Treeview(
            queue_frame,
            columns=("icon", "name", "status"),
            show="headings",
            height=7,
            style="Queue.Treeview",
            selectmode="browse",
        )
        self._queue.heading("icon",   text="")
        self._queue.heading("name",   text="Video File")
        self._queue.heading("status", text="Status")
        self._queue.column("icon",   width=28,  minwidth=28,  stretch=False, anchor=W)
        self._queue.column("name",   width=260, minwidth=120, anchor=W)
        self._queue.column("status", width=140, minwidth=80,  anchor=W)

        # Tag colors for statuses
        self._queue.tag_configure(ST_QUEUED,    foreground=CLR_DIM)
        self._queue.tag_configure(ST_UPLOADING, foreground=CLR_WARN)
        self._queue.tag_configure(ST_ANALYZING, foreground=CLR_WARN)
        self._queue.tag_configure(ST_DONE,      foreground=CLR_SUCCESS)
        self._queue.tag_configure(ST_ERROR,     foreground=CLR_ERROR)

        q_sb = ttk.Scrollbar(queue_frame, orient=VERTICAL, command=self._queue.yview)
        self._queue.configure(yscrollcommand=q_sb.set)
        q_sb.pack(side=RIGHT, fill=Y)
        self._queue.pack(fill=X)
        self._queue.bind("<<TreeviewSelect>>", self._on_queue_select)

        ttk.Separator(p_top, orient=HORIZONTAL).pack(fill=X, pady=(0, 8))

        # ── RESULTS + CUT ─────────────────────────────────────────────────
        results_head = ttk.Frame(p_top)
        results_head.pack(fill=X, pady=(0, 4))
        ttk.Label(results_head, text="RESULTS", style="BgSection.TLabel").pack(side=LEFT)
        self._results_video_lbl = ttk.Label(
            results_head, text="— select a completed video above —",
            font=("Segoe UI", 9), foreground=CLR_DIM)
        self._results_video_lbl.pack(side=LEFT, padx=(8, 0))

        cand_row = ttk.Frame(p_top)
        cand_row.pack(fill=X, pady=(0, 4))
        ttk.Label(cand_row, text="Candidate:").pack(side=LEFT, padx=(0, 6))
        self._cand_var = tk.StringVar(value="—")
        self._cand_box = ttk.Combobox(cand_row, textvariable=self._cand_var,
                                      state="readonly", width=44)
        self._cand_box.pack(side=LEFT, fill=X, expand=True)
        self._cand_box.bind("<<ComboboxSelected>>", self._on_candidate_selected)

        self._reason_txt = scrolledtext.ScrolledText(
            p_top, bg=CLR_INPUT_BG, fg=CLR_DIM,
            font=("Segoe UI", 9), height=3, wrap=WORD,
            state=DISABLED, borderwidth=1, relief=SUNKEN,
        )
        self._reason_txt.pack(fill=X, pady=(0, 6))

        tk.Label(p_top, text="Viral Titles — click to select & copy:",
                 bg=CLR_BG, fg=CLR_FG2, font=("Segoe UI", 9, "bold")).pack(
            anchor=W, pady=(4, 4))
        self._title_btns: list[tk.Button] = []
        for i in range(5):
            btn = tk.Button(
                p_top, text=f"{i+1}. —",
                bg=CLR_SURFACE, fg=CLR_FG,
                font=("Segoe UI", 9), relief=FLAT,
                anchor=W, justify=LEFT,
                wraplength=600, cursor="hand2",
                pady=6, padx=10,
                activebackground=CLR_ACCENT_D,
                highlightbackground=CLR_BORDER, highlightthickness=1,
            )
            btn.pack(fill=X, pady=2)
            self._title_btns.append(btn)

        # CUT button
        self._btn_cut = tk.Button(
            p_top, text="✂  CUT SELECTED CLIP  (exact 16s)",
            bg="#0a2a1e", fg=CLR_SUCCESS,
            activebackground="#0f3d2a", activeforeground="#6ee7b7",
            font=("Segoe UI", 11, "bold"), relief=FLAT,
            cursor="hand2", pady=9,
            state=DISABLED, command=self._start_cut,
        )
        self._btn_cut.pack(fill=X, pady=(10, 0))
        ToolTip(self._btn_cut, "Cut the selected 16-second clip from the source video")

        # Send to Edit Tab button (enabled after a successful cut)
        self._btn_send_edit = tk.Button(
            p_top, text="📤  Send to Edit Tab",
            bg="#0f1e3d", fg="#60a5fa",
            activebackground="#172d5c", activeforeground="#93c5fd",
            font=("Segoe UI", 10, "bold"), relief=FLAT,
            cursor="hand2", pady=7,
            state=DISABLED, command=self._send_to_edit_tab,
        )
        self._btn_send_edit.pack(fill=X, pady=(4, 0))
        ToolTip(self._btn_send_edit, "Add this clip + title to the Edit & Export queue")
        # Dummy label kept for backwards compatibility
        self._reup_title_lbl = tk.Label(p_top, text="", bg=CLR_BG,
                                        fg=CLR_DIM, font=("Segoe UI", 8), wraplength=580)
        self._reup_title_lbl.pack(anchor=W)

        # ── PREVIEW + LOG (side by side) ───────────────────────────────────
        # NOTE: parented to `p` (not p_top) — sits OUTSIDE the scroll area,
        # always visible at the bottom of the tab.
        bottom = ttk.Frame(p)
        bottom.pack(fill=BOTH, expand=False, pady=(6, 0))

        # Preview
        prev_frame = ttk.Frame(bottom, style="Panel.TFrame", padding=6)
        prev_frame.pack(side=LEFT, anchor="nw", expand=False)

        prev_hdr = ttk.Frame(prev_frame, style="Panel.TFrame")
        prev_hdr.pack(fill=X, pady=(0, 4))
        ttk.Label(prev_hdr, text="CLIP PREVIEW", style="Section.TLabel",
                  background=CLR_PANEL).pack(side=LEFT)
        self._prev_lbl = ttk.Label(prev_hdr, text="— select a candidate —",
                                   style="Panel.TLabel", foreground=CLR_DIM,
                                   font=("Segoe UI", 8))
        self._prev_lbl.pack(side=LEFT, padx=(8, 0))

        # Play button lives in the HEADER — always visible regardless of height
        self._btn_play = tk.Button(
            prev_hdr,
            text="▶ Play",
            bg="#1e40af", fg="white",
            font=("Segoe UI", 9, "bold"), relief=FLAT,
            activebackground="#1d4ed8", padx=8, pady=2,
            state=DISABLED,
            command=self._toggle_preview_playback,
        )
        self._btn_play.pack(side=RIGHT, padx=(6, 0))

        self._preview_canvas = tk.Canvas(
            prev_frame, bg="#0d0d1a",
            width=PREVIEW_W, height=PREVIEW_H,
            highlightthickness=1, highlightbackground="#3C3C3C",
        )
        self._preview_canvas.pack(anchor="nw")
        self._draw_preview_placeholder()

        # Instantiate player — canvas is ready
        self._player = VideoPlayer(
            self._preview_canvas, PREVIEW_W, PREVIEW_H,
            on_state_change=self._on_player_state_change,
        )

        # Log
        log_frame = ttk.Frame(bottom, padding=(10, 0, 0, 0))
        log_frame.pack(side=LEFT, fill=BOTH, expand=True)
        ttk.Label(log_frame, text="ACTIVITY LOG", style="BgSection.TLabel").pack(
            anchor=W, pady=(0, 4))
        self._log_widget = scrolledtext.ScrolledText(
            log_frame, bg=CLR_INPUT_BG, fg=CLR_FG,
            font=("Consolas", 8), state=DISABLED,
            wrap=WORD, borderwidth=1, relief=SUNKEN,
        )
        self._log_widget.pack(fill=BOTH, expand=True)
        self._logger = ToolLogger(self._log_widget)

    # ── Tab 2: Edit & Export ─────────────────────────────────────────────────

    def _build_tab2(self, p):
        # ── Top-level: fixed left + scrollable right ──────────────────────────
        outer = ttk.Frame(p)
        outer.pack(fill=BOTH, expand=True)

        # ── Fixed left panel: queue + preview (NEVER scrolls) ─────────────────
        fixed = ttk.Frame(outer, style="Panel.TFrame")
        fixed.pack(side=LEFT, fill=Y, padx=(10, 0), pady=(8, 10))

        # ── Left column: clip queue ───────────────────────────────────────────
        queue_col = ttk.Frame(fixed, style="Panel.TFrame", padding=(6, 6, 6, 6))
        queue_col.pack(side=LEFT, fill=Y, padx=(0, 8))
        queue_col.configure(width=165)
        queue_col.pack_propagate(False)

        # Dynamic queue count label — updated via _update_queue_count_label()
        self._queue_count_var = tk.StringVar(value="QUEUE")
        ttk.Label(queue_col, textvariable=self._queue_count_var,
                  style="Section.TLabel",
                  background=CLR_PANEL).pack(anchor=W, pady=(0, 4))

        # EXTENDED selectmode: Shift+click = range, Ctrl+click = toggle.
        # _on_edit_select still loads only the focused item into the editor;
        # multi-selection is used by bulk Remove.
        self._edit_listbox = tk.Listbox(
            queue_col, bg=CLR_INPUT_BG, fg=CLR_FG,
            font=("Segoe UI", 8), selectbackground="#3730a3",
            activestyle="none", borderwidth=0, highlightthickness=0,
            selectmode=tk.EXTENDED,
        )
        self._edit_listbox.pack(fill=BOTH, expand=True)
        self._edit_listbox.bind("<<ListboxSelect>>", self._on_edit_select)

        tk.Button(
            queue_col, text="🗑 Remove",
            bg="#7f1d1d", fg="white",
            font=("Segoe UI", 8), relief=FLAT, padx=6, pady=3,
            command=self._edit_queue_remove,
        ).pack(fill=X, pady=(6, 0))

        tk.Button(
            queue_col, text="📥 Import 16s Clip",
            bg="#0f766e", fg="white",
            font=("Segoe UI", 8, "bold"), relief=FLAT, padx=6, pady=3,
            command=self._import_16s_clip,
        ).pack(fill=X, pady=(6, 0))

        # ── Middle column: portrait preview canvas (sticky) ───────────────────
        prev_col = ttk.Frame(fixed, style="Panel.TFrame", padding=6)
        prev_col.pack(side=LEFT, fill=Y, padx=(0, 8))

        ttk.Label(prev_col, text="PREVIEW  — drag title │ Draw Mode → blur box",
                  style="Section.TLabel", background=CLR_PANEL).pack(anchor=W, pady=(0, 4))

        self._edit_canvas = tk.Canvas(
            prev_col, width=EDIT_PREV_W, height=EDIT_PREV_H,
            bg="#0d0d1a",
            highlightthickness=1, highlightbackground="#3C3C3C",
            cursor="fleur",
        )
        self._edit_canvas.pack()
        self._draw_edit_placeholder()

        # ── Scrubber bar (seek to any frame in the clip) ──────────────────────
        scrub_row = tk.Frame(prev_col, bg=CLR_PANEL)
        scrub_row.pack(fill=X, pady=(4, 0))
        tk.Label(scrub_row, text="⏱ Seek", bg=CLR_PANEL, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(side=LEFT, padx=(0, 6))
        self._scrub_pos = tk.DoubleVar(value=0.0)
        self._scrub_job = None   # debounce after_id

        def _on_scrub(val):
            # Debounce: cancel any pending regen, schedule new one 80ms later
            if self._scrub_job:
                try:
                    self.after_cancel(self._scrub_job)
                except Exception:
                    pass
            self._scrub_job = self.after(80, _seek_frame)

        def _seek_frame():
            self._scrub_job = None
            if self._edit_sel_idx < 0:
                return
            item = self._edit_queue[self._edit_sel_idx]
            clip = item["clip_path"]
            pct  = self._scrub_pos.get() / 100.0
            # Invalidate frame cache for this clip so next regen uses the seeked frame
            src_key = str(clip)
            # Determine timestamp to seek to
            dur = get_video_duration(clip)
            if dur is None:
                dur = 10.0
            seek_t = max(0.1, pct * dur)
            # Extract frame at seek_t and store in cache
            try:
                tmp = Path(tempfile.mktemp(suffix="_scrub.jpg"))
                subprocess.run(
                    [FFMPEG, "-loglevel", "quiet",
                     "-ss", f"{seek_t:.2f}", "-i", str(clip),
                     "-frames:v", "1", "-q:v", "3", str(tmp)],
                    capture_output=True, timeout=8,
                )
                if tmp.exists():
                    from PIL import Image as _PILImage
                    _img = _PILImage.open(tmp).convert("RGB")
                    _img.load()
                    try: tmp.unlink()
                    except Exception: pass
                    self._frame_cache[src_key] = _img
                    # Also clear bg cache so bg refreshes with new frame
                    for k in list(self._edit_bg_cache.keys()):
                        if k[0] == src_key:
                            del self._edit_bg_cache[k]
                    self._regen_edit_preview()
            except Exception:
                pass

        self._scrub_scale = PremiumScale(
            scrub_row, variable=self._scrub_pos,
            from_=0.0, to=100.0, resolution=0.5,
            value_format="{:.0f}%",
            command=_on_scrub,
        )
        self._scrub_scale.pack(side=LEFT, fill=X, expand=True)
        ToolTip(scrub_row, "Drag to seek to any frame in the clip — preview updates automatically")

        # ── Play / Stop preview button ────────────────────────────────────────
        play_row = tk.Frame(prev_col, bg=CLR_PANEL)
        play_row.pack(fill=X, pady=(4, 0))
        self._edit_play_job   = None   # after() loop id
        self._edit_play_proc  = None   # ffmpeg Popen for frame pipe
        self._edit_playing    = False

        def _toggle_play():
            if self._edit_playing:
                self._stop_edit_play()
            else:
                self._start_edit_play()

        self._btn_edit_play = tk.Button(
            play_row, text="▶  Play Preview",
            bg=CLR_ACCENT_D, fg=CLR_FG,
            activebackground=CLR_ACCENT, activeforeground=CLR_FG,
            font=("Segoe UI", 9, "bold"), relief=FLAT, cursor="hand2",
            pady=4, command=_toggle_play,
        )
        self._btn_edit_play.pack(fill=X)
        ToolTip(self._btn_edit_play, "Play the clip as a live preview in the canvas")

        # Draw-mode and resize-mode must be initialised before any canvas event fires
        self._edit_draw_mode   = False
        self._edit_resize_mode = False
        self._edit_canvas.bind("<Button-1>",        self._on_edit_drag_start)
        self._edit_canvas.bind("<B1-Motion>",       self._on_edit_drag)
        self._edit_canvas.bind("<ButtonRelease-1>", self._on_edit_drag_end)
        self._edit_canvas.bind("<Motion>",          self._on_edit_motion)
        # D/d key → toggle draw mode (focus must be on canvas or tab frame)
        self._edit_canvas.bind("<d>", lambda e: self._toggle_draw_mode())
        self._edit_canvas.bind("<D>", lambda e: self._toggle_draw_mode())

        # ── Right side: scrollable controls + pinned export footer ────────────
        right_outer = ttk.Frame(outer)
        right_outer.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10), pady=(8, 10))

        # Pinned Export footer (always visible at the bottom)
        footer = ttk.Frame(right_outer)
        footer.pack(side=BOTTOM, fill=X, pady=(6, 0))

        # ── Export Settings panel (collapsible) ──────────────────────────────
        exp_outer = tk.Frame(footer, bg=CLR_BORDER, bd=0)
        exp_outer.pack(fill=X, pady=(0, 6))
        exp_inner = tk.Frame(exp_outer, bg=CLR_SURFACE)
        exp_inner.pack(fill=X, padx=1, pady=1)

        # Header row with toggle
        exp_hdr = tk.Frame(exp_inner, bg=CLR_SURFACE)
        exp_hdr.pack(fill=X, pady=(4, 0))
        self._exp_collapsed = tk.BooleanVar(value=False)
        self._exp_chevron = tk.Label(
            exp_hdr, text="▾", bg=CLR_SURFACE, fg=CLR_ACCENT,
            font=("Segoe UI", 11), cursor="hand2")
        self._exp_chevron.pack(side=LEFT, padx=(6, 2))
        tk.Label(exp_hdr, text="⚙️  Export Settings",
                 bg=CLR_SURFACE, fg=CLR_FG2, font=("Segoe UI", 8, "bold"),
                 cursor="hand2").pack(side=LEFT)

        # Content frame that can be shown/hidden
        exp_cfg_frame = tk.Frame(exp_inner, bg=CLR_SURFACE)
        exp_cfg_frame.pack(fill=X, padx=6, pady=(2, 6))

        def _toggle_exp_settings(*_):
            if self._exp_collapsed.get():
                exp_cfg_frame.pack_forget()
                self._exp_chevron.config(text="▸")
                self._exp_collapsed.set(False)   # flip: collapsed=True means hidden
            else:
                exp_cfg_frame.pack(fill=X, padx=6, pady=(2, 6))
                self._exp_chevron.config(text="▾")
                self._exp_collapsed.set(True)

        exp_hdr.bind("<Button-1>", _toggle_exp_settings)
        self._exp_chevron.bind("<Button-1>", _toggle_exp_settings)
        for _w in exp_hdr.winfo_children():
            _w.bind("<Button-1>", _toggle_exp_settings)

        _RC = self._cfg.get("render_cfg", {})

        def _row(parent, label_text):
            r = tk.Frame(parent, bg=CLR_SURFACE)
            r.pack(fill=X, pady=1)
            tk.Label(r, text=label_text, bg=CLR_SURFACE, fg=CLR_FG2,
                     font=("Segoe UI", 8), width=11, anchor=W).pack(side=LEFT)
            return r

        # Resolution
        _res_opts = ["1080×1920 (Full HD)", "720×1280 (HD)", "540×960 (SD)"]
        _res_map   = {
            "1080×1920 (Full HD)": (1080, 1920),
            "720×1280 (HD)":        (720,  1280),
            "540×960 (SD)":         (540,   960),
        }
        _res_default = next(
            (k for k, (w, h) in _res_map.items()
             if w == _RC.get("width", 1080) and h == _RC.get("height", 1920)),
            "1080×1920 (Full HD)"
        )
        self._export_res_var = tk.StringVar(value=_res_default)
        r = _row(exp_cfg_frame, "Resolution")
        ttk.Combobox(r, textvariable=self._export_res_var,
                     values=_res_opts, state="readonly", width=18,
                     font=("Segoe UI", 8)).pack(side=LEFT)

        # Video encoder — only show encoders available on this machine
        _all_encs = [
            ("libx264",   "H.264 (CPU)"),
            ("libx265",   "H.265/HEVC (CPU)"),
            ("h264_nvenc", "H.264 NVENC (NVIDIA)"),
            ("hevc_nvenc", "HEVC NVENC (NVIDIA)"),
            ("h264_qsv",  "H.264 QSV (Intel)"),
            ("hevc_qsv",  "HEVC QSV (Intel)"),
        ]
        _enc_labels = [lbl for enc, lbl in _all_encs if enc in AVAILABLE_ENCODERS]
        _enc_to_id  = {lbl: enc for enc, lbl in _all_encs}
        _id_to_lbl  = {enc: lbl for enc, lbl in _all_encs}
        _enc_default_lbl = _id_to_lbl.get(_RC.get("vcodec", "libx264"), "H.264 (CPU)")
        self._export_enc_var = tk.StringVar(value=_enc_default_lbl)
        r = _row(exp_cfg_frame, "Encoder")
        self._enc_combo = ttk.Combobox(r, textvariable=self._export_enc_var,
                                        values=_enc_labels, state="readonly", width=18,
                                        font=("Segoe UI", 8))
        self._enc_combo.pack(side=LEFT)
        self._enc_to_id = _enc_to_id   # save for _get_render_cfg

        # FPS
        _fps_opts = ["Original", "24", "30", "60"]
        _fps_default = str(_RC.get("fps", "")) or "Original"
        if _fps_default not in _fps_opts:
            _fps_default = "Original"
        self._export_fps_var = tk.StringVar(value=_fps_default)
        r = _row(exp_cfg_frame, "Frame Rate")
        ttk.Combobox(r, textvariable=self._export_fps_var,
                     values=_fps_opts, state="readonly", width=18,
                     font=("Segoe UI", 8)).pack(side=LEFT)

        # Quality (CRF)
        self._export_crf_var = tk.IntVar(value=int(_RC.get("crf", 20)))
        r = _row(exp_cfg_frame, "Quality (CRF)")
        tk.Scale(
            r, variable=self._export_crf_var,
            from_=15, to=35, orient="horizontal",
            bg=CLR_SURFACE, fg=CLR_FG, troughcolor=CLR_BG,
            highlightthickness=0, length=100, showvalue=True,
            font=("Segoe UI", 7),
        ).pack(side=LEFT)
        tk.Label(r, text="← better", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 7)).pack(side=LEFT, padx=(4, 0))

        # Preset
        _preset_opts = ["ultrafast", "fast", "medium", "slow"]
        self._export_preset_var = tk.StringVar(value=_RC.get("preset", "fast"))
        r = _row(exp_cfg_frame, "Preset")
        ttk.Combobox(r, textvariable=self._export_preset_var,
                     values=_preset_opts, state="readonly", width=18,
                     font=("Segoe UI", 8)).pack(side=LEFT)
        ToolTip(r, "ultrafast = fastest encode / largest file;  slow = best compression")

        # Concurrent export threads (GPU users can run 2–4 in parallel)
        self._export_threads_var = tk.IntVar(value=int(_RC.get("export_threads", 1)))
        r = _row(exp_cfg_frame, "Threads")
        tk.Scale(
            r, variable=self._export_threads_var,
            from_=1, to=4, orient="horizontal", resolution=1,
            bg=CLR_SURFACE, fg=CLR_FG, troughcolor=CLR_BG,
            highlightthickness=0, length=100, showvalue=True,
            font=("Segoe UI", 7),
        ).pack(side=LEFT)
        tk.Label(r, text="parallel exports (GPU: 2–4 recommended)",
                 bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 7)
                 ).pack(side=LEFT, padx=(6, 0))
        ToolTip(r, "Number of clips to encode simultaneously.\n"
                   "CPU encoders: keep at 1. NVENC/QSV: 2–4 is safe.")

        self._btn_export_one = AccentButton(
            footer, text="Export Current", icon="📱",
            command=self._start_reup, state=DISABLED,
            font=("Segoe UI", 10, "bold"), pady=8,
        )
        self._btn_export_one.pack(fill=X, pady=(0, 4))
        ToolTip(self._btn_export_one, "Render the currently selected clip as a 9:16 portrait video")

        self._btn_export_all = tk.Button(
            footer, text="📦  Export All",
            bg="#0f766e", fg="white",
            activebackground="#0d6b63", activeforeground="#99f6e4",
            font=("Segoe UI", 10, "bold"), relief=FLAT,
            cursor="hand2", pady=8, state=DISABLED,
            command=self._start_export_all,
        )
        self._btn_export_all.pack(fill=X, pady=(0, 4))
        ToolTip(self._btn_export_all, "Render ALL clips in the queue as 9:16 portrait videos")

        # ── Render progress bar (hidden until export starts) ──────────────────
        self._render_progress_frame = tk.Frame(footer, bg=CLR_BG)
        self._render_progress_frame.pack(fill=X, pady=(0, 4))
        self._render_progress_var  = tk.DoubleVar(value=0.0)
        self._render_progress_lbl  = tk.Label(
            self._render_progress_frame,
            text="", bg=CLR_BG, fg=CLR_FG2, font=("Segoe UI", 8)
        )
        self._render_progress_lbl.pack(anchor=E)
        self._render_progress_bar = ttk.Progressbar(
            self._render_progress_frame,
            variable=self._render_progress_var,
            maximum=100, mode="determinate", length=200,
        )
        self._render_progress_bar.pack(fill=X)
        self._render_progress_frame.pack_forget()  # hidden by default

        def _open_output():
            folder = self._output_var.get().strip()
            if folder and Path(folder).exists():
                os.startfile(folder)
            else:
                self._toast("No output folder configured", kind="warning")

        SecondaryButton(footer, text="Open Output Folder", icon="📂",
                        command=_open_output,
                        font=("Segoe UI", 8, "bold"), pady=4).pack(
            fill=X, pady=(0, 2))

        self._btn_reup = self._btn_export_one   # alias for worker callbacks


        # Scrollable controls area (fills remaining space above footer)
        scroll_canvas = tk.Canvas(right_outer, bg=CLR_BG, highlightthickness=0)
        sb = ttk.Scrollbar(right_outer, orient=VERTICAL, command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        scroll_canvas.pack(side=LEFT, fill=BOTH, expand=True)

        ctrl_frame = ttk.Frame(scroll_canvas)
        ctrl_win = scroll_canvas.create_window((0, 0), window=ctrl_frame, anchor="nw")

        def _on_ctrl_resize(event):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        ctrl_frame.bind("<Configure>", _on_ctrl_resize)

        def _on_scroll_resize(event):
            scroll_canvas.itemconfig(ctrl_win, width=event.width)
        scroll_canvas.bind("<Configure>", _on_scroll_resize)

        def _on_mouse_wheel(event):
            scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mw(event):
            scroll_canvas.bind_all("<MouseWheel>", _on_mouse_wheel)
        def _unbind_mw(event):
            scroll_canvas.unbind_all("<MouseWheel>")
        scroll_canvas.bind("<Enter>", _bind_mw)
        scroll_canvas.bind("<Leave>", _unbind_mw)

        # ── Right column: controls (scrollable) ───────────────────────────────
        ctrl_col = ttk.Frame(ctrl_frame)
        ctrl_col.pack(fill=BOTH, expand=True, padx=10, pady=8)
        self._build_tab2_controls(ctrl_col)

    def _build_tab2_controls(self, p):
        """Right-side controls panel for Tab 2."""

        # ── Per-instance settings-mode state ─────────────────────────────────
        _excl = {"blur_boxes", "text_x", "text_y"}
        self._global_edit_state = {k: v for k, v in _default_edit_state().items()
                                   if k not in _excl}
        self._edit_sync_all = tk.BooleanVar(value=False)

        # ── Settings Mode Toggle ─────────────────────────────────────────────
        mode_card = SectionCard(p, "Settings Mode", collapsible=False)
        mode_card.pack(fill=X, pady=(0, 6))
        mc = mode_card.content

        for _lbl, _val in [("🔓  Per Video", False), ("🔗  Sync All", True)]:
            tk.Radiobutton(
                mc, text=_lbl, variable=self._edit_sync_all, value=_val,
                command=self._on_sync_mode_toggle,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, activeforeground=CLR_ACCENT_H,
                font=("Segoe UI", 9), indicatoron=True,
            ).pack(side=LEFT, padx=(0, 12))

        self._sync_status_lbl = tk.Label(
            mc, text="", font=("Segoe UI", 7, "italic"),
            fg=CLR_DIM, bg=CLR_SURFACE)
        self._sync_status_lbl.pack(side=RIGHT, padx=4)
        ToolTip(mode_card, "Per Video: each clip has independent settings.\n"
                "Sync All: changing any control updates all clips at once.")

        # ── Title Text Content ────────────────────────────────────────────────
        title_card = SectionCard(p, "Title Text", collapsible=False)
        title_card.pack(fill=X, pady=(0, 6))
        tc = title_card.content

        self._edit_title_text_var = tk.StringVar()
        self._edit_title_entry = tk.Entry(
            tc, textvariable=self._edit_title_text_var,
            bg=CLR_INPUT_BG, fg=CLR_FG, insertbackground=CLR_FG,
            font=("Segoe UI", 9), relief=FLAT, bd=0,
            highlightbackground=CLR_BORDER, highlightthickness=1,
        )
        self._edit_title_entry.pack(fill=X, pady=(0, 4), ipady=4)
        self._edit_title_text_var.trace_add("write", self._on_title_text_modified)
        ToolTip(self._edit_title_entry, "Edit the title text that will appear on the video")

        # Suggestions frame
        self._edit_suggestions_frame = tk.Frame(tc, bg=CLR_SURFACE)
        self._edit_suggestions_frame.pack(fill=X, pady=(4, 0))

        # ── Source Mask ───────────────────────────────────────────────────────
        mask_card = SectionCard(p, "Source Mask")
        mask_card.pack(fill=X, pady=(0, 6))
        mc2 = mask_card.content

        tk.Label(mc2, text="Crop edges of the source video to hide banners/watermarks.",
                 bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 8),
                 wraplength=300, justify=LEFT).pack(anchor=W, pady=(0, 4))

        # Mask position selector
        _mpos_row = tk.Frame(mc2, bg=CLR_SURFACE)
        _mpos_row.pack(anchor=W, pady=(0, 6))
        self._edit_mask_position = tk.StringVar(value="top")
        for _ml, _mv in [("Top", "top"), ("Bottom", "bottom"), ("Both", "both")]:
            tk.Radiobutton(
                _mpos_row, text=_ml,
                variable=self._edit_mask_position, value=_mv,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, font=("Segoe UI", 9),
                cursor="hand2", command=self._regen_edit_preview,
            ).pack(side=LEFT, padx=(0, 12))

        tk.Label(mc2, text="Top Crop", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._edit_source_mask = tk.DoubleVar(value=0.0)
        PremiumScale(
            mc2, variable=self._edit_source_mask,
            from_=0.0, to=0.30, resolution=0.01,
            value_format="{:.0%}",
            command=lambda v: self._regen_edit_preview(),
        ).pack(fill=X)

        tk.Label(mc2, text="Bottom Crop", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(6, 0))
        self._edit_source_mask_bottom = tk.DoubleVar(value=0.0)
        PremiumScale(
            mc2, variable=self._edit_source_mask_bottom,
            from_=0.0, to=0.30, resolution=0.01,
            value_format="{:.0%}",
            command=lambda v: self._regen_edit_preview(),
        ).pack(fill=X)
        ToolTip(mask_card, "Crop top/bottom edges of source video to remove banners or watermarks")

        # ── Blur Regions ─────────────────────────────────────────────────────
        blur_card = SectionCard(p, "Blur Regions")
        blur_card.pack(fill=X, pady=(0, 6))
        bc = blur_card.content

        tk.Label(bc, text="Enable Draw Mode → click-drag on preview to add blur boxes.",
                 bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 8),
                 wraplength=300, justify=LEFT).pack(anchor=W, pady=(0, 6))

        draw_row = tk.Frame(bc, bg=CLR_SURFACE)
        draw_row.pack(fill=X, pady=(0, 4))
        self._btn_draw_mode = tk.Button(
            draw_row, text="✏  Draw Mode: OFF",
            bg="#0f1e3d", fg="#60a5fa",
            activebackground="#172d5c", activeforeground="#93c5fd",
            font=("Segoe UI", 9, "bold"), relief=FLAT,
            cursor="hand2", padx=8, pady=5,
            command=self._toggle_draw_mode,
        )
        self._btn_draw_mode.pack(side=LEFT, fill=X, expand=True)
        ToolTip(self._btn_draw_mode, "Toggle blur-box draw mode — shortcut: D")
        DangerButton(draw_row, text="Clear All", icon="🗑",
                     command=self._clear_blur_boxes,
                     font=("Segoe UI", 8, "bold"), pady=4).pack(
            side=RIGHT, padx=(4, 0))

        # ── Mode selector: Blur vs Delogo ──────────────────────────────────
        mode_row = tk.Frame(bc, bg=CLR_SURFACE)
        mode_row.pack(fill=X, pady=(0, 4))
        tk.Label(mode_row, text="Next box mode:", bg=CLR_SURFACE,
                 fg=CLR_FG2, font=("Segoe UI", 8)).pack(side=LEFT, padx=(0, 6))
        self._blur_box_mode = tk.StringVar(value="blur")
        for _m_val, _m_lbl in [("blur", "🫧 Blur"), ("delogo", "🔍 Delogo (inpaint)")]:
            tk.Radiobutton(
                mode_row, text=_m_lbl, variable=self._blur_box_mode, value=_m_val,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_SURFACE,
                activebackground=CLR_SURFACE, font=("Segoe UI", 8),
                relief=FLAT, cursor="hand2",
            ).pack(side=LEFT, padx=(0, 8))

        # ── Auto-detect buttons ─────────────────────────────────────────────
        _auto_row = tk.Frame(bc, bg=CLR_SURFACE)
        _auto_row.pack(fill=X, pady=(0, 4))

        def _autodetect_logo():
            if self._edit_sel_idx < 0:
                messagebox.showwarning("No clip", "Select a clip first.", parent=self)
                return
            clip = self._edit_queue[self._edit_sel_idx].get("clip_path", "")
            if not clip:
                return
            self._blur_btn_logo.config(state=DISABLED, text="🔍 Detecting…")
            def _run():
                bbox = detect_logo_bbox(clip)
                self.after(0, _on_logo_result, bbox)
            def _on_logo_result(bbox):
                self._blur_btn_logo.config(state=NORMAL, text="🔍 Auto-detect Logo")
                if bbox is None:
                    messagebox.showinfo("Not found",
                        "No static logo/watermark detected in this clip.", parent=self)
                    return
                x, y, w, h = bbox
                box = {"x": x, "y": y, "w": w, "h": h,
                       "mode": self._blur_box_mode.get()}
                self._edit_queue[self._edit_sel_idx]["state"].setdefault("blur_boxes", []).append(box)
                self._refresh_blur_listbox()
                self._regen_edit_preview()
            threading.Thread(target=_run, daemon=True).start()

        def _autodetect_subtitle():
            if self._edit_sel_idx < 0:
                messagebox.showwarning("No clip", "Select a clip first.", parent=self)
                return
            clip = self._edit_queue[self._edit_sel_idx].get("clip_path", "")
            if not clip:
                return
            self._blur_btn_sub.config(state=DISABLED, text="📝 Detecting…")
            def _run():
                result = detect_subtitle_region(clip)
                self.after(0, _on_sub_result, result)
            def _on_sub_result(result):
                self._blur_btn_sub.config(state=NORMAL, text="📝 Auto-detect Subtitle")
                if result is None:
                    messagebox.showinfo("Not found",
                        "No subtitle band detected in this clip.", parent=self)
                    return
                x, y, w, h, start_time = result
                box = {"x": x, "y": y, "w": w, "h": h,
                       "mode": "delogo",  # delogo is better for subtitle removal
                       "start_time": round(start_time, 3)}
                self._edit_queue[self._edit_sel_idx]["state"].setdefault("blur_boxes", []).append(box)
                self._refresh_blur_listbox()
                self._regen_edit_preview()
                messagebox.showinfo("Detected",
                    f"Subtitle band detected at y={y} (starts at {start_time:.1f}s).\n"
                    "Added as Delogo box — you can adjust in the list.", parent=self)
            threading.Thread(target=_run, daemon=True).start()

        self._blur_btn_logo = tk.Button(
            _auto_row, text="🔍 Auto-detect Logo",
            bg="#0f1e3d", fg="#60a5fa",
            activebackground="#172d5c", activeforeground="#93c5fd",
            font=("Segoe UI", 8, "bold"), relief=FLAT,
            cursor="hand2", padx=8, pady=3,
            command=_autodetect_logo,
        )
        self._blur_btn_logo.pack(side=LEFT, fill=X, expand=True, padx=(0, 3))

        self._blur_btn_sub = tk.Button(
            _auto_row, text="📝 Auto-detect Subtitle",
            bg="#1a2a1a", fg="#86efac",
            activebackground="#223322", activeforeground="#a7f3d0",
            font=("Segoe UI", 8, "bold"), relief=FLAT,
            cursor="hand2", padx=8, pady=3,
            command=_autodetect_subtitle,
        )
        self._blur_btn_sub.pack(side=LEFT, fill=X, expand=True)

        self._blur_listbox = tk.Listbox(
            bc, bg=CLR_INPUT_BG, fg=CLR_FG,
            font=("Consolas", 8), height=3,
            selectbackground=CLR_ACCENT_D,
            activestyle="none", borderwidth=0, highlightthickness=0,
        )
        self._blur_listbox.pack(fill=X, pady=(4, 2))

        # Action row: remove + track
        _blur_action_row = tk.Frame(bc, bg=CLR_SURFACE)
        _blur_action_row.pack(fill=X, pady=(0, 4))
        SecondaryButton(_blur_action_row, text="Remove Selected",
                        command=self._remove_selected_blur_box,
                        font=("Segoe UI", 8), pady=3).pack(side=LEFT)

        # Track Object button — launches OpenCV CSRT tracking popup
        tk.Button(
            _blur_action_row, text="🎯 Track Object",
            bg="#1a2e1a", fg="#4ade80",
            activebackground="#223322", activeforeground="#86efac",
            font=("Segoe UI", 8, "bold"), relief=FLAT,
            cursor="hand2", padx=8, pady=3,
            command=self._open_track_popup,
        ).pack(side=RIGHT)

        ToolTip(blur_card, "Draw blur boxes over sensitive regions (faces, plates, badges)\n"
                "🔍 Auto-detect Logo: finds static watermark via temporal variance\n"
                "📝 Auto-detect Subtitle: finds burned-in subtitle band + start time\n"
                "🎯 Track Object: select a region on frame 1 → blur follows it automatically")

        # ── Font ─────────────────────────────────────────────────────────────
        font_card = SectionCard(p, "Font")
        font_card.pack(fill=X, pady=(0, 6))
        fc = font_card.content

        self._edit_font_var = tk.StringVar(value="Impact")
        font_combo = ttk.Combobox(
            fc, textvariable=self._edit_font_var,
            values=["Impact", "Arial Bold", "Arial",
                    "Segoe UI Bold", "Calibri Bold", "Verdana Bold",
                    "Comic Sans", "Trebuchet Bold"],
            state="readonly", width=18,
        )
        font_combo.pack(anchor=W, pady=(0, 6))
        self._edit_font_var.trace_add("write", lambda *_: self._regen_edit_preview())
        ToolTip(font_combo, "Choose the title font family")

        tk.Label(fc, text="Font Size", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._edit_font_size = tk.IntVar(value=52)
        PremiumScale(fc, variable=self._edit_font_size,
                     from_=24, to=80, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X, pady=(0, 4))

        # Bold / Italic / Decorations row
        style_row = tk.Frame(fc, bg=CLR_SURFACE)
        style_row.pack(anchor=W, pady=(2, 0))
        self._edit_font_bold = tk.BooleanVar(value=False)
        tk.Checkbutton(
            style_row, text="B",
            variable=self._edit_font_bold,
            bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE, font=("Segoe UI", 10, "bold"),
            command=self._regen_edit_preview,
        ).pack(side=LEFT, padx=(0, 4))

        self._edit_font_italic = tk.BooleanVar(value=False)
        self._edit_text_decoration = tk.StringVar(value="none")

        tk.Checkbutton(
            style_row, text="I",
            variable=self._edit_font_italic,
            font=("Segoe UI", 10, "italic"),
            bg=CLR_SURFACE, fg=CLR_FG2, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE,
            command=self._regen_edit_preview,
        ).pack(side=LEFT, padx=(0, 4))

        def _set_decoration(val):
            cur = self._edit_text_decoration.get()
            self._edit_text_decoration.set("none" if cur == val else val)
            _u_btn.config(relief=SUNKEN if self._edit_text_decoration.get() == "underline"    else FLAT)
            _s_btn.config(relief=SUNKEN if self._edit_text_decoration.get() == "strikethrough" else FLAT)
            self._regen_edit_preview()

        _u_btn = tk.Button(
            style_row, text="U",
            font=("Segoe UI", 10, "underline"),
            bg=CLR_SURFACE, fg=CLR_FG2, relief=FLAT, padx=4, pady=1,
            cursor="hand2", activebackground=CLR_ACCENT_D,
            command=lambda: _set_decoration("underline"),
        )
        _u_btn.pack(side=LEFT, padx=(0, 4))
        _s_btn = tk.Button(
            style_row, text="S",
            font=("Segoe UI", 10, "overstrike"),
            bg=CLR_SURFACE, fg=CLR_FG2, relief=FLAT, padx=4, pady=1,
            cursor="hand2", activebackground=CLR_ACCENT_D,
            command=lambda: _set_decoration("strikethrough"),
        )
        _s_btn.pack(side=LEFT)

        # Alignment
        tk.Label(fc, text="Alignment", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(8, 2))
        self._edit_align_var = tk.StringVar(value="left")
        align_row = tk.Frame(fc, bg=CLR_SURFACE)
        align_row.pack(anchor=W)
        for label, val in [("◀ Left", "left"), ("≡ Center", "center"), ("Right ▶", "right")]:
            tk.Radiobutton(
                align_row, text=label,
                variable=self._edit_align_var, value=val,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, font=("Segoe UI", 8),
                cursor="hand2",
                command=self._regen_edit_preview,
            ).pack(side=LEFT, padx=(0, 8))

        # Title box width
        tk.Label(fc, text="Title Box Width", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(8, 0))
        self._edit_title_wrap_pct = tk.DoubleVar(value=1.0)
        PremiumScale(fc, variable=self._edit_title_wrap_pct,
                     from_=0.3, to=1.0, resolution=0.05,
                     value_format="{:.0%}",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)
        ToolTip(font_card, "Font, size, style and alignment for the title overlay")

        # ── Text Color ────────────────────────────────────────────────────────
        color_card = SectionCard(p, "Text Color")
        color_card.pack(fill=X, pady=(0, 6))
        cc = color_card.content

        self._edit_color_var     = tk.StringVar(value="white")
        self._edit_color_hex_var = tk.StringVar(value="#FFFFFF")

        def _pick_color():
            from tkinter import colorchooser
            initial = self._edit_color_hex_var.get()
            result  = colorchooser.askcolor(color=initial, title="Text colour")
            if result and result[1]:
                self._edit_color_hex_var.set(result[1].upper())
                self._edit_color_swatch.config(bg=result[1])
                _hex_entry.delete(0, END)
                _hex_entry.insert(0, result[1].upper())
                self._regen_edit_preview()

        def _hex_changed(*_):
            v = _hex_entry.get().strip()
            if len(v) == 7 and v.startswith("#"):
                try:
                    self._edit_color_swatch.config(bg=v)
                    self._edit_color_hex_var.set(v.upper())
                    self._regen_edit_preview()
                except Exception:
                    pass

        clr_row = tk.Frame(cc, bg=CLR_SURFACE)
        clr_row.pack(fill=X, pady=(0, 6))
        self._edit_color_swatch = tk.Label(
            clr_row, bg="#FFFFFF", width=3,
            relief="solid", cursor="hand2",
        )
        self._edit_color_swatch.pack(side=LEFT, padx=(0, 8))
        self._edit_color_swatch.bind("<Button-1>", lambda e: _pick_color())
        _hex_entry = tk.Entry(
            clr_row, textvariable=self._edit_color_hex_var,
            bg=CLR_INPUT_BG, fg=CLR_FG, insertbackground=CLR_FG,
            font=("Segoe UI", 9), relief=FLAT, width=9,
            highlightbackground=CLR_BORDER, highlightthickness=1,
        )
        _hex_entry.pack(side=LEFT)
        _hex_entry.bind("<FocusOut>", _hex_changed)
        _hex_entry.bind("<Return>",   _hex_changed)
        SecondaryButton(clr_row, text="Pick…", command=_pick_color,
                        font=("Segoe UI", 8), pady=2, padx=6).pack(
            side=LEFT, padx=(6, 0))

        # Color presets
        preset_row = tk.Frame(cc, bg=CLR_SURFACE)
        preset_row.pack(anchor=W)
        for _label, _hex_val, _fg in [
            ("White",  "#FFFFFF", "#111"),
            ("Yellow", "#FFF000", "#333"),
            ("Black",  "#000000", "#ccc"),
            ("Red",    "#FF3333", "#fff"),
            ("Cyan",   "#00FFFF", "#111"),
        ]:
            def _set_preset(h=_hex_val):
                self._edit_color_hex_var.set(h)
                self._edit_color_swatch.config(bg=h)
                _hex_entry.delete(0, END)
                _hex_entry.insert(0, h)
                self._regen_edit_preview()
            tk.Button(
                preset_row, text=_label,
                bg=_hex_val, fg=_fg, relief=FLAT,
                font=("Segoe UI", 7, "bold"), padx=5, pady=2,
                cursor="hand2",
                command=_set_preset,
            ).pack(side=LEFT, padx=(0, 3), pady=(4, 0))
        ToolTip(color_card, "Text fill color — use the hex field for exact values")

        # ── Text Stroke (Border) ──────────────────────────────────────────────
        tk.Label(cc, text="Stroke / Border", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8, "bold")).pack(anchor=W, pady=(10, 2))

        self._edit_stroke_width    = tk.IntVar(value=0)
        self._edit_stroke_color_hex = tk.StringVar(value="#000000")

        _stk_w_row = tk.Frame(cc, bg=CLR_SURFACE)
        _stk_w_row.pack(fill=X)
        tk.Label(_stk_w_row, text="Width:", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8), width=6, anchor=W).pack(side=LEFT)
        PremiumScale(_stk_w_row, variable=self._edit_stroke_width,
                     from_=0, to=8, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(side=LEFT, fill=X, expand=True)

        _stk_c_row = tk.Frame(cc, bg=CLR_SURFACE)
        _stk_c_row.pack(anchor=W, pady=(4, 0))
        self._edit_stroke_swatch = tk.Label(
            _stk_c_row, bg="#000000", width=3, relief="solid", cursor="hand2",
        )
        self._edit_stroke_swatch.pack(side=LEFT, padx=(0, 6))

        def _pick_stroke_color():
            from tkinter import colorchooser
            r = colorchooser.askcolor(self._edit_stroke_color_hex.get(), title="Stroke / Border color")
            if r and r[1]:
                self._edit_stroke_color_hex.set(r[1].upper())
                self._edit_stroke_swatch.config(bg=r[1])
                self._regen_edit_preview()
        self._edit_stroke_swatch.bind("<Button-1>", lambda e: _pick_stroke_color())

        for _slbl, _shex, _sfg in [
            ("Black",  "#000000", "#ccc"),
            ("White",  "#FFFFFF", "#111"),
            ("Shadow", "#1A1A1A", "#ccc"),
            ("Red",    "#CC0000", "#fff"),
        ]:
            def _set_sc(h=_shex):
                self._edit_stroke_color_hex.set(h)
                self._edit_stroke_swatch.config(bg=h)
                self._regen_edit_preview()
            tk.Button(
                _stk_c_row, text=_slbl, bg=_shex, fg=_sfg, relief=FLAT,
                font=("Segoe UI", 7, "bold"), padx=5, pady=2,
                cursor="hand2", command=_set_sc,
            ).pack(side=LEFT, padx=(0, 3))
        ToolTip(_stk_c_row, "Stroke color — applied around the text outline")

        # ── Spacing ───────────────────────────────────────────────────────────
        spacing_card = SectionCard(p, "Spacing")
        spacing_card.pack(fill=X, pady=(0, 6))
        sc = spacing_card.content

        tk.Label(sc, text="Letter Spacing", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._edit_letter_spacing = tk.IntVar(value=0)
        PremiumScale(sc, variable=self._edit_letter_spacing,
                     from_=-10, to=60, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(sc, text="Line Height", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(6, 0))
        self._edit_line_height = tk.DoubleVar(value=1.2)
        PremiumScale(sc, variable=self._edit_line_height,
                     from_=0.8, to=3.0, resolution=0.1,
                     value_format="{:.1f}x",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)
        ToolTip(spacing_card, "Letter spacing: pixels between characters\nLine height: multiplier for line gap")

        # ── Text Background ───────────────────────────────────────────────────
        textbg_card = SectionCard(p, "Text Background")
        textbg_card.pack(fill=X, pady=(0, 6))
        tbc = textbg_card.content

        self._edit_textbg_var = tk.StringVar(value="none")
        bg_mode_row = tk.Frame(tbc, bg=CLR_SURFACE)
        bg_mode_row.pack(anchor=W, pady=(0, 6))
        for label, val in [("None", "none"), ("Box", "box"), ("Outline", "outline")]:
            tk.Radiobutton(
                bg_mode_row, text=label,
                variable=self._edit_textbg_var, value=val,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, font=("Segoe UI", 9),
                cursor="hand2",
                command=self._regen_edit_preview,
            ).pack(side=LEFT, padx=(0, 12))

        # Box style
        box_style_row = tk.Frame(tbc, bg=CLR_SURFACE)
        box_style_row.pack(fill=X, pady=(0, 4))
        tk.Label(box_style_row, text="Style:", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(side=LEFT)
        self._edit_box_mode = tk.StringVar(value="frame")
        for _lbl, _val in [("Frame", "frame"), ("Per Line", "per_line")]:
            tk.Radiobutton(
                box_style_row, text=_lbl,
                variable=self._edit_box_mode, value=_val,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, font=("Segoe UI", 8),
                cursor="hand2",
                command=self._regen_edit_preview,
            ).pack(side=LEFT, padx=(8, 0))

        # Box color presets + custom picker
        boxclr_row = tk.Frame(tbc, bg=CLR_SURFACE)
        boxclr_row.pack(fill=X, pady=(4, 4))
        tk.Label(boxclr_row, text="Color:", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(side=LEFT)
        self._edit_box_bg_color = tk.StringVar(value="black")
        # Restore saved custom color from config
        _saved_box_hex = self._cfg.get("box_bg_custom_hex", "#222222")
        self._edit_box_bg_color_hex = tk.StringVar(value=_saved_box_hex)
        for _lbl, _val, _clr in [
            ("Black", "black",    "#111"),
            ("Dark",  "darkgray", "#333"),
            ("Gray",  "gray",     "#888"),
            ("White", "white",    "#eee"),
        ]:
            tk.Radiobutton(
                boxclr_row, text=_lbl,
                variable=self._edit_box_bg_color, value=_val,
                bg=CLR_SURFACE, fg=_clr, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, font=("Segoe UI", 8, "bold"),
                cursor="hand2",
                command=self._regen_edit_preview,
            ).pack(side=LEFT, padx=(6, 0))

        # Custom color swatch
        self._box_custom_swatch = tk.Button(
            boxclr_row, text="Custom", width=6,
            bg=_saved_box_hex, fg="white" if _saved_box_hex < "#888888" else "black",
            font=("Segoe UI", 7, "bold"), relief=FLAT, cursor="hand2", padx=4, pady=2,
            command=self._pick_box_bg_color,
        )
        self._box_custom_swatch.pack(side=LEFT, padx=(8, 0))
        ToolTip(self._box_custom_swatch, "Pick any custom background color")

        # Box numeric sliders (radius, padding, opacity)
        tk.Label(tbc, text="Corner Radius", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(2, 0))
        self._edit_box_radius = tk.IntVar(value=0)
        PremiumScale(tbc, variable=self._edit_box_radius,
                     from_=0, to=30, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(tbc, text="Padding H", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._edit_box_pad_x = tk.IntVar(value=30)
        PremiumScale(tbc, variable=self._edit_box_pad_x,
                     from_=0, to=60, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(tbc, text="Padding V", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._edit_box_pad_y = tk.IntVar(value=20)
        PremiumScale(tbc, variable=self._edit_box_pad_y,
                     from_=0, to=40, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(tbc, text="Box Opacity", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._edit_box_opacity = tk.IntVar(value=90)
        PremiumScale(tbc, variable=self._edit_box_opacity,
                     from_=20, to=100, resolution=5,
                     value_format="{:.0f}%",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        # Reset box width
        def _reset_box_width():
            if self._edit_sel_idx < 0:
                return
            st = self._edit_queue[self._edit_sel_idx]["state"]
            st["box_x1_pct"] = -1.0
            st["box_x2_pct"] = -1.0
            self._regen_edit_preview()

        SecondaryButton(tbc, text="Reset Box Width", icon="↺",
                        command=_reset_box_width,
                        font=("Segoe UI", 8), pady=3).pack(
            anchor=W, pady=(6, 0))
        ToolTip(textbg_card, "Add a colored box or outline behind the title text")

        # ── Blending ──────────────────────────────────────────────────────────
        blend_card = SectionCard(p, "Blending")
        blend_card.pack(fill=X, pady=(0, 6))
        blc = blend_card.content

        tk.Label(blc, text="Text Opacity", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._edit_text_opacity = tk.IntVar(value=100)
        PremiumScale(blc, variable=self._edit_text_opacity,
                     from_=0, to=100, resolution=5,
                     value_format="{:.0f}%",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(blc, text="Rotation", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(6, 0))
        self._edit_text_rotation = tk.DoubleVar(value=0.0)
        PremiumScale(blc, variable=self._edit_text_rotation,
                     from_=-45, to=45, resolution=1,
                     value_format="{:.0f}°",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)
        ToolTip(blend_card, "Text opacity and rotation angle")

        # ── Video Position & Scale ─────────────────────────────────────────────
        vid_card = SectionCard(p, "Video Position & Scale")
        vid_card.pack(fill=X, pady=(0, 6))
        vc = vid_card.content

        tk.Label(vc, text="Y Offset", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._edit_video_y = tk.IntVar(value=0)
        PremiumScale(vc, variable=self._edit_video_y,
                     from_=-400, to=400, resolution=1,
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(vc, text="Width Scale", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(6, 0))
        self._edit_video_w_scale = tk.DoubleVar(value=1.0)
        PremiumScale(vc, variable=self._edit_video_w_scale,
                     from_=0.5, to=1.5, resolution=0.05,
                     value_format="{:.2f}x",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        tk.Label(vc, text="Height Scale", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(6, 0))
        self._edit_video_h_scale = tk.DoubleVar(value=1.0)
        PremiumScale(vc, variable=self._edit_video_h_scale,
                     from_=0.5, to=1.5, resolution=0.05,
                     value_format="{:.2f}x",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)
        ToolTip(vid_card, "Shift and scale the video layer within the portrait frame")

        # ── Options ───────────────────────────────────────────────────────────
        opt_card = SectionCard(p, "Options")
        opt_card.pack(fill=X, pady=(0, 6))
        oc = opt_card.content

        self._opt_color_grade = tk.BooleanVar(value=False)
        self._opt_subtitles   = tk.BooleanVar(value=False)
        self._sub_style       = tk.StringVar(value="Normal")
        self._sub_highlight_color = tk.StringVar(value="#FFD700")  # gold
        self._sub_dim_color       = tk.StringVar(value="#FFFFFF")  # white (unhighlighted)
        self._sub_font_size   = tk.IntVar(value=36)

        tk.Checkbutton(
            oc, text="Cinematic color grade",
            variable=self._opt_color_grade,
            bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE, font=("Segoe UI", 9),
            cursor="hand2",
            command=self._regen_edit_preview,
        ).pack(anchor=W)

        self._sub_margin_v = tk.IntVar(value=200)   # pixels from bottom in full-res (1920)

        def _on_sub_toggle():
            if self._opt_subtitles.get():
                _sub_opts_frame.pack(fill=X, pady=(4, 0))
            else:
                _sub_opts_frame.pack_forget()
            self._regen_edit_preview()

        def _on_style_change(*_):
            if self._sub_style.get() == "Normal":
                _kar_opts_row.pack_forget()
            else:
                _kar_opts_row.pack(fill=X, pady=(4, 0))
            self._regen_edit_preview()

        tk.Checkbutton(
            oc,
            text="Auto-subtitles (Gemini AI)",
            variable=self._opt_subtitles,
            bg=CLR_SURFACE, fg=CLR_FG,
            selectcolor=CLR_ACCENT_D, activebackground=CLR_SURFACE,
            font=("Segoe UI", 9), cursor="hand2",
            command=_on_sub_toggle,
        ).pack(anchor=W)

        # ── Subtitle options (hidden until enabled) ────────────────────────────
        _sub_opts_frame = tk.Frame(oc, bg=CLR_SURFACE)

        # Style row
        _style_row = tk.Frame(_sub_opts_frame, bg=CLR_SURFACE)
        _style_row.pack(fill=X)
        tk.Label(_style_row, text="Style:", bg=CLR_SURFACE,
                 fg=CLR_DIM, font=("Segoe UI", 8), width=8, anchor=W).pack(side=LEFT)
        _style_cb = ttk.Combobox(
            _style_row, textvariable=self._sub_style, state="readonly", width=16,
            values=["Normal", "Word Pop", "Highlight Line"],
        )
        _style_cb.pack(side=LEFT, padx=(2, 0))
        self._sub_style.trace_add("write", _on_style_change)

        # Position slider
        tk.Label(_sub_opts_frame, text="Sub position (from bottom)", bg=CLR_SURFACE,
                 fg=CLR_DIM, font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        PremiumScale(_sub_opts_frame, variable=self._sub_margin_v,
                     from_=40, to=500, resolution=10,
                     command=lambda v: self._regen_edit_preview()).pack(fill=X)

        # Karaoke-specific options (hidden until Word Pop or Highlight Line selected)
        _kar_opts_row = tk.Frame(_sub_opts_frame, bg=CLR_SURFACE)

        # ── Dim color (non-highlighted words) ────────────────────────────────
        _dim_row = tk.Frame(_kar_opts_row, bg=CLR_SURFACE)
        _dim_row.pack(fill=X, pady=(0, 2))
        tk.Label(_dim_row, text="Đã chạy:", bg=CLR_SURFACE,
                 fg=CLR_DIM, font=("Segoe UI", 8), width=9, anchor=W).pack(side=LEFT)
        self._sub_dim_swatch = tk.Label(
            _dim_row, bg=self._sub_dim_color.get(),
            width=3, relief="solid", cursor="hand2",
        )
        self._sub_dim_swatch.pack(side=LEFT, padx=(4, 0))

        def _pick_dim_color():
            from tkinter import colorchooser as _cc
            color = _cc.askcolor(self._sub_dim_color.get(),
                                 title="Subtitle dim (non-highlighted) colour")
            if color and color[1]:
                self._sub_dim_color.set(color[1])
                self._sub_dim_swatch.config(bg=color[1])
                self._regen_edit_preview()
        self._sub_dim_swatch.bind("<ButtonPress-1>", lambda _: _pick_dim_color())

        # ── Highlight color (spoken word) ─────────────────────────────────────
        _hl_row = tk.Frame(_kar_opts_row, bg=CLR_SURFACE)
        _hl_row.pack(fill=X, pady=(0, 2))
        tk.Label(_hl_row, text="Chưa chạy:", bg=CLR_SURFACE,
                 fg=CLR_DIM, font=("Segoe UI", 8), width=9, anchor=W).pack(side=LEFT)
        self._sub_hl_swatch = tk.Label(
            _hl_row, bg=self._sub_highlight_color.get(),
            width=3, relief="solid", cursor="hand2",
        )
        self._sub_hl_swatch.pack(side=LEFT, padx=(4, 0))

        def _pick_hl_color():
            from tkinter import colorchooser as _cc
            color = _cc.askcolor(self._sub_highlight_color.get(),
                                 title="Màu chữ chưa chạy (upcoming words)")
            if color and color[1]:
                self._sub_highlight_color.set(color[1])
                self._sub_hl_swatch.config(bg=color[1])
                self._regen_edit_preview()
        self._sub_hl_swatch.bind("<ButtonPress-1>", lambda _: _pick_hl_color())

        # ── Size slider ────────────────────────────────────────────────────────
        _sz_row = tk.Frame(_kar_opts_row, bg=CLR_SURFACE)
        _sz_row.pack(fill=X, pady=(4, 0))
        tk.Label(_sz_row, text="Size:", bg=CLR_SURFACE,
                 fg=CLR_DIM, font=("Segoe UI", 8)).pack(side=LEFT)
        PremiumScale(_sz_row, variable=self._sub_font_size,
                     from_=18, to=120, resolution=2,
                     command=lambda v: self._regen_edit_preview()).pack(side=LEFT, fill=X, expand=True)

        # starts hidden; _on_style_change shows it when non-Normal
        ToolTip(opt_card, "Cinematic grade: adds warm film look\n"
                "Auto-subtitles (Gemini): uploads clip to Gemini for accurate transcription\n"
                "Word Pop: each word appears as spoken (CapCut style)\n"
                "Highlight Line: full line visible, spoken word highlighted")

        # ── Copyright Evasion ─────────────────────────────────────────────────
        ev_card = SectionCard(p, "\U0001f6e1  Copyright Evasion")
        ev_card.pack(fill=X, pady=(0, 6))
        ec = ev_card.content

        tk.Label(ec, text="Apply transforms to avoid platform re-upload detection.",
                 bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 8),
                 wraplength=300, justify=LEFT).pack(anchor=W, pady=(0, 8))

        # ── 1. Background type ────────────────────────────────────────────────
        tk.Label(ec, text="Background", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 9, "bold")).pack(anchor=W)
        self._ev_bg_type = tk.StringVar(value="blur")
        bg_type_row = tk.Frame(ec, bg=CLR_SURFACE)
        bg_type_row.pack(anchor=W, pady=(2, 6))
        for _lbl, _val in [("Blurred", "blur"), ("Image", "image"), ("Video", "video")]:
            tk.Radiobutton(
                bg_type_row, text=_lbl, variable=self._ev_bg_type, value=_val,
                command=self._on_ev_bg_type_change,
                bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                activebackground=CLR_SURFACE, font=("Segoe UI", 9),
            ).pack(side=LEFT, padx=(0, 8))
        ToolTip(bg_type_row, "Blurred: default mirror blur\nImage: static photo background\nVideo: looping video background")

        # File pickers (hidden by default, shown when image/video selected)
        self._ev_bg_file_frame = tk.Frame(ec, bg=CLR_SURFACE)
        self._ev_bg_file_frame.pack(fill=X, pady=(0, 4))

        self._ev_bg_image_var = tk.StringVar()
        self._ev_bg_video_var = tk.StringVar()

        def _pick_bg_image():
            p_ = filedialog.askopenfilename(
                title="Select Background Image",
                filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All", "*.*")])
            if p_:
                if Path(p_).suffix.lower() in {".mp4", ".mov", ".webm", ".mkv", ".avi", ".ts", ".m4v"}:
                    self._ev_bg_video_var.set(p_)
                    self._ev_bg_type.set("video")
                else:
                    self._ev_bg_image_var.set(p_)
                    self._ev_bg_type.set("image")
                self._on_ev_bg_type_change()

        def _pick_bg_video():
            p_ = filedialog.askopenfilename(
                title="Select Background Video",
                filetypes=[("Videos", "*.mp4 *.mov *.avi *.mkv"), ("All", "*.*")])
            if p_:
                if Path(p_).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                    self._ev_bg_image_var.set(p_)
                    self._ev_bg_type.set("image")
                else:
                    self._ev_bg_video_var.set(p_)
                    self._ev_bg_type.set("video")
                self._on_ev_bg_type_change()

        self._ev_img_row = tk.Frame(self._ev_bg_file_frame, bg=CLR_SURFACE)
        self._ev_img_row.pack(fill=X)
        SecondaryButton(self._ev_img_row, text="Choose Image", icon="\U0001f5bc",
                        command=_pick_bg_image, font=("Segoe UI", 8), pady=3
                        ).pack(side=LEFT, padx=(0, 4))
        tk.Label(self._ev_img_row, textvariable=self._ev_bg_image_var,
                 bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 7),
                 width=22, anchor=W).pack(side=LEFT)

        self._ev_vid_row = tk.Frame(self._ev_bg_file_frame, bg=CLR_SURFACE)
        self._ev_vid_row.pack(fill=X, pady=(2, 0))
        SecondaryButton(self._ev_vid_row, text="Choose Video", icon="\U0001f3ac",
                        command=_pick_bg_video, font=("Segoe UI", 8), pady=3
                        ).pack(side=LEFT, padx=(0, 4))
        tk.Label(self._ev_vid_row, textvariable=self._ev_bg_video_var,
                 bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 7),
                 width=22, anchor=W).pack(side=LEFT)

        ttk.Separator(ec, orient=HORIZONTAL).pack(fill=X, pady=8)

        # ── 2. Color Transform ────────────────────────────────────────────────
        tk.Label(ec, text="Color Transform", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 9, "bold")).pack(anchor=W)

        tk.Label(ec, text="Hue Shift", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._ev_hue_shift = tk.IntVar(value=0)
        PremiumScale(ec, variable=self._ev_hue_shift,
                     from_=-180, to=180, resolution=1,
                     value_format="{:.0f}\u00b0",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)
        ToolTip(ec, "Shift all colors by this angle (breaks color hash fingerprinting)")

        tk.Label(ec, text="Saturation", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._ev_saturation = tk.DoubleVar(value=1.0)
        PremiumScale(ec, variable=self._ev_saturation,
                     from_=0.5, to=2.0, resolution=0.05,
                     value_format="{:.2f}x",
                     command=lambda v: self._regen_edit_preview(),
                     ).pack(fill=X)

        # Color presets row
        _preset_row = tk.Frame(ec, bg=CLR_SURFACE)
        _preset_row.pack(anchor=W, pady=(4, 0))
        tk.Label(_preset_row, text="Preset:", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(side=LEFT, padx=(0, 4))
        for _lbl, _h, _s in [
            ("Normal", 0, 1.0), ("Warm", 15, 1.2), ("Cool", -20, 0.9),
            ("Vivid", 0, 1.6),  ("B&W", 0, 0.0),
        ]:
            def _apply_preset(h=_h, s=_s):
                self._ev_hue_shift.set(h); self._ev_saturation.set(s)
                self._regen_edit_preview()
            tk.Button(
                _preset_row, text=_lbl,
                bg=CLR_PANEL, fg=CLR_FG, activebackground=CLR_ACCENT_D,
                font=("Segoe UI", 7), relief=FLAT, padx=4, pady=2, cursor="hand2",
                command=_apply_preset,
            ).pack(side=LEFT, padx=(0, 2))

        ttk.Separator(ec, orient=HORIZONTAL).pack(fill=X, pady=8)

        # ── 3. Flip ───────────────────────────────────────────────────────────
        tk.Label(ec, text="Flip", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 9, "bold")).pack(anchor=W)
        flip_row = tk.Frame(ec, bg=CLR_SURFACE)
        flip_row.pack(anchor=W, pady=(4, 0))
        self._ev_flip_h = tk.BooleanVar(value=False)
        self._ev_flip_v = tk.BooleanVar(value=False)
        tk.Checkbutton(
            flip_row, text="\u21d4  Horizontal",
            variable=self._ev_flip_h, command=self._regen_edit_preview,
            bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE, font=("Segoe UI", 9),
        ).pack(side=LEFT, padx=(0, 12))
        tk.Checkbutton(
            flip_row, text="\u21d5  Vertical",
            variable=self._ev_flip_v, command=self._regen_edit_preview,
            bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE, font=("Segoe UI", 9),
        ).pack(side=LEFT)
        ToolTip(flip_row, "Horizontal flip is most effective at evading platform detection")

        ttk.Separator(ec, orient=HORIZONTAL).pack(fill=X, pady=8)

        # ── 4. Watermark ──────────────────────────────────────────────────────
        tk.Label(ec, text="Watermark", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 9, "bold")).pack(anchor=W)

        self._ev_wm_text = tk.StringVar()
        self._ev_wm_text.trace_add("write",
            lambda *_: self.after(200, self._regen_edit_preview))  # debounced
        wm_entry = tk.Entry(
            ec, textvariable=self._ev_wm_text,
            bg=CLR_INPUT_BG, fg=CLR_FG, insertbackground=CLR_FG,
            font=("Segoe UI", 9), relief=FLAT, bd=0,
            highlightbackground=CLR_BORDER, highlightthickness=1,
        )
        wm_entry.pack(fill=X, ipady=4, pady=(4, 6))
        ToolTip(wm_entry, "Text to burn as watermark (e.g. '@yourhandle')")

        # 3×3 position grid
        tk.Label(ec, text="Position", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._ev_wm_pos = tk.StringVar(value="BR")
        _pos_grid = tk.Frame(ec, bg=CLR_SURFACE)
        _pos_grid.pack(anchor=W, pady=(2, 6))
        for _row_i, _row in enumerate([
            [("TL", "\u2196"), ("TC", "\u2191"), ("TR", "\u2197")],
            [("ML", "\u2190"), ("MC", "\u25a0"), ("MR", "\u2192")],
            [("BL", "\u2199"), ("BC", "\u2193"), ("BR", "\u2198")],
        ]):
            _rf = tk.Frame(_pos_grid, bg=CLR_SURFACE)
            _rf.pack()
            for _pos, _sym in _row:
                tk.Radiobutton(
                    _rf, text=_sym, variable=self._ev_wm_pos, value=_pos,
                    command=self._regen_edit_preview,
                    bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
                    activebackground=CLR_SURFACE, font=("Segoe UI", 10),
                    indicatoron=False, width=3, relief=FLAT,
                    cursor="hand2", padx=2, pady=1,
                ).pack(side=LEFT, padx=1, pady=1)

        # Watermark size + opacity
        tk.Label(ec, text="Size", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W)
        self._ev_wm_size = tk.IntVar(value=28)
        PremiumScale(ec, variable=self._ev_wm_size,
                     from_=12, to=80, resolution=1,
                     command=lambda v: self._regen_edit_preview()).pack(fill=X)

        tk.Label(ec, text="Opacity", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._ev_wm_opacity = tk.IntVar(value=50)
        PremiumScale(ec, variable=self._ev_wm_opacity,
                     from_=10, to=100, resolution=5,
                     value_format="{:.0f}%",
                     command=lambda v: self._regen_edit_preview()).pack(fill=X)

        # Watermark color picker
        wm_clr_row = tk.Frame(ec, bg=CLR_SURFACE)
        wm_clr_row.pack(anchor=W, pady=(4, 0))
        tk.Label(wm_clr_row, text="Color:", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(side=LEFT, padx=(0, 4))
        self._ev_wm_color = tk.StringVar(value="#FFFFFF")
        self._ev_wm_swatch = tk.Label(
            wm_clr_row, bg="#FFFFFF", width=3, relief="solid",
            cursor="hand2", borderwidth=1)
        self._ev_wm_swatch.pack(side=LEFT)

        def _pick_wm_color():
            from tkinter import colorchooser
            c = colorchooser.askcolor(self._ev_wm_color.get(), title="Watermark Color")
            if c and c[1]:
                self._ev_wm_color.set(c[1])
                self._ev_wm_swatch.config(bg=c[1])
                self._regen_edit_preview()

        self._ev_wm_swatch.bind("<Button-1>", lambda e: _pick_wm_color())

        ttk.Separator(ec, orient=HORIZONTAL).pack(fill=X, pady=8)

        # ── 5. Anti-detect ────────────────────────────────────────────────────
        tk.Label(ec, text="Anti-Detection", bg=CLR_SURFACE, fg=CLR_FG2,
                 font=("Segoe UI", 9, "bold")).pack(anchor=W)

        self._ev_add_grain = tk.BooleanVar(value=False)
        tk.Checkbutton(
            ec, text="\U0001f4f7  Film Grain (breaks hash fingerprint)",
            variable=self._ev_add_grain, command=self._regen_edit_preview,
            bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE, font=("Segoe UI", 9),
        ).pack(anchor=W, pady=(4, 0))
        ToolTip(ec, "Adds random noise to each frame — breaks YouTube/TikTok perceptual hash detection")

        tk.Label(ec, text="Grain Strength", bg=CLR_SURFACE, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self._ev_grain_strength = tk.IntVar(value=3)
        PremiumScale(ec, variable=self._ev_grain_strength,
                     from_=1, to=10, resolution=1,
                     command=lambda v: self._regen_edit_preview()).pack(fill=X)

        self._ev_speed_tweak = tk.BooleanVar(value=False)
        tk.Checkbutton(
            ec, text="\u23f3  Speed Tweak \u00b12% (breaks temporal fingerprint)",
            variable=self._ev_speed_tweak, command=self._regen_edit_preview,
            bg=CLR_SURFACE, fg=CLR_FG, selectcolor=CLR_ACCENT_D,
            activebackground=CLR_SURFACE, font=("Segoe UI", 9),
        ).pack(anchor=W, pady=(6, 0))
        ToolTip(ec, "Speeds video up by ~2% — inaudible but breaks timestamp-based detection")

        self._on_ev_bg_type_change()   # set initial visibility of file picker rows

    # ── Tab 2 editor helpers ──────────────────────────────────────────────────

    def _on_ev_bg_type_change(self, *_):
        """Show/hide file picker rows based on selected background type."""
        bg = self._ev_bg_type.get()
        for widget, visible in [
            (self._ev_img_row, bg == "image"),
            (self._ev_vid_row, bg == "video"),
        ]:
            if visible:
                widget.pack(fill=X, pady=(0, 2))
            else:
                widget.pack_forget()
        self._regen_edit_preview()

    # ── Edit tab video playback ──────────────────────────────────────────────

    def _start_edit_play(self):
        """Pipe raw RGB24 frames from FFmpeg into the edit canvas at ~12 fps.
        Also launches an ffplay subprocess for audio, mirroring VideoPlayer."""
        if self._edit_sel_idx < 0:
            return
        self._stop_edit_play()   # kill any previous session

        clip = self._edit_queue[self._edit_sel_idx]["clip_path"]
        if not clip.exists():
            return

        pct     = self._scrub_pos.get() / 100.0
        dur     = get_video_duration(clip) or 10.0
        seek_t  = max(0.0, pct * dur)
        remain  = max(1.0, dur - seek_t)    # seconds left from seek point
        FPS     = 12
        W, H    = EDIT_PREV_W, EDIT_PREV_H
        FRAME_B = W * H * 3   # bytes per RGB24 frame

        cmd = [
            FFMPEG, "-loglevel", "quiet",
            "-ss", f"{seek_t:.2f}", "-i", str(clip),
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                   f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,fps={FPS}",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ]

        self._edit_play_stop_evt = threading.Event()
        stop_evt = self._edit_play_stop_evt
        self._edit_playing = True
        self._btn_edit_play.config(text="⏹  Stop")
        self._edit_audio_proc: Optional[subprocess.Popen] = None

        NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        frame_queue: list = []
        _first_frame_evt = threading.Event()   # signalled when first frame arrives

        def _read_frames():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    creationflags=NO_WIN,
                )
                self._edit_play_proc = proc
                first = True
                while not stop_evt.is_set():
                    raw = proc.stdout.read(FRAME_B)
                    if len(raw) < FRAME_B:
                        break
                    frame_queue.append(raw)
                    if first:
                        first = False
                        _first_frame_evt.set()  # ← unblock audio thread
                proc.stdout.close()
                proc.wait(timeout=2)
            except Exception:
                pass
            finally:
                stop_evt.set()
                _first_frame_evt.set()  # unblock even on error

        def _start_audio_synced():
            """Wait for first video frame then launch ffplay — eliminates A/V drift."""
            _first_frame_evt.wait(timeout=8.0)
            if stop_evt.is_set():
                return
            try:
                self._edit_audio_proc = subprocess.Popen(
                    [
                        FFPLAY, "-nodisp", "-autoexit",
                        "-loglevel", "quiet",
                        "-ss", f"{seek_t:.2f}",
                        "-t",  f"{remain:.2f}",
                        str(clip),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=NO_WIN,
                )
            except Exception:
                self._edit_audio_proc = None

        threading.Thread(target=_read_frames,       daemon=True).start()
        threading.Thread(target=_start_audio_synced, daemon=True).start()

        interval_ms = 1000 // FPS

        def _tick():
            if stop_evt.is_set() and not frame_queue:
                self._stop_edit_play()
                return
            if frame_queue:
                raw = frame_queue.pop(0)
                from PIL import Image, ImageTk
                img = Image.frombytes("RGB", (W, H), raw)
                photo = ImageTk.PhotoImage(img)
                self._edit_canvas.create_image(0, 0, anchor="nw", image=photo)
                self._edit_canvas._play_photo = photo   # prevent GC
            self._edit_play_job = self.after(interval_ms, _tick)

        self._edit_play_job = self.after(80, _tick)

    def _stop_edit_play(self):
        """Stop playback (video frame pipe + audio ffplay) and restore static preview."""
        if self._edit_play_job:
            try: self.after_cancel(self._edit_play_job)
            except Exception: pass
            self._edit_play_job = None

        if hasattr(self, "_edit_play_stop_evt"):
            self._edit_play_stop_evt.set()

        if self._edit_play_proc:
            try:
                self._edit_play_proc.kill()
                self._edit_play_proc.stdout.close()
            except Exception: pass
            self._edit_play_proc = None

        # Kill audio ffplay process
        if getattr(self, "_edit_audio_proc", None):
            try:
                self._edit_audio_proc.terminate()
            except Exception: pass
            self._edit_audio_proc = None

        self._edit_playing = False
        if hasattr(self, "_btn_edit_play"):
            self._btn_edit_play.config(text="▶  Play Preview")

        # Restore the static PIL composite preview
        self._regen_edit_preview()

    def _on_title_text_modified(self, *args):
        if self._edit_sel_idx >= 0:
            new_text = self._edit_title_text_var.get()
            self._edit_queue[self._edit_sel_idx]["title"] = new_text
            self._regen_edit_preview()

    def _send_to_edit_tab(self):
        """Push last cut clip + selected title onto the Tab 2 queue."""
        if not self._last_cut_path or not self._last_cut_path.exists():
            messagebox.showwarning("No Clip", "Cut a clip first.")
            return
        title = self._selected_title_for_reup.strip()
        if not title:
            messagebox.showwarning("No Title",
                "Click one of the title buttons to select a title first.")
            return

        # Fetch suggested titles from currently selected candidate
        suggested = []
        if self._selected_video:
            res = self._video_results.get(str(self._selected_video), {})
            candidates = res.get("candidates", [])
            cand_idx = self._cand_box.current()
            if 0 <= cand_idx < len(candidates):
                suggested = candidates[cand_idx].get("suggested_titles", [])

        item = {
            "clip_path": self._last_cut_path,
            "title":     title,
            "suggested_titles": suggested,
            "state":     _default_edit_state(),
        }
        # In Sync All mode, immediately apply the global template to new items
        if getattr(self, "_edit_sync_all", None) and self._edit_sync_all.get():
            item["state"].update(self._global_edit_state)
        self._edit_queue.append(item)
        self._edit_listbox.insert(END, self._last_cut_path.stem)
        self._update_queue_count_label()

        idx = len(self._edit_queue) - 1
        self._edit_listbox.selection_clear(0, END)
        self._edit_listbox.selection_set(idx)
        self._edit_sel_idx = idx

        self._btn_export_one.config(state=NORMAL)
        self._btn_export_all.config(state=NORMAL)
        self._tab_notebook.select(1)   # switch to Tab 2
        self._on_edit_select()

    def _on_edit_select(self, _event=None):
        """Load queue item state into controls and refresh preview."""
        sel = self._edit_listbox.curselection()
        if not sel:
            return
        self._edit_sel_idx = sel[0]
        item = self._edit_queue[self._edit_sel_idx]

        # In Sync All mode: push global visual settings into item before loading.
        # blur_boxes / text_x / text_y are intentionally absent from _global_edit_state.
        if getattr(self, "_edit_sync_all", None) and self._edit_sync_all.get():
            item["state"].update(self._global_edit_state)

        # Snapshot state BEFORE any .set() calls.
        # tk.Scale.command fires on programmatic .set(), so intermediate _regen_edit_preview
        # calls would read stale widget values and corrupt the new item's state.
        # We suppress those calls with _loading_item and use a frozen snapshot for loading.
        st = dict(item["state"])   # local copy — immune to mid-load mutations
        self._loading_item = True
        try:
            self._edit_title_text_var.set(item["title"])

            _fn = {
                "impact":   "Impact",   "arialbd":  "Arial Bold",  "arial":    "Arial",
                "segoeuib": "Segoe UI Bold", "calibrib": "Calibri Bold",
                "verdanab": "Verdana Bold",  "comicbd":  "Comic Sans",
                "trebucbd": "Trebuchet Bold",
            }
            self._edit_font_var.set(_fn.get(st.get("font_name", "impact"), "Impact"))
            self._edit_font_size.set(st.get("font_size", 52))
            self._edit_color_var.set(st.get("text_color", "white"))
            self._edit_textbg_var.set(st.get("text_bg", "none"))
            self._edit_align_var.set(st.get("text_align", "left"))
            self._edit_video_y.set(st.get("video_y", 0))

            self._edit_video_w_scale.set(st.get("video_w_scale", 1.0))
            self._edit_video_h_scale.set(st.get("video_h_scale", 1.0))

            self._opt_color_grade.set(st.get("color_grade", False))
            self._opt_subtitles.set(st.get("subtitles", False))
            self._sub_style.set(st.get("sub_style", "Normal"))
            _c = st.get("sub_highlight_color", "#FFD700")
            self._sub_highlight_color.set(_c)
            if hasattr(self, "_sub_hl_swatch"):
                self._sub_hl_swatch.config(bg=_c)
            self._sub_font_size.set(int(st.get("sub_font_size", 36)))

            smt = st.get("source_mask_top", 0.0)
            self._edit_source_mask.set(smt)
            smb = st.get("source_mask_bottom", 0.0)
            self._edit_source_mask_bottom.set(smb)
            self._edit_mask_position.set(st.get("mask_position", "top"))
            twp = st.get("title_wrap_pct", 1.0)
            self._edit_title_wrap_pct.set(twp)

            _br = int(st.get("box_radius", 0))
            self._edit_box_radius.set(_br)
            self._edit_box_mode.set(st.get("box_mode", "frame"))

            _bpx = int(st.get("box_pad_x", 30))
            self._edit_box_pad_x.set(_bpx)
            _bpy = int(st.get("box_pad_y", 20))
            self._edit_box_pad_y.set(_bpy)
            self._edit_font_bold.set(bool(st.get("font_bold", False)))
            self._edit_box_bg_color.set(st.get("box_bg_color", "black"))
            _cus_hex = st.get("box_bg_color_hex", self._cfg.get("box_bg_custom_hex", "#222222"))
            self._edit_box_bg_color_hex.set(_cus_hex)
            try:
                self._box_custom_swatch.config(bg=_cus_hex)
            except Exception:
                pass
            _bop = int(st.get("box_opacity", 90))
            self._edit_box_opacity.set(_bop)

            # OpenCut typography state
            self._edit_font_italic.set(bool(st.get("font_italic", False)))
            self._edit_text_decoration.set(st.get("text_decoration", "none"))
            _ls = int(st.get("letter_spacing", 0))
            self._edit_letter_spacing.set(_ls)
            _lh = float(st.get("line_height", 1.2))
            self._edit_line_height.set(_lh)
            _top = int(st.get("text_opacity", 100))
            self._edit_text_opacity.set(_top)
            _rot = float(st.get("text_rotation", 0.0))
            self._edit_text_rotation.set(_rot)
            # Hex color: load from text_color_hex, or map preset → hex
            _PRESET_HEX = {"white": "#FFFFFF", "yellow": "#FFF000", "black": "#000000"}
            _hex = st.get("text_color_hex", "") or _PRESET_HEX.get(st.get("text_color", "white"), "#FFFFFF")
            self._edit_color_hex_var.set(_hex)
            try:
                self._edit_color_swatch.config(bg=_hex)
            except Exception:
                pass

            if "box_x1_pct" not in item["state"]:
                item["state"]["box_x1_pct"] = -1.0
            if "box_x2_pct" not in item["state"]:
                item["state"]["box_x2_pct"] = -1.0

            # Rebuild blur-box listbox from saved state
            self._blur_listbox.delete(0, END)
            for _i, _b in enumerate(st.get("blur_boxes", [])):
                self._blur_listbox.insert(
                    END,
                    f"Box {_i+1}: ({_b['x']},{_b['y']})  {_b['w']}×{_b['h']} px"
                )

            # ── Copyright Evasion widgets ────────────────────────────────────
            self._ev_bg_type.set(st.get("bg_type", "blur"))
            self._ev_bg_image_var.set(st.get("bg_image_path", ""))
            self._ev_bg_video_var.set(st.get("bg_video_path", ""))
            self._on_ev_bg_type_change()

            self._ev_hue_shift.set(int(st.get("hue_shift", 0)))
            self._ev_saturation.set(float(st.get("saturation", 1.0)))
            self._ev_flip_h.set(bool(st.get("flip_h", False)))
            self._ev_flip_v.set(bool(st.get("flip_v", False)))

            self._ev_wm_text.set(st.get("watermark_text", ""))
            self._ev_wm_pos.set(st.get("watermark_pos", "BR"))
            self._ev_wm_size.set(int(st.get("watermark_size", 28)))
            self._ev_wm_opacity.set(int(st.get("watermark_opacity", 50)))
            _wm_clr = st.get("watermark_color", "#FFFFFF")
            self._ev_wm_color.set(_wm_clr)
            try:
                self._ev_wm_swatch.config(bg=_wm_clr)
            except Exception:
                pass

            self._ev_add_grain.set(bool(st.get("add_grain", False)))
            self._ev_grain_strength.set(int(st.get("grain_strength", 3)))
            self._ev_speed_tweak.set(bool(st.get("speed_tweak", False)))
            self._sub_margin_v.set(int(st.get("sub_margin_v", 200)))

        finally:
            self._loading_item = False

        self._regen_edit_preview()  # single authoritative regen after full widget load
        self._refresh_edit_suggestions_ui()

    def _edit_queue_remove(self):
        """Remove all currently selected items from the queue (Shift/Ctrl multi-select)."""
        sel = list(self._edit_listbox.curselection())
        if not sel:
            return
        # Delete in reverse order so indices stay valid as we pop.
        for idx in sorted(sel, reverse=True):
            self._edit_queue.pop(idx)
            self._edit_listbox.delete(idx)
        self._edit_sel_idx = -1
        if not self._edit_queue:
            self._btn_export_one.config(state=DISABLED)
            self._btn_export_all.config(state=DISABLED)
            self._draw_edit_placeholder()
        else:
            # Select the item nearest to the first removed index
            new_idx = min(sel[0], len(self._edit_queue) - 1)
            self._edit_listbox.selection_set(new_idx)
            self._edit_sel_idx = new_idx
            self._on_edit_select()
        self._update_queue_count_label()
        self._refresh_edit_suggestions_ui()

    def _update_queue_count_label(self):
        """Refresh the QUEUE header to show current item count."""
        n = len(self._edit_queue)
        if hasattr(self, "_queue_count_var"):
            self._queue_count_var.set(f"QUEUE  ({n} clip{'s' if n != 1 else ''})")

    def _draw_edit_placeholder(self):
        if not hasattr(self, "_edit_canvas"):
            return
        self._edit_canvas.delete("all")
        self._edit_canvas.create_rectangle(
            0, 0, EDIT_PREV_W, EDIT_PREV_H, fill="#0d0d1a", outline="")
        self._edit_canvas.create_text(
            EDIT_PREV_W // 2, EDIT_PREV_H // 2,
            text="Send a clip from\nTab 1 to start",
            fill=CLR_DIM, font=("Segoe UI", 10), justify="center",
        )

    def _read_edit_controls(self) -> dict:
        """Read control widget values into a state dict (excludes text_x/y and blur_boxes).

        blur_boxes are managed directly in state by the draw-mode interaction,
        so they are intentionally omitted here to prevent accidental overwrites.
        """
        _fn = {
            "Impact": "impact", "Arial Bold": "arialbd", "Arial": "arial",
            "Segoe UI Bold": "segoeuib", "Calibri Bold": "calibrib",
            "Verdana Bold": "verdanab", "Comic Sans": "comicbd",
            "Trebuchet Bold": "trebucbd",
        }
        return {
            "font_name":       _fn.get(self._edit_font_var.get(), "impact"),
            "font_size":       self._edit_font_size.get(),
            "text_color":      self._edit_color_var.get(),
            "text_bg":         self._edit_textbg_var.get(),
            "box_mode":        self._edit_box_mode.get(),
            "box_radius":      self._edit_box_radius.get(),
            "box_pad_x":       self._edit_box_pad_x.get(),
            "box_pad_y":       self._edit_box_pad_y.get(),
            "box_bg_color":     self._edit_box_bg_color.get(),
            "box_bg_color_hex": self._edit_box_bg_color_hex.get(),
            "box_opacity":     self._edit_box_opacity.get(),
            "font_bold":       bool(self._edit_font_bold.get()),
            "text_align":      self._edit_align_var.get(),
            "video_y":         self._edit_video_y.get(),
            "video_w_scale":   self._edit_video_w_scale.get(),
            "video_h_scale":   self._edit_video_h_scale.get(),
            "color_grade":     self._opt_color_grade.get(),
            "subtitles":       self._opt_subtitles.get(),
            "sub_style":       self._sub_style.get(),
            "sub_highlight_color": self._sub_highlight_color.get(),
            "sub_dim_color":    self._sub_dim_color.get(),
            "sub_font_size":   self._sub_font_size.get(),
            "source_mask_top":    self._edit_source_mask.get(),
            "source_mask_bottom": self._edit_source_mask_bottom.get(),
            "mask_position":      self._edit_mask_position.get(),
            "title_wrap_pct":  self._edit_title_wrap_pct.get(),
            # Title position — drag-managed but included so Sync All propagates them
            "text_x": float(self._edit_queue[self._edit_sel_idx]["state"].get("text_x", 0))
                      if self._edit_sel_idx >= 0 else 0,
            "text_y": float(self._edit_queue[self._edit_sel_idx]["state"].get("text_y", 60))
                      if self._edit_sel_idx >= 0 else 60,
            # box_x1_pct / box_x2_pct are drag-managed (no widget); read from live state.
            # We intentionally pass them through so sync-all preserves them.
            "box_x1_pct":      float(self._edit_queue[self._edit_sel_idx]["state"].get("box_x1_pct", -1.0))
                               if self._edit_sel_idx >= 0 else -1.0,
            "box_x2_pct":      float(self._edit_queue[self._edit_sel_idx]["state"].get("box_x2_pct", -1.0))
                               if self._edit_sel_idx >= 0 else -1.0,
            # OpenCut typography
            "letter_spacing":  self._edit_letter_spacing.get(),
            "line_height":     self._edit_line_height.get(),
            "font_italic":     bool(self._edit_font_italic.get()),
            "text_decoration": self._edit_text_decoration.get(),
            "text_opacity":    self._edit_text_opacity.get(),
            "text_rotation":   self._edit_text_rotation.get(),
            "text_color_hex":  self._edit_color_hex_var.get(),
            # Text stroke / border
            "stroke_width":    self._edit_stroke_width.get(),
            "stroke_color_hex": self._edit_stroke_color_hex.get(),
            # Copyright evasion
            "bg_type":          self._ev_bg_type.get(),
            "bg_image_path":    self._ev_bg_image_var.get(),
            "bg_video_path":    self._ev_bg_video_var.get(),
            "hue_shift":        self._ev_hue_shift.get(),
            "saturation":       self._ev_saturation.get(),
            "flip_h":           bool(self._ev_flip_h.get()),
            "flip_v":           bool(self._ev_flip_v.get()),
            "watermark_text":   self._ev_wm_text.get(),
            "watermark_pos":    self._ev_wm_pos.get(),
            "watermark_opacity": self._ev_wm_opacity.get(),
            "watermark_size":   self._ev_wm_size.get(),
            "watermark_color":  self._ev_wm_color.get(),
            "add_grain":        bool(self._ev_add_grain.get()),
            "grain_strength":   self._ev_grain_strength.get(),
            "speed_tweak":      bool(self._ev_speed_tweak.get()),
            "sub_margin_v":     self._sub_margin_v.get(),
        }

    def _regen_edit_preview(self, *_):
        """Sync controls → state dict and rebuild the editor canvas."""
        if self._edit_sel_idx < 0 or not PIL_AVAILABLE:
            return
        # Suppress intermediate calls fired by tk.Scale.command during item load
        if getattr(self, "_loading_item", False):
            return
        ctrl = self._read_edit_controls()

        if getattr(self, "_edit_sync_all", None) and self._edit_sync_all.get():
            # Propagate visual settings to every item in the queue
            self._global_edit_state.update(ctrl)
            for _item in self._edit_queue:
                _item["state"].update(ctrl)   # blur_boxes/text_x/y untouched
            n = len(self._edit_queue)
            self._sync_status_lbl.config(
                text=f"Syncing {n} video{'s' if n != 1 else ''}")
        else:
            self._edit_queue[self._edit_sel_idx]["state"].update(ctrl)

        item = self._edit_queue[self._edit_sel_idx]
        try:
            img  = self._build_edit_image(
                item["clip_path"], item["title"], item["state"])
            if img:
                self._display_edit_preview(img)
        except Exception:
            import traceback
            traceback.print_exc()

    def _on_sync_mode_toggle(self):
        """Handle mode switch between Per Video and Sync All."""
        if self._edit_sync_all.get():
            # Switching TO Sync All — treat current item as the global template
            if self._edit_sel_idx >= 0:
                ctrl = self._read_edit_controls()
                self._global_edit_state.update(ctrl)
                for _item in self._edit_queue:
                    _item["state"].update(ctrl)
            n = len(self._edit_queue)
            self._sync_status_lbl.config(
                text=f"Syncing {n} video{'s' if n != 1 else ''}")
        else:
            # Switching TO Per Video — clear status and reload the item’s own state
            self._sync_status_lbl.config(text="")
            if self._edit_sel_idx >= 0:
                self._on_edit_select()   # reloads item’s independent state
                return
        self._regen_edit_preview()

    def _extract_first_frame_pil(self, clip: Path):
        """Extract first frame at t=0.5 s via FFmpeg → temp JPEG → PIL Image."""
        try:
            tmp = Path(tempfile.mktemp(suffix="_edit_frame.jpg"))
            subprocess.run(
                [FFMPEG, "-loglevel", "quiet",
                 "-ss", "0.5", "-i", str(clip),
                 "-frames:v", "1", "-q:v", "3", str(tmp)],
                capture_output=True, timeout=10,
            )
            if not tmp.exists():
                return None
            from PIL import Image
            img = Image.open(tmp).convert("RGB")
            img.load()
            try:
                tmp.unlink()
            except Exception:
                pass
            return img
        except Exception:
            return None

    def _build_edit_image(self, clip: Path, title: str, state: dict):
        """PIL-only composite at preview scale (378×672). Background and first frame are cached."""
        if not PIL_AVAILABLE:
            return None
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        import textwrap

        W, H = EDIT_PREV_W, EDIT_PREV_H

        # Get / cache first frame
        src_key = str(clip)
        if src_key not in self._frame_cache:
            src = self._extract_first_frame_pil(clip)
            if src is None:
                return None
            self._frame_cache[src_key] = src
        src = self._frame_cache[src_key]

        # ── Background layer ────────────────────────────────────────────────────
        # Cached per (bg_type, bg_path, clip, source_mask_top).
        bg_type  = state.get("bg_type", "blur")
        bg_img_p = state.get("bg_image_path", "")
        bg_vid_p = state.get("bg_video_path", "")
        cpt = max(0.0, min(0.29, float(state.get("source_mask_top", 0.0))))
        bg_cache_key = (bg_type, bg_img_p, bg_vid_p, src_key, cpt)

        if bg_cache_key not in self._edit_bg_cache:
            bg_src = None

            _v_exts = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".ts", ".m4v"}
            if bg_type == "image" and bg_img_p:
                if Path(bg_img_p).suffix.lower() in _v_exts:
                    bg_key_v = f"__bgvid__{bg_img_p}"
                    if bg_key_v not in self._frame_cache:
                        self._frame_cache[bg_key_v] = self._extract_first_frame_pil(Path(bg_img_p))
                    bg_src = self._frame_cache[bg_key_v]
                else:
                    try:
                        bg_src = Image.open(bg_img_p).convert("RGB")
                    except Exception:
                        bg_src = None

            elif bg_type == "video" and bg_vid_p:
                # Extract first frame from background video for preview
                bg_key_v = f"__bgvid__{bg_vid_p}"
                if bg_key_v not in self._frame_cache:
                    self._frame_cache[bg_key_v] = self._extract_first_frame_pil(
                        Path(bg_vid_p))
                bg_src = self._frame_cache[bg_key_v]

            if bg_src is None:
                # Fallback: blurred clip frame (default "blur" behaviour)
                src_for_bg = src
                if cpt > 0:
                    crop_top_px = int(src.height * cpt)
                    src_for_bg = src.crop((0, crop_top_px, src.width, src.height))
                bg_src = src_for_bg

            # Scale-and-crop bg_src to fill W×H
            r  = bg_src.width / bg_src.height
            tr = W / H
            s  = H / bg_src.height if r > tr else W / bg_src.width
            bw, bh = int(bg_src.width * s), int(bg_src.height * s)
            bg = bg_src.resize((bw, bh), Image.LANCZOS)
            cx, cy = (bw - W) // 2, (bh - H) // 2
            bg = bg.crop((cx, cy, cx + W, cy + H))
            # Only blur when in blur mode
            if bg_type not in ("image", "video"):
                bg = bg.filter(ImageFilter.GaussianBlur(radius=14))
            self._edit_bg_cache[bg_cache_key] = bg

        bg_layer = self._edit_bg_cache[bg_cache_key]

        # Foreground scaling on-the-fly (uses video_w_scale and video_h_scale)
        vw_scale = float(state.get("video_w_scale", 1.0))
        vh_scale = float(state.get("video_h_scale", 1.0))
        fg_w = int(W * vw_scale)
        fg_h = int(W * (src.height / src.width) * vh_scale)
        fg_w = max(10, fg_w)
        fg_h = max(10, fg_h)
        fg   = src.resize((fg_w, fg_h), Image.LANCZOS)
        fg_h_orig = fg_h  # save before crop for vy calculation

        # ── Source mask: crop top and/or bottom of fg ────────────────────────────
        cpb_prev = max(0.0, min(0.29, float(state.get("source_mask_bottom", 0.0))))
        _rem = max(0.01, 1.0 - cpt - cpb_prev)
        if cpt > 0 or cpb_prev > 0:
            crop_top_px = int(fg_h_orig * cpt)
            crop_bot_px = int(fg_h_orig * cpb_prev)
            fg = fg.crop((0, crop_top_px, fg_w, fg_h_orig - crop_bot_px))

        # Composite coordinates — unified formula mirrors FFmpeg overlay expression
        vx    = (W - fg_w) // 2
        vy_px = int(state.get("video_y", 0) * EDIT_PREV_SCALE)
        # overlay_y = (H - h/remain)/2 + cpt*h/remain  (h = cropped fg height)
        _fgh  = fg.height
        vy    = int((H - _fgh / _rem) / 2 + vy_px + cpt * _fgh / _rem)

        # ── Copyright evasion: apply transforms to fg before compositing ────────
        if state.get("flip_h", False):
            fg = fg.transpose(Image.FLIP_LEFT_RIGHT)
        if state.get("flip_v", False):
            fg = fg.transpose(Image.FLIP_TOP_BOTTOM)

        # Hue shift + saturation in PIL — use ImageEnhance for saturation (fast),
        # and a vectorized point-table hue shift (avoids slow per-pixel Python loop).
        hue_shift = int(state.get("hue_shift", 0))
        sat_mult  = float(state.get("saturation", 1.0))
        if hue_shift != 0 or abs(sat_mult - 1.0) > 0.01:
            from PIL import ImageEnhance
            if abs(sat_mult - 1.0) > 0.01:
                fg = ImageEnhance.Color(fg).enhance(sat_mult)
            if hue_shift != 0:
                # Hue shift via HSV: convert to RGB bytes, rotate hue channel
                import colorsys
                fg_rgb = fg.convert("RGB")
                h_shift = hue_shift / 360.0
                # Build lookup table: for each possible (r,g,b) → shifted (r,g,b)
                # Operate per-pixel but only on unique values via putdata is still slow;
                # use numpy if available, else fall back to per-pixel colorsys
                try:
                    import numpy as np
                    arr = np.array(fg_rgb, dtype=np.float32) / 255.0
                    r, g, b = arr[...,0], arr[...,1], arr[...,2]
                    maxc  = np.maximum(np.maximum(r, g), b)
                    minc  = np.minimum(np.minimum(r, g), b)
                    delta = maxc - minc
                    valid = maxc > 1e-7   # mask: skip pure black/grey pixels
                    v = maxc

                    # np.divide with where= avoids evaluating division on invalid pixels,
                    # unlike np.where which always computes both branches first.
                    s = np.divide(delta, maxc,
                                  out=np.zeros_like(maxc), where=valid)
                    safe_d = np.where(delta > 1e-7, delta, 1.0)  # avoid /0 in h calc
                    h = np.where(maxc == r, (g - b) / safe_d % 6,
                        np.where(maxc == g, (b - r) / safe_d + 2,
                                            (r - g) / safe_d + 4)) / 6.0
                    h = (h + h_shift) % 1.0
                    # HSV → RGB vectorized
                    i = (h * 6).astype(np.int32) % 6
                    f = h * 6 - i
                    p = v * (1 - s); q = v * (1 - f*s); t_ = v * (1 - (1-f)*s)
                    idx = i
                    rgb_out = np.stack([
                        np.where(idx==0,v, np.where(idx==1,q, np.where(idx==2,p,
                          np.where(idx==3,p, np.where(idx==4,t_,v))))),
                        np.where(idx==0,t_,np.where(idx==1,v, np.where(idx==2,v,
                          np.where(idx==3,q, np.where(idx==4,p,p))))),
                        np.where(idx==0,p, np.where(idx==1,p, np.where(idx==2,t_,
                          np.where(idx==3,v, np.where(idx==4,v,q))))),
                    ], axis=-1)
                    fg = Image.fromarray((rgb_out * 255).clip(0,255).astype(np.uint8), "RGB")
                except ImportError:
                    # numpy not available — skip hue shift in preview (still applied on export)
                    pass

        canvas_img = bg_layer.copy()
        canvas_img.paste(fg, (vx, vy))

        # ── Apply blur boxes (watermark / logo concealment) ───────────────────────
        # Each box is cropped, heavily blurred, then pasted back into the canvas.
        # This is a visual approximation of the FFmpeg boxblur applied on export.
        for _box in state.get("blur_boxes", []):
            if _box.get("tracked"):
                _bx_c, _by_c, _bw_c, _bh_c = map_tracked_box_to_canvas(_box, src.width, src.height, state)
                _bx = int(_bx_c * EDIT_PREV_SCALE)
                _by = int(_by_c * EDIT_PREV_SCALE)
                _bw = max(4, int(_bw_c * EDIT_PREV_SCALE))
                _bh = max(4, int(_bh_c * EDIT_PREV_SCALE))
            else:
                _bx = int(_box["x"] * EDIT_PREV_SCALE)
                _by = int(_box["y"] * EDIT_PREV_SCALE)
                _bw = max(4, int(_box["w"] * EDIT_PREV_SCALE))
                _bh = max(4, int(_box["h"] * EDIT_PREV_SCALE))
            _bx2, _by2 = min(_bx + _bw, W), min(_by + _bh, H)
            if _bx >= W or _by >= H or _bx2 <= 0 or _by2 <= 0:
                continue
            _region = canvas_img.crop((_bx, _by, _bx2, _by2))
            _region = _region.filter(ImageFilter.GaussianBlur(radius=9))
            canvas_img.paste(_region, (_bx, _by))

        # Draw title text
        draw = ImageDraw.Draw(canvas_img)
        _fp = {
            "impact":    "C:/Windows/Fonts/impact.ttf",
            "arialbd":   "C:/Windows/Fonts/arialbd.ttf",
            "arial":     "C:/Windows/Fonts/arial.ttf",
            "segoeuib":  "C:/Windows/Fonts/segoeuib.ttf",
            "calibrib":  "C:/Windows/Fonts/calibrib.ttf",
            "verdanab":  "C:/Windows/Fonts/verdanab.ttf",
            "comicbd":   "C:/Windows/Fonts/comicbd.ttf",
            "trebucbd":  "C:/Windows/Fonts/trebucbd.ttf",
        }
        fsz = max(8, int(state.get("font_size", 52) * EDIT_PREV_SCALE))
        _fp_italic = {
            "arial":    "C:/Windows/Fonts/ariali.ttf",
            "arialbd":  "C:/Windows/Fonts/arialbi.ttf",
            "calibrib": "C:/Windows/Fonts/calibriz.ttf",
            "verdanab": "C:/Windows/Fonts/verdanai.ttf",
            "trebucbd": "C:/Windows/Fonts/trebucit.ttf",
        }
        _fn   = state.get("font_name", "impact")
        _is_italic = bool(state.get("font_italic", False))
        _font_path = ((_fp_italic if _is_italic else {}).get(_fn)
                      or _fp.get(_fn, _fp["impact"]))
        try:
            font = ImageFont.truetype(_font_path, fsz)
        except Exception:
            font = ImageFont.load_default()

        clean = re.sub(r"[^\x00-\x7F\u00C0-\u024F]", "", title).strip()

        # Compute tx first so we can derive the exact pixel width available for text.
        # wrap_pct drives both the bounding box right edge and text wrapping,
        # so they stay in sync.
        tx = int(state.get("text_x", 40) * EDIT_PREV_SCALE)
        ty = int(state.get("text_y", 60) * EDIT_PREV_SCALE)
        wrap_pct  = max(0.3, min(1.0, float(state.get("title_wrap_pct", 1.0))))

        max_line_w = max(30, int(EDIT_PREV_W * wrap_pct) - tx)
        try:
            sample    = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            avg_char_w = max(1.0, font.getlength(sample) / len(sample))
            chars     = max(5, int(max_line_w / avg_char_w))
        except Exception:
            chars = max(10, int(30 * 52 / max(state.get("font_size", 52), 1) * wrap_pct))

        lines = textwrap.wrap(clean, width=chars) or [clean[:chars]]
        multiline_str = "\n".join(lines)

        align = state.get("text_align", "left")

        # CapCut-style alignment: anchor text to the appropriate edge of the text box.
        # rx = right edge of text box in preview pixels.
        rx = min(int(EDIT_PREV_W * wrap_pct), EDIT_PREV_W - 1)
        _ANC = {"left": ("la", tx), "center": ("ma", (tx + rx) // 2), "right": ("ra", rx)}
        pil_anchor, anchor_x = _ANC.get(align, ("la", tx))

        _hex = state.get("text_color_hex", "")
        if _hex and len(_hex) == 7 and _hex.startswith("#"):
            try:
                color = (int(_hex[1:3], 16), int(_hex[3:5], 16), int(_hex[5:7], 16))
            except ValueError:
                color = (255, 255, 255)
        else:
            color = {"white": (255,255,255), "yellow": (255,240,0),
                     "black": (0,0,0)}.get(state.get("text_color", "white"), (255,255,255))
        bg_mode = state.get("text_bg", "none")

        try:
            bb = draw.multiline_textbbox(
                (anchor_x, ty), multiline_str, font=font,
                align=align, anchor=pil_anchor)
            # Cache precise bb so _draw_title_handles can draw tight CapCut-style frame.
            self._title_bb_cache = bb
            if bg_mode == "box":
                _brad  = int(state.get("box_radius", 0))
                _bmode = state.get("box_mode", "frame")
                _pad_x = max(1, int(state.get("box_pad_x", 30) * EDIT_PREV_SCALE))
                _pad_y = max(1, int(state.get("box_pad_y", 20) * EDIT_PREV_SCALE))
                # Resolve fill — mirrors export renderer
                _BG_RGB = {"black":(0,0,0), "darkgray":(30,30,30),
                           "gray":(90,90,90), "white":(255,255,255)}
                _box_clr = state.get("box_bg_color", "black")
                if _box_clr == "custom":
                    _ch = state.get("box_bg_color_hex", "#222222").lstrip("#")
                    try:
                        _rgb = (int(_ch[0:2],16), int(_ch[2:4],16), int(_ch[4:6],16))
                    except Exception:
                        _rgb = (0, 0, 0)
                else:
                    _rgb = _BG_RGB.get(_box_clr, (0, 0, 0))
                _alpha = max(0, min(255, int(state.get("box_opacity", 90) * 2.55)))
                _fill  = (*_rgb, _alpha)
                # Resolve x1/x2 overrides (same sentinel logic as export)
                _x1p = float(state.get("box_x1_pct", -1.0))
                _x2p = float(state.get("box_x2_pct", -1.0))
                _bx1 = int(EDIT_PREV_W * _x1p) if _x1p >= 0 else (bb[0] - _pad_x)
                _bx2 = int(EDIT_PREV_W * _x2p) if _x2p >= 0 else (bb[2] + _pad_x)
                if _bmode == "per_line" and len(lines) > 0:
                    try:
                        ascent, descent = font.getmetrics()
                        line_h  = ascent + descent
                        pil_spc = 4
                        curr_y  = ty
                        for single_line in lines:
                            lbb = draw.textbbox(
                                (anchor_x, curr_y), single_line,
                                font=font, anchor=pil_anchor)
                            _lx1 = int(EDIT_PREV_W * _x1p) if _x1p >= 0 else lbb[0] - _pad_x
                            _lx2 = int(EDIT_PREV_W * _x2p) if _x2p >= 0 else lbb[2] + _pad_x
                            _c = [_lx1, lbb[1] - _pad_y, _lx2, lbb[3] + _pad_y]
                            if _brad > 0:
                                draw.rounded_rectangle(_c, radius=min(_brad, _pad_y + line_h // 2), fill=_fill)
                            else:
                                draw.rectangle(_c, fill=_fill)
                            curr_y += line_h + pil_spc
                    except Exception:
                        draw.rectangle([_bx1, bb[1]-_pad_y, _bx2, bb[3]+_pad_y], fill=_fill)
                else:
                    _bcoords = [_bx1, bb[1] - _pad_y, _bx2, bb[3] + _pad_y]
                    if _brad > 0:
                        draw.rounded_rectangle(_bcoords, radius=_brad, fill=_fill)
                    else:
                        draw.rectangle(_bcoords, fill=_fill)
            elif bg_mode == "outline":
                draw.rounded_rectangle(
                    [bb[0] - 8, bb[1] - 6, bb[2] + 8, bb[3] + 6],
                    radius=10,
                    fill=(0, 0, 0, 140),
                    outline=(255, 255, 255, 230),
                    width=2,
                )
        except Exception:
            pass

        # ── Line metrics (shared by box + text draw) ───────────────────────────
        try:
            _asc, _des = font.getmetrics()
        except Exception:
            _asc, _des = int(fsz * 0.8), int(fsz * 0.2)
        _nlh        = _asc + _des
        _pil_spc    = max(0, int(_nlh * (float(state.get("line_height", 1.2)) - 1.0)))
        _total_lh   = _nlh + _pil_spc
        _letter_spc = int(state.get("letter_spacing", 0))
        _dec        = state.get("text_decoration", "none")
        _dec_thick  = max(1, int(fsz * 0.055))
        _t_opacity  = int(state.get("text_opacity", 100))
        _t_rotation = float(state.get("text_rotation", 0.0))

        if bg_mode == "none":
            for ox, oy in [(-1,-1),(1,-1),(-1,1),(1,1),(0,2)]:
                draw.multiline_text(
                    (anchor_x+ox, ty+oy), multiline_str,
                    font=font, fill=(0,0,0,200), align=align,
                    anchor=pil_anchor, spacing=_pil_spc)

        # Text stroke: bold adds 1px synthetic stroke; user stroke_width overrides
        _user_sw   = int(state.get("stroke_width", 0))
        _sc_hex    = state.get("stroke_color_hex", "#000000")
        try:
            _stroke_fill = (int(_sc_hex[1:3],16), int(_sc_hex[3:5],16), int(_sc_hex[5:7],16))
        except Exception:
            _stroke_fill = (0, 0, 0)
        _stroke = max(1 if state.get("font_bold", False) else 0, _user_sw)

        if _letter_spc != 0:
            _curr_y = ty
            for _ln in lines:
                _lw = sum(font.getlength(c) for c in _ln) + _letter_spc * max(0, len(_ln)-1)
                _lx = (int(anchor_x - _lw/2) if align == "center"
                       else int(anchor_x - _lw) if align == "right"
                       else anchor_x)
                _cx = _lx
                for _ch in _ln:
                    draw.text((_cx, _curr_y), _ch, font=font, fill=color,
                              stroke_width=_stroke, stroke_fill=color)
                    _cx += int(font.getlength(_ch)) + _letter_spc
                if _dec != "none":
                    _dy = (_curr_y + _des + 1 if _dec == "underline"
                           else _curr_y - _asc + int(_nlh * 0.35))
                    draw.line([(_lx, _dy), (int(_lx+_lw), _dy)],
                              fill=color, width=_dec_thick)
                _curr_y += _total_lh
        else:
            draw.multiline_text(
                (anchor_x, ty), multiline_str,
                font=font, fill=color, align=align, anchor=pil_anchor,
                stroke_width=_stroke, stroke_fill=_stroke_fill, spacing=_pil_spc)
            if _dec != "none":
                _curr_y = ty
                for _ln in lines:
                    _lbb = draw.textbbox((anchor_x, _curr_y), _ln, font=font, anchor=pil_anchor)
                    _dy  = (_lbb[3]+1 if _dec == "underline"
                            else _lbb[1]+int((_lbb[3]-_lbb[1])*0.35))
                    draw.line([(_lbb[0], _dy), (_lbb[2], _dy)],
                              fill=color, width=_dec_thick)
                    _curr_y += _total_lh

        # Opacity & rotation applied to the entire canvas_img layer
        if _t_opacity < 100:
            _r2, _g2, _b2, _a2 = canvas_img.split()
            _a2 = _a2.point(lambda v: int(v * _t_opacity / 100))
            canvas_img = Image.merge("RGBA", (_r2, _g2, _b2, _a2))
        if abs(_t_rotation) > 0.5:
            _bb = getattr(self, "_title_bb_cache", None)
            if _bb:
                _rcx = (_bb[0] + _bb[2]) / 2
                _rcy = (_bb[1] + _bb[3]) / 2
                canvas_img = canvas_img.rotate(-_t_rotation, center=(_rcx, _rcy), expand=False)

        # ── Watermark preview ─────────────────────────────────────────────────────────
        _wm_txt = state.get("watermark_text", "").strip()
        if _wm_txt:
            # Ensure canvas is RGBA so alpha blending works
            if canvas_img.mode != "RGBA":
                canvas_img = canvas_img.convert("RGBA")
            _wm_draw  = ImageDraw.Draw(canvas_img)
            _wm_sz    = max(8, int(state.get("watermark_size", 28) * EDIT_PREV_SCALE))
            _wm_alpha = max(5, min(100, int(state.get("watermark_opacity", 50))))
            _wm_hex   = state.get("watermark_color", "#FFFFFF").lstrip("#")
            try:
                _wm_r = int(_wm_hex[0:2], 16)
                _wm_g = int(_wm_hex[2:4], 16)
                _wm_b = int(_wm_hex[4:6], 16)
            except Exception:
                _wm_r, _wm_g, _wm_b = 255, 255, 255
            _wm_fill = (_wm_r, _wm_g, _wm_b, int(_wm_alpha * 2.55))
            _WM_PAD   = int(30 * EDIT_PREV_SCALE)
            _wm_pos_map = {
                "TL": (_WM_PAD, _WM_PAD),
                "TC": (W // 2, _WM_PAD),
                "TR": (W - _WM_PAD, _WM_PAD),
                "ML": (_WM_PAD, H // 2),
                "MC": (W // 2, H // 2),
                "MR": (W - _WM_PAD, H // 2),
                "BL": (_WM_PAD, H - _WM_PAD),
                "BC": (W // 2, H - _WM_PAD),
                "BR": (W - _WM_PAD, H - _WM_PAD),
            }
            _wm_anchor_map = {
                "TL": "la", "TC": "ma", "TR": "ra",
                "ML": "lm", "MC": "mm", "MR": "rm",
                "BL": "ld", "BC": "md", "BR": "rd",
            }
            _wm_pos_code = state.get("watermark_pos", "BR")
            _wmx, _wmy   = _wm_pos_map.get(_wm_pos_code, (W - _WM_PAD, H - _WM_PAD))
            _wm_anch     = _wm_anchor_map.get(_wm_pos_code, "rd")
            try:
                _wm_font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", _wm_sz)
            except Exception:
                _wm_font = ImageFont.load_default()
            # Outline for readability
            _wm_shadow = (0, 0, 0, int(_wm_alpha * 2.55 * 0.7))
            for _ox, _oy in [(-1,-1),(1,-1),(-1,1),(1,1)]:
                _wm_draw.text((_wmx+_ox, _wmy+_oy), _wm_txt,
                              font=_wm_font, fill=_wm_shadow, anchor=_wm_anch)
            _wm_draw.text((_wmx, _wmy), _wm_txt,
                          font=_wm_font, fill=_wm_fill, anchor=_wm_anch)

        # ── Subtitle preview (placeholder line at adjustable position) ──────────
        _sub_on = state.get("subtitles", False)
        if _sub_on:
            if canvas_img.mode != "RGBA":
                canvas_img = canvas_img.convert("RGBA")
            _sub_draw  = ImageDraw.Draw(canvas_img)
            _sub_sz    = max(8, int(24 * EDIT_PREV_SCALE))
            _sub_margin_v = int(state.get("sub_margin_v", 200) * EDIT_PREV_SCALE)
            _sub_y     = H - _sub_margin_v
            try:
                _sub_font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", _sub_sz)
            except Exception:
                _sub_font = ImageFont.load_default()
            _sub_txt   = "[subtitle preview]"
            # Semi-transparent pill background
            _sub_bb    = _sub_draw.textbbox((W//2, _sub_y), _sub_txt,
                                            font=_sub_font, anchor="mm")
            _sub_draw.rectangle(
                [_sub_bb[0]-8, _sub_bb[1]-4, _sub_bb[2]+8, _sub_bb[3]+4],
                fill=(0, 0, 0, 140))
            for _ox, _oy in [(-1,0),(1,0),(0,-1),(0,1)]:
                _sub_draw.text((W//2+_ox, _sub_y+_oy), _sub_txt,
                               font=_sub_font, fill=(0,0,0,180), anchor="mm")
            _sub_draw.text((W//2, _sub_y), _sub_txt,
                           font=_sub_font, fill=(255,255,255,230), anchor="mm")

        return canvas_img

    # ── Shared helper: box edge positions in preview px ─────────────────────
    def _compute_box_x_edges(self, st: dict) -> tuple:
        """Return (box_left_px, box_right_px) in preview coordinates.

        Uses box_x1_pct / box_x2_pct overrides when set; falls back to
        text-bounding-box + pad_x (the 'auto' / default behaviour).
        """
        bb = getattr(self, "_title_bb_cache", None)
        _pad_x = max(1, int(st.get("box_pad_x", 30) * EDIT_PREV_SCALE))
        x1p = float(st.get("box_x1_pct", -1.0))
        x2p = float(st.get("box_x2_pct", -1.0))
        bx1 = int(EDIT_PREV_W * x1p) if x1p >= 0 else ((bb[0] - _pad_x) if bb else 0)
        bx2 = int(EDIT_PREV_W * x2p) if x2p >= 0 else ((bb[2] + _pad_x) if bb else EDIT_PREV_W)
        return max(0, bx1), min(EDIT_PREV_W, bx2)

    def _display_edit_preview(self, img):
        from PIL import ImageTk
        ref = ImageTk.PhotoImage(img)
        self._edit_photo_ref = ref          # keep reference alive
        self._edit_canvas.delete("all")
        self._edit_canvas.create_image(0, 0, image=ref, anchor="nw")
        # Overlay interactive title handles on top of the PIL image
        if self._edit_sel_idx >= 0 and not self._edit_draw_mode:
            self._draw_title_handles()

    def _draw_title_handles(self):
        """Draw CapCut-style tight bounding box + handles using cached PIL text bb."""
        import textwrap, re as _re
        if self._edit_sel_idx < 0:
            return
        st    = self._edit_queue[self._edit_sel_idx]["state"]
        title = self._edit_queue[self._edit_sel_idx]["title"]

        tx       = int(st.get("text_x", 40) * EDIT_PREV_SCALE)
        ty       = int(st.get("text_y", 60) * EDIT_PREV_SCALE)
        wrap_pct = max(0.3, min(1.0, float(st.get("title_wrap_pct", 1.0))))
        font_size = st.get("font_size", 52)
        # rx_wrap = right edge of the WRAP BOUNDARY (where resize handle lives)
        rx_wrap  = min(int(EDIT_PREV_W * wrap_pct), EDIT_PREV_W - 4)

        # Use cached PIL bounding box (computed in _build_edit_image) for tight fit.
        # Fallback to rough estimate if cache is stale or missing.
        bb = getattr(self, "_title_bb_cache", None)
        if bb is None:
            clean = _re.sub(r"[^\x00-\x7F\u00C0-\u024F]", "", title).strip()
            chars = max(10, int(30 * 52 / max(font_size, 1) * wrap_pct))
            lines = textwrap.wrap(clean, width=chars) or [clean[:chars]]
            fsz   = max(8, int(font_size * EDIT_PREV_SCALE))
            est_h = int(len(lines) * fsz * 1.35)
            bb    = (tx, ty, rx_wrap, ty + est_h)

        PAD = 5
        bx1, by1 = bb[0] - PAD, bb[1] - PAD
        bx2, by2 = bb[2] + PAD, bb[3] + PAD

        # Dashed selection rectangle — tight around actual text pixels
        self._edit_canvas.create_rectangle(
            bx1, by1, bx2, by2,
            outline="#22d3ee", width=1, dash=(4, 2), tags="title_box",
        )
        # Corner circles (CapCut style — 4 corners)
        for cx, cy in [(bx1, by1), (bx2, by1), (bx1, by2), (bx2, by2)]:
            self._edit_canvas.create_oval(
                cx - 5, cy - 5, cx + 5, cy + 5,
                fill="#22d3ee", outline="white", width=1, tags="title_box",
            )
        # Right-edge resize handle (square) — always at the WRAP BOUNDARY (rx_wrap),
        # NOT the text content edge, so detection in _on_edit_drag_start matches exactly.
        mid_y = (by1 + by2) // 2
        self._edit_canvas.create_rectangle(
            rx_wrap - 6, mid_y - 6, rx_wrap + 6, mid_y + 6,
            fill="#22d3ee", outline="white", width=1, tags="title_box",
        )
        # Dashed vertical line at wrap boundary so user can see the wrap limit
        self._edit_canvas.create_line(
            rx_wrap, by1, rx_wrap, by2,
            fill="#22d3ee", dash=(2, 4), width=1, tags="title_box",
        )

        # Box left/right edge handles — amber arrows, visible only when text_bg=="box".
        # These let the user drag the dark box edge independently from the text.
        if st.get("text_bg") == "box":
            bx1, bx2 = self._compute_box_x_edges(st)
            mid_y = (by1 + by2) // 2
            hs = 10  # half-size of arrow triangle
            # ◀ left arrow handle
            self._edit_canvas.create_polygon(
                bx1 + hs, mid_y - hs,
                bx1,      mid_y,
                bx1 + hs, mid_y + hs,
                fill="#f59e0b", outline="white", width=1, tags="title_box",
            )
            # ▶ right arrow handle
            self._edit_canvas.create_polygon(
                bx2 - hs, mid_y - hs,
                bx2,      mid_y,
                bx2 - hs, mid_y + hs,
                fill="#f59e0b", outline="white", width=1, tags="title_box",
            )

    def _on_edit_motion(self, event):
        """Update cursor based on which handle the pointer is near."""
        if self._edit_draw_mode or self._edit_sel_idx < 0:
            return
        st = self._edit_queue[self._edit_sel_idx]["state"]
        wrap_pct = float(st.get("title_wrap_pct", 1.0))
        rx = min(int(EDIT_PREV_W * wrap_pct), EDIT_PREV_W - 4)
        HIT = 18
        if abs(event.x - rx) < HIT:
            self._edit_canvas.config(cursor="sb_h_double_arrow")
        elif st.get("text_bg") == "box":
            bx1, bx2 = self._compute_box_x_edges(st)
            if abs(event.x - bx1) < HIT or abs(event.x - bx2) < HIT:
                self._edit_canvas.config(cursor="sb_h_double_arrow")
            else:
                self._edit_canvas.config(cursor="fleur")
        else:
            self._edit_canvas.config(cursor="fleur")

    def _on_edit_drag_start(self, event):
        self._edit_drag_origin  = (event.x, event.y)
        self._edit_resize_mode  = False
        self._edit_box_l_mode   = False   # dragging box LEFT edge
        self._edit_box_r_mode   = False   # dragging box RIGHT edge

        if self._edit_draw_mode or self._edit_sel_idx < 0:
            return

        st = self._edit_queue[self._edit_sel_idx]["state"]
        wrap_pct = float(st.get("title_wrap_pct", 1.0))
        rx  = min(int(EDIT_PREV_W * wrap_pct), EDIT_PREV_W - 4)
        HIT = 18

        if abs(event.x - rx) < HIT:
            self._edit_resize_mode  = True
            self._drag_wrap_origin  = wrap_pct
            self._drag_wrap_start_x = event.x
        elif st.get("text_bg") == "box":
            bx1, bx2 = self._compute_box_x_edges(st)
            if abs(event.x - bx1) < HIT:
                self._edit_box_l_mode    = True
                self._drag_box_start_x   = event.x
                self._drag_box_x1_origin = bx1 / EDIT_PREV_W
            elif abs(event.x - bx2) < HIT:
                self._edit_box_r_mode    = True
                self._drag_box_start_x   = event.x
                self._drag_box_x2_origin = bx2 / EDIT_PREV_W
            else:
                self._drag_text_origin = (st["text_x"], st["text_y"])
        else:
            self._drag_text_origin = (st["text_x"], st["text_y"])

    def _on_edit_drag(self, event):
        if self._edit_sel_idx < 0:
            return
        if self._edit_draw_mode:
            x0, y0 = self._edit_drag_origin
            self._edit_canvas.delete("rubber_band")
            self._edit_canvas.create_rectangle(
                x0, y0, event.x, event.y,
                outline="#22d3ee", width=2, dash=(4, 2),
                tags="rubber_band",
            )
            return

        st = self._edit_queue[self._edit_sel_idx]["state"]

        def _regen():
            img = self._build_edit_image(
                self._edit_queue[self._edit_sel_idx]["clip_path"],
                self._edit_queue[self._edit_sel_idx]["title"], st)
            if img:
                self._display_edit_preview(img)

        if self._edit_resize_mode:
            # Text wrap width handle (cyan square)
            dx_pct = (event.x - self._drag_wrap_start_x) / EDIT_PREV_W
            new_pct = max(0.15, min(1.0, self._drag_wrap_origin + dx_pct))
            st["title_wrap_pct"] = new_pct
            self._edit_title_wrap_pct.set(new_pct)
            _regen()
            return

        if getattr(self, "_edit_box_l_mode", False):
            # Box LEFT edge handle (amber ◀) — drag changes box_x1_pct
            dx_pct = (event.x - self._drag_box_start_x) / EDIT_PREV_W
            x2_max = float(st.get("box_x2_pct", -1.0))
            if x2_max < 0:  # auto right — treat as current right edge in pct
                _, bx2 = self._compute_box_x_edges(st)
                x2_max = bx2 / EDIT_PREV_W
            new_pct = max(0.0, min(x2_max - 0.05, self._drag_box_x1_origin + dx_pct))
            st["box_x1_pct"] = new_pct
            _regen()
            return

        if getattr(self, "_edit_box_r_mode", False):
            # Box RIGHT edge handle (amber ▶) — drag changes box_x2_pct
            dx_pct = (event.x - self._drag_box_start_x) / EDIT_PREV_W
            x1_min = float(st.get("box_x1_pct", -1.0))
            if x1_min < 0:
                bx1, _ = self._compute_box_x_edges(st)
                x1_min = bx1 / EDIT_PREV_W
            new_pct = min(1.0, max(x1_min + 0.05, self._drag_box_x2_origin + dx_pct))
            st["box_x2_pct"] = new_pct
            _regen()
            return

        # Normal mode: move the title text
        dx = int((event.x - self._edit_drag_origin[0]) / EDIT_PREV_SCALE)
        dy = int((event.y - self._edit_drag_origin[1]) / EDIT_PREV_SCALE)
        st["text_x"] = max(0, min(980, self._drag_text_origin[0] + dx))
        st["text_y"] = max(0, min(1820, self._drag_text_origin[1] + dy))
        _regen()

    def _on_edit_drag_end(self, event):
        if self._edit_draw_mode and self._edit_sel_idx >= 0:
            self._edit_canvas.delete("rubber_band")
            x0, y0 = self._edit_drag_origin
            x1, y1 = event.x, event.y
            rw, rh = abs(x1 - x0), abs(y1 - y0)
            if rw < 5 or rh < 5:
                return  # ignore accidental micro-clicks
            box = {
                "x": int(min(x0, x1) / EDIT_PREV_SCALE),
                "y": int(min(y0, y1) / EDIT_PREV_SCALE),
                "w": int(rw / EDIT_PREV_SCALE),
                "h": int(rh / EDIT_PREV_SCALE),
            }
            boxes = self._edit_queue[self._edit_sel_idx]["state"]["blur_boxes"]
            boxes.append(box)
            n = len(boxes)
            self._blur_listbox.insert(
                END, f"Box {n}: ({box['x']},{box['y']})  {box['w']}×{box['h']} px")
            self._regen_edit_preview()

    # ── Blur-region / cover-banner helpers ──────────────────────────────────

    def _pick_box_bg_color(self):
        """Open color picker for text background box; persists selection to config."""
        from tkinter.colorchooser import askcolor
        current = self._edit_box_bg_color_hex.get() or "#222222"
        result = askcolor(color=current, title="Text Background Color", parent=self)
        if result and result[1]:
            hex_val = result[1]
            self._edit_box_bg_color_hex.set(hex_val)
            # Determine readable label fg
            fg_col = "white" if hex_val.lower() < "#888888" else "black"
            self._box_custom_swatch.config(bg=hex_val, fg=fg_col)
            # Switch radio to "custom"
            self._edit_box_bg_color.set("custom")
            # Persist to config so next session restores the color
            self._cfg["box_bg_custom_hex"] = hex_val
            self._save_config()
            self._regen_edit_preview()

    def _toggle_draw_mode(self):
        """Switch between title-drag mode and blur-box drawing mode."""
        self._edit_draw_mode = not self._edit_draw_mode
        self._draw_mode_on   = self._edit_draw_mode      # used by _on_escape
        if self._edit_draw_mode:
            self._btn_draw_mode.config(text="✏  Draw Mode: ON",
                                       bg="#0a2a1e", fg=CLR_SUCCESS,
                                       activebackground="#0f3d2a")
            self._edit_canvas.config(cursor="crosshair")
        else:
            self._btn_draw_mode.config(text="✏  Draw Mode: OFF",
                                       bg="#0f1e3d", fg="#60a5fa",
                                       activebackground="#172d5c")
            self._edit_canvas.config(cursor="fleur")

    def _clear_blur_boxes(self):
        """Remove all blur boxes from the current queue item."""
        if self._edit_sel_idx < 0:
            return
        self._edit_queue[self._edit_sel_idx]["state"]["blur_boxes"] = []
        self._blur_listbox.delete(0, END)
        self._regen_edit_preview()

    def _refresh_blur_listbox(self):
        """Rebuild the blur listbox with mode icons and start_time info."""
        self._blur_listbox.delete(0, END)
        if self._edit_sel_idx < 0:
            return
        boxes = self._edit_queue[self._edit_sel_idx]["state"].get("blur_boxes", [])
        for _i, _b in enumerate(boxes):
            if _b.get("tracked"):
                label = f"🎯 Tracked {_i+1}"
            else:
                _icon = "🔍" if _b.get("mode") == "delogo" else "🫧"
                _st   = _b.get("start_time", 0.0) or 0.0
                _info = f" @{_st:.1f}s" if _st > 0.05 else ""
                label = f"{_icon} Box {_i+1}: ({_b['x']},{_b['y']}) {_b['w']}×{_b['h']}px{_info}"
            self._blur_listbox.insert(END, label)

    def _remove_selected_blur_box(self):
        """Remove the blur box selected in the listbox."""
        if self._edit_sel_idx < 0:
            return
        sel = self._blur_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        boxes = self._edit_queue[self._edit_sel_idx]["state"]["blur_boxes"]
        if 0 <= idx < len(boxes):
            boxes.pop(idx)
            self._refresh_blur_listbox()
            self._regen_edit_preview()

    # ── Object Tracking ────────────────────────────────────────────────────────

    def _open_track_popup(self):
        """ROI picker with time-seek slider → run CSRT tracker from chosen frame."""
        if self._edit_sel_idx < 0:
            messagebox.showwarning("No clip", "Select a clip first.")
            return

        try:
            import cv2 as _cv2  # noqa
        except ImportError:
            messagebox.showerror(
                "OpenCV Required",
                "Install opencv-contrib-python to use object tracking:\n\n"
                "  pip install opencv-contrib-python\n\nThen restart the app."
            )
            return

        clip = Path(self._edit_queue[self._edit_sel_idx]["clip_path"])
        if not clip.exists():
            messagebox.showerror("File not found", str(clip))
            return

        dur     = get_video_duration(clip) or 10.0
        orig_vw = get_video_width(clip)
        orig_vh = get_video_height(clip)

        # Max display: 600 wide OR 440 tall (keeps popup on screen)
        MAX_W, MAX_H = 580, 340
        scale = min(MAX_W / orig_vw, MAX_H / orig_vh, 1.0)
        disp_w = max(1, int(orig_vw * scale))
        disp_h = max(1, int(orig_vh * scale))
        disp_scale_x = orig_vw / disp_w
        disp_scale_y = orig_vh / disp_h

        import tempfile as _tmp
        from PIL import Image as _PI, ImageTk as _PITk

        frame_png = Path(_tmp.gettempdir()) / f"_track_frame_{clip.stem[:30]}.png"

        def _extract_frame(t_sec: float) -> bool:
            """Extract frame at t_sec → frame_png. Returns True on success."""
            r = subprocess.run(
                [FFMPEG, "-y", "-ss", f"{t_sec:.3f}", "-i", str(clip),
                 "-vframes", "1",
                 "-vf", f"scale={disp_w}:{disp_h}",
                 str(frame_png)],
                capture_output=True, timeout=30,
            )
            return r.returncode == 0 and frame_png.exists() and frame_png.stat().st_size > 0

        # Extract first frame to start
        if not _extract_frame(0.0):
            messagebox.showerror("Frame extract failed",
                                 "Could not extract frame from clip.")
            return

        # ── Build popup ────────────────────────────────────────────────────────
        popup = tk.Toplevel(self)
        popup.title("🎯 Track Object — Seek to where object appears, then draw box")
        popup.configure(bg=CLR_BG)
        popup.grab_set()
        popup.resizable(False, False)

        tk.Label(popup,
                 text="① Drag the time slider to where the object first appears\n"
                      "② Click & drag on the frame to draw a box around it\n"
                      "③ Click Confirm & Track",
                 bg=CLR_BG, fg=CLR_FG, font=("Segoe UI", 9),
                 justify=LEFT).pack(pady=(10, 4), padx=12, anchor=W)

        # ── Canvas ────────────────────────────────────────────────────────────
        canvas = tk.Canvas(popup, width=disp_w, height=disp_h,
                           cursor="crosshair", bg="#111",
                           highlightthickness=2, highlightbackground="#334155")
        canvas.pack(padx=12, pady=(0, 4))

        _img_ref: list = [None]   # mutable cell to hold PhotoImage ref

        def _show_frame_on_canvas():
            try:
                pil = _PI.open(frame_png).convert("RGB")
                tk_img = _PITk.PhotoImage(pil)
                _img_ref[0] = tk_img       # prevent GC
                canvas.delete("all")
                canvas.create_image(0, 0, anchor=NW, image=tk_img)
                # Redraw ROI if already drawn
                if _roi["rect"]:
                    _roi["rect"] = canvas.create_rectangle(
                        _roi["x0"], _roi["y0"], _roi["x1"], _roi["y1"],
                        outline="#4ade80", width=2, dash=(4, 2)
                    )
            except Exception as e:
                pass

        _show_frame_on_canvas()

        # ── Time seek slider ───────────────────────────────────────────────────
        seek_row = tk.Frame(popup, bg=CLR_BG)
        seek_row.pack(fill=X, padx=12, pady=(0, 2))
        tk.Label(seek_row, text="Seek:", bg=CLR_BG, fg=CLR_DIM,
                 font=("Segoe UI", 8)).pack(side=LEFT)

        _seek_var = tk.DoubleVar(value=0.0)
        _seek_lbl = tk.Label(seek_row, text="0.0s", bg=CLR_BG, fg=CLR_FG2,
                             font=("Consolas", 8), width=6)
        _seek_lbl.pack(side=RIGHT)

        def _on_seek_change(v):
            t = float(v)
            _seek_lbl.config(text=f"{t:.1f}s")

        def _on_seek_release(event=None):
            t = _seek_var.get()
            popup.config(cursor="watch")
            popup.update()
            # Re-extract frame at this time
            _extract_frame(t)
            _roi["rect"] = None   # clear old ROI on frame change
            _show_frame_on_canvas()
            popup.config(cursor="")

        seek_scale = tk.Scale(
            seek_row, variable=_seek_var,
            from_=0, to=dur, resolution=0.1,
            orient=HORIZONTAL, length=disp_w - 70,
            bg=CLR_BG, fg=CLR_FG, troughcolor=CLR_SURFACE,
            highlightthickness=0, bd=0, sliderrelief=FLAT,
            command=_on_seek_change, showvalue=False,
        )
        seek_scale.pack(side=LEFT, fill=X, expand=True, padx=(4, 4))
        seek_scale.bind("<ButtonRelease-1>", _on_seek_release)

        # ── ROI drag ──────────────────────────────────────────────────────────
        _roi = {"x0": 0, "y0": 0, "x1": 0, "y1": 0, "rect": None}

        def _on_press(ev):
            _roi["x0"] = ev.x; _roi["y0"] = ev.y
            if _roi["rect"]:
                canvas.delete(_roi["rect"])
                _roi["rect"] = None

        def _on_drag(ev):
            _roi["x1"] = ev.x; _roi["y1"] = ev.y
            if _roi["rect"]:
                canvas.delete(_roi["rect"])
            _roi["rect"] = canvas.create_rectangle(
                _roi["x0"], _roi["y0"], ev.x, ev.y,
                outline="#4ade80", width=2, dash=(4, 2)
            )

        def _on_release(ev):
            _roi["x1"] = ev.x; _roi["y1"] = ev.y

        canvas.bind("<ButtonPress-1>",   _on_press)
        canvas.bind("<B1-Motion>",       _on_drag)
        canvas.bind("<ButtonRelease-1>", _on_release)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = tk.Frame(popup, bg=CLR_BG)
        btn_row.pack(pady=(4, 12), padx=12, fill=X)

        def _confirm():
            x0 = min(_roi["x0"], _roi["x1"])
            y0 = min(_roi["y0"], _roi["y1"])
            x1 = max(_roi["x0"], _roi["x1"])
            y1 = max(_roi["y0"], _roi["y1"])
            if (x1 - x0) < 10 or (y1 - y0) < 10:
                messagebox.showwarning("Too small",
                                       "Draw a larger box around the object.", parent=popup)
                return
            seek_t = _seek_var.get()
            popup.destroy()

            # Convert display coords → original video coords
            roi_video = (
                int(x0 * disp_scale_x), int(y0 * disp_scale_y),
                int((x1 - x0) * disp_scale_x), int((y1 - y0) * disp_scale_y),
            )
            self._logger.info(
                f"🎯 Starting CSRT tracker on {clip.name} from {seek_t:.1f}s…")
            threading.Thread(
                target=self._run_tracker,
                args=(clip, roi_video, self._edit_sel_idx, seek_t),
                daemon=True,
            ).start()

        tk.Button(
            btn_row, text="✅  Confirm & Track",
            bg=CLR_ACCENT, fg="white",
            activebackground=CLR_ACCENT_D, activeforeground="white",
            font=("Segoe UI", 9, "bold"), relief=FLAT,
            cursor="hand2", padx=12, pady=6,
            command=_confirm,
        ).pack(side=LEFT, fill=X, expand=True)
        SecondaryButton(btn_row, text="Cancel",
                        command=popup.destroy).pack(side=RIGHT, padx=(8, 0))

    def _run_tracker(self, clip: Path, roi: tuple, item_idx: int,
                     seek_time: float = 0.0):
        """Background thread: CSRT-track roi starting from seek_time, save .track.json."""
        try:
            import cv2 as cv2

            cap = cv2.VideoCapture(str(clip))
            if not cap.isOpened():
                self.after(0, lambda: self._logger.error("Tracker: could not open clip."))
                return

            fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            vw    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            vh    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            # Seek to chosen frame
            start_frame = max(0, int(seek_time * fps))
            if start_frame > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

            ok, frame = cap.read()
            if not ok:
                self.after(0, lambda: self._logger.error("Tracker: could not read frame."))
                return

            # Create CSRT tracker — API changed between OpenCV 4 and 5
            if hasattr(cv2, "TrackerCSRT_create"):
                tracker = cv2.TrackerCSRT_create()
            elif hasattr(cv2, "tracking") and hasattr(cv2.tracking, "TrackerCSRT_create"):
                tracker = cv2.tracking.TrackerCSRT_create()
            elif hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerCSRT_create"):
                tracker = cv2.legacy.TrackerCSRT_create()
            else:
                self.after(0, lambda: self._logger.error(
                    "TrackerCSRT not available — install opencv-contrib-python"))
                cap.release()
                return

            tracker.init(frame, roi)

            frames_data: list[dict] = []
            frame_idx = start_frame  # absolute frame index

            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frame_idx += 1
                success, bbox = tracker.update(frame)
                if success:
                    x, y, w, h = [int(v) for v in bbox]
                    # Clamp to valid frame region
                    x = max(0, min(x, vw - 1)); w = min(w, vw - x)
                    y = max(0, min(y, vh - 1)); h = min(h, vh - y)
                    # Only record this frame if the box is meaningfully inside the frame.
                    # Skipping out-of-frame frames lets CSRT naturally re-acquire
                    # when the object re-enters instead of holding a stale edge position.
                    if w > 4 and h > 4:
                        frames_data.append({"frame": frame_idx, "t": frame_idx / fps,
                                            "x": x, "y": y, "w": w, "h": h})
                # On tracker failure (object fully out of frame) we intentionally
                # skip adding a frame entry so no blur is drawn on those frames.

                if frame_idx % 30 == 0:
                    pct = frame_idx / max(total, 1) * 100
                    self.after(0, lambda p=pct: self._logger.dim(f"   Tracking… {p:.0f}%"))

            cap.release()

            # Save .track.json
            track_p = clip.with_suffix(".track.json")
            import json as _json
            _json.dump({"fps": fps, "width": vw, "height": vh,
                        "seek_time": seek_time,
                        "frames": frames_data},
                       open(track_p, "w"), indent=2)

            def _add_tracked():
                if item_idx < len(self._edit_queue):
                    st    = self._edit_queue[item_idx]["state"]
                    boxes = st.setdefault("blur_boxes", [])
                    boxes.append({
                        "x": roi[0], "y": roi[1], "w": roi[2], "h": roi[3],
                        "tracked": True, "track_file": str(track_p),
                    })
                    n = sum(1 for b in boxes if b.get("tracked"))
                    self._blur_listbox.insert(END, f"🎯 Tracked {n}  (from {seek_time:.1f}s)")
                    self._logger.ok(
                        f"🎯 Tracking complete — {len(frames_data)} frames"
                        f"  (start={seek_time:.1f}s) → {track_p.name}")
                    self._regen_edit_preview()

            self.after(0, _add_tracked)

        except Exception as exc:
            self.after(0, lambda: self._logger.error(f"Tracker failed: {exc}"))


    # ── Bulk export ───────────────────────────────────────────────────────────

    def _start_export_all(self):
        """Export all queued clips sequentially in a background thread."""
        if not self._edit_queue:
            return
        self._btn_export_one.config(state=DISABLED)
        self._btn_export_all.config(state=DISABLED, text="Exporting…")
        self._set_status("Rendering all clips (9:16)…", CLR_WARN)

        # Show progress bar
        self._render_progress_var.set(0.0)
        self._render_progress_lbl.config(text="0%")
        self._render_progress_frame.pack(fill=X, pady=(0, 4), before=self._btn_export_one)

        threading.Thread(target=self._export_all_worker, daemon=True).start()

    def _export_all_worker(self):
        import concurrent.futures
        total = len(self._edit_queue)
        render_cfg = self._get_render_cfg()
        is_gpu = render_cfg.get("vcodec") in {"h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "h264_amf", "hevc_amf"}
        user_threads = self._export_threads_var.get()
        max_workers = max(1, min(3 if is_gpu else 4, user_threads))
        # Shared counters (GIL-safe for simple int reads within after())
        done_count = [0]
        failed_count = [0]
        retry_items = []
        retry_lock = threading.Lock()

        def _export_one(idx_item, is_retry=False):
            i, item = idx_item
            clip  = item["clip_path"]
            title = item["title"]
            state = dict(item["state"])  # copy so concurrent jobs don't stomp each other
            state.update({
                "color_grade": self._opt_color_grade.get(),
                "subtitles":   self._opt_subtitles.get(),
            })
            out_dir = Path(self._output_var.get())
            video_dir = out_dir / "video"
            video_dir.mkdir(parents=True, exist_ok=True)
            dst = video_dir / (clip.stem + "_reup.mp4")

            def _on_progress(frac: float, _i=i):
                pct = max(0.0, min(100.0, frac * 100))
                self.after(0, lambda p=pct: (
                    self._render_progress_var.set(p),
                    self._render_progress_lbl.config(
                        text=f"[{_i+1}/{total}] {p:.0f}%"),
                ))

            try:
                srt = None
                if state["subtitles"]:
                    client, sdk = None, None
                    for k in self._get_all_keys():
                        if k.strip():
                            try:
                                client, sdk = build_client(k.strip())
                                break
                            except Exception:
                                pass
                    _sub_engine = state.get("sub_engine", "gemini_fallback")
                    _sub_style  = state.get("sub_style", "Normal")
                    _word_lvl   = True
                    # Use a fresh Event so a previous "Stop analysis" signal
                    # doesn't immediately abort subtitle transcription.
                    _sub_stop   = threading.Event()
                    if _sub_engine == "whisper":
                        if WHISPER_AVAILABLE:
                            srt = _whisper_transcribe(clip, self._logger, word_level=True, edit_state=state)
                        if srt is None and client and sdk:
                            self._logger.warn("Whisper unavailable or failed — falling back to Gemini")
                            srt = _gemini_transcribe(clip, client, sdk,
                                                     self._logger, _sub_stop,
                                                     word_level=_word_lvl,
                                                     model_name=self._get_model_name(),
                                                     edit_state=state)
                    elif _sub_engine == "gemini":
                        if client and sdk:
                            srt = _gemini_transcribe(clip, client, sdk,
                                                     self._logger, _sub_stop,
                                                     word_level=_word_lvl,
                                                     model_name=self._get_model_name(),
                                                     edit_state=state)
                    else:  # "gemini_fallback"
                        if client and sdk:
                            srt = _gemini_transcribe(clip, client, sdk,
                                                     self._logger, _sub_stop,
                                                     word_level=_word_lvl,
                                                     model_name=self._get_model_name(),
                                                     edit_state=state)
                        if srt is None and WHISPER_AVAILABLE:
                            srt = _whisper_transcribe(clip, self._logger, word_level=True, edit_state=state)

                render_reup(clip, dst, title,
                            state["color_grade"], srt, self._logger,
                            edit_state=state,
                            render_cfg=render_cfg,
                            progress_cb=_on_progress)

                # Organize outputs
                import shutil
                if srt and srt.exists():
                    srt_dir = out_dir / "srt"
                    srt_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy(srt, srt_dir / (clip.stem + "_reup.srt"))
                        srt.unlink(missing_ok=True)
                    except Exception as e:
                        self._logger.warn(f"Could not copy SRT: {e}")

                words_json = clip.with_suffix(".words.json")
                if words_json.exists():
                    json_dir = out_dir / "json"
                    json_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy(words_json, json_dir / (clip.stem + "_reup.json"))
                        words_json.unlink(missing_ok=True)
                    except Exception as e:
                        self._logger.warn(f"Could not copy JSON: {e}")

                done_count[0] += 1
                self._logger.ok(f"[{i+1}/{total}] {dst.name}")

            except Exception as exc:
                is_mem_err = any(err_sig in str(exc).lower() for err_sig in [
                    "cannot allocate memory", "-12", "4294967284", "out of memory",
                    "resource temporarily unavailable", "conversion failed", "oom"
                ])
                if not is_retry and is_mem_err:
                    self._logger.warn(f"[{i+1}/{total}] Quá tải bộ nhớ VRAM: xếp vào hàng đợi tự động thử lại...")
                    with retry_lock:
                        retry_items.append(idx_item)
                    return

                failed_count[0] += 1
                self._logger.error(f"[{i+1}/{total}] Failed: {exc}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            pool.map(_export_one, enumerate(self._edit_queue))

        if retry_items:
            self._logger.info(f"🔄 Đang tự động thử lại (Auto-Retry) {len(retry_items)} video ở chế độ giải phóng VRAM...")
            import time
            time.sleep(1.2)
            for r_item in retry_items:
                _export_one(r_item, is_retry=True)

        self.after(0, lambda: (
            self._btn_export_one.config(state=NORMAL),
            self._btn_export_all.config(state=NORMAL, text="📦  Export All"),
            self._render_progress_frame.pack_forget(),
            self._set_status(
                f"Export complete — {done_count[0]} ok, {failed_count[0]} failed",
                CLR_SUCCESS if not failed_count[0] else CLR_WARN),
        ))


    # ── Dynamic key rows ───────────────────────────────────────────────────

    def _add_key_row(self, value: str = ""):
        container = self._keys_container
        num = len(self._key_rows) + 1

        row_frame = ttk.Frame(container, style="Panel.TFrame")
        row_frame.pack(fill=X, pady=2)

        num_lbl = ttk.Label(row_frame, text=f"#{num}", style="Panel.TLabel",
                            width=3, anchor=E)
        num_lbl.pack(side=LEFT, padx=(0, 4))

        var = tk.StringVar(value=value)
        entry = ttk.Entry(row_frame, textvariable=var, show="●", width=26)
        entry.pack(side=LEFT, fill=X, expand=True)

        row_dict = {
            "frame":   row_frame,
            "var":     var,
            "entry":   entry,
            "label":   num_lbl,
            "visible": False,
        }

        vis_btn = tk.Button(
            row_frame, text="👁", bg=CLR_PANEL, fg=CLR_DIM,
            font=("Segoe UI", 9), relief=FLAT, width=2,
            command=lambda rd=row_dict: self._toggle_key_vis(rd),
        )
        vis_btn.pack(side=LEFT, padx=(3, 0))
        row_dict["vis_btn"] = vis_btn

        del_btn = tk.Button(
            row_frame, text="✕", bg=CLR_PANEL, fg=CLR_ERROR,
            font=("Segoe UI", 9), relief=FLAT, width=2,
            command=lambda rd=row_dict: self._remove_key_row(rd),
        )
        del_btn.pack(side=LEFT, padx=(2, 0))

        self._key_rows.append(row_dict)

        # When called by the user (value=""), scroll the left panel to reveal
        # the new row and focus the entry so they can type immediately.
        # Skip this for config-restore calls (value is a non-empty saved key).
        if not value:
            def _scroll_and_focus():
                self.update_idletasks()
                if hasattr(self, "_left_canvas"):
                    self._left_canvas.yview_moveto(1.0)
                entry.focus_set()
            self.after(30, _scroll_and_focus)

        return row_dict

    def _remove_key_row(self, rd: dict):
        if len(self._key_rows) <= 1:
            messagebox.showinfo("Info", "At least one API key row is required.")
            return
        rd["frame"].destroy()
        self._key_rows.remove(rd)
        self._renumber_key_rows()

    def _toggle_key_vis(self, rd: dict):
        rd["visible"] = not rd["visible"]
        rd["entry"].config(show="" if rd["visible"] else "●")
        rd["vis_btn"].config(fg=CLR_FG if rd["visible"] else CLR_DIM)

    def _renumber_key_rows(self):
        for i, rd in enumerate(self._key_rows):
            rd["label"].config(text=f"#{i+1}")

    def _get_all_keys(self) -> list[str]:
        return [rd["var"].get().strip() for rd in self._key_rows
                if rd["var"].get().strip()]

    # ── File helpers ────────────────────────────────────────────────────────

    def _pick_video_files(self):
        files = filedialog.askopenfilenames(
            title="Select Bodycam Video Files",
            filetypes=[("Video files", "*.mp4 *.mkv *.MP4 *.MKV"),
                       ("All files", "*.*")],
        )
        if files:
            self._video_files = [Path(f) for f in files]
            self._refresh_file_listbox()

    def _clear_video_files(self):
        self._video_files = []
        self._file_listbox.delete(0, END)
        self._file_count_lbl.config(text="No files selected.")

    def _remove_selected_files(self):
        """Remove the currently selected files from the list (Delete hotkey)."""
        selected = list(self._file_listbox.curselection())
        if not selected:
            return
        # Remove in reverse order so indices don't shift
        for idx in reversed(selected):
            self._file_listbox.delete(idx)
            del self._video_files[idx]
        n = len(self._video_files)
        self._file_count_lbl.config(
            text=f"{n} file{'s' if n != 1 else ''} selected." if n else "No files selected."
        )

    def _refresh_file_listbox(self):
        self._file_listbox.delete(0, END)
        for p in self._video_files:
            self._file_listbox.insert(END, p.name)
        n = len(self._video_files)
        self._file_count_lbl.config(text=f"{n} file{'s' if n != 1 else ''} selected.")

    def _pick_folder(self, var: tk.StringVar):
        folder = filedialog.askdirectory()
        if folder:
            var.set(folder)

    # ── Queue Treeview ──────────────────────────────────────────────────────

    def _queue_init(self, videos: list[Path]):
        """Populate queue with all selected videos at status=queued."""
        for item in self._queue.get_children():
            self._queue.delete(item)
        for vid in videos:
            self._queue.insert("", END, iid=str(vid),
                               values=("🕐", vid.name, "Queued"),
                               tags=(ST_QUEUED,))

    def _queue_update(self, path: Path, status: str, info: str = ""):
        """Update a row in the queue. Called via self.after() from threads."""
        iid = str(path)
        if not self._queue.exists(iid):
            return
        icons = {
            ST_QUEUED:    "🕐",
            ST_UPLOADING: "⬆️",
            ST_ANALYZING: "🔍",
            ST_DONE:      "✅",
            ST_ERROR:     "❌",
        }
        icon = icons.get(status, "")
        self._queue.item(iid, values=(icon, path.name, info), tags=(status,))

    def _on_queue_select(self, _event=None):
        sel = self._queue.selection()
        if not sel:
            return
        path = Path(sel[0])
        res  = self._video_results.get(str(path), {})
        if res.get("status") == ST_DONE:
            self._selected_video = path
            self._show_results(path, res.get("candidates", []))
        else:
            # Not done yet — clear results panel
            self._clear_results_panel(path.name, res.get("status", ""))

    def _update_video_status(self, path: Path, status: str,
                             candidates: Optional[list] = None,
                             error: str = ""):
        """Thread-safe: update _video_results and refresh queue row + progress."""
        def _on_main():
            self._video_results[str(path)] = {
                "status": status,
                "candidates": candidates or [],
                "error": error,
            }
            err_str = str(error)
            if "errno 2" in err_str.lower() or "no such file" in err_str.lower():
                err_lbl = "File not found"
            else:
                err_lbl = f"Error: {err_str[:40]}"
            label_map = {
                ST_QUEUED:    "Queued",
                ST_UPLOADING: "Uploading…",
                ST_ANALYZING: "Analyzing…",
                ST_DONE:      f"{len(candidates or [])} clips found",
                ST_ERROR:     err_lbl,
            }
            self._queue_update(path, status, label_map.get(status, status))
            self._refresh_progress()

        self.after(0, _on_main)

    def _refresh_progress(self):
        total  = len(self._video_files)
        done   = sum(1 for r in self._video_results.values()
                     if r["status"] in (ST_DONE, ST_ERROR))
        errors = sum(1 for r in self._video_results.values()
                     if r["status"] == ST_ERROR)
        pct    = (done / total * 100) if total else 0
        self._prog_var.set(pct)
        self._prog_lbl.config(
            text=f"{done}/{total} analyzed"
                 + (f"  •  {errors} error(s)" if errors else ""))
        if done == total and total > 0:
            self.after(0, self._all_done)

    def _all_done(self):
        success = sum(1 for r in self._video_results.values()
                      if r["status"] == ST_DONE)
        errors  = sum(1 for r in self._video_results.values()
                      if r["status"] == ST_ERROR)
        self._set_status(f"Done — {success}/{len(self._video_files)} succeeded",
                         CLR_SUCCESS)
        self._btn_analyze.config(state=NORMAL, text="▶  ANALYZE ALL",
                                 bg=CLR_ACCENT)
        self._btn_stop.config(state=DISABLED)
        # Enable retry only when there are failed videos
        self._btn_retry.config(state=NORMAL if errors > 0 else DISABLED)
        self._logger.ok(
            f"All videos analyzed! "
            + (f" {errors} failed — click 🔄 RETRY ERRORS to re-run them." if errors else "")
        )

    # ── Results panel ───────────────────────────────────────────────────────

    def _clear_results_panel(self, name: str = "", status: str = ""):
        self._player.stop()
        self._results_video_lbl.config(
            text=f"{name} — {ST_LABEL.get(status, 'not done yet')}")
        self._cand_box["values"] = []
        self._cand_var.set("—")
        self._reason_txt.configure(state=NORMAL)
        self._reason_txt.delete("1.0", END)
        self._reason_txt.configure(state=DISABLED)
        for btn in self._title_btns:
            btn.config(text="—", command=lambda: None)
        self._btn_cut.config(state=DISABLED)
        self._btn_play.config(state=DISABLED, text="▶  Play Preview", bg="#1e40af")
        self._draw_preview_placeholder()

    def _show_results(self, path: Path, candidates: list[dict]):
        self._results_video_lbl.config(text=path.name, foreground=CLR_FG)
        labels = [
            f"#{c.get('id', i+1)}  —  {c.get('start_time')} → {c.get('end_time')}"
            for i, c in enumerate(candidates)
        ]
        self._cand_box["values"] = labels
        if labels:
            self._cand_box.current(0)
            self._refresh_candidate_ui(path, candidates, 0)
        self._btn_cut.config(state=NORMAL if candidates else DISABLED)

    def _on_candidate_selected(self, _event=None):
        if not self._selected_video:
            return
        res = self._video_results.get(str(self._selected_video), {})
        candidates = res.get("candidates", [])
        idx = self._cand_box.current()
        if 0 <= idx < len(candidates):
            self._refresh_candidate_ui(self._selected_video, candidates, idx)

    def _refresh_candidate_ui(self, path: Path, candidates: list, idx: int):
        c = candidates[idx]
        # Reason
        self._reason_txt.configure(state=NORMAL)
        self._reason_txt.delete("1.0", END)
        self._reason_txt.insert(END, c.get("reason", ""))
        self._reason_txt.configure(state=DISABLED)
        # Titles
        titles = c.get("suggested_titles", [])
        for i, btn in enumerate(self._title_btns):
            title = titles[i] if i < len(titles) else ""
            btn.config(
                text=f"{i+1}. {title}" if title else f"{i+1}. —",
                command=(lambda t=title: self._copy_title(t)) if title else lambda: None,
            )
        # Reset reup title selection when candidate changes
        self._selected_title_for_reup = titles[0] if titles else ""
        if hasattr(self, "_reup_title_lbl"):
            hint = "Click a title above to select it for reup" if self._last_cut_path \
                   else "— cut a clip first —"
            self._reup_title_lbl.config(text=hint, foreground=CLR_DIM)
        # Preview
        start_ts = c.get("start_time", "00:00:00")
        self._trigger_preview(path, start_ts)

    def _copy_title(self, text: str):
        copy_to_clipboard(self, text)
        # Remember this title for the reup renderer
        self._selected_title_for_reup = text
        if hasattr(self, "_reup_title_lbl") and self._last_cut_path:
            short = text[:80] + "…" if len(text) > 80 else text
            self._reup_title_lbl.config(text=f"✓ {short}", foreground=CLR_FG)
        orig = self._status_lbl.cget("text")
        self._set_status("Copied!", CLR_ACCENT)
        self.after(1500, lambda: self._status_lbl.config(text=orig))

    # ── Preview player ───────────────────────────────────────────────────────

    def _draw_preview_placeholder(self):
        self._preview_canvas.delete("all")
        self._preview_canvas.create_rectangle(
            0, 0, PREVIEW_W, PREVIEW_H, fill="#0d0d1a", outline="")
        self._preview_canvas.create_text(
            PREVIEW_W // 2, PREVIEW_H // 2,
            text="📽  Select a completed video",
            fill=CLR_DIM, font=("Segoe UI", 10),
        )

    # Store pending video/timestamp for play button
    _pending_video:  Optional[Path] = None
    _pending_start:  float          = 0.0
    _preview_gen:    int            = 0   # incremented per request; stale threads bail early
    # Track running preview FFmpeg proc so we can kill it on next click
    _preview_proc:   Optional[subprocess.Popen] = None
    _preview_proc_lock: threading.Lock = None   # initialised in __init__

    def _trigger_preview(self, video: Path, timestamp: str):
        """Stop current playback, store target segment, show first frame."""
        self._player.stop()
        self._pending_video = video
        self._pending_start = ts_to_seconds(timestamp)
        self._btn_play.config(
            state=NORMAL,
            text="▶  Play Preview",
            bg="#1e40af",
        )
        self._prev_lbl.config(
            text=f"{timestamp}  (+{CLIP_DURATION}s)",
            foreground=CLR_FG,
        )

        # Kill any in-flight preview FFmpeg process immediately so rapid
        # video-switching never piles up concurrent FFmpeg extract processes.
        with self._preview_proc_lock:
            old_proc, self._preview_proc = self._preview_proc, None
        if old_proc and old_proc.poll() is None:
            try:
                old_proc.kill()
            except Exception:
                pass

        # Show first frame as thumbnail while stopped
        if not PIL_AVAILABLE:
            return
        self._preview_canvas.delete("all")
        self._preview_canvas.create_text(
            PREVIEW_W // 2, PREVIEW_H // 2,
            text="⏳  Loading first frame…", fill=CLR_DIM, font=("Segoe UI", 10))

        # Bump generation so any previously-queued _grab_first_frame exits early
        self._preview_gen += 1
        my_gen = self._preview_gen
        # Capture now — self._pending_start may change on the next click
        start_sec = self._pending_start

        def _grab_first_frame():
            """Extract first frame as JPEG; proc is tracked so it can be killed."""
            if my_gen != self._preview_gen:
                return

            fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            stderr_data = b""
            proc = None
            try:
                cmd = [
                    FFMPEG, "-y", "-loglevel", "error",
                    "-ss", str(start_sec),        # local capture, not self._pending_start
                    "-i",  str(video),
                    "-frames:v", "1", "-q:v", "3",
                    "-vf", (
                        f"scale={PREVIEW_W}:{PREVIEW_H}:"
                        "force_original_aspect_ratio=decrease,"
                        f"pad={PREVIEW_W}:{PREVIEW_H}:"
                        "(ow-iw)/2:(oh-ih)/2:color=black,"
                        "format=yuvj420p"   # full-range YUV required by JPEG
                    ),
                    tmp_path,
                ]
                # Popen (not run) so _trigger_preview can kill this proc on next click
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL,
                )
                with self._preview_proc_lock:
                    self._preview_proc = proc

                try:
                    _, stderr_data = proc.communicate(timeout=60)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    _, stderr_data = proc.communicate()
                    if my_gen == self._preview_gen:
                        def _show_timeout(g=my_gen):
                            if g != self._preview_gen:
                                return
                            self._preview_canvas.delete("all")
                            self._preview_canvas.create_text(
                                PREVIEW_W // 2, PREVIEW_H // 2,
                                text="⚠️  Frame extraction timed out",
                                fill=CLR_WARN, font=("Segoe UI", 10),
                            )
                        self._preview_canvas.after(0, _show_timeout)
                    return
                finally:
                    with self._preview_proc_lock:
                        if self._preview_proc is proc:
                            self._preview_proc = None

                if my_gen != self._preview_gen:
                    return

                if (proc.returncode == 0
                        and os.path.exists(tmp_path)
                        and os.path.getsize(tmp_path) > 0):
                    img = Image.open(tmp_path).convert("RGB")
                    def _show(i=img, g=my_gen):
                        if g != self._preview_gen:
                            return
                        photo = ImageTk.PhotoImage(i)   # ← main thread ✓
                        self._player._photo_ref = photo
                        self._preview_canvas.delete("all")
                        self._preview_canvas.create_image(
                            PREVIEW_W // 2, PREVIEW_H // 2,
                            image=photo, anchor="center",
                        )
                    self._preview_canvas.after(0, _show)
                else:
                    err_raw = (stderr_data or b"").decode("utf-8", errors="replace").strip()
                    hint = err_raw.split("\n")[0][:90] if err_raw else "Seek beyond video end?"
                    def _show_err(h=hint, g=my_gen):
                        if g != self._preview_gen:
                            return
                        self._preview_canvas.delete("all")
                        self._preview_canvas.create_text(
                            PREVIEW_W // 2, PREVIEW_H // 2 - 12,
                            text="⚠️  Preview unavailable",
                            fill=CLR_WARN, font=("Segoe UI", 10, "bold"),
                        )
                        self._preview_canvas.create_text(
                            PREVIEW_W // 2, PREVIEW_H // 2 + 14,
                            text=h, fill=CLR_DIM, font=("Segoe UI", 8),
                            width=PREVIEW_W - 24,
                        )
                    self._preview_canvas.after(0, _show_err)

            except Exception:
                if my_gen == self._preview_gen:
                    self._preview_canvas.after(0, self._draw_preview_placeholder)
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        threading.Thread(target=_grab_first_frame, daemon=True).start()



    def _toggle_preview_playback(self):
        if self._player.is_playing:
            self._player.stop()
        else:
            if self._pending_video:
                self._player.play(
                    self._pending_video,
                    self._pending_start,
                    CLIP_DURATION,
                )

    def _on_player_state_change(self, playing: bool):
        """Called on main thread when player starts / stops."""
        if playing:
            self._btn_play.config(text="⏹  Stop Preview", bg="#7c3aed")
        else:
            self._btn_play.config(text="▶  Play Preview", bg="#1e40af")

    # ── Status / progress ────────────────────────────────────────

    def _set_status(self, text: str, color: str = CLR_SUCCESS):
        self._status_lbl.config(text=f"● {text}", foreground=color)

    def _check_deps(self):
        if not check_ffmpeg():
            messagebox.showwarning(
                "FFmpeg Missing",
                "FFmpeg not found on PATH.\n\n"
                "Install:  winget install --id Gyan.FFmpeg -e\n\nThen restart.",
            )
            self._logger.warn("FFmpeg not found — install before cutting clips.")
        else:
            self._logger.ok("FFmpeg detected on PATH.")
        if not PIL_AVAILABLE:
            self._logger.warn("Pillow missing — preview disabled.  pip install Pillow")
        self._logger.info(f"Model: {MODEL_NAME}  |  Clip: exactly {CLIP_DURATION}s")
        self._logger.info("Add API keys, select videos, then click ANALYZE ALL.")

    def _save_config(self):
        keys = self._get_all_keys()
        save_config({
            "api_keys":      keys,
            "api_key":       keys[0] if keys else "",
            "output_folder": self._output_var.get(),
            "video_files":   [str(p) for p in self._video_files],
            "render_cfg":    self._get_render_cfg(),
            "model_name":    self._get_model_name(),
            "include_cta":   self._cta_var.get() if hasattr(self, "_cta_var") else False,
        })

    def _get_model_name(self) -> str:
        """Return the currently selected model ID from the UI combobox."""
        if not hasattr(self, "_model_var"):
            return MODEL_NAME
        lbl = self._model_var.get()
        return getattr(self, "_model_label_to_id", {}).get(lbl, MODEL_NAME)

    def _get_render_cfg(self) -> dict:
        """Read Export Settings widgets → return a render_cfg dict for render_reup."""
        if not hasattr(self, "_export_res_var"):
            return {}   # UI not yet built
        _res_map = {
            "1080×1920 (Full HD)": (1080, 1920),
            "720×1280 (HD)":        (720,  1280),
            "540×960 (SD)":         (540,   960),
        }
        w, h = _res_map.get(self._export_res_var.get(), (1080, 1920))
        enc_lbl = self._export_enc_var.get()
        vcodec  = getattr(self, "_enc_to_id", {}).get(enc_lbl, "libx264")
        fps_str = self._export_fps_var.get()
        fps     = None if fps_str == "Original" else int(fps_str)
        return {
            "width":  w,
            "height": h,
            "vcodec": vcodec,
            "acodec": "aac",
            "crf":    self._export_crf_var.get(),
            "preset": self._export_preset_var.get(),
            "fps":    fps,
        }

    # ── Analyze ────────────────────────────────────────────

    def _start_analyze(self):
        keys   = self._get_all_keys()
        videos = self._video_files

        if not keys:
            messagebox.showerror("Missing", "Please enter at least one API key.")
            return
        if not videos:
            messagebox.showerror("Missing", "Please select video files first.")
            return
        missing = [v for v in videos if not v.exists()]
        if len(missing) == len(videos):
            messagebox.showerror(
                "Files Not Found",
                "None of the selected video files exist on disk!\n\n"
                "Please check if the video files were moved, deleted, or if the drive is disconnected.\n"
                "Reselect your video files in 'Input Videos'."
            )
            return
        if not self._output_var.get().strip():
            messagebox.showerror("Missing", "Please select an Output Folder.")
            return

        self._save_config()
        self._stop.clear()
        self._video_results = {}
        self._selected_video = None
        self._clear_results_panel()
        self._prog_var.set(0)
        self._prog_lbl.config(text="")
        self._draw_preview_placeholder()

        self._queue_init(videos)

        n = len(videos)
        max_concurrent = min(3, n)
        sem = threading.Semaphore(max_concurrent)

        self._btn_analyze.config(state=DISABLED, text="ANALYZING…", bg="#4f4f4f")
        self._btn_stop.config(state=NORMAL)
        self._btn_retry.config(state=DISABLED)
        self._btn_cut.config(state=DISABLED)
        self._set_status(
            f"Analyzing {n} video(s)  —  up to {max_concurrent} at a time…",
            CLR_WARN,
        )
        self._logger.header("=" * 50)
        self._logger.header(
            f"  Bulk analysis: {n} video(s), {len(keys)} key(s), "
            f"max {max_concurrent} concurrent"
        )
        self._logger.header("=" * 50)

        self._active_threads = []
        rotator = KeyRotator(keys)   # shared across all worker threads
        for video_path in videos:
            t = threading.Thread(
                target=self._analyze_one_video,
                args=(video_path, rotator, sem),
                daemon=True,
            )
            self._active_threads.append(t)
            t.start()
        self._toast(f"Analyzing {n} video(s)…", kind="info")

    def _analyze_one_video(self, video_path: Path,
                           rotator: "KeyRotator",
                           sem: threading.Semaphore):
        """Worker thread — runs concurrently, bounded by sem."""
        log = self._logger

        # Wait for a slot (max 3 running at once)
        sem.acquire()
        try:
            self._run_analysis(video_path, rotator, log)
        finally:
            sem.release()

    def _run_analysis(self, video_path: Path, rotator: "KeyRotator",
                      log: ToolLogger):

        if not video_path.exists():
            log.error(f"[{video_path.name}] File not found on disk: {video_path}")
            self._update_video_status(video_path, ST_ERROR, error="File not found")
            return

        self._update_video_status(video_path, ST_UPLOADING)
        result       = None
        last_exc     = None
        vid_dur_hint: Optional[float] = None   # set once, reused on key retries

        # Budget: try every key at most once before giving up.
        n_keys = len(rotator)

        # ── Encode proxy/timelapse ONCE before retry loop ──────────────────
        # Moving this outside the loop prevents re-encoding on every key rotation.
        vid_dur_hint = get_video_duration(video_path)
        if vid_dur_hint is not None:
            log.dim(
                f"[{video_path.name}] Duration: "
                f"{int(vid_dur_hint//60):02d}m{int(vid_dur_hint%60):02d}s"
            )
        ds_path, ds_cleanup, ds_speedup = _downsample_for_upload(video_path, log)

        try:
          for attempt in range(n_keys):
            if self._stop.is_set():
                self._update_video_status(video_path, ST_ERROR, error="Stopped")
                return

            key    = rotator.acquire()   # Least Connections: fewest-active, non-cooled key
            remote = None
            client = None
            sdk    = None

            try:
                client, sdk = build_client(key)

                self._update_video_status(video_path, ST_UPLOADING)
                remote = upload_video(client, sdk, ds_path, log, self._stop)

                self._update_video_status(video_path, ST_ANALYZING)
                # Pass the scaled duration so analyze_video gives Gemini accurate
                # timestamp bounds for the sped-up video it actually sees.
                scaled_dur = (vid_dur_hint / ds_speedup) if vid_dur_hint else None
                result = analyze_video(client, sdk, remote,
                                       video_path.name, log, self._stop,
                                       vid_duration=scaled_dur,
                                       model_name=self._get_model_name(),
                                       include_cta=self._cta_var.get() if hasattr(self, "_cta_var") else False)

                # Convert timestamps from sped-up timeline back to original.
                if ds_speedup != 1.0 and result and result.get("candidates"):
                    for cand in result["candidates"]:
                        raw_ts = ts_to_seconds(cand.get("start_time", "00:00:00"))
                        orig_s = raw_ts * ds_speedup
                        h = int(orig_s // 3600)
                        m = int((orig_s % 3600) // 60)
                        s = int(orig_s % 60)
                        cand["start_time"] = f"{h:02d}:{m:02d}:{s:02d}"
                    log.dim(
                        f"[{video_path.name}] Timestamps scaled back "
                        f"{ds_speedup:.2f}x to original timeline."
                    )

                # Correction loop: reuse the live remote file to retry when
                # all timestamps are invalid. Avoids re-upload cost.
                # Before each correction call, try MM:SS re-interpretation first
                # (Gemini sometimes writes 02:30:00 meaning 2min30sec for short videos).
                MAX_CORRECTIONS = 3
                for corr_attempt in range(MAX_CORRECTIONS):
                    raw_candidates = result.get("candidates", [])
                    # Clamp max_t to ≥0 so range never inverts for short clips.
                    # Lower bound is 0.0: 00:00:00 is valid for clips shorter than
                    # CLIP_DURATION (the whole clip IS the highlight).
                    max_t = max(0.0, (vid_dur_hint or float("inf")) - CLIP_DURATION)

                    invalid_cands = [
                        c for c in raw_candidates
                        if not (0.0 <= ts_to_seconds(c.get("start_time", "99:00:00")) <= max_t)
                    ]

                    if len(invalid_cands) < len(raw_candidates):
                        break   # at least some candidates are already valid

                    # All invalid — try MM:SS re-interpretation before burning an API call
                    if vid_dur_hint is not None:
                        rescued = _reinterpret_mmss(raw_candidates, vid_dur_hint)
                        if rescued:
                            log.dim(
                                f"[{video_path.name}] Re-interpreted "
                                f"{len(rescued)} timestamp(s) as MM:SS format."
                            )
                            break   # rescued candidates are now valid

                    if self._stop.is_set():
                        raise InterruptedError("Stopped by user.")

                    rejected = [c.get("start_time", "??") for c in invalid_cands]
                    log.warn(
                        f"[{video_path.name}] Correction {corr_attempt + 1}/{MAX_CORRECTIONS}: "
                        f"timestamps {rejected} invalid — re-analyzing with feedback…"
                    )
                    self._update_video_status(video_path, ST_ANALYZING)
                    result = analyze_video(
                        client, sdk, remote,
                        video_path.name, log, self._stop,
                        vid_duration=vid_dur_hint,
                        rejected_timestamps=rejected,
                        include_cta=self._cta_var.get() if hasattr(self, "_cta_var") else False,
                    )

            except InterruptedError:
                self._update_video_status(video_path, ST_ERROR, error="Stopped")
                return

            except Exception as exc:
                last_exc  = exc
                exc_str   = str(exc)
                exc_lower = exc_str.lower()
                is_quota  = any(kw in exc_lower for kw in (
                    "quota", "429", "rate limit",
                    "resource_exhausted", "too many requests",
                ))
                is_tcp = "10053" in exc_str or "10054" in exc_str

                # Apply cooldown so acquire() steers away from the failing key.
                if is_quota:
                    rotator.penalize(key, KeyRotator.COOLDOWN_RATE_LIMIT)
                    label = f"quota ({KeyRotator.COOLDOWN_RATE_LIMIT:.0f}s cooldown)"
                elif is_tcp:
                    rotator.penalize(key, KeyRotator.COOLDOWN_TCP)
                    label = f"TCP error ({KeyRotator.COOLDOWN_TCP:.0f}s cooldown)"
                else:
                    rotator.penalize(key, KeyRotator.COOLDOWN_GENERIC)
                    label = "error"

                if attempt < n_keys - 1:
                    log.warn(
                        f"[{video_path.name}] Attempt {attempt+1}/{n_keys} failed [{label}]: "
                        f"{exc_str[:60]} — trying next key…"
                    )
                    time.sleep(0.5)   # brief pause; cooldown handles which key is next
                else:
                    log.error(f"[{video_path.name}] {exc}")
                    self._update_video_status(
                        video_path, ST_ERROR, error=str(exc)[:80])
                    return

            else:
                break   # try succeeded — exit key-retry loop

            finally:
                rotator.release(key)   # always decrement active counter
                if remote is not None and client is not None and sdk is not None:
                    try:
                        delete_remote(client, sdk, remote, log)
                    except Exception:
                        pass

        finally:
            # Clean up proxy/timelapse temp file after all retries finish.
            if ds_cleanup:
                try:
                    ds_path.unlink(missing_ok=True)
                except Exception:
                    pass


        if result:
            candidates = result.get("candidates", [])

            # Validate timestamps against actual video duration.
            # Gemini can hallucinate timestamps beyond the video's end,
            # or pick the intro (00:00:00) which is never a dramatic moment.
            vid_dur = get_video_duration(video_path)
            if vid_dur is not None and candidates:
                # For clips shorter than CLIP_DURATION, 00:00:00 is the only possible
                # (and entirely valid) start — accept anything in [0, vid_dur).
                _max_valid = max(0.0, vid_dur - CLIP_DURATION)

                def _is_valid(c: dict) -> bool:
                    t = ts_to_seconds(c.get("start_time", "99:00:00"))
                    return 0.0 <= t <= _max_valid

                valid = [c for c in candidates if _is_valid(c)]

                # Rescue candidates where Gemini used MM:SS format instead of HH:MM:SS
                if len(valid) < len(candidates):
                    mmss_rescued = _reinterpret_mmss(
                        [c for c in candidates if not _is_valid(c)], vid_dur
                    )
                    if mmss_rescued:
                        log.dim(
                            f"[{video_path.name}] Re-interpreted "
                            f"{len(mmss_rescued)} timestamp(s) from MM:SS to HH:MM:SS."
                        )
                    valid = valid + mmss_rescued

                # Last-resort for very short clips: if still empty, accept 00:00:00
                # unconditionally (Gemini correctly identified start-of-clip as highlight).
                if not valid and vid_dur <= CLIP_DURATION + 2:
                    log.dim(
                        f"[{video_path.name}] Short clip ({vid_dur:.0f}s ≤ clip length) — "
                        "accepting 00:00:00 as valid start."
                    )
                    valid = candidates  # all returned candidates accepted as-is

                invalid = len(candidates) - len(valid)
                if invalid > 0:
                    dur_h = int(vid_dur // 3600)
                    dur_m = int((vid_dur % 3600) // 60)
                    dur_s = int(vid_dur % 60)
                    log.warn(
                        f"[{video_path.name}] {invalid} candidate(s) had invalid "
                        f"timestamps (video length: "
                        f"{dur_h:02d}:{dur_m:02d}:{dur_s:02d}) — filtered out"
                    )
                candidates = valid


            if not candidates:
                log.error(
                    f"[{video_path.name}] All Gemini timestamps still invalid after "
                    "correction attempts. Re-run analysis to try again."
                )
                self._update_video_status(
                    video_path, ST_ERROR,
                    error="All timestamps invalid -- retry analysis"
                )
                return

            log.ok(f"[{video_path.name}] {len(candidates)} valid candidate(s) ready.")
            self._update_video_status(video_path, ST_DONE, candidates=candidates)

        elif last_exc:
            self._update_video_status(
                video_path, ST_ERROR, error=str(last_exc)[:80])

    # ── Cut ─────────────────────────────────────────────────────────────────

    def _start_cut(self):
        if not self._selected_video:
            messagebox.showwarning("No Video", "Select a completed video in the queue first.")
            return
        res = self._video_results.get(str(self._selected_video), {})
        candidates = res.get("candidates", [])
        idx = self._cand_box.current()
        if idx < 0 or idx >= len(candidates):
            messagebox.showwarning("No Candidate", "Please select a candidate first.")
            return

        chosen    = candidates[idx]
        start_ts  = chosen.get("start_time", "00:00:00")
        start_sec = ts_to_seconds(start_ts)

        # Guard: validate that start timestamp is within the actual video duration.
        # Gemini occasionally hallucinates timestamps beyond the video length.
        vid_duration = get_video_duration(self._selected_video)
        if vid_duration is not None and start_sec >= vid_duration:
            dur_h = int(vid_duration // 3600)
            dur_m = int((vid_duration % 3600) // 60)
            dur_s = int(vid_duration % 60)
            messagebox.showerror(
                "Invalid Timestamp",
                f"Candidate timestamp {start_ts} is BEYOND the video duration.\n"
                f"Video length : {dur_h:02d}:{dur_m:02d}:{dur_s:02d}\n"
                f"Requested    : {start_ts}\n\n"
                "Gemini returned an incorrect timestamp for this candidate.\n"
                "Please choose a different candidate or re-run the analysis."
            )
            self._set_status(f"Timestamp {start_ts} beyond video end — skipped", CLR_ERROR)
            return

        out_dir  = Path(self._output_var.get())
        stem     = sanitize(self._selected_video.stem)
        out_name = (
            f"{stem}_clip{chosen.get('id', idx+1)}"
            f"_{start_ts.replace(':', '-')}.mp4"
        )
        dst = out_dir / out_name

        self._btn_cut.config(state=DISABLED, text="Cutting…")
        self._set_status("Cutting exact 16s clip…", CLR_WARN)

        threading.Thread(
            target=self._cut_worker,
            args=(self._selected_video, start_ts, dst),
            daemon=True,
        ).start()


    def _cut_worker(self, src: Path, start_ts: str, dst: Path):
        try:
            cut_clip_exact(src, start_ts, dst, self._logger)
            self.after(0, lambda: self._on_cut_done(dst))
        except Exception as exc:
            # Surface a concise reason — take the last non-empty line from the error
            lines = [l.strip() for l in str(exc).splitlines() if l.strip()]
            short = lines[-1][:160] if lines else str(exc)[:160]
            self._logger.error(f"Cut failed: {short}")
            self.after(0, lambda: self._btn_cut.config(
                state=NORMAL, text="✂  CUT SELECTED CLIP  (exact 16s)"))
            self.after(0, lambda: self._set_status("Cut failed", CLR_ERROR))


    def _on_cut_done(self, dst: Path):
        self._btn_cut.config(state=NORMAL, text="✂  CUT SELECTED CLIP  (exact 16s)")
        self._set_status(f"Saved: {dst.name}", CLR_SUCCESS)
        self._logger.ok(f"Clip → {dst}")

        self._last_cut_path = dst
        # Enable the "Send to Edit Tab" button so the user can send the clip to Tab 2
        self._btn_send_edit.config(state=NORMAL)
        short = (self._selected_title_for_reup[:70] + "…"
                 if len(self._selected_title_for_reup) > 70
                 else self._selected_title_for_reup)
        self._reup_title_lbl.config(
            text=(f"✓ {short}" if short else "Click a title above, then -> Send to Edit Tab"),
            fg=CLR_FG if short else CLR_DIM,
        )

        self._toast(f"Clip saved: {dst.name}", kind="success")

        if messagebox.askyesno("Clip Ready!", f"Saved:\n{dst}\n\nOpen output folder?"):
            os.startfile(str(dst.parent))

    # ── Reup Render (Tab 2) ──────────────────────────────────────────────────

    def _start_reup(self):
        """Export the currently selected Tab-2 queue item."""
        if self._edit_sel_idx < 0 or self._edit_sel_idx >= len(self._edit_queue):
            messagebox.showwarning("No Selection",
                "Select a clip in the Edit & Export queue first.")
            return

        item  = self._edit_queue[self._edit_sel_idx]
        clip  = item["clip_path"]
        title = item["title"]

        # Sync GUI controls → state dictionary
        item["state"].update(self._read_edit_controls())
        state = item["state"]

        if not clip.exists():
            messagebox.showerror("File Missing", f"Clip not found:\n{clip}")
            return

        out_dir = Path(self._output_var.get())
        video_dir = out_dir / "video"
        video_dir.mkdir(parents=True, exist_ok=True)
        dst = video_dir / (clip.stem + "_reup.mp4")
        # Gemini transcription is always available; WHISPER is optional fallback.
        use_sub = bool(state["subtitles"])

        self._btn_export_one.config(state=DISABLED, text="Rendering…")
        self._btn_export_all.config(state=DISABLED)
        self._set_status("Rendering reup (9:16)…", CLR_WARN)

        # Show progress bar
        self._render_progress_var.set(0.0)
        self._render_progress_lbl.config(text="0%")
        self._render_progress_frame.pack(fill=X, pady=(0, 4), before=self._btn_export_one)

        threading.Thread(
            target=self._reup_worker,
            args=(clip, dst, title, state["color_grade"], use_sub, state),
            daemon=True,
        ).start()

    def _reup_worker(self, clip: Path, dst: Path, title: str,
                     color_grade: bool, use_subtitles: bool,
                     edit_state: Optional[dict] = None):

        def _on_progress(frac: float):
            pct = max(0.0, min(100.0, frac * 100))
            self.after(0, lambda p=pct: (
                self._render_progress_var.set(p),
                self._render_progress_lbl.config(text=f"{p:.0f}%"),
            ))

        try:
            srt = None
            if use_subtitles:
                # Prefer Gemini (no local model, more accurate on short clips).
                # Falls back to Whisper if Gemini fails or API key is missing.
                client, sdk = None, None
                for k in self._get_all_keys():
                    if k.strip():
                        try:
                            client, sdk = build_client(k.strip())
                            break
                        except Exception:
                            pass
                _sub_engine = (edit_state or {}).get("sub_engine", "gemini_fallback")
                _sub_style  = edit_state.get("sub_style", "Normal") if edit_state else "Normal"
                _word_lvl   = True
                _sub_stop   = threading.Event()  # fresh event — analysis stop must not poison export
                if _sub_engine == "whisper":
                    if WHISPER_AVAILABLE:
                        srt = _whisper_transcribe(clip, self._logger, word_level=True, edit_state=edit_state)
                    if srt is None and client and sdk:
                        self._logger.warn("Whisper unavailable or failed — falling back to Gemini")
                        srt = _gemini_transcribe(clip, client, sdk,
                                                 self._logger, _sub_stop,
                                                 word_level=_word_lvl,
                                                 model_name=self._get_model_name(),
                                                 edit_state=edit_state)
                elif _sub_engine == "gemini":
                    if client and sdk:
                        srt = _gemini_transcribe(clip, client, sdk,
                                                 self._logger, _sub_stop,
                                                 word_level=_word_lvl,
                                                 model_name=self._get_model_name(),
                                                 edit_state=edit_state)
                else:  # "gemini_fallback"
                    if client and sdk:
                        srt = _gemini_transcribe(clip, client, sdk,
                                                 self._logger, _sub_stop,
                                                 word_level=_word_lvl,
                                                 model_name=self._get_model_name(),
                                                 edit_state=edit_state)
                    if srt is None and WHISPER_AVAILABLE:
                        srt = _whisper_transcribe(clip, self._logger, word_level=True, edit_state=edit_state)


            render_reup(clip, dst, title, color_grade, srt, self._logger,
                        edit_state=edit_state,
                        render_cfg=self._get_render_cfg(),
                        progress_cb=_on_progress)

            # Organize outputs: move srt and json to separate folders
            out_dir = Path(self._output_var.get())
            if srt and srt.exists():
                srt_dir = out_dir / "srt"
                srt_dir.mkdir(parents=True, exist_ok=True)
                final_srt = srt_dir / (clip.stem + "_reup.srt")
                import shutil
                try:
                    shutil.copy(srt, final_srt)
                    srt.unlink(missing_ok=True)
                except Exception as copy_err:
                    self._logger.warn(f"Could not copy SRT: {copy_err}")

            words_json = clip.with_suffix(".words.json")
            if words_json.exists():
                json_dir = out_dir / "json"
                json_dir.mkdir(parents=True, exist_ok=True)
                final_json = json_dir / (clip.stem + "_reup.json")
                import shutil
                try:
                    shutil.copy(words_json, final_json)
                    words_json.unlink(missing_ok=True)
                except Exception as copy_err:
                    self._logger.warn(f"Could not copy JSON: {copy_err}")

            self.after(0, lambda: self._on_reup_done(dst))
        except Exception as exc:
            lines = [l.strip() for l in str(exc).splitlines() if l.strip()]
            short = " | ".join(lines[-6:])[:400] if lines else str(exc)[:400]
            self._logger.error(f"Reup failed: {short}")
            self.after(0, lambda: (
                self._btn_export_one.config(state=NORMAL, text="📱  Export Current"),
                self._btn_export_all.config(state=NORMAL),
                self._render_progress_frame.pack_forget(),
                self._set_status("Reup render failed", CLR_ERROR),
            ))

    def _on_reup_done(self, dst: Path):
        self._btn_export_one.config(state=NORMAL, text="📱  Export Current")
        self._btn_export_all.config(state=NORMAL)
        self._render_progress_frame.pack_forget()  # hide progress bar
        self._set_status(f"Reup saved: {dst.name}", CLR_SUCCESS)
        self._toast(f"Export done: {dst.name}", kind="success", duration=5000)
        if messagebox.askyesno("Reup Ready!",
                f"Portrait 9:16 video saved:\n{dst}\n\nOpen output folder?"):
            os.startfile(str(dst.parent))

    # ── Stop ────────────────────────────────────────────────────────────────

    def _stop_work(self):
        self._stop.set()
        self._set_status("Stopping…", CLR_WARN)
        self._btn_stop.config(state=DISABLED)
        self._btn_retry.config(state=DISABLED)
        self._logger.warn("Stop requested — all threads will finish current step and exit.")
        self._toast("Stop requested — finishing current steps…", kind="warning")


    # ── Retry Errors ────────────────────────────────────────────────────────

    def _retry_errors(self):
        """Re-run analysis only for videos that previously failed."""
        keys = self._get_all_keys()
        if not keys:
            messagebox.showerror("Missing", "Please enter at least one API key.")
            return

        # Collect the failed videos
        failed = [
            p for p in self._video_files
            if self._video_results.get(str(p), {}).get("status") == ST_ERROR
        ]
        if not failed:
            return

        self._stop.clear()

        # Reset each failed video to queued in state + queue display
        for p in failed:
            self._video_results[str(p)] = {"status": ST_QUEUED, "candidates": []}
            self._queue_update(p, ST_QUEUED, "Queued")

        n = len(failed)
        max_concurrent = min(3, n)
        sem = threading.Semaphore(max_concurrent)

        self._btn_analyze.config(state=DISABLED, text="ANALYZING…", bg="#4f4f4f")
        self._btn_stop.config(state=NORMAL)
        self._btn_retry.config(state=DISABLED)
        self._prog_var.set(0)
        self._set_status(
            f"Retrying {n} failed video(s)  —  up to {max_concurrent} at a time…",
            CLR_WARN,
        )
        self._logger.header("=" * 50)
        self._logger.header(f"  Retry: {n} failed video(s), {len(keys)} key(s)")
        self._logger.header("=" * 50)

        self._active_threads = []
        rotator = KeyRotator(keys)   # shared round-robin distributor
        for video_path in failed:
            t = threading.Thread(
                target=self._analyze_one_video,
                args=(video_path, rotator, sem),
                daemon=True,
            )
            self._active_threads.append(t)
            t.start()


    # ── Update Checking ──────────────────────────────────────────────────────

    def _check_for_updates(self):
        """Fetch version info in a background thread and show banner on mismatch."""
        try:
            import requests
            r = requests.get(UPDATE_CHECK_URL, timeout=4)
            if r.status_code == 200:
                data = r.json()
                latest = data.get("latest_version")
                download_url = data.get("download_url")
                # Strip leading 'v' if present for comparison
                local_ver = APP_VERSION.lstrip("v")
                latest_ver = latest.lstrip("v") if latest else ""
                if latest_ver and latest_ver != local_ver:
                    self.after(0, lambda: self._show_update_banner(latest, download_url))
        except Exception:
            pass  # fail silently to keep startup uninterrupted

    def _show_update_banner(self, latest: str, url: str):
        """Build and slide in a beautiful update notification banner."""
        banner = self._update_banner
        banner.pack(side=TOP, fill=X, padx=20, pady=(0, 8))

        # Vibrant alert background styling
        lbl = ttk.Label(
            banner, text=f"🔔  A new version ({latest}) is available!",
            foreground="#fbbf24", font=("Segoe UI", 9, "bold"),
            background=CLR_PANEL,
        )
        lbl.pack(side=LEFT, padx=12, pady=6)

        btn = tk.Button(
            banner, text="Download Update", bg="#d97706", fg="white",
            font=("Segoe UI", 8, "bold"), relief=FLAT, padx=10, pady=2,
            activebackground="#b45309", cursor="hand2",
            command=lambda: os.startfile(url),
        )
        btn.pack(side=LEFT, padx=10)

        dismiss = tk.Button(
            banner, text="✕", bg=CLR_PANEL, fg=CLR_DIM,
            font=("Segoe UI", 9, "bold"), relief=FLAT, cursor="hand2",
            activebackground=CLR_PANEL, activeforeground=CLR_FG,
            command=banner.pack_forget,
        )
        dismiss.pack(side=RIGHT, padx=12)

    # ── Drag and Drop + 16s Clip Import ──────────────────────────────────────

    def _setup_drag_and_drop(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes

            WM_DROPFILES = 0x0233
            GWL_WNDPROC = -4

            hwnd = self.winfo_id()
            ctypes.windll.shell32.DragAcceptFiles(hwnd, True)

            # Explicitly declare ctypes for Shell32 DragQueryFileW and DragFinish to avoid pointer truncating
            ctypes.windll.shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
            ctypes.windll.shell32.DragQueryFileW.restype = ctypes.c_uint
            ctypes.windll.shell32.DragFinish.argtypes = [ctypes.c_void_p]
            ctypes.windll.shell32.DragFinish.restype = None

            if ctypes.sizeof(ctypes.c_void_p) == 8:
                SetWindowLongPtr = ctypes.windll.user32.SetWindowLongPtrW
                GetWindowLongPtr = ctypes.windll.user32.GetWindowLongPtrW
                WNDPROC_TYPE = ctypes.WINFUNCTYPE(
                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p
                )
            else:
                SetWindowLongPtr = ctypes.windll.user32.SetWindowLongW
                GetWindowLongPtr = ctypes.windll.user32.GetWindowLongW
                WNDPROC_TYPE = ctypes.WINFUNCTYPE(
                    ctypes.c_int32, ctypes.c_int32, ctypes.c_uint, ctypes.c_int32, ctypes.c_int32
                )

            SetWindowLongPtr.restype = ctypes.c_void_p
            SetWindowLongPtr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            GetWindowLongPtr.restype = ctypes.c_void_p
            GetWindowLongPtr.argtypes = [ctypes.c_void_p, ctypes.c_int]

            CallWindowProc = ctypes.windll.user32.CallWindowProcW
            CallWindowProc.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
            CallWindowProc.restype = ctypes.c_void_p

            self._old_wndproc = GetWindowLongPtr(hwnd, GWL_WNDPROC)

            def wndproc(hwnd_val, msg, wparam, lparam):
                if msg == WM_DROPFILES:
                    try:
                        hdrop = wparam
                        num_files = ctypes.windll.shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                        files = []
                        for i in range(num_files):
                            buf_len = ctypes.windll.shell32.DragQueryFileW(hdrop, i, None, 0) + 1
                            buf = ctypes.create_unicode_buffer(buf_len)
                            ctypes.windll.shell32.DragQueryFileW(hdrop, i, buf, buf_len)
                            files.append(Path(buf.value))
                        ctypes.windll.shell32.DragFinish(hdrop)
                        self.after(0, lambda: self._on_files_dropped(files))
                    except Exception as e:
                        print(f"Error handling dropped files: {e}")
                    return 0
                return CallWindowProc(self._old_wndproc, hwnd_val, msg, wparam, lparam)

            self._wndproc_cb = WNDPROC_TYPE(wndproc)
            SetWindowLongPtr(hwnd, GWL_WNDPROC, self._wndproc_cb)
        except Exception as e:
            print(f"Could not setup native drag and drop: {e}")

    def _on_files_dropped(self, files: list[Path]):
        valid_files = [f for f in files if f.suffix.lower() in SUPPORTED_EXT]
        if not valid_files:
            return

        active_tab = self._tab_notebook.index(self._tab_notebook.select())
        if active_tab == 0:
            existing = {p.resolve() for p in self._video_files}
            new_added = 0
            for f in valid_files:
                if f.resolve() not in existing:
                    self._video_files.append(f)
                    new_added += 1
            if new_added > 0:
                self._refresh_file_listbox()
                self._toast(f"Dropped {new_added} video(s) into Tab 1.", kind="success")
        elif active_tab == 1:
            keys = self._get_all_keys()
            if not keys:
                messagebox.showerror("No API Key", "Please add at least one Gemini API key in Tab 1.")
                return
            self._toast(f"Importing {len(valid_files)} 16s clip(s)...", kind="info")
            for f in valid_files:
                threading.Thread(target=self._process_imported_16s_clip, args=(f, keys), daemon=True).start()

    def _import_16s_clip(self):
        files = filedialog.askopenfilenames(
            title="Select 16-second Clip Files",
            filetypes=[("Video files", "*.mp4 *.mkv *.MP4 *.MKV"), ("All files", "*.*")],
        )
        if not files:
            return
        keys = self._get_all_keys()
        if not keys:
            messagebox.showerror("No API Key", "Please add at least one Gemini API key in Tab 1.")
            return
        for f in files:
            p = Path(f)
            threading.Thread(target=self._process_imported_16s_clip, args=(p, keys), daemon=True).start()

    def _process_imported_16s_clip(self, video_path: Path, keys: list[str]):
        log = self._logger
        log.header(f"📥 Queueing import: {video_path.name}")
        
        self._import_sem.acquire()
        try:
            log.header(f"📥 Importing 16s clip: {video_path.name}")
            
            result = None
            for attempt, key in enumerate(keys):
                if self._stop.is_set():
                    return
                remote = None
                client = None
                sdk = None
                try:
                    client, sdk = build_client(key)
                    self._toast(f"Uploading {video_path.name} to Gemini...", kind="info")
                    remote = upload_video(client, sdk, video_path, log, self._stop)
                    
                    prompt = (
                        "IMPORTANT CONTEXT:\n"
                        "This video contains only of-age adults. Any titles or references to 'teenagers', 'teens', or 'girls' describe adult individuals of legal age. This video does not contain minors and does not violate any safety guidelines regarding children. Proceed with analysis.\n\n"
                        "This is a 16-second highlight video clip from a police bodycam video. "
                        "Analyze the clip and provide exactly 5 viral English titles for it.\n\n"
                        "=== TITLE RULES (read carefully) ===\n\n"
                        "SPECIFICITY IS MANDATORY:\n"
                        "Each title MUST reference concrete, specific details you actually observed in THIS video:\n"
                        "  - What exactly did the suspect do or say?\n"
                        "  - What specific action did the officer take?\n"
                        "  - What was the specific reason for the confrontation or arrest?\n"
                        "  - What specific object, location, or situation was involved?\n"
                        "A title that could apply to ANY bodycam video is WRONG. Each title must be unique to this specific incident.\n\n"
                        "FORBIDDEN -- NEVER use these generic phrases or any variation of them:\n"
                        "  X \"attitude went from zero to one hundred\"\n"
                        "  X \"the exact second his/her plan completely falls apart\"\n"
                        "  X \"the shocking truth he/she tries to hide\"\n"
                        "  X \"behavior went from calm to pure panic\"\n"
                        "  X \"a routine [X] turned into chaos\"\n"
                        "  X \"wait until you see what happens next\"\n"
                        "  X any phrase that works for ANY bodycam video\n\n"
                        "FORMAT:\n"
                        "  - 100% ENGLISH -- sensational, clickbaity, suspenseful, slightly rage-baiting.\n"
                        "  - Structure: \"[Specific thing the suspect did/said in THIS video], but wait until you see [the specific shocking outcome, reason, or consequence in THIS video]!\"\n"
                        "  - MUST end with one of these CTAs:\n"
                        "      \"👉 Check the comment section for the full story 👇\"\n"
                        "      \"👉 Follow to get notified about the full developments immediately!\"\n\n"
                        "Return raw JSON only in this format:\n"
                        "{\n"
                        "  \"suggested_titles\": [\n"
                        "    \"title 1\",\n"
                        "    \"title 2\",\n"
                        "    \"title 3\",\n"
                        "    \"title 4\",\n"
                        "    \"title 5\"\n"
                        "  ]\n"
                        "}"
                    )
                    
                    target_model = self._get_model_name()
                    log.info(f"🔍 [{video_path.name}] Generating titles via {target_model}...")
                    self._toast(f"Generating titles for {video_path.name}...", kind="info")
                    if sdk == "new":
                        from google.genai import types as _gt
                        safety = [
                            _gt.SafetySetting(
                                category=_gt.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                                threshold=_gt.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            _gt.SafetySetting(
                                category=_gt.HarmCategory.HARM_CATEGORY_HARASSMENT,
                                threshold=_gt.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            _gt.SafetySetting(
                                category=_gt.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                                threshold=_gt.HarmBlockThreshold.BLOCK_NONE,
                            ),
                            _gt.SafetySetting(
                                category=_gt.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                                threshold=_gt.HarmBlockThreshold.BLOCK_NONE,
                            ),
                        ]
                        resp = client.models.generate_content(
                            model=target_model,
                            contents=[remote, prompt],
                            config=_gt.GenerateContentConfig(
                                temperature=0.4, max_output_tokens=1024,
                                safety_settings=safety,
                            ),
                        )
                        raw = resp.text
                    else:
                        safety_old = [
                            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                        ]
                        model = client.GenerativeModel(
                            target_model,
                            generation_config={"temperature": 0.4, "max_output_tokens": 1024},
                        )
                        raw = model.generate_content(
                            [remote, prompt],
                            safety_settings=safety_old,
                        ).text
                    
                    raw = (raw or "").strip()
                    parsed = extract_json(raw)
                    if parsed and parsed.get("suggested_titles"):
                        # Strip any preamble Gemini added inside the title strings
                        result = [_clean_title_str(t) for t in parsed.get("suggested_titles") if t]
                        result = [t for t in result if t]  # drop empties after cleanup
                        break
                    else:
                        snippet = (raw[:300] if raw else "None")
                        raise ValueError(f"No suggested_titles in Gemini response:\n{snippet}")
                except Exception as e:
                    log.warn(f"[{video_path.name}] Error with key #{attempt+1}: {e}")
                    if attempt == len(keys) - 1:
                        log.error(f"[{video_path.name}] Failed to generate titles: {e}")
                        self.after(0, lambda: self._toast(f"Failed to generate titles for {video_path.name}.", kind="error"))
                        return
                finally:
                    if remote and client and sdk:
                        try:
                            delete_remote(client, sdk, remote, log)
                        except Exception:
                            pass

            if result:
                def _add_to_queue():
                    first_title = result[0]
                    item = {
                        "clip_path": video_path,
                        "title":     first_title,
                        "suggested_titles": result,
                        "state":     _default_edit_state(),
                    }
                    # Apply global template if Sync All is active
                    if getattr(self, "_edit_sync_all", None) and self._edit_sync_all.get():
                        item["state"].update(self._global_edit_state)
                    self._edit_queue.append(item)
                    self._edit_listbox.insert(END, video_path.stem)
                    self._update_queue_count_label()

                    # Automatically select the newly added item
                    idx = len(self._edit_queue) - 1
                    self._edit_listbox.selection_clear(0, END)
                    self._edit_listbox.selection_set(idx)
                    self._edit_sel_idx = idx
                    
                    self._btn_export_one.config(state=NORMAL)
                    self._btn_export_all.config(state=NORMAL)
                    self._tab_notebook.select(1)  # Switch to Tab 2
                    self._on_edit_select()
                    log.ok(f"📥 Successfully imported {video_path.name} to Edit Queue.")
                    self._toast(f"Imported {video_path.name}!", kind="success")

                self.after(0, _add_to_queue)
        finally:
            self._import_sem.release()

    def _refresh_edit_suggestions_ui(self):
        for widget in self._edit_suggestions_frame.winfo_children():
            widget.destroy()

        if self._edit_sel_idx < 0 or self._edit_sel_idx >= len(self._edit_queue):
            return

        item = self._edit_queue[self._edit_sel_idx]
        suggested = item.get("suggested_titles", [])
        if not suggested:
            return

        tk.Label(
            self._edit_suggestions_frame, text="Suggested Titles:",
            bg=CLR_SURFACE, fg=CLR_DIM, font=("Segoe UI", 8, "bold")
        ).pack(anchor=W, pady=(2, 2))

        for idx, t in enumerate(suggested):
            def _set_title(title_text=t):
                self._edit_title_text_var.set(title_text)

            btn = tk.Button(
                self._edit_suggestions_frame,
                text=f"{idx+1}. {t}",
                anchor=W, justify=LEFT, bg=CLR_INPUT_BG, fg=CLR_FG,
                activebackground=CLR_SURFACE, activeforeground=CLR_FG,
                font=("Segoe UI", 8), relief=FLAT, bd=0,
                padx=6, pady=4, cursor="hand2", wraplength=320
            )
            btn.config(command=_set_title)
            btn.pack(fill=X, pady=1)


# ──────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    app = CliperApp()
    app.mainloop()
