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
MIN_STORY_DUR = 90   # Story Mode: minimum scene duration (1m30s)
MAX_STORY_DUR = 120  # Story Mode: maximum scene duration (2m00s)
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

    stack = np.stack(frames, axis=0)
    std_map = np.std(stack, axis=0)
    mean_map = np.mean(stack, axis=0)

    # Exclude near-black letterbox / pillarbox borders (mean < 15) which naturally have std ~ 0
    non_black = mean_map >= 15

    norm = cv2.normalize(std_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    inv = 255 - norm                              # low std → high value

    # If there are active pixels outside black bars, calculate percentile on them
    if np.any(non_black):
        valid_inv = inv[non_black]
        thresh_val = np.percentile(valid_inv, 90) if len(valid_inv) > 100 else np.percentile(inv, 90)
        mask = ((inv >= thresh_val) & non_black).astype(np.uint8) * 255
    else:
        thresh_val = np.percentile(inv, 90)
        mask = (inv >= thresh_val).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.dilate(mask, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []

    def _eval_contours(cnts):
        cands = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            area = w * h
            if area < 120 or area > 0.20 * width * height:
                continue
            # Watermark logos are reasonably compact; skip extreme aspect ratio bars
            if w / max(1, h) > 8.0 or h / max(1, w) > 8.0:
                continue
            score = area
            if corner_bias:
                cx, cy = x + w / 2, y + h / 2
                corners = [(0, 0), (width, 0), (0, height), (width, height)]
                dist = min(((cx - cx2) ** 2 + (cy - cy2) ** 2) ** 0.5 for cx2, cy2 in corners)
                dist_norm = dist / ((width ** 2 + height ** 2) ** 0.5)
                score = area * ((1.0 - dist_norm) ** 2)
            cands.append((score, x, y, w, h))
        return cands

    if contours:
        candidates = _eval_contours(contours)

    # Fallback pass with lower threshold (85th percentile) for faint/semi-transparent logos
    if not candidates:
        thresh_fb = np.percentile(inv, 85)
        mask_fb = (inv >= thresh_fb).astype(np.uint8) * 255
        if np.any(non_black):
            mask_fb[~non_black] = 0
        mask_fb = cv2.morphologyEx(mask_fb, cv2.MORPH_OPEN, kernel)
        mask_fb = cv2.dilate(mask_fb, kernel, iterations=2)
        cnts_fb, _ = cv2.findContours(mask_fb, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cnts_fb:
            candidates = _eval_contours(cnts_fb)

    if not candidates:
        return None

    _, x, y, w, h = max(candidates, key=lambda t: t[0])
    pad = max(10, int(0.12 * max(w, h)))
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


# ── OCR Engine Singleton (Multi-Tier Hardware Acceleration + Safe Fallback) ──────
# Cached at module level: avoids 0.5-1s re-init on every call.
# Multi-Tier Provider Priority:
#   1. CUDA Execution Provider (NVIDIA CUDA Toolkit & cuDNN runtime)
#   2. DirectML Execution Provider (DirectX 12 GPU acceleration on NVIDIA GeForce,
#      AMD Radeon, and Intel Arc/Iris using standard display drivers — zero extra setup!)
#   3. CPU Execution Provider (Universal fallback on any machine without GPU)
_RAPIDOCR_INSTANCE = None
_RAPIDOCR_DEVICE = "CPU"
_OCR_LOCK = threading.RLock()

def _setup_cuda_dlls():
    """Ensure CUDA & cuDNN DLLs (e.g. cudnn64_9.dll, cublas64_12.dll) are accessible by onnxruntime on Windows."""
    search_dirs = []

    # 1. PyInstaller frozen bundle environment
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass and os.path.isdir(meipass):
            search_dirs.append(meipass)
        exe_dir = os.path.dirname(sys.executable)
        if exe_dir and os.path.isdir(exe_dir):
            search_dirs.append(exe_dir)
            search_dirs.append(os.path.join(exe_dir, 'cuda_libs'))

    # 2. Local app directory
    app_dir = str(Path(__file__).parent)
    search_dirs.append(app_dir)
    search_dirs.append(os.path.join(app_dir, 'cuda_libs'))

    # 3. PyTorch CUDA / cuDNN directory if installed
    try:
        import torch
        t_lib = os.path.join(os.path.dirname(torch.__file__), 'lib')
        if os.path.isdir(t_lib):
            search_dirs.append(t_lib)
    except Exception:
        pass

    # 4. Standard CUDA Toolkit system installations if present
    cuda_path = os.environ.get('CUDA_PATH', '')
    if cuda_path and os.path.isdir(cuda_path):
        search_dirs.append(os.path.join(cuda_path, 'bin'))
        search_dirs.append(os.path.join(cuda_path, 'bin', 'x64'))

    toolkit_root = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    if os.path.isdir(toolkit_root):
        try:
            for entry in os.listdir(toolkit_root):
                v_bin = os.path.join(toolkit_root, entry, 'bin')
                if os.path.isdir(v_bin):
                    search_dirs.append(v_bin)
                    search_dirs.append(os.path.join(v_bin, 'x64'))
        except Exception:
            pass

    # Prepend discovered directories to PATH and register with AddDllDirectory
    current_path = os.environ.get('PATH', '')
    for d in search_dirs:
        if os.path.isdir(d):
            if d not in current_path:
                current_path = d + os.pathsep + current_path
                os.environ['PATH'] = current_path
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(d)
                except Exception:
                    pass

def get_ocr_device() -> str:
    """Return active OCR engine device (e.g. 'GPU (DirectML)', 'GPU (CUDA)', or 'CPU')."""
    global _RAPIDOCR_DEVICE
    if _RAPIDOCR_INSTANCE is None:
        with _OCR_LOCK:
            if _RAPIDOCR_INSTANCE is None:
                _get_ocr_engine()
    return _RAPIDOCR_DEVICE

def _get_ocr_engine():
    """Return cached RapidOCR engine with automatic GPU (CUDA / DirectML) acceleration and CPU fallback."""
    global _RAPIDOCR_INSTANCE, _RAPIDOCR_DEVICE
    if _RAPIDOCR_INSTANCE is not None:
        return _RAPIDOCR_INSTANCE

    with _OCR_LOCK:
        if _RAPIDOCR_INSTANCE is not None:
            return _RAPIDOCR_INSTANCE

        import rapidocr_onnxruntime.rapid_ocr_api as api
        import rapidocr_onnxruntime.utils as ocr_utils
        import onnxruntime as ort
        import numpy as np

        _setup_cuda_dlls()

        orig_ort_init = getattr(ocr_utils, '_orig_ort_init', None)
        if orig_ort_init is None:
            orig_ort_init = ocr_utils.OrtInferSession.__init__
            ocr_utils._orig_ort_init = orig_ort_init

        available_providers = ort.get_available_providers()

        # ── 1. Try Hardware-Accelerated GPU (CUDA or DirectML) ───────────────────
        has_gpu_provider = ('CUDAExecutionProvider' in available_providers or 'DmlExecutionProvider' in available_providers)
        if has_gpu_provider:
            try:
                try:
                    ort.set_default_logger_severity(3)
                except Exception:
                    pass

                def _smart_gpu_ort_init(self, config):
                    sess_opt = ort.SessionOptions()
                    sess_opt.log_severity_level = 4
                    sess_opt.enable_cpu_mem_arena = False
                    sess_opt.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

                    EP_list = []
                    # Priority 1: NVIDIA CUDA EP (if available)
                    if 'CUDAExecutionProvider' in available_providers:
                        EP_list.append(('CUDAExecutionProvider', {
                            'device_id': 0,
                            'arena_extend_strategy': 'kNextPowerOfTwo',
                            'cudnn_conv_algo_search': 'EXHAUSTIVE',
                            'do_copy_in_default_stream': True
                        }))
                    # Priority 2: DirectML EP (Hardware-accelerated DirectX 12 on NVIDIA GeForce, AMD, Intel)
                    if 'DmlExecutionProvider' in available_providers:
                        EP_list.append(('DmlExecutionProvider', {
                            'device_id': 0,
                        }))
                    # Fallback: CPU
                    EP_list.append(('CPUExecutionProvider', {
                        'arena_extend_strategy': 'kSameAsRequested',
                    }))

                    self._verify_model(config['model_path'])
                    self.session = ort.InferenceSession(config['model_path'], sess_options=sess_opt, providers=EP_list)

                ocr_utils.OrtInferSession.__init__ = _smart_gpu_ort_init

                gpu_instance = api.RapidOCR()
                det_sess = getattr(getattr(gpu_instance.text_detector, 'infer', None), 'session', None)
                providers = det_sess.get_providers() if det_sess else []

                # Warmup dummy inference to verify runtime linking
                dummy = np.zeros((64, 128, 3), dtype=np.uint8)
                gpu_instance(dummy)

                if 'CUDAExecutionProvider' in providers:
                    _RAPIDOCR_DEVICE = "GPU (CUDA)"
                elif 'DmlExecutionProvider' in providers:
                    _RAPIDOCR_DEVICE = "GPU (DirectML)"
                else:
                    _RAPIDOCR_DEVICE = "CPU"

                if "GPU" in _RAPIDOCR_DEVICE:
                    _RAPIDOCR_INSTANCE = gpu_instance
                    print(f"[OCR] RapidOCR {_RAPIDOCR_DEVICE} initialized successfully. Providers: {providers}", flush=True)
                    return _RAPIDOCR_INSTANCE
                else:
                    print(f"[OCR] Neither CUDA nor DirectML active in session ({providers}), falling back to pure CPU.", flush=True)
            except Exception as e:
                print(f"[OCR] GPU init/warmup failed ({e}), falling back to CPU.", flush=True)
            finally:
                ocr_utils.OrtInferSession.__init__ = orig_ort_init

        # ── 2. Clean fallback to Pure CPU ─────────────────────────────────────────
        try:
            ocr_utils.OrtInferSession.__init__ = orig_ort_init
            cpu_instance = api.RapidOCR()
            dummy = np.zeros((64, 128, 3), dtype=np.uint8)
            cpu_instance(dummy)
            _RAPIDOCR_INSTANCE = cpu_instance
            _RAPIDOCR_DEVICE = "CPU"
            print("[OCR] Using CPU RapidOCR engine (verified & active).", flush=True)
            return _RAPIDOCR_INSTANCE
        except Exception as e2:
            print(f"[WARN] RapidOCR CPU init failed: {e2}", flush=True)
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
                    with _OCR_LOCK:
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
2. Viral Score (1-10) and brief score reason.
3. A brief explanation of why this moment is highly viral (mention the segment type).
4. Exactly 5 viral English titles.

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

LENGTH & FORMAT:
  - STRICT LENGTH: Keep titles concise and punchy — target 10 to 14 words (STRICT MAXIMUM 15 words). Never write long, bloated titles.
  - Cut all filler words, long setups, and unnecessary preambles. Deliver the specific incident and punchline fast.
  - 100% ENGLISH -- sensational, clickbaity, suspenseful, slightly rage-baiting.
  - Structure: "[Specific suspect action in THIS video], but wait until you see [shocking outcome/charge]!" OR "[Specific action] right before [instant karma/consequence]!"
  - DO NOT include any Call-To-Action (CTA) emojis or phrases at the end (no "👉 Check comments...", no "👉 Follow..."). Keep titles clean and focused purely on the viral story hook.

GOOD (specific, concise, 10–14 words):
  "She threw her drink at the officer, but wait until you see the felony charge!" (15 words)
  "He yelled 'you can't search me' seconds before the K9 hit his car!" (13 words)
  "She refused to drop the weapon, but wait until you see what stopped her!" (14 words)
  "He handed over a fake ID, but the officer caught the lie instantly!" (13 words)
  "She screamed illegal detention, but wait until you see what the search revealed!" (13 words)
  "He ran two red lights, but the plate check exposed his biggest secret!" (13 words)
  "She bit the arresting officer, picking up two shocking felony charges!" (11 words)

BAD (too long, 18+ words -- FORBIDDEN):
  X "She threw her drink at the officer during the traffic stop, but wait until you see the exact charge that ended her night!" (23 words - TOO LONG)
  X "He screamed 'I know my rights, you can't search me!' right before the K9 sat down next to his door, but wait until you see what the dog found in 10 seconds flat!" (31 words - WAY TOO LONG)
  X "Her attitude went from zero to one hundred, but wait until you see the shocking reason she gets arrested!" (Generic)

=====================================

=== VIRAL SCORING & STRICT QUALITY FILTER (THRESHOLD > 6/10) ===

Evaluate each candidate segment on a strict viral potential scale from 1 to 10 (score: integer from 1 to 10):
  - 1 to 5: Routine discussion, calm traffic stop, mundane procedures, no tension or climax, boring filler.
  - 6: Mild tension or standard argument without escalating drama or consequence (MEDIOCRE).
  - 7 to 8: Strong viral potential — intense physical struggle, taser deployment, sudden plot twist, suspect caught lying, instant karma backfire, or high-adrenaline pursuit.
  - 9 to 10: Explosive, sensational viral gold — jaw-dropping revelation, wild crash, instant shock, intense altercation.

MANDATORY FILTER RULE:
- ONLY return candidates with a viral_score of 7 or higher (viral_score > 6 out of 10).
- If a segment scores 6 or below, DISCARD IT. Do NOT include any candidates with viral_score <= 6 in your response.
- Every returned candidate must have "viral_score" (integer 7-10) and "score_reason".

Return ONLY a raw JSON object -- no markdown fences:
{
  "candidates": [
    {
      "id": 1,
      "start_time": "00:12:30",
      "end_time": "00:12:46",
      "viral_score": 8,
      "score_reason": "Instant karma when suspect brags about escaping and gets immediately tased.",
      "reason": "Why this specific segment is viral.",
      "suggested_titles": [
        "She threw her drink at the officer, but wait until you see the felony charge!",
        "He yelled 'you can't search me' seconds before the K9 hit his car!",
        "She refused to drop the weapon, but wait until you see what stopped her!",
        "He handed over a fake ID, but the officer caught the lie instantly!",
        "She screamed illegal detention, but wait until you see what the search revealed!"
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
3. Viral Score (1-10) and brief score reason.
4. A brief explanation of why this scene is viral (mention arc type).
5. Exactly 5 viral English titles.

{SYSTEM_PROMPT.split('=== TITLE RULES')[1].split('Return ONLY a raw JSON object')[0] if '=== TITLE RULES' in SYSTEM_PROMPT else ''}
Return ONLY a raw JSON object -- no markdown fences:
{{
  "candidates": [
    {{
      "id": 1,
      "start_time": "00:05:10",
      "end_time": "00:06:05",
      "viral_score": 9,
      "score_reason": "High-intensity escalating confrontation with unexpected resolution.",
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
                  mode: str = "short",
                  min_viral_score: Optional[float] = 6.0) -> dict:
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
            "DYNAMIC CANDIDATE SELECTION & SCORING FILTER (Strictly > 6/10):\n"
            "- Rate each scene from 1 to 10 on viral hook potential.\n"
            "- CRITICAL: Return ONLY scenes with viral_score > 6 (7, 8, 9, or 10). Omit any scenes scoring 6 or below.\n"
            "- If a video has many compelling scenes, return ALL of them.\n"
            "- Each candidate MUST include start_time, end_time (HH:MM:SS), viral_score (int 7-10), score_reason, reason, and suggested_titles.\n"
            "Return raw JSON only."
            f"{duration_hint}"
            f"{rejection_context}"
        )
        _system = SYSTEM_PROMPT_STORY
    else:
        user_prompt = (
            "Analyze the police bodycam video thoroughly and identify EVERY SINGLE 16-second segment "
            "that has genuine viral potential (drama, tension, karma backfire, shock, unexpected twist, or intense confrontation).\n\n"
            "DYNAMIC CANDIDATE SELECTION & SCORING FILTER (Strictly > 6/10):\n"
            "- Rate each candidate moment on viral hook potential from 1 to 10.\n"
            "- CRITICAL FILTER: Return ONLY candidate segments with viral_score > 6 (score 7, 8, 9, 10). Do NOT return any segments scoring 6 or below.\n"
            "- There is NO fixed quota, minimum, or maximum limit on the number of candidates.\n"
            "- Quality, hook intensity, and viral payoff are the ONLY criteria.\n"
            "- Each candidate MUST include start_time, end_time, viral_score (int 7-10), score_reason, reason, and suggested_titles.\n"
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
    raw_candidates = parsed.get("candidates", [])
    threshold = float(min_viral_score) if min_viral_score is not None else 6.0
    cleaned_candidates = []

    # Strip preamble labels Gemini sometimes adds inside title strings and filter by score
    for idx, cand in enumerate(raw_candidates):
        # Extract and normalize viral_score
        raw_score = cand.get("viral_score") if cand.get("viral_score") is not None else cand.get("score")
        try:
            score_val = round(float(raw_score), 1) if raw_score is not None else 7.0
        except (ValueError, TypeError):
            score_val = 7.0
        cand["viral_score"] = score_val

        # Programmatic quality gate: filter out candidates with score <= threshold
        if threshold > 0 and score_val <= threshold:
            log.dim(f"   [Filtered] Candidate #{cand.get('id', idx+1)} at {cand.get('start_time')} omitted (Score: {score_val}/10 <= {threshold})")
            continue

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
        cleaned_candidates.append(cand)

    # Safety fallback: if strict filter eliminated all candidates but Gemini returned some,
    # keep the single highest-scoring candidate so the video isn't left empty without explanation.
    if not cleaned_candidates and raw_candidates and threshold > 0:
        log.warn(f"[{video_name}] Tất cả cảnh đều có điểm <= {threshold}/10. Giữ lại cảnh có điểm cao nhất.")
        best_cand = max(raw_candidates, key=lambda c: float(c.get("viral_score", 0.0)))
        dur = float(best_cand.get("clip_duration") or CLIP_DURATION)
        raw_start = str(best_cand.get("start_time", "00:00:00")).strip()
        start_sec = ts_to_seconds(raw_start)
        h = int(start_sec // 3600)
        m = int((start_sec % 3600) // 60)
        s = int(start_sec % 60)
        best_cand["start_time"] = f"{h:02d}:{m:02d}:{s:02d}"
        end_sec = start_sec + dur
        eh = int(end_sec // 3600)
        em = int((end_sec % 3600) // 60)
        es = int(end_sec % 60)
        best_cand["end_time"] = f"{eh:02d}:{em:02d}:{es:02d}"
        if not best_cand.get("title") and best_cand.get("suggested_titles"):
            best_cand["title"] = best_cand["suggested_titles"][0]
        cleaned_candidates.append(best_cand)

    parsed["candidates"] = cleaned_candidates
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
        'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'download_ranges': yt_dlp.utils.download_range_func(None, [(req_start, req_end)]),
        'force_keyframes_at_cuts': True,
        'outtmpl': str(out_p),
        'quiet': True,
        'no_warnings': True,
        'retries': 10,
        'fragment_retries': 10,
        'source_address': '0.0.0.0',  # Force IPv4 against Windows IPv6 connection reset drops
        'socket_timeout': 30,
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

    node_bin = shutil.which("node")
    if not node_bin:
        cand_node = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "node.exe"
        if cand_node.exists():
            node_bin = str(cand_node)
    if node_bin:
        try:
            ydl_opts['js_runtimes'] = {'node': {'path': str(Path(node_bin).resolve())}}
        except Exception:
            pass

    MIN_VALID_CLIP_BYTES = 50 * 1024  # Valid 15-90s MP4 clips are >= 50KB; empty skeletons are ~261 bytes

    def _reconcile_alt_container() -> bool:
        """If yt-dlp wrote out_p.webm or out_p.mkv despite merge_output_format, remux/re-encode it to out_p (.mp4)."""
        if out_p.exists() and out_p.stat().st_size >= MIN_VALID_CLIP_BYTES:
            return True
        for alt_ext in (".webm", ".mkv", ".mp4"):
            alt_p = out_p.with_name(out_p.name + alt_ext)
            if alt_p.exists() and alt_p.stat().st_size >= MIN_VALID_CLIP_BYTES:
                try:
                    ffmpeg_bin = str(Path(FFMPEG).resolve()) if (FFMPEG and Path(FFMPEG).exists()) else "ffmpeg"
                    subprocess.run(
                        [ffmpeg_bin, "-y", "-i", str(alt_p), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-c:a", "aac", str(out_p)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=120,
                        check=False,
                    )
                    if out_p.exists() and out_p.stat().st_size >= MIN_VALID_CLIP_BYTES:
                        try:
                            alt_p.unlink()
                        except Exception:
                            pass
                        return True
                except Exception:
                    pass
        return out_p.exists() and out_p.stat().st_size >= MIN_VALID_CLIP_BYTES

    def _safe_run_download(opts_dict: dict, max_tries: int = 2) -> bool:
        last_e = None
        for attempt in range(max_tries):
            try:
                # Clean up any partial/corrupted skeleton file before trying
                if out_p.exists() and out_p.stat().st_size < MIN_VALID_CLIP_BYTES:
                    try:
                        out_p.unlink()
                    except Exception:
                        pass
                with yt_dlp.YoutubeDL(opts_dict) as ydl_inst:
                    ydl_inst.download([url])
                if _reconcile_alt_container():
                    return True
                actual_sz = out_p.stat().st_size if out_p.exists() else 0
                last_e = RuntimeError(f"Tải video YouTube không thành công (file chỉ có {actual_sz} bytes, thiếu luồng video/audio)")
            except Exception as ex:
                last_e = ex
                if attempt < max_tries - 1:
                    time.sleep(2.0)
        if last_e:
            raise last_e
        return False

    try:
        _safe_run_download(ydl_opts, max_tries=2)
    except Exception as e:
        err_msg = str(e)
        is_age_err = any(w in err_msg.lower() for w in ["age-restricted", "confirm your age", "age restricted"])
        # Nếu cookie bị lỗi hoặc session cookie hỏng (và KHÔNG PHẢI video 18+) -> Thử lại không dùng cookie
        if ('cookiefile' in ydl_opts or 'cookiesfrombrowser' in ydl_opts) and not is_age_err:
            _safe_log("⚠️ Cookie YouTube bị lỗi hoặc hết hạn, đang tự động thử lại không dùng cookie...")
            ydl_opts_no_cookie = dict(ydl_opts)
            ydl_opts_no_cookie.pop('cookiefile', None)
            ydl_opts_no_cookie.pop('cookiesfrombrowser', None)
            ydl_opts_no_cookie.pop('extractor_args', None)
            try:
                if _safe_run_download(ydl_opts_no_cookie, max_tries=2):
                    if out_p.exists() and out_p.stat().st_size >= MIN_VALID_CLIP_BYTES:
                        return str(out_p.resolve())
            except Exception as e_retry:
                err_msg = str(e_retry)

        # Fallback 2: Thử luồng dự phòng linh hoạt không cookie, không giới hạn client/format
        _safe_log("🔄 Đang thử lại với luồng tải dự phòng linh hoạt...")
        ydl_opts_fallback = dict(ydl_opts)
        ydl_opts_fallback['format'] = 'bestvideo+bestaudio/best'
        ydl_opts_fallback['merge_output_format'] = 'mp4'
        ydl_opts_fallback.pop('cookiefile', None)
        ydl_opts_fallback.pop('cookiesfrombrowser', None)
        ydl_opts_fallback.pop('extractor_args', None)
        try:
            if _safe_run_download(ydl_opts_fallback, max_tries=2):
                if out_p.exists() and out_p.stat().st_size >= MIN_VALID_CLIP_BYTES:
                    return str(out_p.resolve())
        except Exception as e_fb:
            err_msg = str(e_fb)

        is_network_err = any(k in err_msg.lower() for k in [
            "connection reset", "timed out", "timeout", "remote end closed",
            "network is unreachable", "no route to host", "temporary failure in name resolution",
            "getaddrinfo failed", "connection refused", "broken pipe", "failed to establish a new connection"
        ])
        if is_network_err:
            raise RuntimeError(
                f"[LỖI MẠNG] Mất kết nối Internet hoặc mạng bị rớt khi đang tải clip ({err_msg}). "
                "Vui lòng kiểm tra lại đường truyền WiFi/mạng và bấm Thử lại!"
            ) from e

        if is_age_err:
            raise RuntimeError(
                "Video này bị YouTube gắn cờ giới hạn độ tuổi (18+ / Age-Restricted) và chặn tải tự động qua API. "
                "Giải pháp tốt nhất: Mở link trên trình duyệt tải file gốc về (bằng Cốc Cốc / IDM / extension), "
                "rồi bấm '+' nạp file video vào tool để cắt ngay!"
            ) from e

        if "Sign in to confirm" in err_msg or "bot" in err_msg.lower():
            raise RuntimeError(
                "YouTube yêu cầu xác minh tài khoản (Sign in to confirm you're not a bot). "
                "Vui lòng nạp lại file cookies.txt mới từ trình duyệt để tải video này!"
            ) from e
        raise RuntimeError(err_msg) from e

    if not out_p.exists() or out_p.stat().st_size < MIN_VALID_CLIP_BYTES:
        if out_p.exists():
            try:
                out_p.unlink()
            except Exception:
                pass
        raise RuntimeError(f"Tải đoạn clip YouTube thất bại hoặc file không hợp lệ: {url}")

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

    # Identical src and dst: already at target location
    try:
        if src.resolve() == dst.resolve() and dst.exists() and dst.stat().st_size >= 512:
            return dst
    except Exception:
        pass

    # Fast path: stream copy without re-encoding when importing full clip from start
    is_full_import = (start_sec == 0.0) and (vid_dur <= 0.0 or duration >= vid_dur - 1.0)
    if is_full_import:
        cmd_copy = [
            FFMPEG, "-y",
            "-i", str(src),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(dst),
        ]
        try:
            r_copy = subprocess.run(
                cmd_copy, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=max(60, int(duration * 0.5)),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if r_copy.returncode == 0 and dst.exists() and dst.stat().st_size >= 512:
                mb = dst.stat().st_size / 1_048_576
                log.ok(f"Raw cut (stream copy) saved: {dst.name} ({mb:.2f} MB)")
                return dst
        except Exception:
            pass

    gpu_timeout = max(120, int(duration * 1.5))
    cpu_timeout = max(180, int(duration * 3.5))

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
                encoding="utf-8", errors="replace", timeout=gpu_timeout,
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
            encoding="utf-8", errors="replace", timeout=cpu_timeout,
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

    # ── Exact lines: use title_lines from preview if provided AND matches title, else wrap dynamically ───
    clean_title = " ".join(title.lower().split())
    lines_match = bool(
        title_lines and len(title_lines) > 0 and
        " ".join(" ".join(str(l) for l in title_lines).lower().split()) == clean_title
    )
    if lines_match:
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
    _uid = uuid.uuid4().hex[:10]
    tmp = Path(tempfile.gettempdir()) / f"reup_title_{_uid}.png"
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

    if not clip.exists() or clip.stat().st_size < 10240:
        raise RuntimeError(f"File video nguồn rỗng hoặc không tồn tại ({clip.name}, dung lượng {clip.stat().st_size if clip.exists() else 0} bytes)")

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

        # Sort words by start time and sanitize acoustic overlapping timestamps
        all_words.sort(key=lambda w: float(w.get("start", 0.0)))
        for i in range(len(all_words) - 1):
            if all_words[i]["end"] > all_words[i+1]["start"]:
                mid = round((all_words[i]["end"] + all_words[i+1]["start"]) / 2.0, 3)
                all_words[i]["end"] = max(all_words[i]["start"] + 0.03, mid)
                all_words[i+1]["start"] = max(all_words[i]["end"], all_words[i+1]["start"])
                all_words[i+1]["end"] = max(all_words[i+1]["start"] + 0.04, all_words[i+1]["end"])

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
        cues_to_write = []
        i = 0
        n = len(all_words)
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
            cues_to_write.append({
                "start": group[0]["start"],
                "end": max(group[0]["start"] + 0.1, group[-1]["end"]),
                "text": text
            })

        # Sanitize cues so cue[i].end <= cue[i+1].start (no timeline overlap)
        for i in range(len(cues_to_write) - 1):
            if cues_to_write[i]["end"] > cues_to_write[i+1]["start"]:
                cues_to_write[i]["end"] = cues_to_write[i+1]["start"]

        with open(srt_p, "w", encoding="utf-8") as f:
            for cue_idx, c in enumerate(cues_to_write, 1):
                f.write(f"{cue_idx}\n")
                f.write(f"{_fmt(c['start'])} --> {_fmt(c['end'])}\n")
                f.write(f"{c['text']}\n\n")

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
                    # Sanitize acoustic word timestamps so no two words overlap
                    real_words.sort(key=lambda w: float(w["start"]))
                    for i in range(len(real_words) - 1):
                        if real_words[i]["end"] > real_words[i+1]["start"]:
                            mid = round((real_words[i]["end"] + real_words[i+1]["start"]) / 2.0, 3)
                            real_words[i]["end"] = max(real_words[i]["start"] + 0.03, mid)
                            real_words[i+1]["start"] = max(real_words[i]["end"], real_words[i+1]["start"])
                            real_words[i+1]["end"] = max(real_words[i+1]["start"] + 0.04, real_words[i+1]["end"])
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
        raw_events = []
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
            raw_events.append({"start": ws, "end": we, "tag": bounce_tag, "text": wt})

        # Strict De-overlap so consecutive word pop events never overlap on screen
        raw_events.sort(key=lambda ev: ev["start"])
        for i in range(len(raw_events) - 1):
            if raw_events[i]["end"] > raw_events[i + 1]["start"]:
                raw_events[i]["end"] = raw_events[i + 1]["start"]

        for ev in raw_events:
            if ev["end"] > ev["start"] + 0.03:
                ass_buf.append(
                    f"Dialogue: 0,{_to_ass_ts(ev['start'])},{_to_ass_ts(ev['end'])},WordPop,,0,0,0,,{_sub_pos}{ev['tag']}{ev['text']}"
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

        # Partition real_words into srt_cues strictly by midpoint boundaries between adjacent cues
        cue_word_map: list[list[dict]] = [[] for _ in srt_cues]
        if real_words:
            boundaries = [
                (srt_cues[i]["end"] + srt_cues[i + 1]["start"]) / 2.0
                for i in range(len(srt_cues) - 1)
            ]
            for w in real_words:
                w_mid = (w["start"] + w["end"]) / 2.0
                idx = 0
                while idx < len(boundaries) and w_mid >= boundaries[idx]:
                    idx += 1
                cue_word_map[idx].append(w)

        MAX_WORDS_PER_LINE = 5  # max words shown at once on screen
        raw_karaoke_dialogues = []

        for ci, cue in enumerate(srt_cues):
            c_start = max(0.0, cue["start"] + _offset_s)
            c_end   = max(0.0, cue["end"]   + _offset_s)
            if c_end <= c_start:
                continue

            cue_words = cue_word_map[ci] if real_words else []
            if not cue_words:
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

                raw_karaoke_dialogues.append({
                    "start": grp_start,
                    "end": grp_end,
                    "grp": grp,
                })

        # Strict De-overlap: clamp any overlapping dialogue end times to the next dialogue start
        raw_karaoke_dialogues.sort(key=lambda d: d["start"])
        for i in range(len(raw_karaoke_dialogues) - 1):
            if raw_karaoke_dialogues[i]["end"] > raw_karaoke_dialogues[i + 1]["start"]:
                raw_karaoke_dialogues[i]["end"] = raw_karaoke_dialogues[i + 1]["start"]

        for d in raw_karaoke_dialogues:
            grp_start = d["start"]
            grp_end   = d["end"]
            grp       = d["grp"]
            if grp_end <= grp_start + 0.04:
                continue

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

        raw_normal_dialogues = []
        for cue in cues:
            s   = max(0.0, cue["start"] + _offset_s)
            e   = max(0.0, cue["end"]   + _offset_s)
            if e <= s:
                continue
            txt_raw = cue["text"].upper() if _sub_uppercase else cue["text"]
            txt = _esc_ass_n(txt_raw)
            raw_normal_dialogues.append({"start": s, "end": e, "text": txt})

        raw_normal_dialogues.sort(key=lambda d: d["start"])
        for i in range(len(raw_normal_dialogues) - 1):
            if raw_normal_dialogues[i]["end"] > raw_normal_dialogues[i + 1]["start"]:
                raw_normal_dialogues[i]["end"] = raw_normal_dialogues[i + 1]["start"]

        for d in raw_normal_dialogues:
            if d["end"] > d["start"] + 0.04:
                _normal_ass.append(
                    f"Dialogue: 0,{_to_ass_ts_n(d['start'])},{_to_ass_ts_n(d['end'])},"
                    f"Normal,,0,0,0,,{_sub_pos}{d['text']}"
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
    if not clip.exists() or clip.stat().st_size < 10240:
        raise RuntimeError(f"File video nguồn rỗng hoặc không tồn tại ({clip.name}, dung lượng {clip.stat().st_size if clip.exists() else 0} bytes). Vui lòng cắt/tải lại clip này!")

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

    # ── 3b. Freeform Custom Text Layers (Timed Browser PNGs or PIL Fallback) ──
    _pil_custom_txt_pngs: list[Path] = []
    _timed_pngs = list(st.get("_timed_text_pngs") or [])

    if not _browser_overlay and st.get("custom_texts"):
        for _ct in st.get("custom_texts", []):
            if not isinstance(_ct, dict) or _ct.get("enabled") is False:
                continue
            _ct_raw = str(_ct.get("text") or "").strip()
            if not _ct_raw:
                continue
            _ct_txt = _ct_raw.upper() if _ct.get("uppercase", False) else _ct_raw
            _ct_box_mode = _ct.get("box_mode", "frame")
            _ct_opacity = 0 if _ct_box_mode == "none" else int(_ct.get("box_opacity", 90))
            _ct_img = _make_title_image(
                _ct_txt,
                font_name        = _ct.get("font_name", "impact"),
                font_size        = int(_ct.get("font_size", 40)),
                text_color       = "custom",
                text_bg          = "box" if _ct_opacity > 0 else "none",
                text_x           = int(_ct.get("x", 0)),
                text_y           = int(_ct.get("y", 1290)),
                text_align       = _ct.get("text_align", "center"),
                title_wrap_pct   = float(_ct.get("wrap_pct", 0.78)),
                box_radius       = int(_ct.get("box_radius", 16)),
                box_mode         = "frame" if _ct_box_mode == "none" else _ct_box_mode,
                box_bg_color     = "custom",
                box_bg_color_hex = _ct.get("box_bg_color_hex", "#000000"),
                box_opacity      = _ct_opacity,
                font_bold        = bool(_ct.get("font_bold", True)),
                letter_spacing   = int(_ct.get("letter_spacing", 0)),
                line_height      = float(_ct.get("line_height", 1.2)),
                font_italic      = bool(_ct.get("font_italic", False)),
                text_opacity     = int(_ct.get("text_opacity", 100)),
                text_rotation    = float(_ct.get("rotation", 0.0)),
                text_color_hex   = _ct.get("text_color_hex", "#ffffff"),
                stroke_width     = int(_ct.get("stroke_width", 2)),
                stroke_color_hex = _ct.get("stroke_color_hex", "#000000"),
                stroke_enabled   = bool(_ct.get("stroke_enabled", True)),
            )
            if _ct_img and _ct_img.exists():
                _pil_custom_txt_pngs.append(_ct_img)
                _timed_pngs.append({
                    "path": str(_ct_img),
                    "start_time": float(_ct.get("start_time", 0.0) or 0.0),
                    "end_time": float(_ct.get("end_time", 0.0) or 0.0),
                })

    for _ti, _tp_info in enumerate(_timed_pngs):
        _tp_path = Path(str(_tp_info.get("path", "")))
        if not _tp_path.exists():
            continue
        _tst = float(_tp_info.get("start_time", 0.0) or 0.0)
        _ted = float(_tp_info.get("end_time", 0.0) or 0.0)
        _en_expr = ""
        if _tst > 0.01 or _ted > 0.01:
            if _ted > _tst + 0.01:
                _en_expr = f":enable='between(t,{_tst:.3f},{_ted:.3f})'"
            else:
                _en_expr = f":enable='gte(t,{_tst:.3f})'"
        inputs += ["-thread_queue_size", "512", "-i", str(_tp_path)]
        _ct_tag = f"comp_ctxt_{_ti}"
        parts.append(f"[{current}][{inp_idx}:v]overlay=0:0{_en_expr}:format=auto:eof_action=repeat[{_ct_tag}]")
        current = _ct_tag
        inp_idx += 1

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
    for _ptp in _pil_custom_txt_pngs:
        try:
            _ptp.unlink(missing_ok=True)
        except Exception:
            pass

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
# Lazy Tkinter GUI Delegation (legacy/desktop_gui.py)
# ──────────────────────────────────────────────────────────────────────────────
_TK_GUI_SYMBOLS = {
    'ToolTip', 'Toast', 'PremiumScale', 'AccentButton', 'SecondaryButton',
    'DangerButton', 'SuccessButton', 'SectionCard', 'PLAYBACK_FPS', 'PLAYBACK_VF',
    'VideoPlayer', 'CliperApp',
}

def __getattr__(name: str):
    if name in _TK_GUI_SYMBOLS:
        from legacy import desktop_gui
        return getattr(desktop_gui, name)
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    from legacy.desktop_gui import CliperApp
    app = CliperApp()
    app.mainloop()
