import React from 'react';
import {
  Plus,
  Trash2,
  Copy,
  AlignLeft,
  AlignCenter,
  AlignRight,
  Clock,
  Sparkles,
  Smartphone,
} from 'lucide-react';

const QUICK_EMOJIS = ['👉', '👇', '👈', '👆', '💬', '⚠️', '🔥', '🚨', '👀', '❤️'];

/**
 * Deep Module: CustomTextInspector.jsx
 * Property Inspector controls for managing multiple freeform CapCut-style text & emoji layers,
 * 1-click Facebook Reels Comment CTA preset, batch synchronization across clips, and timing controls.
 */
export default function CustomTextInspector({
  customTexts = [],
  selCustomTextIdx = -1,
  setSelCustomTextIdx,
  onSelectLayer,
  onUpdateCustomTexts,
  onSyncCustomTextsToAll,
  onEnableFbMockup,
  currentTime = 0,
  clipDuration = 16,
  FontPicker,
  Slider,
  Toggle,
  ColorPicker,
}) {
  const createId = () => `ctxt_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;

  const handleAddTextBox = () => {
    const newLayer = {
      id: createId(),
      text: 'check the comments to watch part 2',
      font_name: 'impact',
      font_size: 38,
      font_bold: true,
      font_italic: false,
      uppercase: false,
      text_align: 'center',
      text_color_hex: '#ffffff',
      text_opacity: 100,
      box_mode: 'frame',
      box_bg_color_hex: '#000000',
      box_opacity: 92,
      box_radius: 12,
      stroke_enabled: true,
      stroke_width: 2,
      stroke_color_hex: '#000000',
      letter_spacing: 0,
      line_height: 1.2,
      x: -55,
      y: 1300,
      wrap_pct: 0.76,
      rotation: 0,
      start_time: 0,
      end_time: 0,
      enabled: true,
    };
    const next = [...customTexts, newLayer];
    onUpdateCustomTexts(next, true);
    setSelCustomTextIdx(next.length - 1);
    onSelectLayer('custom_text', next.length - 1);
  };

  const handleAddEmoji = (emojiChar = '👉') => {
    const newLayer = {
      id: createId(),
      text: emojiChar,
      font_name: 'arialbd',
      font_size: 92,
      font_bold: true,
      font_italic: false,
      uppercase: false,
      text_align: 'center',
      text_color_hex: '#ffffff',
      text_opacity: 100,
      box_mode: 'none',
      box_bg_color_hex: '#000000',
      box_opacity: 0,
      box_radius: 0,
      stroke_enabled: false,
      stroke_width: 0,
      stroke_color_hex: '#000000',
      letter_spacing: 0,
      line_height: 1.1,
      x: 430,
      y: 1300,
      wrap_pct: 0.22,
      rotation: 0,
      start_time: 0,
      end_time: 0,
      enabled: true,
    };
    const next = [...customTexts, newLayer];
    onUpdateCustomTexts(next, true);
    setSelCustomTextIdx(next.length - 1);
    onSelectLayer('custom_text', next.length - 1);
  };

  const handleAddFbCommentCtaPreset = () => {
    const ctaBox = {
      id: createId(),
      text: 'check the comments to watch part 2',
      font_name: 'impact',
      font_size: 38,
      font_bold: true,
      font_italic: false,
      uppercase: false,
      text_align: 'center',
      text_color_hex: '#ffffff',
      text_opacity: 100,
      box_mode: 'frame',
      box_bg_color_hex: '#000000',
      box_opacity: 92,
      box_radius: 10,
      stroke_enabled: true,
      stroke_width: 2,
      stroke_color_hex: '#000000',
      letter_spacing: 0,
      line_height: 1.2,
      x: -60,
      y: 1300,
      wrap_pct: 0.76,
      rotation: 0,
      start_time: 0,
      end_time: 0,
      enabled: true,
    };
    const handEmoji = {
      id: `${createId()}_hand`,
      text: '👉',
      font_name: 'arialbd',
      font_size: 92,
      font_bold: true,
      font_italic: false,
      uppercase: false,
      text_align: 'center',
      text_color_hex: '#ffffff',
      text_opacity: 100,
      box_mode: 'none',
      box_bg_color_hex: '#000000',
      box_opacity: 0,
      box_radius: 0,
      stroke_enabled: false,
      stroke_width: 0,
      stroke_color_hex: '#000000',
      letter_spacing: 0,
      line_height: 1.1,
      x: 430,
      y: 1300,
      wrap_pct: 0.22,
      rotation: 0,
      start_time: 0,
      end_time: 0,
      enabled: true,
    };
    const next = [...customTexts, ctaBox, handEmoji];
    onUpdateCustomTexts(next, true);
    setSelCustomTextIdx(next.length - 2);
    onSelectLayer('custom_text', next.length - 2);
    if (onEnableFbMockup) onEnableFbMockup(true);
  };

  const patchSelected = (patch, commit = true) => {
    if (selCustomTextIdx < 0 || selCustomTextIdx >= customTexts.length) return;
    const next = customTexts.map((it, i) => (i === selCustomTextIdx ? { ...it, ...patch } : it));
    onUpdateCustomTexts(next, commit);
  };

  const deleteIdx = (idx) => {
    const next = customTexts.filter((_, i) => i !== idx);
    onUpdateCustomTexts(next, true);
    if (selCustomTextIdx === idx) {
      setSelCustomTextIdx(next.length > 0 ? 0 : -1);
    } else if (selCustomTextIdx > idx) {
      setSelCustomTextIdx(selCustomTextIdx - 1);
    }
  };

  const duplicateIdx = (idx) => {
    const src = customTexts[idx];
    if (!src) return;
    const copy = {
      ...src,
      id: createId(),
      y: Math.min(1860, (src.y ?? 1290) + 70),
    };
    const next = [...customTexts, copy];
    onUpdateCustomTexts(next, true);
    setSelCustomTextIdx(next.length - 1);
    onSelectLayer('custom_text', next.length - 1);
  };

  const selItem =
    selCustomTextIdx >= 0 && selCustomTextIdx < customTexts.length
      ? customTexts[selCustomTextIdx]
      : null;

  return (
    <div className="space-y-2">
      {/* 1. Quick Add Action Buttons */}
      <div className="grid grid-cols-2 gap-1.5">
        <button
          type="button"
          onClick={handleAddTextBox}
          className="py-1.5 px-2 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white rounded-lg text-[8.5px] font-bold flex items-center justify-center gap-1 shadow transition cursor-pointer"
        >
          <Plus className="w-3 h-3" /> Thêm Chữ tự do
        </button>
        <button
          type="button"
          onClick={() => handleAddEmoji('👉')}
          className="py-1.5 px-2 bg-gray-800 hover:bg-gray-700 border border-amber-500/40 text-amber-200 rounded-lg text-[8.5px] font-bold flex items-center justify-center gap-1 shadow transition cursor-pointer"
        >
          <span>👉</span> Thêm Icon / Emoji
        </button>
      </div>

      {/* 2. 1-Click Preset: Facebook Reels Comment CTA */}
      <button
        type="button"
        onClick={handleAddFbCommentCtaPreset}
        className="w-full py-1.5 px-2 bg-indigo-950/80 hover:bg-indigo-900/90 border border-indigo-500/50 rounded-lg text-[8.5px] font-bold text-indigo-200 flex items-center justify-center gap-1.5 shadow transition cursor-pointer"
        title="Tự động tạo hộp chữ 'check the comments to watch part 2' + bàn tay 👉 chỉ thẳng vào nút Comment trên khung UI Facebook"
      >
        <Smartphone className="w-3 h-3 text-cyan-400 shrink-0" />
        <span>🎯 Mẫu "Check Comments + 👉" (Chuẩn vị trí FB)</span>
      </button>

      {/* Quick Emoji Picker Bar */}
      <div className="flex items-center justify-between bg-gray-900/80 border border-gray-800 rounded-lg px-1.5 py-1">
        <span className="text-[7.5px] text-gray-400 mr-1">Chèn nhanh:</span>
        <div className="flex items-center gap-1 flex-wrap">
          {QUICK_EMOJIS.map((em) => (
            <button
              key={em}
              type="button"
              onClick={() => handleAddEmoji(em)}
              className="w-5 h-5 rounded hover:bg-gray-700 flex items-center justify-center text-[11px] transition cursor-pointer"
              title={`Thêm icon ${em}`}
            >
              {em}
            </button>
          ))}
        </div>
      </div>

      {/* 3. Batch Sync Button for Custom Texts */}
      {customTexts.length > 0 && (
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onSyncCustomTextsToAll}
            className="flex-1 py-1 px-2 bg-violet-900/50 hover:bg-violet-700/60 border border-violet-600/50 rounded-lg text-[8px] font-bold text-violet-200 transition cursor-pointer flex items-center justify-center gap-1"
            title="Copy toàn bộ các lớp chữ/icon tự do của clip này sang TẤT CẢ clip trong hàng đợi (giữ nguyên Tiêu đề riêng của từng clip)"
          >
            <Sparkles className="w-2.5 h-2.5 text-amber-300" />
            ↻ Đồng bộ Chữ tự do sang Tất cả Clip
          </button>
          <button
            type="button"
            onClick={() => {
              onUpdateCustomTexts([], true);
              setSelCustomTextIdx(-1);
            }}
            className="px-2 py-1 bg-red-950/50 hover:bg-red-900/70 border border-red-800/50 rounded-lg text-[8px] text-red-300 transition cursor-pointer"
            title="Xóa hết chữ tự do của clip này"
          >
            Xóa hết
          </button>
        </div>
      )}

      {/* 4. List of Custom Text Layers */}
      {customTexts.length === 0 ? (
        <p className="text-[8px] text-gray-500 text-center py-2 italic">
          Chưa có lớp chữ tự do nào. Bấm "+ Thêm Chữ tự do" hoặc "🎯 Mẫu Check Comments + 👉" ở trên.
        </p>
      ) : (
        <div className="space-y-1 max-h-32 overflow-y-auto pr-0.5">
          {customTexts.map((t, idx) => {
            const isSel = selCustomTextIdx === idx;
            const hasTime = (t.start_time || 0) > 0.01 || (t.end_time || 0) > 0.01;
            return (
              <div
                key={t.id || idx}
                onClick={() => {
                  setSelCustomTextIdx(idx);
                  onSelectLayer('custom_text', idx);
                }}
                className={`flex items-center justify-between gap-1 px-2 py-1 rounded-lg border text-[8.5px] cursor-pointer transition ${
                  isSel
                    ? 'bg-amber-950/50 border-amber-500/80 text-amber-200 font-semibold'
                    : 'bg-gray-900/70 border-gray-800 text-gray-300 hover:bg-gray-800/80'
                }`}
              >
                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                  <input
                    type="checkbox"
                    checked={t.enabled !== false}
                    onChange={(e) => {
                      e.stopPropagation();
                      const next = customTexts.map((it, i) =>
                        i === idx ? { ...it, enabled: e.target.checked } : it
                      );
                      onUpdateCustomTexts(next, true);
                    }}
                    className="accent-amber-500 rounded cursor-pointer"
                  />
                  <span className="text-amber-400 font-mono text-[7.5px]">#{idx + 1}</span>
                  <span className="truncate">{t.text || '(Trống)'}</span>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {hasTime && (
                    <span className="text-[7px] font-mono bg-cyan-950/80 text-cyan-300 px-1 rounded">
                      {(t.start_time || 0).toFixed(1)}s-
                      {(t.end_time || 0) > 0 ? `${Number(t.end_time).toFixed(1)}s` : 'Hết'}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      duplicateIdx(idx);
                    }}
                    className="p-0.5 text-gray-400 hover:text-indigo-300"
                    title="Nhân bản"
                  >
                    <Copy className="w-2.5 h-2.5" />
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteIdx(idx);
                    }}
                    className="p-0.5 text-gray-400 hover:text-red-400"
                    title="Xóa"
                  >
                    <Trash2 className="w-2.5 h-2.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 5. Property Controls for Selected Custom Text Layer */}
      {selItem && (
        <div className="p-2 rounded-lg bg-gray-900/70 border border-amber-500/30 space-y-2 mt-1">
          <div className="flex items-center justify-between">
            <span className="text-[8.5px] font-bold text-amber-300">
              ✏️ Đang chỉnh Lớp #{selCustomTextIdx + 1}
            </span>
            <span className="text-[7.5px] text-gray-400 font-mono">
              X:{selItem.x ?? 0} • Y:{selItem.y ?? 1290}
            </span>
          </div>

          <textarea
            value={selItem.text || ''}
            onChange={(e) => patchSelected({ text: e.target.value }, false)}
            onBlur={(e) => patchSelected({ text: e.target.value }, true)}
            rows={2}
            placeholder="Nhập nội dung chữ hoặc emoji..."
            className="w-full bg-gray-950 border border-gray-800 rounded-lg p-1.5 text-[10px] text-white outline-none focus:border-amber-500 resize-none"
          />

          <div className="grid grid-cols-2 gap-1.5">
            <div>
              <label className="text-[8px] text-gray-500 block mb-0.5">Font</label>
              <FontPicker
                value={selItem.font_name || 'impact'}
                onChange={(v) => patchSelected({ font_name: v })}
              />
            </div>
            <Slider
              label="Cỡ chữ"
              value={selItem.font_size ?? 40}
              min={16}
              max={160}
              onChange={(v) => patchSelected({ font_size: v })}
              unit="px"
            />
          </div>

          <div className="flex items-center justify-between gap-2">
            <div className="flex gap-2">
              <Toggle
                label="Bold"
                value={selItem.font_bold !== false}
                onChange={(v) => patchSelected({ font_bold: v })}
              />
              <Toggle
                label="Italic"
                value={Boolean(selItem.font_italic)}
                onChange={(v) => patchSelected({ font_italic: v })}
              />
              <Toggle
                label="AA"
                value={Boolean(selItem.uppercase)}
                onChange={(v) => patchSelected({ uppercase: v })}
              />
            </div>
            <div className="flex gap-1">
              {[
                ['left', <AlignLeft className="w-3 h-3" />],
                ['center', <AlignCenter className="w-3 h-3" />],
                ['right', <AlignRight className="w-3 h-3" />],
              ].map(([v, ico]) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => patchSelected({ text_align: v })}
                  className={`px-1.5 py-1 rounded flex items-center justify-center transition text-xs ${
                    (selItem.text_align || 'center') === v
                      ? 'bg-amber-600 text-white'
                      : 'bg-gray-800 text-gray-400'
                  }`}
                >
                  {ico}
                </button>
              ))}
            </div>
          </div>

          <ColorPicker
            label="Màu chữ"
            value={selItem.text_color_hex || '#ffffff'}
            onChange={(v) => patchSelected({ text_color_hex: v })}
            presets={['#ffffff', '#ffff00', '#00ffff', '#ff4444', '#00ff88']}
          />

          {/* Box Mode */}
          <div>
            <p className="text-[8px] text-gray-500 mb-1">Kiểu hộp nền</p>
            <div className="grid grid-cols-4 gap-1">
              {[
                ['frame', '⬜ Hộp'],
                ['capcut', '✨ CapCut'],
                ['badges', '🏷️ Thanh'],
                ['none', '🚫 Trong suốt'],
              ].map(([v, lbl]) => (
                <button
                  key={v}
                  type="button"
                  onClick={() =>
                    patchSelected({
                      box_mode: v,
                      box_opacity: v === 'none' ? 0 : Math.max(20, selItem.box_opacity || 90),
                    })
                  }
                  className={`py-1 rounded text-[7.5px] font-medium transition text-center ${
                    (selItem.box_mode || 'frame') === v
                      ? 'bg-amber-600 text-white shadow'
                      : 'bg-gray-800 text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {lbl}
                </button>
              ))}
            </div>
          </div>

          {selItem.box_mode !== 'none' && (
            <>
              <ColorPicker
                label="Màu hộp nền"
                value={selItem.box_bg_color_hex || '#000000'}
                onChange={(v) => patchSelected({ box_bg_color_hex: v })}
                presets={['#000000', '#222222', '#dc2626', '#2563eb', '#7c3aed', '#ffffff']}
              />
              <div className="grid grid-cols-2 gap-1.5">
                <Slider
                  label="Độ đậm nền"
                  value={selItem.box_opacity ?? 90}
                  min={0}
                  max={100}
                  onChange={(v) => patchSelected({ box_opacity: v })}
                  unit="%"
                />
                <Slider
                  label="Bo góc hộp"
                  value={selItem.box_radius ?? 16}
                  min={0}
                  max={60}
                  onChange={(v) => patchSelected({ box_radius: v })}
                  unit="px"
                />
              </div>
            </>
          )}

          {/* Stroke */}
          <div className="flex items-center justify-between py-1 border-t border-gray-800/60">
            <span className="text-[8.5px] text-gray-300 font-semibold">Viền chữ (Stroke)</span>
            <Toggle
              label=""
              value={selItem.stroke_enabled !== false && (selItem.stroke_width ?? 0) > 0}
              onChange={(v) =>
                patchSelected({
                  stroke_enabled: v,
                  stroke_width: v ? (selItem.stroke_width > 0 ? selItem.stroke_width : 2) : 0,
                })
              }
            />
          </div>
          {selItem.stroke_enabled !== false && (selItem.stroke_width ?? 0) > 0 && (
            <div className="grid grid-cols-2 gap-1.5">
              <Slider
                label="Độ dày viền"
                value={selItem.stroke_width ?? 2}
                min={1}
                max={10}
                onChange={(v) => patchSelected({ stroke_width: v, stroke_enabled: true })}
                unit="px"
              />
              <ColorPicker
                label="Màu viền"
                value={selItem.stroke_color_hex || '#000000'}
                onChange={(v) => patchSelected({ stroke_color_hex: v })}
                presets={['#000000', '#ffffff', '#ff0000']}
              />
            </div>
          )}

          {/* Position & Rotation */}
          <div className="grid grid-cols-2 gap-1.5 pt-1 border-t border-gray-800/60">
            <Slider
              label="Vị trí ngang (X)"
              value={selItem.x ?? 0}
              min={-500}
              max={500}
              onChange={(v) => patchSelected({ x: v })}
              unit="px"
            />
            <Slider
              label="Vị trí dọc (Y)"
              value={selItem.y ?? 1300}
              min={20}
              max={1880}
              onChange={(v) => patchSelected({ y: v })}
              unit="px"
            />
            <Slider
              label="Độ rộng khung"
              value={selItem.wrap_pct ?? 0.78}
              min={0.15}
              max={1.0}
              step={0.02}
              onChange={(v) => patchSelected({ wrap_pct: v })}
            />
            <Slider
              label="Xoay góc"
              value={selItem.rotation ?? 0}
              min={-180}
              max={180}
              onChange={(v) => patchSelected({ rotation: v })}
              unit="°"
            />
          </div>

          {/* Timing: Start Time / End Time */}
          <div className="pt-1.5 border-t border-gray-800/60 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[8px] font-bold text-cyan-300 flex items-center gap-1">
                <Clock className="w-2.5 h-2.5" /> Thời gian xuất hiện (0 = Hiện suốt clip)
              </span>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              <div>
                <label className="text-[7.5px] text-gray-400 block mb-0.5">Bắt đầu (giây)</label>
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={selItem.start_time ?? 0}
                  onChange={(e) =>
                    patchSelected({ start_time: Math.max(0, parseFloat(e.target.value) || 0) })
                  }
                  className="w-full bg-gray-950 border border-gray-800 rounded px-1.5 py-0.5 text-[9px] text-cyan-200 font-mono"
                />
              </div>
              <div>
                <label className="text-[7.5px] text-gray-400 block mb-0.5">
                  Kết thúc (0 = hết clip)
                </label>
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={selItem.end_time ?? 0}
                  onChange={(e) =>
                    patchSelected({ end_time: Math.max(0, parseFloat(e.target.value) || 0) })
                  }
                  className="w-full bg-gray-950 border border-gray-800 rounded px-1.5 py-0.5 text-[9px] text-cyan-200 font-mono"
                />
              </div>
            </div>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => patchSelected({ start_time: 0, end_time: 0 })}
                className="flex-1 py-0.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-[7.5px] cursor-pointer"
              >
                Hiện suốt clip
              </button>
              <button
                type="button"
                onClick={() => {
                  const dur = Math.max(6, clipDuration || 16);
                  patchSelected({
                    start_time: parseFloat(Math.max(0, dur - 5).toFixed(1)),
                    end_time: 0,
                  });
                }}
                className="flex-1 py-0.5 bg-cyan-950/70 hover:bg-cyan-900/80 border border-cyan-700/50 text-cyan-200 rounded text-[7.5px] cursor-pointer"
              >
                ⏱️ Chỉ 5s cuối clip
              </button>
              <button
                type="button"
                onClick={() =>
                  patchSelected({ start_time: parseFloat(currentTime.toFixed(1)) })
                }
                className="flex-1 py-0.5 bg-gray-800 hover:bg-gray-700 text-amber-300 rounded text-[7.5px] cursor-pointer"
              >
                Từ giây {currentTime.toFixed(1)}s
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

