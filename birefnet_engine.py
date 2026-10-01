# -*- coding: utf-8 -*-
"""
BiRefNet / RMBG Background Removal Engine (ONNX Runtime + PyTorch Fallback)
===========================================================================
High-Resolution Dichotomous Image & Video Segmentation for Overlays/Cutouts.
Runs standalone on clean Windows machines using ONNX Runtime (CPU / DirectML / CUDA)
without requiring PyTorch or HuggingFace Transformers.
"""

import os
import sys
import time
import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from typing import Optional, Callable, Union, Tuple
import threading
import urllib.request

# Global cached ONNX session
_ONNX_SESSION = None
_ONNX_MODEL_TYPE = None
_SESSION_LOCK = threading.Lock()

MODEL_DIR = Path("overlay_assets/models")
RMBG_MODEL_PATH = MODEL_DIR / "rmbg14.onnx"
BIREFNET_MODEL_PATH = MODEL_DIR / "birefnet_lite.onnx"

RMBG_URL = "https://huggingface.co/briaai/RMBG-1.4/resolve/main/onnx/model.onnx"
BIREFNET_URL = "https://huggingface.co/onnx-community/BiRefNet_lite-ONNX/resolve/main/onnx/model.onnx"


def _ensure_model_file(progress_cb: Optional[Callable[[float, str], None]] = None) -> Tuple[Path, str]:
    """Ensure at least one ONNX background removal model exists on disk, downloading if needed."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    # Priority 1: RMBG 1.4 (Fast 167MB, high quality)
    if RMBG_MODEL_PATH.exists() and RMBG_MODEL_PATH.stat().st_size > 10_000_000:
        return RMBG_MODEL_PATH, "rmbg"
    
    # Priority 2: BiRefNet Lite (213MB)
    if BIREFNET_MODEL_PATH.exists() and BIREFNET_MODEL_PATH.stat().st_size > 10_000_000:
        return BIREFNET_MODEL_PATH, "birefnet"
    
    # Auto-download RMBG 1.4
    if progress_cb:
        progress_cb(0.05, "Đang tải model tách nền AI (RMBG-1.4 ~167MB, chỉ tải 1 lần duy nhất)...")
    
    print(f"[BG-Remove] Downloading AI segmentation model to {RMBG_MODEL_PATH}...", flush=True)
    try:
        # Use certifi for TLS
        try:
            import certifi
            import ssl
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ssl_ctx = None

        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_ctx)) if ssl_ctx else urllib.request.build_opener()
        opener.addheaders = [("User-Agent", "OpenCutStudio/2.6")]
        urllib.request.install_opener(opener)

        tmp_download = RMBG_MODEL_PATH.with_suffix(".tmp")
        urllib.request.urlretrieve(RMBG_URL, str(tmp_download))
        if tmp_download.exists() and tmp_download.stat().st_size > 10_000_000:
            tmp_download.replace(RMBG_MODEL_PATH)
            print(f"[BG-Remove] Download completed: {RMBG_MODEL_PATH} ({RMBG_MODEL_PATH.stat().st_size // (1024*1024)} MB)", flush=True)
            return RMBG_MODEL_PATH, "rmbg"
    except Exception as e:
        print(f"[BG-Remove] Download error: {e}", flush=True)
        # Try BiRefNet lite fallback download
        try:
            tmp_download = BIREFNET_MODEL_PATH.with_suffix(".tmp")
            urllib.request.urlretrieve(BIREFNET_URL, str(tmp_download))
            if tmp_download.exists() and tmp_download.stat().st_size > 10_000_000:
                tmp_download.replace(BIREFNET_MODEL_PATH)
                return BIREFNET_MODEL_PATH, "birefnet"
        except Exception as e2:
            raise RuntimeError(f"Không thể tải model tách nền AI: {e} / {e2}. Vui lòng kiểm tra kết nối mạng.")

    return RMBG_MODEL_PATH, "rmbg"


def get_onnx_session(progress_cb: Optional[Callable[[float, str], None]] = None):
    """Load and cache ONNX Runtime inference session (CPU with safe CUDA fallback)."""
    global _ONNX_SESSION, _ONNX_MODEL_TYPE
    with _SESSION_LOCK:
        if _ONNX_SESSION is not None:
            return _ONNX_SESSION, _ONNX_MODEL_TYPE

        model_path, model_type = _ensure_model_file(progress_cb)
        import onnxruntime as ort

        # Try CUDA first if cuDNN is healthy, otherwise CPU
        avail_providers = ort.get_available_providers()
        selected_providers = ["CPUExecutionProvider"]
        
        # Test if CUDA provider works without crashing cuDNN
        if "CUDAExecutionProvider" in avail_providers:
            try:
                test_sess = ort.InferenceSession(str(model_path), providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
                # Run a dummy check
                inp = test_sess.get_inputs()[0]
                dummy = np.zeros((1, 3, 256, 256), dtype=np.float32)
                out_name = test_sess.get_outputs()[0].name
                test_sess.run([out_name], {inp.name: dummy})
                _ONNX_SESSION = test_sess
                _ONNX_MODEL_TYPE = model_type
                print(f"[BG-Remove] ONNX Session loaded on CUDA GPU: {model_path.name}", flush=True)
                return _ONNX_SESSION, _ONNX_MODEL_TYPE
            except Exception:
                pass

        # Fallback to high-performance multi-threaded CPU Execution Provider
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = min(8, os.cpu_count() or 4)
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        _ONNX_SESSION = ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])
        _ONNX_MODEL_TYPE = model_type
        print(f"[BG-Remove] ONNX Session loaded on CPU: {model_path.name}", flush=True)
        return _ONNX_SESSION, _ONNX_MODEL_TYPE


def _predict_mask_onnx(session, model_type: str, img_pil: Image.Image, resolution: int = 1024) -> Image.Image:
    """Predict alpha matte mask for a single PIL Image using ONNX session."""
    orig_w, orig_h = img_pil.size
    
    # 1. Preprocessing
    im_resized = img_pil.resize((resolution, resolution), Image.BILINEAR)
    arr = np.array(im_resized, dtype=np.float32) / 255.0
    
    if model_type == "rmbg":
        # RMBG-1.4 normalization: mean=0.5, std=1.0
        arr = (arr - np.array([0.5, 0.5, 0.5], dtype=np.float32)) / np.array([1.0, 1.0, 1.0], dtype=np.float32)
    else:
        # BiRefNet normalization: ImageNet mean/std
        arr = (arr - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
        
    arr = np.transpose(arr, (2, 0, 1))
    arr = np.expand_dims(arr, 0)
    
    # 2. Run Inference
    inp_name = session.get_inputs()[0].name
    out_name = session.get_outputs()[0].name
    res = session.run([out_name], {inp_name: arr})[0]
    
    # 3. Postprocess Alpha Mask
    raw_mask = res[0, 0]
    if raw_mask.min() < 0 or raw_mask.max() > 1:
        # Sigmoid activation
        mask = 1.0 / (1.0 + np.exp(-raw_mask))
    else:
        mask = raw_mask
        
    ma, mi = float(np.max(mask)), float(np.min(mask))
    if ma > mi and ma <= 1.0 and mi >= 0.0:
        pass
    elif ma > mi:
        mask = (mask - mi) / (ma - mi)
        
    mask_u8 = (np.clip(mask, 0.0, 1.0) * 255).astype(np.uint8)
    mask_pil = Image.fromarray(mask_u8).resize((orig_w, orig_h), Image.BICUBIC)
    return mask_pil


def remove_image_background(
    image_input: Union[str, Path, Image.Image, np.ndarray],
    output_path: Optional[Union[str, Path]] = None,
    resolution: int = 1024,
) -> Image.Image:
    """
    Remove background from an image and return transparent 32-bit RGBA PIL Image.
    Optionally saves the result to output_path.
    """
    # 1. Standardize input to PIL Image (RGB)
    if isinstance(image_input, (str, Path)):
        orig_img = Image.open(str(image_input)).convert("RGB")
    elif isinstance(image_input, np.ndarray):
        if image_input.shape[2] == 4:
            orig_img = Image.fromarray(cv2.cvtColor(image_input, cv2.COLOR_BGRA2RGBA)).convert("RGB")
        else:
            orig_img = Image.fromarray(cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB))
    elif isinstance(image_input, Image.Image):
        orig_img = image_input.convert("RGB")
    else:
        raise ValueError(f"Unsupported image input type: {type(image_input)}")

    # 2. Predict mask via ONNX
    session, model_type = get_onnx_session()
    mask_pil = _predict_mask_onnx(session, model_type, orig_img, resolution=resolution)

    # 3. Composite into RGBA
    rgba_img = orig_img.convert("RGBA")
    rgba_img.putalpha(mask_pil)

    # 4. Save if destination specified
    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        rgba_img.save(str(out_p), format="PNG")
        print(f"[BG-Remove] Saved cutout to {out_p}", flush=True)

    return rgba_img


def remove_video_background(
    input_video: Union[str, Path],
    output_video: Union[str, Path],
    resolution: int = 1024,
    batch_size: int = 4,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    ffmpeg_bin: str = "ffmpeg"
) -> Path:
    """
    Remove background from a video file frame-by-frame and export as
    a transparent WebM (VP9 with alpha) or MOV (ProRes/PNG with alpha).
    """
    import tempfile
    import subprocess
    import shutil

    src_p = Path(input_video)
    if not src_p.exists():
        raise FileNotFoundError(f"Input video not found: {input_video}")

    out_p = Path(output_video)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(src_p))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {input_video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1

    session, model_type = get_onnx_session(progress_cb)

    tmp_frames_dir = Path(tempfile.gettempdir()) / f"birefnet_vid_{src_p.stem}_{int(time.time())}"
    tmp_frames_dir.mkdir(parents=True, exist_ok=True)

    if progress_cb:
        progress_cb(0.02, "Bắt đầu tách nền video AI...")

    try:
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_frame)
            
            mask_pil = _predict_mask_onnx(session, model_type, pil_img, resolution=resolution)
            rgba = pil_img.convert("RGBA")
            rgba.putalpha(mask_pil)
            rgba.save(str(tmp_frames_dir / f"{frame_idx:06d}.png"), format="PNG")
            
            frame_idx += 1
            if progress_cb and total_frames > 0 and frame_idx % 3 == 0:
                pct = min(0.90, 0.05 + 0.85 * (frame_idx / total_frames))
                progress_cb(pct, f"Tách nền video: frame {frame_idx}/{total_frames}...")

        cap.release()

        # Encode transparent video using FFmpeg
        if progress_cb:
            progress_cb(0.92, "Đang đóng gói video trong suốt (Alpha Channel)...")

        if out_p.suffix.lower() == ".webm":
            cmd = [
                ffmpeg_bin, "-y",
                "-framerate", str(fps),
                "-i", str(tmp_frames_dir / "%06d.png"),
                "-i", str(src_p),
                "-map", "0:v:0",
                "-map", "1:a:0?",
                "-c:v", "libvpx-vp9",
                "-pix_fmt", "yuva420p",
                "-crf", "24",
                "-b:v", "0",
                "-c:a", "libopus",
                str(out_p)
            ]
        else:
            cmd = [
                ffmpeg_bin, "-y",
                "-framerate", str(fps),
                "-i", str(tmp_frames_dir / "%06d.png"),
                "-i", str(src_p),
                "-map", "0:v:0",
                "-map", "1:a:0?",
                "-c:v", "png",
                "-c:a", "copy",
                str(out_p)
            ]

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if res.returncode != 0 or not out_p.exists():
            raise RuntimeError(f"FFmpeg encode failed: {res.stderr[-300:]}")

        if progress_cb:
            progress_cb(1.0, "Hoàn tất tách nền video!")

        return out_p

    finally:
        try:
            shutil.rmtree(tmp_frames_dir, ignore_errors=True)
        except Exception:
            pass


def remove_gif_background(
    input_gif: Union[str, Path],
    output_gif: Union[str, Path],
    resolution: int = 1024,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    ffmpeg_bin: str = "ffmpeg"
) -> Path:
    """
    Remove background from each frame of an animated GIF, preserving frame timing
    and looping, and export a high-quality transparent animated GIF.
    """
    from PIL import ImageSequence
    import tempfile
    import subprocess
    import shutil

    src_p = Path(input_gif)
    if not src_p.exists():
        raise FileNotFoundError(f"Input GIF not found: {input_gif}")

    out_p = Path(output_gif)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    gif_im = Image.open(str(src_p))
    n_frames = getattr(gif_im, "n_frames", 1)

    # If static (single frame), handle as standard image
    if n_frames <= 1:
        remove_image_background(src_p, out_p, resolution=resolution)
        return out_p

    session, model_type = get_onnx_session(progress_cb)

    if progress_cb:
        progress_cb(0.02, f"Bắt đầu tách nền GIF động ({n_frames} frames)...")

    tmp_frames_dir = Path(tempfile.gettempdir()) / f"birefnet_gif_{src_p.stem}_{int(time.time())}"
    tmp_frames_dir.mkdir(parents=True, exist_ok=True)

    try:
        durations = []
        frame_idx = 0
        for frame in ImageSequence.Iterator(gif_im):
            dur = frame.info.get("duration", 100) or 100
            durations.append(dur)

            frame_rgb = frame.convert("RGB")
            mask_pil = _predict_mask_onnx(session, model_type, frame_rgb, resolution=resolution)
            rgba = frame_rgb.convert("RGBA")
            rgba.putalpha(mask_pil)

            rgba.save(str(tmp_frames_dir / f"{frame_idx:06d}.png"), format="PNG")
            frame_idx += 1

            if progress_cb and frame_idx % 2 == 0:
                pct = min(0.85, 0.05 + 0.80 * (frame_idx / n_frames))
                progress_cb(pct, f"Tách nền GIF: frame {frame_idx}/{n_frames}...")

        if progress_cb:
            progress_cb(0.88, "Đang đóng gói GIF động trong suốt...")

        # Calculate average fps from frame durations
        avg_dur = float(np.mean(durations)) if durations else 100.0
        fps = max(1.0, min(50.0, 1000.0 / max(10.0, avg_dur)))

        # Step 1: Try high-quality FFmpeg palette generation with alpha transparency
        palette_path = tmp_frames_dir / "palette.png"
        pal_cmd = [
            ffmpeg_bin, "-y",
            "-framerate", f"{fps:.3f}",
            "-i", str(tmp_frames_dir / "%06d.png"),
            "-vf", "palettegen=reserve_transparent=1:transparency_color=ffffff",
            str(palette_path)
        ]
        p_res = subprocess.run(
            pal_cmd,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

        if p_res.returncode == 0 and palette_path.exists():
            gif_cmd = [
                ffmpeg_bin, "-y",
                "-framerate", f"{fps:.3f}",
                "-i", str(tmp_frames_dir / "%06d.png"),
                "-i", str(palette_path),
                "-lavfi", "paletteuse=alpha_threshold=128",
                "-loop", "0",
                str(out_p)
            ]
            subprocess.run(
                gif_cmd,
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )

        # Step 2: Fallback to Pillow quantization if FFmpeg did not produce output
        if not out_p.exists() or out_p.stat().st_size == 0:
            pil_frames = []
            for i in range(frame_idx):
                f_rgba = Image.open(str(tmp_frames_dir / f"{i:06d}.png"))
                alpha = f_rgba.getchannel("A")
                mask = Image.eval(alpha, lambda a: 255 if a <= 128 else 0)
                f_p = f_rgba.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
                f_p.paste(255, mask)
                f_p.info["transparency"] = 255
                pil_frames.append(f_p)
            if pil_frames:
                pil_frames[0].save(
                    str(out_p),
                    save_all=True,
                    append_images=pil_frames[1:],
                    duration=durations,
                    loop=0,
                    disposal=2
                )

        if progress_cb:
            progress_cb(1.0, "Hoàn tất tách nền GIF động!")

        return out_p

    finally:
        try:
            shutil.rmtree(tmp_frames_dir, ignore_errors=True)
        except Exception:
            pass

