/**
 * Deep Module: canvasCompositor.js
 * Centralizes Default Edit State (DEF), Font Family Mapping (FONT_MAP),
 * Deterministic Word Wrapping (wrapTitleText), and Full-Resolution 1080x1920
 * Title Card + Freeform Custom Text PNG Overlay Generation.
 */
import { API } from './api';

export const DEF = {
  title: '',
  font_name: 'impact', font_size: 52, font_bold: false, font_italic: false, title_uppercase: false,
  text_color: 'white', text_color_hex: '#ffffff',
  text_bg: 'box', text_align: 'left',
  text_x: 0, text_y: 60, title_wrap_pct: 1.0,
  text_opacity: 100, text_rotation: 0.0,
  stroke_width: 2, stroke_color_hex: '#000000',
  letter_spacing: 0, line_height: 1.2,
  box_mode: 'frame', box_radius: 40,
  box_pad_x: 30, box_pad_y: 20, box_opacity: 90,
  box_bg_color: 'custom', box_bg_color_hex: '#222222',
  source_mask_mode: 'top', source_mask_top: 0.0, source_mask_bottom: 0.0,
  crop_top: 0.0, crop_bottom: 0.0, crop_left: 0.0, crop_right: 0.0,
  video_x: 0, video_y: 0, video_w_scale: 1.0, video_h_scale: 1.0,
  bg_type: 'blur', bg_image_path: '', bg_video_path: '',
  color_grade: false, flip_h: false, flip_v: false,
  hue_shift: 0, saturation: 1.0,
  add_grain: false, grain_strength: 3, speed_tweak: false,
  vignette_strength: 50,
  subtitles: false, sub_style: 'Normal',
  sub_engine: 'gemini_fallback',
  sub_font_name: 'arialbd', sub_uppercase: false, sub_bold: true, sub_italic: false,
  sub_font_size: 36, sub_margin_v: 200, sub_x: 0, sub_bg_box: false, sub_bg_box_color: '#000000', sub_bg_box_opacity: 80,
  sub_highlight_color: '#FFD700', sub_dim_color: '#FFFFFF',
  sub_offset_ms: -100,
  watermark_text: '', watermark_pos: 'BR',
  watermark_opacity: 50, watermark_size: 28, watermark_color: '#FFFFFF',
  custom_audio_path: '', custom_audio_name: '', custom_audio_url: '',
  custom_audio_dur: 0.0, custom_audio_offset: 0.0,
  custom_audio_trim_start: 0.0, custom_audio_trim_dur: 0.0,
  video_trim_dur: 0.0,
  orig_volume: 100, custom_volume: 100,
  title_lines: null,
  custom_texts: [],
};

const EMOJI_FALLBACK = ', "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif';

export const FONT_MAP = {
  impact:          'Impact, "Arial Narrow"' + EMOJI_FALLBACK,
  arialbd:         '"Arial Black", Arial' + EMOJI_FALLBACK,
  arial:           'Arial' + EMOJI_FALLBACK,
  bebas:           '"Bebas Neue", Impact' + EMOJI_FALLBACK,
  anton:           '"Anton", Impact' + EMOJI_FALLBACK,
  ariblk:          '"Arial Black", Impact' + EMOJI_FALLBACK,
  gothicb:         '"Century Gothic", Futura' + EMOJI_FALLBACK,
  verdanab:        'Verdana, Geneva' + EMOJI_FALLBACK,
  calibrib:        'Calibri, "Gill Sans"' + EMOJI_FALLBACK,
  comicbd:         '"Comic Sans MS", Chalkboard' + EMOJI_FALLBACK,
  trebucbd:        '"Trebuchet MS", Tahoma' + EMOJI_FALLBACK,
  montserrat:      'Montserrat, "Trebuchet MS"' + EMOJI_FALLBACK,
  luckiestguy:     '"Luckiest Guy", Impact, cursive' + EMOJI_FALLBACK,
  nunito:          'Nunito, "Century Gothic"' + EMOJI_FALLBACK,
  permanentmarker: '"Permanent Marker", "Comic Sans MS", cursive' + EMOJI_FALLBACK,
};

