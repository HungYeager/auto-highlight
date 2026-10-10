# -*- mode: python ; coding: utf-8 -*-
# OpenCutStudio — Web Studio Executable PyInstaller spec
# v2.9.0 — Full dependency bundling (sub, layer, AI detect, OCR, Whisper, GenAI, ONNX BG removal)

import sys
from pathlib import Path

block_cipher = None

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all

# ─────────────────────────────────────────────────────────────
# Collect data files & submodules for ALL feature-critical libs
# ─────────────────────────────────────────────────────────────
def safe_collect_data(pkg):
    try:
        return collect_data_files(pkg)
    except Exception as e:
        print(f"[WARN] collect_data_files({pkg!r}) failed: {e}")
        return []

def safe_collect_sub(pkg):
    try:
        return collect_submodules(pkg)
    except Exception as e:
        print(f"[WARN] collect_submodules({pkg!r}) failed: {e}")
        return []

# Feature → library mapping
# SUB / OCR / AI Detection
extra_datas  = safe_collect_data('rapidocr_onnxruntime')
extra_datas += safe_collect_data('onnxruntime')
extra_datas += safe_collect_data('shapely')
# Layer / Image Processing
extra_datas += safe_collect_data('PIL')
extra_datas += safe_collect_data('cv2')
# Web / API
extra_datas += safe_collect_data('fastapi')
extra_datas += safe_collect_data('starlette')
extra_datas += safe_collect_data('pydantic')
extra_datas += safe_collect_data('uvicorn')
extra_datas += safe_collect_data('httpx')
extra_datas += safe_collect_data('anyio')
extra_datas += safe_collect_data('websockets')
extra_datas += safe_collect_data('h11')
# Google AI / GenAI
extra_datas += safe_collect_data('google.genai')
extra_datas += safe_collect_data('google')
# Whisper subtitle AI
extra_datas += safe_collect_data('whisper')
# Network / TLS
extra_datas += safe_collect_data('cryptography')
extra_datas += safe_collect_data('certifi')
extra_datas += safe_collect_data('charset_normalizer')
extra_datas += safe_collect_data('idna')

# ─────────────────────────────────────────────────────────────
# Hidden imports: all submodules for each feature
# ─────────────────────────────────────────────────────────────
extra_hidden  = safe_collect_sub('rapidocr_onnxruntime')
extra_hidden += safe_collect_sub('onnxruntime')
extra_hidden += safe_collect_sub('shapely')
extra_hidden += safe_collect_sub('pyclipper')
extra_hidden += safe_collect_sub('yaml')
extra_hidden += safe_collect_sub('PIL')
extra_hidden += safe_collect_sub('cv2')
extra_hidden += safe_collect_sub('fastapi')
extra_hidden += safe_collect_sub('starlette')
extra_hidden += safe_collect_sub('pydantic')
extra_hidden += safe_collect_sub('uvicorn')
extra_hidden += safe_collect_sub('httpx')
extra_hidden += safe_collect_sub('httpcore')
extra_hidden += safe_collect_sub('anyio')
extra_hidden += safe_collect_sub('websockets')
extra_hidden += safe_collect_sub('google.genai')
extra_hidden += safe_collect_sub('stable_whisper')
extra_hidden += safe_collect_sub('whisper')
extra_hidden += safe_collect_sub('cryptography')
extra_hidden += safe_collect_sub('certifi')
extra_hidden += safe_collect_sub('charset_normalizer')
extra_hidden += safe_collect_sub('idna')
extra_hidden += safe_collect_sub('sniffio')
extra_hidden += safe_collect_sub('multipart')

