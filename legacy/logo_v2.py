#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Logo/Watermark Auto Remover (GUI + Batch + Multi-thread + GPU)
================================================================

Chức năng:
- GUI chọn nhiều video cùng lúc (kéo thả hoặc chọn file).
- Tự động PHÁT HIỆN vị trí logo tĩnh cho từng video (phân tích độ biến
  thiên - temporal variance - qua nhiều frame mẫu).
- LUỒNG XÁC NHẬN: trước khi xử lý, với MỖI video có phát hiện được
  logo, chương trình hiện cửa sổ preview kèm khung logo đã detect sẵn
  (màu vàng) để bạn xác nhận nhanh hoặc kéo chỉnh lại nếu detect lệch.
  Có nút "Bỏ qua video này" phòng khi detect sai hoàn toàn.
  Video nào KHÔNG phát hiện được logo sẽ tự động bỏ qua, không hiện
  cửa sổ, không xử lý.
- Ngoài ra vẫn có thể double-click 1 video trong danh sách để tự vẽ
  tay vùng logo TRƯỚC khi bấm xử lý (bỏ qua bước auto-detect + xác
  nhận cho riêng video đó).
- Che logo bằng blur (qua bộ lọc `delogo` của FFmpeg).
- Sau khi xác nhận xong toàn bộ, xử lý NHIỀU VIDEO SONG SONG bằng
  ThreadPoolExecutor.
- Dùng GPU NVIDIA (h264_nvenc) để tăng tốc phần encode. Nếu máy không
  có GPU NVIDIA, tự động fallback về CPU (libx264).

Yêu cầu cài đặt:
    pip install opencv-python numpy pillow tkinterdnd2 --break-system-packages
    FFmpeg phải được cài sẵn trên máy (và build có hỗ trợ NVENC nếu
    muốn dùng GPU). Tải tại: https://ffmpeg.org/download.html

Chạy:
    python3 logo_remover_gui.py
"""

import os
import sys
import subprocess
import threading
import queue
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np

import tkinter as tk
from tkinter import filedialog, ttk, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False


# ----------------------------------------------------------------------
# 1. PHÁT HIỆN LOGO TỰ ĐỘNG (temporal variance + ưu tiên vùng góc/rìa)
# ----------------------------------------------------------------------

def clamp_bbox(x, y, w, h, width, height):
    """Đảm bảo bbox nằm an toàn trong khung hình và có kích thước chẵn
    (bắt buộc để filter delogo không lỗi trên yuv420p)."""
    margin = 2
    x = max(margin, int(x))
    y = max(margin, int(y))
    w = min(width - margin - x, int(w))
    h = min(height - margin - y, int(h))
    x -= x % 2
    y -= y % 2
    w -= w % 2
    h -= h % 2
    if w <= 0 or h <= 0:
        return None
    return (x, y, w, h)


def detect_logo_bbox(video_path, sample_frames=40, corner_bias=True):
    """
    Trả về (x, y, w, h) vùng nghi ngờ là logo tĩnh, hoặc None nếu
    không tìm thấy vùng nào đủ rõ ràng.

    Nguyên lý:
    - Lấy `sample_frames` frame rải đều trong video.
    - Tính độ lệch chuẩn (std) theo thời gian cho từng pixel.
      Vùng logo tĩnh -> std thấp bất thường so với nền (người/cảnh
      chuyển động liên tục -> std cao).
    - Vì logo có thể hơi trong suốt (bán trong suốt), ta không đòi
      std = 0 tuyệt đối, mà lấy percentile thấp nhất.
    - Ưu tiên các vùng nằm ở góc/rìa khung hình vì watermark thường
      đặt ở đó -> giảm false positive từ nền tĩnh (ví dụ tường trắng).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if total <= 0 or width <= 0 or height <= 0:
        cap.release()
        return None

    idxs = np.linspace(0, max(total - 1, 0), num=min(sample_frames, total), dtype=int)

    frames = []
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frames.append(gray.astype(np.float32))
    cap.release()

    if len(frames) < 5:
        return None

    stack = np.stack(frames, axis=0)
    std_map = np.std(stack, axis=0)  # càng thấp càng "tĩnh"

    # Chuẩn hoá về 0-255 để dễ threshold
    norm = cv2.normalize(std_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    # Vùng tĩnh = std thấp -> đảo ngược để vùng tĩnh có giá trị cao
    inv = 255 - norm

    # Lấy threshold theo percentile (giữ lại top ~8% tĩnh nhất)
    thresh_val = np.percentile(inv, 92)
    mask = (inv >= thresh_val).astype(np.uint8) * 255

    # Loại nhiễu nhỏ, nối liền vùng logo
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
        # Bỏ vùng quá nhỏ (nhiễu) hoặc quá lớn (gần hết khung hình)
        if area < 400 or area > 0.25 * width * height:
            continue
        score = area
        if corner_bias:
            cx, cy = x + w / 2, y + h / 2
            # khoảng cách tới góc gần nhất (chuẩn hoá theo kích thước khung)
            corners = [(0, 0), (width, 0), (0, height), (width, height)]
            dist = min(
                ((cx - cxx) ** 2 + (cy - cyy) ** 2) ** 0.5
                for cxx, cyy in corners
            )
            dist_norm = dist / ((width ** 2 + height ** 2) ** 0.5)
            # điểm càng cao nếu gần góc + diện tích hợp lý
            score = area * (1.0 - dist_norm) ** 2
        candidates.append((score, x, y, w, h))

    if not candidates:
        return None

    candidates.sort(reverse=True, key=lambda t: t[0])
    _, x, y, w, h = candidates[0]

    # Nới rộng vùng để bắt trọn viền mờ/anti-alias của logo. Đây là
    # bước quan trọng: contour phát hiện được thường sát viền chữ/icon,
    # cần pad đủ rộng để không còn sót viền mờ ra ngoài.
    pad = max(14, int(0.12 * max(w, h)))
    x = x - pad
    y = y - pad
    w = w + 2 * pad
    h = h + 2 * pad

    # An toàn biên + làm tròn số chẵn (dùng hàm dùng chung clamp_bbox)
    return clamp_bbox(x, y, w, h, width, height)


# ----------------------------------------------------------------------
# 2. KIỂM TRA GPU / NVENC CÓ SẴN KHÔNG
# ----------------------------------------------------------------------

_GPU_CHECK_CACHE = {"checked": False, "has_nvenc": False, "has_cuvid": False}


def check_gpu_support():
    if _GPU_CHECK_CACHE["checked"]:
        return _GPU_CHECK_CACHE["has_nvenc"], _GPU_CHECK_CACHE["has_cuvid"]

    has_nvenc = False
    has_cuvid = False
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=15
        )
        has_nvenc = "h264_nvenc" in out.stdout
    except Exception:
        pass

    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-decoders"],
            capture_output=True, text=True, timeout=15
        )
        has_cuvid = "h264_cuvid" in out.stdout
    except Exception:
        pass

    _GPU_CHECK_CACHE.update(checked=True, has_nvenc=has_nvenc, has_cuvid=has_cuvid)
    return has_nvenc, has_cuvid