export const wrapTitleText = (text, fontSpec, maxTextW, letterSpacing = 0) => {
  if (!text || !text.trim()) return [];
  const offCtx = document.createElement('canvas').getContext('2d');
  offCtx.font = fontSpec;
  if (letterSpacing) offCtx.letterSpacing = `${letterSpacing}px`;

  const clean = text.replace(/\r/g, '').trim();
  const paragraphs = clean.split('\n');
  const allLines = [];

  for (const para of paragraphs) {
    const words = para.split(' ').filter(Boolean);
    if (!words.length) {
      allLines.push('');
      continue;
    }
    let cur = [];
    for (const word of words) {
      const test = cur.length ? cur.join(' ') + ' ' + word : word;
      if (offCtx.measureText(test).width <= maxTextW) {
        cur.push(word);
      } else {
        if (cur.length) {
          allLines.push(cur.join(' '));
          cur = [word];
        } else {
          allLines.push(word);
          cur = [];
        }
      }
    }
    if (cur.length) {
      allLines.push(cur.join(' '));
    }
  }
  return allLines.length ? allLines : [text];
};

const BUNDLED_FONTS = {
  montserrat: 'Montserrat',
  luckiestguy: 'Luckiest Guy',
  nunito: 'Nunito',
  permanentmarker: 'Permanent Marker',
};

const ensureFontLoaded = async (fontKey) => {
  const key = (fontKey || 'impact').toLowerCase();
  if (!BUNDLED_FONTS[key]) return;
  try {
    const fontUrl = `${API}/font/file?key=${key}`;
    const face = new FontFace(BUNDLED_FONTS[key], `url(${fontUrl})`);
    if (![...document.fonts].some(f => f.family === BUNDLED_FONTS[key] && f.status === 'loaded')) {
      await face.load();
      document.fonts.add(face);
    }
  } catch (_) {
    /* fallback gracefully */
  }
};

const parseHex = (hex) => {
  if (!hex || hex.length < 7) return [255, 255, 255];
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
};

/**
 * Draw a single text box or emoji layer onto a 1080x1920 2D canvas context.
 */
