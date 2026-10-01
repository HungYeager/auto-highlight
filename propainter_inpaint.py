#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProPainter GPU Inpainting Worker
=================================
Wrapper around ProPainter's official inference_propainter.py.
Runs as a subprocess called by inpaint_video_region() in app.py.

Outputs progress to stdout as:
    PROGRESS:<float 0-1>:<message>
    DONE:<output_mp4_path>
    ERROR:<message>
"""

import sys
import os
import argparse
import shutil
import tempfile
from pathlib import Path


if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass
os.environ['PYTHONIOENCODING'] = 'utf-8'


def emit(tag: str, payload: str):
    print(f"{tag}:{payload}", flush=True)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--video",            required=True)
    p.add_argument("--mask",             required=True,
                   help="Dir of per-frame PNG masks (white=inpaint area)")
    p.add_argument("--output",           required=True)
    p.add_argument("--propainter-dir",   required=True)
    p.add_argument("--neighbor-length",  type=int, default=10)
    p.add_argument("--ref-stride",       type=int, default=10)
    p.add_argument("--subvideo-length",  type=int, default=50)
    p.add_argument("--mask-dilation",    type=int, default=4)
    p.add_argument("--fp16",             action="store_true",
                   help="Use FP16 half-precision (saves VRAM on 6GB GPU)")
    return p.parse_args()


def main():
    args = parse_args()
    pp_dir = Path(args.propainter_dir).resolve()
    if not pp_dir.exists():
        emit("ERROR", f"ProPainter dir not found: {pp_dir}")
        sys.exit(1)

    sys.path.insert(0, str(pp_dir))

    emit("PROGRESS", "0.01:Loading ProPainter...")

    try:
        import torch
        import cv2
        import numpy as np
        import scipy.ndimage
        import imageio
        from PIL import Image
        from tqdm import tqdm

        import torchvision
        from model.modules.flow_comp_raft import RAFT_bi
        from model.recurrent_flow_completion import RecurrentFlowCompleteNet
        from model.propainter import InpaintGenerator
        from utils.download_util import load_file_from_url
        from core.utils import to_tensors
        from model.misc import get_device

        import warnings
        warnings.filterwarnings("ignore")

        device = get_device()
        use_half = args.fp16 and device != torch.device("cpu")
        emit("PROGRESS", f"0.03:Device: {device} | FP16: {use_half}")

        pretrain_url = "https://github.com/sczhou/ProPainter/releases/download/v0.1.0/"
        weights_dir  = str(pp_dir / "weights")

        # ── Load weights ──────────────────────────────────────────────────────
        emit("PROGRESS", "0.05:Loading model weights…")

        raft_ckpt = load_file_from_url(
            url=pretrain_url + "raft-things.pth",
            model_dir=weights_dir, progress=False, file_name=None
        )
        flow_ckpt = load_file_from_url(
            url=pretrain_url + "recurrent_flow_completion.pth",
            model_dir=weights_dir, progress=False, file_name=None
        )
        pp_ckpt = load_file_from_url(
            url=pretrain_url + "ProPainter.pth",
            model_dir=weights_dir, progress=False, file_name=None
        )

        emit("PROGRESS", "0.09:Initializing RAFT…")
        fix_raft = RAFT_bi(raft_ckpt, device)

        emit("PROGRESS", "0.12:Initializing RecurrentFlowCompleteNet…")
        fix_flow = RecurrentFlowCompleteNet(flow_ckpt)
        for p in fix_flow.parameters():
            p.requires_grad = False
        fix_flow.to(device).eval()

        emit("PROGRESS", "0.15:Initializing InpaintGenerator…")
        model = InpaintGenerator(model_path=pp_ckpt).to(device).eval()

        # ── Read frames & downscale to max 640 for RAM efficiency ─────────────
        emit("PROGRESS", "0.18:Reading video frames...")
        cap = cv2.VideoCapture(args.video)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        vw  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1080
        vh  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1920
        orig_size = (vw, vh)

        # Scale down for inpaint processing (max 640px maintains quality while saving 10x RAM)
        max_dim = 640
        scale = min(1.0, max_dim / max(vw, vh))
        proc_w = int(vw * scale)
        proc_w = max(16, proc_w - proc_w % 8)
        proc_h = int(vh * scale)
        proc_h = max(16, proc_h - proc_h % 8)
        proc_size = (proc_w, proc_h)

        frames_pil = []
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            if scale < 1.0:
                img = img.resize(proc_size, Image.BILINEAR)
            frames_pil.append(img)
        cap.release()

        if not frames_pil:
            emit("ERROR", f"Could not decode frames from video: {args.video}")
            sys.exit(1)

        frames_len = len(frames_pil)
        w, h = proc_size

        # ── Read masks ────────────────────────────────────────────────────────
        emit("PROGRESS", "0.22:Reading masks…")
        mask_dir  = Path(args.mask)
        mask_files = sorted(mask_dir.glob("*.png"))

        if not mask_files:
            emit("ERROR", f"No mask PNGs found in {args.mask}")
            sys.exit(1)

        # Pad/repeat if fewer masks than frames
        if len(mask_files) < frames_len:
            mask_files = list(mask_files) + [mask_files[-1]] * (frames_len - len(mask_files))

        D = args.mask_dilation
        flow_masks, masks_dilated = [], []
        for mf in mask_files[:frames_len]:
            m = Image.open(mf).convert("L").resize(proc_size, Image.NEAREST)
            m_arr = np.array(m)
            # Flow mask: larger dilation
            if D > 0:
                flow_m = scipy.ndimage.binary_dilation(m_arr, iterations=D).astype(np.uint8)
            else:
                flow_m = (m_arr > 127).astype(np.uint8)
            flow_masks.append(Image.fromarray(flow_m * 255))
            # Inpaint mask: normal dilation
            if D > 0:
                dil_m = scipy.ndimage.binary_dilation(m_arr, iterations=D).astype(np.uint8)
            else:
                dil_m = (m_arr > 127).astype(np.uint8)
            masks_dilated.append(Image.fromarray(dil_m * 255))

        # ── Tensorise ─────────────────────────────────────────────────────────
        emit("PROGRESS", "0.27:Preparing tensors…")
        frames_inp = [np.array(f).astype(np.uint8) for f in frames_pil]
        frames_t       = to_tensors()(frames_pil).unsqueeze(0) * 2 - 1
        flow_masks_t   = to_tensors()(flow_masks).unsqueeze(0)
        masks_dilated_t = to_tensors()(masks_dilated).unsqueeze(0)
        frames_t, flow_masks_t, masks_dilated_t = (
            frames_t.to(device), flow_masks_t.to(device), masks_dilated_t.to(device)
        )

        # ── Optical flow ──────────────────────────────────────────────────────
        emit("PROGRESS", "0.30:Computing optical flow (RAFT)…")
        with torch.no_grad():
            if w <= 640:
                short_clip = 12
            elif w <= 720:
                short_clip = 8
            elif w <= 1280:
                short_clip = 4
            else:
                short_clip = 2

            if frames_len > short_clip:
                gt_flows_f_list, gt_flows_b_list = [], []
                for f in range(0, frames_len, short_clip):
                    ef = min(frames_len, f + short_clip)
                    chunk = frames_t[:, (f-1 if f > 0 else 0):ef]
                    flows_f, flows_b = fix_raft(chunk, iters=20)
                    gt_flows_f_list.append(flows_f)
                    gt_flows_b_list.append(flows_b)
                    torch.cuda.empty_cache()
                    pct = 0.30 + 0.14 * (f / frames_len)
                    emit("PROGRESS", f"{pct:.3f}:Computing optical flow (RAFT frame {f}/{frames_len})...")
                gt_flows_bi = (
                    torch.cat(gt_flows_f_list, dim=1),
                    torch.cat(gt_flows_b_list, dim=1)
                )
            else:
                gt_flows_bi = fix_raft(frames_t, iters=20)
                torch.cuda.empty_cache()

            if use_half:
                frames_t      = frames_t.half()
                flow_masks_t  = flow_masks_t.half()
                masks_dilated_t = masks_dilated_t.half()
                gt_flows_bi   = (gt_flows_bi[0].half(), gt_flows_bi[1].half())
                fix_flow      = fix_flow.half()
                model         = model.half()

            emit("PROGRESS", "0.45:Completing optical flow…")
            flow_len = gt_flows_bi[0].size(1)
            sub = args.subvideo_length
            if flow_len > sub:
                pred_f_list, pred_b_list = [], []
                pad = 5
                for f in range(0, flow_len, sub):
                    sf = max(0, f - pad); ef = min(flow_len, f + sub + pad)
                    ps = max(0, f) - sf;  pe = ef - min(flow_len, f + sub)
                    pred_bi_sub, _ = fix_flow.forward_bidirect_flow(
                        (gt_flows_bi[0][:, sf:ef], gt_flows_bi[1][:, sf:ef]),
                        flow_masks_t[:, sf:ef+1]
                    )
                    pred_bi_sub = fix_flow.combine_flow(
                        (gt_flows_bi[0][:, sf:ef], gt_flows_bi[1][:, sf:ef]),
                        pred_bi_sub, flow_masks_t[:, sf:ef+1]
                    )
                    pred_f_list.append(pred_bi_sub[0][:, ps:ef-sf-pe])
                    pred_b_list.append(pred_bi_sub[1][:, ps:ef-sf-pe])
                    torch.cuda.empty_cache()
                pred_flows_bi = (
                    torch.cat(pred_f_list, dim=1),
                    torch.cat(pred_b_list, dim=1)
                )
            else:
                pred_flows_bi, _ = fix_flow.forward_bidirect_flow(
                    gt_flows_bi, flow_masks_t
                )
                pred_flows_bi = fix_flow.combine_flow(
                    gt_flows_bi, pred_flows_bi, flow_masks_t
                )
                torch.cuda.empty_cache()

            emit("PROGRESS", "0.57:Image propagation…")
            masked_frames = frames_t * (1 - masks_dilated_t)
            sub_img = min(100, sub)
            if frames_len > sub_img:
                upd_frames_list, upd_masks_list = [], []
                pad = 10
                for f in range(0, frames_len, sub_img):
                    sf = max(0, f - pad); ef = min(frames_len, f + sub_img + pad)
                    ps = max(0, f) - sf;  pe = ef - min(frames_len, f + sub_img)
                    b, t = masks_dilated_t[:, sf:ef].size()[:2]
                    pf_sub = (pred_flows_bi[0][:, sf:ef-1], pred_flows_bi[1][:, sf:ef-1])
                    prop, upd_masks = model.img_propagation(
                        masked_frames[:, sf:ef], pf_sub, masks_dilated_t[:, sf:ef], "nearest"
                    )
                    upd_f = frames_t[:, sf:ef] * (1 - masks_dilated_t[:, sf:ef]) + \
                            prop.view(b, t, 3, h, w) * masks_dilated_t[:, sf:ef]
                    upd_m = upd_masks.view(b, t, 1, h, w)
                    upd_frames_list.append(upd_f[:, ps:ef-sf-pe])
                    upd_masks_list.append(upd_m[:, ps:ef-sf-pe])
                    torch.cuda.empty_cache()
                updated_frames = torch.cat(upd_frames_list, dim=1)
                updated_masks  = torch.cat(upd_masks_list, dim=1)
            else:
                b, t = masks_dilated_t.size()[:2]
                prop, upd_masks = model.img_propagation(
                    masked_frames, pred_flows_bi, masks_dilated_t, "nearest"
                )
                updated_frames = frames_t * (1 - masks_dilated_t) + \
                                 prop.view(b, t, 3, h, w) * masks_dilated_t
                updated_masks  = upd_masks.view(b, t, 1, h, w)
                torch.cuda.empty_cache()

        # ── Inpaint transformer ───────────────────────────────────────────────
        emit("PROGRESS", "0.65:Running inpaint transformer…")
        ori_frames  = frames_inp
        comp_frames = [None] * frames_len

        neighbor_stride = args.neighbor_length // 2
        ref_num = sub // args.ref_stride if frames_len > sub else -1

        def get_ref_index(mid, neighbors, length, stride=10, num=-1):
            if num == -1:
                return [i for i in range(0, length, stride) if i not in neighbors]
            start = max(0, mid - stride * (num // 2))
            end   = min(length, mid + stride * (num // 2))
            idx   = []
            for i in range(start, end, stride):
                if i not in neighbors:
                    if len(idx) > num: break
                    idx.append(i)
            return idx

        total_iters = len(range(0, frames_len, neighbor_stride))
        for ci, f in enumerate(range(0, frames_len, neighbor_stride)):
            neighbor_ids = [i for i in range(
                max(0, f - neighbor_stride),
                min(frames_len, f + neighbor_stride + 1)
            )]
            ref_ids = get_ref_index(f, neighbor_ids, frames_len, args.ref_stride, ref_num)
            sel_imgs  = updated_frames[:, neighbor_ids + ref_ids]
            sel_masks = masks_dilated_t[:, neighbor_ids + ref_ids]
            sel_upd   = updated_masks[:, neighbor_ids + ref_ids]
            sel_flows = (
                pred_flows_bi[0][:, neighbor_ids[:-1]],
                pred_flows_bi[1][:, neighbor_ids[:-1]]
            )

            with torch.no_grad():
                l_t = len(neighbor_ids)
                pred_img = model(sel_imgs, sel_flows, sel_masks, sel_upd, l_t)
                pred_img = pred_img.view(-1, 3, h, w)
                pred_img = (pred_img + 1) / 2
                pred_img = pred_img.cpu().permute(0, 2, 3, 1).numpy() * 255
                bin_masks = masks_dilated_t[0, neighbor_ids].cpu().permute(0, 2, 3, 1).numpy().astype(np.uint8)

                for i, idx in enumerate(neighbor_ids):
                    img = np.array(pred_img[i]).astype(np.uint8) * bin_masks[i] + \
                          ori_frames[idx] * (1 - bin_masks[i])
                    if comp_frames[idx] is None:
                        comp_frames[idx] = img
                    else:
                        comp_frames[idx] = (comp_frames[idx].astype(np.float32) * 0.5 +
                                            img.astype(np.float32) * 0.5).astype(np.uint8)

            torch.cuda.empty_cache()

            if ci % max(1, total_iters // 20) == 0:
                pct = 0.65 + 0.30 * (ci / total_iters)
                emit("PROGRESS", f"{pct:.3f}:Inpainting frame {f}/{frames_len}…")

        # ── Save output ───────────────────────────────────────────────────────
        emit("PROGRESS", "0.96:Saving output video…")
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Resize back to original video resolution if downscaled
        comp_out = [cv2.resize(f, orig_size, interpolation=cv2.INTER_CUBIC) for f in comp_frames]

        # Write with imageio (handles fps cleanly)
        tmp_out = out_path.with_suffix(".tmp.mp4")
        imageio.mimwrite(str(tmp_out), comp_out, fps=fps, quality=8)

        # Mux audio from original
        import subprocess as _sp
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        mux = _sp.run([
            ffmpeg, "-y",
            "-i", str(tmp_out),
            "-i", args.video,
            "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "copy", "-movflags", "+faststart",
            str(out_path),
        ], capture_output=True, timeout=600)

        try: tmp_out.unlink(missing_ok=True)
        except Exception: pass

        if mux.returncode != 0:
            err = (mux.stderr or b"").decode(errors="replace")[-300:]
            emit("ERROR", f"FFmpeg mux failed: {err}")
            sys.exit(1)

        emit("PROGRESS", "1.0:Done.")
        emit("DONE", str(out_path))

    except Exception as exc:
        import traceback
        emit("ERROR", f"{exc}\n{traceback.format_exc()[-600:]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
