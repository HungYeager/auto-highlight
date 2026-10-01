# -*- coding: utf-8 -*-
"""
FastAPI Backend Engine for OpenCut-Style Web Studio
===================================================
"""

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

# In windowless GUI mode (PyInstaller console=False on packaged client machines),
# sys.stdout and sys.stderr are None. We wrap them safely to prevent any print() or
# logging calls from raising AttributeError: 'NoneType' object has no attribute 'write'.
class _SafeStream:
    def __init__(self, log_path=None):
        self._f = None
        if log_path:
            try:
                self._f = open(log_path, "a", encoding="utf-8", errors="replace")
            except Exception:
                self._f = None

    def write(self, s):
        if self._f:
            try:
                self._f.write(s)
                self._f.flush()
            except Exception:
                pass

    def flush(self):
        if self._f:
            try:
                self._f.flush()
            except Exception:
                pass

    def isatty(self):
        return False

if sys.stdout is None or sys.stderr is None:
    import tempfile
    _log_path = os.path.join(tempfile.gettempdir(), "opencutstudio.log")
    if sys.stdout is None:
        sys.stdout = _SafeStream(_log_path)
    if sys.stderr is None:
        sys.stderr = _SafeStream(_log_path)

# Force UTF-8 output on Windows to prevent 'charmap codec can't encode' errors
# when filenames or log messages contain Vietnamese / Unicode characters.
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

import cv2
import numpy as np

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, UploadFile, File, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Import all top-level processing functions from app.py (no Tkinter class dependency)
from app import (
    CONFIG_FILE, MODEL_NAME, CLIP_DURATION, MIN_STORY_DUR, MAX_STORY_DUR,
    FFMPEG, FFPROBE,
    AVAILABLE_ENCODERS, BEST_ENCODER, KeyRotator, ToolLogger,
    get_video_duration, get_video_width, get_video_height,
    upload_video, analyze_video, delete_remote,
    _make_title_image, render_reup, _downsample_for_upload,
    _reinterpret_mmss, ts_to_seconds, build_client,
    cut_clip_exact, _default_edit_state, sanitize,
    _gemini_transcribe, _whisper_transcribe,
    detect_logo_bbox, detect_subtitle_region, auto_detect_subtitle_tracks,
    get_ocr_device,
    map_canvas_box_to_orig_video, map_tracked_box_to_canvas, inpaint_video_region,
    ST_QUEUED, ST_UPLOADING, ST_ANALYZING, ST_DONE, ST_ERROR,
    get_youtube_info, download_youtube_section, get_yt_cookie_file,
)
try:
    from app import _probe_encoders as _probe_hw_encoders
except ImportError:
    _probe_hw_encoders = None

def _run_encoder_probe_and_apply():
    """Run GPU encoder probe in background, then auto-apply best encoder to config."""
    import app as _app
    if _probe_hw_encoders:
        _probe_hw_encoders()  # updates _app.AVAILABLE_ENCODERS + _app.BEST_ENCODER
    best = _app.BEST_ENCODER
    # Only upgrade — never downgrade a user's explicit choice
    current = app_state.config.get("export_encoder", "libx264")
    if current == "libx264" and best != "libx264":
        app_state.config["export_encoder"] = best
        app_state.save_config()
        print(f"[INFO] GPU encoder auto-selected: {best}", flush=True)

# Run probe once at startup in daemon thread — takes ~1-2s per HW encoder tested
threading.Thread(target=_run_encoder_probe_and_apply, daemon=True).start()
try:
    from app import WHISPER_AVAILABLE
except ImportError:
    WHISPER_AVAILABLE = False
import tempfile
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Suppress WinError 10054 (ConnectionResetError) from Windows asyncio ProactorEventLoop
    import platform
    if platform.system() == "Windows":
        loop = asyncio.get_running_loop()
        _original = loop.default_exception_handler
        def _handler(loop, context):
            exc = context.get("exception")
            if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
                return
            _original(context)
        loop.set_exception_handler(_handler)
    yield

app = FastAPI(title="Viral Bodycam Clipper Engine", version="2.9.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global Application State ──────────────────────────────────────────────────
# RLock (reentrant) prevents deadlock when save_config() is called while
# Lock for app_state operations
STATE_LOCK = threading.RLock()
# Dedicated Lock for logs array — separates log reads/writes from STATE_LOCK so polling /api/logs never blocks
LOG_LOCK = threading.Lock()

# ── Suppress noisy-but-harmless uvicorn WebSocket close-frame errors ──────────
# When a browser tab closes/refreshes, the TCP connection drops before uvicorn
# can send the WebSocket close frame → "socket.send() raised exception."
# This is expected and harmless; the filter keeps the console clean.
import logging as _logging

class _SuppressSocketSend(_logging.Filter):
    def filter(self, record):
        return "socket.send() raised exception" not in record.getMessage()

_logging.getLogger("uvicorn.error").addFilter(_SuppressSocketSend())

# ── Preview cache (LRU with size-capped eviction) ─────────────────────────────
# Maps "path|start_sec" → Path of pre-cut mp4 in temp dir.
# Evicted when entries > _PREVIEW_CACHE_MAX_ENTRIES  OR
#                 bytes  > _PREVIEW_CACHE_MAX_BYTES  (whichever triggers first).
from collections import OrderedDict as _ODict
_PREVIEW_CACHE: "_ODict[str, Path]" = _ODict()
_PREVIEW_CACHE_LOCK = threading.Lock()
_PREVIEW_DIR = Path(tempfile.gettempdir()) / "clipper_previews"
_PREVIEW_DIR.mkdir(exist_ok=True)

_PREVIEW_CACHE_MAX_ENTRIES = 500
_PREVIEW_CACHE_MAX_BYTES   = 1 * 1024 ** 3   # 1 GB

def _preview_cache_insert(key: str, path: "Path") -> None:
    """Insert *key → path* into the LRU cache and evict oldest entries if over limits.

    Must be called while holding *_PREVIEW_CACHE_LOCK*.
    """
    _PREVIEW_CACHE[key] = path
    _PREVIEW_CACHE.move_to_end(key)           # mark as most-recently-used

    # Evict until both constraints satisfied
    while True:
        if len(_PREVIEW_CACHE) <= _PREVIEW_CACHE_MAX_ENTRIES:
            # Check byte usage only when entry count is fine
            try:
                total = sum(
                    p.stat().st_size for p in _PREVIEW_CACHE.values() if p.exists()
                )
            except Exception:
                total = 0
            if total <= _PREVIEW_CACHE_MAX_BYTES:
                break
        # Pop the least-recently-used (oldest) entry
        oldest_key, oldest_path = _PREVIEW_CACHE.popitem(last=False)
        try:
            oldest_path.unlink(missing_ok=True)
        except Exception:
            pass


# ── Thumbnail cache ────────────────────────────────────────────────────────────
# Maps "path|start_sec" → Path of JPEG thumbnail for that candidate.
# Generated in background after precut succeeds. Served by /api/clip/thumbnail.
_THUMBNAIL_CACHE: "_ODict[str, Path]" = _ODict()
_THUMBNAIL_CACHE_LOCK = threading.Lock()
_THUMBNAIL_DIR = _PREVIEW_DIR / "thumbs"
_THUMBNAIL_DIR.mkdir(exist_ok=True)


# Single worker = at most ONE IDLE-priority FFmpeg precut process at any time,
# no matter how many videos were just analyzed.
# Problem it solves: 21 videos → 21 threads → 21 concurrent IDLE FFmpeg processes
# all reading 21 large files simultaneously → disk I/O saturated → even ABOVE_NORMAL
# stream_preview FFmpeg must wait.
# With max_workers=1: background precut is strictly serialized globally; preview
# FFmpeg (ABOVE_NORMAL, zero contention) always gets disk I/O first.
_BG_PRECUT_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bg_precut")

SESSION_FILE = Path(CONFIG_FILE).parent / "session_data.json"

class AppState:
    def __init__(self):
        self.config: Dict[str, Any] = self.load_config()
        self.video_files: List[Any] = []
        for f in self.config.get("video_files", []):
            if isinstance(f, str) and (f.startswith("http://") or f.startswith("https://")):
                self.video_files.append(f)
            elif Path(f).exists():
                self.video_files.append(Path(f))
        self.yt_metadata: Dict[str, Dict[str, Any]] = {}
        self.video_results: Dict[str, Dict[str, Any]] = {}
        self.is_analyzing: bool = False
        self.stop_event: threading.Event = threading.Event()
        # Separate event so stopping export never interferes with analysis
        self.export_cancel_event: threading.Event = threading.Event()
        self.export_progress: Dict[str, Any] = {"status": "idle", "completed": 0, "total": 0, "current": ""}
        # Persistent KeyRotator shared across all Gemini calls (title regen, transcription, etc.)
        self._key_rotator: Optional[Any] = None
        self._rotator_keys: List[str] = []
        self.frame_cache: Dict[str, Image.Image] = {}
        self.bg_cache: Dict[tuple, Image.Image] = {}
        self.logs: List[Dict[str, str]] = []
        self.ws_clients: List[WebSocket] = []
        # Batches & Session: multi-batch workspace
        self.batches: Dict[str, Dict[str, Any]] = {}
        self.active_batch_id: str = "default"
        self.load_session()

    @property
    def edit_queue(self) -> List[Dict[str, Any]]:
        with STATE_LOCK:
            if not self.batches:
                self.batches = {
                    "default": {
                        "id": "default",
                        "name": "Cụm 1",
                        "output_folder": self.config.get("output_folder", str(Path.home() / "Videos" / "Clipper_Outputs")),
                        "items": []
                    }
                }
                self.active_batch_id = "default"
            elif self.active_batch_id not in self.batches:
                self.active_batch_id = next(iter(self.batches.keys()))
            return self.batches[self.active_batch_id].setdefault("items", [])

    @edit_queue.setter
    def edit_queue(self, val: List[Dict[str, Any]]):
        with STATE_LOCK:
            if not self.batches or self.active_batch_id not in self.batches:
                self.batches = {
                    "default": {
                        "id": "default",
                        "name": "Cụm 1",
                        "output_folder": self.config.get("output_folder", str(Path.home() / "Videos" / "Clipper_Outputs")),
                        "items": []
                    }
                }
                self.active_batch_id = "default"
            self.batches[self.active_batch_id]["items"] = list(val)
        self.save_session()

    def get_current_output_folder(self, batch_id: Optional[str] = None) -> str:
        b_id = batch_id or self.active_batch_id
        folder = None
        if b_id in self.batches and self.batches[b_id].get("output_folder"):
            folder = self.batches[b_id]["output_folder"]
        if not folder:
            folder = self.config.get("output_folder", "")
        if folder and str(folder).strip():
            try:
                p = Path(str(folder).strip())
                p.mkdir(parents=True, exist_ok=True)
                return str(p)
            except Exception:
                pass
        fallback = Path.cwd() / "output_clips"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            return str(fallback)
        except Exception:
            return str(Path.home() / "Videos" / "Clipper_Outputs")

    def create_batch(self, name: str = "Cụm mới", output_folder: Optional[str] = None) -> str:
        with STATE_LOCK:
            existing_nums = []
            for k in self.batches.keys():
                if k.startswith("batch_"):
                    try:
                        existing_nums.append(int(k.split("_")[1]))
                    except (ValueError, IndexError):
                        pass
                elif k == "default":
                    existing_nums.append(1)
            next_num = max(existing_nums, default=len(self.batches)) + 1
            new_id = f"batch_{next_num}"
            while new_id in self.batches:
                next_num += 1
                new_id = f"batch_{next_num}"

            default_folder = self.config.get("output_folder", str(Path.home() / "Videos" / "Clipper_Outputs"))
            folder = output_folder.strip() if (output_folder and output_folder.strip()) else default_folder

            self.batches[new_id] = {
                "id": new_id,
                "name": name.strip() or f"Cụm {next_num}",
                "output_folder": folder,
                "items": []
            }
            self.active_batch_id = new_id
            self.save_session()
            return new_id

    def switch_batch(self, batch_id: str) -> bool:
        with STATE_LOCK:
            if batch_id not in self.batches:
                return False
            self.active_batch_id = batch_id
            self.save_session()
            return True

    def delete_batch(self, batch_id: str) -> bool:
        with STATE_LOCK:
            if batch_id not in self.batches:
                return False
            if len(self.batches) <= 1:
                return False
            del self.batches[batch_id]
            if self.active_batch_id == batch_id:
                self.active_batch_id = next(iter(self.batches.keys()))
            self.save_session()
            return True

    def save_session(self):
        try:
            with STATE_LOCK:
                data = {
                    "version": 1,
                    "active_batch_id": self.active_batch_id,
                    "batches": self.batches,
                    "video_results": self.video_results,
                    "yt_metadata": getattr(self, "yt_metadata", {}),
                }
            tmp_file = Path(SESSION_FILE).with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp_file.replace(SESSION_FILE)
        except Exception as e:
            print(f"[AppState] Error saving session: {e}", flush=True)

    def load_session(self):
        default_folder = self.config.get("output_folder", str(Path.home() / "Videos" / "Clipper_Outputs"))
        if not os.path.exists(SESSION_FILE):
            self.batches = {
                "default": {
                    "id": "default",
                    "name": "Cụm 1",
                    "output_folder": default_folder,
                    "items": []
                }
            }
            self.active_batch_id = "default"
            return

        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.video_results = data.get("video_results", {})
                self.yt_metadata = data.get("yt_metadata", {})
                self.batches = data.get("batches", {})
                self.active_batch_id = data.get("active_batch_id", "default")
                if not self.batches:
                    self.batches = {
                        "default": {
                            "id": "default",
                            "name": "Cụm 1",
                            "output_folder": default_folder,
                            "items": []
                        }
                    }
                    self.active_batch_id = "default"
                elif self.active_batch_id not in self.batches:
                    self.active_batch_id = next(iter(self.batches.keys()))
            print(f"[AppState] Loaded session: {len(self.video_results)} videos, {len(self.batches)} batches", flush=True)
        except Exception as e:
            print(f"[AppState] Error loading session: {e}", flush=True)
            self.batches = {
                "default": {
                    "id": "default",
                    "name": "Cụm 1",
                    "output_folder": default_folder,
                    "items": []
                }
            }
            self.active_batch_id = "default"

    def load_config(self) -> Dict[str, Any]:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "api_keys": [""],
            "output_folder": str(Path.home() / "Videos" / "Clipper_Outputs"),
            "video_files": [],
            "model_name": MODEL_NAME,
            "analysis_parallel": 3,
            "export_threads": 2,
            "export_crf": 20,
            "export_preset": "medium",
            "export_encoder": "libx264",
            "box_bg_color_hex": "#222222",
            "source_mask_top": 0.0,
            "source_mask_bottom": 0.0,
            "source_mask_mode": "top",
            "direct_import_gen_title": True,
            "auto_clean_temp": True,
        }

    def save_config(self):
        with STATE_LOCK:
            self.config["video_files"] = [str(p) for p in self.video_files]
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Error saving config: {e}")

    def get_rotator(self) -> Any:
        """Returns/refreshes the shared KeyRotator when API keys change.
        Uses least-connections + cooldown rotation (same as analysis threads)."""
        keys = [k.strip() for k in self.config.get("api_keys", []) if k.strip()]
        if not keys:
            raise ValueError("No API keys configured")
        if self._key_rotator is None or self._rotator_keys != keys:
            self._key_rotator = KeyRotator(keys)
            self._rotator_keys = list(keys)
        return self._key_rotator

    def log(self, text: str, level: str = "info"):
        # Encode-safe: replace any char that Windows cp1252 can't handle
        safe_text = text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        entry = {"timestamp": datetime_now_str(), "text": safe_text, "level": level}
        with LOG_LOCK:
            self.logs.append(entry)
            if len(self.logs) > 500:
                self.logs.pop(0)
        try:
            print(f"[{level.upper()}] {safe_text}", flush=True)
        except Exception:
            pass  # Never let a log call crash the server
        # Push log to SSE clients (set after _sse_bus is initialized)
        _notify = getattr(self, '_sse_notify', None)
        if _notify:
            try:
                _notify('log', {'text': safe_text, 'level': level, 'ts': datetime_now_str()})
            except Exception:
                pass


def datetime_now_str() -> str:
    return time.strftime("%H:%M:%S")

app_state = AppState()

# WebSocket Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

# ── SSE Event Bus ─────────────────────────────────────────────────────────────
# Thread-safe broadcast bus: worker threads (sync) push events;
# async SSE endpoint drains per-client queues at 50ms cadence.
import queue as _stdlib_queue