export const drawSingleTextLayer = (ctx, layerCfg, W = 1080, H = 1920) => {
  const rawText = layerCfg.text || '';
  const text = layerCfg.uppercase ? rawText.toUpperCase() : rawText;
  if (!text.trim()) return;

  const fontKey = (layerCfg.font_name || 'impact').toLowerCase();
  const fontSize = layerCfg.font_size || 52;
  const fontFamily = FONT_MAP[fontKey] || `"${fontKey}", Impact${EMOJI_FALLBACK}`;
  const fontWeight = layerCfg.font_bold ? 'bold' : 'normal';
  const fontStyle = layerCfg.font_italic ? 'italic' : 'normal';
  const fontSpec = `${fontStyle} ${fontWeight} ${fontSize}px ${fontFamily}`;

  const boxMode = layerCfg.box_mode || 'frame';
  const isBubbleMode = boxMode === 'capcut' || boxMode === 'badges';
  const marginX = 26.67;
  const fullContainerW = W - 2 * marginX;
  const wrapPct = Math.max(0.12, Math.min(1.0, layerCfg.wrap_pct ?? 1.0));
  const boxW = fullContainerW * wrapPct;
  const lPadX = Math.max(6.0, Math.round(fontSize * 0.35));
  const padX = boxMode === 'none' ? 8.0 : isBubbleMode ? 20.0 + lPadX : 40.0;
  const padY = boxMode === 'none' ? 4.0 : isBubbleMode ? Math.max(2.0, Math.round(fontSize * 0.16)) : 26.67;
  const maxTextW = Math.max(40.0, boxW - 2 * padX);

  const letterSp = layerCfg.letter_spacing ?? 0;
  const cleanCurrent = text.replace(/\s+/g, ' ').trim().toLowerCase();
  const hasValidLines =
    Array.isArray(layerCfg.lines) &&
    layerCfg.lines.length > 0 &&
    layerCfg.lines.join(' ').replace(/\s+/g, ' ').trim().toLowerCase() === cleanCurrent;

  const lines = hasValidLines ? layerCfg.lines : wrapTitleText(text, fontSpec, maxTextW, letterSp);

  const fgRgb = parseHex(layerCfg.text_color_hex || '#ffffff');
  const bgRgb = parseHex(layerCfg.box_bg_color_hex || '#222222');
  const boxAlpha = boxMode === 'none' ? 0 : (layerCfg.box_opacity ?? 90) / 100;
  const lineH = (layerCfg.line_height || (boxMode === 'capcut' ? 1.35 : 1.2)) * fontSize;

  const textX = layerCfg.x || 0;
  const textY = layerCfg.y ?? 60;
  const boxRad = layerCfg.box_radius ?? 40;
  const align = layerCfg.text_align || 'left';

  const boxLeft = W / 2 - boxW / 2 + textX;
  const totalTextH = lines.length * lineH;
  const frameTotalH = totalTextH + 2 * padY;
  const boxTopY = textY - frameTotalH / 2;

  ctx.save();

  const rotation = ((layerCfg.rotation || 0) * Math.PI) / 180;
  const boxCenterX = boxLeft + boxW / 2;
  const boxCenterY = textY;
  if (rotation !== 0) {
    ctx.translate(boxCenterX, boxCenterY);
    ctx.rotate(rotation);
    ctx.translate(-boxCenterX, -boxCenterY);
  }

  const roundRect = (x, y, w, h, r) => {
    r = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  };

  ctx.font = fontSpec;
  ctx.letterSpacing = `${letterSp}px`;

  const strokePx =
    layerCfg.stroke_enabled !== false && (layerCfg.stroke_width ?? 0) > 0
      ? layerCfg.stroke_width
      : 0;
  const strokeColor = layerCfg.stroke_color_hex || '#000000';
  const [sr, sg, sb] = parseHex(strokeColor);
  const fgFill = `rgba(${fgRgb[0]},${fgRgb[1]},${fgRgb[2]},${(layerCfg.text_opacity ?? 100) / 100})`;

  const drawTextWithStroke = (line, lx, ly) => {
    if (strokePx > 0) {
      ctx.fillStyle = `rgba(${sr},${sg},${sb},1)`;
      for (const [dx, dy] of [
        [-strokePx, -strokePx],
        [strokePx, -strokePx],
        [-strokePx, strokePx],
        [strokePx, strokePx],
        [0, -strokePx],
        [0, strokePx],
        [-strokePx, 0],
        [strokePx, 0],
      ]) {
        ctx.fillText(line, lx + dx, ly + dy);
      }
    }
    ctx.fillStyle = fgFill;
    ctx.fillText(line, lx, ly);
  };

  if (boxMode === 'frame' || boxMode === 'none' || boxAlpha <= 0) {
    if (boxMode === 'frame' && boxAlpha > 0) {
      ctx.fillStyle = `rgba(${bgRgb[0]},${bgRgb[1]},${bgRgb[2]},${boxAlpha})`;
      roundRect(boxLeft, boxTopY, boxW, frameTotalH, boxRad);
      ctx.fill();
    }

    lines.forEach((line, i) => {
      const ly = boxTopY + padY + i * lineH + fontSize * 0.8;
      let lx;
      if (align === 'center') lx = boxLeft + boxW / 2;
      else if (align === 'right') lx = boxLeft + boxW - padX;
      else lx = boxLeft + padX;

      ctx.textAlign = align === 'center' ? 'center' : align === 'right' ? 'right' : 'left';
      drawTextWithStroke(line, lx, ly);
    });
  } else if (boxMode === 'capcut') {
    const lPadY = Math.max(2, Math.round(lineH * 0.16));
    const effRad = Math.min(boxRad, Math.round((lineH + 2 * lPadY) * 0.3));

    if (boxAlpha > 0) {
      ctx.fillStyle = `rgba(${bgRgb[0]},${bgRgb[1]},${bgRgb[2]},${boxAlpha})`;
      lines.forEach((line, i) => {
        const lw = ctx.measureText(line).width;
        const ly = boxTopY + i * lineH;
        let lx;
        if (align === 'center') lx = boxLeft + padX + (maxTextW - lw) / 2;
        else if (align === 'right') lx = boxLeft + boxW - padX - lw;
        else lx = boxLeft + padX;

        roundRect(lx - lPadX, ly - lPadY, lw + 2 * lPadX, lineH + 2 * lPadY, effRad);
        ctx.fill();
      });
    }

    lines.forEach((line, i) => {
      const lw = ctx.measureText(line).width;
      const ly = boxTopY + i * lineH;
      let lx;
      if (align === 'center') lx = boxLeft + padX + (maxTextW - lw) / 2;
      else if (align === 'right') lx = boxLeft + boxW - padX - lw;
      else lx = boxLeft + padX;

      ctx.textAlign = 'left';
      drawTextWithStroke(line, lx, ly + fontSize * 0.8);
    });
  } else {
    // badges mode
    const lPadY = Math.max(1, Math.round(lineH * 0.08));
    const gap = Math.max(2, Math.round(fontSize * 0.15));
    const effRad = Math.min(boxRad, Math.round((lineH + 2 * lPadY) * 0.3));

    if (boxAlpha > 0) {
      ctx.fillStyle = `rgba(${bgRgb[0]},${bgRgb[1]},${bgRgb[2]},${boxAlpha})`;
      lines.forEach((line, i) => {
        const lw = ctx.measureText(line).width;
        const ly = boxTopY + i * (lineH + gap);
        let lx;
        if (align === 'center') lx = boxLeft + padX + (maxTextW - lw) / 2;
        else if (align === 'right') lx = boxLeft + boxW - padX - lw;
        else lx = boxLeft + padX;

        roundRect(lx - lPadX, ly - lPadY, lw + 2 * lPadX, lineH + 2 * lPadY, effRad);
        ctx.fill();
      });
    }

    lines.forEach((line, i) => {
      const lw = ctx.measureText(line).width;
      const ly = boxTopY + i * (lineH + gap);
      let lx;
      if (align === 'center') lx = boxLeft + padX + (maxTextW - lw) / 2;
      else if (align === 'right') lx = boxLeft + boxW - padX - lw;
      else lx = boxLeft + padX;

      ctx.textAlign = 'left';
      drawTextWithStroke(line, lx, ly + fontSize * 0.8);
    });
  }

  ctx.restore();
};