# ----------------------------------------------------------------------
# 3. XỬ LÝ 1 VIDEO: DETECT + CHE LOGO QUA FFMPEG (GPU nếu có)
# ----------------------------------------------------------------------

def process_one_video(video_path, output_dir, use_gpu, log_fn, blur_strength=25,
                       manual_bbox=None, force_916=False):
    """
    Trả về (video_path, success: bool, message: str)
    manual_bbox: nếu được cung cấp, có thể là:
      - (x, y, w, h)                -> 1 vùng, che từ đầu đến cuối video.
      - (x, y, w, h, start_time_s)  -> 1 vùng, chỉ che logo kể từ giây
        start_time_s trở đi (dùng cho trường hợp logo không xuất hiện
        ngay từ đầu mà nằm ở giữa video, người dùng đã tua tới đó rồi
        mới khoanh vùng).
      - [ (x,y,w,h[,start_time_s]), (x,y,w,h[,start_time_s]), ... ]
                                     -> NHIỀU vùng cùng lúc (mỗi vùng có
        thể có mốc thời gian bắt đầu riêng).
      - [] (danh sách rỗng)         -> không che logo gì cả (chỉ dùng khi
        force_916=True, ví dụ video không có logo nhưng vẫn cần ép 9:16).
    force_916: True -> ép video về khung dọc 9:16 (1080x1920) mà KHÔNG kéo
      méo hình: video gốc được giữ nguyên tỉ lệ, thu nhỏ vừa khung rồi đặt
      giữa; phần trống trên/dưới (hoặc trái/phải) được lấp bằng chính hình
      ảnh video đó phóng to + làm mờ làm nền, thay vì để viền đen.
    """
    name = os.path.basename(video_path)

    def is_region_list(mb):
        # True nếu mb là danh sách/tuple CÁC vùng (mỗi phần tử cũng là
        # tuple/list số), False nếu mb chỉ là 1 vùng đơn (x,y,w,h[,t]).
        if not isinstance(mb, (list, tuple)):
            return False
        if len(mb) == 0:
            return False
        first = mb[0]
        return isinstance(first, (list, tuple))

    cap = cv2.VideoCapture(video_path)
    vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    regions = []
    if manual_bbox is not None:
        if is_region_list(manual_bbox):
            regions_in = list(manual_bbox)
        elif len(manual_bbox) == 0:
            regions_in = []  # explicit: không có vùng logo nào cả
        else:
            regions_in = [manual_bbox]

        for r in regions_in:
            if len(r) >= 5:
                x_in, y_in, w_in, h_in, st = r[:5]
                st = max(0.0, float(st or 0.0))
            else:
                x_in, y_in, w_in, h_in = r
                st = 0.0
            bb = clamp_bbox(x_in, y_in, w_in, h_in, vw, vh)
            if bb is None:
                continue
            regions.append((bb[0], bb[1], bb[2], bb[3], st))

        if not regions and not regions_in and not force_916:
            # manual_bbox=[] và không ép 9:16 -> chẳng có việc gì để làm
            return video_path, False, "Không có vùng logo nào để xử lý."
        if regions_in and not regions:
            return video_path, False, "Vùng logo thủ công không hợp lệ."
        if regions:
            log_fn(f"[{name}] Dùng {len(regions)} vùng logo do bạn chọn thủ công.")
    else:
        log_fn(f"[{name}] Đang phát hiện logo...")
        bbox = detect_logo_bbox(video_path)
        if bbox is None:
            if force_916:
                log_fn(f"[{name}] Không phát hiện được logo -> chỉ ép 9:16, không che gì.")
            else:
                return video_path, False, "Không phát hiện được vùng logo tĩnh. Hãy double-click video trong danh sách để chọn tay."
        else:
            regions = [(bbox[0], bbox[1], bbox[2], bbox[3], 0.0)]

    for x, y, w, h, st in regions:
        if w <= 0 or h <= 0:
            return video_path, False, f"Vùng logo không hợp lệ: w={w}, h={h}"
        if st > 0.05:
            log_fn(f"[{name}] Vùng logo x={x}, y={y}, w={w}, h={h} "
                   f"(chỉ che từ giây {st:.2f} trở đi)")
        else:
            log_fn(f"[{name}] Vùng logo x={x}, y={y}, w={w}, h={h}")

    if not regions and not force_916:
        return video_path, False, "Không có gì để xử lý (không có vùng logo, không ép 9:16)."

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, os.path.splitext(name)[0] + "_clean.mp4")

    has_nvenc, _ = check_gpu_support() if use_gpu else (False, False)

    # Bộ lọc delogo: che vùng (x,y,w,h) bằng nội suy pixel xung quanh.
    # Lưu ý: filter delogo gốc của FFmpeg chỉ nhận x,y,w,h,show.
    # Với nhiều vùng, nối chuỗi nhiều filter delogo lại (ghép bằng dấu
    # phẩy) để ffmpeg che tuần tự từng vùng trên cùng 1 lần encode.
    vf_parts = []
    for x, y, w, h, st in regions:
        part = f"delogo=x={x}:y={y}:w={w}:h={h}:show=0"
        if st > 0.05:
            # delogo hỗ trợ timeline editing qua tuỳ chọn "enable" chung
            # của FFmpeg -> chỉ áp dụng filter kể từ mốc thời gian st trở
            # đi (t tính bằng giây kể từ đầu video), giữ nguyên phần trước.
            part += f":enable='gte(t\\,{st:.3f})'"
        vf_parts.append(part)

    # Ghép chuỗi filter thành 1 đồ thị filter_complex duy nhất:
    #   bước 1 (nếu có): che logo (delogo x N)
    #   bước 2 (nếu force_916): ép về khung dọc 1080x1920 mà KHÔNG bóp méo
    #     -> tách hình làm 2 nhánh: 1 nhánh phóng to + crop kín khung rồi
    #        làm mờ để làm NỀN (lấp đầy khung, không còn viền đen), nhánh
    #        còn lại giữ nguyên tỉ lệ gốc, thu nhỏ vừa khung rồi đặt giữa
    #        đè lên trên nền mờ đó -> hình chính không bị kéo dãn/méo.
    segments = []
    cur_label = "0:v"
    if vf_parts:
        segments.append(f"[{cur_label}]{','.join(vf_parts)}[vlogo]")
        cur_label = "vlogo"
    if force_916:
        # fg phóng 1.5x so với vừa khung rồi crop giữa
        # (chỉ cắt phần thừa, không ép crop lớn hơn kích thước thật)
        segments.append(
            f"[{cur_label}]split=2[bg][fg];"
            f"[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,gblur=sigma=80:steps=6,eq=brightness=-0.01:saturation=1[bg2];"
            f"[fg]scale=1620:2880:force_original_aspect_ratio=decrease,"
            f"crop=min(iw\\,1080):min(ih\\,1920):(iw-ow)/2:(ih-oh)/2[fg2];"
            f"[bg2][fg2]overlay=(W-w)/2:(H-h)/2[vout]"
        )
        cur_label = "vout"
    filter_complex = ";".join(segments)

    # Ghi chú: chỉ tăng tốc phần ENCODE bằng GPU (nvenc). Phần DECODE +
    # filter delogo vẫn chạy trên CPU vì delogo là CPU-only filter, và
    # việc ép decode qua GPU (cuvid) rồi tải ngược về CPU để lọc thường
    # không nhanh hơn đáng kể mà lại dễ lỗi tương thích tuỳ driver/build
    # FFmpeg -> encode GPU đã là phần tốn thời gian nhất nên ưu tiên ở đây.
    def build_cmd(with_gpu_encode):
        c = ["ffmpeg", "-y", "-i", video_path]
        if filter_complex:
            c += ["-filter_complex", filter_complex, "-map", f"[{cur_label}]", "-map", "0:a?"]
        if with_gpu_encode:
            c += ["-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "6M"]
        else:
            c += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
        c += ["-c:a", "copy", out_path]
        return c

    use_gpu_encode = bool(use_gpu and has_nvenc)
    log_fn(f"[{name}] Đang xử lý ({'GPU encode' if use_gpu_encode else 'CPU'})...")

    try:
        result = subprocess.run(build_cmd(use_gpu_encode), capture_output=True, text=True)
        if result.returncode != 0:
            if use_gpu_encode:
                log_fn(f"[{name}] GPU encode lỗi, thử lại bằng CPU...")
                result2 = subprocess.run(build_cmd(False), capture_output=True, text=True)
                if result2.returncode != 0:
                    return video_path, False, result2.stderr[-800:]
                return video_path, True, out_path
            return video_path, False, result.stderr[-800:]
        return video_path, True, out_path
    except Exception as e:
        return video_path, False, str(e)


# ----------------------------------------------------------------------
# 4. GUI (Tkinter)
# ----------------------------------------------------------------------

class LogoRemoverApp:
    # ---- Bảng màu giao diện (light theme, "phòng dựng phim" - sáng, có chiều sâu) ----
    C_BG = "#f3f4f9"        # nền tổng - trắng ngả xanh tím rất nhạt
    C_PANEL = "#ffffff"     # nền card/section - trắng
    C_PANEL_2 = "#f1f2f8"   # nền input/log - xám nhạt
    C_BORDER = "#e4e5f0"    # viền card
    C_SHADOW = "#dfe0ec"    # đổ bóng nhẹ dưới card
    C_TEXT = "#1e2030"      # chữ chính - mực đậm
    C_SUBTEXT = "#84869c"   # chữ phụ - xám
    C_ACCENT = "#6fbf73"    # xanh lá nhạt - màu thương hiệu / nút chính
    C_ACCENT_HOVER = "#5aa860"
    C_ACCENT_SOFT = "#eaf6ea"  # nền dịu cho chip/badge xanh
    C_TEAL = "#0f9b8e"      # điểm nhấn cho khối "xuất video"
    C_AMBER = "#d9932a"     # điểm nhấn cho khối "tuỳ chọn" / cảnh báo
    C_GREEN = "#1fa971"
    C_RED = "#e5484d"
    C_YELLOW = "#d9932a"

    def __init__(self, root):
        self.root = root
        self.root.title("LogoWipe Studio  —  Auto Logo/Watermark Remover")
        self.root.geometry("880x760")
        self.root.minsize(760, 620)
        self.root.configure(bg=self.C_BG)

        self.video_paths = []
        self.manual_bboxes = {}  # video_path -> (x, y, w, h) chọn tay
        self.output_dir = os.path.join(os.getcwd(), "output_clean")
        self.log_queue = queue.Queue()
        self.executor = None

        self._build_style()
        self._build_ui()
        self._poll_log_queue()

    # ---------------- ttk style (dark, bo tròn theo khả năng của ttk) ----------------
    def _build_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        base_font = ("Segoe UI", 10)
        bold_font = ("Segoe UI", 10, "bold")

        style.configure(".", background=self.C_BG, foreground=self.C_TEXT, font=base_font)

        style.configure("Card.TFrame", background=self.C_PANEL)
        style.configure("Bg.TFrame", background=self.C_BG)
        style.configure("Shadow.TFrame", background=self.C_SHADOW)

        style.configure("Card.TLabel", background=self.C_PANEL, foreground=self.C_TEXT)
        style.configure("CardSub.TLabel", background=self.C_PANEL, foreground=self.C_SUBTEXT, font=("Segoe UI", 9))
        style.configure("Bg.TLabel", background=self.C_BG, foreground=self.C_TEXT)
        style.configure("Title.TLabel", background=self.C_BG, foreground=self.C_TEXT, font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background=self.C_BG, foreground=self.C_SUBTEXT, font=("Segoe UI", 10))
        style.configure("SectionTitle.TLabel", background=self.C_PANEL, foreground=self.C_TEXT,
                         font=("Segoe UI", 11, "bold"))
        style.configure("Step.TLabel", background=self.C_PANEL, foreground=self.C_SUBTEXT,
                         font=("Segoe UI", 9, "bold"))
        style.configure("Status.TLabel", background=self.C_BG, foreground=self.C_SUBTEXT, font=("Segoe UI", 9))

        style.configure("TCheckbutton", background=self.C_PANEL, foreground=self.C_TEXT, font=base_font)
        style.map("TCheckbutton", background=[("active", self.C_PANEL)])

        style.configure("TEntry", fieldbackground=self.C_PANEL_2, foreground=self.C_TEXT,
                         insertcolor=self.C_TEXT, bordercolor=self.C_BORDER, lightcolor=self.C_PANEL_2,
                         darkcolor=self.C_PANEL_2, borderwidth=1)
        style.configure("TSpinbox", fieldbackground=self.C_PANEL_2, foreground=self.C_TEXT,
                         arrowsize=12, bordercolor=self.C_BORDER)

        # Nút phụ (outline rõ, không còn "chìm" vào nền)
        style.configure("Ghost.TButton", background=self.C_PANEL, foreground=self.C_TEXT,
                         font=base_font, borderwidth=1, focusthickness=0, padding=(13, 8),
                         bordercolor=self.C_BORDER)
        style.map("Ghost.TButton",
                  background=[("active", self.C_PANEL_2)],
                  bordercolor=[("active", self.C_SUBTEXT)])

        # Nút chính (accent, nổi bật, đổ bóng bằng viền tối hơn)
        style.configure("Accent.TButton", background=self.C_ACCENT, foreground="#ffffff",
                         font=("Segoe UI", 11, "bold"), borderwidth=0, focusthickness=0, padding=(18, 11))
        style.map("Accent.TButton", background=[("active", self.C_ACCENT_HOVER), ("disabled", self.C_BORDER)])

        style.configure("TProgressbar", troughcolor=self.C_PANEL_2, background=self.C_ACCENT,
                         bordercolor=self.C_PANEL_2, lightcolor=self.C_ACCENT, darkcolor=self.C_ACCENT,
                         thickness=8)

    def _card(self, parent, title=None, subtitle=None, step=None, accent=None, expand=False):
        """Tạo 1 khối 'card' nổi trên nền: viền mảnh + bóng đổ nhẹ phía dưới,
        có dải màu mảnh ở đỉnh để phân biệt từng bước trong quy trình."""
        accent = accent or self.C_ACCENT

        outer = tk.Frame(parent, bg=self.C_BG)
        outer.pack(fill="both" if expand else "x", expand=expand, padx=20, pady=(0, 16))

        # lớp bóng: 1 khối cùng kích thước, lệch 3px xuống dưới-phải
        shadow = tk.Frame(outer, bg=self.C_SHADOW)
        shadow.place(x=3, y=3, relwidth=1, relheight=1)

        card_outer = tk.Frame(outer, bg=self.C_PANEL, highlightthickness=1,
                               highlightbackground=self.C_BORDER, highlightcolor=self.C_BORDER)
        card_outer.pack(fill="both", expand=True)

        # dải màu mảnh trên đỉnh card, encode "công đoạn" của quy trình
        tk.Frame(card_outer, bg=accent, height=3).pack(fill="x", side="top")

        card = ttk.Frame(card_outer, style="Card.TFrame", padding=(18, 16, 18, 16))
        card.pack(fill="both", expand=True)

        if title:
            head = ttk.Frame(card, style="Card.TFrame")
            head.pack(fill="x", anchor="w")
            if step:
                ttk.Label(head, text=step, style="Step.TLabel").pack(side="left", padx=(0, 8))
            ttk.Label(head, text=title, style="SectionTitle.TLabel").pack(side="left")
        if subtitle:
            ttk.Label(card, text=subtitle, style="CardSub.TLabel", wraplength=780, justify="left").pack(
                anchor="w", pady=(3, 12))
        elif title:
            ttk.Frame(card, style="Card.TFrame", height=10).pack()
        return card

    # ---------------- UI layout ----------------
    def _build_ui(self):
        # ---- Header ----
        header = ttk.Frame(self.root, style="Bg.TFrame", padding=(20, 20, 20, 8))
        header.pack(fill="x")

        head_row = ttk.Frame(header, style="Bg.TFrame")
        head_row.pack(fill="x", anchor="w")

        badge = tk.Frame(head_row, bg=self.C_ACCENT, width=40, height=40)
        badge.pack(side="left", padx=(0, 12))
        badge.pack_propagate(False)
        tk.Label(badge, text="🎬", bg=self.C_ACCENT, fg="#ffffff", font=("Segoe UI", 15)).pack(expand=True)

        title_col = ttk.Frame(head_row, style="Bg.TFrame")
        title_col.pack(side="left", fill="x")
        ttk.Label(title_col, text="LogoWipe Studio", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_col, text="Tự động xoá logo/watermark trong video — hàng loạt, có GPU, có ép khung 9:16",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))

        tk.Frame(header, bg=self.C_BORDER, height=1).pack(fill="x", pady=(16, 0))

        # ---- Card: danh sách video ----
        card1 = self._card(self.root, "Video đầu vào", step="01", accent=self.C_ACCENT)

        btn_row = ttk.Frame(card1, style="Card.TFrame")
        btn_row.pack(fill="x", pady=(0, 8))
        ttk.Button(btn_row, text="➕  Chọn video", style="Accent.TButton",
                   command=self.add_videos).pack(side="left")
        ttk.Button(btn_row, text="🗑  Xoá danh sách", style="Ghost.TButton",
                   command=self.clear_videos).pack(side="left", padx=(8, 0))

        list_wrap = tk.Frame(card1, bg=self.C_PANEL_2, highlightthickness=1,
                              highlightbackground=self.C_BORDER, highlightcolor=self.C_BORDER)
        list_wrap.pack(fill="both", expand=True)
        list_scroll = ttk.Scrollbar(list_wrap, orient="vertical")
        self.listbox = tk.Listbox(
            list_wrap, height=8, bg=self.C_PANEL_2, fg=self.C_TEXT,
            selectbackground=self.C_ACCENT, selectforeground="#ffffff",
            activestyle="none", relief="flat", highlightthickness=0,
            font=("Segoe UI", 10), yscrollcommand=list_scroll.set
        )
        list_scroll.config(command=self.listbox.yview)
        self.listbox.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=6)
        list_scroll.pack(side="right", fill="y", pady=6, padx=(0, 4))
        self.listbox.bind("<Double-Button-1>", self.open_manual_select)

        if _DND_AVAILABLE:
            self.listbox.drop_target_register(DND_FILES)
            self.listbox.dnd_bind("<<Drop>>", self.on_drop_files)
            hint = "💡 Kéo-thả video vào danh sách   •   🎯 Double-click 1 video để tự chọn tay vùng logo"
            hint_color = self.C_SUBTEXT
        else:
            hint = ("⚠ Chưa cài tkinterdnd2 nên chưa kéo-thả được (pip install tkinterdnd2 --break-system-packages)   "
                    "•   🎯 Double-click 1 video để tự chọn tay vùng logo")
            hint_color = self.C_YELLOW
        ttk.Label(card1, text=hint, style="CardSub.TLabel", foreground=hint_color).pack(anchor="w", pady=(8, 0))

        # ---- Card: output ----
        card2 = self._card(self.root, "Thư mục xuất video", step="02", accent=self.C_TEAL)
        out_row = ttk.Frame(card2, style="Card.TFrame")
        out_row.pack(fill="x")
        self.output_var = tk.StringVar(value=self.output_dir)
        ttk.Entry(out_row, textvariable=self.output_var, font=("Segoe UI", 10)).pack(
            side="left", fill="x", expand=True, ipady=4)
        ttk.Button(out_row, text="Chọn...", style="Ghost.TButton",
                   command=self.choose_output_dir).pack(side="left", padx=(8, 0))

        # ---- Card: tuỳ chọn xử lý ----
        card3 = self._card(self.root, "Tuỳ chọn xử lý", step="03", accent=self.C_AMBER)

        row1 = ttk.Frame(card3, style="Card.TFrame")
        row1.pack(fill="x", pady=(0, 10))
        self.gpu_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row1, text="Dùng GPU (NVIDIA NVENC/CUVID) nếu có",
                         variable=self.gpu_var).pack(side="left")

        ttk.Label(row1, text="Số video song song:", style="Card.TLabel").pack(side="left", padx=(24, 6))
        self.threads_var = tk.IntVar(value=min(4, os.cpu_count() or 2))
        ttk.Spinbox(row1, from_=1, to=16, width=5, textvariable=self.threads_var).pack(side="left")

        row2 = ttk.Frame(card3, style="Card.TFrame")
        row2.pack(fill="x")
        self.force_916_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            row2,
            text="Ép video ngang về dọc 9:16 — giữ nguyên tỉ lệ, KHÔNG bóp méo "
                 "(lấp nền mờ tối 2 bên/trên-dưới)",
            variable=self.force_916_var
        ).pack(side="left")

        gpu_ok, cuvid_ok = check_gpu_support()
        status = (f"GPU encode (nvenc): {'✅ sẵn sàng' if gpu_ok else '❌ không tìm thấy'}"
                  f"     GPU decode (cuvid): {'✅ sẵn sàng' if cuvid_ok else '❌ không tìm thấy'}")
        ttk.Label(card3, text=status, style="CardSub.TLabel").pack(anchor="w", pady=(10, 0))

        # ---- Nút xử lý chính ----
        action_row = ttk.Frame(self.root, style="Bg.TFrame", padding=(20, 4, 20, 10))
        action_row.pack(fill="x")
        self.start_btn = ttk.Button(action_row, text="▶   Bắt đầu: Detect & Xác nhận rồi xử lý",
                                     style="Accent.TButton", command=self.start_processing)
        self.start_btn.pack(fill="x", ipady=4)

        self.progress = ttk.Progressbar(self.root, style="TProgressbar", mode="determinate")
        self.progress.pack(fill="x", padx=20, pady=(10, 12))

        # ---- Card: log ----
        log_card = self._card(self.root, "Nhật ký xử lý", step="04", accent=self.C_SUBTEXT, expand=True)

        log_wrap = tk.Frame(log_card, bg=self.C_PANEL_2, highlightthickness=1,
                             highlightbackground=self.C_BORDER, highlightcolor=self.C_BORDER)
        log_wrap.pack(fill="both", expand=True)
        log_scroll = ttk.Scrollbar(log_wrap, orient="vertical")
        self.log_text = tk.Text(
            log_wrap, height=12, bg=self.C_PANEL_2, fg=self.C_TEXT, insertbackground=self.C_TEXT,
            relief="flat", highlightthickness=0, font=("Consolas", 9), wrap="word",
            yscrollcommand=log_scroll.set
        )
        log_scroll.config(command=self.log_text.yview)
        self.log_text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=6)
        log_scroll.pack(side="right", fill="y", pady=6, padx=(0, 4))

    # ---------------- Actions ----------------
    def _parse_dnd_paths(self, data):
        """
        tkinterdnd2 trả về chuỗi path, các path có khoảng trắng sẽ được
        bọc trong {}. Hàm này tách chuỗi thành list path chính xác.
        """
        paths = []
        buf = ""
        in_brace = False
        for ch in data:
            if ch == "{":
                in_brace = True
                buf = ""
            elif ch == "}":
                in_brace = False
                paths.append(buf)
                buf = ""
            elif ch == " " and not in_brace:
                if buf:
                    paths.append(buf)
                    buf = ""
            else:
                buf += ch
        if buf:
            paths.append(buf)
        return paths

    def on_drop_files(self, event):
        valid_ext = (".mp4", ".mov", ".mkv", ".avi", ".webm")
        paths = self._parse_dnd_paths(event.data)
        added = 0
        for p in paths:
            if os.path.isdir(p):
                # nếu thả cả thư mục -> quét toàn bộ video bên trong
                for fname in os.listdir(p):
                    fp = os.path.join(p, fname)
                    if fname.lower().endswith(valid_ext) and fp not in self.video_paths:
                        self.video_paths.append(fp)
                        added += 1
            elif p.lower().endswith(valid_ext) and p not in self.video_paths:
                self.video_paths.append(p)
                added += 1
        if added == 0:
            self.log("⚠ Không có file video hợp lệ nào trong nội dung vừa thả.")
        else:
            self._refresh_listbox()
            self.log(f"➕ Đã thêm {added} video qua kéo-thả.")

    def _refresh_listbox(self):
        self.listbox.delete(0, "end")
        for vp in self.video_paths:
            label = os.path.basename(vp)
            if vp in self.manual_bboxes:
                label = "🎯 " + label + "  (đã chọn logo thủ công)"
            self.listbox.insert("end", label)

    def open_manual_select(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        video_path = self.video_paths[idx]

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            messagebox.showerror("Lỗi", "Không đọc được video này.")
            return
        # Lấy frame ở khoảng giữa video (tránh frame đen mở đầu)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        start_frame_idx = max(0, total // 3)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame_idx)
        ok, frame = cap.read()
        if not ok:
            cap.release()
            messagebox.showerror("Lỗi", "Không đọc được frame để xem trước.")
            return

        vh, vw = frame.shape[:2]
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Thu nhỏ ảnh nếu quá lớn để vừa màn hình
        max_disp = 700
        scale = min(1.0, max_disp / max(vw, vh))
        disp_w, disp_h = int(vw * scale), int(vh * scale)
        frame_disp = cv2.resize(frame_rgb, (disp_w, disp_h))

        from PIL import Image, ImageTk  # Pillow thường có sẵn cùng tkinter/opencv env

        win = tk.Toplevel(self.root)
        win.configure(bg=self.C_BG)
        win.title(f"Chọn vùng logo - {os.path.basename(video_path)}")

        info = ttk.Label(
            win,
            text="Tua tới đoạn có logo (nếu logo không xuất hiện ngay từ đầu), "
                 "kéo chuột để vẽ khung quanh logo. Có thể vẽ NHIỀU khung "
                 "(kéo tiếp ở chỗ khác để thêm vùng mới). Vẽ xong bấm 'Xác nhận'.\n"
                 "Vùng che sẽ được áp dụng từ đúng thời điểm đang tua tới trở đi."
        )
        info.pack(pady=6)

        canvas = tk.Canvas(win, width=disp_w, height=disp_h, cursor="cross")
        canvas.pack()

        img = Image.fromarray(frame_disp)
        photo = ImageTk.PhotoImage(img)
        image_id = canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.image = photo  # giữ tham chiếu tránh bị garbage collect

        seek_state = {"frame_idx": start_frame_idx}

        def fmt_time(sec):
            sec = max(0, int(sec))
            return f"{sec // 60:02d}:{sec % 60:02d}"

        time_label = ttk.Label(win, text=f"Vị trí: {fmt_time(start_frame_idx / fps)} / {fmt_time(total / fps)}")

        def seek_to_frame(frame_idx):
            frame_idx = max(0, min(total - 1, int(frame_idx)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok2, fr = cap.read()
            if not ok2:
                return
            fr_rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
            fr_disp = cv2.resize(fr_rgb, (disp_w, disp_h))
            img2 = Image.fromarray(fr_disp)
            photo2 = ImageTk.PhotoImage(img2)
            canvas.itemconfig(image_id, image=photo2)
            canvas.image = photo2
            seek_state["frame_idx"] = frame_idx
            time_label.config(text=f"Vị trí: {fmt_time(frame_idx / fps)} / {fmt_time(total / fps)}")

        def on_scale_move(val):
            seek_to_frame(float(val))

        seek_scale = ttk.Scale(
            win, from_=0, to=max(total - 1, 0), orient="horizontal",
            value=start_frame_idx, command=on_scale_move
        )
        seek_scale.pack(fill="x", padx=10, pady=(0, 2))
        time_label.pack(anchor="w", padx=10, pady=(0, 6))

        win.bind("<Destroy>", lambda e: cap.release())

        # rects: danh sách các khung ĐÃ được xác nhận giữ lại (canvas item id).
        # start/cur_id: khung đang được kéo dở (chưa thả chuột).
        # pending_id: khung vừa vẽ xong (đã thả chuột) nhưng CHƯA xác nhận giữ.
        rect_state = {"rects": [], "start": None, "cur_id": None, "pending_id": None}

        btn_frame = ttk.Frame(win)
        # Ẩn ban đầu -> chỉ hiện ra khi đã có ít nhất 1 vùng được xác nhận giữ.

        pending_frame = ttk.Frame(win)
        # Ẩn ban đầu -> chỉ hiện ra khi vừa vẽ xong 1 khung, chờ xác nhận.

        def _add_finished_rect(rect_id):
            rect_state["rects"].append(rect_id)
            if not btn_frame.winfo_ismapped():
                btn_frame.pack(pady=8)

        def _discard_pending():
            if rect_state["pending_id"] is not None:
                canvas.delete(rect_state["pending_id"])
                rect_state["pending_id"] = None
            if pending_frame.winfo_ismapped():
                pending_frame.pack_forget()

        def on_press(e):
            _discard_pending()  # đang vẽ khung mới -> huỷ khung chờ xác nhận cũ (nếu có)
            rect_state["start"] = (e.x, e.y)
            rect_state["cur_id"] = canvas.create_rectangle(
                e.x, e.y, e.x, e.y, outline="#00FF00", width=2
            )

        def on_drag(e):
            if rect_state["start"] is None or rect_state["cur_id"] is None:
                return
            sx, sy = rect_state["start"]
            canvas.coords(rect_state["cur_id"], sx, sy, e.x, e.y)

        def on_release(e):
            if rect_state["start"] is None or rect_state["cur_id"] is None:
                return
            sx, sy = rect_state["start"]
            x1, x2 = sorted((sx, e.x))
            y1, y2 = sorted((sy, e.y))
            cur_id = rect_state["cur_id"]
            rect_state["start"] = None
            rect_state["cur_id"] = None
            if (x2 - x1) < 4 or (y2 - y1) < 4:
                # Khung quá nhỏ (coi như click nhầm) -> bỏ, không tính.
                canvas.delete(cur_id)
                return
            # Chưa chốt ngay -> chuyển sang trạng thái "chờ xác nhận" (màu cam),
            # để nếu vẽ sai/lệch thì có thể vẽ lại thay vì bị lấy luôn.
            canvas.itemconfig(cur_id, outline="#FF8800", width=2)
            rect_state["pending_id"] = cur_id
            pending_frame.pack(pady=4)

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)

        def keep_pending():
            if rect_state["pending_id"] is None:
                return
            canvas.itemconfig(rect_state["pending_id"], outline="#FFD500")  # chốt -> vàng
            _add_finished_rect(rect_state["pending_id"])
            rect_state["pending_id"] = None
            pending_frame.pack_forget()

        def redo_pending():
            _discard_pending()

        ttk.Label(pending_frame, text="Vùng vừa vẽ (cam) - giữ lại hay vẽ lại?").pack(side="left", padx=(0, 6))
        ttk.Button(pending_frame, text="✅ Giữ vùng này", command=keep_pending).pack(side="left", padx=4)
        ttk.Button(pending_frame, text="🔁 Vẽ lại", command=redo_pending).pack(side="left", padx=4)

        def draw_subtitle_band():
            """Vẽ sẵn khung full-width ở dải dưới màn hình (~22% chiều cao)
            cho trường hợp che phụ đề đổi liên tục -- người dùng có thể
            kéo lại 4 cạnh nếu cần chỉnh độ cao/vị trí. Khung này cũng ở
            trạng thái "chờ xác nhận" như khung vẽ tay."""
            _discard_pending()
            band_h = int(disp_h * 0.22)
            y2 = disp_h - int(disp_h * 0.03)  # chừa lề dưới nhỏ
            y1 = y2 - band_h
            rect_id = canvas.create_rectangle(0, y1, disp_w, y2, outline="#FF8800", width=2)
            rect_state["pending_id"] = rect_id
            pending_frame.pack(pady=4)
            info.config(text="Đã vẽ sẵn dải phụ đề (cam) - bấm 'Giữ vùng này' nếu ổn, hoặc 'Vẽ lại' nếu cần chỉnh.")

        ttk.Button(win, text="📝 Tự vẽ dải che phụ đề (full-width, đáy màn hình)",
                   command=draw_subtitle_band).pack(pady=(0, 6))

        def confirm():
            if not rect_state["rects"]:
                messagebox.showwarning("Chưa chọn", "Bạn chưa xác nhận giữ vùng nào.")
                return
            start_time = seek_state["frame_idx"] / fps
            manual_pad = 10
            regions = []
            for rect_id in rect_state["rects"]:
                x1, y1, x2, y2 = canvas.coords(rect_id)
                x1, x2 = sorted((x1, x2))
                y1, y2 = sorted((y1, y2))
                real_x = x1 / scale - manual_pad
                real_y = y1 / scale - manual_pad
                real_w = (x2 - x1) / scale + manual_pad * 2
                real_h = (y2 - y1) / scale + manual_pad * 2
                regions.append((real_x, real_y, real_w, real_h, start_time))

            self.manual_bboxes[video_path] = regions
            self._refresh_listbox()
            if start_time > 0.05:
                self.log(f"🎯 Đã lưu {len(regions)} vùng logo thủ công cho "
                          f"[{os.path.basename(video_path)}] (che từ {fmt_time(start_time)} trở đi)")
            else:
                self.log(f"🎯 Đã lưu {len(regions)} vùng logo thủ công cho "
                          f"[{os.path.basename(video_path)}]")
            win.destroy()

        def cancel():
            win.destroy()

        ttk.Button(btn_frame, text="✅ Xác nhận", command=confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="❌ Hủy bỏ", command=cancel).pack(side="left", padx=6)

    def add_videos(self):
        files = filedialog.askopenfilenames(
            title="Chọn video",
            filetypes=[("Video files", "*.mp4 *.mov *.mkv *.avi *.webm"), ("All files", "*.*")]
        )
        added = False
        for f in files:
            if f not in self.video_paths:
                self.video_paths.append(f)
                added = True
        if added:
            self._refresh_listbox()

    def clear_videos(self):
        self.video_paths = []
        self.manual_bboxes = {}
        self.listbox.delete(0, "end")

    def choose_output_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.output_var.set(d)

    def log(self, msg):
        self.log_queue.put(msg)

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_log_queue)

    def start_processing(self):
        if not self.video_paths:
            messagebox.showwarning("Chưa có video", "Vui lòng chọn ít nhất 1 video.")
            return
        if shutil.which("ffmpeg") is None:
            messagebox.showerror("Thiếu FFmpeg", "Không tìm thấy ffmpeg trong PATH. Vui lòng cài đặt FFmpeg trước.")
            return

        self.start_btn.config(state="disabled")
        out_dir = self.output_var.get().strip() or self.output_dir
        use_gpu = self.gpu_var.get()
        max_workers = max(1, self.threads_var.get())
        force_916 = self.force_916_var.get()

        self.log(f"Đang phát hiện logo cho {len(self.video_paths)} video "
                  f"({max_workers} luồng song song)...")
        threading.Thread(
            target=self._detect_phase, args=(out_dir, use_gpu, max_workers, force_916), daemon=True
        ).start()

    # ---- Giai đoạn 1: detect logo cho toàn bộ video (chạy nền, song song) ----
    def _detect_phase(self, out_dir, use_gpu, max_workers, force_916):
        detected = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {}
            for vp in self.video_paths:
                if vp in self.manual_bboxes:
                    continue  # đã có bbox thủ công từ trước -> khỏi cần auto-detect
                futs[ex.submit(detect_logo_bbox, vp)] = vp
            for fut in as_completed(futs):
                vp = futs[fut]
                try:
                    detected[vp] = fut.result()
                except Exception as e:
                    self.log(f"⚠ [{os.path.basename(vp)}] Lỗi khi detect: {e}")
                    detected[vp] = None
        # Quay lại main thread để mở cửa sổ xác nhận (bắt buộc với Tkinter)
        self.root.after(0, self._start_confirmation_flow, out_dir, use_gpu, max_workers, detected, force_916)

    # ---- Giai đoạn 2: hiện cửa sổ xác nhận cho từng video có phát hiện logo ----
    def _start_confirmation_flow(self, out_dir, use_gpu, max_workers, detected, force_916):
        self._confirm_queue = []
        self._confirmed_for_run = {}
        self._copy_only = []  # video bị bỏ qua (bấm "Bỏ qua") -> copy nguyên bản

        for vp in self.video_paths:
            if vp in self.manual_bboxes:
                # Video đã có bbox thủ công từ trước (double-click) -> dùng luôn
                self._confirmed_for_run[vp] = self.manual_bboxes[vp]
                continue
            bbox = detected.get(vp)
            if bbox is None:
                self.log(f"ℹ [{os.path.basename(vp)}] Không tự phát hiện được logo -> "
                          f"mở cửa sổ để bạn tự vẽ vùng (hoặc bấm Bỏ qua nếu video không có logo).")
            self._confirm_queue.append((vp, bbox))

        self._process_next_confirmation(out_dir, use_gpu, max_workers, force_916)

    def _process_next_confirmation(self, out_dir, use_gpu, max_workers, force_916):
        if not self._confirm_queue:
            self._run_final_batch(out_dir, use_gpu, max_workers, force_916)
            return

        video_path, bbox = self._confirm_queue.pop(0)

        def handle_result(result_bbox):
            name = os.path.basename(video_path)
            if result_bbox is not None:
                self._confirmed_for_run[video_path] = result_bbox
                self.log(f"✅ [{name}] Đã xác nhận vùng logo.")
            else:
                self._copy_only.append(video_path)
                self.log(f"⏭ [{name}] Đã bỏ qua -> sẽ copy nguyên bản vào thư mục xuất (không che).")
            self._process_next_confirmation(out_dir, use_gpu, max_workers, force_916)

        self._show_confirm_dialog(video_path, bbox, handle_result)

    def _show_confirm_dialog(self, video_path, bbox, on_result):
        """
        Hiện cửa sổ preview với khung logo đã auto-detect vẽ sẵn (màu vàng),
        cho phép kéo lại nếu cần chỉnh, rồi bấm Xác nhận hoặc Bỏ qua.
        on_result(bbox_or_None) được gọi khi đóng cửa sổ.
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.log(f"⚠ [{os.path.basename(video_path)}] Không đọc được video -> bỏ qua.")
            on_result(None)
            return
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        start_frame_idx = max(0, total // 3)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame_idx)
        ok, frame = cap.read()
        if not ok:
            cap.release()
            self.log(f"⚠ [{os.path.basename(video_path)}] Không đọc được frame preview -> bỏ qua.")
            on_result(None)
            return

        vh, vw = frame.shape[:2]
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        max_disp = 700
        scale = min(1.0, max_disp / max(vw, vh))
        disp_w, disp_h = int(vw * scale), int(vh * scale)
        frame_disp = cv2.resize(frame_rgb, (disp_w, disp_h))

        from PIL import Image, ImageTk

        win = tk.Toplevel(self.root)
        win.configure(bg=self.C_BG)
        win.title(f"Xác nhận vùng logo - {os.path.basename(video_path)}")
        win.grab_set()  # bắt buộc xử lý cửa sổ này trước khi qua video tiếp theo

        ttk.Label(
            win,
            text="Tự vẽ khung quanh logo (kéo chuột). Nếu logo chỉ xuất hiện từ giữa "
                 "video, hãy tua tới đúng đoạn đó trước khi vẽ. Có thể vẽ nhiều khung "
                 "nếu có nhiều logo. Mỗi khung vẽ xong (màu cam) cần bấm 'Giữ vùng "
                 "này' mới được tính, nếu vẽ lệch thì bấm 'Vẽ lại'. Xong hết thì bấm "
                 "Xác nhận & xử lý. Nếu video không có logo, bấm Bỏ qua video này."
        ).pack(pady=6)

        canvas = tk.Canvas(win, width=disp_w, height=disp_h, cursor="cross")
        canvas.pack()

        img = Image.fromarray(frame_disp)
        photo = ImageTk.PhotoImage(img)
        image_id = canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.image = photo

        seek_state = {"frame_idx": start_frame_idx}

        def fmt_time(sec):
            sec = max(0, int(sec))
            return f"{sec // 60:02d}:{sec % 60:02d}"

        time_label = ttk.Label(win, text=f"Vị trí: {fmt_time(start_frame_idx / fps)} / {fmt_time(total / fps)}")

        def seek_to_frame(frame_idx):
            frame_idx = max(0, min(total - 1, int(frame_idx)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok2, fr = cap.read()
            if not ok2:
                return
            fr_rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
            fr_disp = cv2.resize(fr_rgb, (disp_w, disp_h))
            img2 = Image.fromarray(fr_disp)
            photo2 = ImageTk.PhotoImage(img2)
            canvas.itemconfig(image_id, image=photo2)
            canvas.image = photo2
            seek_state["frame_idx"] = frame_idx
            time_label.config(text=f"Vị trí: {fmt_time(frame_idx / fps)} / {fmt_time(total / fps)}")

        def on_scale_move(val):
            seek_to_frame(float(val))

        seek_scale = ttk.Scale(
            win, from_=0, to=max(total - 1, 0), orient="horizontal",
            value=start_frame_idx, command=on_scale_move
        )
        seek_scale.pack(fill="x", padx=10, pady=(0, 2))
        time_label.pack(anchor="w", padx=10, pady=(0, 6))

        win.bind("<Destroy>", lambda e: cap.release())

        # KHÔNG vẽ sẵn khung auto-detect nữa (thường không chuẩn) -> để
        # trống, bắt người dùng tự vẽ và tự xác nhận từng khung.
        rect_state = {"rects": [], "start": None, "cur_id": None, "pending_id": None}

        btn_frame = ttk.Frame(win)
        # Ẩn ban đầu -> chỉ hiện khi có ít nhất 1 vùng đã xác nhận giữ.

        pending_frame = ttk.Frame(win)
        # Ẩn ban đầu -> chỉ hiện khi vừa vẽ xong 1 khung, chờ xác nhận.

        def _add_finished_rect(rect_id):
            rect_state["rects"].append(rect_id)
            if not btn_frame.winfo_ismapped():
                btn_frame.pack(pady=8)

        def _discard_pending():
            if rect_state["pending_id"] is not None:
                canvas.delete(rect_state["pending_id"])
                rect_state["pending_id"] = None
            if pending_frame.winfo_ismapped():
                pending_frame.pack_forget()

        def on_press(e):
            _discard_pending()
            rect_state["start"] = (e.x, e.y)
            rect_state["cur_id"] = canvas.create_rectangle(
                e.x, e.y, e.x, e.y, outline="#00FF00", width=2
            )

        def on_drag(e):
            if rect_state["start"] is None or rect_state["cur_id"] is None:
                return
            sx, sy = rect_state["start"]
            canvas.coords(rect_state["cur_id"], sx, sy, e.x, e.y)

        def on_release(e):
            if rect_state["start"] is None or rect_state["cur_id"] is None:
                return
            sx, sy = rect_state["start"]
            x1, x2 = sorted((sx, e.x))
            y1, y2 = sorted((sy, e.y))
            cur_id = rect_state["cur_id"]
            rect_state["start"] = None
            rect_state["cur_id"] = None
            if (x2 - x1) < 4 or (y2 - y1) < 4:
                canvas.delete(cur_id)
                return
            canvas.itemconfig(cur_id, outline="#FF8800", width=2)
            rect_state["pending_id"] = cur_id
            pending_frame.pack(pady=4)

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)

        def keep_pending():
            if rect_state["pending_id"] is None:
                return
            canvas.itemconfig(rect_state["pending_id"], outline="#FFD500")
            _add_finished_rect(rect_state["pending_id"])
            rect_state["pending_id"] = None
            pending_frame.pack_forget()

        def redo_pending():
            _discard_pending()

        ttk.Label(pending_frame, text="Vùng vừa vẽ (cam) - giữ lại hay vẽ lại?").pack(side="left", padx=(0, 6))
        ttk.Button(pending_frame, text="✅ Giữ vùng này", command=keep_pending).pack(side="left", padx=4)
        ttk.Button(pending_frame, text="🔁 Vẽ lại", command=redo_pending).pack(side="left", padx=4)

        def confirm():
            if not rect_state["rects"]:
                messagebox.showwarning("Chưa có khung", "Vui lòng vẽ và xác nhận giữ ít nhất 1 khung.")
                return
            start_time = seek_state["frame_idx"] / fps
            regions = []
            for rect_id in rect_state["rects"]:
                x1, y1, x2, y2 = canvas.coords(rect_id)
                x1, x2 = sorted((x1, x2))
                y1, y2 = sorted((y1, y2))
                real_x, real_y = x1 / scale, y1 / scale
                real_w, real_h = (x2 - x1) / scale, (y2 - y1) / scale
                if real_w < 4 or real_h < 4:
                    continue
                regions.append((real_x, real_y, real_w, real_h, start_time))
            if not regions:
                messagebox.showwarning("Vùng quá nhỏ", "Vui lòng vẽ khung to hơn.")
                return
            win.destroy()
            on_result(regions)

        def skip():
            win.destroy()
            on_result(None)

        ttk.Button(btn_frame, text="✅ Xác nhận & xử lý", command=confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="⏭ Bỏ qua video này", command=skip).pack(side="left", padx=6)

        # Nếu người dùng bấm nút X đóng cửa sổ -> coi như bỏ qua video đó
        win.protocol("WM_DELETE_WINDOW", skip)

    # ---- Giai đoạn 3: xử lý hàng loạt các video đã được xác nhận + copy các video còn lại ----
    def _run_final_batch(self, out_dir, use_gpu, max_workers, force_916):
        videos_to_run = list(self._confirmed_for_run.items())
        copy_only = list(self._copy_only)

        if not videos_to_run and not copy_only:
            self.log("Không có video nào để xử lý. Kết thúc.")
            self.start_btn.config(state="normal")
            return

        self.progress["value"] = 0
        self.progress["maximum"] = len(videos_to_run) + len(copy_only)
        threading.Thread(
            target=self._run_batch_confirmed,
            args=(videos_to_run, copy_only, out_dir, use_gpu, max_workers, force_916),
            daemon=True
        ).start()

    def _run_batch_confirmed(self, videos_to_run, copy_only, out_dir, use_gpu, max_workers, force_916):
        total = len(videos_to_run) + len(copy_only)
        self.log(f"Bắt đầu xử lý {len(videos_to_run)} video che logo + "
                  f"{'ép 9:16 ' if force_916 else ''}"
                  f"{len(copy_only)} video bị bỏ qua "
                  f"({max_workers} luồng song song, GPU={'Bật' if use_gpu else 'Tắt'})")

        os.makedirs(out_dir, exist_ok=True)
        done = 0

        # Video bị bỏ qua (không che logo): nếu KHÔNG ép 9:16 -> copy nguyên
        # bản; nếu CÓ ép 9:16 -> vẫn phải chạy qua ffmpeg để đổi khung hình,
        # nên gộp chung vào hàng đợi xử lý bằng ffmpeg bên dưới.
        plain_copy = [] if force_916 else copy_only
        resize_only = copy_only if force_916 else []

        for vp in plain_copy:
            name = os.path.basename(vp)
            dest = os.path.join(out_dir, name)
            try:
                shutil.copy2(vp, dest)
                self.log(f"📋 [{name}] Đã copy nguyên bản (không che) -> {dest}")
            except Exception as e:
                self.log(f"❌ [{name}] Lỗi copy: {e}")
            done += 1
            self.progress["value"] = done

        all_jobs = list(videos_to_run) + [(vp, []) for vp in resize_only]

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {
                ex.submit(process_one_video, vp, out_dir, use_gpu, self.log, 25, bbox, force_916): vp
                for vp, bbox in all_jobs
            }
            for fut in as_completed(futures):
                vp, ok, msg = fut.result()
                name = os.path.basename(vp)
                if ok:
                    self.log(f"✅ [{name}] Hoàn tất -> {msg}")
                else:
                    self.log(f"❌ [{name}] Lỗi: {msg}")
                done += 1
                self.progress["value"] = done

        self.log("=== XONG TOÀN BỘ ===")
        self.start_btn.config(state="normal")


def main():
    if _DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = LogoRemoverApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()