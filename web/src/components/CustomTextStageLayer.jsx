import React, { useState } from 'react';
import { RotateCw, Copy, Trash2 } from 'lucide-react';
import { FONT_MAP, wrapTitleText } from '../utils/canvasCompositor';

/**
 * Deep Module: CustomTextStageLayer.jsx
 * Renders all freeform custom text / emoji layers on the 9:16 stage (324x576)
 * with CapCut-style interactive drag, 4-corner resize (width wrap_pct + font_size),
 * top rotation handle, double-click inline editing, and timeline visibility indicator.
 */
export default function CustomTextStageLayer({
  customTexts = [],
  selectedLayer,
  selCustomTextIdx,
  currentTime = 0,
  canvasRef,
  onSelectLayer,
  onUpdateCustomTexts,
}) {
  const [editingIdx, setEditingIdx] = useState(-1);
  const scale = 324 / 1080;

  const updateOne = (idx, patch, commit = false) => {
    const next = customTexts.map((item, i) => (i === idx ? { ...item, ...patch } : item));
    onUpdateCustomTexts(next, commit);
  };

  const removeOne = (idx) => {
    const next = customTexts.filter((_, i) => i !== idx);
    onUpdateCustomTexts(next, true);
    if (selCustomTextIdx === idx) {
      onSelectLayer(null, -1);
    }
  };

  const duplicateOne = (idx) => {
    const src = customTexts[idx];
    if (!src) return;
    const copy = {
      ...src,
      id: `ctxt_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      y: Math.min(1860, (src.y ?? 960) + 70),
    };
    const next = [...customTexts, copy];
    onUpdateCustomTexts(next, true);
    onSelectLayer('custom_text', next.length - 1);
  };

  const startMove = (e, idx) => {
    if (e.target.dataset.handle || editingIdx === idx) return;
    e.stopPropagation();
    e.preventDefault();
    onSelectLayer('custom_text', idx);

    const rect = canvasRef.current
      ? canvasRef.current.getBoundingClientRect()
      : { width: 324, height: 576 };
    const startX = e.clientX;
    const startY = e.clientY;
    const item = customTexts[idx] || {};
    const origX = item.x ?? 0;
    const origY = item.y ?? 1290;
    let latestPatch = null;

    const onMove = (me) => {
      const dx1080 = Math.round(((me.clientX - startX) / (rect.width || 324)) * 1080);
      const dy1920 = Math.round(((me.clientY - startY) / (rect.height || 576)) * 1920);
      let newX = Math.max(-520, Math.min(520, origX + dx1080));
      // Snap to horizontal center when close to 0
      if (Math.abs(newX) < 12) newX = 0;
      const newY = Math.max(20, Math.min(1900, origY + dy1920));
      latestPatch = { x: newX, y: newY };
      updateOne(idx, latestPatch, false);
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      if (latestPatch) updateOne(idx, latestPatch, true);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const startCornerResize = (e, idx, corner) => {
    e.stopPropagation();
    e.preventDefault();
    const startX = e.clientX;
    const startY = e.clientY;
    const item = customTexts[idx] || {};
    const startWrap = item.wrap_pct ?? 0.78;
    const startSize = item.font_size ?? 40;
    const signX = corner === 'tr' || corner === 'br' ? 1 : -1;
    const signY = corner === 'bl' || corner === 'br' ? 1 : -1;
    let latestPatch = null;

    const onMove = (me) => {
      const dx = (me.clientX - startX) * signX;
      const dy = (me.clientY - startY) * signY;
      const newWrap = Math.max(0.15, Math.min(1.0, startWrap + (dx * 2) / 308));
      const newSize = Math.max(16, Math.min(160, Math.round(startSize + dy * 0.45)));
      latestPatch = {
        wrap_pct: parseFloat(newWrap.toFixed(3)),
        font_size: newSize,
      };
      updateOne(idx, latestPatch, false);
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      if (latestPatch) updateOne(idx, latestPatch, true);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const startRotate = (e, idx) => {
    e.stopPropagation();
    e.preventDefault();
    const startX = e.clientX;
    const item = customTexts[idx] || {};
    const startRot = item.rotation || 0;
    let latestPatch = null;

    const onMove = (me) => {
      const deltaX = me.clientX - startX;
      let newRot = Math.max(-180, Math.min(180, Math.round(startRot + deltaX * 0.6)));
      if (Math.abs(newRot) < 3) newRot = 0;
      latestPatch = { rotation: newRot };
      updateOne(idx, latestPatch, false);
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      if (latestPatch) updateOne(idx, latestPatch, true);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  return (
    <>
      {customTexts.map((item, idx) => {
        if (!item || item.enabled === false) return null;
        const rawText = item.text || '';
        if (!rawText.trim() && editingIdx !== idx) return null;

        const isSelected = selectedLayer?.type === 'custom_text' && selCustomTextIdx === idx;
        const stTime = Number(item.start_time || 0);
        const endTime = Number(item.end_time || 0);
        const hasTime = stTime > 0.01 || endTime > 0.01;
        const isVisibleAtTime =
          !hasTime || (currentTime >= stTime && (endTime > 0.01 ? currentTime <= endTime : true));

        if (!isVisibleAtTime && !isSelected) return null;

        const yPct = Math.max(0, Math.min(100, ((item.y ?? 1290) / 1920) * 100));
        const textX = (item.x || 0) * scale;
        const wrapPct = Math.max(0.15, Math.min(1.0, item.wrap_pct ?? 0.78));
        const fullContainerW = 324 - 16;
        const boxW = fullContainerW * wrapPct;
        const fontSize1080 = item.font_size || 40;
        const fontSize = Math.max(8, Math.round(fontSize1080 * scale));
        const boxMode = item.box_mode || 'frame';
        const boxOpacity = boxMode === 'none' ? 0 : item.box_opacity ?? 90;
        const boxHex = item.box_bg_color_hex || '#000000';
        const boxAlpha = Math.round((boxOpacity / 100) * 255)
          .toString(16)
          .padStart(2, '0');
        const fontFamily =
          FONT_MAP[(item.font_name || 'impact').toLowerCase()] ||
          `"${item.font_name}", Impact, "Segoe UI Emoji", sans-serif`;
        const rotation = item.rotation || 0;
        const displayText = item.uppercase ? rawText.toUpperCase() : rawText;

        const strokeEnabled = item.stroke_enabled !== false;
        const strokeWidth = item.stroke_width ?? 2;
        const strokeColor = item.stroke_color_hex || '#000000';
        const strokePx = strokeEnabled && strokeWidth > 0 ? Math.max(1, Math.round(strokeWidth * scale)) : 0;
        const strokeShadow =
          strokePx > 0
            ? [
                [-strokePx, -strokePx],
                [strokePx, -strokePx],
                [-strokePx, strokePx],
                [strokePx, strokePx],
                [0, -strokePx],
                [0, strokePx],
                [-strokePx, 0],
                [strokePx, 0],
              ]
                .map(([dx, dy]) => `${dx}px ${dy}px 0 ${strokeColor}`)
                .join(', ')
            : 'none';

        const frameAlign = item.text_align || 'center';
        const textStyle = {
          fontFamily,
          fontSize: `${fontSize}px`,
          color: item.text_color_hex || '#ffffff',
          textShadow: strokeShadow,
          textAlign: frameAlign,
          fontWeight: item.font_bold !== false ? 'bold' : 'normal',
          fontStyle: item.font_italic ? 'italic' : 'normal',
          lineHeight: item.line_height || 1.2,
          letterSpacing: `${(item.letter_spacing ?? 0) * scale}px`,
          opacity: (item.text_opacity ?? 100) / 100,
        };

        // Compute wrapped lines at 1080p scale for 1:1 parity with export
        const isBubbleMode = boxMode === 'capcut' || boxMode === 'badges';
        const fullW1080 = 1080 - 2 * 26.67;
        const boxW1080 = fullW1080 * wrapPct;
        const lPadX1080 = Math.max(6.0, Math.round(fontSize1080 * 0.35));
        const padX1080 = boxMode === 'none' ? 8.0 : isBubbleMode ? 20.0 + lPadX1080 : 40.0;
        const maxTextW1080 = Math.max(40.0, boxW1080 - 2 * padX1080);
        const fontSpec1080 = `${item.font_italic ? 'italic' : 'normal'} ${
          item.font_bold !== false ? 'bold' : 'normal'
        } ${fontSize1080}px ${fontFamily}`;
        const lines = wrapTitleText(displayText, fontSpec1080, maxTextW1080, item.letter_spacing ?? 0);

        let padH, padV;
        if (boxMode === 'none' || boxOpacity <= 0) {
          padH = 2;
          padV = 2;
        } else if (boxMode === 'frame') {
          padH = Math.round(40 * scale);
          padV = Math.round(26.67 * scale);
        } else if (boxMode === 'capcut') {
          padH = Math.max(3, Math.round(fontSize * 0.35));
          padV = Math.max(1, Math.round(fontSize * 0.16));
        } else {
          padH = Math.max(3, Math.round(fontSize * 0.35));
          padV = Math.max(1, Math.round(fontSize * 0.08));
        }
        const effRadPx = Math.round((item.box_radius ?? 16) * scale);

        const handles = isSelected ? (
          <>
            {/* Floating Mini Action Bar */}
            <div
              className="absolute -top-12 left-1/2 -translate-x-1/2 flex items-center gap-1 bg-gray-950/95 border border-amber-500/70 text-amber-300 text-[7.5px] font-bold px-1.5 py-0.5 rounded-full shadow-xl whitespace-nowrap z-50 pointer-events-auto"
              data-handle="toolbar"
              onPointerDown={(e) => e.stopPropagation()}
            >
              <span>✨ Text #{idx + 1}</span>
              {hasTime && (
                <span className="text-cyan-300 font-mono">
                  ⏱{stTime.toFixed(1)}s-{endTime > 0 ? `${endTime.toFixed(1)}s` : 'Hết'}
                </span>
              )}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  updateOne(idx, { x: 0 }, true);
                }}
                className="px-1 py-0.2 bg-gray-800 hover:bg-gray-700 text-gray-200 rounded"
                title="Căn giữa ngang"
              >
                ↺ Giữa
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  duplicateOne(idx);
                }}
                className="p-0.5 bg-indigo-900/80 hover:bg-indigo-700 text-indigo-200 rounded"
                title="Nhân bản lớp chữ này"
              >
                <Copy className="w-2.5 h-2.5" />
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  removeOne(idx);
                }}
                className="p-0.5 bg-red-900/80 hover:bg-red-600 text-red-200 rounded"
                title="Xóa lớp chữ này"
              >
                <Trash2 className="w-2.5 h-2.5" />
              </button>
            </div>

            {/* Rotate handle */}
            <div
              className="absolute -top-6 left-1/2 -translate-x-1/2 flex flex-col items-center pointer-events-auto z-40"
              data-handle="rotate"
              onPointerDown={(e) => startRotate(e, idx)}
            >
              <div
                className="w-4 h-4 rounded-full bg-amber-500 border border-amber-200 text-black flex items-center justify-center shadow-lg hover:scale-125 transition-transform cursor-grab active:cursor-grabbing"
                title="Kéo trái/phải để xoay chữ"
              >
                <RotateCw className="w-2.5 h-2.5" />
              </div>
              <div className="w-0.5 h-1.5 bg-amber-400/80" />
            </div>

            {/* 4 Corner Resize Handles */}
            <div
              className="absolute -top-1.5 -left-1.5 w-3 h-3 rounded-sm bg-white border-2 border-amber-500 shadow cursor-nwse-resize hover:scale-125 transition-transform z-40"
              data-handle="resize-tl"
              onPointerDown={(e) => startCornerResize(e, idx, 'tl')}
            />
            <div
              className="absolute -top-1.5 -right-1.5 w-3 h-3 rounded-sm bg-white border-2 border-amber-500 shadow cursor-nesw-resize hover:scale-125 transition-transform z-40"
              data-handle="resize-tr"
              onPointerDown={(e) => startCornerResize(e, idx, 'tr')}
            />
            <div
              className="absolute -bottom-1.5 -left-1.5 w-3 h-3 rounded-sm bg-white border-2 border-amber-500 shadow cursor-nesw-resize hover:scale-125 transition-transform z-40"
              data-handle="resize-bl"
              onPointerDown={(e) => startCornerResize(e, idx, 'bl')}
            />
            <div
              className="absolute -bottom-1.5 -right-1.5 w-3 h-3 rounded-sm bg-white border-2 border-amber-500 shadow cursor-nwse-resize hover:scale-125 transition-transform z-40"
              data-handle="resize-br"
              onPointerDown={(e) => startCornerResize(e, idx, 'br')}
            />
          </>
        ) : null;

        const inlineEditor =
          editingIdx === idx ? (
            <textarea
              autoFocus
              value={item.text || ''}
              onChange={(e) => updateOne(idx, { text: e.target.value }, false)}
              onBlur={(e) => {
                updateOne(idx, { text: e.target.value }, true);
                setEditingIdx(-1);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  updateOne(idx, { text: e.target.value }, true);
                  setEditingIdx(-1);
                }
              }}
              className="w-full bg-black/90 text-white rounded p-1 outline-none resize-none border border-amber-400"
              style={{
                fontFamily,
                fontSize: `${fontSize}px`,
                textAlign: frameAlign,
                lineHeight: item.line_height || 1.2,
              }}
            />
          ) : null;

        return (
          <div
            key={item.id || idx}
            className={`absolute pointer-events-auto select-none z-35 transition-shadow ${
              isSelected
                ? 'ring-2 ring-amber-400 shadow-2xl'
                : 'hover:ring-1 hover:ring-amber-400/60'
            }`}
            style={{
              top: `${yPct}%`,
              left: '50%',
              width: `${boxW}px`,
              opacity: !isVisibleAtTime && isSelected ? 0.4 : 1,
              transform: `translate(calc(-50% + ${textX}px), -50%) rotate(${rotation}deg)`,
              transformOrigin: 'center center',
            }}
            onPointerDown={(e) => startMove(e, idx)}
            onDoubleClick={(e) => {
              e.stopPropagation();
              setEditingIdx(idx);
            }}
          >
            {boxMode === 'capcut' && boxOpacity > 0 ? (
              <div
                className={`relative border border-dashed ${
                  isSelected ? 'border-amber-400' : 'border-transparent hover:border-amber-400/60'
                } cursor-move p-0.5`}
                style={{ width: `${boxW}px`, textAlign: frameAlign }}
              >
                {handles}
                {inlineEditor || (
                  <div
                    style={{
                      textAlign: frameAlign,
                      lineHeight: item.line_height || 1.35,
                      padding: `${padV}px ${padH}px`,
                    }}
                  >
                    <span
                      style={{
                        ...textStyle,
                        display: 'inline',
                        backgroundColor: `${boxHex}${boxAlpha}`,
                        borderRadius: `${effRadPx}px`,
                        boxDecorationBreak: 'clone',
                        WebkitBoxDecorationBreak: 'clone',
                        padding: `${padV}px ${padH}px`,
                        boxShadow: `${padH}px 0 0 ${boxHex}${boxAlpha}, -${padH}px 0 0 ${boxHex}${boxAlpha}`,
                        wordBreak: 'break-word',
                        whiteSpace: 'pre-line',
                      }}
                    >
                      {lines.join('\n')}
                    </span>
                  </div>
                )}
              </div>
            ) : boxMode === 'badges' && boxOpacity > 0 ? (
              <div
                className={`relative border border-dashed ${
                  isSelected ? 'border-amber-400' : 'border-transparent hover:border-amber-400/60'
                } cursor-move p-0.5`}
                style={{ width: `${boxW}px` }}
              >
                {handles}
                {inlineEditor || (
                  <div
                    className="flex flex-col select-none"
                    style={{
                      alignItems:
                        frameAlign === 'right'
                          ? 'flex-end'
                          : frameAlign === 'center'
                          ? 'center'
                          : 'flex-start',
                    }}
                  >
                    {lines.map((line, i) => (
                      <div
                        key={i}
                        style={{
                          display: 'flex',
                          justifyContent:
                            frameAlign === 'right'
                              ? 'flex-end'
                              : frameAlign === 'center'
                              ? 'center'
                              : 'flex-start',
                          marginBottom:
                            i < lines.length - 1 ? `${Math.max(2, Math.round(fontSize * 0.15))}px` : 0,
                          maxWidth: '100%',
                        }}
                      >
                        <span
                          style={{
                            ...textStyle,
                            display: 'inline-block',
                            backgroundColor: `${boxHex}${boxAlpha}`,
                            borderRadius: `${effRadPx}px`,
                            padding: `${padV}px ${padH}px`,
                            lineHeight: 1.15,
                            wordBreak: 'break-word',
                            whiteSpace: 'pre-wrap',
                          }}
                        >
                          {line || '\u00A0'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              // Frame mode or Transparent/Emoji mode (boxMode === 'none' || boxOpacity === 0)
              <div
                className={`relative border border-dashed ${
                  isSelected ? 'border-amber-400' : 'border-transparent hover:border-amber-400/60'
                } cursor-move transition-colors`}
                style={{
                  width: `${boxW}px`,
                  backgroundColor:
                    boxMode !== 'none' && boxOpacity > 0 ? `${boxHex}${boxAlpha}` : 'transparent',
                  borderRadius: `${effRadPx}px`,
                  padding: `${padV}px ${padH}px`,
                }}
              >
                {handles}
                {inlineEditor || (
                  <p
                    style={{
                      ...textStyle,
                      textAlign: frameAlign,
                      wordBreak: 'break-word',
                      whiteSpace: 'pre-line',
                      lineHeight: item.line_height || 1.2,
                    }}
                  >
                    {lines.join('\n')}
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}