const canvasToBase64Png = (cvs) =>
  new Promise((resolve) =>
    cvs.toBlob((blob) => {
      if (!blob) {
        resolve(null);
        return;
      }
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result.split(',')[1]);
      reader.readAsDataURL(blob);
    }, 'image/png')
  );

export const buildTitleOverlayBlob = async (clip, W = 1080, H = 1920) => {
  const st = { ...DEF, ...(clip.state || {}) };
  const rawTitle = clip.title || '';
  const hasTitle = Boolean(rawTitle.trim());

  const allCustomTexts = Array.isArray(st.custom_texts) ? st.custom_texts : [];
  const staticCustomTexts = allCustomTexts.filter(
    (t) =>
      t &&
      t.enabled !== false &&
      (t.text || '').trim() &&
      !((t.start_time || 0) > 0.01 || (t.end_time || 0) > 0.01)
  );

  if (!hasTitle && staticCustomTexts.length === 0) return null;

  // Load any bundled fonts needed
  const fontsToLoad = new Set([st.font_name || 'impact']);
  staticCustomTexts.forEach((t) => fontsToLoad.add(t.font_name || 'impact'));
  for (const fk of fontsToLoad) {
    await ensureFontLoaded(fk);
  }

  const cvs = document.createElement('canvas');
  cvs.width = W;
  cvs.height = H;
  const ctx = cvs.getContext('2d');
  ctx.clearRect(0, 0, W, H);

  if (hasTitle) {
    drawSingleTextLayer(
      ctx,
      {
        text: rawTitle,
        uppercase: st.title_uppercase,
        font_name: st.font_name,
        font_size: st.font_size,
        font_bold: st.font_bold,
        font_italic: st.font_italic,
        box_mode: st.box_mode,
        wrap_pct: st.title_wrap_pct,
        letter_spacing: st.letter_spacing,
        line_height: st.line_height,
        lines: st.title_lines,
        text_color_hex: st.text_color_hex,
        text_opacity: st.text_opacity,
        box_bg_color_hex: st.box_bg_color_hex,
        box_opacity: st.box_opacity,
        box_radius: st.box_radius,
        text_align: st.text_align,
        x: st.text_x,
        y: st.text_y,
        rotation: st.text_rotation,
        stroke_enabled: st.stroke_enabled,
        stroke_width: st.stroke_width,
        stroke_color_hex: st.stroke_color_hex,
      },
      W,
      H
    );
  }

  for (const ct of staticCustomTexts) {
    drawSingleTextLayer(ctx, ct, W, H);
  }

  return canvasToBase64Png(cvs);
};

/**
 * Render timed custom text layers (those with start_time > 0 or end_time > 0)
 * into individual 1080x1920 PNG base64 strings so FFmpeg can apply :enable='between(t,s,e)'.
 */
export const buildTimedCustomTextBlobs = async (clip, W = 1080, H = 1920) => {
  const st = { ...DEF, ...(clip.state || {}) };
  const allCustomTexts = Array.isArray(st.custom_texts) ? st.custom_texts : [];
  const timedLayers = allCustomTexts.filter(
    (t) =>
      t &&
      t.enabled !== false &&
      (t.text || '').trim() &&
      ((t.start_time || 0) > 0.01 || (t.end_time || 0) > 0.01)
  );
  if (timedLayers.length === 0) return [];

  for (const t of timedLayers) {
    await ensureFontLoaded(t.font_name || 'impact');
  }

  const results = [];
  for (const t of timedLayers) {
    const cvs = document.createElement('canvas');
    cvs.width = W;
    cvs.height = H;
    const ctx = cvs.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    drawSingleTextLayer(ctx, t, W, H);
    const b64 = await canvasToBase64Png(cvs);
    if (b64) {
      results.push({
        b64,
        start_time: Number(t.start_time || 0),
        end_time: Number(t.end_time || 0),
      });
    }
  }
  return results;
};