class _SSEBus:
    """Thread-safe SSE broadcast bus.

    Any thread calls push(event_type, data). Each connected SSE client
    has its own SimpleQueue that gets a copy of every event.
    The async generator in /api/events drains the queue without blocking.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._queues: List[_stdlib_queue.SimpleQueue] = []

    def subscribe(self) -> _stdlib_queue.SimpleQueue:
        q: _stdlib_queue.SimpleQueue = _stdlib_queue.SimpleQueue()
        with self._lock:
            self._queues.append(q)
        return q

    def unsubscribe(self, q: _stdlib_queue.SimpleQueue) -> None:
        with self._lock:
            try:
                self._queues.remove(q)
            except ValueError:
                pass

    def push(self, event_type: str, data: dict | None = None) -> None:
        msg = json.dumps({"type": event_type, "data": data or {}, "ts": time.time()})
        with self._lock:
            for q in list(self._queues):
                try:
                    q.put_nowait(msg)
                except Exception:
                    pass

_sse_bus = _SSEBus()
# Wire SSE bus into app_state so log() can push events
app_state._sse_notify = _sse_bus.push

# ── API Models ────────────────────────────────────────────────────────────────
class ConfigModel(BaseModel):
    api_keys: Optional[List[str]] = None
    output_folder: Optional[str] = None
    model_name: Optional[str] = None
    include_cta: Optional[bool] = None
    title_prompt: Optional[str] = None  # custom prompt template; None = use default
    export_threads: Optional[int] = 2
    export_crf: Optional[int] = 20
    export_preset: Optional[str] = "medium"
    export_encoder: Optional[str] = "libx264"
    box_bg_color_hex: Optional[str] = "#222222"
    source_mask_top: Optional[float] = 0.0
    source_mask_bottom: Optional[float] = 0.0
    source_mask_mode: Optional[str] = "top"
    direct_import_gen_title: Optional[bool] = True
    auto_clean_temp: Optional[bool] = True
    analysis_parallel: Optional[int] = None   # concurrent analysis streams (1-10)
    video_files: Optional[List[str]] = None

class VideoAddRequest(BaseModel):
    paths: List[str]

class PreviewRequest(BaseModel):
    clip_path: str
    title: str = "POLICE OFFICER EXPOSES TRUTH!"
    width: int = 378
    height: int = 672
    state: Dict[str, Any] = {}
    no_title: bool = False  # when True, skip title render — frontend renders it via HTML


class ExportRequest(BaseModel):
    selected_videos: List[str]
    threads: int = 2
    crf: int = 20
    preset: str = "fast"
    encoder: str = "libx264"
    resolution: str = "1080x1920"
    fps: Optional[int] = None
    state: Dict[str, Any] = {}


# ── REST Endpoints ────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    return app_state.config

@app.post("/api/config")
def update_config(cfg: ConfigModel):
    with STATE_LOCK:
        data = cfg.model_dump(exclude_unset=True) if hasattr(cfg, "model_dump") else cfg.dict(exclude_unset=True)
        for k, v in data.items():
            if v is not None:
                app_state.config[k] = v
        # Only overwrite video list when explicitly provided AND non-empty.
        # Prevents accidental reset when frontend config sync omits the field.
        if cfg.video_files is not None and len(cfg.video_files) > 0:
            app_state.video_files = [
                p if isinstance(p, str) and (p.startswith("http://") or p.startswith("https://"))
                else Path(p) for p in cfg.video_files if (isinstance(p, str) and (p.startswith("http://") or p.startswith("https://"))) or Path(p).exists()
            ]
        app_state.save_config()
    return {"status": "ok", "config": app_state.config}

def _norm_path(p: Any) -> str:
    """Canonical normalized path string to prevent slash/backslash mismatch bugs."""
    if not p:
        return ""
    s = str(p).strip()
    if s.startswith(("http://", "https://")):
        return s
    try:
        return str(Path(p).resolve())
    except Exception:
        return s

def _get_video_result(p: Any) -> dict:
    """Safely find analysis results by normalized path, raw string, or filename match."""
    if not p:
        return {}
    norm_k = _norm_path(p)
    str_k = str(p)
    if norm_k in app_state.video_results:
        return app_state.video_results[norm_k]
    if str_k in app_state.video_results:
        return app_state.video_results[str_k]
    try:
        p_name = Path(p).name
        for k, v in app_state.video_results.items():
            if Path(k).name == p_name:
                return v
    except Exception:
        pass
    return {}

@app.get("/api/videos")
def list_videos():
    res = []
    for p in app_state.video_files:
        is_yt = isinstance(p, str) and (p.startswith("http://") or p.startswith("https://"))
        if is_yt:
            norm_k = p.strip()
            status_info = _get_video_result(norm_k) or {"status": ST_QUEUED, "candidates": []}
            yt_meta = getattr(app_state, "yt_metadata", {}).get(norm_k, {})
            title = yt_meta.get("title") or "YouTube Video"
            dur = yt_meta.get("duration") or 0
            thumb = yt_meta.get("thumbnail") or ""
            res.append({
                "path": norm_k,
                "name": title,
                "is_youtube": True,
                "exists": True,
                "duration": dur,
                "width": 1920,
                "height": 1080,
                "thumbnail": thumb,
                "status": status_info.get("status", ST_QUEUED),
                "candidates": status_info.get("candidates", []),
                "error": status_info.get("error", ""),
            })
        else:
            p_obj = Path(p) if not isinstance(p, Path) else p
            status_info = _get_video_result(p_obj) or {"status": ST_QUEUED, "candidates": []}
            dur = get_video_duration(p_obj) or 0
            w = get_video_width(p_obj)
            h = get_video_height(p_obj)
            res.append({
                "path": str(p_obj),
                "name": p_obj.name,
                "is_youtube": False,
                "exists": p_obj.exists(),
                "duration": dur,
                "width": w,
                "height": h,
                "thumbnail": "",
                "status": status_info.get("status", ST_QUEUED),
                "candidates": status_info.get("candidates", []),
                "error": status_info.get("error", ""),
            })
    return {"videos": res, "is_analyzing": app_state.is_analyzing}

@app.post("/api/videos/add")
def add_videos(req: VideoAddRequest):
    added = []
    existing = {str(p.resolve()) if hasattr(p, "resolve") else str(p) for p in app_state.video_files}
    for p_str in req.paths:
        if p_str.startswith(("http://", "https://")):
            if p_str not in existing:
                app_state.video_files.append(p_str)
                added.append(p_str)
                existing.add(p_str)
        else:
            p = _safe_resolve_path(p_str)
            if p and p.exists() and str(p.resolve()) not in existing:
                app_state.video_files.append(p)
                added.append(str(p))
                existing.add(str(p.resolve()))
    app_state.save_config()
    return {"status": "ok", "added": added, "total": len(app_state.video_files)}

@app.post("/api/videos/remove")
def remove_video(req: Dict[str, str]):
    target = req.get("path")
    if target:
        app_state.video_files = [p for p in app_state.video_files if str(p) != target]
        if target in app_state.video_results:
            del app_state.video_results[target]
        app_state.save_config()
        app_state.save_session()
    return {"status": "ok", "total": len(app_state.video_files)}

@app.post("/api/videos/clear")
def clear_videos():
    app_state.video_files = []
    app_state.video_results = {}
    app_state.save_config()
    app_state.save_session()
    return {"status": "ok"}

def _run_analysis_worker(video_path: Path):
    """Background worker for re-analyzing a single video."""
    keys = app_state.config.get("api_keys", [])
    if not keys:
        app_state.log(f"❌ Không có API key nào để phân tích lại {video_path.name}", "err")
        norm_k = _norm_path(video_path)
        with STATE_LOCK:
            app_state.video_results[norm_k] = {
                "status": ST_ERROR, "candidates": [], "error": "Chưa nhập API key"
            }
        _sse_bus.push("videos_changed", {"path": str(video_path), "status": ST_ERROR})
        return

    model_name = app_state.config.get("model_name", "gemini-3.5-flash-lite")
    include_cta = bool(app_state.config.get("include_cta", False))
    mode = app_state.config.get("analysis_mode", "short")
    _run_bulk_analysis_thread(
        keys=keys,
        videos=[video_path],
        model_name=model_name,
        include_cta=include_cta,
        mode=mode,
    )


@app.post("/api/videos/reanalyze")
def reanalyze_video(req: Dict[str, str], background_tasks: BackgroundTasks):
    target = req.get("path")
    if not target:
        raise HTTPException(status_code=400, detail="Missing video path")

    if target.startswith(("http://", "https://")):
        with STATE_LOCK:
            app_state.video_results[target] = {
                "status": ST_QUEUED, "candidates": [], "error": ""
            }
            app_state.save_session()
        _sse_bus.push("videos_changed", {"path": target, "status": ST_QUEUED})
        app_state.log(f"🔄 Yêu cầu phân tích lại YouTube: {target}", "info")
        background_tasks.add_task(_run_analysis_worker, target)
        return {"status": "ok", "message": "Queued re-analysis for YouTube video"}

    p = _safe_resolve_path(target)
    if not p or not p.exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    norm_k = _norm_path(p)
    with STATE_LOCK:
        app_state.video_results[norm_k] = {
            "status": ST_QUEUED, "candidates": [], "error": ""
        }
        app_state.save_session()

    _sse_bus.push("videos_changed", {"path": str(p), "status": ST_QUEUED})
    app_state.log(f"🔄 Yêu cầu phân tích lại: {p.name}", "info")
    background_tasks.add_task(_run_analysis_worker, p)
    return {"status": "ok", "message": f"Queued re-analysis for {p.name}"}

@app.get("/api/fonts")
def list_fonts():
    fonts = set()
    font_dir = Path("C:/Windows/Fonts")
    if font_dir.exists():
        for f in font_dir.glob("*.[tT][tT][fF]"):
            name = f.stem
            clean_name = re.sub(r"(bd|b|i|bi|italic|bold)$", "", name, flags=re.I).strip()
            if clean_name:
                fonts.add(clean_name)
    sorted_fonts = sorted(list(fonts))
    default_favs = ["Impact", "Arial Black", "Montserrat", "Outfit", "Roboto", "Segoe UI", "Tahoma", "Verdana"]
    return {"fonts": sorted_fonts, "recommended": [f for f in default_favs if any(f.lower() in sf.lower() for sf in sorted_fonts)]}


# Bundled curated fonts — always available regardless of Windows font installation
_BUNDLED_FONTS: list[dict] = [
    {"key": "montserrat",      "label": "Montserrat",       "file": "Montserrat-Bold.ttf",       "style": "Sans-Serif Bold"},
    {"key": "luckiestguy",     "label": "Luckiest Guy",     "file": "LuckiestGuy-Regular.ttf",   "style": "Display / Cartoon"},
    {"key": "nunito",          "label": "Futura (Nunito)",  "file": "Nunito-ExtraBold.ttf",       "style": "Geometric Sans"},
    {"key": "permanentmarker", "label": "Komika Hand",      "file": "PermanentMarker-Regular.ttf","style": "Marker / Comic"},
]


@app.get("/api/fonts/bundled")
def list_bundled_fonts():
    """Return the list of always-available bundled fonts with metadata."""
    return {"fonts": _BUNDLED_FONTS}


@app.get("/api/font/preview")
def font_preview(key: str, text: str = "AaBbCc 123", size: int = 36, width: int = 260, height: int = 52):
    """Render a small PNG swatch showing what a font looks like at the given size.

    Returns a PNG image (no file saved — streamed directly from memory).
    Uses the actual TTF file so WYSIWYG matches the real render output.
    """
    import io
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise HTTPException(status_code=503, detail="PIL not available")

    # Resolve font file path
    from app import FONTS_DIR
    _WIN = Path("C:/Windows/Fonts")
    FONT_FILE_MAP: dict[str, Path] = {
        "impact":          _WIN / "impact.ttf",
        "arialbd":         _WIN / "arialbd.ttf",
        "arial":           _WIN / "arial.ttf",
        "bebas":           _WIN / "BebasNeue.ttf",
        "anton":           _WIN / "Anton-Regular.ttf",
        "ariblk":          _WIN / "ariblk.ttf",
        "gothicb":         _WIN / "GOTHICB.TTF",
        "verdanab":        _WIN / "verdanab.ttf",
        "segoeuib":        _WIN / "segoeuib.ttf",
        "montserrat":      FONTS_DIR / "Montserrat-Bold.ttf",
        "luckiestguy":     FONTS_DIR / "LuckiestGuy-Regular.ttf",
        "nunito":          FONTS_DIR / "Nunito-ExtraBold.ttf",
        "permanentmarker": FONTS_DIR / "PermanentMarker-Regular.ttf",
    }

    fp = FONT_FILE_MAP.get(key.lower())
    font = None
    if fp and fp.exists():
        try:
            font = ImageFont.truetype(str(fp), size)
        except Exception:
            pass
    if font is None:
        # Fallback: try any system TTF
        for fallback in [_WIN / "arialbd.ttf", _WIN / "arial.ttf"]:
            if fallback.exists():
                try:
                    font = ImageFont.truetype(str(fallback), size)
                    break
                except Exception:
                    pass

    img = Image.new("RGBA", (width, height), (18, 18, 24, 255))   # dark bg matching UI
    draw = ImageDraw.Draw(img)

    if font:
        # Measure text to center vertically
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = 10
        y = max(0, (height - th) // 2 - bbox[1])
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    else:
        draw.text((10, 10), text, fill=(200, 200, 200, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(content=buf.read(), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/font/file")
def font_file(key: str):
    """Serve the raw TTF bytes for a bundled font so @font-face can load it.

    Cached for 24h in browser — fonts don't change between sessions.
    Only bundled fonts are served (system fonts are already available in Windows).
    """
    from fastapi.responses import Response as _Resp
    from app import FONTS_DIR

    _WIN = Path("C:/Windows/Fonts")
    FONT_FILE_MAP: dict[str, Path] = {
        "montserrat":      FONTS_DIR / "Montserrat-Bold.ttf",
        "luckiestguy":     FONTS_DIR / "LuckiestGuy-Regular.ttf",
        "nunito":          FONTS_DIR / "Nunito-ExtraBold.ttf",
        "permanentmarker": FONTS_DIR / "PermanentMarker-Regular.ttf",
        # System fonts exposed for completeness
        "impact":          _WIN / "impact.ttf",
        "arialbd":         _WIN / "arialbd.ttf",
        "bebas":           _WIN / "BebasNeue.ttf",
        "anton":           _WIN / "Anton-Regular.ttf",
    }
    fp = FONT_FILE_MAP.get(key.lower())
    if not fp or not fp.exists():
        raise HTTPException(status_code=404, detail=f"Font '{key}' not found")

    data = fp.read_bytes()
    return _Resp(
        content=data,
        media_type="font/ttf",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/api/encoders")
def list_encoders():
    import app as _app
    return {
        "encoders": sorted(list(_app.AVAILABLE_ENCODERS)),
        "best": _app.BEST_ENCODER,
    }


@app.get("/api/ocr_status")
def get_ocr_status():
    """Return active OCR engine device (GPU (CUDA) vs CPU)."""
    device = get_ocr_device()
    return {
        "device": device,
        "is_gpu": "GPU" in str(device),
    }

# ── Multitrack Overlay & BiRefNet Endpoints ─────────────────────────────────

class RemoveBgRequest(BaseModel):
    path: str
    type: Optional[str] = "image"  # "image" | "video"

@app.post("/api/overlay/upload")
async def upload_overlay(file: UploadFile = File(...)):
    import uuid
    import urllib.parse
    ovl_dir = Path("overlay_assets")
    ovl_dir.mkdir(exist_ok=True)
    
    ext = Path(file.filename).suffix.lower()
    is_video = ext in {".mp4", ".mov", ".webm", ".mkv"}
    ovl_type = "video" if is_video else "image"
    
    uid = uuid.uuid4().hex[:8]
    safe_name = f"{uid}_{file.filename}"
    dst = ovl_dir / safe_name
    
    content = await file.read()
    with open(dst, "wb") as f:
        f.write(content)
        
    w, h = 400, 400
    if not is_video:
        try:
            with Image.open(dst) as im:
                w, h = im.size
        except Exception:
            pass
    else:
        try:
            cap = cv2.VideoCapture(str(dst))
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
        except Exception:
            pass

    resolved_path = str(dst.resolve())
    return {
        "id": uid,
        "name": file.filename,
        "path": resolved_path,
        "url": f"/overlay/file?path={urllib.parse.quote(resolved_path)}",
        "type": ovl_type,
        "w": w,
        "h": h,
    }


class OverlayUrlRequest(BaseModel):
    url: str

@app.post("/api/overlay/upload_url")
async def upload_overlay_from_url(req: OverlayUrlRequest):
    """Fetch an image/video from a remote URL and save it as an overlay asset.

    Solves CORS: the browser can't fetch arbitrary external images,
    but the Python backend can. Frontend drags an image URL here.
    Returns same shape as /api/overlay/upload.
    """
    import uuid, urllib.request, urllib.parse
    import mimetypes

    url = req.url.strip()
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Only http/https URLs supported")

    ovl_dir = Path("overlay_assets")
    ovl_dir.mkdir(exist_ok=True)

    uid = uuid.uuid4().hex[:8]

    try:
        # urllib with a browser-like User-Agent to avoid 403 on image hosts
        req_obj = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        })
        with urllib.request.urlopen(req_obj, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
            data = resp.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not fetch URL: {e}")

    # Determine extension from content-type or URL path
    ext = mimetypes.guess_extension(content_type) or Path(urllib.parse.urlparse(url).path).suffix
    if ext in (".jpe", ""):
        ext = ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".webm", ".mov"}:
        ext = ".jpg"

    is_video = ext in {".mp4", ".webm", ".mov"}
    ovl_type = "video" if is_video else "image"

    # Derive a readable filename from the URL
    url_name = Path(urllib.parse.urlparse(url).path).name or "image"
    if not Path(url_name).suffix:
        url_name = url_name + ext
    safe_name = f"{uid}_{url_name}"
    dst = ovl_dir / safe_name

    with open(dst, "wb") as f:
        f.write(data)

    w, h = 400, 400
    if not is_video:
        try:
            with Image.open(dst) as im:
                w, h = im.size
        except Exception:
            pass

    resolved_path = str(dst.resolve())
    return {
        "id": uid,
        "name": url_name,
        "path": resolved_path,
        "url": f"/overlay/file?path={urllib.parse.quote(resolved_path)}",
        "type": ovl_type,
        "w": w,
        "h": h,
    }


@app.get("/api/overlay/file")
@app.get("/overlay/file")
def get_overlay_file(path: str):
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Overlay file not found")
    ext = p.suffix.lower()
    media_type = "application/octet-stream"
    if ext in {".png", ".webp"}:
        media_type = "image/png" if ext == ".png" else "image/webp"
    elif ext == ".gif":
        media_type = "image/gif"
    elif ext in {".jpg", ".jpeg"}:
        media_type = "image/jpeg"
    elif ext in {".mp4", ".m4v"}:
        media_type = "video/mp4"
    elif ext in {".webm"}:
        media_type = "video/webm"
    elif ext in {".mov"}:
        media_type = "video/quicktime"
    return FileResponse(p, media_type=media_type)


# ── Custom Audio & Voiceover Endpoints ─────────────────────────────────────────

@app.post("/api/audio/upload")
async def upload_custom_audio(file: UploadFile = File(...)):
    import uuid
    import urllib.parse
    audio_dir = Path("audio_assets")
    audio_dir.mkdir(exist_ok=True)
    
    uid = uuid.uuid4().hex[:8]
    ext = Path(file.filename).suffix.lower()
    raw_dst = audio_dir / f"{uid}_raw{ext}"
    
    content = await file.read()
    with open(raw_dst, "wb") as f:
        f.write(content)
        
    is_video = ext in {".mp4", ".mov", ".webm", ".mkv", ".avi", ".ts", ".flv"}
    final_dst = raw_dst
    if is_video or ext not in {".mp3", ".m4a", ".wav", ".aac"}:
        out_m4a = audio_dir / f"{uid}.m4a"
        cmd = [FFMPEG, "-y", "-i", str(raw_dst), "-vn", "-c:a", "aac", "-b:a", "192k", str(out_m4a)]
        res = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if res.returncode == 0 and out_m4a.exists():
            final_dst = out_m4a
            try:
                raw_dst.unlink(missing_ok=True)
            except Exception:
                pass
    
    dur = get_video_duration(final_dst) or 0.0
    resolved_path = str(final_dst.resolve())
    return {
        "id": uid,
        "name": file.filename,
        "path": resolved_path,
        "url": f"/audio/file?path={urllib.parse.quote(resolved_path)}",
        "duration": round(dur, 2),
    }


@app.get("/api/audio/file")
@app.get("/audio/file")
def get_audio_file(path: str):
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    ext = p.suffix.lower()
    media_type = "audio/mpeg" if ext == ".mp3" else "audio/mp4" if ext in {".m4a", ".aac"} else "audio/wav" if ext == ".wav" else "application/octet-stream"
    return FileResponse(p, media_type=media_type)


@app.post("/api/overlay/remove_bg")
async def overlay_remove_bg(req: RemoveBgRequest):
    import urllib.parse
    src_p = Path(req.path)
    if not src_p.exists():
        raise HTTPException(status_code=404, detail=f"Source file not found: {req.path}")
    
    app_state.log(f"✂️ BiRefNet: Tách nền cho {src_p.name}...", "info")
    try:
        import birefnet_engine
        out_dir = Path("overlay_assets/cutouts")
        out_dir.mkdir(parents=True, exist_ok=True)
        
        is_gif = src_p.suffix.lower() == ".gif"
        is_video = req.type == "video" or src_p.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}
        is_animated_img = is_gif
        if not is_animated_img and not is_video and src_p.suffix.lower() in {".webp", ".png", ".apng"}:
            try:
                from PIL import Image as _PILImg
                with _PILImg.open(str(src_p)) as _timg:
                    if getattr(_timg, "is_animated", False) and getattr(_timg, "n_frames", 1) > 1:
                        is_animated_img = True
            except Exception:
                pass

        if is_animated_img:
            dst_p = out_dir / f"{src_p.stem}_nobg.gif"
            birefnet_engine.remove_gif_background(
                src_p, dst_p,
                progress_cb=lambda pct, msg: app_state.log(f"[BiRefNet GIF] {msg}", "info"),
                ffmpeg_bin=FFMPEG
            )
        elif is_video:
            dst_p = out_dir / f"{src_p.stem}_nobg.webm"
            birefnet_engine.remove_video_background(
                src_p, dst_p,
                progress_cb=lambda pct, msg: app_state.log(f"[BiRefNet Video] {msg}", "info"),
                ffmpeg_bin=FFMPEG
            )
        else:
            dst_p = out_dir / f"{src_p.stem}_nobg.png"
            birefnet_engine.remove_image_background(src_p, dst_p)
            
        resolved_dst = str(dst_p.resolve())
        app_state.log(f"✅ BiRefNet: Tách nền thành công -> {dst_p.name}", "ok")
        return {
            "status": "ok",
            "remove_bg_path": resolved_dst,
            "remove_bg_url": f"/overlay/file?path={urllib.parse.quote(resolved_dst)}",
        }
    except Exception as e:
        app_state.log(f"❌ BiRefNet error: {e}", "error")
        raise HTTPException(status_code=500, detail=str(e))

# ── Native Windows Dialogs & System Endpoints ─────────────────────────────────


@app.post("/api/videos/upload_files")
async def upload_files(files: List[UploadFile] = File(...)):
    added = []
    tmp_dir = Path("temp_uploads")
    tmp_dir.mkdir(exist_ok=True)
    existing = {p.resolve() for p in app_state.video_files}
    for file in files:
        dst = tmp_dir / file.filename
        with open(dst, "wb") as f:
            content = await file.read()
            f.write(content)
        if dst.exists() and dst.resolve() not in existing:
            app_state.video_files.append(dst)
            added.append(str(dst))
    app_state.save_config()
    return {"status": "ok", "added": added, "total": len(app_state.video_files)}


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

        # Parse double-null-delimited wchar buffer cleanly without accessing .raw
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


import unicodedata

def _safe_resolve_path(p_str: str) -> Optional[Path]:
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
                if 'app_state' in globals():
                    out_folder = app_state.get_current_output_folder()
                    if out_folder:
                        p_out = Path(out_folder)
                        candidate_dirs.extend([p_out, p_out / "raw_cuts"])
                    cfg_out = app_state.config.get("output_folder")
                    if cfg_out:
                        p_cfg = Path(cfg_out)
                        candidate_dirs.extend([p_cfg, p_cfg / "raw_cuts"])
                    for b in app_state.batches.values():
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




@app.post("/api/dialog/pick_files")
def pick_files_dialog():
    files = _py_pick_files(
        title="Select Bodycam Videos",
        filetypes=[("Video Files", "*.mp4;*.mkv;*.mov;*.avi;*.ts"), ("All Files", "*.*")],
        multi=True,
    )
    if files:
        req = VideoAddRequest(paths=files)
        return add_videos(req)
    return {"status": "cancelled", "added": []}


@app.post("/api/dialog/pick_edit_files")
def pick_edit_files_dialog():
    """Native file picker for Tab 2 Direct Edit addition."""
    files = _py_pick_files(
        title="Select Videos for Direct Edit",
        filetypes=[("Video Files", "*.mp4;*.mkv;*.mov;*.avi;*.ts"), ("All Files", "*.*")],
        multi=True,
    )
    if files:
        threading.Thread(target=_run_direct_edit_import, args=(files,), daemon=True).start()
        return {"status": "started", "count": len(files)}
    return {"status": "cancelled"}



# ── Tab 2 Direct Video Import & Background Gemini Analysis ─────────────────────

class DirectImportRequest(BaseModel):
    paths: List[str]


def _gemini_generate_video_title(
    video_path: Path,
    prompt_tpl: Optional[str],
    rotator: "KeyRotator",
    model_name: str,
    stop_event: threading.Event,
    log_fn: Any,
) -> tuple[Optional[str], Optional[str]]:
    """
    Generate a viral title for a video clip using Gemini AI with full key rotation and retry.
    Mirrors the resilience of Tab 1 analyze_video:
      - Uses Least Connections + Cooldown via rotator.acquire()
      - Retries across all available API keys on 429 quota, TCP error, or generic failures
      - Applies proper cooldown penalty to failed keys (60s on 429, 10s on TCP, 2s generic)
      - Cleans up remote uploaded video in finally block
    Returns: (title, error_message)
    """
    _tpl = (prompt_tpl or "").strip()
    if _tpl:
        _file_title = video_path.stem.replace("_", " ").title()
        try:
            _gen_prompt = _tpl.format(
                old_title=_file_title,
                description="based on what you see in the video",
                highlight_reason="based on what you see in the video",
            )
        except (KeyError, ValueError):
            _gen_prompt = _tpl
        if "output only" not in _gen_prompt.lower() and "nothing else" not in _gen_prompt.lower():
            _gen_prompt += "\n\nOutput ONLY the single title, nothing else. No numbering, no asterisks, no markdown."
    else:
        _gen_prompt = (
            "Watch this bodycam / dashcam video clip carefully.\n\n"
            "Write ONE viral, emotionally-charged title for YouTube Shorts / TikTok.\n\n"
            "RULES:\n"
            "• ALL CAPS, 3-10 words.\n"
            "• 100% ENGLISH — sensational, clickbaity, suspenseful, slightly rage-baiting.\n"
            "• MUST be specific to THIS video — not generic phrases that fit any bodycam clip.\n"
            "• No hashtags, no emoji, no quotes, no asterisks, no numbering.\n\n"
            "Output ONLY the title text, nothing else."
        )

    n_keys = max(1, len(rotator))
    last_exc = None

    for attempt in range(n_keys):
        if stop_event.is_set():
            return None, "Stopped by user"

        key = rotator.acquire()
        remote = None
        client = None
        sdk = None

        try:
            client, sdk = build_client(key)
            log_fn("info", f"[{video_path.name}] Uploading to Gemini (attempt {attempt+1}/{n_keys})...")
            remote = upload_video(client, sdk, video_path, _make_logger(log_fn), stop_event)
            if not remote:
                raise RuntimeError("Gemini video upload returned no remote file.")

            log_fn("info", f"[{video_path.name}] Generating title with AI (attempt {attempt+1}/{n_keys})...")
            if sdk == "new":
                from google.genai import types as _gt
                _safety = [
                    _gt.SafetySetting(category=_gt.HarmCategory.HARM_CATEGORY_HATE_SPEECH,       threshold=_gt.HarmBlockThreshold.BLOCK_NONE),
                    _gt.SafetySetting(category=_gt.HarmCategory.HARM_CATEGORY_HARASSMENT,        threshold=_gt.HarmBlockThreshold.BLOCK_NONE),
                    _gt.SafetySetting(category=_gt.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=_gt.HarmBlockThreshold.BLOCK_NONE),
                    _gt.SafetySetting(category=_gt.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=_gt.HarmBlockThreshold.BLOCK_NONE),
                ]
                _resp = client.models.generate_content(
                    model=model_name,
                    contents=[_gt.Content(role="user", parts=[
                        _gt.Part.from_uri(file_uri=remote.uri, mime_type=remote.mime_type or "video/mp4"),
                        _gt.Part.from_text(text=_gen_prompt),
                    ])],
                    config=_gt.GenerateContentConfig(
                        temperature=0.7,
                        max_output_tokens=200,
                        safety_settings=_safety,
                    ),
                )
            else:
                _safe_p = _gen_prompt.encode("ascii", errors="replace").decode("ascii")
                _m = client.GenerativeModel(model_name)
                _resp = _m.generate_content(
                    [remote, _safe_p],
                    generation_config={
                        "temperature": 0.7,
                        "max_output_tokens": 200,
                    },
                    safety_settings=[
                        {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HARASSMENT",         "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",  "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT",  "threshold": "BLOCK_NONE"},
                    ],
                )
            _raw = (_resp.text or "").strip()

            import re as _re2
            _first_line = next(
                (ln.strip() for ln in _raw.splitlines() if ln.strip()),
                _raw.strip()
            )
            _t = _re2.sub(r"[*#]+", "", _first_line).strip()
            _t = _re2.sub(r"^\d+[.)\s]+", "", _t).strip()
            _t = _t.strip('"\'')
            _META = frozenset({'here','is','are','the','a','an','title','headline',
                               'best','fits','context','video','sure','suggested',
                               'for','you','most','suitable','that','this','following',
                               'captures','my','option','viral'})
            if ": " in _t:
                _cp   = _t.index(": ")
                _pre  = _t[:_cp]
                _rest = _t[_cp + 2:].strip()
                _pw   = _re2.findall(r"[a-z']+", _pre.lower())
                _caps = _re2.findall(r"\b[A-Z]{2,}\b", _pre)
                _mc   = sum(1 for w in _pw if w in _META)
                if len(_pw) <= 15 and _mc >= 2 and not _caps and _rest:
                    _t = _rest

            if not _t:
                raise ValueError("Gemini returned empty or blank title.")

            log_fn("ok", f"✅ [{video_path.name}] Title generated: {_t[:70]}")
            return _t, None

        except InterruptedError:
            return None, "Stopped by user"
        except Exception as exc:
            last_exc = exc
            err_str = str(exc)
            err_lower = err_str.lower()
            is_quota = any(kw in err_lower for kw in (
                "quota", "429", "rate limit",
                "resource_exhausted", "too many requests",
            ))
            is_tcp = "10053" in err_str or "10054" in err_str
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
                log_fn("warn", f"[{video_path.name}] Attempt {attempt+1}/{n_keys} failed [{label}]: {str(exc)[:60]} — trying next key…")
                time.sleep(0.5)
            else:
                log_fn("error", f"[{video_path.name}] All {n_keys} API keys failed title gen: {exc}")

        finally:
            rotator.release(key)
            if remote is not None and client is not None and sdk is not None:
                try:
                    delete_remote(client, sdk, remote, _make_logger(log_fn))
                except Exception:
                    pass

    return None, str(last_exc) if last_exc else "Failed to generate title"


def _run_direct_edit_import(video_paths: List[str]):
    """Background worker for Tab 2 direct video addition.
    Uploads each clip to Gemini, generates a title (using config.title_prompt if set,
    otherwise a sensible default) with full key rotation and retry, cuts a 16s segment
    from the start, and adds it to the Edit Queue.
    """
    app_state.stop_event.clear()
    out_dir = Path(app_state.get_current_output_folder())
    raw_dir = out_dir / "raw_cuts"
    raw_dir.mkdir(parents=True, exist_ok=True)

    def _log(level: str, msg: str):
        app_state.log(msg, level)

    keys       = [k.strip() for k in app_state.config.get("api_keys", []) if k.strip()]
    model_name = app_state.config.get("model_name", MODEL_NAME)

    def _process_one(p_str: str):
        p = _safe_resolve_path(p_str)
        if not p or not p.exists():
            app_state.log(f"Direct Import: File missing {p_str}", "warn")
            return

        titles_found: list = []
        title_error = False
        title_error_msg = ""
        gen_title_enabled = app_state.config.get("direct_import_gen_title", True)

        if gen_title_enabled and keys:
            try:
                rotator = app_state.get_rotator()
                _custom_tpl = app_state.config.get("title_prompt")
                t, err = _gemini_generate_video_title(p, _custom_tpl, rotator, model_name, app_state.stop_event, _log)
                if t:
                    titles_found = [t]
                else:
                    title_error = True
                    title_error_msg = err or "Title generation failed"
                    app_state.log(f"⚠️ Title gen failed for {p.name}: {title_error_msg} (can retry in Tab 2)", "warn")
            except Exception as _ge:
                title_error = True
                title_error_msg = str(_ge)
                app_state.log(f"⚠️ Title gen exception for {p.name}: {_ge}", "warn")

        # Tab 2 is for pre-cut clips — always start from beginning.
        start_ts = "00:00:00"
        vid_dur  = get_video_duration(p) or 0.0

        # Final safety strip: remove any residual asterisks or leading numbering
        import re as _re3
        if titles_found:
            title = _re3.sub(r"[*#]+", "", titles_found[0]).strip()
            title = _re3.sub(r"^\d+[.)\s]+", "", title).strip()
            suggested = titles_found
        else:
            # Khi tắt tính năng AI title hoặc không có title: để trống tiêu đề (không lấy tên file)
            title = ""
            suggested = []

        # Cut 16s clip exact into raw_cuts
        stem        = sanitize(p.stem)
        start_clean = start_ts.replace(":", "-")
        dst_clip    = raw_dir / f"{stem}_highlight_{start_clean}.mp4"

        # Preserve the full clip duration — Tab 2 is for pre-cut clips.
        # Fall back to CLIP_DURATION only if ffprobe couldn't read the duration.
        _cut_dur = int(vid_dur) if vid_dur > 1 else CLIP_DURATION

        try:
            cut_clip_exact(p, start_ts, dst_clip, _make_logger(_log), duration=_cut_dur)

            entry = {
                "clip_path":        str(dst_clip),
                "path":             str(dst_clip),
                "name":             dst_clip.name,
                "source_path":      str(p),
                "title":            title,
                "suggested_titles": suggested,
                "description":      "",
                "highlight_reason": "",
                "title_error":      title_error,
                "title_error_msg":  title_error_msg,
                "state":            _default_edit_state(),
            }
            with STATE_LOCK:
                app_state.edit_queue = [e for e in app_state.edit_queue
                                        if (e.get("clip_path") or e.get("path")) != str(dst_clip)]
                app_state.edit_queue.append(entry)
            _sse_bus.push("queue_changed", {"action": "add", "name": dst_clip.name})
            status_tag = "⚠️ (Title Error - Retry available)" if title_error else ""
            display_title = title[:40] if title else "(để trống tiêu đề)"
            app_state.log(f"✅ Added to Edit Queue: {p.name} — {display_title} {status_tag}", "ok" if not title_error else "warn")
        except Exception as ce:
            app_state.log(f"Cut failed for direct import {p.name}: {ce}", "error")

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(_process_one, video_paths)


@app.post("/api/edit_queue/import_direct")
def import_direct_to_edit(req: DirectImportRequest):
    if not req.paths:
        raise HTTPException(status_code=400, detail="No video paths provided.")
    threading.Thread(target=_run_direct_edit_import, args=(req.paths,), daemon=True).start()
    return {"status": "started", "count": len(req.paths)}

@app.post("/api/edit_queue/upload_direct")
async def upload_direct_to_edit(files: List[UploadFile] = File(...)):
    added_paths = []
    tmp_dir = Path("temp_uploads")
    tmp_dir.mkdir(exist_ok=True)
    for file in files:
        dst = tmp_dir / file.filename
        with open(dst, "wb") as f:
            content = await file.read()
            f.write(content)
        if dst.exists():
            added_paths.append(str(dst))
    if added_paths:
        threading.Thread(target=_run_direct_edit_import, args=(added_paths,), daemon=True).start()
    return {"status": "started", "count": len(added_paths)}


@app.post("/api/dialog/pick_folder")
def pick_folder_dialog(req: Optional[Dict[str, Any]] = Body(None)):
    folder = _py_pick_folder("Select Output Folder")
    if folder:
        norm_folder = os.path.normpath(folder)
        batch_id = None
        if req and isinstance(req, dict):
            batch_id = req.get("batch_id")
        if not batch_id:
            batch_id = app_state.active_batch_id

        with STATE_LOCK:
            if batch_id and batch_id in app_state.batches:
                app_state.batches[batch_id]["output_folder"] = norm_folder
            app_state.config["output_folder"] = norm_folder
            app_state.save_config()
            app_state.save_session()

        _sse_bus.push("batches_changed", {"action": "update_folder", "id": batch_id, "folder": norm_folder})
        app_state.log(f"📁 Output folder set to: {norm_folder}", "ok")
        return {"status": "ok", "folder": norm_folder, "path": norm_folder}
    return {"status": "cancelled", "folder": "", "path": ""}

@app.post("/api/dialog/pick_bg_image")
def pick_bg_image_dialog():
    paths = _py_pick_files(
        title="Select Background Image",
        filetypes=[
            ("Image Files", "*.jpg *.jpeg *.png *.bmp *.webp"),
            ("All Files", "*.*"),
        ],
        multi=False,
    )
    if paths:
        return {"status": "ok", "path": paths[0]}
    return {"status": "cancelled", "path": ""}

@app.post("/api/dialog/pick_bg_video")
def pick_bg_video_dialog():
    paths = _py_pick_files(
        title="Select Background Video",
        filetypes=[
            ("Video Files", "*.mp4 *.mkv *.mov *.avi"),
            ("All Files", "*.*"),
        ],
        multi=False,
    )
    if paths:
        return {"status": "ok", "path": paths[0]}
    return {"status": "cancelled", "path": ""}


_last_opened_folders: Dict[str, float] = {}


def _reveal_folder_in_explorer(folder_path: str) -> str:
    """Reliably open a folder in Windows Explorer without opening duplicate windows.
    
    1. Debounces rapid calls within 1.0s to prevent multiple windows on double-click.
    2. Opens the folder via os.startfile() (native Windows ShellExecute, opens exactly 1 window).
    3. Falls back to explorer.exe only if os.startfile fails.
    """
    target = os.path.normpath(os.path.abspath(folder_path))
    try:
        os.makedirs(target, exist_ok=True)
    except Exception as e:
        app_state.log(f"⚠️ Could not create directory: {e}", "warn")

    # Debounce rapid consecutive clicks on the same folder within 1.0s
    now = time.time()
    last_time = _last_opened_folders.get(target, 0.0)
    if now - last_time < 1.0:
        return target
    _last_opened_folders[target] = now

    # Housekeeping: prune old entries
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
            app_state.log(f"⚠️ Failed to open explorer for {target}: {e}", "warn")

    return target


@app.post("/api/system/open_output")
@app.post("/api/open_output")
@app.get("/api/system/open_output")
@app.get("/api/open_output")
@app.post("/api/open_folder")
@app.post("/open_folder")
@app.get("/api/open_folder")
@app.get("/open_folder")
@app.post("/api/open_export_folder")
@app.get("/api/open_export_folder")
def open_output_folder(req: Optional[Dict[str, Any]] = Body(None)):
    custom_folder = None
    batch_id = None
    if req and isinstance(req, dict):
        custom_folder = req.get("folder") or req.get("path")
        batch_id = req.get("batch_id")
    if custom_folder and str(custom_folder).strip():
        folder = str(custom_folder).strip()
    else:
        folder = app_state.get_current_output_folder(batch_id)

    target_path = os.path.normpath(os.path.abspath(folder))
    try:
        _reveal_folder_in_explorer(target_path)
        app_state.log(f"📂 Opened output folder: {target_path}", "ok")
        return {"status": "ok", "ok": True, "path": target_path}
    except Exception as ex:
        app_state.log(f"❌ Failed to open folder {target_path}: {ex}", "err")
        raise HTTPException(status_code=500, detail=f"Cannot open folder: {ex}")


@app.post("/api/system/open_raw_cuts")
@app.post("/api/open_raw_cuts")
@app.get("/api/system/open_raw_cuts")
@app.get("/api/open_raw_cuts")
@app.post("/api/open_raw_cuts_folder")
@app.get("/api/open_raw_cuts_folder")
def open_raw_cuts_folder(req: Optional[Dict[str, Any]] = Body(None)):
    custom_folder = None
    batch_id = None
    if req and isinstance(req, dict):
        custom_folder = req.get("folder") or req.get("path")
        batch_id = req.get("batch_id")
    if custom_folder and str(custom_folder).strip():
        base_folder = str(custom_folder).strip()
    else:
        base_folder = app_state.get_current_output_folder(batch_id)

    raw_path = os.path.normpath(os.path.abspath(os.path.join(base_folder, "raw_cuts")))
    try:
        _reveal_folder_in_explorer(raw_path)
        app_state.log(f"📂 Opened raw_cuts folder: {raw_path}", "ok")
        return {"status": "ok", "ok": True, "path": raw_path}
    except Exception as ex:
        app_state.log(f"❌ Failed to open raw_cuts folder {raw_path}: {ex}", "err")
        raise HTTPException(status_code=500, detail=f"Cannot open raw_cuts folder: {ex}")


@app.post("/api/cut")
def cut_candidate_clip(req: Dict[str, Any]):
    """Quick stream-copy cut — also adds the clip to the Edit queue.
    Supports optional trim_start_offset (±30s) and trim_duration overrides.
    """
    video_path_str    = req.get("video_path")
    candidate_idx     = req.get("candidate_index", 0)
    title             = req.get("title", "")         # user-confirmed title from Tab 1
    trim_start_offset = float(req.get("trim_start_offset", 0.0))  # signed seconds
    trim_duration     = float(req.get("trim_duration", CLIP_DURATION))

    is_yt = isinstance(video_path_str, str) and video_path_str.startswith(("http://", "https://"))
    v_path = None
    if not is_yt:
        v_path = _safe_resolve_path(video_path_str)
        if not v_path or not v_path.exists():
            v_name = Path(video_path_str).name
            for vf in app_state.video_files:
                if vf.name == v_name and vf.exists():
                    v_path = vf
                    break
        if not v_path or not v_path.exists():
            raise HTTPException(status_code=404, detail=f"Source video not found: {video_path_str}")

    status_info = _get_video_result(video_path_str if is_yt else v_path)
    candidates  = status_info.get("candidates", [])
    if candidate_idx >= len(candidates):
        raise HTTPException(status_code=400, detail="Candidate index out of range")

    chosen   = candidates[candidate_idx]
    start_ts = (
        req.get("start_time")
        or req.get("start_ts")
        or chosen.get("start_time")
        or chosen.get("start_ts")
        or "00:00:00"
    )
    vid_dur = (getattr(app_state, "yt_metadata", {}).get(video_path_str, {}).get("duration", 0.0)
               if is_yt else (get_video_duration(v_path) or 0.0))

    # Apply trim_start_offset
    start_sec = ts_to_seconds(start_ts)
    if abs(trim_start_offset) > 0.01:
        start_sec = max(0.0, start_sec + trim_start_offset)
        h = int(start_sec // 3600)
        m = int((start_sec % 3600) // 60)
        s = start_sec % 60
        start_ts = f"{h:02d}:{m:02d}:{s:06.3f}"

    # Clamp clip duration so it never extends beyond the source video
    if vid_dur > 0:
        trim_duration = min(trim_duration, vid_dur - start_sec)

    suggested_titles = chosen.get("suggested_titles", [])
    cand_title = chosen.get("title", "")
    if not cand_title and suggested_titles:
        cand_title = suggested_titles[0]
    final_title = (title or cand_title).strip()

    out_dir = Path(app_state.get_current_output_folder())
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        app_state.log(f"⚠️ Không tạo được output_folder ({out_dir}): {e} — dùng output_clips thay thế", "warn")
        out_dir = Path("output_clips")
        out_dir.mkdir(parents=True, exist_ok=True)

    raw_dir = out_dir / "raw_cuts"
    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
        app_state.log(f"📁 raw_cuts folder: {raw_dir} (exists={raw_dir.exists()})", "info")
    except Exception as e:
        app_state.log(f"❌ Không tạo được raw_cuts folder ({raw_dir}): {e}", "error")
        raise HTTPException(status_code=500, detail=f"Cannot create raw_cuts folder: {e}")

    if is_yt:
        yt_title = getattr(app_state, "yt_metadata", {}).get(video_path_str, {}).get("title") or "yt_clip"
        stem = sanitize(yt_title)[:30]
    else:
        stem = sanitize(v_path.stem)
    dst  = raw_dir / f"{stem}_clip{chosen.get('id', candidate_idx+1)}_{start_ts.replace(':', '-')}.mp4"
    app_state.log(f"✂️  Cắt → {dst}", "info")

    def _log(level: str, msg: str):
        app_state.log(msg, level)

    if is_yt:
        end_sec = start_sec + max(1.0, trim_duration)
        eh = int(end_sec // 3600)
        em = int((end_sec % 3600) // 60)
        es = end_sec % 60
        end_ts = f"{eh:02d}:{em:02d}:{es:06.3f}"
        cookie_browser = app_state.config.get("youtube_cookie_browser", None)
        try:
            download_youtube_section(
                url=video_path_str,
                start_time=start_ts,
                end_time=end_ts,
                output_path=str(dst),
                cookies_browser=cookie_browser,
                log=_log,
            )
        except Exception as exc:
            app_state.log(f"❌ Tải đoạn YouTube thất bại: {exc}", "error")
            raise HTTPException(status_code=500, detail=str(exc))
    else:
        try:
            cut_clip_exact(v_path, start_ts, dst, _make_logger(_log), duration=max(1.0, trim_duration))
        except Exception as exc:
            app_state.log(f"❌ Raw cut thất bại: {exc}", "error")
            raise HTTPException(status_code=500, detail=f"Cut failed: {exc}")

    if dst.exists():
        size_mb = dst.stat().st_size / 1_048_576
        app_state.log(f"✅ Raw cut saved → {dst.name} ({size_mb:.2f} MB)", "ok")
    else:
        app_state.log(f"⚠️ FFmpeg/yt-dlp chạy xong nhưng file không tồn tại: {dst}", "warn")

    # ── Add to edit_queue (idempotent: skip if same path already queued) ──
    entry = {
        "clip_path":  str(dst),
        "path":       str(dst),
        "name":       dst.name,
        "title":      final_title,
        "source":     video_path_str if is_yt else v_path.name,
        "start_time": start_ts,
        "start_sec":  start_sec,
        "duration":   max(1.0, trim_duration),
        "suggested_titles": suggested_titles,
        "state":      _default_edit_state(),
    }
    with STATE_LOCK:
        batch_id = app_state.active_batch_id
        if batch_id and batch_id in app_state.batches:
            entry["batch_id"] = batch_id
            b_queue = app_state.batches[batch_id].setdefault("edit_queue", [])
            b_queue.append(entry)
            app_state.batches[batch_id]["count"] = len(b_queue)

        already = any(e["path"] == str(dst) for e in app_state.edit_queue)
        if not already:
            app_state.edit_queue.append(entry)
            app_state.save_session()
            _sse_bus.push("queue_changed", {"action": "add", "name": dst.name})

    app_state.log(f"✂️  Cut → {dst.name} (Title: {final_title or '—'})", "ok")
    return {"status": "ok", "output": str(dst), "queued": True, "entry": entry}


# ── Video Streaming (for HTML5 <video> player with seek support) ──────────────

from fastapi import Request as FastAPIRequest

@app.get("/api/stream")
async def stream_video(path: str, request: FastAPIRequest):
    """Serve video file with HTTP Range support so the browser can seek with zero event-loop blocking."""
    if not path or path.strip() in ("", "."):
        raise HTTPException(status_code=404, detail="File not found.")
    p = _safe_resolve_path(path) or Path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found or is a directory.")

    file_size    = p.stat().st_size
    range_header = request.headers.get("Range")
    media_type   = "video/mp4" if p.suffix.lower() in (".mp4", ".mov", ".m4v") else "video/webm"
    headers_base = {"Accept-Ranges": "bytes", "Cache-Control": "no-cache"}

    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            start = int(m.group(1))
            end   = int(m.group(2)) if m.group(2) else min(start + 8 * 1024 * 1024 - 1, file_size - 1)
            end   = min(end, file_size - 1)
            chunk = end - start + 1

            async def _iter():
                import anyio
                def _read(f_obj, sz):
                    return f_obj.read(sz)
                with open(p, "rb") as f:
                    f.seek(start)
                    remaining = chunk
                    while remaining > 0:
                        read_sz = min(262144, remaining)
                        data = await anyio.to_thread.run_sync(_read, f, read_sz)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            return StreamingResponse(
                _iter(), status_code=206, media_type=media_type,
                headers={**headers_base,
                         "Content-Range":  f"bytes {start}-{end}/{file_size}",
                         "Content-Length": str(chunk)})

    return FileResponse(str(p), media_type=media_type, headers=headers_base)



# ── Clip Preview Endpoint ──────────────────────────────────────────────────────
# Serves a pre-cut 16s clip from the in-memory cache (instant FileResponse).
# Falls back to on-demand ffmpeg pipe if the cache hasn't been populated yet.

@app.get("/api/clip/preview")
def clip_preview(path: str, start: float = 0.0, dur: float = 16.0):
    p = _safe_resolve_path(path) or Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    dur = max(1.0, min(dur, 120.0))
    cache_key = f"{p}|{start:.1f}"

    # 1. Fast path: serve pre-cut file from cache (browser-cached for instant replay)
    with _PREVIEW_CACHE_LOCK:
        cached = _PREVIEW_CACHE.get(cache_key)
    if cached and cached.exists() and cached.stat().st_size > 500:
        return FileResponse(
            str(cached), media_type="video/mp4",
            headers={"Cache-Control": "public, max-age=86400", "Accept-Ranges": "bytes"},
        )

    # 2. On-demand encode fallback when cache miss (first selection, before background precut finishes)
    out = _precut_preview(p, start, dur)
    if out and out.exists() and out.stat().st_size > 500:
        return FileResponse(
            str(out), media_type="video/mp4",
            headers={"Cache-Control": "public, max-age=86400", "Accept-Ranges": "bytes"},
        )

    raise HTTPException(status_code=500, detail="Failed to generate clip preview.")


@app.get("/api/clip/thumbnail")
def get_clip_thumbnail(path: str, start: float = 0.0):
    """Return a tiny 90×160 JPEG thumbnail for the candidate at *start* seconds.

    Returns 204 (No Content) when the thumbnail is still being generated in the
    background so the browser can retry without showing a broken-image icon.
    Returns 200 with image/jpeg when ready.
    """
    if path.startswith(("http://", "https://")):
        m = re.search(r"(?:v=|\/|be\/|embed\/|shorts\/)([a-zA-Z0-9_\-]{11})", path)
        if m:
            vid_id = m.group(1)
            from fastapi.responses import RedirectResponse
            return RedirectResponse(f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg")
        meta = getattr(app_state, "yt_metadata", {}).get(path, {})
        if meta.get("thumbnail"):
            from fastapi.responses import RedirectResponse
            return RedirectResponse(meta["thumbnail"])
        from fastapi.responses import Response as _Resp
        return _Resp(status_code=204)

    v_path = Path(path)
    if not v_path.exists():
        raise HTTPException(status_code=404, detail="Video not found.")

    thumb = _generate_thumbnail(v_path, start)
    if thumb is None or not thumb.exists():
        # Still generating — caller should retry
        from fastapi.responses import Response as _Resp
        return _Resp(status_code=204)

    from fastapi.responses import FileResponse as _FR
    return _FR(str(thumb), media_type="image/jpeg",
               headers={"Cache-Control": "max-age=3600"})


@app.get("/api/clip/stream_preview")
async def stream_clip_preview(path: str, start: float = 0.0, dur: float = 16.0):
    """Stream a clip segment directly from source video via FFmpeg pipe.

    Guaranteed ~100-200ms response regardless of analysis load:
    - Cache hit  → FileResponse (fastest, supports browser seek/range)
    - Cache miss → FFmpeg frag-MP4 pipe → browser starts playing immediately
      No disk write needed; fragmented MP4 is playable as it streams.

    FFmpeg runs at ABOVE_NORMAL_PRIORITY so it beats all background analysis
    and proxy-encode processes for CPU and I/O scheduling.
    """
    if path.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="YouTube clips use the embedded player, not stream preview.")

    p = _safe_resolve_path(path) or Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    dur = max(1.0, min(dur, 120.0))

    # ── Fast path: pre-cut cache file exists ──────────────────────────────────
    cache_key = f"{p}|{start:.1f}"
    with _PREVIEW_CACHE_LOCK:
        cached = _PREVIEW_CACHE.get(cache_key)
    if cached and cached.exists() and cached.stat().st_size > 500:
        return FileResponse(
            str(cached), media_type="video/mp4",
            headers={"Cache-Control": "public, max-age=86400", "Accept-Ranges": "bytes"},
        )

    # ── Streaming path: pipe FFmpeg output directly to browser ────────────────
    # frag_keyframe+empty_moov: no moov atom needed at start → browser can decode
    # chunks as they arrive, giving near-instant playback start.
    _NO_WIN   = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    _ABOVE    = 0x00008000  # ABOVE_NORMAL_PRIORITY_CLASS — beats analysis/proxy processes
    cmd = [
        FFMPEG,
        "-ss", str(max(0.0, start - 0.5)),  # seek 0.5s early for clean keyframe
        "-i", str(p),
        "-ss", "0.5",                        # trim the 0.5s pre-seek buffer
        "-t", str(dur),
        "-c", "copy",
        "-movflags", "frag_keyframe+empty_moov+faststart",
        "-f", "mp4",
        "pipe:1",
    ]

    async def _generate():
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=_NO_WIN | _ABOVE,
        )
        try:
            while True:
                chunk = await proc.stdout.read(65536)  # 64 KB chunks
                if not chunk:
                    break
                yield chunk
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            await proc.wait()

    return StreamingResponse(
        _generate(),
        media_type="video/mp4",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )




# ── Edit Queue Endpoints ───────────────────────────────────────────────────────

@app.get("/api/edit_queue")
def get_edit_queue():
    with STATE_LOCK:
        return {"clips": list(app_state.edit_queue)}

class RemoveEditRequest(BaseModel):
    path: str

@app.post("/api/edit_queue/remove")
def remove_from_edit_queue(req: RemoveEditRequest):
    with STATE_LOCK:
        app_state.edit_queue = [
            e for e in app_state.edit_queue
            if (e.get("clip_path") or e.get("path")) != req.path
        ]
        app_state.save_session()
    return {"status": "ok"}

@app.post("/api/edit_queue/clear")
def clear_edit_queue():
    with STATE_LOCK:
        app_state.edit_queue = []
        app_state.save_session()
    return {"status": "ok"}

class AddEditRequest(BaseModel):
    clip_path: str
    title: str = ""
    suggested_titles: List[str] = []
    state: Dict[str, Any] = {}

@app.post("/api/edit_queue/add")
def add_to_edit_queue(req: AddEditRequest):
    """Called by 'Send to Edit & Export' button — adds already-cut clip to Tab 2 queue."""
    p = Path(req.clip_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Clip not found: {req.clip_path}")
    entry = {
        "clip_path": str(p),
        "path":      str(p),   # alias so both keys work
        "name":      p.name,
        "title":     req.title,
        "suggested_titles": req.suggested_titles,
        "state":     req.state or {},
    }
    with STATE_LOCK:
        # Idempotent: remove existing entry with same path then re-append
        app_state.edit_queue = [e for e in app_state.edit_queue if (e.get("clip_path") or e.get("path")) != str(p)]
        app_state.edit_queue.append(entry)
        app_state.save_session()
    _sse_bus.push("queue_changed", {"action": "add", "name": p.name})
    app_state.log(f"📥 Added to Edit queue: {p.name} — {req.title[:40] or '(no title)'}", "ok")
    # CRITICAL: must return entry so frontend sendToEdit can update local state without re-fetch race
    return {"status": "ok", "entry": entry}


class SendAllCandidatesRequest(BaseModel):
    video_path: str

@app.post("/api/candidates/send_all_to_edit")
def send_all_candidates_to_edit(req: SendAllCandidatesRequest):
    """Batch cut and transfer ALL candidates for a video into Tab 2 edit queue using Title #1."""
    is_yt = isinstance(req.video_path, str) and req.video_path.startswith(("http://", "https://"))
    v_path = None
    if not is_yt:
        v_path = _safe_resolve_path(req.video_path)
        if not v_path or not v_path.exists():
            v_name = Path(req.video_path).name
            for vf in app_state.video_files:
                if vf.name == v_name and vf.exists():
                    v_path = vf
                    break
        if not v_path or not v_path.exists():
            raise HTTPException(status_code=404, detail=f"Source video not found: {req.video_path}")

    status_info = _get_video_result(req.video_path if is_yt else v_path)
    candidates = status_info.get("candidates", [])
    if not candidates:
        raise HTTPException(status_code=400, detail="Video chưa có candidates phân tích xong.")

    out_dir = Path(app_state.get_current_output_folder())
    raw_dir = out_dir / "raw_cuts"
    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        app_state.log(f"⚠️ Không tạo được raw_cuts folder ({raw_dir}): {e} — dùng output_clips", "warn")
        raw_dir = Path("output_clips") / "raw_cuts"
        raw_dir.mkdir(parents=True, exist_ok=True)

    def _log(level: str, msg: str):
        app_state.log(msg, level)

    if is_yt:
        yt_title = getattr(app_state, "yt_metadata", {}).get(req.video_path, {}).get("title") or "yt_clip"
        stem = sanitize(yt_title)[:30]
        vid_dur = getattr(app_state, "yt_metadata", {}).get(req.video_path, {}).get("duration", 0.0)
    else:
        stem = sanitize(v_path.stem)
        vid_dur = get_video_duration(v_path) or 0.0

    added_entries = []

    for idx, chosen in enumerate(candidates):
        start_ts = (
            chosen.get("start_time")
            or chosen.get("start_ts")
            or "00:00:00"
        )
        base_dur = float(chosen.get("clip_duration") or CLIP_DURATION)
        start_sec = ts_to_seconds(start_ts)
        if vid_dur > 0:
            dur = min(base_dur, max(1.0, vid_dur - start_sec))
        else:
            dur = base_dur

        dst = raw_dir / f"{stem}_clip{chosen.get('id', idx+1)}_{start_ts.replace(':', '-')}.mp4"

        # Cut / download clip if not already exists on disk with valid size
        if not dst.exists() or dst.stat().st_size < 1000:
            app_state.log(f"✂️  [Tất cả] Cắt cảnh #{idx+1} ({start_ts}) → {dst.name}", "info")
            if is_yt:
                end_sec = start_sec + dur
                eh = int(end_sec // 3600)
                em = int((end_sec % 3600) // 60)
                es = end_sec % 60
                end_ts = f"{eh:02d}:{em:02d}:{es:06.3f}"
                cookie_browser = app_state.config.get("youtube_cookie_browser", None)
                try:
                    download_youtube_section(
                        url=req.video_path,
                        start_time=start_ts,
                        end_time=end_ts,
                        output_path=str(dst),
                        cookies_browser=cookie_browser,
                        log=_log,
                    )
                except Exception as exc:
                    app_state.log(f"❌ Tải đoạn #{idx+1} thất bại: {exc}", "error")
                    continue
            else:
                try:
                    cut_clip_exact(v_path, start_ts, dst, _make_logger(_log), duration=dur)
                except Exception as exc:
                    app_state.log(f"❌ Cắt cảnh #{idx+1} thất bại: {exc}", "error")
                    continue

        suggested = chosen.get("suggested_titles", [])
        title1 = (suggested[0] if (suggested and len(suggested) > 0) else chosen.get("title", "")).strip()

        entry = {
            "clip_path": str(dst),
            "path":      str(dst),
            "name":      dst.name,
            "title":     title1,
            "source":    req.video_path if is_yt else v_path.name,
            "start_time": start_ts,
            "start_sec":  start_sec,
            "duration":   dur,
            "suggested_titles": suggested,
            "state":     _default_edit_state(),
        }

        with STATE_LOCK:
            batch_id = app_state.active_batch_id
            if batch_id and batch_id in app_state.batches:
                entry["batch_id"] = batch_id
                b_queue = app_state.batches[batch_id].setdefault("edit_queue", [])
                if not any((x.get("clip_path") or x.get("path")) == str(dst) for x in b_queue):
                    b_queue.append(entry)
                app_state.batches[batch_id]["count"] = len(b_queue)

            app_state.edit_queue = [e for e in app_state.edit_queue if (e.get("clip_path") or e.get("path")) != str(dst)]
            app_state.edit_queue.append(entry)
            added_entries.append(entry)

    with STATE_LOCK:
        app_state.save_session()

    _sse_bus.push("queue_changed", {"action": "batch_add", "count": len(added_entries)})
    v_label = stem if is_yt else v_path.name
    app_state.log(f"⚡ Đã chuyển {len(added_entries)} cảnh của '{v_label}' sang Tab 2 (Title #1)", "ok")
    return {"status": "ok", "added_count": len(added_entries), "entries": added_entries}

class UpdateEditRequest(BaseModel):
    index: int
    patch: Dict[str, Any] = {}

@app.post("/api/edit_queue/update")
def update_edit_queue_item(req: UpdateEditRequest):
    """Update state/title patch for an item in edit_queue by index."""
    with STATE_LOCK:
        if 0 <= req.index < len(app_state.edit_queue):
            item = app_state.edit_queue[req.index]
            if "title" in req.patch:
                item["title"] = req.patch.pop("title")
            if "state" not in item or not isinstance(item["state"], dict):
                item["state"] = {}
            item["state"].update(req.patch)
            app_state.save_session()
            return {"status": "ok", "index": req.index, "entry": item}
        raise HTTPException(status_code=404, detail="Edit queue index out of bounds")


# ── Batch Management Endpoints ───────────────────────────────────────────────

class BatchCreateRequest(BaseModel):
    name: str = "Cụm mới"
    output_folder: Optional[str] = None

class BatchSwitchRequest(BaseModel):
    batch_id: str

class BatchRenameRequest(BaseModel):
    batch_id: str
    name: str

class BatchFolderRequest(BaseModel):
    batch_id: str
    output_folder: str

class BatchDeleteRequest(BaseModel):
    batch_id: str

@app.get("/api/batches")
def get_batches():
    with STATE_LOCK:
        batch_list = []
        for b_id, b_data in app_state.batches.items():
            folder = b_data.get("output_folder") or app_state.get_current_output_folder(b_id)
            batch_list.append({
                "id": b_id,
                "name": b_data.get("name", "Cụm"),
                "output_folder": folder,
                "count": len(b_data.get("items", [])),
                "is_active": (b_id == app_state.active_batch_id)
            })
        return {
            "batches": batch_list,
            "active_batch_id": app_state.active_batch_id,
            "total_clips": sum(len(b.get("items", [])) for b in app_state.batches.values())
        }

@app.post("/api/batches/create")
def create_batch(req: BatchCreateRequest):
    new_id = app_state.create_batch(name=req.name, output_folder=req.output_folder)
    _sse_bus.push("batches_changed", {"action": "create", "id": new_id})
    return {"status": "ok", "batch_id": new_id, "active_batch_id": app_state.active_batch_id}

@app.post("/api/batches/switch")
def switch_batch(req: BatchSwitchRequest):
    if not app_state.switch_batch(req.batch_id):
        raise HTTPException(status_code=404, detail="Batch not found")
    _sse_bus.push("batches_changed", {"action": "switch", "id": req.batch_id})
    return {"status": "ok", "active_batch_id": app_state.active_batch_id, "clips": list(app_state.edit_queue)}

@app.post("/api/batches/rename")
def rename_batch(req: BatchRenameRequest):
    with STATE_LOCK:
        if req.batch_id not in app_state.batches:
            raise HTTPException(status_code=404, detail="Batch not found")
        app_state.batches[req.batch_id]["name"] = req.name.strip() or "Cụm"
        app_state.save_session()
    _sse_bus.push("batches_changed", {"action": "rename", "id": req.batch_id})
    return {"status": "ok"}

@app.post("/api/batches/update_folder")
def update_batch_folder(req: BatchFolderRequest):
    with STATE_LOCK:
        if req.batch_id not in app_state.batches:
            raise HTTPException(status_code=404, detail="Batch not found")
        app_state.batches[req.batch_id]["output_folder"] = req.output_folder.strip()
        app_state.save_session()
    _sse_bus.push("batches_changed", {"action": "update_folder", "id": req.batch_id})
    return {"status": "ok"}

@app.post("/api/batches/delete")
def delete_batch(req: BatchDeleteRequest):
    if not app_state.delete_batch(req.batch_id):
        raise HTTPException(status_code=400, detail="Cannot delete last batch or batch not found")
    _sse_bus.push("batches_changed", {"action": "delete", "id": req.batch_id})
    return {"status": "ok", "active_batch_id": app_state.active_batch_id, "clips": list(app_state.edit_queue)}


# ── Preview Composite Generator ───────────────────────────────────────────────


def _extract_first_frame(clip: Path) -> Optional[Image.Image]:
    """Extract first frame in-memory in < 15ms using OpenCV VideoCapture with pipe fallback."""
    key = str(clip)
    if key in app_state.frame_cache:
        return app_state.frame_cache[key]
    if not clip.exists():
        return None

    # 1. Ultra-fast in-memory frame capture via OpenCV (0 subprocesses, ~10ms)
    try:
        cap = cv2.VideoCapture(str(clip))
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None and frame.size > 0:
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                app_state.frame_cache[key] = img
                return img
    except Exception:
        pass

    # 2. In-memory FFmpeg pipe fallback (no temporary files on disk)
    cmd = [FFMPEG, "-y", "-ss", "0.0", "-i", str(clip), "-vframes", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"]
    try:
        r = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if r.returncode == 0 and r.stdout and len(r.stdout) > 100:
            img = Image.open(io.BytesIO(r.stdout)).convert("RGB")
            app_state.frame_cache[key] = img
            return img
    except Exception:
        pass

    return None


def _cv2_render_preview(src_img: Image.Image, W: int, H: int, st: Dict[str, Any], title_text: str = "", no_title: bool = True) -> bytes:
    """Ultra-fast C++ SIMD & OpenCV matrix rendering for preview frames (< 25 ms)."""
    src = cv2.cvtColor(np.array(src_img), cv2.COLOR_RGB2BGR)
    src_h, src_w = src.shape[:2]

    # Mask & crop parameters
    cpt = max(0.0, min(0.48, float(st.get("crop_top",    st.get("source_mask_top",    0.0)))))
    cpb = max(0.0, min(0.48, float(st.get("crop_bottom", st.get("source_mask_bottom", 0.0)))))
    cpl = max(0.0, min(0.48, float(st.get("crop_left",   0.0))))
    cpr = max(0.0, min(0.48, float(st.get("crop_right",  0.0))))
    if cpt + cpb > 0.96:
        cpb = max(0.0, 0.96 - cpt)
    if cpl + cpr > 0.96:
        cpr = max(0.0, 0.96 - cpl)

    # Background layer: Blur / Image / Video
    bg_type = st.get("bg_type", "blur")
    bg_img_p = st.get("bg_image_path", "")
    bg_vid_p = st.get("bg_video_path", "")
    _v_exts = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".ts", ".m4v", ".flv", ".wmv"}

    bg_path = None
    is_video_bg = False
    if bg_type == "video" and bg_vid_p and Path(bg_vid_p).exists():
        bg_path = bg_vid_p
        is_video_bg = True
    elif bg_type == "image" and bg_img_p and Path(bg_img_p).exists():
        bg_path = bg_img_p
        is_video_bg = Path(bg_img_p).suffix.lower() in _v_exts
    elif bg_vid_p and Path(bg_vid_p).exists():
        bg_path = bg_vid_p
        is_video_bg = True
    elif bg_img_p and Path(bg_img_p).exists():
        bg_path = bg_img_p
        is_video_bg = Path(bg_img_p).suffix.lower() in _v_exts

    bg = None
    if bg_path:
        try:
            if is_video_bg:
                b_pil = _extract_first_frame(Path(bg_path))
                if b_pil is not None:
                    b_raw = cv2.cvtColor(np.array(b_pil), cv2.COLOR_RGB2BGR)
                else:
                    b_raw = None
            else:
                buf   = np.fromfile(bg_path, dtype=np.uint8)
                b_raw = cv2.imdecode(buf, cv2.IMREAD_COLOR)

            if b_raw is not None:
                bh_r, bw_r = b_raw.shape[:2]
                r = bw_r / bh_r
                tr = W / H
                s = H / bh_r if r > tr else W / bw_r
                bw, bh = int(bw_r * s), int(bh_r * s)
                b_resized = cv2.resize(b_raw, (bw, bh), interpolation=cv2.INTER_LINEAR)
                cx, cy = max(0, (bw - W) // 2), max(0, (bh - H) // 2)
                bg = b_resized[cy:cy+H, cx:cx+W]
        except Exception:
            pass

    if bg is None or bg.shape[0] != H or bg.shape[1] != W:
        # Default: Fast blurred background from video frame using OpenCV
        src_for_bg = src
        if cpt > 0 or cpb > 0:
            t_px = int(src_h * cpt)
            b_px = int(src_h * cpb)
            src_for_bg = src[t_px:max(t_px + 10, src_h - b_px), :]

        sb_h, sb_w = src_for_bg.shape[:2]
        r = sb_w / sb_h
        tr = W / H
        s = H / sb_h if r > tr else W / sb_w
        bw, bh = int(sb_w * s), int(sb_h * s)
        b_resized = cv2.resize(src_for_bg, (bw, bh), interpolation=cv2.INTER_LINEAR)
        cx, cy = max(0, (bw - W) // 2), max(0, (bh - H) // 2)
        bg_cropped = b_resized[cy:cy+H, cx:cx+W]
        # Fast C++ OpenCV Gaussian Blur (kernel 31x31)
        bg = cv2.GaussianBlur(bg_cropped, (31, 31), 16)

    # Foreground video frame crop & scaling
    vw_scale = float(st.get("video_w_scale", 1.0))
    vh_scale = float(st.get("video_h_scale", 1.0))
    fg_w = int(W * vw_scale)
    fg_h_orig = int(W * (src_h / src_w) * vh_scale)
    fg_h = max(10, fg_h_orig)
    fg = cv2.resize(src, (fg_w, fg_h), interpolation=cv2.INTER_LINEAR)

    # 1. Flip H / Flip V
    if st.get("flip_h", False):
        fg = cv2.flip(fg, 1)
    if st.get("flip_v", False):
        fg = cv2.flip(fg, 0)

    # 2 & 3. Color Grade / Saturation / Contrast
    color_grade = st.get("color_grade", False)
    sat = float(st.get("saturation", 1.0))
    if color_grade or abs(sat - 1.0) > 0.01:
        hsv = cv2.cvtColor(fg, cv2.COLOR_BGR2HSV).astype(np.float32)
        if color_grade:
            hsv[:, :, 1] *= 1.18
            hsv[:, :, 2] = np.clip(hsv[:, :, 2] * 1.08, 0, 255)
        if abs(sat - 1.0) > 0.01:
            hsv[:, :, 1] *= sat
        hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)
        fg = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 4. Hue Shift
    hue_deg = int(st.get("hue_shift", 0))
    if hue_deg != 0:
        hsv = cv2.cvtColor(fg, cv2.COLOR_BGR2HSV)
        hsv[:, :, 0] = (hsv[:, :, 0].astype(int) + int(hue_deg * 180 / 360)) % 180
        fg = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    # 5. Film Grain Noise (vectorized NumPy array addition)
    if st.get("add_grain", False):
        grain_s = max(1, min(10, int(st.get("grain_strength", 3))))
        noise = np.random.randint(-grain_s * 4, grain_s * 4, fg.shape, dtype=np.int16)
        fg = np.clip(fg.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # 6. Micro Rotate (1.2 deg)
    if st.get("micro_rotate", False):
        center = (fg_w // 2, fg_h // 2)
        M = cv2.getRotationMatrix2D(center, 1.2, 1.0)
        fg = cv2.warpAffine(fg, M, (fg_w, fg_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    # 7. Smart Zoom (2% Crop)
    if st.get("smart_zoom", False):
        zx = int(fg_w * 0.01)
        zy = int(fg_h * 0.01)
        if fg_w - 2*zx > 5 and fg_h - 2*zy > 5:
            fg_cropped = fg[zy:fg_h-zy, zx:fg_w-zx]
            fg = cv2.resize(fg_cropped, (fg_w, fg_h), interpolation=cv2.INTER_LINEAR)

    # 8. Vignette 3D (Dark Corners) Preview
    if st.get("vignette", False):
        rows, cols = fg.shape[:2]
        if rows > 10 and cols > 10:
            # vignette_strength 5–100: controls sigma — smaller σ = more aggressive darkening
            _vs = max(5, min(100, int(st.get("vignette_strength", 50))))
            _sigma_factor = 0.80 - (_vs / 100.0) * 0.51  # 0.75 → 0.29
            kernel_x = cv2.getGaussianKernel(cols, cols * _sigma_factor)
            kernel_y = cv2.getGaussianKernel(rows, rows * _sigma_factor)
            kernel = kernel_y * kernel_x.T
            mask = kernel / (kernel.max() or 1.0)
            vignette_mask = np.dstack([mask] * 3)
            # amplify: center stays bright (≥1.0), corners clamp to (1-strength) darkness
            _amp      = 1.0 + (_vs / 100.0) * 0.5      # 1.025 → 1.5
            _min_lum  = max(0.0, 1.0 - (_vs / 100.0) * 0.75)  # 0.9625 → 0.25
            vignette_mask = np.clip(vignette_mask * _amp, _min_lum, 1.0)
            fg = (fg.astype(np.float32) * vignette_mask).astype(np.uint8)



    # Source mask & 4-edge crop
    _rem_h = max(0.01, 1.0 - cpt - cpb)
    _rem_w = max(0.01, 1.0 - cpl - cpr)
    if cpt > 0 or cpb > 0 or cpl > 0 or cpr > 0:
        crop_top_px = int(fg_h_orig * cpt)
        crop_bot_px = int(fg_h_orig * cpb)
        crop_l_px   = int(fg_w * cpl)
        crop_r_px   = int(fg_w * cpr)
        fg = fg[crop_top_px:max(crop_top_px + 10, fg_h_orig - crop_bot_px),
                crop_l_px:max(crop_l_px + 10, fg_w - crop_r_px)]

    curr_fgh = fg.shape[0]
    curr_fgw = fg.shape[1]
    vx_px = int(float(st.get("video_x", 0)) * (W / 1080.0))
    vy_px = int(float(st.get("video_y", 0)) * (W / 1080.0))
    vy = int((H - curr_fgh / _rem_h) / 2 + vy_px + cpt * curr_fgh / _rem_h)
    vx = int((W - curr_fgw / _rem_w) / 2 + vx_px + cpl * curr_fgw / _rem_w)

    # Composite FG onto BG canvas safely
    canvas = bg.copy()
    y1, y2 = max(0, vy), min(H, vy + curr_fgh)
    x1, x2 = max(0, vx), min(W, vx + curr_fgw)
    fg_y1 = max(0, -vy)
    fg_y2 = fg_y1 + (y2 - y1)
    fg_x1 = max(0, -vx)
    fg_x2 = fg_x1 + (x2 - x1)

    if y2 > y1 and x2 > x1 and fg_y2 > fg_y1 and fg_x2 > fg_x1:
        canvas[y1:y2, x1:x2] = fg[fg_y1:fg_y2, fg_x1:fg_x2]

    # ── Blur Regions (OpenCV Gaussian Blur — instant) ────────────────────────
    for _box in st.get("blur_boxes", []):
        try:
            bx = max(0, int(_box.get("x", 0) * (W / 1080.0)))
            by = max(0, int(_box.get("y", 0) * (H / 1920.0)))
            bw = max(2, int(_box.get("w", 100) * (W / 1080.0)))
            bh = max(2, int(_box.get("h", 100) * (H / 1920.0)))
            bw = min(bw, W - bx)
            bh = min(bh, H - by)
            if bw > 2 and bh > 2:
                sub = canvas[by:by+bh, bx:bx+bw]
                kw = (bw // 4) * 2 + 1
                kh = (bh // 4) * 2 + 1
                canvas[by:by+bh, bx:bx+bw] = cv2.GaussianBlur(sub, (max(3, kw), max(3, kh)), 12)
        except Exception:
            pass

    # ── Auto MD5 Hash Badge in Live Preview ─────────────────────────────────
    if st.get("change_md5", True):
        try:
            cv2.rectangle(canvas, (W - 105, 8), (W - 8, 24), (20, 30, 20), -1)
            cv2.rectangle(canvas, (W - 105, 8), (W - 8, 24), (60, 180, 60), 1)
            cv2.putText(canvas, "MD5: AUTO-SHIFT", (W - 101, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (120, 240, 120), 1, cv2.LINE_AA)
        except Exception:
            pass

    ok, buf = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return buf.tobytes() if ok else b""



@app.post("/api/preview")
def generate_preview(req: PreviewRequest, request: FastAPIRequest):
    clip_p = Path(req.clip_path)
    if not clip_p.exists():
        img = Image.new("RGB", (req.width, req.height), (20, 20, 25))
        draw = ImageDraw.Draw(img)
        draw.text((req.width//2, req.height//2), "Video File Not Found", fill=(220, 80, 80), anchor="mm")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        raw_b = buf.getvalue()
        if "image/jpeg" in request.headers.get("accept", ""):
            return Response(content=raw_b, media_type="image/jpeg")
        return {"b64": base64.b64encode(raw_b).decode("utf-8")}

    src = _extract_first_frame(clip_p)
    if src is None:
        img = Image.new("RGB", (req.width, req.height), (15, 15, 20))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        raw_b = buf.getvalue()
        if "image/jpeg" in request.headers.get("accept", ""):
            return Response(content=raw_b, media_type="image/jpeg")
        return {"b64": base64.b64encode(raw_b).decode("utf-8")}

    jpeg_bytes = _cv2_render_preview(src, req.width, req.height, req.state, req.title, req.no_title)
    
    # Direct binary JPEG response when Accept: image/jpeg header is sent by frontend
    if "image/jpeg" in request.headers.get("accept", ""):
        return Response(content=jpeg_bytes, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    
    # Fallback Base64 JSON response for standard callers
    return {"b64": base64.b64encode(jpeg_bytes).decode("utf-8")}

# ── Gemini Analysis Execution ─────────────────────────────────────────────────

def _run_single_analysis(
    video_path: Path,
    rotator: "KeyRotator",
    model_name: str,
    stop_event: threading.Event,
    log: Any,
    include_cta: bool = False,
    mode: str = "short",   # "short" | "story"
):
    """
    Standalone replication of CliperApp._run_analysis logic.
    Calls top-level functions from app.py directly (no Tkinter class needed).
    Updates app_state.video_results in-place.
    """
    norm_k = _norm_path(video_path)
    if not video_path.exists():
        log("error", f"[{video_path.name}] File not found on disk.")
        app_state.video_results[norm_k] = {
            "status": ST_ERROR, "candidates": [], "error": "File not found"
        }
        return

    app_state.video_results[norm_k] = {
        "status": ST_UPLOADING, "candidates": [], "error": ""
    }

    result = None
    last_exc = None
    vid_dur_hint: Optional[float] = None
    n_keys = len(rotator)

    # ── Encode proxy/timelapse ONCE before any retry attempts ─────────────────
    # Previously this was inside the retry loop, causing re-encoding on every
    # key rotation (up to 8x FFmpeg encodes for a single video). Moved here so
    # we pay the encode cost exactly once.
    vid_dur_hint = get_video_duration(video_path)
    if vid_dur_hint:
        log("info", f"[{video_path.name}] Duration: {int(vid_dur_hint//60):02d}m{int(vid_dur_hint%60):02d}s")

    ds_path, ds_cleanup, ds_speedup = _downsample_for_upload(video_path, _make_logger(log))

    try:
      for attempt in range(n_keys):
        if stop_event.is_set():
            app_state.video_results[norm_k] = {
                "status": ST_ERROR, "candidates": [], "error": "Stopped"
            }
            return

        key    = rotator.acquire()   # Least Connections: picks fewest-active, non-cooled key
        remote = None
        client = None
        sdk    = None

        try:
            client, sdk = build_client(key)

            app_state.video_results[norm_k]["status"] = ST_UPLOADING

            remote = upload_video(client, sdk, ds_path, _make_logger(log), stop_event)

            app_state.video_results[norm_k]["status"] = ST_ANALYZING
            scaled_dur = (vid_dur_hint / ds_speedup) if vid_dur_hint else None

            result = analyze_video(
                client, sdk, remote,
                video_path.name, _make_logger(log), stop_event,
                vid_duration=scaled_dur,
                model_name=model_name,
                include_cta=include_cta,
                mode=mode,
            )

            # Scale timestamps from sped-up timeline back to original
            if ds_speedup != 1.0 and result and result.get("candidates"):
                for cand in result["candidates"]:
                    raw_ts = ts_to_seconds(cand.get("start_time", "00:00:00"))
                    orig_s = raw_ts * ds_speedup
                    h = int(orig_s // 3600)
                    m = int((orig_s % 3600) // 60)
                    s = int(orig_s % 60)
                    cand["start_time"] = f"{h:02d}:{m:02d}:{s:02d}"

            # Correction loop: retry with rejected timestamps feedback
            MAX_CORRECTIONS = 3
            for corr in range(MAX_CORRECTIONS):
                raw_cands = result.get("candidates", [])
                # Dùng min duration đúng theo mode khi kiểm tra max_t
                _min_dur = MIN_STORY_DUR if mode == "story" else CLIP_DURATION
                max_t = max(0.0, (vid_dur_hint or float("inf")) - _min_dur)
                invalid = [c for c in raw_cands
                           if not (0.0 <= ts_to_seconds(c.get("start_time", "99:00:00")) <= max_t)]
                if len(invalid) < len(raw_cands):
                    break  # at least some are valid
                if vid_dur_hint:
                    rescued = _reinterpret_mmss(raw_cands, vid_dur_hint)
                    if rescued:
                        break
                if stop_event.is_set():
                    raise InterruptedError("Stopped by user.")
                rejected_ts = [c.get("start_time", "??") for c in invalid]
                log("warn", f"[{video_path.name}] Correction {corr+1}/{MAX_CORRECTIONS}: {rejected_ts} invalid — retrying")
                app_state.video_results[norm_k]["status"] = ST_ANALYZING
                result = analyze_video(
                    client, sdk, remote,
                    video_path.name, _make_logger(log), stop_event,
                    vid_duration=vid_dur_hint,
                    rejected_timestamps=rejected_ts,
                    mode=mode,
                )

        except InterruptedError:
            app_state.video_results[norm_k] = {
                "status": ST_ERROR, "candidates": [], "error": "Stopped"
            }
            return

        except Exception as exc:
            last_exc = exc
            err_str  = str(exc)
            err_lower = err_str.lower()
            is_quota = any(kw in err_lower for kw in (
                "quota", "429", "rate limit",
                "resource_exhausted", "too many requests",
            ))
            is_tcp = "10053" in err_str or "10054" in err_str

            # Apply cooldown to the failed key so acquire() steers clear of it.
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
                log("warn", f"[{video_path.name}] Attempt {attempt+1}/{n_keys} failed [{label}]: {str(exc)[:60]} — trying next key…")
                time.sleep(0.5)   # brief pause before next acquire; cooldown handles key selection
            else:
                log("error", f"[{video_path.name}] All {n_keys} API keys failed: {exc}")
                app_state.video_results[norm_k] = {
                    "status": ST_ERROR, "candidates": [], "error": str(exc)[:80]
                }
                return

        else:
            break  # success

        finally:
            rotator.release(key)   # always decrement active counter
            if remote is not None and client is not None and sdk is not None:
                try:
                    delete_remote(client, sdk, remote, _make_logger(log))
                except Exception:
                    pass

    finally:
        # Always clean up the proxy/timelapse temp file after all retries finish.
        if ds_cleanup:
            try:
                ds_path.unlink(missing_ok=True)
            except Exception:
                pass

    # Post-process: validate & filter timestamps
    if result:
        candidates = result.get("candidates", [])
        vid_dur = get_video_duration(video_path)
        if vid_dur is not None and candidates:
            _min_dur = MIN_STORY_DUR if mode == "story" else CLIP_DURATION
            max_valid = max(0.0, vid_dur - _min_dur)

            def _is_valid(c):
                t = ts_to_seconds(c.get("start_time", "99:00:00"))
                return 0.0 <= t <= max_valid

            valid = [c for c in candidates if _is_valid(c)]
            if len(valid) < len(candidates):
                rescued = _reinterpret_mmss([c for c in candidates if not _is_valid(c)], vid_dur)
                valid = valid + rescued
            if not valid and vid_dur <= _min_dur + 2:
                valid = candidates  # Short clip — accept all
            candidates = valid

        if not candidates:
            app_state.video_results[norm_k] = {
                "status": ST_ERROR, "candidates": [], "error": "All timestamps invalid — retry analysis"
            }
            app_state.save_session()
            return

        log("ok", f"[{video_path.name}] {len(candidates)} valid candidate(s) ready.")
        app_state.video_results[norm_k] = {
            "status": ST_DONE, "candidates": candidates, "error": ""
        }
        app_state.save_session()
        _sse_bus.push("videos_changed", {"path": str(video_path), "status": ST_DONE})
        # Submit background precut: dùng clip_duration của từng candidate (Story Mode có duration riêng)
        _BG_PRECUT_EXECUTOR.submit(_precut_all_candidates, video_path, candidates)

    elif last_exc:
        app_state.video_results[norm_k] = {
            "status": ST_ERROR, "candidates": [], "error": str(last_exc)[:80]
        }
        app_state.save_session()
        _sse_bus.push("videos_changed", {"path": str(video_path), "status": ST_ERROR})



_PREVIEW_IN_FLIGHT: dict[str, threading.Event] = {}
_PREVIEW_IN_FLIGHT_LOCK = threading.Lock()

def _precut_preview(video_path: Path, start_sec: float, dur: float = 16.0,
                    bg_idle: bool = False) -> Path | None:
    """Pre-cut preview clip with stream-copy fast path.

    Priority tiers (Windows creationflags):
      bg_idle=False (user click) → ABOVE_NORMAL_PRIORITY_CLASS (0x8000)
          Beats all background analysis/proxy FFmpeg processes. Guarantees <0.2s
          stream-copy on any machine regardless of concurrent analysis load.
      bg_idle=True  (background warm-up) → IDLE_PRIORITY_CLASS (0x40)
          Yields to everything. Fills cache silently during analysis dead time.
    """


    vid_dur = get_video_duration(video_path) or 0.0
    if vid_dur > 0 and start_sec >= max(0.0, vid_dur - 1.0):
        start_sec = 0.0

    # Cache key bao gồm cả dur — tránh serve nhầm clip 16s cho candidate Story dài hơn
    cache_key = f"{video_path}|{start_sec:.1f}|{dur:.0f}"
    with _PREVIEW_CACHE_LOCK:
        if cache_key in _PREVIEW_CACHE and _PREVIEW_CACHE[cache_key].exists() and _PREVIEW_CACHE[cache_key].stat().st_size > 500:
            _PREVIEW_CACHE.move_to_end(cache_key)   # mark as recently used
            return _PREVIEW_CACHE[cache_key]

    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", video_path.stem[:30])
    out = _PREVIEW_DIR / f"prev_{safe}_{int(start_sec)}.mp4"

    # Fast return if already completed on disk
    if out.exists() and out.stat().st_size > 500:
        with _PREVIEW_CACHE_LOCK:
            _preview_cache_insert(cache_key, out)
        return out

    # Deduplicate concurrent encode jobs for the exact same clip timestamp
    ev = None
    is_leader = False
    with _PREVIEW_IN_FLIGHT_LOCK:
        if cache_key in _PREVIEW_IN_FLIGHT:
            ev = _PREVIEW_IN_FLIGHT[cache_key]
        else:
            ev = threading.Event()
            _PREVIEW_IN_FLIGHT[cache_key] = ev
            is_leader = True

    if not is_leader and ev:
        # Wait for the in-progress leader encoder to finish (up to 12s)
        ev.wait(timeout=12.0)
        with _PREVIEW_CACHE_LOCK:
            if cache_key in _PREVIEW_CACHE and _PREVIEW_CACHE[cache_key].exists():
                return _PREVIEW_CACHE[cache_key]
        if out.exists() and out.stat().st_size > 500:
            return out

    tmp_out = _PREVIEW_DIR / f"prev_{safe}_{int(start_sec)}_t{threading.current_thread().ident}_{int(time.time()*1000)}.mp4"
    try:
        # 0. FAST PATH: stream-copy (no re-encode) — near-instant (<0.5s) on any machine.
        #    Cuts at nearest keyframe → start may be slightly off but fine for previews.
        #    This eliminates the 20-30s cold-start wait on new machines with no cache.
        cmd_copy = [
            FFMPEG, "-y",
            "-ss", str(start_sec),
            "-i", str(video_path),
            "-t", str(dur),
            "-c", "copy",          # zero re-encode cost
            "-sn", "-dn",
            "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",
            "-f", "mp4", str(tmp_out),
        ]
        _NO_WIN   = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # 0x08000000
        _PRIORITY = 0x00000040 if bg_idle else 0x00008000       # IDLE vs ABOVE_NORMAL
        _FLAGS    = _NO_WIN | _PRIORITY
        r_copy = subprocess.run(
            cmd_copy,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=12,   # ↑ 6→12s: disk may be under pressure from parallel analysis uploads
            creationflags=_FLAGS,
        )
        if r_copy.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 500:
            try:
                tmp_out.replace(out)
            except Exception:
                pass
            target = out if out.exists() else tmp_out
            with _PREVIEW_CACHE_LOCK:
                _preview_cache_insert(cache_key, target)
            return target

        # 1. Fallback: x264 ultrafast re-encode at 640px (slower but always works)
        #    Used when stream copy fails (e.g., container issues, codec mismatch).
        cmd_cpu = [
            FFMPEG, "-y",
            "-ss", str(start_sec),
            "-i", str(video_path),
            "-t", str(dur),
            "-sn", "-dn",
            "-vf", "scale=640:-2",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "fastdecode",
            "-crf", "28",
            "-threads", "4",
            "-g", "15",
            "-c:a", "aac", "-b:a", "96k",
            "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",
            "-f", "mp4", str(tmp_out),
        ]
        r = subprocess.run(
            cmd_cpu,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=20,   # ↑ 10→20s: allow more time when disk is busy with analysis
            creationflags=_FLAGS,
        )
        if r.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 500:
            try:
                tmp_out.replace(out)
            except Exception:
                pass
            target = out if out.exists() else tmp_out
            with _PREVIEW_CACHE_LOCK:
                _preview_cache_insert(cache_key, target)
            return target
    except Exception:
        pass
    finally:
        with _PREVIEW_IN_FLIGHT_LOCK:
            if cache_key in _PREVIEW_IN_FLIGHT:
                _PREVIEW_IN_FLIGHT[cache_key].set()
                del _PREVIEW_IN_FLIGHT[cache_key]
        try:
            if tmp_out.exists() and tmp_out != out:
                tmp_out.unlink(missing_ok=True)
        except Exception:
            pass

    return None


def _generate_thumbnail(video_path: Path, start_sec: float) -> "Path | None":
    """Extract a single frame (90×160 JPEG) for the candidate at *start_sec*.

    Prefers reading from the already-precut preview clip to avoid seeking a
    large source file. Cached in _THUMBNAIL_CACHE with a 2000-entry LRU cap
    (≈10 MB total — thumbnail size is negligible compared to preview clips).
    """
    key = f"{video_path}|{start_sec:.1f}"
    with _THUMBNAIL_CACHE_LOCK:
        if key in _THUMBNAIL_CACHE and _THUMBNAIL_CACHE[key].exists():
            _THUMBNAIL_CACHE.move_to_end(key)
            return _THUMBNAIL_CACHE[key]

    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", video_path.stem[:30])
    out  = _THUMBNAIL_DIR / f"thumb_{safe}_{int(start_sec)}.jpg"
    if out.exists() and out.stat().st_size > 100:
        with _THUMBNAIL_CACHE_LOCK:
            _THUMBNAIL_CACHE[key] = out
        return out

    # Prefer reading from the already-precut preview clip when cached
    with _PREVIEW_CACHE_LOCK:
        src_path = _PREVIEW_CACHE.get(key)
    if src_path is None or not src_path.exists():
        src_path = video_path

    read_ss = 0.0 if src_path != video_path else start_sec
    try:
        r = subprocess.run(
            [
                FFMPEG, "-y",
                "-ss", str(read_ss),
                "-i", str(src_path),
                "-vframes", "1",
                "-vf", "scale=90:160:force_original_aspect_ratio=increase,crop=90:160",
                "-q:v", "5",
                str(out),
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x00000040,  # IDLE
        )
        if r.returncode == 0 and out.exists() and out.stat().st_size > 100:
            with _THUMBNAIL_CACHE_LOCK:
                while len(_THUMBNAIL_CACHE) >= 2000:
                    _THUMBNAIL_CACHE.popitem(last=False)
                _THUMBNAIL_CACHE[key] = out
            return out
    except Exception:
        pass
    return None



def _precut_all_candidates(video_path: Path, candidates: list):
    """Warm the preview cache for the first N candidates at IDLE priority.

    Dùng clip_duration từng candidate (16s cho Short Mode, 30-90s cho Story Mode).
    Runs inside _BG_PRECUT_EXECUTOR (max_workers=1) so only ONE precut FFmpeg
    process runs globally at any time.
    """
    for cand in candidates[:3]:
        if app_state.stop_event.is_set():
            return
        start_sec = ts_to_seconds(cand.get("start_time", "00:00:00"))
        # Lấy clip_duration từng candidate; fallback về CLIP_DURATION (16s) nếu thiếu
        cand_dur = float(cand.get("clip_duration", CLIP_DURATION))
        _precut_preview(video_path, start_sec, cand_dur, bg_idle=True)
        _generate_thumbnail(video_path, start_sec)




def _make_logger(log_fn):
    """Adapt a simple (level, msg) callable into a ToolLogger-compatible object."""
    class _AdaptedLogger:
        def info(self, msg):  log_fn("info", msg)
        def ok(self, msg):    log_fn("ok",   msg)
        def warn(self, msg):  log_fn("warn", msg)
        def error(self, msg): log_fn("error", msg)
        def dim(self, msg):   log_fn("dim",  msg)
        def header(self, msg): log_fn("info", msg)
    return _AdaptedLogger()


def _run_single_youtube_analysis(
    url: str,
    rotator: KeyRotator,
    model_name: str,
    stop_event: threading.Event,
    log: Any,
    include_cta: bool = False,
    mode: str = "short",
):
    url = url.strip()
    norm_k = url

    # Fetch metadata if not yet cached
    yt_meta = getattr(app_state, "yt_metadata", {}).get(norm_k, {})
    vid_title = yt_meta.get("title")
    vid_dur = yt_meta.get("duration")
    if not vid_title:
        try:
            cookie_browser = app_state.config.get("youtube_cookie_browser", None)
            info = get_youtube_info(url, cookies_browser=cookie_browser)
            if info:
                vid_title = info.get("title")
                vid_dur = info.get("duration")
                if not hasattr(app_state, "yt_metadata"):
                    app_state.yt_metadata = {}
                app_state.yt_metadata[norm_k] = info
                app_state.save_session()
        except Exception as e:
            log("warn", f"[{url}] Warning fetching YouTube info: {e}")

    vid_title = vid_title or "YouTube Video"

    with STATE_LOCK:
        app_state.video_results[norm_k] = {
            "status": ST_ANALYZING, "candidates": [], "error": ""
        }
        app_state.save_session()
    _sse_bus.push("videos_changed", {"path": norm_k, "status": ST_ANALYZING})

    log("info", f"🔍 [YouTube: {vid_title}] Analyzing with Gemini Visual AI ({mode.upper()} mode)...")

    n_keys = len(rotator.peek_all())
    result = None
    last_exc = None

    for attempt in range(max(1, n_keys)):
        if stop_event.is_set():
            with STATE_LOCK:
                app_state.video_results[norm_k] = {
                    "status": ST_ERROR, "candidates": [], "error": "Stopped by user"
                }
                app_state.save_session()
            _sse_bus.push("videos_changed", {"path": norm_k, "status": ST_ERROR})
            return

        key = rotator.acquire()
        client = None
        sdk = None
        try:
            client, sdk = build_client(key)
            result = analyze_video(
                client, sdk, url, vid_title,
                _make_logger(log),
                stop_event,
                vid_duration=vid_dur,
                model_name=model_name,
                include_cta=include_cta,
                mode=mode,
            )
            rotator.release(key)
            break
        except Exception as exc:
            rotator.penalize(key, KeyRotator.COOLDOWN_GENERIC)
            rotator.release(key)
            last_exc = exc
            log("warn", f"[{vid_title}] Key [...{key[-6:]}] failed: {str(exc)[:80]}")
            if attempt < n_keys - 1:
                time.sleep(0.5)
            else:
                log("error", f"[{vid_title}] All {n_keys} API keys failed: {exc}")
                with STATE_LOCK:
                    app_state.video_results[norm_k] = {
                        "status": ST_ERROR, "candidates": [], "error": str(exc)[:80]
                    }
                    app_state.save_session()
                _sse_bus.push("videos_changed", {"path": norm_k, "status": ST_ERROR})
                return

    if result:
        candidates = result.get("candidates", [])
        if vid_dur and candidates:
            _min_dur = MIN_STORY_DUR if mode == "story" else CLIP_DURATION
            max_valid = max(0.0, float(vid_dur) - _min_dur)
            valid = [c for c in candidates if 0.0 <= ts_to_seconds(c.get("start_time", "99:00:00")) <= max_valid]
            if len(valid) < len(candidates):
                rescued = _reinterpret_mmss([c for c in candidates if c not in valid], vid_dur)
                valid = valid + rescued
            candidates = valid if valid else candidates

        with STATE_LOCK:
            app_state.video_results[norm_k] = {
                "status": ST_DONE, "candidates": candidates, "error": ""
            }
            app_state.save_session()
        log("ok", f"✅ [YouTube: {vid_title}] Analysis complete ({len(candidates)} highlights ready)")
        _sse_bus.push("videos_changed", {"path": norm_k, "status": ST_DONE})
    elif last_exc:
        with STATE_LOCK:
            app_state.video_results[norm_k] = {
                "status": ST_ERROR, "candidates": [], "error": str(last_exc)[:80]
            }
            app_state.save_session()
        _sse_bus.push("videos_changed", {"path": norm_k, "status": ST_ERROR})


def _run_bulk_analysis_thread(
    keys: List[str],
    videos: List[Any],
    model_name: str,
    include_cta: bool = False,
    mode: str = "short",
):
    app_state.is_analyzing = True
    app_state.stop_event.clear()
    app_state.log(f"🚀 Starting analysis for {len(videos)} video(s) using model {model_name}...", "info")
    try:
        rotator = KeyRotator(keys)
        # Respect user-configured parallel limit (default 3, range 1-10)
        parallel = max(1, min(int(app_state.config.get("analysis_parallel", 3)), len(videos)))
        sem = threading.Semaphore(parallel)

        def _log(level: str, msg: str):
            app_state.log(msg, level)

        def _worker(v_path: Any):
            sem.acquire()
            is_yt = isinstance(v_path, str) and (v_path.startswith("http://") or v_path.startswith("https://"))
            v_name = v_path if is_yt else getattr(v_path, "name", str(v_path))
            try:
                if is_yt:
                    _run_single_youtube_analysis(
                        v_path, rotator, model_name, app_state.stop_event, _log,
                        include_cta=include_cta, mode=mode,
                    )
                else:
                    _run_single_analysis(
                        v_path, rotator, model_name, app_state.stop_event, _log,
                        include_cta=include_cta, mode=mode,
                    )
            except Exception as e:
                app_state.log(f"Analysis worker error [{v_name}]: {e}", "error")
                app_state.video_results[str(v_path)] = {
                    "status": ST_ERROR, "candidates": [], "error": str(e)[:80]
                }
            finally:
                sem.release()

        threads = [threading.Thread(target=_worker, args=(v,), daemon=True) for v in videos]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    except Exception as exc:
        app_state.log(f"Bulk analysis error: {exc}", "error")
    finally:
        app_state.is_analyzing = False
        app_state.log("🏁 Bulk analysis finished.", "info")




@app.post("/api/analyze/start")
def start_analysis(body: Dict[str, Any] = None):
    """Start bulk analysis. Accepts optional JSON body with 'mode' field.

    mode: 'short' (default) | 'story'
    """
    if body is None:
        body = {}
    keys = [k.strip() for k in app_state.config.get("api_keys", []) if k.strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="No Gemini API keys configured.")
    if not app_state.video_files:
        raise HTTPException(status_code=400, detail="No videos selected in queue.")

    if app_state.is_analyzing:
        return {"status": "running"}

    model       = app_state.config.get("model_name", MODEL_NAME)
    include_cta = bool(app_state.config.get("include_cta", False))
    mode        = str(body.get("mode", "short"))  # "short" | "story"
    if mode not in ("short", "story"):
        mode = "short"

    threading.Thread(
        target=_run_bulk_analysis_thread,
        args=(keys, list(app_state.video_files), model, include_cta, mode),
        daemon=True
    ).start()
    return {"status": "started", "total": len(app_state.video_files), "mode": mode}

@app.post("/api/analyze/stop")
def stop_analysis():
    app_state.stop_event.set()
    app_state.is_analyzing = False
    # Immediately mark all in-flight videos so the UI reflects the stop
    for k, v in list(app_state.video_results.items()):
        if v.get("status") in (ST_UPLOADING, ST_ANALYZING):
            app_state.video_results[k] = {
                "status": ST_ERROR, "candidates": [], "error": "Stopped by user"
            }
    app_state.log("⛔ Analysis stopped by user.", "warn")
    return {"status": "stopped"}


@app.post("/api/export/stop")
def stop_export():
    """Cancel the running export immediately. The render_reup polling loop checks
    export_cancel_event every 300 ms and kills FFmpeg as soon as it is set."""
    app_state.export_cancel_event.set()
    app_state.export_progress["status"] = "cancelled"
    app_state.export_progress["current"] = "Cancelled by user"
    app_state.log("⛔ Export cancelled by user.", "warn")
    return {"status": "cancelled"}


# ── AI Title Re-generation ─────────────────────────────────────────────────────

# ── Default title generation prompt (user-overridable) ───────────────────────
DEFAULT_TITLE_PROMPT = (
    "You generate short, viral, emotionally-charged YouTube Shorts / TikTok titles "
    "for bodycam footage.\n\n"
    "Clip context:\n"
    "- Description: {description}\n"
    "- Highlight reason: {highlight_reason}\n"
    "- Previous title: {old_title}\n\n"
    "Rules:\n"
    "1. ALL CAPS, 3-8 words max.\n"
    "2. No hashtags, no emoji, no quotes.\n"
    "3. Must be emotionally gripping — shock, urgency, outrage, or triumph.\n"
    "4. Output ONLY the title, nothing else."
)

# ── Preset storage directory ───────────────────────────────────────────────────
PROMPTS_DIR = Path("title_prompts")
PROMPTS_DIR.mkdir(exist_ok=True)
if hasattr(sys, "_MEIPASS"):
    _mei_prompts = Path(getattr(sys, "_MEIPASS")) / "title_prompts"
    if _mei_prompts.exists() and _mei_prompts.is_dir():
        for _f in _mei_prompts.glob("*.txt"):
            _dst = PROMPTS_DIR / _f.name
            if not _dst.exists():
                try:
                    shutil.copy2(_f, _dst)
                except Exception:
                    pass


class TitleGenRequest(BaseModel):
    video_path: str
    candidate_index: int = 0
    custom_prompt: Optional[str] = None  # per-call override; None = use config/default

@app.post("/api/generate_title")
def generate_title(req: TitleGenRequest):
    """Call Gemini to regenerate a viral title for a specific highlight candidate."""
    v_path = Path(req.video_path)
    res    = app_state.video_results.get(str(v_path), {})
    cands  = res.get("candidates", [])

    if req.candidate_index >= len(cands):
        raise HTTPException(status_code=400, detail="Candidate index out of range")

    cand  = cands[req.candidate_index]
    keys  = [k.strip() for k in app_state.config.get("api_keys", []) if k.strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="No Gemini API keys configured")

    description      = cand.get("description", "")
    highlight_reason = cand.get("highlight_reason", "")
    old_title        = cand.get("title", "")
    model_name       = app_state.config.get("model_name", MODEL_NAME)

    # Priority: per-call custom_prompt → config title_prompt → DEFAULT_TITLE_PROMPT
    raw_tpl = (
        req.custom_prompt
        or app_state.config.get("title_prompt")
        or DEFAULT_TITLE_PROMPT
    )
    prompt = raw_tpl.format(
        description=description,
        highlight_reason=highlight_reason,
        old_title=old_title,
    )

    try:
        rotator = app_state.get_rotator()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    for _ in range(max(1, len(rotator.peek_all()))):
        key = rotator.acquire()
        try:
            client, sdk = build_client(key)
            if sdk == "new":
                resp = client.models.generate_content(model=model_name, contents=prompt)
                new_title = resp.text.strip().upper()
            else:
                model_obj = client.GenerativeModel(model_name)
                resp = model_obj.generate_content(prompt)
                new_title = resp.text.strip().upper()

            rotator.release(key)
            if new_title:
                app_state.video_results[str(v_path)]["candidates"][req.candidate_index]["title"] = new_title
                app_state.log(f"Generated title for {v_path.name}[{req.candidate_index}]: {new_title}", "ok")
                return {"title": new_title}
        except Exception as e:
            rotator.penalize(key, KeyRotator.COOLDOWN_GENERIC)
            rotator.release(key)
            app_state.log(f"Title gen error [{key[-6:]}]: {e}", "warn")
            continue

    raise HTTPException(status_code=500, detail="All API keys failed for title generation")


# ── Preset management endpoints ────────────────────────────────────────────────

@app.get("/api/title_prompts")
def list_title_prompts():
    """Return names of all saved .txt preset files."""
    files = sorted(PROMPTS_DIR.glob("*.txt"))
    return {"presets": [f.stem for f in files]}


class SavePromptRequest(BaseModel):
    name: str
    content: str


@app.post("/api/title_prompts/save")
def save_title_prompt(req: SavePromptRequest):
    """Save prompt content to a named .txt preset file."""
    safe_name = re.sub(r"[^\w\- ]", "_", req.name.strip())[:60]
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid preset name")
    path = PROMPTS_DIR / f"{safe_name}.txt"
    path.write_text(req.content, encoding="utf-8")
    return {"status": "saved", "name": safe_name}


@app.delete("/api/title_prompts/{name}")
def delete_title_prompt(name: str):
    """Delete a named .txt preset file."""
    path = PROMPTS_DIR / f"{name}.txt"
    if path.exists():
        path.unlink()
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Preset not found")




@app.get("/api/title_prompts/{name}")
def get_title_prompt(name: str):
    """Return content of a named .txt preset file."""
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"name": name, "content": path.read_text(encoding="utf-8")}


# ── Edit-Style Presets (save/load full editState as JSON) ─────────────────────
EDIT_PRESETS_DIR = Path("edit_presets")
EDIT_PRESETS_DIR.mkdir(exist_ok=True)

# Fields excluded from a preset (clip-specific — differ per video)
_PRESET_EXCLUDE = {"title", "overlays", "blur_boxes", "sub_words", "sub_word_timings",
                   "track_results", "inpaint_status"}

class SaveEditPresetRequest(BaseModel):
    name: str
    state: Dict[str, Any]


@app.get("/api/edit_presets")
def list_edit_presets():
    files = sorted(EDIT_PRESETS_DIR.glob("*.json"))
    return {"presets": [f.stem for f in files]}


@app.post("/api/edit_presets/save")
def save_edit_preset(req: SaveEditPresetRequest):
    safe = re.sub(r"[^\w\- ]", "_", req.name.strip())[:60]
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid preset name")
    state = {k: v for k, v in req.state.items() if k not in _PRESET_EXCLUDE}
    path = EDIT_PRESETS_DIR / f"{safe}.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "saved", "name": safe}


@app.get("/api/edit_presets/{name}")
def get_edit_preset(name: str):
    path = EDIT_PRESETS_DIR / f"{name}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"name": name, "state": json.loads(path.read_text(encoding="utf-8"))}


@app.delete("/api/edit_presets/{name}")
def delete_edit_preset(name: str):
    path = EDIT_PRESETS_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Preset not found")


# ── Logo / Subtitle Auto-Detection endpoints ───────────────────────────────────

class DetectRequest(BaseModel):
    clip_path: str


def _get_item_state_and_dims(clip_path: str):
    """Retrieve item edit state and original video stream dimensions (vw, vh)."""
    p = Path(clip_path)
    st = {}
    with STATE_LOCK:
        for item in app_state.edit_queue:
            if item.get("clip_path") == str(p) or item.get("path") == str(p):
                st = item.get("state", {})
                break
    vw, vh = 1920, 1080
    if p.exists():
        import cv2
        cap = cv2.VideoCapture(str(p))
        if cap.isOpened():
            vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
            vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
            cap.release()
    return st, vw, vh


@app.post("/api/detect_logo")
async def api_detect_logo(req: DetectRequest):
    """
    Analyse a clip using temporal variance to find a static logo / watermark region.
    Returns mapped {bbox: {x,y,w,h}} in 1080x1920 canvas space or {bbox: null}.
    """
    p = Path(req.clip_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Clip not found")

    import asyncio
    loop = asyncio.get_event_loop()
    bbox = await loop.run_in_executor(None, detect_logo_bbox, str(p))

    if bbox is None:
        return {"bbox": None}
    ox, oy, ow, oh = bbox
    st, vw, vh = _get_item_state_and_dims(str(p))
    cx, cy, cw, ch = map_tracked_box_to_canvas({"x": ox, "y": oy, "w": ow, "h": oh}, vw, vh, st)
    return {"bbox": {"x": int(cx), "y": int(cy), "w": int(cw), "h": int(ch)}}


@app.post("/api/detect_subtitle")
async def api_detect_subtitle(req: DetectRequest):
    """
    Detect the burned-in subtitle band (bottom region) and when it first appears.
    Returns mapped {bbox: {x,y,w,h}, start_time: float} in 1080x1920 canvas space.
    """
    p = Path(req.clip_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Clip not found")

    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, detect_subtitle_region, str(p))

    if result is None:
        return {"bbox": None, "start_time": 0.0}
    ox, oy, ow, oh, start_time = result
    st, vw, vh = _get_item_state_and_dims(str(p))
    cx, cy, cw, ch = map_tracked_box_to_canvas({"x": ox, "y": oy, "w": ow, "h": oh}, vw, vh, st)
    return {
        "bbox": {"x": int(cx), "y": int(cy), "w": int(cw), "h": int(ch)},
        "start_time": round(start_time, 3),
    }


@app.post("/api/detect_subtitle_tracks")
async def api_detect_subtitle_tracks(req: DetectRequest):
    """
    Dynamic subtitle track detection: analyse the video frame-by-frame and return
    a list of time ranges and mapped 1080x1920 canvas bboxes.
    """
    p = Path(req.clip_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Clip not found")

    print(f"\n[🤖 AI Subtitle Scan] Scanning clip: {p.name}...", flush=True)
    import asyncio
    loop = asyncio.get_running_loop()
    tracks = await loop.run_in_executor(None, auto_detect_subtitle_tracks, str(p))
    st, vw, vh = _get_item_state_and_dims(str(p))
    mapped_tracks = []
    for tr in (tracks or []):
        nb = tr.get("bbox", [0, 0, 1, 1])
        ox = int(nb[0] * vw)
        oy = int(nb[1] * vh)
        ow = int(nb[2] * vw)
        oh = int(nb[3] * vh)
        cx, cy, cw, ch = map_tracked_box_to_canvas({"x": ox, "y": oy, "w": ow, "h": oh}, vw, vh, st)
        mapped_tracks.append({
            "start": tr.get("start", 0.0),
            "end": tr.get("end", 0.0),
            "bbox": {"x": int(cx), "y": int(cy), "w": int(cw), "h": int(ch)}
        })
    print(f"[🤖 AI Subtitle Scan] Scan Complete! Detected {len(mapped_tracks)} track(s) using {get_ocr_device()}.\n", flush=True)
    return {"tracks": mapped_tracks, "device": get_ocr_device()}


class BulkSubtitleRequest(BaseModel):
    clip_paths: List[str]     # ordered list matching edit queue indices
    box_mode: str = "delogo"  # blur | delogo


# Per-bulk-job progress: stored server-side so the frontend can poll
_bulk_sub_progress: Dict[str, Any] = {}
_bulk_sub_lock = threading.Lock()
_background_tasks = set()


@app.post("/api/detect_subtitle_tracks_bulk")
async def api_detect_subtitle_tracks_bulk(req: BulkSubtitleRequest):
    """
    Concurrent per-clip subtitle detection for all clips in the edit queue.
    Returns immediately with a job_id; client polls /api/detect_subtitle_tracks_bulk/{job_id}.

    Concurrency is capped by a semaphore (min(4, cpu_count)) because
    auto_detect_subtitle_tracks is OpenCV-heavy — running too many in parallel
    exhausts RAM.  Results are patched into app_state.edit_queue in-memory.
    """
    import uuid, os as _os
    job_id = uuid.uuid4().hex
    max_workers = min(4, max(1, (_os.cpu_count() or 2) // 2))

    with _bulk_sub_lock:
        _bulk_sub_progress[job_id] = {
            "status":       "running",
            "total":        len(req.clip_paths),
            "done":         0,
            "workers":      max_workers,
            "device":       get_ocr_device(),
            "current_clips": [],          # list of clip names currently in-flight
            "results":      {},           # clip_path → mapped tracks list
            "errors":       {},           # clip_path → error message
        }

    sem = asyncio.Semaphore(max_workers)

    async def _process_one(clip_path: str) -> None:
        """Scan one clip inside the semaphore gate."""
        p = Path(clip_path)
        async with sem:
            with _bulk_sub_lock:
                _bulk_sub_progress[job_id]["current_clips"].append(p.name)

            print(f"\n[🤖 Bulk Sub] ▶ {p.name}", flush=True)

            if not p.exists():
                with _bulk_sub_lock:
                    _bulk_sub_progress[job_id]["errors"][clip_path] = "File not found"
                    _bulk_sub_progress[job_id]["done"] += 1
                    _bulk_sub_progress[job_id]["current_clips"] = [
                        c for c in _bulk_sub_progress[job_id]["current_clips"] if c != p.name
                    ]
                return

            try:
                loop = asyncio.get_running_loop()
                tracks = await loop.run_in_executor(None, auto_detect_subtitle_tracks, str(p))
                st, vw, vh = _get_item_state_and_dims(str(p))

                mapped = []
                for tr in (tracks or []):
                    nb = tr.get("bbox", [0, 0, 1, 1])
                    ox, oy = int(nb[0] * vw), int(nb[1] * vh)
                    ow, oh = int(nb[2] * vw), int(nb[3] * vh)
                    cx, cy, cw, ch = map_tracked_box_to_canvas(
                        {"x": ox, "y": oy, "w": ow, "h": oh}, vw, vh, st
                    )
                    mapped.append({
                        "start": tr.get("start", 0.0),
                        "end":   tr.get("end",   0.0),
                        "bbox":  {"x": int(cx), "y": int(cy), "w": int(cw), "h": int(ch)},
                    })

                print(f"[🤖 Bulk Sub] ✅ {p.name} → {len(mapped)} track(s)", flush=True)

                # Patch edit queue in-memory — STATE_LOCK guards concurrent writes
                with STATE_LOCK:
                    for item in app_state.edit_queue:
                        if item.get("clip_path") == str(p) or item.get("path") == str(p):
                            existing = item.setdefault("state", {}).get("blur_boxes", [])
                            new_boxes = [
                                {
                                    "id":         f"sub_{i}_{tr['start']}",
                                    "x":          tr["bbox"]["x"],
                                    "y":          tr["bbox"]["y"],
                                    "w":          tr["bbox"]["w"],
                                    "h":          tr["bbox"]["h"],
                                    "mode":       req.box_mode,
                                    "start_time": tr["start"],
                                    "end_time":   tr["end"],
                                }
                                for i, tr in enumerate(mapped)
                            ]
                            item["state"]["blur_boxes"] = existing + new_boxes
                            break

                with _bulk_sub_lock:
                    _bulk_sub_progress[job_id]["results"][clip_path] = mapped

            except Exception as exc:
                print(f"[🤖 Bulk Sub] ❌ {p.name}: {exc}", flush=True)
                with _bulk_sub_lock:
                    _bulk_sub_progress[job_id]["errors"][clip_path] = str(exc)

            finally:
                with _bulk_sub_lock:
                    _bulk_sub_progress[job_id]["done"] += 1
                    _bulk_sub_progress[job_id]["current_clips"] = [
                        c for c in _bulk_sub_progress[job_id]["current_clips"] if c != p.name
                    ]

    async def _run_all():
        tasks = [asyncio.create_task(_process_one(cp)) for cp in req.clip_paths]
        await asyncio.gather(*tasks, return_exceptions=True)
        with _bulk_sub_lock:
            _bulk_sub_progress[job_id]["status"] = "done"
            _bulk_sub_progress[job_id]["current_clips"] = []
        total = len(req.clip_paths)
        errs  = len(_bulk_sub_progress[job_id]["errors"])
        print(f"[🤖 Bulk Sub] All {total} clip(s) done. Errors: {errs}\n", flush=True)

    task = asyncio.create_task(_run_all())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"job_id": job_id, "workers": max_workers}


@app.get("/api/detect_subtitle_tracks_bulk/{job_id}")
async def api_bulk_subtitle_status(job_id: str):
    """Poll progress of a running bulk subtitle job."""
    with _bulk_sub_lock:
        data = _bulk_sub_progress.get(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return data


class TrackObjectRequest(BaseModel):
    clip_path:  str
    bbox:       dict          # {x, y, w, h} in video-pixel space
    start_time: float = 0.0  # seconds from which to start tracking


def _run_csrt_tracking(clip_path: str, bbox: dict, start_time: float, st: dict = None) -> dict:
    """Run OpenCV CSRT tracker in a background thread.

    Returns {"track_file": str, "frame_count": int} or {"error": str}.
    """
    try:
        import cv2; import json as _json  # noqa: lazy import
        p = Path(clip_path)

        cap = cv2.VideoCapture(str(p))
        if not cap.isOpened():
            return {"error": "could not open clip"}

        fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        vw    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        vh    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        start_frame = max(0, int(start_time * fps))
        if start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        ok, frame = cap.read()
        if not ok:
            cap.release()
            return {"error": "could not read initial frame"}

        # CSRT API changed between OpenCV 4 and 5
        if hasattr(cv2, "TrackerCSRT_create"):
            tracker = cv2.TrackerCSRT_create()
        elif hasattr(cv2, "tracking") and hasattr(cv2.tracking, "TrackerCSRT_create"):
            tracker = cv2.tracking.TrackerCSRT_create()
        elif hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerCSRT_create"):
            tracker = cv2.legacy.TrackerCSRT_create()
        else:
            cap.release()
            return {"error": "TrackerCSRT not available — install opencv-contrib-python"}

        # Convert 1080x1920 canvas bbox to original video frame ROI
        roi = map_canvas_box_to_orig_video(bbox, vw, vh, st or {})
        tracker.init(frame, roi)

        frames_data: list[dict] = []
        frame_idx = start_frame

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1
            success, box = tracker.update(frame)
            if success:
                x, y, w, h = [int(v) for v in box]
                x = max(0, min(x, vw - 1)); w = min(w, vw - x)
                y = max(0, min(y, vh - 1)); h = min(h, vh - y)
                if w > 4 and h > 4:
                    frames_data.append({"frame": frame_idx, "t": frame_idx / fps,
                                        "x": x, "y": y, "w": w, "h": h})
        cap.release()

        track_path = p.with_suffix(".track.json")
        _json.dump({"fps": fps, "width": vw, "height": vh,
                    "seek_time": start_time, "frames": frames_data},
                   open(track_path, "w"), indent=2)

        return {"track_file": str(track_path), "frame_count": len(frames_data)}

    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/track_object")
async def api_track_object(req: TrackObjectRequest):
    """Run CSRT object tracking on the given clip/bbox and save a .track.json file.

    Returns {track_file: str, frame_count: int} on success, or {error: str} on failure.
    The resulting track_file is stored in the blur_box and applied during export via
    _apply_tracked_blur_pass.
    """
    p = Path(req.clip_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Clip not found")

    st = {}
    with STATE_LOCK:
        for item in app_state.edit_queue:
            if item.get("clip_path") == str(p) or item.get("path") == str(p):
                st = item.get("state", {})
                break

    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _run_csrt_tracking, str(p), req.bbox, req.start_time, st
    )
    return result


# ── Video Inpainting (Object Removal) endpoint ────────────────────────────────

# In-memory job store: {job_id: {status, pct, msg, result}}
_inpaint_jobs: dict[str, dict] = {}
_inpaint_jobs_lock = threading.Lock()


class InpaintObjectRequest(BaseModel):
    clip_path:  str
    blur_boxes: list[dict]   # boxes with mode="inpaint", x/y/w/h, optional start_time/end_time
    output_path: str = ""    # if empty, auto-generates alongside clip


@app.post("/api/inpaint_object")
async def api_inpaint_object(req: InpaintObjectRequest):
    """Start an async inpainting job. Returns {job_id} immediately.

    The caller polls GET /api/inpaint_status/{job_id} for progress.
    Result is {status: done|error, output_path?, error?, pct, msg}.
    """
    import uuid
    job_id = str(uuid.uuid4())

    p = Path(req.clip_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Clip not found")

    # Resolve output path
    out_path = req.output_path.strip() or str(p.with_name(f"{p.stem}_inpainted{p.suffix}"))

    # Fetch edit state for this clip (needed for coordinate mapping)
    st: dict = {}
    with STATE_LOCK:
        for item in app_state.edit_queue:
            if item.get("clip_path") == str(p) or item.get("path") == str(p):
                st = item.get("state", {})
                break

    # Register job
    with _inpaint_jobs_lock:
        _inpaint_jobs[job_id] = {"status": "running", "pct": 0.0, "msg": "Queued…"}

    def _progress(pct: float, msg: str):
        with _inpaint_jobs_lock:
            if job_id in _inpaint_jobs:
                _inpaint_jobs[job_id].update({"pct": round(pct, 3), "msg": msg})

    def _worker():
        result = inpaint_video_region(
            clip_path=str(p),
            blur_boxes=req.blur_boxes,
            output_path=out_path,
            st=st,
            progress_cb=_progress,
        )
        with _inpaint_jobs_lock:
            if job_id in _inpaint_jobs:
                if result.get("status") == "done":
                    _inpaint_jobs[job_id].update({
                        "status": "done", "pct": 1.0,
                        "msg": "Done.", "output_path": result["output_path"],
                    })
                else:
                    _inpaint_jobs[job_id].update({
                        "status": "error", "error": result.get("error", "Unknown error"),
                    })

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _worker)

    return {"job_id": job_id, "output_path": out_path}


@app.get("/api/inpaint_status/{job_id}")
async def api_inpaint_status(job_id: str):
    """Poll inpainting job progress."""
    with _inpaint_jobs_lock:
        job = _inpaint_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ── Title Re-generation endpoint ───────────────────────────────────────────────


class RegenTitleRequest(BaseModel):
    clip_path:        str = ""
    current_title:    str = ""
    description:      str = ""
    highlight_reason: str = ""
    custom_prompt:    Optional[str] = None


@app.post("/api/edit_queue/regen_title")
@app.post("/api/edit_queue/retry_title")
async def api_regen_title(req: RegenTitleRequest):
    """
    Re-generate / retry title for one edit-queue clip using Gemini AI.
    Features full key rotation, rate-limit cooldown, and automatic retry across all keys.
    If the clip video exists on disk, analyzes the actual video content.
    Otherwise, uses the text prompt template.
    """
    keys = [k.strip() for k in app_state.config.get("api_keys", []) if k.strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="No Gemini API keys configured.")

    rotator = app_state.get_rotator()
    model_name = app_state.config.get("model_name", MODEL_NAME)
    custom_tpl = req.custom_prompt or app_state.config.get("title_prompt") or ""

    # Find the target queue item
    target_item = None
    with STATE_LOCK:
        for item in app_state.edit_queue:
            if (item.get("clip_path") or item.get("path")) == req.clip_path:
                target_item = item
                break

    # Look for video file on disk (clip_path or source_path)
    video_file = None
    if req.clip_path and Path(req.clip_path).exists():
        video_file = Path(req.clip_path)
    elif target_item:
        src = target_item.get("source_path") or target_item.get("clip_path") or target_item.get("path")
        if src and Path(src).exists():
            video_file = Path(src)

    def _log(level: str, msg: str):
        app_state.log(msg, level)

    def _call_video() -> tuple[Optional[str], Optional[str]]:
        return _gemini_generate_video_title(
            video_file, custom_tpl, rotator, model_name,
            app_state.stop_event, _log
        )

    def _call_text() -> tuple[Optional[str], Optional[str]]:
        old_title = req.current_title or (target_item.get("title") if target_item else "") or "Bodycam Video"
        desc = req.description or (target_item.get("description") if target_item else "") or "based on what you see in the video"
        reason = req.highlight_reason or (target_item.get("highlight_reason") if target_item else "") or "based on what you see in the video"
        if custom_tpl:
            try:
                prompt = custom_tpl.format(old_title=old_title, description=desc, highlight_reason=reason)
            except Exception:
                prompt = custom_tpl
        else:
            prompt = (
                f"Previous title: {old_title}\n"
                f"Context: {desc} — {reason}\n\n"
                "Write ONE viral, emotionally-charged title for YouTube Shorts / TikTok (ALL CAPS, 3-10 words, 100% ENGLISH). "
                "Output ONLY the title text, nothing else."
            )
        n_keys = max(1, len(rotator))
        last_exc = None
        for attempt in range(n_keys):
            if app_state.stop_event.is_set():
                return None, "Stopped by user"
            key = rotator.acquire()
            try:
                client, sdk = build_client(key)
                if sdk == "new":
                    from google.genai import types as _gt
                    r = client.models.generate_content(
                        model=model_name, contents=prompt,
                        config=_gt.GenerateContentConfig(temperature=0.9, max_output_tokens=200),
                    )
                    title = (r.text or "").strip().strip('"\'')
                else:
                    m = client.GenerativeModel(model_name)
                    title = m.generate_content(prompt).text.strip().strip('"\'')
                rotator.release(key)
                if title:
                    return title, None
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                is_quota = any(kw in err_str for kw in ("quota", "429", "rate limit", "resource_exhausted", "too many requests"))
                is_tcp = "10053" in str(exc) or "10054" in str(exc)
                if is_quota:
                    rotator.penalize(key, KeyRotator.COOLDOWN_RATE_LIMIT)
                elif is_tcp:
                    rotator.penalize(key, KeyRotator.COOLDOWN_TCP)
                else:
                    rotator.penalize(key, KeyRotator.COOLDOWN_GENERIC)
                rotator.release(key)
                if attempt < n_keys - 1:
                    time.sleep(0.5)
        return None, str(last_exc) if last_exc else "All API keys failed"

    loop = asyncio.get_event_loop()
    if video_file:
        new_title, err_msg = await loop.run_in_executor(None, _call_video)
    else:
        new_title, err_msg = await loop.run_in_executor(None, _call_text)

    if not new_title:
        if target_item:
            with STATE_LOCK:
                target_item["title_error"] = True
                target_item["title_error_msg"] = err_msg or "Failed"
        raise HTTPException(status_code=500, detail=err_msg or "All API keys failed to generate title.")

    # Update server-side queue in-place so next poll returns the new title
    with STATE_LOCK:
        for item in app_state.edit_queue:
            if (item.get("clip_path") or item.get("path")) == req.clip_path:
                item["title"] = new_title
                item["title_error"] = False
                item["title_error_msg"] = ""
                sug = item.get("suggested_titles") or []
                if new_title not in sug:
                    item["suggested_titles"] = [new_title] + sug
                break

    return {"status": "ok", "title": new_title}


@app.post("/api/edit_queue/retry_all_failed_titles")
def retry_all_failed_titles():
    """Background worker to retry AI title generation for all failed clips in edit queue."""
    keys = [k.strip() for k in app_state.config.get("api_keys", []) if k.strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="No Gemini API keys configured.")

    with STATE_LOCK:
        failed = [item for item in app_state.edit_queue if item.get("title_error")]
    if not failed:
        return {"status": "no_failures", "count": 0}

    def _worker():
        rotator = app_state.get_rotator()
        model_name = app_state.config.get("model_name", MODEL_NAME)
        custom_tpl = app_state.config.get("title_prompt") or ""
        def _log(level: str, msg: str):
            app_state.log(msg, level)

        for item in failed:
            if app_state.stop_event.is_set():
                break
            clip_p = item.get("clip_path") or item.get("path")
            src_p = item.get("source_path") or clip_p
            v_file = Path(src_p) if src_p and Path(src_p).exists() else (Path(clip_p) if clip_p and Path(clip_p).exists() else None)
            if v_file:
                t, err = _gemini_generate_video_title(v_file, custom_tpl, rotator, model_name, app_state.stop_event, _log)
                with STATE_LOCK:
                    if t:
                        item["title"] = t
                        item["title_error"] = False
                        item["title_error_msg"] = ""
                        sug = item.get("suggested_titles") or []
                        if t not in sug:
                            item["suggested_titles"] = [t] + sug
                    else:
                        item["title_error"] = True
                        item["title_error_msg"] = err or "Failed"

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started", "count": len(failed)}


@app.post("/api/analyze/retry")
def retry_failed():
    """Re-queue and re-run analysis only for videos that previously errored."""
    keys = [k.strip() for k in app_state.config.get("api_keys", []) if k.strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="No Gemini API keys configured.")

    failed = [p for p in app_state.video_files
              if app_state.video_results.get(str(p), {}).get("status") == ST_ERROR]
    if not failed:
        return {"status": "no_failures", "count": 0}

    # Reset failed → queued
    for p in failed:
        app_state.video_results[str(p)] = {"status": ST_QUEUED, "candidates": [], "error": ""}

    model = app_state.config.get("model_name", MODEL_NAME)
    app_state.stop_event.clear()
    threading.Thread(
        target=_run_bulk_analysis_thread,
        args=(keys, failed, model),
        daemon=True
    ).start()
    return {"status": "started", "count": len(failed)}

# ── Parallel FFmpeg Export Engine (Correct render_reup signature) ─────────────


def _run_export_worker(req: ExportRequest):
    # Clear any leftover cancel from a previous run
    app_state.export_cancel_event.clear()
    app_state.export_progress = {
        "status": "exporting", "completed": 0, "total": len(req.selected_videos),
        "current": "", "clip_pct": 0.0, "clip_name": "",
    }
    out_dir = Path(app_state.config.get(
        "output_folder", str(Path.home() / "Videos" / "Clipper_Outputs")
    ))
    out_dir.mkdir(parents=True, exist_ok=True)
    video_dir = out_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    srt_dir   = out_dir / "srt"
    srt_dir.mkdir(parents=True, exist_ok=True)
    json_dir  = out_dir / "json"
    json_dir.mkdir(parents=True, exist_ok=True)

    # Parse resolution string "1080x1920" → (w, h)
    try:
        rw, rh = [int(x) for x in req.resolution.lower().replace("×", "x").split("x")]
    except Exception:
        rw, rh = 1080, 1920

    def _log(level: str, msg: str):
        app_state.log(msg, level)

    def _export_one(vid_path_str: str):
        # Bail out immediately if export was cancelled
        if app_state.export_cancel_event.is_set():
            return
        v_path = Path(vid_path_str)
        if not v_path.exists():
            app_state.log(f"Skipping {v_path.name}: file not found", "warn")
            return

        res = app_state.video_results.get(vid_path_str, {})
        cands = res.get("candidates", [])
        if not cands:
            app_state.log(f"Skipping {v_path.name}: no analysis results", "warn")
            return

        # Merge config + request state
        edit_state = {**_default_edit_state(), **dict(app_state.config), **req.state}
        render_cfg = {
            "width":  rw, "height": rh,
            "vcodec": req.encoder,
            "acodec": "aac",
            "crf":    req.crf,
            "preset": req.preset,
            "fps":    req.fps,
        }

        for idx, cand in enumerate(cands):
            start_ts = cand.get("start_time", "00:00:00")
            title    = cand.get("title", edit_state.get("title", ""))
            stem     = sanitize(v_path.stem)
            clip_name = f"{stem}_clip{cand.get('id', idx+1)}_{start_ts.replace(':', '-')}"

            # Step 1: Cut raw 16s clip from source video
            clip_path = video_dir / f"{clip_name}_raw.mp4"
            app_state.export_progress["current"] = f"Cutting {clip_name}..."
            try:
                cut_clip_exact(v_path, start_ts, clip_path, _make_logger(_log))
            except Exception as e:
                app_state.log(f"Cut failed for {clip_name}: {e}", "error")
                continue

            # Step 2 (optional): Gemini/Whisper transcription
            srt_path = None
            if edit_state.get("subtitles"):
                app_state.export_progress["current"] = f"Transcribing {clip_name}..."
                keys = [k.strip() for k in app_state.config.get("api_keys", []) if k.strip()]
                sub_style  = edit_state.get("sub_style", "Normal")
                word_level = sub_style in ("Word Pop", "Highlight Line")
                model_name = app_state.config.get("model_name", MODEL_NAME)
                sub_engine = edit_state.get("sub_engine", "gemini_fallback")
                if sub_engine in ("gemini", "gemini_fallback"):
                    for k in keys:
                        try:
                            client, sdk = build_client(k)
                            srt_path = _gemini_transcribe(
                                clip_path, client, sdk, _make_logger(_log),
                                app_state.stop_event,
                                word_level=word_level,
                                model_name=model_name,
                                edit_state=edit_state
                            )
                            if srt_path:
                                break
                        except Exception as te:
                            app_state.log(f"Gemini transcribe error: {te}", "warn")
                _use_whisper = (sub_engine == "whisper") or (sub_engine == "gemini_fallback" and srt_path is None)
                if _use_whisper and WHISPER_AVAILABLE:
                    try:
                        srt_path = _whisper_transcribe(clip_path, _make_logger(_log), word_level=word_level, edit_state=edit_state)
                    except Exception as we:
                        app_state.log(f"Whisper fallback error: {we}", "warn")

            # Move SRT and words.json to their dedicated output folders
            if srt_path and srt_path.exists():
                target_srt = srt_dir / srt_path.name
                try:
                    if target_srt.exists():
                        target_srt.unlink(missing_ok=True)
                    shutil.move(str(srt_path), str(target_srt))
                    srt_path = target_srt  # render_reup reads from the new location
                except Exception:
                    pass
            target_words = None
            words_json = clip_path.with_suffix(".words.json")
            if words_json.exists():
                try:
                    target_words = json_dir / words_json.name
                    if target_words.exists():
                        target_words.unlink(missing_ok=True)
                    shutil.move(str(words_json), str(target_words))
                except Exception:
                    target_words = words_json

            # Step 3: Full 9:16 portrait render
            dst = video_dir / f"{clip_name}_reup.mp4"
            app_state.export_progress["current"] = f"Rendering 9:16 → {dst.name}..."
            try:
                render_reup(
                    clip        = clip_path,
                    dst         = dst,
                    title       = title,
                    color_grade = bool(edit_state.get("color_grade", False)),
                    srt_path    = srt_path,
                    log         = _make_logger(_log),
                    edit_state  = edit_state,
                    render_cfg  = render_cfg,
                    stop_event  = app_state.export_cancel_event,
                    words_json_path = target_words,
                    progress_cb = lambda pct: app_state.export_progress.update(
                        {"clip_pct": round(pct, 3), "clip_name": dst.name}
                    ),
                )
                # Cleanup raw cut after successful render
                try: clip_path.unlink(missing_ok=True)
                except Exception: pass
            except InterruptedError:
                # Clean up partial output so the folder isn't polluted
                for f in (clip_path, dst):
                    try: f.unlink(missing_ok=True)
                    except Exception: pass
                app_state.log(f"Export interrupted: {dst.name} removed.", "warn")
                return  # stop processing further candidates for this video
            except Exception as e:
                app_state.log(f"Render failed for {dst.name}: {e}", "error")

        app_state.export_progress["completed"] += 1

    is_gpu = req.encoder in {"h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "h264_amf", "hevc_amf"}
    effective_workers = max(1, min(req.threads, 3 if is_gpu else req.threads))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=effective_workers) as pool:
        pool.map(_export_one, req.selected_videos)

    app_state.export_progress["status"] = "done"
    _sse_bus.push("export_changed", {"status": "done"})
    app_state.log(f"Export complete: {req.selected_videos.__len__()} video(s) processed.", "ok")

@app.post("/api/export/start")
def start_export(req: ExportRequest):
    if not req.selected_videos:
        raise HTTPException(status_code=400, detail="No videos selected for export.")
    threading.Thread(target=_run_export_worker, args=(req,), daemon=True).start()
    return {"status": "started", "total": len(req.selected_videos)}


# ── Edit Queue Bulk Export ─────────────────────────────────────────────────────
# /api/export/queue — handles pre-cut clips from Tab 2 Edit Queue.
# Unlike /api/export/start (which re-cuts from source + needs Gemini analysis),
# this endpoint goes straight to render_reup using each clip's own title+state.

class QueueExportItem(BaseModel):
    clip_path: str
    title: str = ""
    state: Dict[str, Any] = {}
    # Optional: browser-rendered title overlay PNG (base64). When present,
    # backend skips PIL _make_title_image entirely and passes this PNG to FFmpeg
    # directly — guarantees 100% WYSIWYG with the live preview.
    title_overlay_b64: Optional[str] = None

class QueueExportRequest(BaseModel):
    items: List[QueueExportItem] = []
    threads: int = 2
    crf: int = 20
    preset: str = "fast"
    encoder: str = "libx264"
    resolution: str = "1080x1920"
    fps: Optional[int] = None
    output_folder: Optional[str] = None

def _run_queue_export_inner(req: QueueExportRequest, total_overall: int, completed_offset: int, target_dir: Optional[str] = None):
    chosen_dir = target_dir or req.output_folder or app_state.get_current_output_folder()
    out_dir = Path(chosen_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    video_dir = out_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    srt_dir   = out_dir / "srt"
    srt_dir.mkdir(parents=True, exist_ok=True)
    json_dir  = out_dir / "json"
    json_dir.mkdir(parents=True, exist_ok=True)

    try:
        rw, rh = [int(x) for x in req.resolution.lower().replace("x", "x").split("x")]
    except Exception:
        rw, rh = 1080, 1920

    def _log(level: str, msg: str):
        app_state.log(msg, level)

    completed_lock = threading.Lock()
    local_completed = 0
    def _on_item_finish():
        nonlocal local_completed
        with completed_lock:
            local_completed += 1
            app_state.export_progress["completed"] = completed_offset + local_completed

    retry_candidates: List[QueueExportItem] = []
    retry_lock = threading.Lock()

    def _export_item(item: QueueExportItem, is_retry: bool = False):
        if app_state.export_cancel_event.is_set():
            _on_item_finish()
            return
        clip_path = Path(item.clip_path)
        if not clip_path.exists():
            app_state.log(f"Skipping {clip_path.name}: file not found", "warn")
            _on_item_finish()
            return

        edit_state = {**_default_edit_state(), **dict(app_state.config), **item.state}
        render_cfg = {
            "width":  rw, "height": rh,
            "vcodec": req.encoder, "acodec": "aac",
            "crf":    req.crf, "preset": req.preset, "fps": req.fps,
        }

        srt_path = None
        if edit_state.get("subtitles"):
            app_state.export_progress["current"] = f"Transcribing {clip_path.name}..."
            keys = [k.strip() for k in app_state.config.get("api_keys", []) if k.strip()]
            sub_style  = edit_state.get("sub_style", "Normal")
            word_level = sub_style in ("Word Pop", "Highlight Line")
            model_name = app_state.config.get("model_name", MODEL_NAME)
            sub_engine = edit_state.get("sub_engine", "gemini_fallback")
            if sub_engine in ("gemini", "gemini_fallback"):
                for k in keys:
                    try:
                        client, sdk = build_client(k)
                        srt_path = _gemini_transcribe(
                            clip_path, client, sdk, _make_logger(_log),
                            app_state.stop_event, word_level=word_level, model_name=model_name,
                            edit_state=edit_state
                        )
                        if srt_path:
                            break
                    except Exception as te:
                        app_state.log(f"Gemini transcribe error: {te}", "warn")
            _use_whisper = (sub_engine == "whisper") or (sub_engine == "gemini_fallback" and srt_path is None)
            if _use_whisper and WHISPER_AVAILABLE:
                try:
                    srt_path = _whisper_transcribe(clip_path, _make_logger(_log), word_level=word_level, edit_state=edit_state)
                except Exception as we:
                    app_state.log(f"Whisper fallback error: {we}", "warn")

        if srt_path and srt_path.exists():
            target_srt = srt_dir / srt_path.name
            try:
                if target_srt.exists():
                    target_srt.unlink(missing_ok=True)
                shutil.move(str(srt_path), str(target_srt))
                srt_path = target_srt
            except Exception:
                pass
        target_words = None
        words_json = clip_path.with_suffix(".words.json")
        if words_json.exists():
            try:
                target_words = json_dir / words_json.name
                if target_words.exists():
                    target_words.unlink(missing_ok=True)
                shutil.move(str(words_json), str(target_words))
            except Exception:
                target_words = words_json

        stem = sanitize(clip_path.stem)
        dst  = video_dir / f"{stem}_reup.mp4"
        app_state.export_progress["current"] = f"Rendering {dst.name}..."

        tmp_overlay = None
        try:
            if item.title_overlay_b64:
                import base64, tempfile
                png_bytes = base64.b64decode(item.title_overlay_b64)
                tmp_overlay = Path(tempfile.mktemp(suffix="_title_overlay.png"))
                tmp_overlay.write_bytes(png_bytes)
        except Exception as _oe:
            app_state.log(f"Could not decode title overlay PNG, falling back to PIL: {_oe}", "warn")
            tmp_overlay = None

        try:
            render_reup(
                clip        = clip_path,
                dst         = dst,
                title       = (item.title or edit_state.get("title") or "").strip(),
                color_grade = bool(edit_state.get("color_grade", False)),
                srt_path    = srt_path,
                log         = _make_logger(_log),
                edit_state  = edit_state,
                render_cfg  = render_cfg,
                stop_event  = app_state.export_cancel_event,
                title_overlay_path = tmp_overlay,
                words_json_path = target_words,
                progress_cb = lambda pct: app_state.export_progress.update(
                    {"clip_pct": round(pct, 3), "clip_name": dst.name}
                ),
            )
            app_state.log(f"✅ Exported: {dst.name}", "ok")
        except InterruptedError:
            try: dst.unlink(missing_ok=True)
            except Exception: pass
            app_state.log(f"Export interrupted: {dst.name} removed.", "warn")
            _on_item_finish()
            return
        except Exception as e:
            err_short = str(e)[:300]
            # Transient or memory error detection:
            is_mem_err = any(err_sig in str(e).lower() for err_sig in [
                "cannot allocate memory", "-12", "4294967284", "out of memory",
                "resource temporarily unavailable", "conversion failed", "oom"
            ])
            if not is_retry and not app_state.export_cancel_event.is_set() and is_mem_err:
                app_state.log(f"⚠️ Render quá tải bộ đệm/VRAM cho {dst.name}. Đã xếp vào hàng đợi Tự động Retry...", "warn")
                with retry_lock:
                    retry_candidates.append(item)
                return  # Do not record as failed yet; will retry cleanly in single-thread pass

            app_state.log(f"Render failed for {dst.name}: {e}", "error")
            app_state.export_progress.setdefault("failed_items", []).append({
                "clip_path": str(clip_path),
                "title":     item.title,
                "state":     item.state,
                "error":     err_short,
            })
            _on_item_finish()
            return
        finally:
            if tmp_overlay and tmp_overlay.exists():
                try: tmp_overlay.unlink(missing_ok=True)
                except Exception: pass

        _on_item_finish()

    is_gpu = req.encoder in {"h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "h264_amf", "hevc_amf"}
    # On consumer GPUs (e.g. RTX 3050 with 6GB VRAM and 1 NVENC chip), running >3 jobs causes
    # severe context thrashing (drops to 6 fps) and VRAM exhaustion (FFmpeg error -12 Cannot allocate memory).
    # Capping GPU encoders to max 3 concurrent workers delivers 5-10x higher throughput without OOM crashes.
    effective_workers = max(1, min(req.threads, 3 if is_gpu else req.threads))

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=effective_workers) as pool:
        list(pool.map(_export_item, req.items))

    # ── Auto-Retry Pass (Sequential / Single Worker to guarantee zero VRAM contention) ──
    if retry_candidates and not app_state.export_cancel_event.is_set():
        app_state.log(f"🔄 Đang tự động thử lại (Auto-Retry) {len(retry_candidates)} video ở chế độ giải phóng VRAM...", "info")
        time.sleep(1.2)  # Allow Windows/NVIDIA driver to reclaim released VRAM
        for retrying_item in retry_candidates:
            if app_state.export_cancel_event.is_set():
                _on_item_finish()
                continue
            _export_item(retrying_item, is_retry=True)


def _clean_orphaned_temp_uploads() -> tuple[int, float]:
    """Scan temp_uploads and delete orphaned files not in active queue, batches, or session.
    Returns (deleted_count, freed_mb).
    """
    tu_dir = Path("temp_uploads")
    if not tu_dir.exists():
        return 0, 0.0

    active_names = set()
    with STATE_LOCK:
        for item in app_state.edit_queue:
            p = item.get("path") or item.get("clip_path")
            if p:
                active_names.add(Path(p).name)
        for b_data in app_state.batches.values():
            for item in b_data.get("items", []):
                p = item.get("path") or item.get("clip_path")
                if p:
                    active_names.add(Path(p).name)
        for vf in app_state.video_files:
            active_names.add(vf.name)

    freed_bytes = 0
    deleted_count = 0
    for f in tu_dir.iterdir():
        if f.is_file() and f.name not in active_names:
            sz = f.stat().st_size
            try:
                f.unlink()
                freed_bytes += sz
                deleted_count += 1
            except Exception:
                pass
    freed_mb = freed_bytes / (1024 * 1024)
    return deleted_count, freed_mb


def _auto_clean_temp_cache_if_enabled():
    """Auto-clean orphaned temp clips from temp_uploads if enabled in config."""
    if not app_state.config.get("auto_clean_temp", True):
        return
    try:
        deleted_count, freed_mb = _clean_orphaned_temp_uploads()
        if deleted_count > 0:
            app_state.log(f"🧹 Đã tự động dọn {deleted_count} file tạm ({freed_mb:.1f} MB) trong temp_uploads/", "ok")
    except Exception as ex:
        app_state.log(f"⚠️ Auto-clean temp cache note: {ex}", "warn")


def _run_queue_export(req: QueueExportRequest):
    app_state.export_cancel_event.clear()
    app_state.export_progress = {
        "status": "exporting", "completed": 0, "total": len(req.items),
        "current": "", "clip_pct": 0.0, "clip_name": "", "failed_items": []
    }
    try:
        _run_queue_export_inner(req, total_overall=len(req.items), completed_offset=0)
        if not app_state.export_cancel_event.is_set():
            app_state.export_progress["status"] = "done"
            _sse_bus.push("export_changed", {"status": "done"})
            app_state.log(f"✅ Bulk Export Complete: {len(req.items)} video(s) processed.", "ok")
            _auto_clean_temp_cache_if_enabled()
        else:
            app_state.export_progress["status"] = "cancelled"
            _sse_bus.push("export_changed", {"status": "cancelled"})
    except Exception as ge:
        app_state.export_progress["status"] = "error"
        _sse_bus.push("export_changed", {"status": "error"})
        app_state.log(f"Export error: {ge}", "error")


def _run_all_batches_export(req: QueueExportRequest):
    app_state.export_cancel_event.clear()
    with STATE_LOCK:
        batch_tasks = []
        total_items_count = 0
        for b_id, b_data in app_state.batches.items():
            items = b_data.get("items", [])
            if items:
                b_folder = b_data.get("output_folder") or app_state.get_current_output_folder(b_id)
                batch_tasks.append({
                    "batch_id": b_id,
                    "name": b_data.get("name", "Cụm"),
                    "output_folder": b_folder,
                    "items": list(items)
                })
                total_items_count += len(items)

    if not batch_tasks:
        app_state.export_progress = {"status": "idle", "completed": 0, "total": 0, "current": ""}
        app_state.log("⚠️ Không có clip nào trong tất cả các cụm để xuất.", "warn")
        return

    app_state.export_progress = {
        "status": "exporting", "completed": 0, "total": total_items_count,
        "current": f"Bắt đầu xuất {len(batch_tasks)} cụm ({total_items_count} clips)...",
        "clip_pct": 0.0, "clip_name": "", "failed_items": []
    }

    try:
        completed_acc = 0
        for b_idx, b_task in enumerate(batch_tasks):
            if app_state.export_cancel_event.is_set():
                break
            b_name = b_task["name"]
            b_folder = b_task["output_folder"]
            b_items = b_task["items"]

            app_state.log(f"🚀 [{b_idx+1}/{len(batch_tasks)}] Đang xuất cụm: '{b_name}' ({len(b_items)} video) → {b_folder}", "info")

            sub_req = QueueExportRequest(
                items=[
                    QueueExportItem(
                        clip_path=it.get("clip_path") or it.get("path", ""),
                        title=it.get("title") or it.get("state", {}).get("title", ""),
                        state=it.get("state", {}),
                        title_overlay_b64=it.get("title_overlay_b64")
                    )
                    for it in b_items
                ],
                threads=req.threads,
                crf=req.crf,
                preset=req.preset,
                encoder=req.encoder,
                resolution=req.resolution,
                fps=req.fps,
                output_folder=b_folder,
            )

            _run_queue_export_inner(sub_req, total_overall=total_items_count, completed_offset=completed_acc, target_dir=b_folder)
            completed_acc += len(b_items)

        if not app_state.export_cancel_event.is_set():
            app_state.export_progress["status"] = "done"
            _sse_bus.push("export_changed", {"status": "done"})
            app_state.log(f"✅ Hoàn thành xuất tất cả {len(batch_tasks)} cụm ({total_items_count} video)!", "ok")
            _auto_clean_temp_cache_if_enabled()
        else:
            app_state.export_progress["status"] = "cancelled"
            _sse_bus.push("export_changed", {"status": "cancelled"})
            app_state.log("Đã hủy quá trình xuất tất cả cụm.", "warn")

    except Exception as ge:
        app_state.export_progress["status"] = "error"
        _sse_bus.push("export_changed", {"status": "error"})
        app_state.log(f"Export all batches error: {ge}", "error")


@app.post("/api/system/clean_temp_cache")
def api_clean_temp_cache():
    """Manually clean orphaned temp uploads."""
    deleted_count, freed_mb = _clean_orphaned_temp_uploads()
    app_state.log(f"🧹 Đã dọn dẹp {deleted_count} file tạm ({freed_mb:.1f} MB) trong temp_uploads/", "ok")
    return {"status": "ok", "deleted_count": deleted_count, "freed_mb": round(freed_mb, 2)}


@app.post("/api/export/queue")
def start_queue_export(req: QueueExportRequest):
    """Export Edit Queue clips (pre-cut). Does NOT require Gemini analysis results."""
    if not req.items:
        raise HTTPException(status_code=400, detail="No items in export queue.")
    if app_state.export_progress.get("status") == "exporting":
        raise HTTPException(status_code=409, detail="Export already in progress.")
    threading.Thread(target=_run_queue_export, args=(req,), daemon=True).start()
    return {"status": "started", "total": len(req.items)}


@app.post("/api/export/all_batches")
def start_all_batches_export(req: QueueExportRequest):
    """Export clips across all batches sequentially to each batch's output folder."""
    if app_state.export_progress.get("status") == "exporting":
        raise HTTPException(status_code=409, detail="Export already in progress.")
    threading.Thread(target=_run_all_batches_export, args=(req,), daemon=True).start()
    return {"status": "started"}


@app.get("/api/export/status")
def get_export_status():
    return app_state.export_progress


@app.post("/api/export/retry_failed")
def retry_failed_exports(req: QueueExportRequest):
    """Re-export only the items that failed in the last export run.

    The frontend passes the same encoder/crf/preset settings; the failed items
    are sourced from export_progress['failed_items'] so the caller just needs
    to supply render settings, not the full item list again.
    """
    failed = app_state.export_progress.get("failed_items", [])
    if not failed:
        raise HTTPException(status_code=400, detail="No failed exports to retry.")
    if app_state.export_progress.get("status") == "exporting":
        raise HTTPException(status_code=409, detail="Export already in progress.")

    # Rebuild QueueExportItem list from the stored failure records
    retry_items = [
        QueueExportItem(
            clip_path=f["clip_path"],
            title=f.get("title", ""),
            state=f.get("state", {}),
        )
        for f in failed
    ]
    retry_req = QueueExportRequest(
        items=retry_items,
        threads=req.threads,
        crf=req.crf,
        preset=req.preset,
        encoder=req.encoder,
        resolution=req.resolution,
        fps=req.fps,
    )
    threading.Thread(target=_run_queue_export, args=(retry_req,), daemon=True).start()
    return {"status": "started", "retrying": len(retry_items)}


# ── Transcription Endpoint ─────────────────────────────────────────────────────

class TranscribeRequest(BaseModel):
    video_path: str
    style: str = "Normal"   # Normal | Word Pop | Highlight Line
    engine: str = "gemini_fallback"  # gemini | whisper | gemini_fallback
    edit_state: Optional[dict] = None

@app.post("/api/transcribe")
def transcribe_video(req: TranscribeRequest):
    app_state.stop_event.clear()
    v_path = Path(req.video_path)
    if not v_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found.")

    keys = [k.strip() for k in app_state.config.get("api_keys", []) if k.strip()]
    model_name  = app_state.config.get("model_name", MODEL_NAME)
    word_level  = req.style in ("Word Pop", "Highlight Line", "Viral Bounce")
    engine      = req.engine  # gemini | whisper | gemini_fallback

    def _log(level, msg): app_state.log(msg, level)
    srt_path = None

    # ── Engine: Gemini or Gemini→Whisper fallback ──────────────────────────
    if engine in ("gemini", "gemini_fallback"):
        for k in keys:
            try:
                client, sdk = build_client(k)
                srt_path = _gemini_transcribe(
                    v_path, client, sdk, _make_logger(_log),
                    app_state.stop_event,
                    word_level=word_level,
                    model_name=model_name,
                    edit_state=req.edit_state
                )
                if srt_path:
                    break
            except Exception as e:
                app_state.log(f"Gemini transcribe error: {e}", "warn")

    # ── Engine: Whisper (direct or fallback) ──────────────────────────────
    use_whisper = (engine == "whisper") or (engine == "gemini_fallback" and srt_path is None)
    if use_whisper and WHISPER_AVAILABLE:
        if engine == "whisper":
            app_state.log("🎙 Whisper engine selected.", "info")
        else:
            app_state.log("⚠️ Gemini failed — falling back to Whisper.", "warn")
        try:
            srt_path = _whisper_transcribe(v_path, _make_logger(_log), word_level=True, edit_state=req.edit_state)
        except Exception as we:
            app_state.log(f"Whisper error: {we}", "warn")
    elif use_whisper and not WHISPER_AVAILABLE:
        app_state.log("Whisper not installed — pip install openai-whisper", "warn")

    if srt_path and srt_path.exists():
        srt_text = srt_path.read_text(encoding="utf-8", errors="replace")
        words_data = []
        words_p = v_path.with_suffix(".words.json")
        if not words_p.exists():
            words_p = srt_path.with_suffix(".words.json")
        if words_p.exists():
            try:
                import json as _j
                words_data = _j.loads(words_p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"status": "ok", "srt": srt_text, "path": str(srt_path), "words": words_data}

    return {"status": "error", "srt": "", "path": "", "words": []}

# ── Log Streaming Endpoint ─────────────────────────────────────────────────────

@app.get("/api/logs")
def get_logs(n: int = 100):
    with LOG_LOCK:
        return {"logs": list(app_state.logs[-n:])}

# ── Video Probe Endpoint ───────────────────────────────────────────────────────

@app.get("/api/video/probe")
def probe_video(path: str):
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return {
        "path":     str(p),
        "name":     p.name,
        "exists":   True,
        "duration": get_video_duration(p) or 0,
        "width":    get_video_width(p) or 0,
        "height":   get_video_height(p) or 0,
        "whisper_available": WHISPER_AVAILABLE,
    }

# ── SSE ──────────────────────────────────────────────────────────────────────
@app.get("/api/events")
async def sse_events(request: FastAPIRequest):
    """Server-Sent Events stream — replaces 1s HTTP polling.

    The browser subscribes once; the server pushes events whenever state
    actually changes. Falls back to a slow 30s safety poll on the client.

    Event types:
      log            – new log entry  (text, level, ts)
      videos_changed – a video finished analysis / hit error
      queue_changed  – clip added/removed from Edit Queue
      export_changed – export done/error
      heartbeat      – keep-alive every 20 s
    """
    q = _sse_bus.subscribe()

    async def _generate():
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        heartbeat_ticks = 0
        try:
            while True:
                if await request.is_disconnected():
                    break
                # Drain all pending events without blocking the event loop
                burst = 0
                try:
                    while burst < 50:
                        msg = q.get_nowait()
                        yield f"data: {msg}\n\n"
                        burst += 1
                except _stdlib_queue.Empty:
                    pass
                # Send heartbeat every 20s (400 × 50ms)
                heartbeat_ticks += 1
                if heartbeat_ticks >= 400:
                    heartbeat_ticks = 0
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                await asyncio.sleep(0.05)  # 50ms tick — only drains in-memory queue
        finally:
            _sse_bus.unsubscribe(q)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

# ── WebSockets ────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ── YouTube Direct Visual Analysis & Segment Downloader ────────────────────────

class YouTubeInfoRequest(BaseModel):
    url: str

class YouTubeAnalyzeRequest(BaseModel):
    url: str
    mode: str = "short"  # "short" | "story"

class YouTubeDownloadRequest(BaseModel):
    url: str
    start_time: str
    end_time: str
    title: str = ""
    suggested_titles: List[str] = []
    target: str = "edit"

class YouTubeCookieUploadRequest(BaseModel):
    content: str
    filename: Optional[str] = "cookies.txt"

@app.get("/api/youtube/cookies_status")
def get_yt_cookies_status_endpoint():
    c_path = get_yt_cookie_file()
    if c_path:
        p = Path(c_path)
        return {
            "has_cookies": True,
            "filename": p.name,
            "size": p.stat().st_size,
            "path": str(p),
        }
    return {"has_cookies": False, "filename": "", "size": 0}

@app.post("/api/youtube/upload_cookies")
def upload_yt_cookies_endpoint(req: YouTubeCookieUploadRequest):
    content = req.content.strip()
    if not content or len(content) < 10:
        raise HTTPException(status_code=400, detail="Nội dung cookie trống hoặc không hợp lệ")

    target_p = Path(__file__).parent / "cookies.txt"
    try:
        target_p.write_text(content, encoding="utf-8")
        Path("cookies.txt").write_text(content, encoding="utf-8")
        app_state.log(f"🍪 Đã nạp thành công cookies.txt ({len(content)} bytes)", "ok")
        return {
            "status": "ok",
            "filename": target_p.name,
            "size": len(content),
            "message": "Nạp cookies thành công!"
        }
    except Exception as e:
        app_state.log(f"Lỗi ghi file cookies.txt: {e}", "error")
        raise HTTPException(status_code=500, detail=f"Không thể lưu file cookies: {e}")

@app.delete("/api/youtube/cookies")
def delete_yt_cookies_endpoint():
    deleted = []
    for cand in (
        Path("cookies.txt"),
        Path("youtube_cookies.txt"),
        Path(__file__).parent / "cookies.txt",
        Path(__file__).parent / "youtube_cookies.txt",
    ):
        if cand.exists():
            try:
                cand.unlink()
                deleted.append(cand.name)
            except Exception:
                pass
    app_state.log("🍪 Đã xóa file cookies YouTube", "info")
    return {"status": "ok", "deleted": deleted}

class YouTubeBatchAddRequest(BaseModel):
    urls: Optional[List[str]] = None
    text: Optional[str] = None
    analyze_now: Optional[bool] = False
    mode: Optional[str] = "short"

@app.post("/api/youtube/batch_add")
def batch_add_youtube(req: YouTubeBatchAddRequest):
    raw_candidates = []
    if req.urls:
        raw_candidates.extend(req.urls)
    if req.text:
        for line in re.split(r"[\r\n,;]+", req.text):
            line = line.strip()
            if line:
                raw_candidates.append(line)

    valid_urls = []
    yt_regex = re.compile(r"https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[a-zA-Z0-9_\-]+[^\s]*", re.I)

    for item in raw_candidates:
        item = item.strip()
        matches = yt_regex.findall(item)
        if matches:
            for m in matches:
                u = m.strip().rstrip(".,;")
                if u and u not in valid_urls:
                    valid_urls.append(u)
        elif item.startswith(("http://", "https://")) and ("youtube.com" in item or "youtu.be" in item):
            if item not in valid_urls:
                valid_urls.append(item)

    if not valid_urls:
        raise HTTPException(status_code=400, detail="Không tìm thấy link YouTube hợp lệ nào.")

    added = []
    existing = {str(p.resolve()) if hasattr(p, "resolve") else str(p) for p in app_state.video_files}

    for url in valid_urls:
        if url not in existing:
            app_state.video_files.append(url)
            added.append(url)
            existing.add(url)
            if url not in app_state.video_results:
                app_state.video_results[url] = {
                    "status": ST_QUEUED,
                    "candidates": [],
                    "error": "",
                }

    app_state.save_config()
    app_state.save_session()
    _sse_bus.push("videos_changed", {"action": "batch_add", "count": len(added)})

    # Fetch metadata in background for added URLs so thumbnails & titles show up
    def _fetch_meta_bg(urls_to_fetch):
        cookie_browser = app_state.config.get("youtube_cookie_browser", None)
        for u in urls_to_fetch:
            try:
                info = get_youtube_info(u, cookies_browser=cookie_browser)
                if info:
                    if not hasattr(app_state, "yt_metadata"):
                        app_state.yt_metadata = {}
                    app_state.yt_metadata[u] = info
                    app_state.save_session()
                    _sse_bus.push("videos_changed", {"action": "metadata_updated", "url": u})
            except Exception:
                pass

    if added:
        threading.Thread(target=_fetch_meta_bg, args=(added,), daemon=True).start()

    app_state.log(f"🔴 Đã thêm {len(added)} video YouTube vào hàng đợi (Tổng: {len(app_state.video_files)})", "ok")

    if req.analyze_now and app_state.video_files:
        keys = [k.strip() for k in app_state.config.get("api_keys", []) if k.strip()]
        if not keys:
            app_state.log("⚠️ Không thể tự động phân tích: Chưa cài đặt Gemini API key.", "warn")
        elif not app_state.is_analyzing:
            model = app_state.config.get("model_name", MODEL_NAME)
            include_cta = bool(app_state.config.get("include_cta", False))
            mode = req.mode if req.mode in ("short", "story") else "short"
            threading.Thread(
                target=_run_bulk_analysis_thread,
                args=(keys, list(app_state.video_files), model, include_cta, mode),
                daemon=True,
            ).start()

    return {
        "status": "ok",
        "added_count": len(added),
        "total": len(app_state.video_files),
        "urls": added,
    }

@app.post("/api/youtube/info")
def get_yt_info_endpoint(req: YouTubeInfoRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")
    try:
        cookie_browser = app_state.config.get("youtube_cookie_browser", None)
        info = get_youtube_info(url, cookies_browser=cookie_browser)
        return {"status": "ok", "info": info}
    except Exception as e:
        app_state.log(f"Error fetching YouTube info: {e}", "warn")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/youtube/analyze")
def analyze_yt_endpoint(req: YouTubeAnalyzeRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")
    keys = [k.strip() for k in app_state.config.get("api_keys", []) if k.strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="No Gemini API keys configured.")

    cookie_browser = app_state.config.get("youtube_cookie_browser", None)
    info = None
    try:
        info = get_youtube_info(url, cookies_browser=cookie_browser)
    except Exception as e:
        app_state.log(f"Warning fetching YT metadata: {e}", "warn")

    vid_title = info.get("title", "YouTube Video") if info else "YouTube Video"
    vid_dur = info.get("duration", None) if info else None

    model_name = app_state.config.get("model_name", MODEL_NAME)
    include_cta = bool(app_state.config.get("include_cta", False))

    rotator = app_state.get_rotator()
    last_err = None
    app_state.log(f"🔍 Analyzing YouTube video with Gemini Visual AI: {vid_title}...", "info")

    for _ in range(max(1, len(rotator.peek_all()))):
        key = rotator.acquire()
        try:
            client, sdk = build_client(key)
            result = analyze_video(
                client, sdk, url, vid_title,
                _make_logger(lambda lvl, msg: app_state.log(msg, lvl)),
                app_state.stop_event,
                vid_duration=vid_dur,
                model_name=model_name,
                include_cta=include_cta,
                mode=req.mode,
            )
            rotator.release(key)
            candidates = result.get("candidates", [])
            app_state.log(f"✅ Gemini analysis complete for: {vid_title} ({len(candidates)} highlights found)", "ok")
            return {
                "status": "ok",
                "info": info or {"title": vid_title, "duration": vid_dur, "url": url},
                "candidates": candidates,
            }
        except Exception as e:
            rotator.penalize(key, KeyRotator.COOLDOWN_GENERIC)
            rotator.release(key)
            last_err = e
            app_state.log(f"Gemini YT analysis error with key [...{key[-6:]}]: {e}", "warn")
            continue

    raise HTTPException(status_code=500, detail=f"Analysis failed: {last_err}")

@app.post("/api/youtube/download_to_studio")
def download_yt_segment_endpoint(req: YouTubeDownloadRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    tmp_dir = Path("temp_uploads")
    tmp_dir.mkdir(exist_ok=True)

    clean_title = sanitize(req.title) if req.title else "yt_clip"
    start_clean = req.start_time.replace(":", "-")
    filename = f"{clean_title[:30]}_{start_clean}.mp4"
    output_path = tmp_dir / filename

    cookie_browser = app_state.config.get("youtube_cookie_browser", None)
    app_state.log(f"⚡ Downloading YouTube highlight [{req.start_time} - {req.end_time}]...", "info")

    try:
        final_path = download_youtube_section(
            url=url,
            start_time=req.start_time,
            end_time=req.end_time,
            output_path=str(output_path),
            cookies_browser=cookie_browser,
            log=lambda msg: app_state.log(msg, "info"),
        )
    except Exception as e:
        app_state.log(f"Download section error: {e}", "error")
        raise HTTPException(status_code=500, detail=str(e))

    dst_p = Path(final_path)
    entry = {
        "clip_path": str(dst_p),
        "path": str(dst_p),
        "name": dst_p.name,
        "source_path": url,
        "title": req.title or "",
        "suggested_titles": req.suggested_titles or ([req.title] if req.title else []),
        "description": "",
        "highlight_reason": "",
        "state": _default_edit_state(),
    }

    with STATE_LOCK:
        batch_id = app_state.active_batch_id
        if batch_id and batch_id in app_state.batches:
            entry["batch_id"] = batch_id
            b_queue = app_state.batches[batch_id].setdefault("edit_queue", [])
            b_queue.append(entry)
            app_state.batches[batch_id]["count"] = len(b_queue)

        app_state.edit_queue = [e for e in app_state.edit_queue if (e.get("clip_path") or e.get("path")) != str(dst_p)]
        app_state.edit_queue.append(entry)
        app_state.save_session()

    _sse_bus.push("queue_changed", {"action": "add", "name": dst_p.name})
    app_state.log(f"✅ Đã tải và thêm vào Studio: {dst_p.name} [{req.start_time} - {req.end_time}]", "ok")

    return {"status": "ok", "entry": entry}


# ── Auto-Update API Endpoints ────────────────────────────────────────────────
@app.get("/api/update/status")
async def get_update_status():
    """Kiểm tra nhanh xem có bản cập nhật mới hay không từ Web UI."""
    try:
        from updater import get_local_version, get_repo_urls, parse_version, CHECK_TIMEOUT
        import urllib.request
        local_ver = get_local_version()
        server_url, _ = get_repo_urls()
        if not server_url or "YOUR_USERNAME" in server_url:
            return {"configured": False, "local_version": local_ver, "has_update": False}

        req = urllib.request.Request(server_url, headers={"User-Agent": "OpenCutStudio/2.0"})
        with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT) as resp:
            remote_data = json.loads(resp.read().decode("utf-8"))

        remote_ver = remote_data.get("version", local_ver)
        has_update = parse_version(remote_ver) > parse_version(local_ver)
        return {
            "configured": True,
            "local_version": local_ver,
            "remote_version": remote_ver,
            "has_update": has_update,
            "changelog": remote_data.get("changelog", ""),
            "release_date": remote_data.get("release_date", ""),
        }
    except Exception as e:
        local_ver = "2.9.0"
        try:
            from updater import get_local_version
            local_ver = get_local_version()
        except Exception:
            pass
        return {"configured": True, "local_version": local_ver, "has_update": False, "error": str(e)}

@app.post("/api/update/apply")
async def trigger_update_apply():
    """Kích hoạt tải và cập nhật bản mới từ Web UI."""
    try:
        py_exe = sys.executable
        venv_py = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
        if os.path.exists(venv_py):
            py_exe = venv_py
        res = subprocess.run([py_exe, "updater.py"], capture_output=True, text=True, timeout=60)
        return {"status": "ok", "output": res.stdout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Static Files (Vite Production Build) ─────────────────────────────────────

web_dist = Path(__file__).parent / "web" / "dist"
if not web_dist.exists() and hasattr(sys, "_MEIPASS"):
    web_dist = Path(getattr(sys, "_MEIPASS")) / "web" / "dist"

if web_dist.exists():
    app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="static")

if __name__ == "__main__":
    import socket
    import uvicorn
    import webbrowser

    # Fix for PyInstaller --noconsole mode: sys.stdout/sys.stderr are None, causing
    # uvicorn.logging.DefaultFormatter to crash on sys.stdout.isatty()
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    def _find_free_port(start: int = 8000, end: int = 8020) -> int:
        """Probe ports in [start, end) and return the first one not in use.

        Using a real bind() test (vs. just checking /proc or netstat) is the only
        reliable way to detect port availability on Windows — it avoids race conditions
        and correctly handles TIME_WAIT sockets left by a previous server run.
        """
        for port in range(start, end):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(("127.0.0.1", port))
                    return port  # bind succeeded → port is free
                except OSError:
                    continue    # port busy → try next
        # Fallback: let OS pick any free ephemeral port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    PORT = _find_free_port()
    if PORT != 8000:
        print(f"[OpenCutStudio] Port 8000 is in use — using port {PORT} instead.")

    def _open_browser():
        time.sleep(1.5)
        url = f"http://127.0.0.1:{PORT}"
        try:
            # Try app window mode in Edge/Chrome for desktop app experience
            subprocess.Popen(["msedge.exe", f"--app={url}", "--window-size=1440,900"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            try:
                subprocess.Popen(["chrome.exe", f"--app={url}", "--window-size=1440,900"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception:
                webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, reload=False)