# ─────────────────────────────────────────────────────────────
# Explicit hidden imports (modules PyInstaller won't auto-find)
# ─────────────────────────────────────────────────────────────
hidden = [
    # ── FastAPI / Uvicorn / Starlette web stack ──────────────
    "fastapi",
    "fastapi.middleware.cors",
    "fastapi.staticfiles",
    "fastapi.responses",
    "fastapi.encoders",
    "fastapi.exception_handlers",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "starlette",
    "starlette.routing",
    "starlette.middleware",
    "starlette.middleware.cors",
    "starlette.middleware.base",
    "starlette.staticfiles",
    "starlette.responses",
    "starlette.requests",
    "starlette.websockets",
    "pydantic",
    "pydantic.v1",
    "pydantic_core",
    "multipart",
    "python_multipart",
    "websockets",
    "websockets.legacy",
    "websockets.legacy.server",
    "websockets.legacy.client",
    "h11",
    "h11._readers",
    "h11._writers",
    "wsproto",
    "wsproto.connection",

    # ── Google GenAI (AI highlight / AI detect features) ─────
    "google.genai",
    "google.genai.types",
    "google.genai.client",
    "google.genai.models",
    "google.genai.files",
    "google.genai.live",
    "google.ai.generativelanguage_v1beta",
    "google.api_core",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.protobuf",
    "google.protobuf.descriptor",
    "google.protobuf.message",
    "proto.marshal",

    # ── Network / TLS / HTTP ──────────────────────────────────
    "httpx",
    "httpx._config",
    "httpcore",
    "httpcore._async",
    "httpcore._sync",
    "anyio",
    "anyio._backends._asyncio",
    "anyio._backends._trio",
    "sniffio",
    "certifi",
    "charset_normalizer",
    "idna",
    "cryptography",
    "cryptography.hazmat.primitives",
    "cryptography.hazmat.backends.openssl",
    "cryptography.x509",

    # ── RapidOCR + ONNXRuntime (AI subtitle detect) ──────────
    "rapidocr_onnxruntime",
    "rapidocr_onnxruntime.ch_ppocr_v2_cls",
    "rapidocr_onnxruntime.ch_ppocr_v3_det",
    "rapidocr_onnxruntime.ch_ppocr_v3_rec",
    "onnxruntime",
    "onnxruntime.capi",
    "onnxruntime.capi._pybind_state",
    "onnxruntime.capi.onnxruntime_pybind11_state",

    # ── Shapely / PyCLipper (polygon clipping for sub boxes) ─
    "shapely",
    "shapely.geometry",
    "shapely.geometry.polygon",
    "shapely.affinity",
    "pyclipper",

    # ── YAML (RapidOCR config parsing) ───────────────────────
    "yaml",

    # ── Pillow / Image layer processing ──────────────────────
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageFilter",
    "PIL.ImageEnhance",
    "PIL.ImageOps",
    "PIL.ImageChops",
    "PIL.ImageColor",
    "PIL.BmpImagePlugin",
    "PIL.JpegImagePlugin",
    "PIL.PngImagePlugin",
    "PIL.TiffImagePlugin",
    "PIL.GifImagePlugin",
    "PIL.WebPImagePlugin",
    "PIL._imaging",

    # ── OpenCV (frame capture, blur, delogo, layer) ──────────
    "cv2",
    "cv2.dnn",

    # ── Whisper / Stable-Whisper (subtitle from audio) ───────
    "whisper",
    "whisper.audio",
    "whisper.decoding",
    "whisper.model",
    "whisper.tokenizer",
    "stable_whisper",

    # ── NumPy (all compute features) ─────────────────────────
    "numpy",
    "numpy._core",
    "numpy._core._multiarray_umath",
    "numpy._core._multiarray_config",
    "numpy.core",
    "numpy.core.multiarray",
    "numpy.core.numeric",
    "numpy.lib",
    "numpy.fft",
    "numpy.linalg",
    "numpy.random",
    "numpy.ma",

    # ── Auto-Updater module ──────────────────────────────────
    "updater",
    "youtube_manager",

    # ── Standard Library holes PyInstaller can miss ───────────
    "ctypes",
    "ctypes.wintypes",
    "winreg",
    "urllib.parse",
    "urllib.request",
    "urllib.error",
    "http.client",
    "json",
    "shutil",
    "subprocess",
    "threading",
    "tempfile",
    "pathlib",
    "logging",
    "logging.handlers",
    "asyncio",
    "asyncio.events",
    "asyncio.tasks",
    "queue",
    "re",
    "base64",
    "hashlib",
    "hmac",
    "email.mime.multipart",
    "email.mime.text",
    "colorsys",
    "struct",
    "io",
    "os.path",
    "traceback",
] + extra_hidden

# ─────────────────────────────────────────────────────────────
# Analysis
# ─────────────────────────────────────────────────────────────
a = Analysis(
    ["server.py"],
    pathex=[str(Path(".").resolve())],
    binaries=[],
    datas=[
        ("config.json",   "."),
        ("web/dist",      "web/dist"),
        ("title_prompts", "title_prompts"),
        ("fonts",         "fonts"),          # Bundled TTF fonts (Montserrat, LuckiestGuy, etc.)
        ("version.json",  "."),
    ] + extra_datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy unused ML frameworks
        "matplotlib", "pandas",
        "IPython", "jupyter", "notebook",
        "PyQt5", "PyQt6", "wx",
        "unittest", "doctest", "pdb",
        "streamlit", "flask", "django",
        # PyTorch/CUDA (only ONNXRuntime CPU is needed, not PyTorch)
        "torch", "torchvision", "torchaudio",
        "transformers", "numba", "llvmlite",
        "triton", "timm", "accelerate",
        "av",
        "sympy",
    ],
    noarchive=False,
    optimize=2,
)

# ─────────────────────────────────────────────────────────────
# Strip ONLY heavy CUDA/PyTorch DLLs — preserve everything else
# ─────────────────────────────────────────────────────────────
def _is_unwanted_dll(dest_name: str, src_path: str) -> bool:
    dest_lower = dest_name.lower()
    src_lower  = str(src_path).lower()

    # Always keep these critical DLL families
    keep_keywords = ["numpy", "numpy.libs", "onnxruntime", "directml", "opencv", "cv2", "shapely"]
    for kw in keep_keywords:
        if kw in src_lower or kw in dest_lower:
            return False

    # Strip only CUDA/PyTorch/AI-training DLLs (they're huge, not needed at runtime)
    strip_keywords = [
        "torch", "torchvision", "torchaudio",
        "c10", "cublas", "cudart", "cudnn", "cufft", "curand",
        "cusolver", "cusparse", "nvrtc", "nvjitlink",
        "numba", "llvmlite",
        "scipy.libs",    # scipy itself is excluded; its .libs DLLs aren't needed
        "tbb",
        "libtriton",
    ]
    return any(p in dest_lower or p in src_lower for p in strip_keywords)

a.binaries = [b for b in a.binaries if not _is_unwanted_dll(b[0], b[1])]

# ─────────────────────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────────────────────
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OpenCutStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Keep console=True so users can see server startup logs & any errors
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
