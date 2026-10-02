import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Film, Download, Trash2, Plus, Sparkles, CheckCircle2, AlertCircle,
  RefreshCw, Terminal, FolderOpen, Scissors, Square, Settings,
  Shield, Droplets, Zap, AlignLeft, AlignCenter, AlignRight,
  FlipHorizontal, FlipVertical, Image, Move, MessageSquare, Key,
  ChevronRight, Type, Layers, Palette, Copy, Eye, ChevronDown, Send, RotateCw,
  Volume2, VolumeX, Music, Crop, Mic, Loader2, Youtube, ExternalLink, Link2, X,
  Play, Clipboard
} from 'lucide-react';


const API  = 'http://127.0.0.1:8000/api';
const post = (url, body) => {
  let serialized = '{}';
  try {
    // If body contains React synthetic events or circular references, sanitize
    serialized = JSON.stringify(body || {});
  } catch (err) {
    console.error('JSON serialize error in post:', err);
    serialized = '{}';
  }
  return fetch(`${API}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: serialized,
  });
};

const toAssetUrl = (url) => {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('blob:') || url.startsWith('data:')) return url;
  if (url.startsWith('/api/')) return `http://127.0.0.1:8000${url}`;
  if (url.startsWith('/')) return `http://127.0.0.1:8000/api${url}`;
  return `http://127.0.0.1:8000/api/${url}`;
};

// ── VirtualList ── renders only visible rows (+ overscan) regardless of total count
// itemHeight: fixed px height per row; containerHeight: visible viewport px height
const VirtualList = ({ items, itemHeight, containerHeight, renderItem, className = '', style = {} }) => {
  const [scrollTop, setScrollTop] = React.useState(0);
  const overscan = 6;
  const totalHeight = items.length * itemHeight;
  const firstVisible = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const lastVisible  = Math.min(items.length, Math.ceil((scrollTop + containerHeight) / itemHeight) + overscan);
  const visible      = items.slice(firstVisible, lastVisible);

  return (
    <div
      style={{ height: containerHeight, overflowY: 'auto', ...style }}
      className={className}
      onScroll={e => setScrollTop(e.currentTarget.scrollTop)}
    >
      <div style={{ height: totalHeight, position: 'relative' }}>
        {visible.map((item, i) => (
          <div
            key={firstVisible + i}
            style={{ position: 'absolute', top: (firstVisible + i) * itemHeight, left: 0, right: 0, height: itemHeight }}
          >
            {renderItem(item, firstVisible + i)}
          </div>
        ))}
      </div>
    </div>
  );
};

  // ── Primitives ──

const Slider = ({ label, value, min, max, step = 1, onChange, unit = '' }) => {
  const isFloat = step < 1;
  const fmt = v => isFloat ? parseFloat(v).toFixed(2) : String(Math.round(v));

  const [editing, setEditing] = React.useState(false);
  const [draft,   setDraft]   = React.useState('');
  const inputRef = React.useRef(null);

  const startEdit = () => {
    setDraft(fmt(value));
    setEditing(true);
    // Focus on next tick after render
    setTimeout(() => inputRef.current?.select(), 0);
  };

  const commit = () => {
    const parsed = isFloat ? parseFloat(draft) : parseInt(draft, 10);
    if (!isNaN(parsed)) {
      const clamped = Math.min(max, Math.max(min, parsed));
      onChange(isFloat ? parseFloat(clamped.toFixed(10)) : clamped);
    }
    setEditing(false);
  };

  const onKeyDown = e => {
    if (e.key === 'Enter')  { e.preventDefault(); commit(); }
    if (e.key === 'Escape') { e.preventDefault(); setEditing(false); }
  };

  return (
    <div>
      <div className="flex justify-between mb-0.5">
        <span className="text-[10px] text-gray-400">{label}</span>
        {editing ? (
          <input
            ref={inputRef}
            type="number"
            min={min} max={max} step={step}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={onKeyDown}
            className="w-14 text-right text-[10px] font-mono bg-indigo-950 border border-indigo-500 rounded px-1 py-0 text-indigo-200 outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
          />
        ) : (
          <span
            onClick={startEdit}
            title="Click để nhập số trực tiếp"
            className="text-[10px] text-indigo-300 font-mono cursor-text hover:bg-indigo-900/50 hover:text-indigo-200 rounded px-1 transition select-none"
          >
            {fmt(value)}{unit}
          </span>
        )}
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(isFloat ? parseFloat(e.target.value) : parseInt(e.target.value))}
        className="w-full h-1 accent-indigo-500" />
    </div>
  );
};


const Toggle = ({ label, value, onChange, icon }) => (
  <label className="flex items-center justify-between cursor-pointer py-0.5">
    <span className="flex items-center gap-1.5 text-[11px] text-gray-300">{icon}{label}</span>
    <div onClick={() => onChange(!value)}
      className={`w-8 h-4 rounded-full relative cursor-pointer transition-colors ${value ? 'bg-indigo-600' : 'bg-gray-700'}`}>
      <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-all ${value ? 'left-[18px]' : 'left-0.5'}`} />
    </div>
  </label>
);

const ColorPicker = ({ label, value, onChange, presets = [] }) => (
  <div className="flex items-center gap-2">
    <span className="text-[10px] text-gray-400 flex-1">{label}</span>
    <input type="color" value={value} onChange={e => onChange(e.target.value)}
      className="w-6 h-6 rounded cursor-pointer border border-gray-700 bg-transparent" />
    {presets.map(c => (
      <button key={c} onClick={() => onChange(c)} style={{ backgroundColor: c }}
        className={`w-4 h-4 rounded-full border-2 transition ${value === c ? 'border-white' : 'border-transparent'}`} />
    ))}
  </div>
);

const Section = ({ title, icon, children, defaultOpen = false, id, active = false }) => {
  const [open, setOpen] = useState(defaultOpen);
  React.useEffect(() => {
    if (active) setOpen(true);
  }, [active]);
  return (
    <div id={id} className={`border rounded-xl overflow-hidden transition-all scroll-mt-2 ${active ? 'border-indigo-500/70 ring-1 ring-indigo-500/40 shadow-lg' : 'border-gray-800/50'}`}>
      <button onClick={() => setOpen(p => !p)}
        className={`w-full flex items-center justify-between px-3 py-2 transition ${active ? 'bg-indigo-950/40 hover:bg-indigo-900/40 text-white' : 'bg-gray-900/60 hover:bg-gray-800/40 text-gray-300'}`}>
        <span className="flex items-center gap-2 text-[11px] font-semibold">{icon}{title}</span>
        <ChevronDown className={`w-3 h-3 text-gray-400 transition-transform ${open ? '' : '-rotate-90'}`} />
      </button>
      {open && <div className="px-3 py-2 bg-gray-950/30 space-y-2">{children}</div>}
    </div>
  );
};

// ???? FontPicker: CapCut-style list ?? font name label + rendered preview ????????????????
const FONT_OPTIONS = [
  // Bundled fonts — always available, shown first
  { key: 'montserrat',      label: 'Montserrat',     bundled: true },
  { key: 'luckiestguy',     label: 'Luckiest Guy',   bundled: true },
  { key: 'nunito',          label: 'Futura (Nunito)', bundled: true },
  { key: 'permanentmarker', label: 'Komika Hand',     bundled: true },
  // System fonts
  { key: 'impact',   label: 'Impact' },
  { key: 'bebas',    label: 'Bebas Neue' },
  { key: 'anton',    label: 'Anton' },
  { key: 'ariblk',   label: 'Arial Black' },
  { key: 'arialbd',  label: 'Arial Bold' },
  { key: 'arial',    label: 'Arial' },
  { key: 'gothicb',  label: 'Century Gothic' },
  { key: 'verdanab', label: 'Verdana Bold' },
  { key: 'segoeuib', label: 'Segoe UI Bold' },
];
const _fontPreviewCache = new Map(); // module-level cache: key → objectURL

const FontPicker = ({ value, onChange }) => {
  const API = 'http://127.0.0.1:8000/api';
  const [open, setOpen] = React.useState(false);
  const [previews, setPreviews] = React.useState({});
  const ref = React.useRef(null);

  // Helper: fetch + cache a single font preview
  // ── Text ──
  // the font's own label rendered in its own typeface (CapCut style)
  const fetchPreview = React.useCallback((key) => {
    if (_fontPreviewCache.has(key)) {
      setPreviews(p => ({ ...p, [key]: _fontPreviewCache.get(key) }));
      return;
    }
    const f = FONT_OPTIONS.find(x => x.key === key);
    if (!f) return;
  // ── Encode label as URL ──
  // param; use taller canvas so descenders aren't clipped
    const label = encodeURIComponent(f.label);
    fetch(`${API}/font/preview?key=${key}&text=${label}&size=36&width=240&height=56`)
      .then(r => r.ok ? r.blob() : null)
      .then(blob => {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        _fontPreviewCache.set(key, url);
        setPreviews(p => ({ ...p, [key]: url }));
      })
      .catch(() => {});
  }, [API]);

  // ── Pre-fetch selected font on mount so trigger button always shows preview ──
React.useEffect(() => { fetchPreview(value); }, [value, fetchPreview]);

  // ── Fetch all previews when dropdown opens ──
React.useEffect(() => {
    if (!open) return;
    FONT_OPTIONS.forEach(({ key }) => fetchPreview(key));
  }, [open, fetchPreview]);

  // Close on outside click
  React.useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const selected = FONT_OPTIONS.find(f => f.key === value) || FONT_OPTIONS[0];

  // Font row: preview image IS the font name rendered in its own typeface (CapCut style)
  // Falls back to plain text label while the image is still loading.
  const FontRow = ({ f, compact = false }) => (
    <div className="flex items-center gap-1.5 min-w-0 flex-1">
      {previews[f.key]
        ? <img
            src={previews[f.key]}
            alt={f.label}
            className={`${compact ? 'h-7' : 'h-9'} object-contain object-left`}
            style={{ imageRendering: 'crisp-edges', width: compact ? 160 : 200 }}
          />
        : <span className={`${compact ? 'text-[9px]' : 'text-[10px]'} text-gray-300`}>{f.label}</span>
      }
      {f.bundled && (
        <span className="text-[6px] font-bold text-violet-400 bg-violet-900/40 px-1 py-0.5 rounded shrink-0 leading-tight">NEW</span>
      )}
    </div>
  );

  return (
    <div ref={ref} className="relative w-full mb-1.5">
      {/* ── Trigger button  ── */}
      <button type="button" onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between bg-gray-900 border border-gray-800 hover:border-indigo-600/60 rounded-lg px-2 py-1.5 text-left transition gap-1"
      >
        <FontRow f={selected} compact />
        <svg className={`w-3 h-3 text-gray-500 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7"/>
        </svg>
      </button>

      {/* ── Dropdown list  ── */}
      {open && (
        <div className="absolute z-50 left-0 right-0 mt-1 bg-[#0f0f14] border border-gray-800 rounded-xl shadow-2xl overflow-hidden">
          {/* ── Bundled section header ── */}
          <div className="px-3 pt-2 pb-0.5">
            <p className="text-[7px] text-violet-400 uppercase tracking-widest font-bold">✦ Bundled Fonts</p>
          </div>
          <div className="overflow-y-auto max-h-56">
            {FONT_OPTIONS.filter(f => f.bundled).map(f => (
              <button key={f.key} type="button"
                onClick={() => { onChange(f.key); setOpen(false); }}
                className={`w-full flex items-center px-3 py-2 hover:bg-indigo-900/25 transition text-left gap-2 ${
                  value === f.key ? 'bg-indigo-900/35 border-l-2 border-indigo-500' : 'border-l-2 border-transparent'
                }`}
              >
                <FontRow f={f} />
                {value === f.key && (
                  <svg className="w-3 h-3 text-indigo-400 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd"/>
                  </svg>
                )}
              </button>
            ))}

            {/* ── System fonts section ── */}
            <div className="px-3 pt-2 pb-0.5 border-t border-gray-800/60 mt-1">
              <p className="text-[7px] text-gray-600 uppercase tracking-widest font-bold">System Fonts</p>
            </div>
            {FONT_OPTIONS.filter(f => !f.bundled).map(f => (
              <button key={f.key} type="button"
                onClick={() => { onChange(f.key); setOpen(false); }}
                className={`w-full flex items-center px-3 py-2 hover:bg-gray-800/40 transition text-left gap-2 ${
                  value === f.key ? 'bg-gray-800/50 border-l-2 border-gray-500' : 'border-l-2 border-transparent'
                }`}
              >
                <FontRow f={f} />
                {value === f.key && (
                  <svg className="w-3 h-3 text-gray-400 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd"/>
                  </svg>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};


  // ── Status badge ──
const Badge = ({ status }) => ({
  done:      <span className="text-[9px] text-emerald-400 flex items-center gap-0.5"><CheckCircle2 className="w-2.5 h-2.5"/>Done</span>,
  uploading: <span className="text-[9px] text-amber-400 flex items-center gap-0.5 animate-pulse"><RefreshCw className="w-2.5 h-2.5 animate-spin"/>Uploading</span>,
  analyzing: <span className="text-[9px] text-indigo-400 flex items-center gap-0.5 animate-pulse"><Sparkles className="w-2.5 h-2.5"/>Analyzing</span>,
  error:     <span className="text-[9px] text-red-400 flex items-center gap-0.5"><AlertCircle className="w-2.5 h-2.5"/>Error</span>,
  queued:    <span className="text-[9px] text-gray-600">Queued</span>,
}[status] || <span className="text-[9px] text-gray-600">{status}</span>);

  // ── Default edit state ──
const DEF = {
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
};

// ── Font family map (shared across preview, canvas overlay, and font measurements) ──
const FONT_MAP = {
  impact:          'Impact, "Arial Narrow", sans-serif',
  arialbd:         '"Arial Black", Arial, sans-serif',
  arial:           'Arial, sans-serif',
  bebas:           '"Bebas Neue", Impact, sans-serif',
  anton:           '"Anton", Impact, sans-serif',
  ariblk:          '"Arial Black", Impact, sans-serif',
  gothicb:         '"Century Gothic", Futura, sans-serif',
  verdanab:        'Verdana, Geneva, sans-serif',
  calibrib:        'Calibri, "Gill Sans", sans-serif',
  comicbd:         '"Comic Sans MS", Chalkboard, sans-serif',
  trebucbd:        '"Trebuchet MS", Tahoma, sans-serif',
  montserrat:      'Montserrat, "Trebuchet MS", sans-serif',
  luckiestguy:     '"Luckiest Guy", Impact, cursive',
  nunito:          'Nunito, "Century Gothic", sans-serif',
  permanentmarker: '"Permanent Marker", "Comic Sans MS", cursive',
};

// ── Deterministic Word Wrapping Helper matching Preview, Canvas Overlay, and PIL ──
const wrapTitleText = (text, fontSpec, maxTextW, letterSpacing = 0) => {
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

// ── App ──
export default 
function App() {
  const [tab, setTab]         = useState('analyze');
  const [config, setConfig]   = useState({ api_keys: [''], output_folder: '', model_name: 'gemini-3.5-flash-lite', analysis_parallel: 3, export_threads: 2, export_crf: 20, export_preset: 'fast', export_encoder: 'libx264', export_resolution: '1080x1920', export_fps: null, box_bg_color_hex: '#222222' });
  const [videos, setVideos]   = useState([]);           // ── all videos in queue ────────────────────────────────────────────────────────
  const totalAllCandidates = useMemo(() => {
    return (videos || []).reduce((acc, v) => acc + (v.candidates?.length || 0), 0);
  }, [videos]);
const [editQueue, setEditQueue] = useState([]);       // Tab 2 queue: {clip_path, title, suggested_titles, state}
  const [selVideo, setSelVideo]   = useState(null);     // ── selected video in Tab 1
const [selCand, setSelCand]     = useState(0);        // ── selected candidate index
const [selTitle, setSelTitle]   = useState('');       // ── title user clicked in Tab 1
const [lastCutPath, setLastCutPath] = useState('');   // path of last cut clip (from /api/cut)
  const [trimStart, setTrimStart] = useState(() => Number(localStorage.getItem('trimStart') || 0));
  const [trimEnd,   setTrimEnd]   = useState(() => Number(localStorage.getItem('trimEnd') || 0));
  // analysisMode persists via localStorage: 'short' | 'story'
  const [analysisMode, setAnalysisMode] = useState(() => localStorage.getItem('analysisMode') || 'short');
  // clipDuration: user-set target length in Short Mode (persists via localStorage)
  const [clipDuration, setClipDuration] = useState(() => Number(localStorage.getItem('clipDuration') || 16));
  const [selEditIdx, setSelEditIdx]   = useState(-1);   // ── selected item in Tab 2 edit queue ────────────────────────────────────────────────────────
const [fonts, setFonts]     = useState([]);
  const [encoders, setEncoders] = useState(['libx264']);
  const [logs, setLogs]       = useState([]);
  const [showLog, setShowLog] = useState(true);
  const [showKeys, setShowKeys] = useState(true);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [cutBusy, setCutBusy] = useState(false);
  const [sendAllBusy, setSendAllBusy] = useState(false);
  const [sendAllVideosBusy, setSendAllVideosBusy] = useState(false);
  const [exportProg, setExportProg] = useState({ status: 'idle', completed: 0, total: 0, current: '' });
  const [batches, setBatches]                     = useState([]);
  const [activeBatchId, setActiveBatchId]         = useState('default');
  const [batchNameInput, setBatchNameInput]       = useState('');
  const [isEditingBatchName, setIsEditingBatchName] = useState(false);
  const [titlePrompt, setTitlePrompt]   = useState('');
  const [savedPresets, setSavedPresets] = useState([]);
  const [savePresetName, setSavePresetName] = useState('');
  const [editPresets, setEditPresets]     = useState([]);          // F2: edit style preset list
  const [editPresetName, setEditPresetName] = useState('');        // F2: new preset name input
  const [boxMode, setBoxMode]         = useState('blur');   // 'blur' | 'delogo' | 'inpaint'
  const [detectingLogo, setDetectingLogo]   = useState(false);
  const [detectingSub,  setDetectingSub]    = useState(false);
  const [detectingSubTracks, setDetectingSubTracks] = useState(false);
  const [ocrInfo, setOcrInfo] = useState({ device: 'GPU (CUDA)', is_gpu: true });
  const [transcribingSub, setTranscribingSub] = useState(false);
  // ── null ──
  const [bulkSubJob, setBulkSubJob] = useState(null);
  const bulkSubPollRef = useRef(null);

  const [videoLoaded, setVideoLoaded] = useState(false);
  const [regenningIdx,  setRegenningIdx]    = useState(-1);  // queue idx being regenerated
  // Inpaint job polling state: null | {jobId, pct, msg, status}
  // ── YouTube Direct Visual Analysis State ──
  const [showYtModal, setShowYtModal]             = useState(false);
  const [ytUrl, setYtUrl]                         = useState('');
  const [ytMode, setYtMode]                       = useState('short');
  const [ytStatus, setYtStatus]                   = useState('idle'); // 'idle' | 'analyzing' | 'done' | 'error'
  const [ytLoadingMsg, setYtLoadingMsg]           = useState('');
  const [ytInfo, setYtInfo]                       = useState(null);
  const [ytCandidates, setYtCandidates]           = useState([]);
  const [ytDownloadingMap, setYtDownloadingMap]   = useState({}); // { [idx]: { percent: number, statusText: string } }
  const [ytDownloadedSet, setYtDownloadedSet]     = useState(() => new Set());
  const [ytError, setYtError]                     = useState('');
  const [ytDownloadAllBusy, setYtDownloadAllBusy] = useState(false);
  const [ytCookiesStatus, setYtCookiesStatus]     = useState({ has_cookies: false, filename: '', size: 0 });
  const [showCookieGuide, setShowCookieGuide]     = useState(false);
  const [cookieInputText, setCookieInputText]     = useState('');
  const [showCookiePasteModal, setShowCookiePasteModal] = useState(false);
  const [ytBatchTab, setYtBatchTab]               = useState('single'); // 'single' | 'batch'
  const [ytBatchText, setYtBatchText]             = useState('');
  const [ytBatchBusy, setYtBatchBusy]             = useState(false);
  const ytCookieFileInputRef                      = useRef(null);

  // ── Preview ──
  // (Tab 2 ?? GPU CUDA + OpenCV background preview stream)
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewErr, setPreviewErr] = useState('');
  const prevTimer  = useRef(null);
  // ── Video Playback ──
  const [isPlaying, setIsPlaying] = useState(false);
  const [isEditingTitleInline, setIsEditingTitleInline] = useState(false);
  const [currentTime, setCurrentTime]     = useState(0);
  const [duration, setDuration]           = useState(0);
  const [drawMode, setDrawMode]           = useState(false);
  const [selBlurBoxIdx, setSelBlurBoxIdx] = useState(-1);
  const [drawStart, setDrawStart]         = useState(null);
  const [drawCurrent, setDrawCurrent]     = useState(null);
  const [selOverlayIdx, setSelOverlayIdx] = useState(-1);
  const [selectedLayer, setSelectedLayer] = useState({ type: null, id: null });
  const [isCroppingVideo, setIsCroppingVideo] = useState(false);
  const [isRemovingBg, setIsRemovingBg]   = useState(false);
  const overlayFileInputRef               = useRef(null);
  const audioFileInputRef                 = useRef(null);
  const customAudioRef                    = useRef(null);
  const videoRef       = useRef(null);
  const videoCanvasRef = useRef(null); // transparent canvas draws video frames
  const rafRef         = useRef(null); // requestAnimationFrame handle
  const bgImageRef     = useRef(null); // hidden <img> for bg_type='image' preview
  const bgVideoRef     = useRef(null); // hidden <video> for bg_type='video' preview
  const bgCacheRef     = useRef(null); // offscreen canvas caching pre-scaled background (avoids drawImage from large raw image every frame)
const canvasRef  = useRef(null);
  const logRef     = useRef(null);
  // F1: tracks video's rendered position in canvas each frame (for blur-box coord mapping)
  const videoFrameRef  = useRef({ fgX: 0, fgY: 0, fgW: 324, fgH: 576, vw: 1920, vh: 1080 });
  // F1: ref mirror of drawStart so onMove/onUp closures never go stale — avoids remove+readd listener on every mouse move
  const drawStartRef   = useRef(null);
  // F1: reusable pixelation canvas — avoids createElement on every RAF frame for each blur box
  const pxCvsRef       = useRef(null);
  // F4: undo history (destructive actions only — remove clip, change title)
  const undoStack      = useRef([]);
  // F3: multi-selection sets for Tab1 + Tab2
  const [selVideos, setSelVideos]         = useState(new Set());
  const [selEditIdxs, setSelEditIdxs]     = useState(new Set());
  const lastSelVideoIdxRef = useRef(-1);
  const lastSelEditIdxRef  = useRef(-1);
  // ── Track whether ──
  // we've done the initial edit_queue load from server
  const editQueueInited = useRef(false);

  // ── Text-box drag state ──
  // (refs so they don't stale-capture in pointermove closure)
  const dragActive    = useRef(false);  // ── true while pointer is held down on text box ────────────────────────────────────────────────────────
const dragRect      = useRef(null);   // ── canvas BoundingClientRect at drag start ────────────────────────────────────────────────────────
const dragStartPos  = useRef({ x: 0, y: 0 }); // ── cursor position at drag start ────────────────────────────────────────────────────────
const dragStartText = useRef({ x: 0, y: 0 }); // text_x/text_y at drag start
const dragFinalText = useRef(null);
const subDragActive = useRef(false);  // ── true while pointer is held down on subtitle box
const dragStartSub  = useRef({ margin_v: 200, x: 0 });
const dragFinalSub  = useRef(null);

  // ── Always merge with DEF so controls always show correct defaults ──
  const currentEditItem = editQueue[selEditIdx] || null;
  const editState = { ...DEF, ...(currentEditItem?.state || {}) };

  const patchEdit = useCallback((patch) => {
    if (selEditIdx < 0) return;
    setEditQueue(prev => prev.map((item, i) =>
      i === selEditIdx ? { ...item, state: { ...item.state, ...patch } } : item
    ));
    post('/edit_queue/update', { index: selEditIdx, patch });
  }, [selEditIdx]);

  const handleTranscribeSub = useCallback(async () => {
    const vPath = currentEditItem?.clip_path || currentEditItem?.path;
    if (!vPath) {
      alert('Vui lòng chọn một clip trong danh sách chỉnh sửa để tạo phụ đề.');
      return;
    }
    setTranscribingSub(true);
    try {
      const res = await post('/transcribe', {
        video_path: vPath,
        style: editState?.sub_style || 'Normal',
        engine: editState?.sub_engine || 'whisper',
        edit_state: editState,
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Lỗi server HTTP ${res.status}`);
      }
      const data = await res.json();
      if (data && data.status === 'ok') {
        const nWords = data.words?.length || 0;
        patchEdit({
          subtitles: true,
          srt_content: data.srt,
          srt_path: data.path,
          words_data: data.words,
        });
        alert(`✅ Đã bóc phụ đề thành công!\n• Nguồn: ${editState?.sub_engine === 'whisper' ? 'Stable Whisper (Khớp âm học từng từ)' : 'Gemini AI'}\n• Số từ: ${nWords > 0 ? nWords + ' từ (Acoustic Words)' : 'SRT cues'}\n• File: ${data.path}`);
      } else {
        alert(`⚠️ Không tạo được phụ đề: ${data?.detail || 'Lỗi xử lý âm thanh'}`);
      }
    } catch (err) {
      alert(`❌ Lỗi kết nối khi tạo phụ đề: ${err.message}`);
    } finally {
      setTranscribingSub(false);
    }
  }, [currentEditItem, editState, patchEdit]);

  // ── Auto-sync computed title_lines to clip state so Export uses identical lines ──
  useEffect(() => {
    if (selEditIdx < 0 || !currentEditItem) return;
    const rawTitleText = currentEditItem.title || '';
    const titleText = editState?.title_uppercase ? rawTitleText.toUpperCase() : rawTitleText;
    if (!titleText.trim()) return;

    const wrapPct = Math.max(0.3, Math.min(1.0, editState?.title_wrap_pct ?? 1.0));
    const fullContainerW = 1080 - 2 * 26.67;
    const boxW1080 = fullContainerW * wrapPct;
    const fontSize1080 = editState?.font_size || 52;
    const boxMode = editState?.box_mode || 'frame';
    const isBubbleMode = (boxMode === 'capcut' || boxMode === 'badges');
    const lPadX1080 = Math.max(6.0, Math.round(fontSize1080 * 0.35));
    const padX1080 = isBubbleMode ? (20.0 + lPadX1080) : 40.0;
    const maxTextW1080 = Math.max(50.0, boxW1080 - 2 * padX1080);
    const fontKey = (editState?.font_name || 'impact').toLowerCase();
    const fontFamily = FONT_MAP[fontKey] || `"${fontKey}", Impact, sans-serif`;
    const fontSpec1080 = `${editState?.font_italic ? 'italic' : 'normal'} ${editState?.font_bold ? 'bold' : 'normal'} ${fontSize1080}px ${fontFamily}`;
    const letterSp1080 = editState?.letter_spacing ?? 0;

    const computed = wrapTitleText(titleText, fontSpec1080, maxTextW1080, letterSp1080);
    const existing = editState?.title_lines || [];
    if (computed.length !== existing.length || computed.some((l, idx) => l !== existing[idx])) {
      patchEdit({ title_lines: computed });
    }
  }, [
    currentEditItem?.title,
    editState?.title_uppercase,
    editState?.title_wrap_pct,
    editState?.font_size,
    editState?.box_mode,
    editState?.font_name,
    editState?.font_bold,
    editState?.font_italic,
    editState?.letter_spacing,
    selEditIdx,
    patchEdit
  ]);

  // CapCut-style 4-corner resize for title box:
  // Horizontal drag → adjusts title_wrap_pct (narrower/wider lines, matching CapCut text bounding box)
  // Vertical drag   → adjusts font_size (smaller/bigger text)
  const startTitleCornerResize = useCallback((e, corner) => {
    e.stopPropagation();
    e.preventDefault();
    const startX    = e.clientX;
    const startY    = e.clientY;
    const startWrap = editState?.title_wrap_pct ?? 1.0;
    const startSize = editState?.font_size || 52;
    // canvas is 324px wide, usable box range maps to [0.3, 1.0] over 308px
    const CANVAS_USABLE = 308;
    const hDir = corner.includes('r') ? 1 : -1;
    const vDir = corner.includes('b') ? 1 : -1;

    const onMove = (me) => {
      const dx = me.clientX - startX;
      const dy = me.clientY - startY;
      // Width: each px of horizontal drag = 1px of canvas width change, mapped to wrap units
      const newWrap = Math.max(0.3, Math.min(1.0, startWrap + (dx * hDir) / CANVAS_USABLE));
      // Font: each px of vertical drag = ~0.25pt font change
      const newSize = Math.max(14, Math.min(160, Math.round(startSize + dy * vDir * 0.35)));
      patchEdit({ title_wrap_pct: parseFloat(newWrap.toFixed(3)), font_size: newSize });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [editState, patchEdit]);

  // ── Unified Layer Selection & Auto-Focus Sidebar ──
  const selectAndFocusLayer = useCallback((type, id = null) => {
    setSelectedLayer({ type, id });
    if (type !== 'video') {
      setIsCroppingVideo(false);
    }
    if (type === 'overlay') setSelOverlayIdx(id);
    else setSelOverlayIdx(-1);
    if (type === 'blur_box') setSelBlurBoxIdx(id);
    else setSelBlurBoxIdx(-1);

    const sectionMap = {
      video: 'section-video',
      title: 'section-title',
      subtitle: 'section-subtitles',
      overlay: 'section-multitrack',
      blur_box: 'section-blur',
    };
    const targetId = sectionMap[type];
    if (targetId) {
      setTimeout(() => {
        const el = document.getElementById(targetId);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          const btn = el.querySelector('button');
          const hasContent = el.querySelector('.space-y-2');
          if (!hasContent && btn) btn.click();
        }
      }, 60);
    }
  }, []);

  // ── Interactive Main Video Drag & Move ──
  const startVideoMove = useCallback((e) => {
    e.stopPropagation();
    e.preventDefault();
    selectAndFocusLayer('video');
    const startX = e.clientX;
    const startY = e.clientY;
    const initialVx = editState?.video_x || 0;
    const initialVy = editState?.video_y || 0;

    const onMove = (moveEv) => {
      const dx = Math.round((moveEv.clientX - startX) * (1080 / 324));
      const dy = Math.round((moveEv.clientY - startY) * (1920 / 576));
      patchEdit({
        video_x: Math.max(-540, Math.min(540, initialVx + dx)),
        video_y: Math.max(-960, Math.min(960, initialVy + dy)),
      });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [editState, patchEdit, selectAndFocusLayer]);

  // ── Interactive Main Video Corner Scale ──
  const startVideoScale = useCallback((e, handle) => {
    e.stopPropagation();
    e.preventDefault();
    selectAndFocusLayer('video');
    const startX = e.clientX;
    const startY = e.clientY;
    const initialWScale = editState?.video_w_scale ?? 1.0;
    const initialHScale = editState?.video_h_scale ?? 1.0;

    const onMove = (moveEv) => {
      const hDir = (handle === 'tr' || handle === 'br') ? 1 : -1;
      const vDir = (handle === 'bl' || handle === 'br') ? 1 : -1;
      const delta = ((moveEv.clientX - startX) * hDir / 162 + (moveEv.clientY - startY) * vDir / 288) / 2;
      const newScale = Math.max(0.4, Math.min(2.5, parseFloat((initialWScale + delta).toFixed(3))));
      patchEdit({ video_w_scale: newScale, video_h_scale: newScale });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [editState, patchEdit, selectAndFocusLayer]);

  // ── Interactive 8-Handle Video Freeform Crop ──
  const startVideoCrop = useCallback((e, handle) => {
    e.stopPropagation();
    e.preventDefault();
    selectAndFocusLayer('video');
    setIsCroppingVideo(true);
    const startX = e.clientX;
    const startY = e.clientY;
    const vf = videoFrameRef.current || { fgW: 324, fgH: 182 };
    const curTop = editState?.crop_top ?? editState?.source_mask_top ?? 0.0;
    const curBot = editState?.crop_bottom ?? ((editState?.source_mask_mode === 'bottom' || editState?.source_mask_mode === 'both') ? (editState?.source_mask_bottom ?? 0.0) : 0.0);
    const curLeft = editState?.crop_left ?? 0.0;
    const curRight = editState?.crop_right ?? 0.0;

    const onMove = (moveEv) => {
      const dxNorm = (moveEv.clientX - startX) / (vf.fgW || 324);
      const dyNorm = (moveEv.clientY - startY) / (vf.fgH || 182);
      const updates = {};

      if (handle.includes('t')) {
        const maxT = Math.min(0.48, 1.0 - curBot - 0.04);
        updates.crop_top = parseFloat(Math.max(0.0, Math.min(maxT, curTop + dyNorm)).toFixed(4));
        updates.source_mask_top = updates.crop_top;
      }
      if (handle.includes('b')) {
        const maxB = Math.min(0.48, 1.0 - curTop - 0.04);
        updates.crop_bottom = parseFloat(Math.max(0.0, Math.min(maxB, curBot - dyNorm)).toFixed(4));
        updates.source_mask_bottom = updates.crop_bottom;
      }
      if (handle.includes('l')) {
        const maxL = Math.min(0.48, 1.0 - curRight - 0.04);
        updates.crop_left = parseFloat(Math.max(0.0, Math.min(maxL, curLeft + dxNorm)).toFixed(4));
      }
      if (handle.includes('r')) {
        const maxR = Math.min(0.48, 1.0 - curLeft - 0.04);
        updates.crop_right = parseFloat(Math.max(0.0, Math.min(maxR, curRight - dxNorm)).toFixed(4));
      }

      patchEdit(updates);
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [editState, patchEdit, selectAndFocusLayer]);



  // ── Interactive Subtitle 4-Corner Resize (Smooth Font Scaling) ──
  const startSubtitleCornerResize = useCallback((e, corner) => {
    e.stopPropagation();
    e.preventDefault();
    selectAndFocusLayer('subtitle');
    const startX = e.clientX;
    const startY = e.clientY;
    const startSize = editState?.sub_font_size || 36;
    const hDir = corner.includes('r') ? 1 : -1;
    const vDir = corner.includes('t') ? -1 : 1;

    let finalPatch = null;

    const onMove = (me) => {
      const dx = (me.clientX - startX) * hDir;
      const dy = (me.clientY - startY) * vDir;
      const delta = (dx + dy) * 0.4;
      const newSize = Math.max(18, Math.min(140, Math.round(startSize + delta)));
      finalPatch = { sub_font_size: newSize };
      setEditQueue(prev => prev.map((item, i) =>
        i === selEditIdx ? { ...item, state: { ...item.state, ...finalPatch } } : item
      ));
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      if (finalPatch) {
        patchEdit(finalPatch);
      }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [editState, patchEdit, selectAndFocusLayer, selEditIdx]);

  // ── Interactive Blur Box Move ──
  const startBlurBoxMove = useCallback((e, idx) => {
    e.stopPropagation();
    e.preventDefault();
    setSelBlurBoxIdx(idx);
    const startX = e.clientX;
    const startY = e.clientY;
    const box = editState?.blur_boxes?.[idx];
    if (!box) return;
    const initialX = box.x;
    const initialY = box.y;

    const onMove = (moveEv) => {
      if (box.video_rel) {
        // New format: video-local fractions (follow video on video_y change)
        const { fgW, fgH } = videoFrameRef.current;
        const newX = Math.max(0, Math.min(1 - (box.w || 0.1), initialX + (moveEv.clientX - startX) / fgW));
        const newY = Math.max(0, Math.min(1 - (box.h || 0.1), initialY + (moveEv.clientY - startY) / fgH));
        const updated = (editState?.blur_boxes || []).map((b, i) => i === idx ? { ...b, x: newX, y: newY } : b);
        patchEdit({ blur_boxes: updated });
      } else {
        // Legacy: output-frame pixels (1080×1920)
        const dxVideo = Math.round((moveEv.clientX - startX) * (1080 / 324));
        const dyVideo = Math.round((moveEv.clientY - startY) * (1920 / 576));
        const newX = Math.max(0, Math.min(1080 - box.w, initialX + dxVideo));
        const newY = Math.max(0, Math.min(1920 - box.h, initialY + dyVideo));
        const updated = (editState?.blur_boxes || []).map((b, i) => i === idx ? { ...b, x: newX, y: newY } : b);
        patchEdit({ blur_boxes: updated });
      }
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [editState, patchEdit]);

  const startBlurBoxResize = useCallback((e, idx, handle) => {
    e.stopPropagation();
    e.preventDefault();
    setSelBlurBoxIdx(idx);
    const startX = e.clientX;
    const startY = e.clientY;
    const box = editState?.blur_boxes?.[idx];
    if (!box) return;
    const initialX = box.x;
    const initialY = box.y;
    const initialW = box.w;
    const initialH = box.h;

    const onMove = (moveEv) => {
      let newX = initialX, newY = initialY, newW = initialW, newH = initialH;
      if (box.video_rel) {
        // New format: video-local fractions
        const { fgW, fgH } = videoFrameRef.current;
        const dxF = (moveEv.clientX - startX) / fgW;
        const dyF = (moveEv.clientY - startY) / fgH;
        const minSz = 0.015; // 1.5% of video dimension minimum
        if (handle.includes('r')) newW = Math.max(minSz, Math.min(1 - initialX, initialW + dxF));
        if (handle.includes('l')) { const pw = initialW - dxF; if (pw >= minSz) { newX = Math.max(0, initialX + dxF); newW = pw; } }
        if (handle.includes('b')) newH = Math.max(minSz, Math.min(1 - initialY, initialH + dyF));
        if (handle.includes('t')) { const ph = initialH - dyF; if (ph >= minSz) { newY = Math.max(0, initialY + dyF); newH = ph; } }
      } else {
        // Legacy: output-frame pixels
        const dxVideo = Math.round((moveEv.clientX - startX) * (1080 / 324));
        const dyVideo = Math.round((moveEv.clientY - startY) * (1920 / 576));
        if (handle.includes('r')) newW = Math.max(20, Math.min(1080 - initialX, initialW + dxVideo));
        if (handle.includes('l')) { const pw = initialW - dxVideo; if (pw >= 20) { newX = Math.max(0, initialX + dxVideo); newW = pw; } }
        if (handle.includes('b')) newH = Math.max(20, Math.min(1920 - initialY, initialH + dyVideo));
        if (handle.includes('t')) { const ph = initialH - dyVideo; if (ph >= 20) { newY = Math.max(0, initialY + dyVideo); newH = ph; } }
      }
      const updated = (editState?.blur_boxes || []).map((b, i) =>
        i === idx ? { ...b, x: newX, y: newY, w: newW, h: newH } : b
      );
      patchEdit({ blur_boxes: updated });
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [editState, patchEdit]);

  // ── Custom Audio Upload Handler ──
  const handleAudioUpload = async (e) => {
    const file = e.target?.files?.[0];
    if (!file || selEditIdx < 0) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`${API}/audio/upload`, { method: 'POST', body: formData });
      if (!res.ok) throw new Error('Upload audio failed');
      const data = await res.json();
      patchEdit({
        custom_audio_path: data.path,
        custom_audio_name: data.name,
        custom_audio_url: data.url,
        custom_audio_dur: data.duration,
        custom_audio_offset: 0,
        custom_audio_trim_start: 0,
        custom_audio_trim_dur: data.duration,
        orig_volume: 0,
        custom_volume: 100,
      });
    } catch (err) {
      alert(`Lỗi upload audio: ${err.message}`);
    } finally {
      if (e.target) e.target.value = '';
    }
  };

  // ── Multitrack Overlay Handlers ──
const handleOverlayUpload = async (e) => {
    const file = e.target?.files?.[0];
    if (!file || selEditIdx < 0) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`${API}/overlay/upload`, { method: 'POST', body: formData });
      if (!res.ok) throw new Error('Upload failed');
      const data = await res.json();
      const newOverlay = {
        id: data.id,
        name: data.name,
        path: data.path,
        url: data.url,
        type: data.type,
        x: Math.max(0, 540 - Math.round(Math.min(400, data.w || 300) / 2)),
        y: Math.max(0, 960 - Math.round(Math.min(400, data.h || 300) / 2)),
        w: Math.min(600, data.w || 300),
        h: Math.min(600, data.h || 300),
        opacity: 100,
        rotation: 0,
        start_time: 0,
        end_time: 0,
        remove_bg: false,
        remove_bg_path: '',
        remove_bg_url: '',
        enabled: true,
      };
      const curOverlays = editState?.overlays || [];
      patchEdit({ overlays: [...curOverlays, newOverlay] });
      setSelOverlayIdx(curOverlays.length);
    } catch (err) {
      alert(`Lỗi upload layer: ${err.message}`);
    } finally {
      if (e.target) e.target.value = '';
    }
  };

  const handleRemoveBg = async (idx) => {
    const ovl = editState?.overlays?.[idx];
    if (!ovl) return;
    setIsRemovingBg(true);
    try {
      const res = await post('/overlay/remove_bg', { path: ovl.path, type: ovl.type });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Lỗi tách nền');
      }
      const data = await res.json();
      const updated = (editState?.overlays || []).map((o, i) =>
        i === idx ? { ...o, remove_bg: true, remove_bg_path: data.remove_bg_path, remove_bg_url: data.remove_bg_url } : o
      );
      patchEdit({ overlays: updated });
    } catch (err) {
      alert(`Lỗi tách nền BiRefNet: ${err.message}`);
    } finally {
      setIsRemovingBg(false);
    }
  };

  const startOverlayMove = useCallback((e, idx) => {
    e.stopPropagation();
    e.preventDefault();
    setSelOverlayIdx(idx);
    setSelBlurBoxIdx(-1);
    const startX = e.clientX;
    const startY = e.clientY;
    const ovl = editState?.overlays?.[idx];
    if (!ovl) return;
    const initialX = ovl.x;
    const initialY = ovl.y;

    let finalUpdated = null;

    const onMove = (moveEv) => {
      const dxVideo = Math.round((moveEv.clientX - startX) * (1080 / 324));
      const dyVideo = Math.round((moveEv.clientY - startY) * (1920 / 576));
      const MARGIN = 1080;
      const newX = Math.max(-MARGIN, Math.min(1080 + MARGIN - ovl.w, initialX + dxVideo));
      const newY = Math.max(-1920, Math.min(1920 + 1920 - ovl.h, initialY + dyVideo));
      const updated = (editState?.overlays || []).map((o, i) =>
        i === idx ? { ...o, x: newX, y: newY } : o
      );
      finalUpdated = updated;
      setEditQueue(prev => prev.map((item, i) =>
        i === selEditIdx ? { ...item, state: { ...item.state, overlays: updated } } : item
      ));
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      if (finalUpdated) {
        patchEdit({ overlays: finalUpdated });
      }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [editState, patchEdit, selEditIdx]);

  const startOverlayResize = useCallback((e, idx, handle) => {
    e.stopPropagation();
    e.preventDefault();
    setSelOverlayIdx(idx);
    const startX = e.clientX;
    const startY = e.clientY;
    const ovl = editState?.overlays?.[idx];
    if (!ovl) return;
    const initialX = ovl.x;
    const initialY = ovl.y;
    const initialW = ovl.w;
    const initialH = ovl.h;

    let finalUpdated = null;

    const onMove = (moveEv) => {
      const dxVideo = Math.round((moveEv.clientX - startX) * (1080 / 324));
      const dyVideo = Math.round((moveEv.clientY - startY) * (1920 / 576));
      let newX = initialX;
      let newY = initialY;
      let newW = initialW;
      let newH = initialH;

      if (handle.includes('r')) {
        newW = Math.max(30, initialW + dxVideo);
      }
      if (handle.includes('l')) {
        const possibleW = initialW - dxVideo;
        if (possibleW >= 30) {
          newX = initialX + dxVideo;
          newW = possibleW;
        }
      }
      if (handle.includes('b')) {
        newH = Math.max(30, initialH + dyVideo);
      }
      if (handle.includes('t')) {
        const possibleH = initialH - dyVideo;
        if (possibleH >= 30) {
          newY = initialY + dyVideo;
          newH = possibleH;
        }
      }

      const updated = (editState?.overlays || []).map((o, i) =>
        i === idx ? { ...o, x: newX, y: newY, w: newW, h: newH } : o
      );
      finalUpdated = updated;
      setEditQueue(prev => prev.map((item, i) =>
        i === selEditIdx ? { ...item, state: { ...item.state, overlays: updated } } : item
      ));
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      if (finalUpdated) {
        patchEdit({ overlays: finalUpdated });
      }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [editState, patchEdit, selEditIdx]);

  const startOverlayRotate = useCallback((e, idx) => {
    e.stopPropagation();
    e.preventDefault();
    setSelOverlayIdx(idx);
    const startX = e.clientX;
    const ovl = editState?.overlays?.[idx];
    if (!ovl) return;
    const startRot = ovl.rotation || 0;

    let finalUpdated = null;

    const onRotateMove = (re) => {
      const deltaX = re.clientX - startX;
      const newRot = Math.max(-180, Math.min(180, Math.round(startRot + deltaX * 0.5)));
      const updated = (editState?.overlays || []).map((o, i) =>
        i === idx ? { ...o, rotation: newRot } : o
      );
      finalUpdated = updated;
      setEditQueue(prev => prev.map((item, i) =>
        i === selEditIdx ? { ...item, state: { ...item.state, overlays: updated } } : item
      ));
    };

    const onRotateUp = () => {
      window.removeEventListener('pointermove', onRotateMove);
      window.removeEventListener('pointerup', onRotateUp);
      if (finalUpdated) {
        patchEdit({ overlays: finalUpdated });
      }
    };
    window.addEventListener('pointermove', onRotateMove);
    window.addEventListener('pointerup', onRotateUp);
  }, [editState, patchEdit, selEditIdx]);

  // ── Bootstrap ──
useEffect(() => {
    (async () => {
      try {
        const [cfgR, fontsR, encR] = await Promise.all([
          fetch(`${API}/config`).then(r => r.json()),
          fetch(`${API}/fonts`).then(r => r.json()),
          fetch(`${API}/encoders`).then(r => r.json()),
        ]);
        // ── Load title prompts presets list ──
        try {
          const prR = await fetch(`${API}/title_prompts`).then(r => r.json());
          setSavedPresets(prR.presets || []);
        } catch {}
        // F2: Load edit style presets
        try {
          const epR = await fetch(`${API}/edit_presets`).then(r => r.json());
          setEditPresets(epR.presets || []);
        } catch {}
        // Load OCR hardware engine status
        try {
          const ocrR = await fetch(`${API}/ocr_status`).then(r => r.json());
          if (ocrR && ocrR.device) setOcrInfo(ocrR);
        } catch {}
        setConfig(p => ({ ...p, ...cfgR }));
        setFonts(fontsR.fonts || []);
        setEncoders(encR.encoders || ['libx264']);
  // ── Auto-apply GPU encoder if server detected one and user ──
  // hasn't manually chosen
        if (encR.best && encR.best !== 'libx264' && (!cfgR.export_encoder || cfgR.export_encoder === 'libx264')) {
          setConfig(p => ({ ...p, export_encoder: encR.best }));
        }
      } catch {}

  // ── Re-fetch encoders after 5s ──
  // GPU probe runs async at startup (~2s),
  // ── so the first fetch always returns libx264 before probe ──
// completes.
      setTimeout(async () => {
        try {
          const encR = await fetch(`${API}/encoders`).then(r => r.json());
          const newEncoders = encR.encoders || ['libx264'];
          setEncoders(newEncoders);
  // ── Auto-upgrade to GPU encoder if probe found one ──
setConfig(prev => {
            if (encR.best && encR.best !== 'libx264' &&
                (!prev.export_encoder || prev.export_encoder === 'libx264')) {
              return { ...prev, export_encoder: encR.best };
            }
            return prev;
          });
        } catch {}
      }, 5000);
  // ── Load title prompts presets list ──
try {
        const prR = await fetch(`${API}/title_prompts`).then(r => r.json());
        setSavedPresets(prR.presets || []);
      } catch {}
    })();
  }, []);

  const loadPromptPreset = async (name) => {
    try {
      const r = await fetch(`${API}/title_prompts/${encodeURIComponent(name)}`).then(r => r.json());
      setTitlePrompt(r.content || '');
    } catch {}
  };

  const savePromptPreset = async () => {
    const n = savePresetName.trim();
    if (!n || !titlePrompt.trim()) { alert('Nhập tên preset và nội dung prompt.'); return; }
    await post('/title_prompts/save', { name: n, content: titlePrompt });
    const prR = await fetch(`${API}/title_prompts`).then(r => r.json());
    setSavedPresets(prR.presets || []);
    setSavePresetName('');
  };

  const deletePromptPreset = async (name) => {
    await fetch(`${API}/title_prompts/${encodeURIComponent(name)}`, { method: 'DELETE' });
    const prR = await fetch(`${API}/title_prompts`).then(r => r.json());
    setSavedPresets(prR.presets || []);
  };

  // ── F2: Edit style presets ────────────────────────────────────────────────
  const refreshEditPresets = async () => {
    try { const r = await fetch(`${API}/edit_presets`).then(r => r.json()); setEditPresets(r.presets || []); } catch {}
  };
  const saveEditPreset = async () => {
    const n = editPresetName.trim();
    if (!n) { alert('Nhập tên preset'); return; }
    await post('/edit_presets/save', { name: n, state: editState });
    setEditPresetName('');
    refreshEditPresets();
  };
  const loadEditPreset = async (name) => {
    if (selEditIdx < 0) { alert('Chọn một clip trước'); return; }
    try {
      const r = await fetch(`${API}/edit_presets/${encodeURIComponent(name)}`).then(r => r.json());
      if (r.state) patchEdit(r.state);
    } catch {}
  };
  const delEditPreset = async (name) => {
    await fetch(`${API}/edit_presets/${encodeURIComponent(name)}`, { method: 'DELETE' });
    refreshEditPresets();
  };

  // ── F4: Undo ─────────────────────────────────────────────────────────────
  const pushUndo = useCallback((entry) => {
    undoStack.current = [...undoStack.current.slice(-49), entry];
  }, []);
  const applyUndo = useCallback(() => {
    if (!undoStack.current.length) return;
    const entry = undoStack.current.pop();
    if (entry.type === 'removeEditClip') {
      setEditQueue(prev => { const n = [...prev]; n.splice(entry.idx, 0, entry.item); return n; });
      setSelEditIdx(entry.idx);
    } else if (entry.type === 'setTitle') {
      setEditQueue(prev => prev.map((it, i) => i === entry.idx ? { ...it, title: entry.prevTitle } : it));
    }
  }, []);

  const applyTitlePrompt = async () => {
    await post('/config', { title_prompt: titlePrompt || null });
    setConfig(p => ({ ...p, title_prompt: titlePrompt || null }));
  };

  const regenTitle = async (idx) => {
    const clip = editQueue[idx];
    if (!clip) return;
    setRegenningIdx(idx);
    try {
      const res = await post('/edit_queue/regen_title', {
        clip_path:        clip.clip_path || clip.path || '',
        current_title:    clip.title || '',
        description:      clip.description || '',
        highlight_reason: clip.highlight_reason || '',
        custom_prompt:    titlePrompt || config.title_prompt || null,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Lỗi tạo tiêu đề AI');
      }
      if (data.title) {
        setEditQueue(prev => prev.map((item, i) => i === idx ? {
          ...item,
          title: data.title,
          title_error: false,
          title_error_msg: '',
          suggested_titles: data.suggested_titles || (item.suggested_titles ? [data.title, ...item.suggested_titles.filter(t => t !== data.title)] : [data.title]),
        } : item));
      }
    } catch (err) {
      const msg = err?.message || err;
      alert(`Tạo lại tiêu đề thất bại: ${msg}`);
      setEditQueue(prev => prev.map((item, i) => i === idx ? {
        ...item,
        title_error: true,
        title_error_msg: String(msg),
      } : item));
    } finally {
      setRegenningIdx(-1);
    }
  };

  const retryAllFailedTitles = async () => {
    try {
      const res = await post('/edit_queue/retry_all_failed_titles', {});
      const data = await res.json();
      if (data.count > 0) {
        alert(`🔄 Đang thử lại tạo tiêu đề AI cho ${data.count} clip lỗi (xoay key tự động)...`);
      } else {
        alert('Không có clip nào bị lỗi tiêu đề.');
      }
    } catch (err) {
      alert(`Lỗi: ${err?.message || err}`);
    }
  };

  const DEFAULT_PROMPT_HINT = `You generate short, viral, emotionally-charged YouTube Shorts / TikTok titles for bodycam footage.

Clip context:
- Description: {description}
- Highlight reason: {highlight_reason}
- Previous title: {old_title}

Rules:
1. ALL CAPS, 3-8 words max.
2. No hashtags, no emoji, no quotes.
3. Must be emotionally gripping — shock, urgency, outrage, or triumph.
4. Output ONLY the title, nothing else.`;

  // ── State fetch helpers (called on-demand by SSE events or fallback poll) ──
  const fetchVideos = React.useCallback(async () => {
    try {
      const vR = await fetch(`${API}/videos`).then(r => r.json());
      const vids = vR.videos || [];
      setVideos(vids);
      setIsAnalyzing(Boolean(vR.is_analyzing) || vids.some(v => v.status === 'uploading' || v.status === 'analyzing'));
      if (selVideo) {
        const upd = vids.find(v => v.path === selVideo.path);
        if (upd && (upd.status !== selVideo.status ||
          (upd.candidates?.length ?? 0) !== (selVideo.candidates?.length ?? 0) ||
          upd.error !== selVideo.error)) setSelVideo(upd);
      }
    } catch {}
  }, [selVideo]);

  const fetchQueue = React.useCallback(async () => {
    try {
      const eqR = await fetch(`${API}/edit_queue`).then(r => r.json());
      const serverClips = eqR.clips || [];
      setEditQueue(prev => {
        if (!editQueueInited.current) { editQueueInited.current = true; return serverClips; }
        const prevPaths   = new Set(prev.map(c => c.clip_path || c.path));
        const serverPaths = new Set(serverClips.map(c => c.clip_path || c.path));
        const added = serverClips.filter(c => !prevPaths.has(c.clip_path || c.path));
        const kept  = prev.filter(c => serverPaths.has(c.clip_path || c.path));
        return added.length || kept.length !== prev.length ? [...kept, ...added] : prev;
      });
    } catch {}
  }, []);

  const fetchBatches = React.useCallback(async () => {
    try {
      const res = await fetch(`${API}/batches`).then(r => r.json());
      if (res && res.batches) {
        setBatches(res.batches);
        setActiveBatchId(res.active_batch_id || 'default');
      }
    } catch {}
  }, []);

  const switchBatch = async (id) => {
    try {
      const r = await post('/batches/switch', { batch_id: id });
      const res = await r.json();
      if (res.status === 'ok') {
        setActiveBatchId(res.active_batch_id);
        setEditQueue(res.clips || []);
        setSelEditIdx(-1);
        setSelEditIdxs(new Set());
        fetchBatches();
      }
    } catch (e) {
      alert(`Lỗi chuyển cụm: ${e}`);
    }
  };

  const createNewBatch = async () => {
    const name = prompt('Nhập tên cụm mới:', `Cụm ${batches.length + 1}`);
    if (!name || !name.trim()) return;
    try {
      const r = await post('/batches/create', { name: name.trim() });
      const res = await r.json();
      if (res.status === 'ok') {
        await switchBatch(res.batch_id);
      }
    } catch (e) {
      alert(`Lỗi tạo cụm: ${e}`);
    }
  };

  const deleteBatch = async (id, e) => {
    e?.stopPropagation();
    if (!confirm('Bạn có chắc muốn xóa cụm này không? Toàn bộ clip trong cụm này sẽ bị xóa khỏi hàng đợi.')) return;
    try {
      const r = await post('/batches/delete', { batch_id: id });
      const res = await r.json();
      if (res.status === 'ok') {
        setActiveBatchId(res.active_batch_id);
        setEditQueue(res.clips || []);
        setSelEditIdx(-1);
        setSelEditIdxs(new Set());
        fetchBatches();
      } else {
        alert(res.detail || 'Không thể xóa cụm');
      }
    } catch (err) {
      alert(`Không thể xóa cụm: ${err}`);
    }
  };

  const saveBatchName = async () => {
    if (!batchNameInput.trim()) return;
    try {
      await post('/batches/rename', { batch_id: activeBatchId, name: batchNameInput.trim() });
      setIsEditingBatchName(false);
      fetchBatches();
    } catch (e) {
      alert(`Lỗi đổi tên cụm: ${e}`);
    }
  };

  const pickBatchOutputFolder = async (batchId) => {
    try {
      const r = await post('/dialog/pick_folder', { batch_id: batchId });
      const res = await r.json();
      const folder = res?.folder || res?.path;
      if (folder) {
        await post('/batches/update_folder', { batch_id: batchId, output_folder: folder });
        await fetchBatches();
      }
    } catch (e) {
      alert(`Lỗi chọn thư mục: ${e}`);
    }
  };

  const fetchExport = React.useCallback(async () => {
    try { setExportProg(await fetch(`${API}/export/status`).then(r => r.json())); } catch {}
  }, []);

  // ── SSE connection — replaces interval polling ──────────────────────────────
  // Receives push events from server; falls back to a slow 30s safety poll.
  // During active analysis also runs a 3s poll for video status (frequent transitions).
  useEffect(() => {
    // Initial load
    Promise.all([fetchVideos(), fetchQueue(), fetchBatches(), fetchExport(),
      fetch(`${API}/logs?n=150`).then(r => r.json()).then(d => setLogs(d.logs || [])).catch(() => {})
    ]);

    const es = new EventSource(`${API}/events`);

    es.onmessage = async (e) => {
      try {
        const evt = JSON.parse(e.data);
        switch (evt.type) {
          case 'log':
            setLogs(prev => {
              const entry = { text: evt.data.text, level: evt.data.level, timestamp: evt.data.ts };
              const next  = [...prev, entry];
              return next.length > 500 ? next.slice(-500) : next;
            });
            break;
          case 'videos_changed':
            await fetchVideos();
            break;
          case 'queue_changed':
            await fetchQueue();
            await fetchBatches();
            break;
          case 'batches_changed':
            await fetchBatches();
            await fetchQueue();
            break;
          case 'export_changed':
            await fetchExport();
            break;
          // heartbeat / connected — no action needed
        }
      } catch {}
    };

    es.onerror = () => {
      // SSE disconnected — browser auto-reconnects; fetchVideos on reconnect covers any gap
    };

    // 30s safety fallback poll — catches any events missed during SSE gaps/reconnects
    const fallbackIv = setInterval(() => {
      Promise.all([fetchVideos(), fetchQueue(), fetchBatches(), fetchExport()]);
    }, 30_000);

    return () => { es.close(); clearInterval(fallbackIv); };
  }, []);   // run once; fetchVideos/Queue/Export are stable useCallbacks

  // Fast 3s poll ONLY while analysis is active (frequent status transitions not in SSE)
  useEffect(() => {
    if (!isAnalyzing) return;
    const iv = setInterval(fetchVideos, 3000);
    return () => clearInterval(iv);
  }, [isAnalyzing, fetchVideos]);



  // ── auto-scroll log ──
useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [logs]);

  // ???? Preview: Ultra-fast OpenCV background rendering ??????????????????????????????????
  // ── Fetch as binary ──
  // Preview: OpenCV background rendering — skip while playing (canvas is live, preview is hidden behind it)
  useEffect(() => {
    if (tab !== 'edit' || !currentEditItem || isPlaying) return;
    if (prevTimer.current) clearTimeout(prevTimer.current);
    prevTimer.current = setTimeout(async () => {
      try {
        const r = await fetch(`${API}/preview`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'image/jpeg' },
          body: JSON.stringify({
            clip_path: currentEditItem.clip_path || currentEditItem.path || '',
            title: '',
            no_title: true,
            width: 324, height: 576,
            state: currentEditItem.state,
          }),
        });
        if (!r.ok) { setPreviewErr('Preview Error'); return; }
        const blob = await r.blob();
        const objectUrl = URL.createObjectURL(blob);
        const img = new window.Image();
        img.onload = () => {
          setPreviewUrl(prev => {
            if (prev) URL.revokeObjectURL(prev); // ── FREES GPU TEXTURE MEMORY IN CHROMIUM IMMEDIATELY ────────────────────────────────────────────────────────
return objectUrl;
          });
          setPreviewErr('');
        };
        img.src = objectUrl;
      } catch (e) { setPreviewErr(String(e)); }
    }, 60);
    return () => { if (prevTimer.current) clearTimeout(prevTimer.current); };
  }, [tab, currentEditItem, isPlaying]);

  // ── Window-level pointer drag (text move + draw blur box) ──
  // IMPORTANT: drawStartRef (not state) is used so the closure never goes stale.
  // This avoids remove+readd of window listeners on every mouse move (which caused rubber band to lag).
  useEffect(() => {
    const onMove = (e) => {
      // ── Draw blur box rubber band ──
      if (drawMode && drawStartRef.current && canvasRef.current) {
        const rect = canvasRef.current.getBoundingClientRect();
        const normX = Math.max(0, Math.min(1, (e.clientX - rect.left) / (rect.width || 1)));
        const normY = Math.max(0, Math.min(1, (e.clientY - rect.top) / (rect.height || 1)));
        setDrawCurrent({ x: normX * 324, y: normY * 576 });
        return;
      }
      // ── Text-box drag (delta-based so box doesn't jump to cursor) ──
      if (dragActive.current && dragRect.current) {
        const scaleY = 1920 / dragRect.current.height;
        const scaleX = 1080 / dragRect.current.width;
        const deltaX = (e.clientX - dragStartPos.current.x) * scaleX;
        const deltaY = (e.clientY - dragStartPos.current.y) * scaleY;
        const newY = Math.round(Math.max(0, Math.min(1900, dragStartText.current.y + deltaY)));
        const newX = Math.round(Math.max(-500, Math.min(500, dragStartText.current.x + deltaX)));
        dragFinalText.current = { text_y: newY, text_x: newX };
        setEditQueue(prev => prev.map((item, i) =>
          i === selEditIdx ? { ...item, state: { ...item.state, text_y: newY, text_x: newX } } : item
        ));
      }

      // ── Subtitle drag (delta-based, 100% unified with Title drag engine) ──
      if (subDragActive.current && dragRect.current) {
        const scaleY = 1920 / dragRect.current.height;
        const scaleX = 1080 / dragRect.current.width;
        const deltaX = (e.clientX - dragStartPos.current.x) * scaleX;
        const deltaY = (e.clientY - dragStartPos.current.y) * scaleY;
        const newMargin = Math.round(Math.max(20, Math.min(1800, dragStartSub.current.margin_v - deltaY)));
        const newX = Math.round(Math.max(-500, Math.min(500, dragStartSub.current.x + deltaX)));
        dragFinalSub.current = { sub_margin_v: newMargin, sub_x: newX };
        setEditQueue(prev => prev.map((item, i) =>
          i === selEditIdx ? { ...item, state: { ...item.state, sub_margin_v: newMargin, sub_x: newX } } : item
        ));
      }
    };

    const onUp = (e) => {
      const start = drawStartRef.current;
      if (drawMode && start) {
        // Clear refs and state immediately so UI updates
        drawStartRef.current = null;
        setDrawStart(null);
        setDrawCurrent(null);
        if (canvasRef.current) {
          const rect = canvasRef.current.getBoundingClientRect();
          const normX = Math.max(0, Math.min(1, (e.clientX - rect.left) / (rect.width || 1)));
          const normY = Math.max(0, Math.min(1, (e.clientY - rect.top) / (rect.height || 1)));
          const endX = normX * 324;
          const endY = normY * 576;

          const minX = Math.min(start.x, endX);
          const minY = Math.min(start.y, endY);
          const w = Math.abs(endX - start.x);
          const h = Math.abs(endY - start.y);
          if (w > 8 && h > 8) {
            // F1 v2: store as VIDEO-LOCAL fractions so box follows video when video_y changes
            const { fgX: fx, fgY: fy, fgW: fw, fgH: fh, vw: srcW, vh: srcH } = videoFrameRef.current;
            const clMinX = Math.max(fx, minX), clMinY = Math.max(fy, minY);
            const clMaxX = Math.min(fx + fw, minX + w), clMaxY = Math.min(fy + fh, minY + h);
            const clW = clMaxX - clMinX, clH = clMaxY - clMinY;
            if (clW > 4 && clH > 4) {
              const currentBoxes = editState?.blur_boxes || [];
              patchEdit({
                blur_boxes: [...currentBoxes, {
                  x: (clMinX - fx) / fw, y: (clMinY - fy) / fh,
                  w: clW / fw,           h: clH / fh,
                  id: Date.now(), mode: boxMode,
                  video_rel: true, _vw: srcW, _vh: srcH
                }]
              });
            }
          }
        }
        return;
      }
      if (dragActive.current && dragFinalText.current) {
        patchEdit(dragFinalText.current);
        dragFinalText.current = null;
      }
      dragActive.current = false;

      if (subDragActive.current && dragFinalSub.current) {
        patchEdit(dragFinalSub.current);
        dragFinalSub.current = null;
      }
      subDragActive.current = false;
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup',   onUp);
    return () => { window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', onUp); };
    // drawStart and drawCurrent intentionally EXCLUDED from deps — we use drawStartRef so the
    // listener is NOT removed+re-added on every mouse move (which caused the rubber band lag).
  }, [drawMode, editState, patchEdit]);

  const handleCanvasPointerDown = (e) => {
    if (!canvasRef.current) return;
    if (drawMode) {
      const rect = canvasRef.current.getBoundingClientRect();
      const normX = Math.max(0, Math.min(1, (e.clientX - rect.left) / (rect.width || 1)));
      const normY = Math.max(0, Math.min(1, (e.clientY - rect.top) / (rect.height || 1)));
      const pt = { x: normX * 324, y: normY * 576 };
      drawStartRef.current = pt;  // update ref immediately — closure in useEffect reads this
      setDrawStart(pt);
      setDrawCurrent(pt);
      e.preventDefault();
      return;
    }

    // Hit-test click inside visible foreground video frame
    const rect = canvasRef.current.getBoundingClientRect();
    const clickX = ((e.clientX - rect.left) / (rect.width || 1)) * 324;
    const clickY = ((e.clientY - rect.top) / (rect.height || 1)) * 576;
    const vf = videoFrameRef.current;

    if (vf) {
      const cL = editState?.crop_left ?? 0;
      const cR = editState?.crop_right ?? 0;
      const cT = editState?.crop_top ?? editState?.source_mask_top ?? 0;
      const cB = editState?.crop_bottom ?? ((editState?.source_mask_mode === 'bottom' || editState?.source_mask_mode === 'both') ? (editState?.source_mask_bottom ?? 0) : 0);

      const vx = vf.fgX + cL * vf.fgW;
      const vy = vf.fgY + cT * vf.fgH;
      const vw = Math.max(10, vf.fgW * (1 - cL - cR));
      const vh = Math.max(10, vf.fgH * (1 - cT - cB));

      if (clickX >= vx && clickX <= vx + vw && clickY >= vy && clickY <= vy + vh) {
        startVideoMove(e);
        return;
      }
    }

    // Clicked on blank canvas backdrop: clear active selection
    setSelectedLayer({ type: null, id: null });
    setIsCroppingVideo(false);
    setSelOverlayIdx(-1);
    setSelBlurBoxIdx(-1);
  };

  // ── Keyboard listener for Spacebar ──
  // play/pause in Tab 2 Edit
  useEffect(() => {
    const onKey = (e) => {
      if (tab === 'edit' && e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        setIsPlaying(p => !p);
        e.preventDefault();
      }
      // F4: Ctrl+Z undo
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        e.preventDefault();
        applyUndo();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [tab, applyUndo]);

  // ── Keep a ref to editState so the RAF draw loop and paintFrame always see the latest values ──
  const editStateRef = useRef(editState);

  // ── Standalone Canvas Paint Function (CapCut-style compositor) ──
  // Paints background (blur/image/video) + transformed foreground video (scale, aspect-ratio, mask, flip, color grade)
  const paintFrame = useCallback(() => {
    const v   = videoRef.current;
    const cvs = videoCanvasRef.current;
    if (!v || !cvs) return;

    const ctx = cvs.getContext('2d');
    const { videoWidth: vw, videoHeight: vh } = v;
    ctx.clearRect(0, 0, cvs.width, cvs.height);

    if (vw && vh) {
      const CW = cvs.width;
      const CH = cvs.height;
      const st = editStateRef.current;

      const effectiveVideoDur = (st?.video_trim_dur > 0 && st.video_trim_dur < (v.duration || duration || 9999))
        ? st.video_trim_dur
        : (v.duration || duration || 9999);

      // If current playback time is past trimmed video length, show black screen (matches FFmpeg tpad)
      if (currentTime > effectiveVideoDur + 0.05) {
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, CW, CH);
        return;
      }

      // 1. Background layer: blur (default) | custom image | custom video
      const rawBgType = st?.bg_type || 'blur';
      const isImgVid = rawBgType === 'image' && st?.bg_image_path && /\.(mp4|mov|webm|mkv|avi|ts|m4v)$/i.test(st.bg_image_path);
      const bgType = isImgVid ? 'video' : rawBgType;
      const bgSrc  = bgType === 'image' ? bgImageRef.current
                   : bgType === 'video' ? bgVideoRef.current
                   : null;
      const bgEl   = (bgSrc && (bgSrc.complete !== false) && (bgSrc.naturalWidth > 0 || bgSrc.videoWidth > 0)) ? bgSrc : null;
      const drawEl = bgEl || v; // fallback to video if custom bg not ready
      const { naturalWidth: bgNW, naturalHeight: bgNH, videoWidth: bgVW, videoHeight: bgVH } = drawEl;
      const bgW0   = bgNW || bgVW || vw;
      const bgH0   = bgNH || bgVH || vh;

      const cropTop  = st?.crop_top ?? st?.source_mask_top ?? 0.0;
      const cropBottom = st?.crop_bottom ?? ((st?.source_mask_mode === 'bottom' || st?.source_mask_mode === 'both')
                       ? (st?.source_mask_bottom ?? 0.0) : 0.0);
      const cropLeft   = st?.crop_left ?? 0.0;
      const cropRight  = st?.crop_right ?? 0.0;

      ctx.save();
      if (!bgEl || bgType === 'blur') {
        // Default: blurred video fill (matches FFmpeg export crop shift when cropTop > 0)
        const srcSY = cropTop > 0 ? vh * cropTop : 0;
        const srcSH = Math.max(1, vh * (1 - cropTop - cropBottom));
        const srcSX = cropLeft > 0 ? vw * cropLeft : 0;
        const srcSW = Math.max(1, vw * (1 - cropLeft - cropRight));

        const coverScale = Math.max(CW / srcSW, CH / srcSH);
        const bgW = srcSW * coverScale * 1.05;
        const bgH = srcSH * coverScale * 1.05;
        const bgX = (CW - bgW) / 2;
        const bgY = (CH - bgH) / 2;

        ctx.filter = 'blur(22px) brightness(0.6) saturate(1.2)';
        ctx.drawImage(v, srcSX, srcSY, srcSW, srcSH, bgX, bgY, bgW, bgH);
        ctx.filter = 'none';
      } else if (bgCacheRef.current && bgType === 'image') {
        // Fast path: draw from pre-scaled offscreen cache (pixel copy)
        ctx.drawImage(bgCacheRef.current, 0, 0, CW, CH);
      } else {
        // Fallback: draw directly from element (custom video or raw image)
        const coverScale = Math.max(CW / bgW0, CH / bgH0);
        const bgW = bgW0 * coverScale * 1.05;
        const bgH = bgH0 * coverScale * 1.05;
        const bgX = (CW - bgW) / 2;
        const bgY = (CH - bgH) / 2;
        ctx.drawImage(drawEl, bgX, bgY, bgW, bgH);
      }
      ctx.restore();

      // 2. Foreground: video with edit transforms (contain scale, offset, masks, flips, color grade)
      const wScale   = st?.video_w_scale ?? 1.0;
      const hScale   = st?.video_h_scale ?? 1.0;
      const videoX   = st?.video_x       ?? 0;
      const videoY   = st?.video_y       ?? 0;
      const flipH    = st?.flip_h ?? false;
      const flipV    = st?.flip_v ?? false;
      const colorGrade = st?.color_grade ?? false;
      const sat      = st?.saturation ?? 1.0;
      const hueShift = st?.hue_shift ?? 0;
      const microRotate = st?.micro_rotate ?? false;
      const smartZoom = st?.smart_zoom ?? false;
      const vignette = st?.vignette ?? false;
      const vignetteStrength = st?.vignette_strength ?? 50;

      const containScale = Math.min(CW / vw, CH / vh);
      const fgW = vw * containScale * wScale;
      const fgH = vh * containScale * hScale;

      const xOffset = (videoX / 1080) * CW;
      const yOffset = (videoY / 1920) * CH;
      const fgX = (CW - fgW) / 2 + xOffset;
      const fgY = (CH - fgH) / 2 + yOffset;
      // F1: persist video bounds so HTML handles + blur-box coords can be mapped
      videoFrameRef.current = { fgX, fgY, fgW, fgH, vw, vh, cropTop, cropBottom, cropLeft, cropRight };

      // Crop foreground video using 4-edge crop margins relative to foreground video bounds (fgH, fgY)
      const cropTopPx   = cropTop * fgH;
      const cropBotPx   = cropBottom * fgH;
      const cropLeftPx  = cropLeft * fgW;
      const cropRightPx = cropRight * fgW;
      const fgVisibleLeft = fgX + cropLeftPx;
      const fgVisibleTop  = fgY + cropTopPx;
      const fgVisibleW    = Math.max(0, fgW - cropLeftPx - cropRightPx);
      const fgVisibleH    = Math.max(0, fgH - cropTopPx - cropBotPx);

      ctx.save();
      ctx.beginPath();
      ctx.rect(fgVisibleLeft, fgVisibleTop, fgVisibleW, fgVisibleH);
      ctx.clip();

      // Color filters (Color Grade / Saturation / Hue Shift)
      const filters = [];
      if (colorGrade) {
        filters.push('contrast(1.1) brightness(1.05) saturate(1.18)');
      }
      if (Math.abs(sat - 1.0) > 0.01) {
        filters.push(`saturate(${sat})`);
      }
      if (hueShift !== 0) {
        filters.push(`hue-rotate(${hueShift}deg)`);
      }
      if (filters.length > 0) {
        ctx.filter = filters.join(' ');
      }

      // Center for transforms (flip, micro-rotate)
      const cx = fgX + fgW / 2;
      const cy = fgY + fgH / 2;

      // Apply flip & micro-rotate transforms around the foreground video center
      if (flipH || flipV || microRotate) {
        ctx.translate(cx, cy);
        if (flipH || flipV) {
          ctx.scale(flipH ? -1 : 1, flipV ? -1 : 1);
        }
        if (microRotate) {
          // Micro-rotate 1.2 degrees (matches FFmpeg rotate=1.2*PI/180)
          ctx.rotate((1.2 * Math.PI) / 180);
        }
        ctx.translate(-cx, -cy);
      }

      // Smart Zoom: 2% crop before scale (matches FFmpeg crop=0.98*iw:0.98*ih)
      if (smartZoom) {
        const zx = vw * 0.01;
        const zy = vh * 0.01;
        ctx.drawImage(v, zx, zy, vw - 2 * zx, vh - 2 * zy, fgX, fgY, fgW, fgH);
      } else {
        ctx.drawImage(v, fgX, fgY, fgW, fgH);
      }

      // Vignette 3D: Soft Gaussian/radial darkening around corners of foreground video
      if (vignette) {
        ctx.filter = 'none';
        const vs = Math.max(5, Math.min(100, Number(vignetteStrength)));
        const maxR = Math.sqrt((fgW / 2) ** 2 + (fgH / 2) ** 2);
        const innerR = Math.max(0, maxR * (0.45 - (vs / 100) * 0.25));
        const grad = ctx.createRadialGradient(cx, cy, innerR, cx, cy, maxR);
        const edgeAlpha = Math.min(0.95, 0.25 + (vs / 100) * 0.65);
        grad.addColorStop(0, 'rgba(0,0,0,0)');
        grad.addColorStop(0.5, `rgba(0,0,0,${(edgeAlpha * 0.15).toFixed(3)})`);
        grad.addColorStop(0.8, `rgba(0,0,0,${(edgeAlpha * 0.60).toFixed(3)})`);
        grad.addColorStop(1, `rgba(0,0,0,${edgeAlpha.toFixed(3)})`);

        ctx.fillStyle = grad;
        ctx.fillRect(fgX, fgY, fgW, fgH);
      }

      ctx.restore();


      // F1: Render blur boxes ON the canvas — actual blur from source video pixels
      // Coordinates: box.x/y/w/h in 1080×1920 output-frame space; mapped → canvas px
      const nowT = v.currentTime ?? 0;
      for (const box of (st?.blur_boxes || [])) {
        if (box.tracked) continue;
        const stT = box.start_time ?? 0, endT = box.end_time ?? 0;
        if ((stT > 0 || endT > 0) && !(nowT >= stT && (endT <= 0 || nowT <= endT))) continue;

        // Compute canvas position + source video region (two formats)
        let bx, by, bw, bh, sx, sy, sw, sh;
        if (box.video_rel) {
          bx = fgX + box.x * fgW;  by = fgY + box.y * fgH;
          bw = box.w * fgW;         bh = box.h * fgH;
          sx = box.x * vw;          sy = box.y * vh;
          sw = box.w * vw;          sh = box.h * vh;
        } else {
          bx = (box.x / 1080) * CW;  by = (box.y / 1920) * CH;
          bw = (box.w / 1080) * CW;  bh = (box.h / 1920) * CH;
          sx = Math.max(0, ((bx - fgX) / fgW) * vw);
          sy = Math.max(0, ((by - fgY) / fgH) * vh);
          sw = Math.min(vw - sx, (bw / fgW) * vw);
          sh = Math.min(vh - sy, (bh / fgH) * vh);
        }
        if (bw < 1 || bh < 1 || sw <= 0 || sh <= 0) continue;

        ctx.save();
        // Clip to the destination box — prevents visual bleed outside
        ctx.beginPath();
        ctx.rect(Math.floor(bx), Math.floor(by), Math.ceil(bw), Math.ceil(bh));
        ctx.clip();

        // Pixelate blur: scale video down to k×k blocks then back up without smoothing.
        // Reuse a single canvas element (pxCvsRef) to avoid per-frame GC pressure at 60fps.
        const k = 6; // block size in canvas px
        const pxW = Math.max(1, Math.ceil(bw / k));
        const pxH = Math.max(1, Math.ceil(bh / k));
        if (!pxCvsRef.current) pxCvsRef.current = document.createElement('canvas');
        const pxCvs = pxCvsRef.current;
        // Only resize the reused canvas when dimensions change (avoids expensive realloc)
        if (pxCvs.width !== pxW) pxCvs.width = pxW;
        if (pxCvs.height !== pxH) pxCvs.height = pxH;
        // Step 1: sample source video at low resolution
        pxCvs.getContext('2d').drawImage(v, sx, sy, sw, sh, 0, 0, pxW, pxH);
        // Step 2: scale back up with no interpolation → visible pixel blocks
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(pxCvs, 0, 0, pxW, pxH, bx, by, bw, bh);
        ctx.imageSmoothingEnabled = true;

        // Frosted glass tint
        ctx.fillStyle = 'rgba(180,210,255,0.12)';
        ctx.fillRect(bx, by, bw, bh);

        ctx.restore();

      }

    }
  }, []);

  // ── Immediate re-paint when paused and user tweaks any edit setting ──
  useEffect(() => {
    editStateRef.current = editState;
    if (!isPlaying && videoRef.current && videoRef.current.readyState >= 2) {
      paintFrame();
    }
  }, [editState, isPlaying, paintFrame]);

  // ── Pre-render custom background image into an offscreen canvas ──
  useEffect(() => {
    const imgPath = editState?.bg_image_path;
    if (editState?.bg_type !== 'image' || !imgPath) {
      bgCacheRef.current = null;
      if (!isPlaying && videoRef.current && videoRef.current.readyState >= 2) {
        paintFrame();
      }
      return;
    }
    const img = bgImageRef.current;
    if (!img) return;

    const buildCache = () => {
      if (!img.naturalWidth || !img.naturalHeight) return;
      const CW = 324, CH = 576;
      const off = document.createElement('canvas');
      off.width = CW; off.height = CH;
      const ctx = off.getContext('2d');
      const r  = img.naturalWidth / img.naturalHeight;
      const tr = CW / CH;
      const s  = r > tr ? CH / img.naturalHeight : CW / img.naturalWidth;
      const bw = img.naturalWidth  * s * 1.05;
      const bh = img.naturalHeight * s * 1.05;
      ctx.drawImage(img, (CW - bw) / 2, (CH - bh) / 2, bw, bh);
      bgCacheRef.current = off;
      if (!isPlaying && videoRef.current && videoRef.current.readyState >= 2) {
        paintFrame();
      }
    };

    if (img.complete && img.naturalWidth > 0) {
      buildCache();
    } else {
      img.onload = buildCache;
    }
  }, [editState?.bg_image_path, editState?.bg_type, isPlaying, paintFrame]);

  const currentTimeRef = useRef(currentTime);
  useEffect(() => {
    currentTimeRef.current = currentTime;
  }, [currentTime]);

  // ── Drive the canvas render loop when playing / repaint on pause & seek ──
  useEffect(() => {
    const v   = videoRef.current;
    const cvs = videoCanvasRef.current;
    if (!v || !cvs) return;

    const cancelLoop = () => {
      if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
    };

    if (!isPlaying) {
      v.pause();
      cancelLoop();
      const repaint = () => { if (v.readyState >= 2) paintFrame(); };
      repaint();
      v.addEventListener('seeked', repaint);
      return () => v.removeEventListener('seeked', repaint);
    }

    const st = editStateRef.current;
    const origVidDur = v.duration || duration || 16;
    const effectiveVidDur = (st?.video_trim_dur > 0 && st.video_trim_dur < origVidDur)
      ? st.video_trim_dur
      : origVidDur;
    const caOffset = st?.custom_audio_offset || 0;
    const caTrimStart = st?.custom_audio_trim_start || 0;
    const caTrimDur = (st?.custom_audio_trim_dur > 0)
      ? st.custom_audio_trim_dur
      : Math.max(0, (st?.custom_audio_dur || 0) - caTrimStart);
    const effectiveAudioEnd = st?.custom_audio_path ? (caOffset + caTrimDur) : 0;
    const masterDur = Math.max(effectiveVidDur, effectiveAudioEnd, 1);

    if (currentTimeRef.current < effectiveVidDur) {
      v.currentTime = currentTimeRef.current;
      v.play().catch(() => {});
    } else {
      v.pause();
    }

    let lastTick = performance.now();
    let lastDrawTime = 0;
    const FRAME_MS = 1000 / 30; // ~33ms per frame

    const draw = (timestamp) => {
      const now = performance.now();
      const dt = (now - lastTick) / 1000;
      lastTick = now;

      const currSt = editStateRef.current;
      const curOrigVidDur = v.duration || duration || 16;
      const curEffVidDur = (currSt?.video_trim_dur > 0 && currSt.video_trim_dur < curOrigVidDur)
        ? currSt.video_trim_dur
        : curOrigVidDur;
      const curCaOffset = currSt?.custom_audio_offset || 0;
      const curCaTrimStart = currSt?.custom_audio_trim_start || 0;
      const curCaTrimDur = (currSt?.custom_audio_trim_dur > 0)
        ? currSt.custom_audio_trim_dur
        : Math.max(0, (currSt?.custom_audio_dur || 0) - curCaTrimStart);
      const curEffAudioEnd = currSt?.custom_audio_path ? (curCaOffset + curCaTrimDur) : 0;
      const curMasterDur = Math.max(curEffVidDur, curEffAudioEnd, 1);

      let nextT = currentTimeRef.current;
      if (currentTimeRef.current < curEffVidDur && !v.paused) {
        nextT = v.currentTime;
        if (nextT >= curEffVidDur) {
          v.pause();
          nextT = curEffVidDur;
        }
      } else {
        nextT = currentTimeRef.current + dt;
      }

      if (nextT >= curMasterDur) {
        setIsPlaying(false);
        setCurrentTime(0);
        v.currentTime = 0;
        cancelLoop();
        paintFrame();
        return;
      }

      setCurrentTime(nextT);

      if (timestamp - lastDrawTime >= FRAME_MS) {
        paintFrame();
        lastDrawTime = timestamp;
      }
      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);
    return cancelLoop;
  }, [isPlaying, paintFrame, duration]);


  // ── Reset when switching clips — clear canvas immediately so no stale frame shows ──
useEffect(() => {
    const v = videoRef.current;
    setVideoLoaded(false);
    setIsPlaying(false);
    setCurrentTime(0);
    // Clear canvas right away so we don't flash the previous video's last frame
    const cvs = videoCanvasRef.current;
    if (cvs) {
      const ctx = cvs.getContext('2d');
      ctx.clearRect(0, 0, cvs.width, cvs.height);
    }
    if (!v) return;
    v.pause();
    v.currentTime = 0;
  }, [currentEditItem?.clip_path, currentEditItem?.path]);

  // Speed ±2% live preview: set HTML5 playbackRate so the preview actually plays faster.
  // Exact match to app.py: atempo=1.0204 (2% speed increase = 1/0.98 ≈ 1.0204).
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.playbackRate = editState?.speed_tweak ? 1.0204 : 1.0;
  }, [editState?.speed_tweak]);

  // ── Custom Audio Live Synchronization ──
  useEffect(() => {
    const v = videoRef.current;
    const a = customAudioRef.current;
    if (v) {
      const origVol = editState?.custom_audio_path ? (editState?.orig_volume ?? 0) : 100;
      v.volume = Math.max(0, Math.min(1.0, origVol / 100.0));
    }
    if (!a) return;

    if (!editState?.custom_audio_url || !editState?.custom_audio_path) {
      a.pause();
      return;
    }

    const custVol = (editState?.custom_volume ?? 100) / 100.0;
    a.volume = Math.max(0, Math.min(1.0, custVol));

    const offset = editState?.custom_audio_offset || 0;
    const trimStart = editState?.custom_audio_trim_start || 0;
    const rawDur = editState?.custom_audio_dur || a.duration || 9999;
    const trimDur = (editState?.custom_audio_trim_dur > 0)
      ? editState.custom_audio_trim_dur
      : Math.max(0, rawDur - trimStart);

    const progressInClip = currentTime - offset;

    if (isPlaying) {
      if (progressInClip >= 0 && progressInClip < trimDur) {
        const targetAudioTime = trimStart + progressInClip;
        if (Math.abs(a.currentTime - targetAudioTime) > 0.15) {
          a.currentTime = targetAudioTime;
        }
        if (a.paused) {
          a.play().catch(() => {});
        }
      } else {
        a.pause();
      }
    } else {
      a.pause();
      if (progressInClip >= 0 && progressInClip <= trimDur) {
        a.currentTime = trimStart + progressInClip;
      }
    }
  }, [
    isPlaying, currentTime,
    editState?.custom_audio_url, editState?.custom_audio_path,
    editState?.custom_audio_offset, editState?.custom_audio_trim_start,
    editState?.custom_audio_trim_dur, editState?.custom_volume,
    editState?.orig_volume, editState?.custom_audio_dur
  ]);


  // ── Config save helper ──
const updateCfg = useCallback(async (p) => {
    const next = { ...config, ...p };
    setConfig(next);
  // ── Never send video_files from the frontend ──
  // that list is managed exclusively
  // ── by the backend ──
  // (add/remove endpoints). Sending it here would overwrite the
    // server's in-memory list with a stale/empty frontend copy.
  // ── eslint-disable-next-line no-unused-vars ──
const { video_files, ...safePayload } = next;
    try { await post('/config', safePayload); } catch {}
  }, [config]);

  // ── Actions ──
const addFiles = async () => {
    await post('/dialog/pick_files', {});
    const r = await fetch(`${API}/videos`).then(res => res.json());
    setVideos(r.videos || []);
  };
  const pickFolder = () =>
    post('/dialog/pick_folder', { batch_id: activeBatchId })
      .then(r => r.json())
      .then(d => {
        const folder = d?.folder || d?.path;
        if (folder) {
          setConfig(p => ({ ...p, output_folder: folder }));
          fetchBatches();
        }
      });
  const lastOpenFolderRef = useRef(0);
  const openOutput = (folder = null) => {
    const now = Date.now();
    if (now - lastOpenFolderRef.current < 750) return;
    lastOpenFolderRef.current = now;
    const f = (typeof folder === 'string' && folder.trim()) ? folder.trim() : (config.output_folder || '');
    post('/system/open_output', f ? { folder: f, path: f } : {});
  };
  const openRawCuts = (folder = null) => {
    const now = Date.now();
    if (now - lastOpenFolderRef.current < 750) return;
    lastOpenFolderRef.current = now;
    const f = (typeof folder === 'string' && folder.trim()) ? folder.trim() : (config.output_folder || '');
    post('/system/open_raw_cuts', f ? { folder: f, path: f } : {});
  };
  const clearAll = async () => {
    await post('/videos/clear', {});
    setSelVideo(null);
    setVideos([]);
  };
  const removeVideo = async (p) => {
    await post('/videos/remove', { path: p });
    if (selVideo?.path === p) setSelVideo(null);
    const r = await fetch(`${API}/videos`).then(res => res.json());
    setVideos(r.videos || []);
  };

  const startAnalysis = async () => {
    const unanalyzed = (videos || []).filter(v => v.status !== 'done');
    if (videos.length > 0 && unanalyzed.length === 0) {
      const reRun = window.confirm('Tất cả video trong danh sách đã được phân tích xong.\n\nBạn có muốn phân tích lại TOÀN BỘ danh sách không?');
      if (!reRun) return;
      const r = await post('/analyze/start', { mode: analysisMode, force_all: true });
      if (!r.ok) { const d = await r.json(); alert(d.detail || 'Start failed'); }
      return;
    }
    const r = await post('/analyze/start', { mode: analysisMode });
    if (!r.ok) { const d = await r.json(); alert(d.detail || 'Start failed'); }
  };
  const retryErrors  = () => post('/analyze/start', { mode: analysisMode, retry_errors: true });
  const stopAnalysis = () => post('/analyze/stop', {});
  const stopExport   = () => post('/export/stop', {});
  // ── YouTube Direct Visual Analysis Handlers ──
  const handleAnalyzeYouTube = async () => {
    const url = ytUrl.trim();
    if (!url) {
      setYtError('Vui lòng dán link YouTube hợp lệ.');
      return;
    }
    setYtError('');
    setYtStatus('analyzing');
    setYtLoadingMsg('Gemini AI đang xem video trực tiếp từ YouTube và phân tích hình ảnh...');
    setYtInfo(null);
    setYtCandidates([]);
    setYtDownloadedSet(new Set());

    try {
      const res = await post('/youtube/analyze', { url, mode: ytMode });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: 'Phân tích thất bại' }));
        throw new Error(errData.detail || 'Phân tích thất bại');
      }
      const data = await res.json();
      setYtInfo(data.info || null);
      setYtCandidates(data.candidates || []);
      setYtStatus('done');
    } catch (err) {
      setYtStatus('error');
      setYtError(err.message || 'Lỗi kết nối máy chủ');
    }
  };

  const checkYtCookies = useCallback(async () => {
    try {
      const res = await fetch(`${API}/youtube/cookies_status`).then(r => r.json());
      setYtCookiesStatus(res || { has_cookies: false, filename: '', size: 0 });
    } catch {}
  }, []);

  useEffect(() => {
    checkYtCookies();
  }, [checkYtCookies]);

  useEffect(() => {
    if (showYtModal) {
      checkYtCookies();
    }
  }, [showYtModal, checkYtCookies]);

  const [updateStatus, setUpdateStatus] = useState(null);
  const [updating, setUpdating] = useState(false);

  const checkAppUpdate = useCallback(async () => {
    try {
      const res = await fetch(`${API}/update/status`).then(r => r.json());
      setUpdateStatus(res);
    } catch {}
  }, []);

  useEffect(() => {
    checkAppUpdate();
  }, [checkAppUpdate]);

  const handleApplyUpdateInApp = async () => {
    if (!confirm(`Tải và cập nhật lên phiên bản ${updateStatus?.remote_version || 'mới'}?\nSau khi cập nhật xong, hãy khởi động lại ứng dụng để sử dụng.`)) return;
    setUpdating(true);
    try {
      const res = await post('/update/apply', {});
      if (res.ok) {
        alert('🎉 Cập nhật thành công! Vui lòng đóng và mở lại run.bat để chạy phiên bản mới nhất.');
        checkAppUpdate();
      } else {
        alert('Cập nhật chưa thành công. Vui lòng kiểm tra lại kết nối mạng.');
      }
    } catch (e) {
      alert(`Lỗi cập nhật: ${e.message}`);
    } finally {
      setUpdating(false);
    }
  };

  const handleUploadCookieFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      if (!text || text.length < 10) {
        alert('File cookie trống hoặc không hợp lệ.');
        return;
      }
      const res = await post('/youtube/upload_cookies', { content: text, filename: file.name });
      if (res.ok) {
        await checkYtCookies();
        alert('✅ Nạp cookies.txt thành công! Giờ bạn có thể tải video YouTube mà không sợ bị chặn.');
      } else {
        const err = await res.json().catch(() => ({ detail: 'Lỗi nạp cookie' }));
        alert(`Lỗi: ${err.detail}`);
      }
    } catch (err) {
      alert(`Lỗi nạp file cookie: ${err.message}`);
    } finally {
      if (ytCookieFileInputRef.current) ytCookieFileInputRef.current.value = '';
    }
  };

  const handleSaveCookieText = async () => {
    if (!cookieInputText.trim()) return;
    try {
      const res = await post('/youtube/upload_cookies', { content: cookieInputText.trim() });
      if (res.ok) {
        await checkYtCookies();
        setShowCookiePasteModal(false);
        setCookieInputText('');
        alert('✅ Nạp cookies.txt thành công! Giờ bạn có thể tải video YouTube mà không sợ bị chặn.');
      } else {
        const err = await res.json().catch(() => ({ detail: 'Lỗi nạp cookie' }));
        alert(`Lỗi: ${err.detail}`);
      }
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
    }
  };

  const handleQuickPasteCookiesFromClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text || text.trim().length < 10) {
        setShowCookiePasteModal(true);
        return;
      }
      const res = await post('/youtube/upload_cookies', { content: text.trim() });
      if (res.ok) {
        await checkYtCookies();
        alert(`✅ Đã nạp Cookie YouTube trực tiếp từ Clipboard thành công! (${text.trim().length} bytes)`);
      } else {
        const err = await res.json().catch(() => ({ detail: 'Lỗi nạp cookie' }));
        alert(`Lỗi: ${err.detail}`);
      }
    } catch (err) {
      // Browser blocked clipboard permission -> open manual paste modal
      setShowCookiePasteModal(true);
    }
  };

  const handleDeleteCookies = async () => {
    if (!confirm('Bạn có chắc muốn xóa cookies.txt đã nạp?')) return;
    try {
      await fetch(`${API}/youtube/cookies`, { method: 'DELETE' });
      await checkYtCookies();
      alert('Đã xóa cookies thành công.');
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
    }
  };

  const parseYtUrls = (text) => {
    if (!text) return [];
    const ytRegex = /https?:\/\/(?:www\.)?(?:youtube\.com\/(?:watch\?v=|shorts\/)|youtu\.be\/)[a-zA-Z0-9_\-]+[^\s]*/gi;
    const matches = text.match(ytRegex) || [];
    return [...new Set(matches.map(u => u.replace(/[.,;]+$/, '').trim()))];
  };

  const handleBatchAddYouTube = async (analyzeNow = false) => {
    const urls = parseYtUrls(ytBatchText);
    if (urls.length === 0) {
      alert('Vui lòng dán ít nhất 1 link YouTube hợp lệ.');
      return;
    }
    setYtBatchBusy(true);
    try {
      const res = await post('/youtube/batch_add', {
        urls,
        analyze_now: analyzeNow,
        mode: ytMode,
      });
      if (res.ok) {
        const data = await res.json();
        alert(`✅ Đã thêm ${data.added_count} video YouTube vào hàng đợi Tab 1!${analyzeNow ? ' Hệ thống đang phân tích...' : ''}`);
        setShowYtModal(false);
        setYtBatchText('');
        try {
          const vR = await fetch(`${API}/videos`).then(r => r.json());
          setVideos(vR.videos || []);
        } catch {}
      } else {
        const err = await res.json().catch(() => ({ detail: 'Lỗi thêm video YouTube' }));
        alert(`Lỗi: ${err.detail}`);
      }
    } catch (e) {
      alert(`Lỗi: ${e.message}`);
    } finally {
      setYtBatchBusy(false);
    }
  };

  const downloadSingleCandidate = async (cand, idx, switchTab = true) => {
    // Khởi tạo tiến trình giả lập mượt mà theo từng giai đoạn
    setYtDownloadingMap(prev => ({
      ...prev,
      [idx]: { percent: 12, statusText: 'Đang kết nối YouTube...' }
    }));

    const progressTimer = setInterval(() => {
      setYtDownloadingMap(prev => {
        const cur = prev[idx];
        if (!cur) return prev;
        let nextP = cur.percent;
        let nextText = cur.statusText;
        if (nextP < 40) {
          nextP += 6;
          nextText = 'Đang tải luồng video...';
        } else if (nextP < 75) {
          nextP += 4;
          nextText = 'Đang tải luồng âm thanh...';
        } else if (nextP < 92) {
          nextP += 2;
          nextText = 'Đang ghép lát cắt MP4...';
        }
        return {
          ...prev,
          [idx]: { percent: Math.min(nextP, 92), statusText: nextText }
        };
      });
    }, 350);

    try {
      const res = await post('/youtube/download_to_studio', {
        url: ytUrl.trim(),
        start_time: cand.start_time,
        end_time: cand.end_time,
        title: cand.title || '',
        suggested_titles: cand.suggested_titles || [],
        target: 'edit',
      });
      clearInterval(progressTimer);

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: 'Tải đoạn clip thất bại' }));
        throw new Error(errData.detail || 'Tải đoạn clip thất bại');
      }
      const data = await res.json();

      setYtDownloadingMap(prev => ({
        ...prev,
        [idx]: { percent: 100, statusText: 'Hoàn thành 100%!' }
      }));
      await new Promise(r => setTimeout(r, 350));

      setYtDownloadedSet(prev => new Set([...prev, idx]));
      if (data.entry) {
        setEditQueue(prev => [...prev.filter(e => (e.clip_path || e.path) !== (data.entry.clip_path || data.entry.path)), data.entry]);
        if (switchTab) {
          setSelEditIdx(editQueue.length);
          setTab('edit');
        }
      }
    } catch (err) {
      clearInterval(progressTimer);
      const msg = err.message || '';
      if (msg.includes('Sign in to confirm') || msg.includes('cookies.txt') || msg.toLowerCase().includes('bot') || msg.toLowerCase().includes('xác minh')) {
        setShowCookieGuide(true);
        alert(`⚠️ Video này bị YouTube chặn hoặc yêu cầu đăng nhập (Sign in to confirm you're not a bot).\n\nVui lòng nạp file cookies.txt theo hướng dẫn màu vàng bên dưới để tải không bị chặn!`);
      } else {
        alert(`Lỗi tải đoạn clip: ${msg}`);
      }
    } finally {
      clearInterval(progressTimer);
      setYtDownloadingMap(prev => {
        const copy = { ...prev };
        delete copy[idx];
        return copy;
      });
    }
  };

  const handleDownloadYtCandidate = async (cand, idx) => {
    if (ytDownloadingMap[idx]) return;
    if (Object.keys(ytDownloadingMap).length >= 3) {
      alert("Hệ thống đang tải tối đa 3 luồng cùng lúc. Vui lòng chờ đoạn clip hiện tại hoàn thành!");
      return;
    }
    await downloadSingleCandidate(cand, idx, true);
  };

  const handleDownloadAllYtCandidates = async () => {
    if (ytDownloadAllBusy || ytCandidates.length === 0) return;
    setYtDownloadAllBusy(true);

    const CONCURRENCY = 3;
    const pending = ytCandidates
      .map((cand, idx) => ({ cand, idx }))
      .filter(({ idx }) => !ytDownloadedSet.has(idx) && !ytDownloadingMap[idx]);

    if (pending.length === 0) {
      setYtDownloadAllBusy(false);
      return;
    }

    let queue = [...pending];
    const worker = async () => {
      while (queue.length > 0) {
        const item = queue.shift();
        if (!item) break;
        await downloadSingleCandidate(item.cand, item.idx, false);
      }
    };

    const workerCount = Math.min(CONCURRENCY, pending.length);
    const workers = [];
    for (let w = 0; w < workerCount; w++) {
      workers.push(worker());
    }
    await Promise.all(workers);
    setYtDownloadAllBusy(false);
  };

  const renderYouTubeModal = () => {
    if (!showYtModal) return null;
    return (
      <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200">
        <div className="bg-[#0f111c] border border-gray-800 rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="px-5 py-4 border-b border-gray-800/80 flex items-center justify-between bg-gradient-to-r from-red-950/30 to-indigo-950/20">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-red-600/20 border border-red-500/30 flex items-center justify-center">
                <Youtube className="w-4 h-4 text-red-500" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  Phân Tích Video YouTube Trực Tiếp
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">Gemini Visual AI</span>
                </h3>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  Không cần tải video về máy — Gemini soi trực tiếp hình ảnh &amp; âm thanh trên Google Cloud, chỉ tải lát cắt hay vào Studio
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowYtModal(false)}
              className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800/60 transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Body */}
          <div className="p-5 flex-1 overflow-y-auto space-y-4">
            {/* Cookie Status & Bypass Section */}
            {ytCookiesStatus.has_cookies ? (
              <div className="px-3.5 py-2.5 bg-emerald-950/30 border border-emerald-800/40 rounded-xl flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-emerald-300 font-semibold">Cookie YouTube: Đã kết nối</span>
                  <span className="text-[11px] text-gray-400">({ytCookiesStatus.filename || 'cookies.txt'} · {(ytCookiesStatus.size / 1024).toFixed(1)} KB)</span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-900/50 text-emerald-200 border border-emerald-700/50">Tải được video 18+ &amp; chống bot</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleQuickPasteCookiesFromClipboard}
                    className="text-[11px] text-emerald-400 hover:text-emerald-200 underline font-semibold flex items-center gap-1"
                    title="Dán đè Cookie mới trực tiếp từ Clipboard"
                  >
                    <Clipboard className="w-3 h-3" />
                    <span>Dán mới từ Clipboard</span>
                  </button>
                  <span className="text-gray-600">|</span>
                  <button
                    onClick={() => ytCookieFileInputRef.current?.click()}
                    className="text-[11px] text-indigo-400 hover:text-indigo-300 underline"
                    title="Cập nhật file cookie mới"
                  >
                    Đổi file
                  </button>
                  <span className="text-gray-600">|</span>
                  <button
                    onClick={handleDeleteCookies}
                    className="text-[11px] text-red-400 hover:text-red-300"
                    title="Xóa cookies đã lưu"
                  >
                    Xóa
                  </button>
                </div>
              </div>
            ) : (
              <div className="p-3 bg-amber-950/25 border border-amber-800/40 rounded-xl space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2">
                    <span className="text-amber-400 text-sm mt-0.5">🍪</span>
                    <div>
                      <p className="text-xs font-bold text-amber-200">
                        Chưa nạp Cookie YouTube (Khuyên dùng để chống chặn bot &amp; tải video 18+)
                      </p>
                      <p className="text-[11px] text-amber-300/80 mt-0.5">
                        YouTube thường bắt xác minh bot hoặc đăng nhập với các video phóng sự, bodycam nhạy cảm. Nạp cookie giúp tải mọi video 100% mượt mà.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 pt-0.5">
                  <button
                    type="button"
                    onClick={handleQuickPasteCookiesFromClipboard}
                    className="px-3 py-1.5 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-black text-xs font-bold rounded-lg flex items-center gap-1.5 transition shadow"
                    title="Dán ngay cookie bạn vừa copy từ trình duyệt mà không cần chỉnh sửa file"
                  >
                    <Clipboard className="w-3.5 h-3.5" />
                    <span>📋 Dán nhanh Cookie từ Clipboard (1-Click)</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowCookiePasteModal(true)}
                    className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-semibold rounded-lg transition"
                  >
                    📝 Mở ô Dán tay
                  </button>
                  <button
                    type="button"
                    onClick={() => ytCookieFileInputRef.current?.click()}
                    className="px-2.5 py-1.5 bg-gray-900 hover:bg-gray-800 text-gray-400 text-xs rounded-lg transition"
                  >
                    <span>📂 Nạp file .txt</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowCookieGuide(prev => !prev)}
                    className="text-xs text-amber-400 hover:text-amber-300 underline ml-auto"
                  >
                    {showCookieGuide ? 'Ẩn hướng dẫn ▲' : '❓ Cách lấy cookie (30s) ▼'}
                  </button>
                </div>

                {showCookieGuide && (
                  <div className="mt-2 pt-2 border-t border-amber-800/40 text-[11px] text-gray-300 space-y-1.5 bg-black/40 p-3 rounded-lg">
                    <p className="font-bold text-amber-300">3 bước đơn giản để lấy cookie:</p>
                    <ol className="list-decimal list-inside space-y-1 text-gray-300">
                      <li>
                        Cài tiện ích Chrome/Edge:&nbsp;
                        <a
                          href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc"
                          target="_blank"
                          rel="noreferrer"
                          className="text-indigo-400 hover:text-indigo-300 underline font-semibold"
                        >
                          Get cookies.txt LOCALLY (Bấm vào đây để mở trang cài đặt)
                        </a>
                      </li>
                      <li>Mở tab <span className="text-white font-mono">youtube.com</span> (đảm bảo đang đăng nhập).</li>
                      <li>Bấm vào biểu tượng tiện ích ở góc trình duyệt ➔ Chọn <strong>Copy</strong> (hoặc Export).</li>
                      <li>Quay lại đây bấm nút <strong>"📋 Dán nhanh Cookie từ Clipboard"</strong> ➔ Xong ngay, không cần sửa file!</li>
                    </ol>
                    <p className="text-[10px] text-gray-400 italic mt-1">
                      * File cookies được lưu cục bộ trên máy tính của bạn, hoàn toàn an toàn và bảo mật.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Sub Navigation: Single vs Batch */}
            <div className="flex border-b border-gray-800 bg-black/30 rounded-xl p-1 gap-1">
              <button
                type="button"
                onClick={() => setYtBatchTab('single')}
                className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5 ${
                  ytBatchTab === 'single'
                    ? 'bg-red-950/60 text-white border border-red-800/60 shadow-sm'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                <Youtube className="w-3.5 h-3.5 text-red-500" />
                <span>Phân Tích 1 Video Nhanh</span>
              </button>
              <button
                type="button"
                onClick={() => setYtBatchTab('batch')}
                className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5 ${
                  ytBatchTab === 'batch'
                    ? 'bg-indigo-950/60 text-white border border-indigo-800/60 shadow-sm'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                <Layers className="w-3.5 h-3.5 text-indigo-400" />
                <span>Nhập List YouTube Hàng Loạt (Như Local)</span>
                <span className="text-[9px] px-1.5 py-0.2 rounded-full bg-indigo-600/40 text-indigo-300 font-semibold">Mới</span>
              </button>
            </div>

            {ytBatchTab === 'batch' ? (
              /* ── Batch YouTube Import Tab ── */
              <div className="space-y-4 pt-1 animate-in fade-in duration-150">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-gray-200 flex items-center gap-1.5">
                      <span>Dán danh sách link YouTube (Mỗi dòng 1 link hoặc cách nhau bằng dấu phẩy)</span>
                    </label>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          const text = await navigator.clipboard.readText();
                          if (text) {
                            setYtBatchText(prev => prev ? `${prev}\n${text}` : text);
                          }
                        } catch (err) {
                          alert('Trình duyệt chưa cấp quyền đọc Clipboard.');
                        }
                      }}
                      className="text-[11px] text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1"
                    >
                      <Clipboard className="w-3 h-3" />
                      <span>Dán link từ Clipboard</span>
                    </button>
                  </div>
                  <textarea
                    value={ytBatchText}
                    onChange={e => setYtBatchText(e.target.value)}
                    rows={6}
                    placeholder="https://www.youtube.com/watch?v=...&#10;https://youtu.be/...&#10;https://www.youtube.com/shorts/..."
                    className="w-full bg-black/60 border border-gray-700 rounded-xl p-3 text-xs font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
                  />
                  <div className="flex items-center justify-between text-[11px]">
                    {(() => {
                      const detected = parseYtUrls(ytBatchText);
                      return (
                        <span className={detected.length > 0 ? "text-emerald-400 font-semibold" : "text-gray-500"}>
                          ✓ Đã phát hiện {detected.length} link YouTube hợp lệ
                        </span>
                      );
                    })()}
                    {ytBatchText && (
                      <button
                        type="button"
                        onClick={() => setYtBatchText('')}
                        className="text-gray-500 hover:text-gray-300 text-[10px]"
                      >
                        Xóa danh sách
                      </button>
                    )}
                  </div>
                </div>

                {/* Mode selection for batch */}
                <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-3 space-y-2">
                  <span className="text-[11px] font-semibold text-gray-300">Chế độ phân tích AI:</span>
                  <div className="grid grid-cols-2 gap-3">
                    <label
                      onClick={() => setYtMode('short')}
                      className={`cursor-pointer rounded-xl p-3 border transition flex flex-col gap-1 ${
                        ytMode === 'short'
                          ? 'bg-red-950/40 border-red-500/60 ring-1 ring-red-500/40'
                          : 'bg-gray-900/50 border-gray-800 hover:border-gray-700'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-white">⚡ Short Mode (16s)</span>
                        <input type="radio" checked={ytMode === 'short'} onChange={() => setYtMode('short')} className="accent-red-500" />
                      </div>
                      <p className="text-[10px] text-gray-400">Tìm các pha giật gân, hành động, cao trào 16s chuẩn TikTok / Reels.</p>
                    </label>
                    <label
                      onClick={() => setYtMode('story')}
                      className={`cursor-pointer rounded-xl p-3 border transition flex flex-col gap-1 ${
                        ytMode === 'story'
                          ? 'bg-red-950/40 border-red-500/60 ring-1 ring-red-500/40'
                          : 'bg-gray-900/50 border-gray-800 hover:border-gray-700'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-white">📖 Story Mode (30–90s)</span>
                        <input type="radio" checked={ytMode === 'story'} onChange={() => setYtMode('story')} className="accent-red-500" />
                      </div>
                      <p className="text-[10px] text-gray-400">Trích xuất câu chuyện trọn vẹn, phóng sự có mở đầu - cao trào - kết thúc.</p>
                    </label>
                  </div>
                </div>

                {/* Batch action buttons */}
                <div className="flex items-center justify-end gap-2.5 pt-2">
                  <button
                    type="button"
                    disabled={ytBatchBusy || parseYtUrls(ytBatchText).length === 0}
                    onClick={() => handleBatchAddYouTube(false)}
                    className="px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-200 text-xs font-semibold rounded-xl transition flex items-center gap-1.5"
                  >
                    <Plus className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Thêm vào hàng đợi Tab 1</span>
                  </button>
                  <button
                    type="button"
                    disabled={ytBatchBusy || parseYtUrls(ytBatchText).length === 0}
                    onClick={() => handleBatchAddYouTube(true)}
                    className="px-5 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white text-xs font-bold rounded-xl transition shadow-lg flex items-center gap-1.5"
                  >
                    {ytBatchBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-current" />}
                    <span>Thêm &amp; Phân tích hàng loạt ngay</span>
                  </button>
                </div>
              </div>
            ) : (
              /* ── Single Video Analysis Tab ── */
              <div className="space-y-4 pt-1 animate-in fade-in duration-150">
                {/* Input URL & Mode */}
                <div className="space-y-2">
                  <label className="text-[11px] font-medium text-gray-300 flex items-center justify-between">
                    <span>Dán link YouTube (Public hoặc Unlisted)</span>
                    <span className="text-[10px] text-gray-500">Hỗ trợ link youtube.com hoặc youtu.be</span>
                  </label>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <input
                        type="text"
                        value={ytUrl}
                        onChange={e => setYtUrl(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && ytStatus !== 'analyzing') handleAnalyzeYouTube(); }}
                        placeholder="https://www.youtube.com/watch?v=..."
                        className="w-full bg-black/60 border border-gray-700 rounded-xl px-3.5 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-red-500 transition"
                      />
                      {ytUrl && (
                        <button
                          onClick={() => setYtUrl('')}
                          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs"
                        >
                          ✕
                        </button>
                      )}
                    </div>

                    {/* Mode Selector */}
                    <div className="flex bg-black/40 border border-gray-700/80 rounded-xl p-0.5 gap-0.5">
                      <button
                        type="button"
                        onClick={() => setYtMode('short')}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                          ytMode === 'short' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        ⚡ Short (16s)
                      </button>
                      <button
                        type="button"
                        onClick={() => setYtMode('story')}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                          ytMode === 'story' ? 'bg-emerald-600 text-white' : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        🎥 Story (30–90s)
                      </button>
                    </div>

                    <button
                      onClick={handleAnalyzeYouTube}
                      disabled={ytStatus === 'analyzing' || !ytUrl.trim()}
                      className="px-4 py-2 bg-gradient-to-r from-red-600 to-indigo-600 hover:from-red-500 hover:to-indigo-500 disabled:opacity-40 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 transition shadow-lg shrink-0"
                    >
                      {ytStatus === 'analyzing' ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Đang xem video...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>Soi Highlight</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Error banner */}
                {ytError && (
                  <div className="p-3 bg-red-950/40 border border-red-800/60 rounded-xl text-xs text-red-300 flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="font-semibold">Lỗi phân tích:</p>
                      <p className="text-[11px] text-red-400/90 mt-0.5">{ytError}</p>
                    </div>
                  </div>
                )}

                {/* Analyzing state */}
                {ytStatus === 'analyzing' && (
                  <div className="py-10 flex flex-col items-center justify-center text-center space-y-3">
                    <div className="relative">
                      <div className="w-14 h-14 rounded-full bg-red-600/20 border-2 border-red-500/40 flex items-center justify-center animate-pulse">
                        <Youtube className="w-7 h-7 text-red-500 animate-bounce" />
                      </div>
                      <div className="absolute inset-0 rounded-full border-2 border-indigo-500 animate-ping opacity-25" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-white">Gemini đang giải mã và xem video</h4>
                      <p className="text-xs text-gray-400 mt-1 max-w-md">
                        Google Cloud đang phân tích các khung hình hành động, cao trào và âm thanh trực tiếp từ YouTube. Quá trình mất khoảng 5–15 giây...
                      </p>
                    </div>
                  </div>
                )}

                {/* Results: Info + Highlights */}
                {ytStatus === 'done' && (
                  <div className="space-y-4 animate-in fade-in duration-300">
                    {/* YouTube Video Info Card */}
                    {ytInfo && (
                      <div className="p-3 bg-black/40 border border-gray-800 rounded-xl flex items-center gap-3.5">
                        {ytInfo.thumbnail ? (
                          <img
                            src={ytInfo.thumbnail}
                            alt="thumbnail"
                            className="w-24 h-14 object-cover rounded-lg border border-gray-800 shrink-0"
                          />
                        ) : (
                          <div className="w-24 h-14 bg-gray-900 rounded-lg flex items-center justify-center text-gray-600 shrink-0">
                            <Youtube className="w-6 h-6" />
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-bold text-white truncate" title={ytInfo.title}>
                            {ytInfo.title}
                          </p>
                          <div className="flex items-center gap-3 text-[10px] text-gray-400 mt-1">
                            {ytInfo.uploader && <span>Kênh: <strong className="text-gray-300">{ytInfo.uploader}</strong></span>}
                            {ytInfo.duration > 0 && (
                              <span>Thời lượng: <strong className="text-emerald-400">{Math.floor(ytInfo.duration / 60)}m{Math.floor(ytInfo.duration % 60)}s</strong></span>
                            )}
                            <span className="text-indigo-400 font-medium">⚡ Đã tìm thấy {ytCandidates.length} highlight</span>
                          </div>
                        </div>
                        {ytCandidates.length > 1 && (
                          <button
                            onClick={handleDownloadAllYtCandidates}
                            disabled={ytDownloadAllBusy}
                            className="px-3 py-1.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shrink-0 flex items-center gap-1.5 transition shadow"
                          >
                            {ytDownloadAllBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-200" /> : <Download className="w-3.5 h-3.5" />}
                            <span>{ytDownloadAllBusy ? 'Đang tải 3 luồng cùng lúc...' : `Tải tất cả (${ytCandidates.length}) - 3 luồng song song`}</span>
                          </button>
                        )}
                      </div>
                    )}

                    {/* Candidate List */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-[11px] text-gray-400 px-1">
                        <span className="font-semibold uppercase tracking-wider text-[10px] text-gray-500">Danh sách Highlight phát hiện bởi Gemini:</span>
                        <span>Tải cùng lúc 3 luồng song song vào Canvas</span>
                      </div>

                      {ytCandidates.length === 0 ? (
                        <div className="p-6 text-center text-gray-500 text-xs border border-dashed border-gray-800 rounded-xl">
                          Gemini không phát hiện khoảnh khắc nào thực sự kịch tính đạt tiêu chuẩn. Thử đổi sang chế độ Story hoặc link khác.
                        </div>
                      ) : (
                        ytCandidates.map((cand, idx) => {
                          const isDownloaded = ytDownloadedSet.has(idx);
                          const downloadInfo = ytDownloadingMap[idx];
                          const isDownloading = Boolean(downloadInfo);
                          return (
                            <div
                              key={idx}
                              className={`p-3.5 bg-gray-900/40 hover:bg-gray-900/70 border rounded-xl transition flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                                isDownloading
                                  ? 'border-indigo-500/70 bg-indigo-950/20 shadow-[0_0_15px_rgba(99,102,241,0.15)]'
                                  : isDownloaded
                                  ? 'border-emerald-800/40 bg-emerald-950/10'
                                  : 'border-gray-800/80 hover:border-gray-700'
                              }`}
                            >
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="px-1.5 py-0.5 rounded bg-red-950 text-red-300 border border-red-800/50 text-[9px] font-bold font-mono">
                                    #{idx + 1}
                                  </span>
                                  <span className="px-2 py-0.5 rounded-full bg-emerald-950/60 text-emerald-300 border border-emerald-800/40 text-[9px] font-mono font-semibold">
                                    ⏱ {cand.start_time} ➔ {cand.end_time} ({cand.clip_duration || 16}s)
                                  </span>
                                </div>
                                <h5 className="text-xs font-bold text-white text-left break-words">
                                  {cand.title}
                                </h5>
                                {cand.highlight_reason && (
                                  <p className="text-[11px] text-gray-400 mt-1 text-left line-clamp-2">
                                    💡 {cand.highlight_reason}
                                  </p>
                                )}

                                {/* Thanh tiến trình tải thời gian thực */}
                                {isDownloading && (
                                  <div className="mt-2.5 space-y-1">
                                    <div className="flex items-center justify-between text-[10px]">
                                      <span className="text-indigo-300 font-semibold flex items-center gap-1.5">
                                        <Loader2 className="w-3 h-3 animate-spin text-indigo-400" />
                                        {downloadInfo.statusText}
                                      </span>
                                      <span className="font-mono font-bold text-indigo-300">{downloadInfo.percent}%</span>
                                    </div>
                                    <div className="w-full bg-gray-800/80 rounded-full h-2 overflow-hidden border border-indigo-950/60 p-[1px]">
                                      <div
                                        className="bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-400 h-full rounded-full transition-all duration-300 ease-out shadow-sm"
                                        style={{ width: `${downloadInfo.percent}%` }}
                                      />
                                    </div>
                                  </div>
                                )}
                              </div>

                              <div className="shrink-0 flex items-center gap-2">
                                <button
                                  onClick={() => handleDownloadYtCandidate(cand, idx)}
                                  disabled={isDownloading || isDownloaded}
                                  className={`px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition ${
                                    isDownloaded
                                      ? 'bg-emerald-900/40 border border-emerald-600/50 text-emerald-300 cursor-default'
                                      : isDownloading
                                      ? 'bg-indigo-950 border border-indigo-500/80 text-indigo-300 cursor-wait'
                                      : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-md'
                                  }`}
                                >
                                  {isDownloaded ? (
                                    <>
                                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                                      <span>Đã trong Studio</span>
                                    </>
                                  ) : isDownloading ? (
                                    <>
                                      <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping mr-0.5" />
                                      <span className="font-mono font-bold">{downloadInfo.percent}%</span>
                                    </>
                                  ) : (
                                    <>
                                      <Download className="w-3.5 h-3.5" />
                                      <span>Tải vào Studio</span>
                                    </>
                                  )}
                                </button>
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <input
          ref={ytCookieFileInputRef}
          type="file"
          accept=".txt"
          className="hidden"
          onChange={handleUploadCookieFile}
        />

        {showCookiePasteModal && (
          <div className="fixed inset-0 z-[60] bg-black/80 flex items-center justify-center p-4 animate-in fade-in duration-150">
            <div className="bg-[#141724] border border-gray-700 rounded-2xl p-5 max-w-lg w-full space-y-3 shadow-2xl">
              <div className="flex items-center justify-between border-b border-gray-800 pb-2.5">
                <h4 className="text-xs font-bold text-white flex items-center gap-2">
                  <span>📋</span> Dán nội dung Cookie YouTube
                </h4>
                <button onClick={() => setShowCookiePasteModal(false)} className="text-gray-400 hover:text-white text-sm">✕</button>
              </div>
              <div className="flex items-center justify-between">
                <p className="text-[11px] text-gray-400">
                  Dán trực tiếp nội dung cookie từ tiện ích (định dạng Netscape):
                </p>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const text = await navigator.clipboard.readText();
                      if (text) setCookieInputText(text);
                    } catch {}
                  }}
                  className="text-[11px] text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1"
                >
                  <Clipboard className="w-3 h-3" />
                  <span>Dán từ Clipboard</span>
                </button>
              </div>
              <textarea
                value={cookieInputText}
                onChange={e => setCookieInputText(e.target.value)}
                rows={8}
                placeholder="# Netscape HTTP Cookie File&#10;.youtube.com&#9;TRUE&#9;/&#9;TRUE&#9;..."
                className="w-full bg-black/60 border border-gray-700 rounded-xl p-3 text-[11px] font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
              />
              <div className="flex justify-end gap-2 pt-1">
                <button
                  onClick={() => setShowCookiePasteModal(false)}
                  className="px-3.5 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs rounded-xl"
                >
                  Hủy
                </button>
                <button
                  onClick={handleSaveCookieText}
                  disabled={!cookieInputText.trim()}
                  className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-xs font-bold rounded-xl shadow"
                >
                  Lưu Cookie
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  // CUT: cuts clip, returns path, does NOT send to edit yet
  const cutClip = async () => {
    if (!selVideo || selCand < 0) return;
    setCutBusy(true);
    try {
      // Dùng clip_duration của candidate nếu Story Mode (AI đã xác định), fallback về clipDuration (Short Mode)
      const cand = selVideo?.candidates?.[selCand];
      const isStory = analysisMode === 'story' && cand?.clip_duration && cand.clip_duration !== 16;
      const baseDuration = isStory ? cand.clip_duration : (clipDuration || 16);
      const trimDuration = Math.max(1, baseDuration + trimEnd - trimStart);
      const startTime = cand?.start_time || cand?.start_ts || '00:00:00';
      const r = await post('/cut', {
        video_path:         selVideo.path,
        candidate_index:    selCand,
        title:              selTitle,
        start_time:         startTime,
        trim_start_offset:  trimStart,   // seconds to shift start (±30)
        trim_duration:      trimDuration, // resulting clip length
      });
      const d = await r.json();
      if (r.ok) {
        setLastCutPath(d.output);
      } else {
        alert(d.detail || 'Cut failed');
      }
    } catch (e) { alert(String(e)); }
    finally { setCutBusy(false); }
  };

  // ── SEND ALL CANDIDATES TO TAB 2 (TITLE #1) ──
  const sendAllCandidatesToEdit = async () => {
    if (!selVideo) return;
    const cands = selVideo?.candidates || [];
    if (!cands.length) {
      alert('Video chưa có cảnh (candidates) nào được AI phân tích.');
      return;
    }
    setSendAllBusy(true);
    try {
      const effDuration = Math.max(1, (clipDuration || 16) + trimEnd - trimStart);
      const r = await post('/candidates/send_all_to_edit', {
        video_path: selVideo.path,
        trim_start_offset: trimStart,
        trim_duration: effDuration,
        mode: analysisMode,
      });
      const d = await r.json();
      if (r.ok) {
        if (d.entries && Array.isArray(d.entries)) {
          setEditQueue(prev => {
            const newMap = new Map();
            prev.forEach(item => newMap.set(item.clip_path || item.path, item));
            d.entries.forEach(entry => newMap.set(entry.clip_path || entry.path, entry));
            return Array.from(newMap.values());
          });
        }
        if (d.added_count > 0) {
          setTimeout(() => {
            setSelEditIdx(0);
            setTab('edit');
          }, 50);
          alert(`⚡ Đã chuyển thành công ${d.added_count} cảnh vào Tab 2 (với Title #1)!`);
        } else {
          alert('Không có cảnh nào được thêm vào Tab 2. Vui lòng kiểm tra lại log hoặc kết nối.');
        }
      } else {
        alert(d.detail || 'Không thể chuyển tất cả cảnh vào Tab 2');
      }
    } catch (e) {
      alert(String(e));
    } finally {
      setSendAllBusy(false);
    }
  };

  // ── SEND ALL CANDIDATES ACROSS ALL VIDEOS TO TAB 2 (TITLE #1) ──
  const sendAllVideosCandidatesToEdit = async () => {
    if (totalAllCandidates === 0) {
      alert('Chưa có video nào trong danh sách có cảnh (candidates) được AI phân tích.');
      return;
    }
    const confirmed = window.confirm(
      `⚡ CẮT HÀNG LOẠT:\nBạn có chắc muốn tự động cắt toàn bộ ${totalAllCandidates} cảnh của TẤT CẢ các video trong danh sách sang Tab 2 (sử dụng Title #1)?`
    );
    if (!confirmed) return;

    setSendAllVideosBusy(true);
    try {
      const effDuration = Math.max(1, (clipDuration || 16) + trimEnd - trimStart);
      const r = await post('/candidates/send_all_videos_to_edit', {
        trim_start_offset: trimStart,
        trim_duration: effDuration,
        mode: analysisMode,
      });
      const d = await r.json();
      if (r.ok) {
        if (d.entries && Array.isArray(d.entries)) {
          setEditQueue(prev => {
            const newMap = new Map();
            prev.forEach(item => newMap.set(item.clip_path || item.path, item));
            d.entries.forEach(entry => newMap.set(entry.clip_path || entry.path, entry));
            return Array.from(newMap.values());
          });
        }
        if (d.added_count > 0) {
          setTimeout(() => {
            setSelEditIdx(0);
            setTab('edit');
          }, 50);
          alert(`⚡ Thành công! Đã cắt & chuyển ${d.added_count} cảnh của ${d.processed_videos || ''} video vào Tab 2!`);
        } else {
          alert('Không có cảnh nào được thêm vào Tab 2. Vui lòng kiểm tra lại log.');
        }
      } else {
        alert(d.detail || 'Không thể cắt tất cả cảnh của các video');
      }
    } catch (e) {
      alert(String(e));
    } finally {
      setSendAllVideosBusy(false);
    }
  };

  // ── SEND TO ──
  // EDIT: push cut clip + selected title into edit queue (Tab 2)
  const sendToEdit = async () => {
    if (!lastCutPath) { alert('Cut a clip first.'); return; }
    if (!selTitle.trim()) { alert('Click a title to select it first.'); return; }
    const cand = selVideo?.candidates?.[selCand];
    const suggested = cand?.suggested_titles || [];
    const r = await post('/edit_queue/add', {
      clip_path: lastCutPath,
      title: selTitle.trim(),
      suggested_titles: suggested,
      state: DEF,
    });
    if (r.ok) {
      const d = await r.json();
  // ── Server returns entry ──
  // directly; fall back to constructing it locally if missing
      const entry = d.entry || {
        clip_path: lastCutPath, path: lastCutPath,
        name: lastCutPath.split(/[\\/]/).pop(),
        title: selTitle.trim(),
        suggested_titles: suggested,
        state: { ...DEF },
      };
  // ── Avoid race with ──
  // polling: update local state directly from POST response
      let nextIdx = 0;
      setEditQueue(prev => {
        const without = prev.filter(c => (c.clip_path || c.path) !== entry.clip_path);
        nextIdx = without.length; // ── new item lands at this index ────────────────────────────────────────────────────────
return [...without, entry];
      });
  // ── Defer index ──
  // ── has already been processed before selEditIdx is ──
// evaluated.
      setTimeout(() => {
        setSelEditIdx(nextIdx);
        setTab('edit');
      }, 50);
    } else {
      const d = await r.json().catch(() => ({}));
      alert(`Send to Edit failed: ${d.detail || r.status}`);
    }
  };

  // ── Export all clips from Edit Queue ──
  // each clip uses its OWN state+title
  // ── Uses ──

  // ── Canvas Title Overlay Renderer ─────────────────────────────────────────
  // Renders the title box at full 1080×1920 resolution using the same browser
  // Canvas 2D engine that drives the live preview → guarantees identical
  // word-wrap, stroke, padding, and positioning in the exported video.
  //
  // Works in main thread using a hidden <canvas> because OffscreenCanvas
  // requires a Worker context for toBlob(). The canvas is 1080×1920 but
  // never attached to the DOM, so no layout impact.
  const buildTitleOverlayBlob = React.useCallback(async (clip, W = 1080, H = 1920) => {
    const st    = { ...DEF, ...(clip.state || {}) };
    const title = st.title_uppercase ? (clip.title || '').toUpperCase() : (clip.title || '');
    if (!title.trim()) return null;

    // Ensure bundled fonts are loaded (served from FastAPI)
    const BUNDLED = { montserrat: 'Montserrat', luckiestguy: 'Luckiest Guy', nunito: 'Nunito', permanentmarker: 'Permanent Marker' };
    const fontKey = (st.font_name || 'impact').toLowerCase();
    if (BUNDLED[fontKey]) {
      try {
        const fontUrl = `${API}/font/file?key=${fontKey}`;
        const face = new FontFace(BUNDLED[fontKey], `url(${fontUrl})`);
        if (![...document.fonts].some(f => f.family === BUNDLED[fontKey] && f.status === 'loaded')) {
          await face.load();
          document.fonts.add(face);
        }
      } catch (_) { /* fallback gracefully */ }
    }

    const fontSize     = st.font_size || 52;
    const fontFamily   = FONT_MAP[fontKey] || `"${fontKey}", Impact, sans-serif`;
    const fontWeight   = st.font_bold ? 'bold' : 'normal';
    const fontStyle    = st.font_italic ? 'italic' : 'normal';
    const fontSpec     = `${fontStyle} ${fontWeight} ${fontSize}px ${fontFamily}`;

    // ── Geometry — must exactly mirror _make_title_image in app.py ──
    const boxMode         = st.box_mode || 'frame';
    const isBubbleMode    = (boxMode === 'capcut' || boxMode === 'badges');
    const marginX         = 26.67;
    const fullContainerW  = W - 2 * marginX;
    const wrapPct         = Math.max(0.3, Math.min(1.0, st.title_wrap_pct ?? 1.0));
    const boxW            = fullContainerW * wrapPct;
    const lPadX           = Math.max(6.0, Math.round(fontSize * 0.35));
    const padX            = isBubbleMode ? (20.0 + lPadX) : 40.0;
    const padY            = isBubbleMode ? Math.max(2.0, Math.round(fontSize * 0.16)) : 26.67;
    const maxTextW        = Math.max(50.0, boxW - 2 * padX);

    // ── Word wrap (use st.title_lines if present, else deterministic wrapTitleText) ──
    const letterSp = st.letter_spacing ?? 0;
    const lines = (Array.isArray(st.title_lines) && st.title_lines.length > 0)
      ? st.title_lines
      : wrapTitleText(title, fontSpec, maxTextW, letterSp);

    // ── Canvas setup ──
    const cvs = document.createElement('canvas');
    cvs.width  = W;
    cvs.height = H;
    const ctx  = cvs.getContext('2d');
    ctx.clearRect(0, 0, W, H);

    // ── Parse colors ──
    const parseHex = hex => {
      if (!hex || hex.length < 7) return [255,255,255];
      return [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)];
    };
    const fgRgb   = parseHex(st.text_color_hex || '#ffffff');
    const bgRgb   = parseHex(st.box_bg_color_hex || '#222222');
    const boxAlpha = (st.box_opacity ?? 90) / 100;
    const lineH   = (st.line_height || (boxMode === 'capcut' ? 1.35 : 1.2)) * fontSize;
    // letterSp declared above (before offCtx) — do not re-declare

    // ── Text position ──────────────────────────────────────────────────────────
    // IMPORTANT: In the CSS preview, `top: yPct%; transform: translateY(-50%)`
    // means the CENTER of the title box sits at text_y pixels from the top of
    // the 1920px frame.  My canvas must match this: compute boxTopY so that the
    // CENTER of the drawn rectangle is at textY.
    const textX   = (st.text_x || 0);   // px offset from center at full 1080px width
    const textY   = (st.text_y ?? 60);  // CENTER of the box in 1920px space
    const boxRad  = st.box_radius ?? 40;  // matches CSS preview default (also in DEF)
    const align   = st.text_align || 'left';

    // ── Horizontal position: box centered at W/2 + textX offset ──
    const boxLeft = W / 2 - boxW / 2 + textX;
    const totalTextH = lines.length * lineH;

    // ── Vertical: compute top of box so its CENTER is at textY ──
    // frame:  box height = totalTextH + 2*padY
    // capcut: first line starts at boxTopY, each line lineH tall + 2*lPadY
    // badges: similar, but with gaps between lines
    // We use frame geometry for the centering anchor; modes adjust from boxTopY.
    const frameTotalH = totalTextH + 2 * padY;
    const boxTopY     = textY - frameTotalH / 2;

    ctx.save();

    // ── Apply rotation around the box's visual center ──
    const rotation   = (st.text_rotation || 0) * Math.PI / 180;
    const boxCenterX = boxLeft + boxW / 2;
    const boxCenterY = textY;   // the CENTER is exactly at textY (matching CSS)
    if (rotation !== 0) {
      ctx.translate(boxCenterX, boxCenterY);
      ctx.rotate(rotation);
      ctx.translate(-boxCenterX, -boxCenterY);
    }


    // ── Draw function for a rounded rect ──
    const roundRect = (x, y, w, h, r) => {
      r = Math.min(r, w/2, h/2);
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

    const strokePx    = (st.stroke_enabled !== false && (st.stroke_width ?? 0) > 0) ? st.stroke_width : 0;
    const strokeColor = st.stroke_color_hex || '#000000';
    const [sr, sg, sb] = parseHex(strokeColor);

    // ─────────────────────────────────────────────────────────────────────────
    if (boxMode === 'frame') {
      // Full rectangular background box — top edge at boxTopY so center is at textY
      const bgFillColor = `rgba(${bgRgb[0]},${bgRgb[1]},${bgRgb[2]},${boxAlpha})`;
      const boxH = frameTotalH;
      ctx.fillStyle = bgFillColor;
      roundRect(boxLeft, boxTopY, boxW, boxH, boxRad);
      ctx.fill();

      // Draw each line
      lines.forEach((line, i) => {
        const ly = boxTopY + padY + i * lineH + fontSize * 0.8; // baseline
        let lx;
        if (align === 'center') lx = boxLeft + boxW / 2;
        else if (align === 'right') lx = boxLeft + boxW - padX;
        else lx = boxLeft + padX;

        ctx.textAlign = align === 'center' ? 'center' : align === 'right' ? 'right' : 'left';
        if (strokePx > 0) {
          ctx.fillStyle = `rgba(${sr},${sg},${sb},1)`;
          for (const [dx, dy] of [[-strokePx,-strokePx],[strokePx,-strokePx],[-strokePx,strokePx],[strokePx,strokePx],[0,-strokePx],[0,strokePx],[-strokePx,0],[strokePx,0]]) {
            ctx.fillText(line, lx + dx, ly + dy);
          }
        }
        ctx.fillStyle = `rgba(${fgRgb[0]},${fgRgb[1]},${fgRgb[2]},${(st.text_opacity ?? 100)/100})`;
        ctx.fillText(line, lx, ly);
      });

    } else if (boxMode === 'capcut') {
      // Per-line continuous bubble — start from boxTopY so the group center is at textY
      const lPadX = Math.max(6, Math.round(fontSize * 0.35));
      const lPadY = Math.max(2, Math.round(lineH * 0.16));
      const effRad = Math.min(boxRad, Math.round((lineH + 2 * lPadY) * 0.30));

      // Draw all merged background boxes first
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

      // Draw text for all lines on top
      lines.forEach((line, i) => {
        const lw = ctx.measureText(line).width;
        const ly = boxTopY + i * lineH;
        let lx;
        if (align === 'center') lx = boxLeft + padX + (maxTextW - lw) / 2;
        else if (align === 'right') lx = boxLeft + boxW - padX - lw;
        else lx = boxLeft + padX;

        ctx.textAlign = 'left';
        const baseline = ly + fontSize * 0.8;
        if (strokePx > 0) {
          ctx.fillStyle = `rgba(${sr},${sg},${sb},1)`;
          for (const [dx, dy] of [[-strokePx,-strokePx],[strokePx,-strokePx],[-strokePx,strokePx],[strokePx,strokePx],[0,-strokePx],[0,strokePx],[-strokePx,0],[strokePx,0]]) {
            ctx.fillText(line, lx + dx, baseline + dy);
          }
        }
        ctx.fillStyle = `rgba(${fgRgb[0]},${fgRgb[1]},${fgRgb[2]},${(st.text_opacity ?? 100)/100})`;
        ctx.fillText(line, lx, baseline);
      });

    } else {
      // badges — separate pill per line, start from boxTopY
      const lPadX = Math.max(6, Math.round(fontSize * 0.35));
      const lPadY = Math.max(1, Math.round(lineH * 0.08));
      const gap   = Math.max(2, Math.round(fontSize * 0.15));
      const effRad = Math.min(boxRad, Math.round((lineH + 2 * lPadY) * 0.30));

      // Draw backgrounds
      ctx.fillStyle = `rgba(${bgRgb[0]},${bgRgb[1]},${bgRgb[2]},${boxAlpha})`;
      lines.forEach((line, i) => {
        const lw  = ctx.measureText(line).width;
        const ly  = boxTopY + i * (lineH + gap);
        let lx;
        if (align === 'center') lx = boxLeft + padX + (maxTextW - lw) / 2;
        else if (align === 'right') lx = boxLeft + boxW - padX - lw;
        else lx = boxLeft + padX;

        roundRect(lx - lPadX, ly - lPadY, lw + 2 * lPadX, lineH + 2 * lPadY, effRad);
        ctx.fill();
      });

      // Draw text
      lines.forEach((line, i) => {
        const lw  = ctx.measureText(line).width;
        const ly  = boxTopY + i * (lineH + gap);
        let lx;
        if (align === 'center') lx = boxLeft + padX + (maxTextW - lw) / 2;
        else if (align === 'right') lx = boxLeft + boxW - padX - lw;
        else lx = boxLeft + padX;

        ctx.textAlign = 'left';
        const baseline = ly + fontSize * 0.8;
        if (strokePx > 0) {
          ctx.fillStyle = `rgba(${sr},${sg},${sb},1)`;
          for (const [dx, dy] of [[-strokePx,-strokePx],[strokePx,-strokePx],[-strokePx,strokePx],[strokePx,strokePx],[0,-strokePx],[0,strokePx],[-strokePx,0],[strokePx,0]]) {
            ctx.fillText(line, lx + dx, baseline + dy);
          }
        }
        ctx.fillStyle = `rgba(${fgRgb[0]},${fgRgb[1]},${fgRgb[2]},${(st.text_opacity ?? 100)/100})`;
        ctx.fillText(line, lx, baseline);
      });
    }


    ctx.restore();

    // ── Convert to base64 PNG ──
    return new Promise(resolve => cvs.toBlob(blob => {
      if (!blob) { resolve(null); return; }
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result.split(',')[1]); // strip data:...;base64,
      reader.readAsDataURL(blob);
    }, 'image/png'));
  }, []);   // no deps — pure function over args


  const startExport = async () => {
    if (!editQueue.length) { alert('No clips in Edit queue.'); return; }
    try {
      // Generate canvas PNG overlays for every clip concurrently
      const overlays = await Promise.all(
        editQueue.map(c => buildTitleOverlayBlob(c).catch(() => null))
      );

      const r = await post('/export/queue', {
        items: editQueue.map((c, i) => ({
          clip_path:         c.clip_path || c.path,
          title:             c.title || '',
          state:             { ...DEF, ...(c.state || {}) },
          title_overlay_b64: overlays[i] || null,
        })),
        threads:    config.export_threads || 2,
        crf:        config.export_crf || 20,
        preset:     config.export_preset || 'fast',
        encoder:    config.export_encoder || 'libx264',
        resolution: config.export_resolution || '1080x1920',
        fps:        config.export_fps || null,
      });
      const d = await r.json();
      if (r.ok) {
        alert(`🚀 Export started for ${editQueue.length} clip(s)!\nWatch progress in status bar at the bottom.`);
      } else {
        alert(`Export failed: ${d.detail || 'Error'}`);
      }
    } catch (e) {
      alert(`Export error: ${String(e)}`);
    }
  };

  const startExportAllBatches = async () => {
    const totalClips = batches.reduce((acc, b) => acc + (b.count || 0), 0);
    if (totalClips === 0) { alert('Không có clip nào trong tất cả các cụm để xuất.'); return; }
    if (!confirm(`Bạn có muốn xuất tất cả ${batches.length} cụm với tổng cộng ${totalClips} clip không?\nMỗi cụm sẽ tự động xuất vào thư mục riêng tương ứng.`)) return;

    try {
      const r = await post('/export/all_batches', {
        threads:    config.export_threads || 2,
        crf:        config.export_crf || 20,
        preset:     config.export_preset || 'fast',
        encoder:    config.export_encoder || 'libx264',
        resolution: config.export_resolution || '1080x1920',
        fps:        config.export_fps || null,
      });
      const d = await r.json();
      if (r.ok) {
        alert(`🚀 Đã bắt đầu xuất tất cả ${batches.length} cụm (${totalClips} clip)!\nTheo dõi tiến độ ở thanh trạng thái bên dưới.`);
      } else {
        alert(`Lỗi xuất: ${d.detail || 'Error'}`);
      }
    } catch (e) {
      alert(`Export error: ${String(e)}`);
    }
  };

  const reanalyzeVideo = async (path, e) => {
    e?.stopPropagation();
    try {
      const r = await post('/videos/reanalyze', { path });
      const d = await r.json();
      if (r.ok) {
        await fetchVideos();
      } else {
        alert(d.detail || 'Lỗi phân tích lại video');
      }
    } catch (err) {
      alert(`Lỗi: ${err}`);
    }
  };


  // ── Drag ──
  const handleDropTab1 = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const files = Array.from(e.dataTransfer?.files || []);
    if (!files.length) return;
    const videoFiles = files.filter(f => /\.(mp4|mkv|mov|avi|ts)$/i.test(f.name));
    if (!videoFiles.length) { alert('Please drop valid video files (.mp4, .mkv, .mov, .avi, .ts).'); return; }

    const formData = new FormData();
    videoFiles.forEach(f => formData.append('files', f));
    try {
      const r = await fetch(`${API}/videos/upload_files`, { method: 'POST', body: formData });
      if (r.ok) {
        const vR = await fetch(`${API}/videos`).then(res => res.json());
        setVideos(vR.videos || []);
      }
    } catch (err) { alert(`Upload error: ${err}`); }
  };

  const handleDropTab2 = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const files = Array.from(e.dataTransfer?.files || []);
    if (!files.length) return;
    const videoFiles = files.filter(f => /\.(mp4|mkv|mov|avi|ts)$/i.test(f.name));
    if (!videoFiles.length) { alert('Please drop valid video files (.mp4, .mkv, .mov, .avi, .ts).'); return; }

    const formData = new FormData();
    videoFiles.forEach(f => formData.append('files', f));
    try {
      if (config.direct_import_gen_title !== false) {
        alert(`✨ Đang thêm trực tiếp: Gemini AI đang tạo tiêu đề cho ${videoFiles.length} video...\nClip sẽ xuất hiện trong Edit Queue sau giây lát.`);
      } else {
        alert(`✨ Đang thêm trực tiếp ${videoFiles.length} video vào Edit Queue (để trống tiêu đề)...`);
      }
      await fetch(`${API}/edit_queue/upload_direct`, { method: 'POST', body: formData });
    } catch (err) { alert(`Lỗi import: ${err}`); }
  };

  // ── Sync current ──
  // item's edit state to ALL clips in the queue (bulk sync).
  // ── Timed subtitle boxes ──
  // (created by auto-detect, have start_time or end_time)
  // ── are clip-specific ──
  // they must NOT be propagated to other clips.
  const syncAllState = () => {
    if (selEditIdx < 0) return;
    const srcState = currentEditItem?.state || {};

  // ── Strip boxes that were generated by auto-detect ──
  // (they carry timestamps
  // ── tied to the source ──
  // clip's content → useless / wrong on other clips).
    const isTimedSubBox = b =>
      (b.start_time !== undefined && b.start_time > 0) ||
      (b.end_time   !== undefined && b.end_time   > 0);

    const syncableBoxes = (srcState.blur_boxes || []).filter(b => !isTimedSubBox(b));
    const syncableState = { ...srcState, blur_boxes: syncableBoxes };

    setEditQueue(prev => prev.map((item, i) => {
      if (i === selEditIdx) return item; // leave source untouched
      // F3: when a selection is active, only sync to selected items
      if (selEditIdxs.size > 1 && !selEditIdxs.has(i)) return item;
      const targetTimedBoxes = (item.state?.blur_boxes || []).filter(isTimedSubBox);
      const newState = {
        ...DEF,
        ...syncableState,
        blur_boxes: [...syncableBoxes, ...targetTimedBoxes],
      };

      // CRITICAL FIX: persist synced state to server so that Bulk Subtitle "Apply & Dismiss"
      // (which fetches server state) doesn't revert these settings back to pre-sync values.
      // Strip `title` from patch — server treats it specially and would overwrite clip's own title.
      const { title: _ignored, ...patchWithoutTitle } = newState;
      post('/edit_queue/update', { index: i, patch: patchWithoutTitle });

      return { ...item, state: newState };
    }));
  };

  const removeEditClip = async (idx) => {
    const clip = editQueue[idx];
    if (!clip) return;
    pushUndo({ type: 'removeEditClip', idx, item: clip }); // F4: allow Ctrl+Z undo
    await post('/edit_queue/remove', { path: clip.clip_path || clip.path });
    const eq = await fetch(`${API}/edit_queue`).then(r => r.json());
    const clips = eq.clips || [];
    setEditQueue(clips);
    if (selEditIdx >= clips.length) setSelEditIdx(clips.length - 1);
  };

  // ── Derived ──
const errLogs    = logs.filter(l => l.level === 'error').length;
  const isExporting = exportProg.status === 'exporting';
  const cand       = selVideo?.candidates?.[selCand];
  const titles5    = (cand?.suggested_titles?.length > 0)
    ? cand.suggested_titles
    : (cand?.title ? [cand.title] : []);

  // ── Keyboard shortcuts (Tab 1 only) ───────────────────────────────────────
  // Space: play/pause preview  |  ↑↓: navigate candidates
  // E: cut selected clip       |  Enter: jump to next video in list
  useEffect(() => {
    if (tab !== 'analyze') return;
    const onKey = (e) => {
      // Never intercept when the user is typing in an input / select
      const tag = document.activeElement?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

      const cands = selVideo?.candidates || [];

      if (e.code === 'Space') {
        e.preventDefault();
        const v = videoRef.current;
        if (!v) return;
        v.paused ? v.play() : v.pause();

      } else if (e.code === 'ArrowUp') {
        e.preventDefault();
        setSelCand(c => Math.max(0, c - 1));
        setSelTitle('');

      } else if (e.code === 'ArrowDown') {
        e.preventDefault();
        setSelCand(c => Math.min(cands.length - 1, c + 1));
        setSelTitle('');

      } else if (e.code === 'KeyE') {
        e.preventDefault();
        if (selVideo && !cutBusy) cutClip();

      } else if (e.code === 'Enter') {
        e.preventDefault();
        if (!selVideo) return;
        const idx = videos.findIndex(v => v.path === selVideo.path);
        if (next) { setSelVideo(next); setSelCand(0); setSelTitle(''); setLastCutPath(''); }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [tab, selVideo, selCand, cutBusy, videos, cutClip]);

  // ── TAB ──
  // 1: Analyze & Select ??????????????????????????????????????????????????????????????????????????????????????????????
  const AnalyzeTab = () => (
    <div className="flex flex-1 overflow-hidden">

      {/* ── Left Sidebar  ── */}
      <div className="w-52 shrink-0 border-r border-gray-800/70 flex flex-col bg-[#0d0e17] text-xs">

        {/* ── API Keys ── */}
        <div className="border-b border-gray-800/60">
          <button onClick={() => setShowKeys(p => !p)}
            className="w-full flex items-center gap-2 px-3 py-2 text-[10px] font-bold text-gray-500 uppercase tracking-widest hover:text-gray-300 transition">
            <Key className="w-3 h-3 text-indigo-400" />API Keys
            <ChevronRight className={`w-3 h-3 ml-auto transition-transform ${showKeys ? 'rotate-90' : ''}`} />
          </button>
          {showKeys && (
            <div className="px-3 pb-3 space-y-2">
              <select value={config.model_name || 'gemini-3.5-flash-lite'} onChange={e => updateCfg({ model_name: e.target.value })}
                className="w-full bg-gray-900 border border-gray-800 rounded-lg px-2 py-1.5 text-[10px] text-gray-200 outline-none">
                <option value="gemini-3.1-flash-lite">Gemini 3.1 Flash Lite ⚡</option>
                <option value="gemini-3.5-flash-lite">Gemini 3.5 Flash Lite</option>
              </select>

              {/* Analysis parallel streams */}
              <div className="flex items-center justify-between py-1 border-t border-gray-800/50">
                <div>
                  <p className="text-[9px] text-gray-400 font-semibold">Analysis Streams</p>
                  <p className="text-[8px] text-gray-600">Videos analyzed at once</p>
                </div>
                <div className="flex items-center gap-1">
                  <input type="range" min={1} max={5} step={1}
                    value={config.analysis_parallel ?? 3}
                    onChange={e => updateCfg({ analysis_parallel: parseInt(e.target.value) })}
                    className="w-16 accent-indigo-500" />
                  <span className="text-[10px] text-indigo-300 w-3 text-center">{config.analysis_parallel ?? 3}</span>
                </div>
              </div>

              {/* CTA Toggle ?? persisted to config so backend reads it before each analysis run */}
              <div className="flex items-center justify-between py-1 border-t border-gray-800/50">
                <div>
                  <p className="text-[9px] text-gray-400 font-semibold">CTA at end of title</p>
                  <p className="text-[8px] text-gray-600">👉 Follow for more!</p>
                </div>
                <button
                  id="cta-toggle-btn"
                  onClick={() => updateCfg({ include_cta: !config.include_cta })}
                  className={`relative w-8 h-4 rounded-full transition-colors duration-200 focus:outline-none ${
                    config.include_cta ? 'bg-indigo-600' : 'bg-gray-700'
                  }`}
                >
                  <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform duration-200 ${
                    config.include_cta ? 'translate-x-4' : 'translate-x-0.5'
                  }`} />
                </button>
              </div>

              <div className="flex items-center justify-between mt-1 mb-1">
                <span className="text-[8.5px] text-gray-400 font-medium">Gemini API Keys</span>
                <button
                  type="button"
                  onClick={() => {
                    const raw = prompt("Dán danh sách API Keys (mỗi dòng 1 key, hoặc cách nhau bởi dấu phẩy):");
                    if (!raw) return;
                    const keys = raw.split(/[\r\n,;]+/).map(k => k.trim()).filter(k => k.length > 5);
                    if (keys.length > 0) {
                      const current = (config.api_keys || []).filter(k => k && k.trim());
                      const merged = Array.from(new Set([...current, ...keys]));
                      updateCfg({ api_keys: merged });
                      alert(`Đã thêm ${keys.length} API key(s) thành công!`);
                    }
                  }}
                  className="text-[8px] text-indigo-400 hover:text-indigo-300 hover:underline flex items-center gap-0.5"
                  title="Dán nhiều API key cùng một lúc">
                  📋 Dán hàng loạt
                </button>
              </div>

              {(config.api_keys || ['']).map((k, i) => (
                <div key={i} className="flex gap-1">
                  <input type="password" value={k} placeholder={`#${i + 1} AIzaSy…`}
                    onPaste={e => {
                      const text = e.clipboardData?.getData('text');
                      if (!text) return;
                      const keys = text.split(/[\r\n,;]+/).map(x => x.trim()).filter(x => x.length > 5);
                      if (keys.length > 1) {
                        e.preventDefault();
                        const current = (config.api_keys || []).filter((_, j) => j !== i && _.trim());
                        const merged = Array.from(new Set([...current, ...keys]));
                        updateCfg({ api_keys: merged });
                      }
                    }}
                    onChange={e => { const a = [...config.api_keys]; a[i] = e.target.value; updateCfg({ api_keys: a }); }}
                    className="flex-1 bg-gray-900 border border-gray-800 rounded-lg px-2 py-1 text-[9px] font-mono text-gray-300 outline-none focus:border-indigo-500" />
                  <button onClick={() => updateCfg({ api_keys: [...config.api_keys, ''] })}
                    className="text-indigo-400 p-1 hover:bg-gray-800 rounded"><Plus className="w-2.5 h-2.5" /></button>
                  {config.api_keys.length > 1 &&
                    <button onClick={() => updateCfg({ api_keys: config.api_keys.filter((_, j) => j !== i) })}
                      className="text-red-500 p-1 hover:bg-gray-800 rounded"><Trash2 className="w-2.5 h-2.5" /></button>}
                </div>
              ))}
            </div>
          )}
        </div>


        {/* ── Input Videos ── */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800/50">
          <span className="text-[9px] font-bold text-gray-500 uppercase tracking-widest">Input Videos</span>
          <div className="flex gap-1 items-center">
            <button
              onClick={() => { setShowYtModal(true); setYtBatchTab('batch'); }}
              className="px-1.5 py-0.5 bg-red-950/40 hover:bg-red-900/60 border border-red-800/50 rounded text-red-300 flex items-center gap-1 text-[8.5px] font-semibold transition"
              title="Nhập danh sách link YouTube để phân tích hàng loạt như local"
            >
              <Youtube className="w-2.5 h-2.5 text-red-500" /> + List YouTube
            </button>
            <button onClick={addFiles} className="p-1 hover:bg-gray-800 rounded text-indigo-400" title="Select Files"><Plus className="w-3 h-3" /></button>
            <button onClick={clearAll} className="p-1 hover:bg-gray-800 rounded text-red-500" title="Clear all"><Trash2 className="w-3 h-3" /></button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-1" onDragOver={e => e.preventDefault()} onDrop={handleDropTab1}>
          {videos.length === 0
            ? <button onClick={addFiles} className="w-full h-24 border-2 border-dashed border-gray-800/80 rounded-xl p-3 flex flex-col items-center justify-center gap-1 text-gray-600 hover:text-indigo-400 hover:border-indigo-500/40 transition text-[9px]">
              <Plus className="w-5 h-5 text-indigo-400" />
              <span>Select Files or Drag & Drop videos here</span>
            </button>
            : videos.map(v => (
              <div key={v.path} onClick={() => { setSelVideo(v); setSelCand(0); setSelTitle(''); setLastCutPath(''); }}
                className={`px-2.5 py-1.5 border-b border-gray-800/30 cursor-pointer transition flex items-center gap-1.5 ${selVideo?.path === v.path ? 'bg-indigo-600/20' : 'hover:bg-gray-800/40'}`}>
                <div className="flex-1 overflow-hidden">
                  <div className="flex items-center gap-1">
                    {v.is_youtube && (
                      <span className="px-1 py-0.2 bg-red-600/30 text-red-400 border border-red-500/30 text-[7.5px] font-bold rounded shrink-0">
                        YT
                      </span>
                    )}
                    <p className="text-[10px] font-medium truncate text-gray-100" title={v.name}>{v.name}</p>
                  </div>
                  <Badge status={v.status} />
                </div>
                <button onClick={e => reanalyzeVideo(v.path, e)} className="shrink-0 text-gray-600 hover:text-amber-400 p-0.5" title="Phân tích lại video này">
                  <RefreshCw className="w-2.5 h-2.5" />
                </button>
                <button onClick={e => { e.stopPropagation(); removeVideo(v.path); }} className="shrink-0 text-gray-700 hover:text-red-400 p-0.5">
                  <Trash2 className="w-2.5 h-2.5" />
                </button>
              </div>
            ))}
        </div>

        {/* ── Output folder ── */}
        <div className="border-t border-gray-800/60 px-3 py-2 space-y-1.5">
          <div className="flex items-center justify-between">
            <p className="text-[9px] text-gray-600 uppercase tracking-widest">Output Folder</p>
            <button onClick={() => openRawCuts()} className="text-[8px] text-indigo-400 hover:text-indigo-300 hover:underline flex items-center gap-0.5" title="Mở thư mục chứa các file raw cuts đã cắt">
              <FolderOpen className="w-2.5 h-2.5" /> Raw Cuts
            </button>
          </div>
          <div className="flex items-center gap-1.5">
            <p onClick={() => openOutput()} className="text-[9px] text-indigo-400 hover:underline truncate flex-1 cursor-pointer" title="Click to open folder in Windows Explorer">
              {config.output_folder || 'Default'}
            </p>
            <button onClick={() => openOutput()} className="text-amber-400 hover:text-amber-300 p-1 bg-gray-800/60 hover:bg-gray-800 rounded" title="Open Folder in Windows Explorer">
              <FolderOpen className="w-3.5 h-3.5" />
            </button>
            <button onClick={pickFolder} className="px-2 py-1 bg-indigo-600/80 hover:bg-indigo-600 text-white rounded text-[9px] font-medium shrink-0" title="Change Output Folder">
              Change
            </button>
          </div>
        </div>
      </div>

      {/* ── Main Panel  ── */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* ── VIDEO QUEUE table ── */}
        <div className="shrink-0 border-b border-gray-800/50 bg-gray-900/20">
          <div className="px-3 py-1 border-b border-gray-800/40 text-[9px] font-bold text-gray-500 uppercase tracking-widest flex items-center justify-between gap-4">
            <span className="flex-1">Video File</span>
            <div className="flex items-center gap-2">
              {totalAllCandidates > 0 && (
                <button
                  onClick={sendAllVideosCandidatesToEdit}
                  disabled={sendAllVideosBusy}
                  className="px-2 py-0.5 rounded bg-emerald-800/60 hover:bg-emerald-700 text-emerald-200 text-[8.5px] font-bold flex items-center gap-1 transition shadow-sm"
                  title="Cắt tất cả candidates của tất cả video trong danh sách sang Tab 2"
                >
                  {sendAllVideosBusy ? <RefreshCw className="w-2.5 h-2.5 animate-spin" /> : <Scissors className="w-2.5 h-2.5 text-amber-300" />}
                  Cắt hết tất cả cảnh ({totalAllCandidates})
                </button>
              )}
              <span className="w-28 text-right">Status</span>
            </div>
          </div>
          <div className="max-h-32 overflow-y-auto">
            {videos.length === 0
              ? <p className="text-[9px] text-gray-700 text-center py-3">No videos — add files from sidebar</p>
              : videos.map(v => (
                <div key={v.path} onClick={() => { setSelVideo(v); setSelCand(0); setSelTitle(''); setLastCutPath(''); }}
                  className={`px-3 py-1.5 border-b border-gray-800/20 cursor-pointer flex items-center transition ${selVideo?.path === v.path ? 'bg-indigo-600/20' : 'hover:bg-gray-800/30'}`}>
                  <span className="text-[10px] text-gray-200 flex-1 truncate">{v.name}</span>
                  <div className="w-28 flex items-center justify-end gap-1.5">
                    <Badge status={v.status} />
                    <button onClick={e => reanalyzeVideo(v.path, e)} className="text-gray-500 hover:text-amber-400 p-0.5 transition" title="Phân tích lại video này">
                      <RefreshCw className="w-2.5 h-2.5" />
                    </button>
                  </div>
                </div>
              ))}
          </div>
        </div>

        {/* ── RESULTS ── */}
        {selVideo ? (
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* ── Results header ── */}
            <div className="shrink-0 px-3 py-1.5 border-b border-gray-800/40 bg-gray-900/30 flex items-center justify-between">
              <div className="flex items-center gap-2 truncate">
                <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest">RESULTS</span>
                <span className="text-[9px] text-gray-400 truncate">{selVideo.name}</span>
              </div>
              <button
                onClick={e => reanalyzeVideo(selVideo.path, e)}
                className="px-2 py-0.5 bg-gray-800/80 hover:bg-amber-950/50 border border-gray-700/60 hover:border-amber-600/50 rounded text-[9px] text-gray-300 hover:text-amber-300 flex items-center gap-1 transition shrink-0"
                title="Chạy lại phân tích cho video này"
              >
                <RefreshCw className="w-2.5 h-2.5 text-amber-400" />
                <span>Phân tích lại video này</span>
              </button>
            </div>

            {selVideo.candidates?.length > 0 ? (
              <div className="flex-1 overflow-y-auto p-3 space-y-3">

                {/* ── Candidate thumbnail strip ── */}
                <div className="flex gap-2 overflow-x-auto pb-1 snap-x snap-mandatory">
                  {selVideo.candidates.map((c, i) => {
                    const startSec = (() => {
                      const parts = (c.start_time || '00:00:00').split(':').map(Number);
                      return parts.length === 3
                        ? parts[0] * 3600 + parts[1] * 60 + parts[2]
                        : parts.length === 2 ? parts[0] * 60 + parts[1] : 0;
                    })();
                    const thumbUrl = `/api/clip/thumbnail?path=${encodeURIComponent(selVideo.path)}&start=${startSec}`;
                    const isSelected = selCand === i;
                    return (
                      <button
                        key={i}
                        onClick={() => { setSelCand(i); setSelTitle(''); setLastCutPath(''); }}
                        className={`flex-none snap-start rounded-lg overflow-hidden border-2 transition focus:outline-none ${
                          isSelected ? 'border-indigo-500 ring-1 ring-indigo-400/60' : 'border-gray-800 hover:border-gray-600'
                        }`}
                        title={`Clip #${c.id || i + 1} · ${c.start_time} → ${c.end_time || '+16s'}`}
                      >
                        <div className="relative w-[45px] h-[80px] bg-gray-900">
                          <img
                            src={thumbUrl}
                            alt={`Clip ${i + 1}`}
                            className="w-full h-full object-cover"
                            onError={e => { e.target.style.display = 'none'; }}
                            loading="lazy"
                          />
                          {/* Gradient + label */}
                          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-0.5 pb-0.5 pt-2">
                            <p className="text-[7px] font-bold text-white leading-none text-center">
                              #{c.id || i + 1}
                            </p>
                            <p className="text-[6px] text-gray-300 leading-none text-center truncate">
                              {c.start_time?.slice(0, 5)}
                            </p>
                            {/* Badge thoi luong candidate */}
                            <p className="text-[6px] text-indigo-300 leading-none text-center font-bold">
                              {"⏱"}{c.clip_duration ? c.clip_duration + "s" : "16s"}
                            </p>
                          </div>
                          {isSelected && (
                            <div className="absolute inset-0 ring-inset ring-2 ring-indigo-400/70 pointer-events-none rounded-md" />
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>

                {/* ── Clip Trimmer ── */}
                <div className="bg-gray-900/50 border border-gray-800/40 rounded-lg p-2.5 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider">✂ Clip Trimmer</span>
                    {/* Hiển thị độ dài hiệu lực của clip đang chọn */}
                    {(() => {
                      const cand = selVideo?.candidates?.[selCand];
                      const isStory = analysisMode === 'story' && cand?.clip_duration && cand.clip_duration !== 16;
                      const base = isStory ? cand.clip_duration : (clipDuration || 16);
                      const eff  = Math.max(1, base + trimEnd - trimStart);
                      return (
                        <span className="text-[9px] font-mono text-indigo-300">
                          {trimStart > 0 ? `+${trimStart}s` : trimStart < 0 ? `${trimStart}s` : '0s'} / {eff}s total
                        </span>
                      );
                    })()}
                    {(trimStart !== 0 || trimEnd !== 0) && (
                      <button onClick={() => {
                        setTrimStart(0);
                        setTrimEnd(0);
                        localStorage.setItem('trimStart', '0');
                        localStorage.setItem('trimEnd', '0');
                      }}
                        className="text-[8px] text-gray-600 hover:text-gray-400 transition ml-1">reset</button>
                    )}
                  </div>
                  <div className="space-y-1.5">
                    {/* Clip Length — chỉ hiển khi Short Mode và candidate không có clip_duration tự động từ AI */}
                    {(() => {
                      const cand = selVideo?.candidates?.[selCand];
                      const isStoryCandidate = cand?.clip_duration && cand.clip_duration !== 16;
                      return !isStoryCandidate ? (
                        <div className="flex items-center gap-2">
                          <span className="text-[8px] text-gray-600 w-16 shrink-0">Clip length</span>
                          <input type="number" min="5" max="90" step="1" value={clipDuration}
                            onChange={e => {
                              const raw = e.target.value;
                              if (raw === '') {
                                setClipDuration('');
                                return;
                              }
                              const v = Number(raw);
                              setClipDuration(v);
                              if (!isNaN(v) && v >= 5 && v <= 90) {
                                localStorage.setItem('clipDuration', String(v));
                              }
                            }}
                            onBlur={() => {
                              const v = Math.max(5, Math.min(90, Number(clipDuration) || 16));
                              setClipDuration(v);
                              localStorage.setItem('clipDuration', String(v));
                            }}
                            className="w-14 h-5 bg-gray-800 border border-gray-700 rounded text-[9px] font-mono text-indigo-300 text-center px-1" />
                          <span className="text-[8px] text-gray-600 shrink-0">s</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <span className="text-[8px] text-gray-600 w-16 shrink-0">Clip length</span>
                          <span className="text-[9px] font-mono text-emerald-400">{cand.clip_duration}s (auto)</span>
                        </div>
                      );
                    })()}
                    <div className="flex items-center gap-2">
                      <span className="text-[8px] text-gray-600 w-16 shrink-0">Start offset</span>
                      <input type="range" min="-30" max="30" step="1" value={trimStart}
                        onChange={e => {
                          const v = Number(e.target.value);
                          setTrimStart(v);
                          localStorage.setItem('trimStart', String(v));
                        }}
                        className="flex-1 h-1 accent-indigo-500 cursor-pointer" />
                      <span className="text-[8px] font-mono text-indigo-400 w-8 text-right shrink-0">
                        {trimStart > 0 ? `+${trimStart}` : trimStart}s
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[8px] text-gray-600 w-16 shrink-0">End offset</span>
                      <input type="range" min="-30" max="30" step="1" value={trimEnd}
                        onChange={e => {
                          const v = Number(e.target.value);
                          setTrimEnd(v);
                          localStorage.setItem('trimEnd', String(v));
                        }}
                        className="flex-1 h-1 accent-indigo-500 cursor-pointer" />
                      <span className="text-[8px] font-mono text-indigo-400 w-8 text-right shrink-0">
                        {trimEnd > 0 ? `+${trimEnd}` : trimEnd}s
                      </span>
                    </div>
                  </div>
                </div>

                {/* Reason / description */}
                {(cand?.reason || cand?.description) && (
                  <div className="bg-gray-900/50 border border-gray-800/50 rounded-lg p-2">
                    <p className="text-[10px] text-gray-400 leading-relaxed">{cand.reason || cand.description}</p>
                  </div>
                )}

                {/* ???? Viral Titles — click to select & copy ???? */}
                {titles5.length > 0 && (
                  <div>
                    <p className="text-[9px] text-gray-500 mb-1.5">Viral Titles — click to select &amp; copy:</p>
                    <div className="space-y-1">
                      {titles5.map((t, i) => (
                        <button key={i}
                          onClick={() => { setSelTitle(t); navigator.clipboard?.writeText(t); }}
                          className={`w-full text-left px-2.5 py-2 rounded-lg border text-[11px] leading-snug transition
                            ${selTitle === t
                              ? 'border-indigo-500/70 bg-indigo-600/15 text-white'
                              : 'border-gray-800/50 bg-gray-900/30 text-gray-400 hover:border-gray-700 hover:text-gray-200'}`}>
                          <span className="text-gray-600 mr-1">{i + 1}.</span>{t}
                        </button>
                      ))}
                    </div>
                    {selTitle && (
                      <p className="text-[9px] text-emerald-400 mt-1.5 flex items-center gap-1">
                        <Copy className="w-2.5 h-2.5" /> Copied: {selTitle.slice(0, 60)}…
                      </p>
                    )}
                  </div>
                )}

                {/* ── Clip Preview ── */}
                <div className="border border-gray-800/50 rounded-xl overflow-hidden">
                  <div className="px-2.5 py-1.5 bg-gray-900/60 border-b border-gray-800/40 flex items-center gap-2">
                    <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest">CLIP PREVIEW</span>
                    <span className="text-[9px] text-indigo-300 font-mono">{cand?.start_time}  (+16s)</span>
                    <span className="text-[9px] text-emerald-400 ml-auto italic font-medium">
                      {selVideo?.is_youtube ? '🔴 YouTube Cloud' : '⚡ GPU native'}
                    </span>
                    <span className="text-[8px] text-gray-600 border border-gray-800 rounded px-1 py-0.5 ml-1 cursor-help"
                      title="Keyboard shortcuts&#10;Space → play/pause&#10;↑↓ → switch candidate&#10;E → cut clip&#10;Enter → next video">
                      ⌨ shortcuts
                    </span>
                  </div>
                  {(() => {
                    const parts = (cand?.start_time || '00:00:00').split(':').map(Number);
                    const startSec = parts.length === 3
                      ? parts[0] * 3600 + parts[1] * 60 + parts[2]
                      : parts[0] * 60 + (parts[1] || 0);
                    const isStory = analysisMode === 'story' && cand?.clip_duration && cand.clip_duration !== 16;
                    const baseDur = isStory ? cand.clip_duration : (Number(clipDuration) || 16);
                    const effDur = Math.max(1, baseDur + trimEnd - trimStart);
                    const effStartSec = Math.max(0, startSec + trimStart);

                    if (selVideo?.is_youtube) {
                      const ytMatch = (selVideo.path || '').match(/(?:v=|\/|be\/|embed\/|shorts\/)([a-zA-Z0-9_\-]{11})/);
                      const ytId = ytMatch ? ytMatch[1] : '';
                      return (
                        <div className="w-full bg-black flex items-center justify-center aspect-video" style={{ maxHeight: 220 }}>
                          {ytId ? (
                            <iframe
                              key={`${selVideo.path}|${selCand}|${effStartSec}|${effDur}`}
                              src={`https://www.youtube-nocookie.com/embed/${ytId}?start=${Math.floor(effStartSec)}&end=${Math.ceil(effStartSec + effDur)}&autoplay=1&rel=0`}
                              title="YouTube Highlight Preview"
                              className="w-full h-full border-0"
                              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                              allowFullScreen
                            />
                          ) : (
                            <p className="text-xs text-gray-500">Không tìm thấy Video ID</p>
                          )}
                        </div>
                      );
                    }

                    const previewSrc = `${API}/clip/stream_preview?path=${encodeURIComponent(selVideo.path)}&start=${effStartSec}&dur=${effDur}`;
                    return (
                      <video
                        key={`${selVideo.path}|${selCand}|${effStartSec}|${effDur}`}
                        controls
                        autoPlay
                        preload="auto"
                        src={previewSrc}
                        className="w-full bg-black"
                        style={{ maxHeight: 180 }}
                      />
                    );
                  })()}
                </div>


                {/* ???? CUT + Send to Edit ???? */}
                <div className="space-y-2 pt-1">
                  <button onClick={cutClip} disabled={cutBusy}
                    className="w-full py-2.5 rounded-xl bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white font-bold text-sm flex items-center justify-center gap-2 transition">
                    {cutBusy ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Scissors className="w-4 h-4" />}
                    {cutBusy ? 'Cutting…' : (() => {
                      const cand = selVideo?.candidates?.[selCand];
                      const isStory = analysisMode === 'story' && cand?.clip_duration && cand.clip_duration !== 16;
                      const base = isStory ? cand.clip_duration : (Number(clipDuration) || 16);
                      const eff = Math.max(1, base + trimEnd - trimStart);
                      return `✂️  CUT SELECTED CLIP  (${eff}s)`;
                    })()}
                  </button>

                  {lastCutPath && (
                    <div className="flex items-center gap-2 px-2 py-1.5 bg-emerald-900/20 border border-emerald-800/40 rounded-lg">
                      <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                      <span className="text-[9px] text-emerald-300 truncate flex-1">{lastCutPath.split(/[\\/]/).pop()}</span>
                    </div>
                  )}

                  <button onClick={sendToEdit}
                    disabled={!lastCutPath || !selTitle.trim()}
                    className="w-full py-2.5 rounded-xl bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white font-bold text-sm flex items-center justify-center gap-2 transition">
                    <Send className="w-4 h-4" />
                    Send to Edit &amp; Export
                  </button>

                  {!selTitle && lastCutPath && (
                    <p className="text-[9px] text-amber-400 text-center">👆 Select a title above first</p>
                  )}

                  <button onClick={sendAllCandidatesToEdit}
                    disabled={sendAllBusy || sendAllVideosBusy || !selVideo?.candidates?.length}
                    className="w-full py-2.5 rounded-xl bg-gradient-to-r from-purple-700 to-indigo-700 hover:from-purple-600 hover:to-indigo-600 disabled:opacity-40 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-purple-900/30 transition">
                    {sendAllBusy ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4 text-amber-300" />}
                    {sendAllBusy ? 'Đang cắt & chuyển cảnh video này…' : `⚡ CHUYỂN TẤT CẢ CẢNH VIDEO NÀY VÀO TAB 2 (${selVideo?.candidates?.length || 0})`}
                  </button>

                  <button onClick={sendAllVideosCandidatesToEdit}
                    disabled={sendAllVideosBusy || sendAllBusy || totalAllCandidates === 0}
                    className="w-full py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 via-teal-600 to-indigo-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-40 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-emerald-950/40 transition"
                    title="Cắt toàn bộ candidate của tất cả các video có trong danh sách">
                    {sendAllVideosBusy ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Scissors className="w-4 h-4 text-emerald-300" />}
                    {sendAllVideosBusy ? 'Đang cắt toàn bộ các video trong DS…' : `🎬 CẮT HẾT TẤT CẢ CANDIDATE CỦA CÁC VIDEO (${totalAllCandidates})`}
                  </button>
                </div>

              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center p-6">
                {selVideo.status === 'uploading' || selVideo.status === 'analyzing'
                  ? <><Sparkles className="w-10 h-10 text-indigo-500 animate-pulse" /><p className="text-indigo-300 text-sm">{selVideo.status === 'uploading' ? 'Uploading to Gemini…' : 'AI analyzing…'}</p></>
                  : selVideo.status === 'error'
                  ? <><AlertCircle className="w-10 h-10 text-red-500" /><p className="text-red-400 text-xs">{selVideo.error || 'Failed'}</p><button onClick={retryErrors} className="px-3 py-1.5 bg-red-700/60 hover:bg-red-600 rounded-lg text-white text-xs flex items-center gap-1"><RefreshCw className="w-3 h-3" />Retry</button></>
                  : <><Film className="w-10 h-10 text-gray-800" /><p className="text-gray-600 text-xs">Click ANALYZE ALL to find highlights</p></>}
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-center">
            <div><Film className="w-14 h-14 mx-auto mb-3 text-gray-800" /><p className="text-gray-600 text-sm">Select a video from the queue</p></div>
          </div>
        )}
      </div>

      {/* ???? Right: Activity Log ?????????????????????????????????????????????????????????????????????????????????????? */}
      <div className={`shrink-0 border-l border-gray-800/70 bg-[#0a0b12] flex flex-col transition-all ${showLog ? 'w-72' : 'w-0 overflow-hidden'}`}>
        <div className="px-3 py-2 border-b border-gray-800/40 flex items-center justify-between shrink-0">
          <span className="text-[9px] font-bold text-gray-500 uppercase tracking-widest flex items-center gap-2">
            <Terminal className="w-2.5 h-2.5" />Activity Log
            {errLogs > 0 && <span className="text-red-400 text-[8px]">{errLogs} ERR</span>}
          </span>
          <button onClick={() => setLogs([])} className="text-[9px] text-gray-700 hover:text-gray-400">Clear</button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-1.5 font-mono text-[9px] space-y-px">
          {logs.length === 0 ? <span className="text-gray-800">Waiting…</span>
            : logs.map((l, i) => (
              <div key={i} className={{
                error: 'text-red-400 bg-red-950/20 border-l border-red-700 pl-1',
                warn:  'text-amber-400',
                ok:    'text-emerald-400',
                dim:   'text-gray-700',
                info:  'text-gray-500',
              }[l.level] || 'text-gray-600'}>
                <span className="text-gray-800">[{l.timestamp}] </span>{l.text}
              </div>
            ))}
        </div>
      </div>
    </div>
  );

  // ── TAB ──
  // 2: Edit & Export ????????????????????????????????????????????????????????????????????????????????????????????????????
  const EditTab = () => {
    const st = editState;
    return (
      <div className="flex flex-1 overflow-hidden">

        {/* Left: Edit controls */}
        <div className="w-60 shrink-0 border-r border-gray-800/70 bg-[#0d0e17] flex flex-col">
          <div className="px-3 py-2 border-b border-gray-800/50 shrink-0">
            <span className="text-[9px] font-bold text-gray-500 uppercase tracking-widest">Edit Settings</span>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {selEditIdx < 0 ? <p className="text-[9px] text-gray-700 text-center py-4">Select a clip from the Edit Queue →</p> : <>

              {/* F2: Edit Style Presets */}
              <div className="mb-2 p-2 rounded-lg bg-gray-900/60 border border-gray-800/50">
                <div className="flex items-center gap-1 mb-1.5">
                  <span className="text-[8px] font-bold text-indigo-400 uppercase tracking-widest flex-1">🎨 Style Presets</span>
                  <span className="text-[7px] text-gray-600 italic">Ctrl+Z = undo</span>
                </div>
                <div className="flex gap-1 mb-1.5">
                  <input value={editPresetName} onChange={e => setEditPresetName(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && saveEditPreset()}
                    placeholder="Tên preset…"
                    className="flex-1 bg-gray-800 border border-gray-700/50 rounded px-1.5 py-0.5 text-[8px] text-white placeholder-gray-600 outline-none focus:border-indigo-500/60" />
                  <button onClick={saveEditPreset}
                    className="px-2 py-0.5 bg-indigo-700 hover:bg-indigo-600 rounded text-[8px] text-white font-bold transition"
                    title="Lưu settings hiện tại thành preset">
                    Lưu
                  </button>
                </div>
                {editPresets.length === 0 ? (
                  <p className="text-[7px] text-gray-700 text-center py-1">Chưa có preset nào</p>
                ) : (
                  <div className="flex flex-col gap-0.5 max-h-24 overflow-y-auto">
                    {editPresets.map(name => (
                      <div key={name} className="flex items-center gap-1 group">
                        <button onClick={() => loadEditPreset(name)}
                          className="flex-1 text-left px-1.5 py-0.5 rounded text-[8px] text-gray-300 bg-gray-800/60 hover:bg-indigo-900/50 hover:text-indigo-200 transition truncate"
                          title={`Load: ${name}`}>
                          📋 {name}
                        </button>
                        <button onClick={() => delEditPreset(name)}
                          className="opacity-0 group-hover:opacity-100 w-4 h-4 flex items-center justify-center rounded-full bg-red-900/60 hover:bg-red-600 text-red-400 hover:text-white text-[8px] font-bold transition"
                          title="Xóa preset">×</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Sync controls — apply current state to all or just current */}
              <div className="flex gap-1 mb-2">
                <span className="flex-1 text-[8px] text-gray-600 self-center">Editing: #{selEditIdx + 1}</span>
                <button onClick={syncAllState}
                  className="px-2 py-1 bg-violet-900/50 hover:bg-violet-700/60 border border-violet-700/40 rounded text-[8px] text-violet-300 transition"
                  title={selEditIdxs.size > 1 ? `Sync settings to ${selEditIdxs.size} selected clips only` : 'Copy current clip settings to ALL clips in queue'}>
                  ↻ {selEditIdxs.size > 1 ? `Sync to ${selEditIdxs.size} clips` : 'Sync to All'}
                </button>
              </div>

              <Section id="section-title" title="Title & Typography" icon={<Type className="w-3 h-3 text-amber-400" />} active={selectedLayer?.type === 'title'} defaultOpen>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[9px] text-gray-500">Title</label>
                    <button
                      onClick={() => regenTitle(selEditIdx)}
                      disabled={regenningIdx === selEditIdx || selEditIdx < 0}
                      className="text-[8px] text-amber-300 hover:text-amber-200 flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-950/60 hover:bg-amber-900/70 border border-amber-800/60 transition disabled:opacity-40 font-medium"
                      title="Tạo lại tiêu đề bằng Gemini AI (Xoay key & Tự động Retry)"
                    >
                      {regenningIdx === selEditIdx ? (
                        <>
                          <RefreshCw className="w-2.5 h-2.5 animate-spin" /> Đang tạo…
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-2.5 h-2.5 text-amber-400" /> Tạo lại AI Title
                        </>
                      )}
                    </button>
                  </div>
                  <textarea value={currentEditItem?.title || ''}
                    onChange={e => setEditQueue(prev => prev.map((item, i) => i === selEditIdx ? { ...item, title: e.target.value } : item))}
                    rows={2} className="w-full bg-gray-900 border border-gray-800 rounded-lg p-1.5 text-[10px] text-white outline-none focus:border-indigo-500 resize-none" />
                  
                  {currentEditItem?.title_error && (
                    <div className="mt-1 p-1.5 bg-red-950/60 border border-red-800/60 rounded flex items-center justify-between gap-2">
                      <span className="text-[8px] text-red-300 truncate" title={currentEditItem.title_error_msg}>
                        ⚠️ AI tạo tiêu đề thất bại: {currentEditItem.title_error_msg || 'Quota / Lỗi API'}
                      </span>
                      <button
                        onClick={() => regenTitle(selEditIdx)}
                        disabled={regenningIdx === selEditIdx}
                        className="px-2 py-0.5 bg-red-800 hover:bg-red-700 text-white rounded text-[8px] font-bold shrink-0 flex items-center gap-1 transition"
                      >
                        {regenningIdx === selEditIdx ? <RefreshCw className="w-2.5 h-2.5 animate-spin" /> : '🔄 Thử lại ngay'}
                      </button>
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  <div>
                  <label className="text-[9px] text-gray-500 block mb-0.5">Font</label>
                  <FontPicker value={st.font_name} onChange={v => patchEdit({ font_name: v })} />
                </div>
                  <Slider label="Size" value={st.font_size} min={18} max={100} onChange={v => patchEdit({ font_size: v })} unit="px" />
                </div>
                <div className="flex gap-2">
                  <Toggle label="Bold" value={st.font_bold} onChange={v => patchEdit({ font_bold: v })} />
                  <Toggle label="Italic" value={st.font_italic} onChange={v => patchEdit({ font_italic: v })} />
                  <Toggle label="AA" value={st.title_uppercase || false} onChange={v => patchEdit({ title_uppercase: v })} />
                </div>
                <div className="flex gap-1">
                  {[['left', <AlignLeft className="w-3 h-3" />], ['center', <AlignCenter className="w-3 h-3" />], ['right', <AlignRight className="w-3 h-3" />]].map(([v, ico]) => (
                    <button key={v} onClick={() => patchEdit({ text_align: v })}
                      className={`flex-1 py-1 rounded flex items-center justify-center transition text-xs ${st.text_align === v ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-500'}`}>{ico}</button>
                  ))}
                </div>
                <ColorPicker label="Text Color" value={st.text_color_hex} onChange={v => patchEdit({ text_color_hex: v, text_color: 'custom' })} presets={['#ffffff', '#ffff00', '#ff4444']} />
                <ColorPicker label="Box BG" value={st.box_bg_color_hex} onChange={v => patchEdit({ box_bg_color_hex: v, box_bg_color: 'custom' })} presets={['#222222', '#000000', '#1a1a2e', '#7c3aed', '#dc2626', '#FFFFFF']} />
                <Slider label="Box Opacity" value={st.box_opacity} min={0} max={100} onChange={v => patchEdit({ box_opacity: v })} unit="%" />

                {/* Box mode: CapCut (Hút chân không li??n khối) vs Badges (Từng thanh) vs Frame (Hộp vuông) */}
                {st.box_opacity > 0 && (
                  <div>
                    <p className="text-[8px] text-gray-500 mb-1">Kiểu hộp nền</p>
                    <div className="grid grid-cols-3 gap-1">
                      {[
                        ['capcut', '✨ CapCut'],
                        ['badges', '🏷️ Từng thanh'],
                        ['frame', '⬜ Khung hộp'],
                      ].map(([v, lbl]) => (
                        <button key={v} onClick={() => patchEdit({ box_mode: v })}
                          className={`py-1 rounded text-[8px] font-medium transition text-center ${
                            (st.box_mode || 'capcut') === v
                              ? 'bg-indigo-600 text-white shadow'
                              : 'bg-gray-800 text-gray-400 hover:text-gray-200'
                          }`}>{lbl}</button>
                      ))}
                    </div>
                    {((st.box_mode || 'capcut') === 'capcut' || st.box_mode === 'badges') && (
                      <Slider label="Bo góc" value={st.box_radius ?? 40} min={0} max={80} onChange={v => patchEdit({ box_radius: v })} unit="px" />
                    )}
                  </div>
                )}

                {/* Text Stroke Toggle & Controls */}
                <div className="flex items-center justify-between py-1 border-t border-gray-800/50 mt-1">
                  <span className="text-[9px] text-gray-300 font-semibold">Viền chữ (Text Stroke)</span>
                  <Toggle label="" value={st.stroke_enabled !== false && (st.stroke_width ?? 0) > 0} 
                          onChange={v => patchEdit({ stroke_enabled: v, stroke_width: v ? (st.stroke_width > 0 ? st.stroke_width : 2) : 0 })} />
                </div>
                {(st.stroke_enabled !== false && (st.stroke_width ?? 0) > 0) && (
                  <>
                    <Slider label="Stroke Size" value={st.stroke_width || 2} min={1} max={10} onChange={v => patchEdit({ stroke_width: v, stroke_enabled: true })} unit="px" />
                    <ColorPicker label="Stroke Color" value={st.stroke_color_hex || '#000000'} onChange={v => patchEdit({ stroke_color_hex: v })} presets={['#000000', '#ffffff', '#ff0000', '#00ff00']} />
                  </>
                )}

                <Slider label="Letter Spacing" value={st.letter_spacing ?? 0} min={-5} max={20} step={1} onChange={v => patchEdit({ letter_spacing: v })} unit="px" />
                <Slider label="Line Height" value={st.line_height ?? 1.2} min={0.8} max={2.5} step={0.05} onChange={v => patchEdit({ line_height: v })} />
                <Slider label="Title Y" value={st.text_y} min={0} max={1800} onChange={v => patchEdit({ text_y: v })} unit="px" />
                <Slider label="Wrap %" value={st.title_wrap_pct} min={0.3} max={1.0} step={0.05} onChange={v => patchEdit({ title_wrap_pct: v })} />
              </Section>

              {/* ── Custom Audio & Voiceover Section ── */}
              <Section title="Âm thanh & Lồng tiếng" icon={<Volume2 className="w-3 h-3 text-emerald-400" />} defaultOpen>
                <input
                  type="file"
                  ref={audioFileInputRef}
                  onChange={handleAudioUpload}
                  accept="audio/*,video/*"
                  className="hidden"
                />

                {!st.custom_audio_path ? (
                  <div className="text-center py-2.5 border border-dashed border-gray-800 rounded-lg bg-gray-900/30 hover:border-emerald-700/60 hover:bg-emerald-950/20 transition">
                    <Music className="w-4 h-4 mx-auto mb-1 text-emerald-400/60" />
                    <p className="text-[8px] text-gray-400 mb-1.5">Chưa có audio ngoài (Dùng tiếng gốc)</p>
                    <button
                      onClick={() => audioFileInputRef.current?.click()}
                      className="px-2.5 py-1 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white rounded text-[8px] font-bold inline-flex items-center gap-1 shadow transition">
                      <Plus className="w-2.5 h-2.5" /> + Thêm Audio / Video 1
                    </button>
                  </div>
                ) : (
                  <div className="space-y-1.5 bg-gray-900/60 border border-emerald-800/40 rounded-lg p-2">
                    {/* Audio Header: Name & Remove */}
                    <div className="flex items-center justify-between gap-1">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <div className="w-5 h-5 rounded bg-emerald-950/80 border border-emerald-600/50 flex items-center justify-center shrink-0">
                          <Volume2 className="w-2.5 h-2.5 text-emerald-300" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-[8px] font-bold text-emerald-200 truncate">{st.custom_audio_name || 'custom_audio.m4a'}</p>
                          <p className="text-[7px] text-emerald-500 font-mono">{st.custom_audio_dur}s</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={() => audioFileInputRef.current?.click()}
                          className="px-1.5 py-0.5 rounded text-[7px] font-medium bg-gray-800 hover:bg-gray-700 text-gray-300 transition"
                          title="Đổi audio khác">
                          Đổi
                        </button>
                        <button
                          onClick={() => patchEdit({ custom_audio_path: '', custom_audio_name: '', custom_audio_url: '', custom_audio_dur: 0, orig_volume: 100 })}
                          className="p-1 rounded text-red-400 hover:bg-red-950/50 hover:text-red-300 transition"
                          title="Gỡ bỏ audio ngoài">
                          <Trash2 className="w-2.5 h-2.5" />
                        </button>
                      </div>
                    </div>

                    {/* Direct timeline trimming info */}
                    <div className="p-2 rounded-lg bg-emerald-950/40 border border-emerald-800/50 text-[8px] space-y-1">
                      <div className="flex items-center justify-between text-emerald-300 font-semibold">
                        <span className="flex items-center gap-1">✂️ Kéo cắt trên Timeline</span>
                        <span className="text-[7px] font-mono bg-emerald-900/60 text-emerald-200 px-1 py-0.5 rounded">Tự động bù màn đen</span>
                      </div>
                      <p className="text-gray-400 text-[7.5px] leading-relaxed">
                        Kéo tay nắm 2 đầu Audio/Video trên thanh Timeline bên dưới để thu gọn đầu/đuôi. Audio dài hơn video sẽ tự động giữ màn đen khi render.
                      </p>
                      <div className="flex items-center justify-between text-[7px] text-gray-400 font-mono pt-1 border-t border-emerald-900/40">
                        <span>Cắt đầu: {(st.custom_audio_trim_start || 0).toFixed(1)}s</span>
                        <span>Độ dài: {(st.custom_audio_trim_dur > 0 ? st.custom_audio_trim_dur : st.custom_audio_dur || 0).toFixed(1)}s</span>
                        {((st.custom_audio_trim_start || 0) > 0 || (st.custom_audio_trim_dur > 0 && st.custom_audio_trim_dur < (st.custom_audio_dur || 0)) || (st.custom_audio_offset || 0) !== 0) && (
                          <button
                            onClick={() => patchEdit({ custom_audio_trim_start: 0, custom_audio_trim_dur: st.custom_audio_dur, custom_audio_offset: 0 })}
                            className="text-amber-400 hover:text-amber-300 underline text-[7px]">
                            ↺ Đặt lại
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Sliders */}
                    <div className="space-y-1 pt-1 border-t border-gray-800/60">
                      <Slider
                        label="Tiếng video gốc"
                        value={st.orig_volume ?? 0}
                        min={0}
                        max={100}
                        onChange={v => patchEdit({ orig_volume: v })}
                        unit="%"
                      />
                      <Slider
                        label="Tiếng lồng ngoài"
                        value={st.custom_volume ?? 100}
                        min={0}
                        max={200}
                        onChange={v => patchEdit({ custom_volume: v })}
                        unit="%"
                      />
                      <Slider
                        label="Độ lệch bắt đầu (Offset)"
                        value={st.custom_audio_offset ?? 0}
                        min={-30}
                        max={30}
                        step={0.1}
                        onChange={v => patchEdit({ custom_audio_offset: v })}
                        unit="s"
                      />
                    </div>
                  </div>
                )}
              </Section>

              {/* ── Multitrack Overlays  ── */}
              <Section id="section-multitrack" title="Lớp phủ Đa tầng (Multitrack)" icon={<Layers className="w-3 h-3 text-pink-400" />} active={selectedLayer?.type === 'overlay'} defaultOpen>
                <div className="flex items-center justify-between gap-1 mb-2">
                  <span className="text-[9px] text-gray-400">Ảnh / Video Overlays</span>
                  <input
                    type="file"
                    ref={overlayFileInputRef}
                    onChange={handleOverlayUpload}
                    accept="image/*,video/*"
                    className="hidden"
                  />
                  <button
                    onClick={() => overlayFileInputRef.current?.click()}
                    className="px-2 py-1 bg-gradient-to-r from-pink-600 to-rose-600 hover:from-pink-500 hover:to-rose-500 text-white rounded text-[8px] font-bold flex items-center gap-1 shadow transition">
                    <Plus className="w-2.5 h-2.5" /> Thêm Layer
                  </button>
                </div>

                {/* Drag-and-drop zone: accepts files from desktop AND image URLs dragged from browser */}
                <div
                  onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); e.currentTarget.classList.add('ring-2','ring-pink-500'); }}
                  onDragLeave={(e) => { e.currentTarget.classList.remove('ring-2','ring-pink-500'); }}
                  onDrop={async (e) => {
                    e.preventDefault(); e.stopPropagation();
                    e.currentTarget.classList.remove('ring-2','ring-pink-500');
                    if (selEditIdx < 0) return;

  // ── Case ──
  // 1: Files dragged from OS file explorer or local disk
                    const files = Array.from(e.dataTransfer.files || []).filter(f => f.type.startsWith('image/') || f.type.startsWith('video/'));
                    if (files.length > 0) {
                      for (const file of files) {
                        const formData = new FormData();
                        formData.append('file', file);
                        try {
                          const res = await fetch(`${API}/overlay/upload`, { method: 'POST', body: formData });
                          if (!res.ok) throw new Error('Upload failed');
                          const data = await res.json();
                          const newOvl = { id: data.id, name: data.name, path: data.path, url: data.url, type: data.type,
                            x: Math.max(0, 540 - Math.round(Math.min(400, data.w||300)/2)),
                            y: Math.max(0, 960 - Math.round(Math.min(400, data.h||300)/2)),
                            w: Math.min(600, data.w||300), h: Math.min(600, data.h||300),
                            opacity: 100, rotation: 0, start_time: 0, end_time: 0,
                            remove_bg: false, remove_bg_path: '', remove_bg_url: '', enabled: true };
                          const cur = editState?.overlays || [];
                          patchEdit({ overlays: [...cur, newOvl] });
                          setSelOverlayIdx(cur.length);
                        } catch(err) { alert('Lỗi upload: ' + err.message); }
                      }
                      return;
                    }

  // ── Case ──
  // 2: Image URL dragged from browser (Google Images, etc.)
                    const imgUrl = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain');
                    if (imgUrl && (imgUrl.startsWith('http') || imgUrl.startsWith('blob:'))) {
                      try {
  // ── Fetch ──
                        const uploadRes = await fetch(`${API}/overlay/upload_url`, {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ url: imgUrl }),
                        });
                        if (!uploadRes.ok) throw new Error('Fetch URL failed');
                        const data = await uploadRes.json();
                        const newOvl = { id: data.id, name: data.name, path: data.path, url: data.url, type: data.type,
                          x: Math.max(0, 540 - Math.round(Math.min(400, data.w||300)/2)),
                          y: Math.max(0, 960 - Math.round(Math.min(400, data.h||300)/2)),
                          w: Math.min(600, data.w||300), h: Math.min(600, data.h||300),
                          opacity: 100, rotation: 0, start_time: 0, end_time: 0,
                          remove_bg: false, remove_bg_path: '', remove_bg_url: '', enabled: true };
                        const cur = editState?.overlays || [];
                        patchEdit({ overlays: [...cur, newOvl] });
                        setSelOverlayIdx(cur.length);
                      } catch(err) { alert('Lỗi tải ảnh từ URL: ' + err.message); }
                    }
                  }}
                  className="rounded-lg transition-all duration-150">

                {/* ── Overlay List ── */}
                {(!editState?.overlays || editState.overlays.length === 0) ? (
                  <div className="text-center py-3 border border-dashed border-gray-800 rounded-lg bg-gray-900/30 hover:border-pink-700/60 hover:bg-pink-950/20 transition">
                    <Layers className="w-5 h-5 mx-auto mb-1 text-gray-600 opacity-60" />
                    <p className="text-[8px] text-gray-500">Chưa có lớp phủ nào</p>
                    <p className="text-[7px] text-gray-600">Kéo thả ảnh vào đây hoặc bấm "+ Thêm Layer"</p>
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    {editState.overlays.map((ovl, idx) => {
                      const isSel = selOverlayIdx === idx;
                      const isImg = ovl.type !== 'video';
                      return (
                        <div
                          key={ovl.id || idx}
                          onClick={() => { setSelOverlayIdx(idx); setSelBlurBoxIdx(-1); }}
                          className={`p-1.5 rounded-lg border transition cursor-pointer ${
                            isSel
                              ? 'bg-pink-950/40 border-pink-500/80 ring-1 ring-pink-500/50 shadow-md'
                              : 'bg-gray-900/60 border-gray-800/60 hover:bg-gray-800/40'
                          }`}>
                          <div className="flex items-center gap-1.5">
                            {/* ── Thumbnail ── */}
                            <div className="w-7 h-7 rounded bg-black/80 border border-gray-700/50 flex items-center justify-center overflow-hidden shrink-0">
                              {isImg ? (
                                <img
                                  src={toAssetUrl(ovl.remove_bg && ovl.remove_bg_url ? ovl.remove_bg_url : ovl.url)}
                                  alt=""
                                  className="w-full h-full object-contain"
                                />
                              ) : (
                                <Film className="w-3.5 h-3.5 text-pink-400" />
                              )}
                            </div>

                            {/* Name & Badge */}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1">
                                <span className="text-[9px] font-bold text-gray-200 truncate">{ovl.name || `Layer #${idx + 1}`}</span>
                                {ovl.remove_bg && (
                                  <span className="text-[6px] font-bold text-emerald-400 bg-emerald-950/80 border border-emerald-500/40 px-1 py-0.2 rounded">
                                    NO-BG
                                  </span>
                                )}
                              </div>
                              <p className="text-[7px] text-gray-500">{isImg ? 'Ảnh (Image)' : 'Video'} • {ovl.w}×{ovl.h}px • {ovl.opacity ?? 100}%</p>
                            </div>

                            {/* ── Actions ── */}
                            <div className="flex items-center gap-1 shrink-0">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  const updated = editState.overlays.map((o, i) => i === idx ? { ...o, enabled: !(o.enabled ?? true) } : o);
                                  patchEdit({ overlays: updated });
                                }}
                                className={`p-1 rounded text-[8px] transition ${ovl.enabled !== false ? 'text-cyan-400 hover:bg-cyan-950/50' : 'text-gray-600 hover:bg-gray-800'}`}
                                title={ovl.enabled !== false ? 'Ẩn layer' : 'Hiện layer'}>
                                <Eye className="w-2.5 h-2.5" />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  const updated = editState.overlays.filter((_, i) => i !== idx);
                                  patchEdit({ overlays: updated });
                                  if (selOverlayIdx === idx) setSelOverlayIdx(-1);
                                }}
                                className="p-1 rounded text-red-400 hover:bg-red-950/50 hover:text-red-300 transition"
                                title="Xóa layer">
                                <Trash2 className="w-2.5 h-2.5" />
                              </button>
                            </div>
                          </div>

                          {/* ── Expanded Controls when Selected ── */}
                          {isSel && (
                            <div className="mt-2 pt-2 border-t border-gray-800/80 space-y-2" onClick={e => e.stopPropagation()}>
                              {/* ── BiRefNet Auto BG Removal Button ── */}
                              <div className="bg-gradient-to-r from-violet-950/50 to-pink-950/50 p-2 rounded-lg border border-pink-500/30">
                                <div className="flex items-center justify-between mb-1.5">
                                  <span className="text-[8px] font-bold text-pink-300 flex items-center gap-1">
                                    <Scissors className="w-2.5 h-2.5 text-pink-400" /> Tách N??n AI (BiRefNet SOTA)
                                  </span>
                                  {ovl.remove_bg && (
                                    <span className="text-[6px] text-emerald-400 font-bold bg-emerald-950 px-1 py-0.5 rounded border border-emerald-500/30">
                                      ✓ ??Ã T??CH NỀN
                                    </span>
                                  )}
                                </div>

                                <div className="flex gap-1">
                                  <button
                                    disabled={isRemovingBg}
                                    onClick={() => handleRemoveBg(idx)}
                                    className={`flex-1 py-1 rounded text-[8px] font-bold flex items-center justify-center gap-1 transition ${
                                      isRemovingBg
                                        ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                                        : 'bg-gradient-to-r from-violet-600 to-pink-600 hover:from-violet-500 hover:to-pink-500 text-white shadow-md'
                                    }`}>
                                    {isRemovingBg ? (
                                      <><RefreshCw className="w-2.5 h-2.5 animate-spin" /> Đang tách nền GPU...</>
                                    ) : (
                                      <><Sparkles className="w-2.5 h-2.5 text-amber-300" /> {ovl.remove_bg ? 'Tách lại nền' : 'Tách nền tự động'}</>
                                    )}
                                  </button>

                                  {ovl.remove_bg && (
                                    <button
                                      onClick={() => {
                                        const updated = editState.overlays.map((o, i) => i === idx ? { ...o, remove_bg: !o.remove_bg } : o);
                                        patchEdit({ overlays: updated });
                                      }}
                                      className="px-2 py-1 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-[8px] transition font-medium">
                                      {ovl.remove_bg ? 'Dùng ảnh gốc' : 'Dùng cutout'}
                                    </button>
                                  )}
                                </div>
                              </div>

                              {/* Sliders: Opacity, Scale, Rotate */}
                              <Slider
                                label="Độ mờ (Opacity)"
                                value={ovl.opacity ?? 100}
                                min={10}
                                max={100}
                                onChange={v => {
                                  const updated = editState.overlays.map((o, i) => i === idx ? { ...o, opacity: v } : o);
                                  patchEdit({ overlays: updated });
                                }}
                                unit="%"
                              />

                              <div className="grid grid-cols-2 gap-1.5">
                                <Slider
                                  label="Width"
                                  value={ovl.w}
                                  min={30}
                                  max={1080}
                                  onChange={v => {
                                    const updated = editState.overlays.map((o, i) => i === idx ? { ...o, w: v } : o);
                                    patchEdit({ overlays: updated });
                                  }}
                                  unit="px"
                                />
                                <Slider
                                  label="Height"
                                  value={ovl.h}
                                  min={30}
                                  max={1920}
                                  onChange={v => {
                                    const updated = editState.overlays.map((o, i) => i === idx ? { ...o, h: v } : o);
                                    patchEdit({ overlays: updated });
                                  }}
                                  unit="px"
                                />
                              </div>

                              <Slider
                                label="Xoay (Rotation)"
                                value={ovl.rotation ?? 0}
                                min={-180}
                                max={180}
                                onChange={v => {
                                  const updated = editState.overlays.map((o, i) => i === idx ? { ...o, rotation: v } : o);
                                  patchEdit({ overlays: updated });
                                }}
                                unit="°"
                              />

                              {/* ???? Timeline Track (Start / End Time & Quick Presets) ???? */}
                              <div className="p-2 rounded-lg bg-gray-950/80 border border-gray-800/80 space-y-2">
                                <div className="flex items-center justify-between">
                                  <span className="text-[8px] font-bold text-gray-300 flex items-center gap-1">
                                    <span className="text-pink-400">⏱️</span> Timeline Track (Thời gian)
                                  </span>
                                  <span className={`text-[7px] font-bold px-1.5 py-0.5 rounded ${
                                    (ovl.start_time || 0) === 0 && (ovl.end_time || 0) === 0
                                      ? 'bg-indigo-950/80 text-indigo-300 border border-indigo-500/30'
                                      : 'bg-amber-950/80 text-amber-300 border border-amber-500/30'
                                  }`}>
                                    {(ovl.start_time || 0) === 0 && (ovl.end_time || 0) === 0
                                      ? 'Toàn bộ clip'
                                      : `${(ovl.start_time || 0).toFixed(1)}s ➔ ${(ovl.end_time || 0) > 0 ? (ovl.end_time || 0).toFixed(1) + 's' : 'Hết clip'}`}
                                  </span>
                                </div>

                                {/* ── Visual Mini Track Bar ── */}
                                <div
                                  className="relative h-4 bg-black rounded border border-gray-800 overflow-hidden cursor-pointer"
                                  title="Click để nhảy tới vị trí trên timeline"
                                  onClick={(e) => {
                                    const rect = e.currentTarget.getBoundingClientRect();
                                    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                                    const newT = pct * (duration || 16);
                                    setCurrentTime(newT);
                                    if (videoRef.current) videoRef.current.currentTime = newT;
                                  }}>
                                  {/* ── Active Range Highlight ── */}
                                  {(() => {
                                    const totalDur = duration || 16;
                                    const st = Math.max(0, Math.min(totalDur, ovl.start_time || 0));
                                    const et = (ovl.end_time && ovl.end_time > 0) ? Math.min(totalDur, ovl.end_time) : totalDur;
                                    const leftPct = (st / totalDur) * 100;
                                    const widthPct = Math.max(2, ((et - st) / totalDur) * 100);
                                    return (
                                      <div
                                        className="absolute top-0 bottom-0 bg-gradient-to-r from-pink-500 to-rose-500 opacity-80 border-x-2 border-white flex items-center justify-center shadow-inner"
                                        style={{ left: `${leftPct}%`, width: `${widthPct}%` }}>
                                        <span className="text-[6px] font-bold text-white tracking-tighter truncate px-0.5 select-none">
                                          {st.toFixed(0)}s - {et.toFixed(0)}s
                                        </span>
                                      </div>
                                    );
                                  })()}
                                  {/* ── Playhead Indicator ── */}
                                  <div
                                    className="absolute top-0 bottom-0 w-0.5 bg-cyan-300 shadow-sm pointer-events-none z-10"
                                    style={{ left: `${((currentTime || 0) / (duration || 16)) * 100}%` }}
                                  />
                                </div>

                                {/* Precise Numeric Inputs & Get Playhead Button */}
                                <div className="grid grid-cols-2 gap-1.5">
                                  <div>
                                    <label className="text-[7px] text-gray-400 block mb-0.5">Bắt đầu (Start time)</label>
                                    <div className="flex items-center gap-1">
                                      <input
                                        type="number"
                                        min={0}
                                        max={duration || 16}
                                        step={0.5}
                                        value={ovl.start_time ?? 0}
                                        onChange={e => {
                                          const val = Math.max(0, parseFloat(e.target.value) || 0);
                                          const updated = editState.overlays.map((o, i) => i === idx ? { ...o, start_time: val } : o);
                                          patchEdit({ overlays: updated });
                                        }}
                                        className="w-full bg-black/60 border border-gray-800 rounded px-1.5 py-0.5 text-[9px] text-white font-mono"
                                      />
                                      <button
                                        type="button"
                                        onClick={() => {
                                          const updated = editState.overlays.map((o, i) => i === idx ? { ...o, start_time: parseFloat(currentTime.toFixed(1)) } : o);
                                          patchEdit({ overlays: updated });
                                        }}
                                        className="px-1 py-0.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-[7px] shrink-0 font-medium"
                                        title="Lấy thời gian hiện tại của Playhead">
                                        📍 Lấy
                                      </button>
                                    </div>
                                  </div>

                                  <div>
                                    <label className="text-[7px] text-gray-400 block mb-0.5">Kết thúc (0 = hết clip)</label>
                                    <div className="flex items-center gap-1">
                                      <input
                                        type="number"
                                        min={0}
                                        max={duration || 16}
                                        step={0.5}
                                        value={ovl.end_time ?? 0}
                                        onChange={e => {
                                          const val = Math.max(0, parseFloat(e.target.value) || 0);
                                          const updated = editState.overlays.map((o, i) => i === idx ? { ...o, end_time: val } : o);
                                          patchEdit({ overlays: updated });
                                        }}
                                        className="w-full bg-black/60 border border-gray-800 rounded px-1.5 py-0.5 text-[9px] text-white font-mono"
                                      />
                                      <button
                                        type="button"
                                        onClick={() => {
                                          const updated = editState.overlays.map((o, i) => i === idx ? { ...o, end_time: parseFloat(currentTime.toFixed(1)) } : o);
                                          patchEdit({ overlays: updated });
                                        }}
                                        className="px-1 py-0.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-[7px] shrink-0 font-medium"
                                        title="Lấy thời gian hiện tại của Playhead">
                                        📍 Lấy
                                      </button>
                                    </div>
                                  </div>
                                </div>

                                {/* ── Quick Presets Buttons ── */}
                                <div className="flex gap-1 pt-1 border-t border-gray-800/60">
                                  <button
                                    type="button"
                                    onClick={() => {
                                      const updated = editState.overlays.map((o, i) => i === idx ? { ...o, start_time: 0, end_time: 20 } : o);
                                      patchEdit({ overlays: updated });
                                    }}
                                    className="flex-1 py-1 bg-pink-950/60 hover:bg-pink-900/80 border border-pink-700/50 rounded text-[7px] font-bold text-pink-200 transition"
                                    title="Chỉ hiện trong 20 giây đầu tiên">
                                     ⏮ 20s Đầu
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      const updated = editState.overlays.map((o, i) => i === idx ? { ...o, start_time: 0, end_time: 10 } : o);
                                      patchEdit({ overlays: updated });
                                    }}
                                    className="flex-1 py-1 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded text-[7px] font-bold text-gray-200 transition"
                                    title="Chỉ hiện trong 10 giây đầu tiên">
                                     ⏩ 10s Đầu
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      const total = duration || 16;
                                      const updated = editState.overlays.map((o, i) => i === idx ? { ...o, start_time: Math.max(0, total - 20), end_time: total } : o);
                                      patchEdit({ overlays: updated });
                                    }}
                                    className="flex-1 py-1 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded text-[7px] font-bold text-gray-200 transition"
                                    title="Chỉ hiện trong 20 giây cuối clip">
                                     ⏭ 20s Cuối
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      const updated = editState.overlays.map((o, i) => i === idx ? { ...o, start_time: 0, end_time: 0 } : o);
                                      patchEdit({ overlays: updated });
                                    }}
                                    className="flex-1 py-1 bg-indigo-950/60 hover:bg-indigo-900/80 border border-indigo-700/50 rounded text-[7px] font-bold text-indigo-200 transition"
                                    title="Hiện xuyên suốt toàn bộ video">
                                     ▶▶ Toàn bộ
                                  </button>
                                </div>
                              </div>

                              {/* Layer Order (Z-Index) */}
                              <div className="flex items-center justify-between pt-1 border-t border-gray-800/60">
                                <span className="text-[8px] text-gray-400">Thứ tự layer:</span>
                                <div className="flex gap-1">
                                  <button
                                    disabled={idx === 0}
                                    onClick={() => {
                                      if (idx === 0) return;
                                      const arr = [...editState.overlays];
                                      [arr[idx - 1], arr[idx]] = [arr[idx], arr[idx - 1]];
                                      patchEdit({ overlays: arr });
                                      setSelOverlayIdx(idx - 1);
                                    }}
                                    className="px-1.5 py-0.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-30 rounded text-[7px] text-gray-300">
                                    ▲ Lên
                                  </button>
                                  <button
                                    disabled={idx === editState.overlays.length - 1}
                                    onClick={() => {
                                      if (idx === editState.overlays.length - 1) return;
                                      const arr = [...editState.overlays];
                                      [arr[idx], arr[idx + 1]] = [arr[idx + 1], arr[idx]];
                                      patchEdit({ overlays: arr });
                                      setSelOverlayIdx(idx + 1);
                                    }}
                                    className="px-1.5 py-0.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-30 rounded text-[7px] text-gray-300">
                                    ▼ Xuống
                                  </button>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
                </div>{/* ── end drag-drop zone ── */}
              </Section>

              {/* ── Blur Regions  ── */}
              <Section id="section-blur" title="Blur Regions" icon={<Layers className="w-3 h-3 text-cyan-400" />} active={selectedLayer?.type === 'blur_box'} defaultOpen>
                <p className="text-[9px] text-gray-400 mb-2 leading-tight">
                  Enable Draw Mode → click-drag on preview to add blur/delogo boxes.
                </p>

                {/* ── Mode toggle ── */}
                <div className="flex gap-1 mb-2">
                  {[['blur','🫧 Blur'],['delogo','🔍 Delogo'],['inpaint','🧹 Remove']].map(([m, lbl]) => (
                    <button key={m} onClick={() => setBoxMode(m)}
                      className={`flex-1 py-1 rounded text-[8px] font-bold transition ${
                        boxMode === m ? 'bg-cyan-700/80 text-cyan-100' : 'bg-gray-800 text-gray-500 hover:bg-gray-700'
                      }`}>
                      {lbl}
                    </button>
                  ))}
                </div>

                <div className="flex gap-1.5 mb-2">
                  <button onClick={() => setDrawMode(!drawMode)}
                    className={`flex-1 py-1.5 px-2 rounded-lg text-[9px] font-bold transition flex items-center justify-center gap-1.5 shadow ${
                      drawMode ? 'bg-indigo-600 text-white ring-2 ring-indigo-400/50' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                    }`}>
                    <span>🎯</span> {drawMode ? 'Draw Mode: ON' : 'Draw Mode: OFF'}
                  </button>
                  <button onClick={() => patchEdit({ blur_boxes: [] })}
                    className="px-2 py-1.5 bg-red-950/60 hover:bg-red-900/80 border border-red-800/40 rounded-lg text-[9px] font-bold text-red-300 transition flex items-center gap-1">
                    <Trash2 className="w-2.5 h-2.5" /> Clear All
                  </button>
                </div>

                {/* ── Auto-detect buttons ── */}
                <div className="flex gap-1 mb-2">
                  <button disabled={!currentEditItem || detectingLogo}
                    onClick={async () => {
                      if (!currentEditItem) return;
                      setDetectingLogo(true);
                      try {
                        const r = await post('/detect_logo', { clip_path: currentEditItem.clip_path });
                        if (r.bbox) {
                          patchEdit({ blur_boxes: [...(st.blur_boxes||[]), { ...r.bbox, id: Date.now(), mode: 'delogo' }] });
                        } else {
                          alert('ℹ️ No static logo detected in this clip.');
                        }
                      } catch { alert('Detection failed.'); }
                      finally { setDetectingLogo(false); }
                    }}
                    className="flex-1 py-1.5 bg-indigo-900/60 hover:bg-indigo-800/70 border border-indigo-700/40 rounded-lg text-[8px] font-bold text-indigo-300 disabled:opacity-40 disabled:cursor-not-allowed transition">
                    {detectingLogo ? '⏳ Detecting…' : '🔍 Auto Logo'}
                  </button>
                  <button disabled={!currentEditItem || detectingSubTracks}
                    onClick={async () => {
                      if (!currentEditItem || selEditIdx < 0) return;
                      setDetectingSubTracks(true);
                      try {
                        const res = await post('/detect_subtitle_tracks', { clip_path: currentEditItem.clip_path });
                        const r = await res.json();
                        if (r.tracks && r.tracks.length > 0) {
                          const newBoxes = r.tracks.map(tr => ({
                            id:         Date.now() + Math.random(),
                            x:          tr.bbox.x,
                            y:          tr.bbox.y,
                            w:          tr.bbox.w,
                            h:          tr.bbox.h,
                            mode:       boxMode || 'delogo',
                            start_time: tr.start,
                            end_time:   tr.end,
                          }));
                          const targetIdx = selEditIdx;
                          setEditQueue(prev => prev.map((item, i) => {
                            if (i !== targetIdx) return item;
                            const cur = item.state?.blur_boxes || [];
                            const updated = [...cur, ...newBoxes];
                            post('/edit_queue/update', { index: targetIdx, patch: { blur_boxes: updated } });
                            return { ...item, state: { ...item.state, blur_boxes: updated } };
                          }));
                          alert(`✨ AI RapidOCR: Detected ${r.tracks.length} timed subtitle segment(s)!`);
                        } else {
                          alert('ℹ️ No hardcoded subtitles detected.');
                        }
                      } catch (err) {
                        console.error('Subtitle detection error:', err);
                        alert('AI Subtitle detection failed. Please check terminal server window.');
                      }
                      finally { setDetectingSubTracks(false); }
                    }}
                    className="flex-1 py-1.5 bg-emerald-950/60 hover:bg-emerald-900/70 border border-emerald-700/40 rounded-lg text-[8px] font-bold text-emerald-300 disabled:opacity-40 disabled:cursor-not-allowed transition">
                    {detectingSubTracks ? '⏳ Scanning…' : '✨ Auto Subtitle'}
                  </button>
                </div>
                {/* AI sub-track detection ?? RapidOCR AI text detector */}
                <button disabled={!currentEditItem || detectingSubTracks}
                  onClick={async () => {
                    if (!currentEditItem || selEditIdx < 0) return;
                    setDetectingSubTracks(true);
                    try {
                      const res = await post('/detect_subtitle_tracks', { clip_path: currentEditItem.clip_path });
                      const r = await res.json();
                      if (r.tracks && r.tracks.length > 0) {
                        const newBoxes = r.tracks.map(tr => ({
                          id:         Date.now() + Math.random(),
                          x:          tr.bbox.x,
                          y:          tr.bbox.y,
                          w:          tr.bbox.w,
                          h:          tr.bbox.h,
                          mode:       boxMode || 'delogo',
                          start_time: tr.start,
                          end_time:   tr.end,
                        }));
                        const targetIdx = selEditIdx;
                        setEditQueue(prev => prev.map((item, i) => {
                          if (i !== targetIdx) return item;
                          const cur = item.state?.blur_boxes || [];
                          const updated = [...cur, ...newBoxes];
                          post('/edit_queue/update', { index: targetIdx, patch: { blur_boxes: updated } });
                          return { ...item, state: { ...item.state, blur_boxes: updated } };
                        }));
                        alert(`✨ AI RapidOCR: Detected ${r.tracks.length} timed subtitle segment(s)!`);
                      } else { alert('ℹ️ No hardcoded subtitles detected.'); }
                    } catch (err) {
                      console.error('Subtitle detection error:', err);
                      alert('AI Subtitle detection failed. Please check terminal server window.');
                    }
                    finally { setDetectingSubTracks(false); }
                  }}
                  className="w-full mb-2 py-1.5 bg-gradient-to-r from-indigo-900/80 to-purple-900/80 hover:from-indigo-800 hover:to-purple-800 border border-indigo-500/50 rounded-lg text-[9px] font-bold text-indigo-200 disabled:opacity-40 disabled:cursor-not-allowed transition shadow flex items-center justify-center gap-1.5">
                  {detectingSubTracks ? (
                    '🤖 AI RapidOCR Scanning...'
                  ) : (
                    <>
                      <span>✨ AI Auto Subtitle (RapidOCR)</span>
                      <span className={`text-[7px] px-1.5 py-0.2 rounded font-mono font-bold ${ocrInfo.is_gpu ? 'bg-emerald-950/90 text-emerald-300 border border-emerald-500/50' : 'bg-gray-800 text-gray-400'}`}>
                        {ocrInfo.is_gpu ? '⚡ GPU' : 'CPU'}
                      </span>
                    </>
                  )}
                </button>

                {/* ── Bulk Subtitle All Clips  ── */}
                {bulkSubJob ? (
                  <div className="w-full mb-2 rounded-lg border border-violet-600/50 bg-violet-950/60 px-2 py-1.5">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[8px] font-bold text-violet-300 flex items-center gap-1">
                        🤖 Bulk Subtitle
                        <span className="text-[7px] px-1 py-0.2 bg-emerald-950/80 text-emerald-300 border border-emerald-500/40 rounded font-mono">
                          {bulkSubJob.device || (ocrInfo.is_gpu ? 'GPU' : 'CPU')}
                        </span>
                        {bulkSubJob.status === 'done'
                          ? <span className="text-emerald-400">✅ Done!</span>
                          : <span className="animate-pulse">Scanning…</span>}
                      </span>
                      <span className="text-[8px] font-mono text-violet-400 tabular-nums flex items-center gap-1">
                        {bulkSubJob.workers && bulkSubJob.status !== 'done' && (
                          <span className="text-fuchsia-400" title="Concurrent workers">×{bulkSubJob.workers}</span>
                        )}
                        {bulkSubJob.done}/{bulkSubJob.total}
                      </span>
                    </div>
                    {/* ── Progress bar ── */}
                    <div className="w-full h-1 bg-gray-800 rounded-full overflow-hidden mb-1">
                      <div className="h-full bg-gradient-to-r from-violet-500 to-purple-400 transition-all duration-300 rounded-full"
                        style={{ width: `${bulkSubJob.total > 0 ? (bulkSubJob.done / bulkSubJob.total) * 100 : 0}%` }} />
                    </div>
                    {/* ── In-flight clips list ── */}
                    {(bulkSubJob.current_clips || []).length > 0 && (
                      <div className="space-y-0.5">
                        {(bulkSubJob.current_clips || []).map(name => (
                          <p key={name} className="text-[7px] text-gray-500 truncate">⚙ {name}</p>
                        ))}
                      </div>
                    )}
                    {Object.keys(bulkSubJob.errors || {}).length > 0 && (
                      <p className="text-[7px] text-red-400 mt-0.5">
                        ⚠ {Object.keys(bulkSubJob.errors).length} error(s)
                      </p>
                    )}
                    {bulkSubJob.status === 'done' && (
                      <div className="flex gap-1 mt-1">
                        <button onClick={() => {
  // ── Pull server-authoritative state ──
  // (incl. newly-added blur_boxes)
  // ── then force-replace so the current ──
  // clip's panel refreshes too.
                          fetch(`${API}/edit_queue`).then(r => r.json()).then(data => {
                            const serverClips = data.clips || [];
                            if (serverClips.length > 0) setEditQueue(serverClips);
                          }).catch(() => {});
                          setBulkSubJob(null);
                          clearInterval(bulkSubPollRef.current);
                        }} className="flex-1 text-[7px] py-0.5 rounded bg-emerald-900/60 text-emerald-300 hover:bg-emerald-800/80 transition">
                          ✅ Apply & Dismiss
                        </button>
                        <button onClick={() => {
                          setBulkSubJob(null);
                          clearInterval(bulkSubPollRef.current);
                        }} className="text-[7px] px-2 py-0.5 rounded bg-gray-800 text-gray-500 hover:text-gray-300 transition">
                          ✕
                        </button>
                      </div>
                    )}
                  </div>
                ) : (
                  <button
                    disabled={editQueue.length === 0 || detectingSubTracks}
                    onClick={async () => {
                      if (editQueue.length === 0) return;
                      const clipPaths = editQueue
                        .map(item => item.clip_path || item.path)
                        .filter(Boolean);
                      try {
                        const res = await post('/detect_subtitle_tracks_bulk', {
                          clip_paths: clipPaths,
                          box_mode: boxMode || 'delogo',
                        });
                        const { job_id } = await res.json();
                        setBulkSubJob({ jobId: job_id, status: 'running', total: clipPaths.length, done: 0, current_clip: '', errors: {} });
  // ── Poll every ──
  // 1.5s until done
                        bulkSubPollRef.current = setInterval(async () => {
                          try {
                            const s = await fetch(`${API}/detect_subtitle_tracks_bulk/${job_id}`).then(r => r.json());
                            setBulkSubJob(prev => prev?.jobId === job_id ? { ...s, jobId: job_id } : prev);
                            if (s.status === 'done') clearInterval(bulkSubPollRef.current);
                          } catch {/* ── keep polling ── */}
                        }, 1500);
                      } catch (err) {
                        alert('Bulk subtitle scan failed: ' + err.message);
                      }
                    }}
                    className="w-full mb-2 py-1.5 bg-gradient-to-r from-violet-900/80 to-fuchsia-900/80 hover:from-violet-800 hover:to-fuchsia-800 border border-violet-500/50 rounded-lg text-[9px] font-bold text-violet-200 disabled:opacity-40 disabled:cursor-not-allowed transition shadow flex items-center justify-center gap-1.5">
                    <span>🤖 Bulk Subtitle All ({editQueue.length} clips)</span>
                    <span className={`text-[7px] px-1.5 py-0.2 rounded font-mono font-bold ${ocrInfo.is_gpu ? 'bg-emerald-950/90 text-emerald-300 border border-emerald-500/50' : 'bg-gray-800 text-gray-400'}`}>
                      {ocrInfo.is_gpu ? '⚡ GPU' : 'CPU'}
                    </span>
                  </button>
                )}

                <div className="bg-gray-900/90 border border-gray-800 rounded-lg p-1 max-h-28 overflow-y-auto space-y-1 mb-2">
                  {(st.blur_boxes || []).length === 0 ? (
                    <p className="text-[8px] text-gray-600 text-center py-2 italic">No blur/delogo boxes added</p>
                  ) : (
                    (st.blur_boxes || []).map((b, idx) => (
                      <div key={b.id || idx}
                        onClick={() => setSelBlurBoxIdx(idx)}
                        className={`flex items-center justify-between px-2 py-1 rounded text-[9px] font-mono cursor-pointer transition ${
                          selBlurBoxIdx === idx ? 'bg-indigo-600/30 border border-indigo-500/50 text-white' : 'text-gray-400 hover:bg-gray-800/50'
                        }`}>
                        <span className="truncate">
                          {b.mode === 'delogo' ? '🔍' : b.mode === 'inpaint' ? '🧹' : '🫧'} #{idx + 1} [{b.x},{b.y} {b.w}x{b.h}]
                          {((b.start_time !== undefined && b.start_time >= 0) || (b.end_time !== undefined && b.end_time > 0)) && (
                            <span className={`font-bold ml-1 px-1 py-0.2 rounded text-[7px] ${
                              (currentTime >= (b.start_time || 0) && currentTime <= (b.end_time || 9999))
                                ? 'text-amber-300 bg-amber-950/80 border border-amber-500/40'
                                : 'text-gray-500 bg-gray-900/60'
                            }`}>
                              ⏱{(b.start_time || 0).toFixed(1)}s-{(b.end_time || 0).toFixed(1)}s
                            </span>
                          )}
                          {b.tracked && <span className="text-emerald-400 ml-1">🎯</span>}
                        </span>
                        {/* ── per-box mode toggle ── */}
                        <div className="flex items-center gap-1 shrink-0">
                          <button onClick={(e) => {
                            e.stopPropagation();
                            // Cycle: blur → delogo → inpaint → blur
                            const cycle = { blur: 'delogo', delogo: 'inpaint', inpaint: 'blur' };
                            const updated = (st.blur_boxes||[]).map((box, i) =>
                              i === idx ? { ...box, mode: cycle[box.mode] || 'blur' } : box
                            );
                            patchEdit({ blur_boxes: updated });
                          }} className="text-gray-600 hover:text-cyan-400 p-0.5 text-[7px]" title="Cycle mode: blur / delogo / inpaint">🔄</button>
                          <button onClick={(e) => {
                            e.stopPropagation();
                            patchEdit({ blur_boxes: (st.blur_boxes || []).filter((_, i) => i !== idx) });
                            if (selBlurBoxIdx === idx) setSelBlurBoxIdx(-1);
                          }} className="text-gray-500 hover:text-red-400 p-0.5">×</button>
                        </div>
                      </div>
                    ))
                  )}
                </div>

                <div className="flex gap-1.5 justify-between">
                  <button onClick={() => {
                    if (selBlurBoxIdx >= 0 && st.blur_boxes) {
                      patchEdit({ blur_boxes: st.blur_boxes.filter((_, i) => i !== selBlurBoxIdx) });
                      setSelBlurBoxIdx(-1);
                    }
                  }} disabled={selBlurBoxIdx < 0}
                    className="px-2 py-1 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed rounded text-[9px] text-gray-300 transition">
                    Remove Selected
                  </button>

                  <button
                    disabled={selBlurBoxIdx < 0 || !currentEditItem}
                    onClick={async () => {
                      const box = (st.blur_boxes || [])[selBlurBoxIdx];
                      if (!box || !currentEditItem) return;
                      const startSec = videoRef.current?.currentTime || 0;
                      const clipPath = currentEditItem.clip_path || currentEditItem.path || '';
                      if (!clipPath) { alert('❌ Không tìm thấy đường dẫn clip.'); return; }
                      if (!confirm(`🎯 Track Object\n\nCSRT-track box #${selBlurBoxIdx+1} (${box.w}×${box.h}px)\nStarting from ${startSec.toFixed(1)}s\n\nTime: 10-60s depending on video length. Proceed?`)) return;
                      try {
                        // post() returns a raw Response — must parse JSON
                        const resp = await post('/track_object', {
                          clip_path: clipPath,
                          bbox: { x: box.x, y: box.y, w: box.w, h: box.h },
                          start_time: startSec,
                        });
                        const r = await resp.json();
                        if (r.track_file) {
                          const updated = (st.blur_boxes || []).map((b, i) =>
                            i === selBlurBoxIdx
                              ? { ...b, tracked: true, track_file: r.track_file }
                              : b
                          );
                          patchEdit({ blur_boxes: updated });
                          alert(`✅ Tracking done! ${r.frame_count} frames. Blur will follow object during export.`);
                        } else {
  // ── Include server error detail if available ──
  // (404 detail, 422 body, etc.)
                          const errMsg = r.error || r.detail || JSON.stringify(r);
                          alert('❌ Tracking failed: ' + errMsg);
                        }
                      } catch (e) { alert('Tracking error: ' + e.message); }
                    }}
                    className={`px-2.5 py-1 border rounded text-[9px] font-bold transition flex items-center gap-1 ${
                      selBlurBoxIdx >= 0 && currentEditItem
                        ? 'bg-emerald-950/70 hover:bg-emerald-900 border-emerald-700/50 text-emerald-300'
                        : 'bg-gray-800/40 border-gray-700/30 text-gray-600 cursor-not-allowed opacity-40'
                    }`}>
                    🎯 Track Object
                  </button>
                </div>

                {/* AI Remove Object (Inpaint) */}
                {(st.blur_boxes||[]).some(b => b.mode === 'inpaint') && (
                  <div className="mt-2">
                    {inpaintJob && inpaintJob.status === 'running' ? (
                      <div className="w-full rounded-lg bg-gray-900 border border-amber-700/50 p-2">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[8px] font-bold text-amber-300">🧹 Removing object…</span>
                          <span className="text-[8px] text-amber-400">{Math.round((inpaintJob.pct||0)*100)}%</span>
                        </div>
                        <div className="w-full h-1 bg-gray-800 rounded-full overflow-hidden">
                          <div className="h-full bg-amber-500 transition-all duration-500" style={{width: `${Math.round((inpaintJob.pct||0)*100)}%`}} />
                        </div>
                        <p className="text-[7px] text-gray-400 mt-1 truncate">{inpaintJob.msg}</p>
                      </div>
                    ) : inpaintJob && inpaintJob.status === 'done' ? (
                      <div className="w-full rounded-lg bg-emerald-950/70 border border-emerald-700/50 p-2">
                        <p className="text-[8px] text-emerald-300 font-bold">✅ Done! Output saved.</p>
                        <p className="text-[7px] text-gray-400 truncate">{inpaintJob.output_path}</p>
                        <button onClick={() => setInpaintJob(null)}
                          className="mt-1 text-[7px] text-gray-500 hover:text-gray-300">Dismiss</button>
                      </div>
                    ) : inpaintJob && inpaintJob.status === 'error' ? (
                      <div className="w-full rounded-lg bg-red-950/70 border border-red-700/50 p-2">
                        <p className="text-[8px] text-red-300 font-bold">❌ Error</p>
                        <p className="text-[7px] text-gray-400 truncate">{inpaintJob.error}</p>
                        <button onClick={() => setInpaintJob(null)}
                          className="mt-1 text-[7px] text-gray-500 hover:text-gray-300">Dismiss</button>
                      </div>
                    ) : (
                      <button
                        disabled={!currentEditItem}
                        onClick={async () => {
                          if (!currentEditItem) return;
                          const boxes = (st.blur_boxes||[]).filter(b => b.mode === 'inpaint');
                          if (!boxes.length) { alert('No inpaint boxes found.'); return; }
                          if (!confirm(`🧹 AI Remove Object\n\nWill process ${boxes.length} inpaint region(s) using ProPainter GPU (NVIDIA RTX 3050 acceleration) in:\n${currentEditItem.clip_path}\n\nThe output is saved as a new _inpainted file alongside the original.\n\nProceed?`)) return;
                          try {
                            const res = await post('/inpaint_object', {
                              clip_path: currentEditItem.clip_path,
                              blur_boxes: boxes,
                            });
                            const r = await res.json();
                            if (!r.job_id) { alert('Failed to start: ' + (r.error || r.detail || 'unknown')); return; }
                            setInpaintJob({ jobId: r.job_id, status: 'running', pct: 0, msg: 'Starting ProPainter…' });
  // ── Poll progress every 2s ──
const poll = async () => {
                              try {
                                const s = await fetch(`${API}/inpaint_status/${r.job_id}`).then(x => x.json());
                                setInpaintJob(prev => prev?.jobId === r.job_id ? { ...prev, ...s, jobId: r.job_id } : prev);
                                if (s.status === 'running') setTimeout(poll, 2000);
                              } catch { setTimeout(poll, 3000); }
                            };
                            setTimeout(poll, 2000);
                          } catch(e) { alert('Error: ' + e.message); }
                        }}
                        className="w-full py-1.5 bg-amber-950/70 hover:bg-amber-900/80 border border-amber-700/50 rounded-lg text-[8px] font-bold text-amber-300 disabled:opacity-40 disabled:cursor-not-allowed transition flex items-center justify-center gap-1.5">
                        🧹 AI Remove Object
                      </button>
                    )}
                  </div>
                )}
              </Section>

              <Section id="section-video" title="Biến đổi & Cắt góc Video (Video Transform & Crop)" icon={<Move className="w-3 h-3 text-indigo-400" />} active={selectedLayer?.type === 'video'} defaultOpen={selectedLayer?.type === 'video'}>
                {/* Crop Action Toolbar */}
                <div className="flex items-center gap-1.5 pb-1 border-b border-gray-800/60">
                  <button
                    onClick={() => {
                      selectAndFocusLayer('video');
                      setIsCroppingVideo(p => !p);
                    }}
                    className={`flex-1 py-1.5 px-2 rounded-lg text-[9px] font-bold flex items-center justify-center gap-1 transition shadow ${
                      isCroppingVideo
                        ? 'bg-amber-600 hover:bg-amber-500 text-white ring-2 ring-amber-400/50 animate-pulse'
                        : 'bg-indigo-600 hover:bg-indigo-500 text-white'
                    }`}>
                    <Crop className="w-3 h-3" /> {isCroppingVideo ? '✓ Đang mở Crop (Bấm xong)' : '✂️ Mở Cắt góc (Crop)'}
                  </button>
                  <button
                    onClick={() => {
                      patchEdit({
                        crop_top: 0.0, crop_bottom: 0.0, crop_left: 0.0, crop_right: 0.0,
                        source_mask_top: 0.0, source_mask_bottom: 0.0,
                        video_x: 0, video_y: 0, video_w_scale: 1.0, video_h_scale: 1.0
                      });
                      setIsCroppingVideo(false);
                    }}
                    className="py-1.5 px-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-[9px] transition shrink-0"
                    title="Đặt lại toàn bộ vị trí và crop về mặc định">
                    ↺ Đặt lại
                  </button>
                </div>

                {/* Quick Aspect Ratio Chips */}
                <div className="space-y-1">
                  <label className="text-[8px] text-gray-500 font-semibold block">Tỉ lệ cắt góc nhanh</label>
                  <div className="grid grid-cols-5 gap-1">
                    {[
                      { label: 'Tự do', t: 0, b: 0, l: 0, r: 0 },
                      { label: '9:16', t: 0, b: 0, l: 0.22, r: 0.22 },
                      { label: '16:9', t: 0.22, b: 0.22, l: 0, r: 0 },
                      { label: '1:1',  t: 0.12, b: 0.12, l: 0.12, r: 0.12 },
                      { label: '4:5',  t: 0.10, b: 0.10, l: 0.18, r: 0.18 },
                    ].map(preset => (
                      <button
                        key={preset.label}
                        onClick={() => {
                          selectAndFocusLayer('video');
                          setIsCroppingVideo(true);
                          patchEdit({
                            crop_top: preset.t, crop_bottom: preset.b,
                            crop_left: preset.l, crop_right: preset.r,
                            source_mask_top: preset.t, source_mask_bottom: preset.b
                          });
                        }}
                        className="py-1 px-1 bg-gray-900 hover:bg-indigo-900/40 border border-gray-800 hover:border-indigo-600 rounded text-[8px] font-mono text-gray-300 text-center transition">
                        {preset.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* 4-Edge Crop Sliders */}
                <div className="space-y-1.5 pt-1 border-t border-gray-800/40">
                  <span className="text-[8px] text-gray-400 font-bold uppercase tracking-wider block">4 Mép Cắt Video (Crop Margins)</span>
                  <div className="grid grid-cols-2 gap-2">
                    <Slider label="Top (Trên)" value={st.crop_top ?? st.source_mask_top ?? 0} min={0} max={0.45} step={0.01}
                      onChange={v => patchEdit({ crop_top: v, source_mask_top: v })} />
                    <Slider label="Bottom (Dưới)" value={st.crop_bottom ?? st.source_mask_bottom ?? 0} min={0} max={0.45} step={0.01}
                      onChange={v => patchEdit({ crop_bottom: v, source_mask_bottom: v })} />
                    <Slider label="Left (Trái)" value={st.crop_left ?? 0} min={0} max={0.45} step={0.01}
                      onChange={v => patchEdit({ crop_left: v })} />
                    <Slider label="Right (Phải)" value={st.crop_right ?? 0} min={0} max={0.45} step={0.01}
                      onChange={v => patchEdit({ crop_right: v })} />
                  </div>
                </div>

                {/* Transform (X, Y Offset, Scales) */}
                <div className="space-y-1.5 pt-1 border-t border-gray-800/40">
                  <span className="text-[8px] text-gray-400 font-bold uppercase tracking-wider block">Vị trí & Phóng to</span>
                  <div className="grid grid-cols-2 gap-2">
                    <Slider label="X Offset" value={st.video_x ?? 0} min={-500} max={500} onChange={v => patchEdit({ video_x: v })} unit="px" />
                    <Slider label="Y Offset" value={st.video_y ?? 0} min={-800} max={800} onChange={v => patchEdit({ video_y: v })} unit="px" />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <Slider label="Width Scale" value={st.video_w_scale ?? 1.0} min={0.5} max={2.0} step={0.01} onChange={v => patchEdit({ video_w_scale: v })} />
                    <Slider label="Height Scale" value={st.video_h_scale ?? 1.0} min={0.5} max={2.0} step={0.01} onChange={v => patchEdit({ video_h_scale: v })} />
                  </div>
                </div>
              </Section>


              <Section title="Deep Copyright Evasion 🛡️" icon={<Shield className="w-3 h-3 text-emerald-400" />}>
                <Toggle label="Auto MD5 Hash Shift" value={st.change_md5 ?? true} onChange={v => patchEdit({ change_md5: v })} icon={<Shield className="w-3 h-3 text-indigo-400" />} />


                <Toggle label="Color Grade" value={st.color_grade} onChange={v => patchEdit({ color_grade: v })} icon={<Palette className="w-3 h-3" />} />
                <Toggle label="Flip H" value={st.flip_h} onChange={v => patchEdit({ flip_h: v })} icon={<FlipHorizontal className="w-3 h-3" />} />
                <Toggle label="Flip V" value={st.flip_v} onChange={v => patchEdit({ flip_v: v })} icon={<FlipVertical className="w-3 h-3" />} />
                <Toggle label="Micro-Rotate 1.2°" value={st.micro_rotate} onChange={v => patchEdit({ micro_rotate: v })} icon={<RotateCw className="w-3 h-3" />} />
                <Toggle label="Vignette 3D" value={st.vignette} onChange={v => patchEdit({ vignette: v })} icon={<Layers className="w-3 h-3" />} />
                {st.vignette && <Slider label="Intensity" value={st.vignette_strength ?? 50} min={5} max={100} onChange={v => patchEdit({ vignette_strength: v })} unit="%" />}

                <Toggle label="Smart Zoom 2%" value={st.smart_zoom} onChange={v => patchEdit({ smart_zoom: v })} icon={<Move className="w-3 h-3" />} />
                <Slider label="Hue Shift" value={st.hue_shift} min={-180} max={180} onChange={v => patchEdit({ hue_shift: v })} unit="°" />
                <Slider label="Saturation" value={st.saturation} min={0.5} max={2.0} step={0.05} onChange={v => patchEdit({ saturation: v })} />
                {/* Film Grain — preview overlay is drawn on canvas when ON */}
                <div className={`rounded transition-all ${st.add_grain ? 'bg-orange-950/30 border border-orange-500/20 px-1 pt-0.5 pb-1' : ''}`}>
                  <Toggle label="Film Grain" value={st.add_grain} onChange={v => patchEdit({ add_grain: v })} icon={<Droplets className={`w-3 h-3 ${st.add_grain ? 'text-orange-400' : ''}`} />} />
                  {st.add_grain && (
                    <div className="flex items-center gap-1 pl-5 mt-0.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse" />
                      <span className="text-[7px] text-orange-300 font-mono">GRAIN ×{st.grain_strength || 3} · live overlay ↑</span>
                    </div>
                  )}
                </div>
                {st.add_grain && <Slider label="Strength" value={st.grain_strength} min={1} max={10} onChange={v => patchEdit({ grain_strength: v })} />}

                {/* Speed ±2% — sets video.playbackRate in preview for real-time feel */}
                <div className={`rounded transition-all ${st.speed_tweak ? 'bg-amber-950/30 border border-amber-500/20 px-1 pt-0.5 pb-1' : ''}`}>
                  <Toggle label="Speed ±2%" value={st.speed_tweak} onChange={v => patchEdit({ speed_tweak: v })} icon={<Zap className={`w-3 h-3 ${st.speed_tweak ? 'text-amber-400' : 'text-amber-400'}`} />} />
                  {st.speed_tweak && (
                    <div className="flex items-center gap-1 pl-5 mt-0.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                      <span className="text-[7px] text-amber-300 font-mono">1.0204× · preview is live ↑</span>
                    </div>
                  )}
                </div>

                {/* Audio Pitch ±3% — export only, no browser API for pitch shift */}
                <div className={`rounded transition-all ${st.audio_pitch ? 'bg-emerald-950/30 border border-emerald-500/20 px-1 pt-0.5 pb-1' : ''}`}>
                  <Toggle label="Audio Pitch ±3%" value={st.audio_pitch} onChange={v => patchEdit({ audio_pitch: v })} icon={<Zap className={`w-3 h-3 ${st.audio_pitch ? 'text-emerald-400' : 'text-emerald-400'}`} />} />
                  {st.audio_pitch && (
                    <div className="flex items-center gap-1 pl-5 mt-0.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      <span className="text-[7px] text-emerald-300 font-mono">+3% pitch · applied on export</span>
                    </div>
                  )}
                </div>

                {/* Audio Spectrum EQ — export only */}
                <div className={`rounded transition-all ${st.audio_eq ? 'bg-cyan-950/30 border border-cyan-500/20 px-1 pt-0.5 pb-1' : ''}`}>
                  <Toggle label="Audio Spectrum EQ" value={st.audio_eq} onChange={v => patchEdit({ audio_eq: v })} icon={<Zap className={`w-3 h-3 ${st.audio_eq ? 'text-cyan-400' : 'text-cyan-400'}`} />} />
                  {st.audio_eq && (
                    <div className="flex items-center gap-1 pl-5 mt-0.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                      <span className="text-[7px] text-cyan-300 font-mono">EQ + highpass + lowpass · on export</span>
                    </div>
                  )}
                </div>
              </Section>


              <Section title="Background" icon={<Image className="w-3 h-3" />}>
                {/* Background type ?? matches the Blurred/Image/Video from original app */}
                <div className="flex gap-1">
                  {[['blur', 'Blurred'], ['image', 'Image'], ['video', 'Video']].map(([v, label]) => (
                    <button key={v} onClick={() => patchEdit({ bg_type: v })}
                      className={`flex-1 py-1 rounded text-[9px] transition ${st.bg_type === v ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-500 hover:text-gray-300'}`}>
                      {label}
                    </button>
                  ))}
                </div>
                {st.bg_type === 'image' && (
                  <div className="flex gap-1 items-center">
                    <input readOnly value={st.bg_image_path ? st.bg_image_path.split(/[\\/]/).pop() : 'No image'}
                      className="flex-1 bg-gray-900 border border-gray-800 rounded p-1 text-[9px] text-gray-500 truncate" />
                    <button onClick={() => post('/dialog/pick_bg_image', {}).then(r => r.json()).then(d => {
                      if (d.path) {
                        if (/\.(mp4|mov|webm|mkv|avi|ts|m4v)$/i.test(d.path)) {
                          patchEdit({ bg_type: 'video', bg_video_path: d.path, bg_image_path: '' });
                        } else {
                          patchEdit({ bg_image_path: d.path });
                        }
                      }
                    })}
                      className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-[9px] text-white">…</button>
                  </div>
                )}
                {st.bg_type === 'video' && (
                  <div className="flex gap-1 items-center">
                    <input readOnly value={st.bg_video_path ? st.bg_video_path.split(/[\\/]/).pop() : 'No video'}
                      className="flex-1 bg-gray-900 border border-gray-800 rounded p-1 text-[9px] text-gray-500 truncate" />
                    <button onClick={() => post('/dialog/pick_bg_video', {}).then(r => r.json()).then(d => {
                      if (d.path) {
                        if (/\.(jpg|jpeg|png|webp|bmp|gif)$/i.test(d.path)) {
                          patchEdit({ bg_type: 'image', bg_image_path: d.path, bg_video_path: '' });
                        } else {
                          patchEdit({ bg_video_path: d.path });
                        }
                      }
                    })}
                      className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-[9px] text-white">…</button>
                  </div>
                )}
              </Section>

              <Section id="section-subtitles" title="Subtitles" icon={<MessageSquare className="w-3 h-3 text-emerald-400" />} active={selectedLayer?.type === 'subtitle'} defaultOpen={selectedLayer?.type === 'subtitle'}>
                <Toggle label="Enable" value={st.subtitles} onChange={v => patchEdit({ subtitles: v })} icon={<Eye className="w-3 h-3" />} />
                {st.subtitles && <>
                  {/* ── Engine selector ── */}
                  <div className="bg-gray-900/60 rounded-lg p-2 border border-gray-800/50">
                    <p className="text-[8px] text-gray-500 uppercase tracking-widest mb-1.5">🤖 Sub Engine</p>
                    <div className="flex gap-1">
                      {[['gemini_fallback','Gemini+FB'], ['gemini','Gemini'], ['whisper','Whisper']].map(([v,lbl]) => (
                        <button key={v} onClick={() => patchEdit({ sub_engine: v })}
                          className={`flex-1 py-1 rounded text-[8px] font-medium transition ${
                            (st.sub_engine || 'gemini_fallback') === v
                              ? 'bg-indigo-600 text-white shadow-md shadow-indigo-900/40'
                              : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                          }`}>{lbl}</button>
                      ))}
                    </div>
                    {(st.sub_engine || 'gemini_fallback') === 'gemini_fallback' && (
                      <p className="text-[7px] text-gray-600 mt-1">Gemini → fallback Whisper nếu lỗi</p>
                    )}
                  </div>

                  <select value={st.sub_style} onChange={e => patchEdit({ sub_style: e.target.value })}
                    className="w-full bg-gray-900 border border-gray-800 rounded-lg p-1 text-[9px] text-gray-200 outline-none">
                    <option value="Normal">Normal</option>
                    <option value="Word Pop">Word Pop</option>
                    <option value="Viral Bounce">🔥 Viral Bounce (TikTok/Reels)</option>
                    <option value="Highlight Line">Highlight Line</option>
                  </select>

                  {/* ── Transcribe On-Demand Button ── */}
                  <div className="flex gap-2 items-center">
                    <button
                      onClick={handleTranscribeSub}
                      disabled={transcribingSub}
                      className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg text-[9px] font-bold shadow-md transition ${
                        transcribingSub
                          ? 'bg-emerald-900/60 text-emerald-300 border border-emerald-500/40 cursor-wait'
                          : 'bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white shadow-emerald-950/40 cursor-pointer active:scale-98'
                      }`}>
                      {transcribingSub ? (
                        <>
                          <Loader2 className="w-3 h-3 animate-spin text-emerald-300" />
                          <span>Đang bóc phụ đề ({st.sub_engine === 'whisper' ? 'Whisper' : 'Gemini'})...</span>
                        </>
                      ) : (
                        <>
                          <Mic className="w-3 h-3" />
                          <span>🎙 Tạo Sub Ngay ({st.sub_engine === 'whisper' ? 'Whisper' : 'Gemini'})</span>
                        </>
                      )}
                    </button>
                    {st.srt_content && (
                      <span className="text-[8px] text-emerald-400 bg-emerald-950/60 border border-emerald-800/40 px-1.5 py-0.5 rounded flex items-center gap-1">
                        ✓ Đã có sub
                      </span>
                    )}
                  </div>

                  {/* ── Sub font face ── */}
                  <div className="bg-gray-900/60 rounded-lg p-2 border border-gray-800/50">
                    <p className="text-[8px] text-gray-500 uppercase tracking-widest mb-1.5">🔤 Sub Font</p>
                    <FontPicker value={st.sub_font_name || 'arialbd'} onChange={v => patchEdit({ sub_font_name: v })} />
                    <div className="flex gap-1.5">
                      <Toggle label="UPPERCASE" value={st.sub_uppercase || false} onChange={v => patchEdit({ sub_uppercase: v })} />
                      <Toggle label="Bold" value={st.sub_bold !== false} onChange={v => patchEdit({ sub_bold: v })} />
                      <Toggle label="Italic" value={st.sub_italic || false} onChange={v => patchEdit({ sub_italic: v })} />
                    </div>
                  </div>

                  <Slider label="Font Size" value={st.sub_font_size} min={18} max={140} onChange={v => patchEdit({ sub_font_size: v })} unit="px" />
                  <div className="grid grid-cols-2 gap-2">
                    <Slider label="Y Margin (Đáy)" value={st.sub_margin_v} min={20} max={1800} onChange={v => patchEdit({ sub_margin_v: v })} unit="px" />
                    <Slider label="X Offset (Ngang)" value={st.sub_x ?? 0} min={-500} max={500} onChange={v => patchEdit({ sub_x: v })} unit="px" />
                  </div>
                  {(st.sub_x || 0) !== 0 && (
                    <div className="flex justify-end">
                      <button onClick={() => patchEdit({ sub_x: 0 })} className="text-[8px] text-amber-400 hover:text-amber-300 transition underline cursor-pointer">
                        ↺ Đưa phụ đề về giữa (Reset X)
                      </button>
                    </div>
                  )}

                  {/* ── CapCut-style opaque background box ── */}
                  <div className="bg-gray-900/60 rounded-lg p-2 border border-gray-800/50 space-y-1.5">
                    <p className="text-[8px] text-gray-500 uppercase tracking-widest mb-1">🟥 Nền Bo Chữ (CapCut)</p>
                    <Toggle label="Bật nền hộp" value={st.sub_bg_box || false} onChange={v => patchEdit({ sub_bg_box: v })} />
                    {st.sub_bg_box && <>
                      <ColorPicker
                        label="Màu nền hộp"
                        value={st.sub_bg_box_color || '#000000'}
                        onChange={v => patchEdit({ sub_bg_box_color: v })}
                        presets={['#000000', '#1a1a1a', '#FFFFFF', '#FFD700', '#FF4444', '#0033FF']}
                      />
                      <Slider label="Độ mờ nền" value={st.sub_bg_box_opacity ?? 80} min={10} max={100} onChange={v => patchEdit({ sub_bg_box_opacity: v })} unit="%" />
                    </>}
                  </div>

                  {/* Color pickers ?? only meaningful in karaoke modes (Word Pop / Highlight Line) */}
                  {st.sub_style !== 'Normal' && <>
                    <ColorPicker
                      label="Đã nói (sáng)"
                      value={st.sub_highlight_color || '#FFD700'}
                      onChange={v => patchEdit({ sub_highlight_color: v })}
                      presets={['#FFD700', '#FF6B35', '#00D4FF', '#FFFFFF', '#FF4444']}
                    />
                    <ColorPicker
                      label="Chưa nói (mờ)"
                      value={st.sub_dim_color || '#FFFFFF'}
                      onChange={v => patchEdit({ sub_dim_color: v })}
                      presets={['#FFFFFF', '#AAAAAA', '#888888', '#FFD700', '#00FF88']}
                    />
                  </>}

                  {/* ?? Subtitle Delay ?? corrects Gemini early-bias or A/V drift */}
                  <div className="mt-1.5 bg-gray-900/60 rounded-lg p-2 border border-gray-800/50">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-[8px] text-gray-400 font-medium flex items-center gap-1">
                        ? Sub Delay
                      </span>
                      <span className={`text-[9px] font-bold tabular-nums px-1.5 py-0.5 rounded ${
                        (st.sub_offset_ms || 0) < 0 ? 'text-blue-300 bg-blue-900/40' :
                        (st.sub_offset_ms || 0) > 0 ? 'text-amber-300 bg-amber-900/40' :
                        'text-gray-500 bg-gray-800/40'
                      }`}>
                        {(st.sub_offset_ms || 0) > 0 ? '+' : ''}{st.sub_offset_ms || 0} ms
                      </span>
                    </div>
                    <input type="range" min={-3000} max={3000} step={50}
                      value={st.sub_offset_ms || 0}
                      onChange={e => patchEdit({ sub_offset_ms: Number(e.target.value) })}
                      className="w-full h-1.5 accent-amber-400 cursor-pointer"
                    />
                    <div className="flex justify-between text-[7px] text-gray-700 mt-1">
                      <span>-3s (sớm hơn)</span>
                      <button onClick={() => patchEdit({ sub_offset_ms: 0 })}
                        className="text-gray-600 hover:text-gray-400 text-[7px] transition">Reset</button>
                      <span>+3s (trễ hơn)</span>
                    </div>
                  </div>

                </>}
              </Section>


              {/* ── Title Prompt Customizer  ── */}
              <Section title="Title Prompt" icon={<Sparkles className="w-3 h-3 text-amber-400" />}>
                <p className="text-[8px] text-gray-600 leading-relaxed mb-2">
                  Tự viết prompt cho Gemini tạo tiêu đ??. Biến dùng được:&nbsp;
                  <span className="text-indigo-400 font-mono">&#123;description&#125;</span>,&nbsp;
                  <span className="text-indigo-400 font-mono">&#123;highlight_reason&#125;</span>,&nbsp;
                  <span className="text-indigo-400 font-mono">&#123;old_title&#125;</span>
                </p>

                {/* ── Textarea ── */}
                <textarea
                  value={titlePrompt}
                  onChange={e => setTitlePrompt(e.target.value)}
                  rows={7}
                  placeholder={DEFAULT_PROMPT_HINT}
                  className="w-full bg-[#0a0b12] border border-gray-800 rounded-lg p-2 text-[9px] font-mono text-gray-300 outline-none focus:border-indigo-500/60 resize-y leading-relaxed"
                />

                {/* ── Active prompt indicator ── */}
                {config.title_prompt && (
                  <p className="text-[8px] text-emerald-400 flex items-center gap-1 mt-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
                    Custom prompt đang active
                  </p>
                )}

                {/* ── Action buttons ── */}
                <div className="flex gap-1 mt-1.5">
                  <button onClick={applyTitlePrompt}
                    className="flex-1 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-[8px] font-bold transition">
                    ✅ Apply
                  </button>
                  <button onClick={() => { setTitlePrompt(''); post('/config', { title_prompt: null }); setConfig(p => ({ ...p, title_prompt: null })); }}
                    className="px-2 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg text-[8px] transition" title="Xóa custom, dùng mặc định">
                    Reset
                  </button>
                </div>

                {/* ── Save as preset ── */}
                <div className="flex gap-1 mt-2">
                  <input
                    value={savePresetName}
                    onChange={e => setSavePresetName(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && savePromptPreset()}
                    placeholder="Tn preset"
                    className="flex-1 bg-gray-900 border border-gray-800 rounded-lg px-2 py-1 text-[8px] text-gray-300 outline-none focus:border-amber-500/60"
                  />
                  <button onClick={savePromptPreset}
                    className="px-2 py-1 bg-amber-700/70 hover:bg-amber-600/80 text-amber-200 rounded-lg text-[8px] font-bold transition">
                    ? Save
                  </button>
                </div>

                {/* ── Saved presets list ── */}
                {savedPresets.length > 0 && (
                  <div className="mt-2 space-y-1">
                    <p className="text-[8px] text-gray-600 uppercase tracking-widest">Presets đã lưu</p>
                    {savedPresets.map(name => (
                      <div key={name} className="flex items-center gap-1">
                        <button onClick={() => loadPromptPreset(name)}
                          className="flex-1 text-left px-2 py-1 bg-gray-900 hover:bg-gray-800 border border-gray-800 rounded text-[8px] text-indigo-300 truncate transition">
                          ? {name}
                        </button>
                        <button onClick={() => deletePromptPreset(name)}
                          className="p-1 text-gray-700 hover:text-red-400 transition" title="Xa preset">
                          <Trash2 className="w-2.5 h-2.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </Section>

              <Section title="Export Settings" icon={<Settings className="w-3 h-3" />}>

                <div className="flex gap-1.5 items-center">
                  <input readOnly value={config.output_folder || 'Default'} onClick={() => openOutput()} className="flex-1 bg-gray-900 border border-gray-800 rounded-lg p-1.5 text-[9px] text-indigo-300 truncate cursor-pointer hover:border-indigo-500/50" title="Click to open folder in Windows Explorer" />
                  <button onClick={() => openOutput()} className="p-1.5 bg-gray-800 hover:bg-gray-700 text-amber-400 rounded-lg shrink-0" title="Open Folder in Windows Explorer">
                    <FolderOpen className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={pickFolder} className="px-2.5 py-1.5 bg-indigo-600/80 hover:bg-indigo-600 text-white rounded-lg text-[9px] font-medium shrink-0" title="Change Folder">
                    Browse…
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {[['Resolution', 'export_resolution', [['1080x1920', '1080×1920'], ['720x1280', '720×1280'], ['540x960', '540×960']]],
                    ['Encoder', 'export_encoder', (encoders.length ? encoders : ['libx264']).map(e => [e, {
                      h264_nvenc: '🚀 NVIDIA H.264 (GPU)',
                      hevc_nvenc: '🚀 NVIDIA HEVC (GPU)',
                      h264_qsv:   '🚀 Intel QSV H.264 (GPU)',
                      hevc_qsv:   '🚀 Intel QSV HEVC (GPU)',
                      h264_amf:   '🚀 AMD AMF H.264 (GPU)',
                      hevc_amf:   '🚀 AMD AMF HEVC (GPU)',
                      h264_mf:    '🚀 Windows MF (GPU)',
                      libx264:    '💻 CPU (libx264)',
                      libx265:    '💻 CPU (libx265)',
                    }[e] || e])],
                    ['Preset', 'export_preset', [['ultrafast', 'ultrafast'], ['fast', 'fast'], ['medium', 'medium'], ['slow', 'slow']]],
                  ].map(([label, key, opts]) => (
                    <div key={key}>
                      <label className="text-[8px] text-gray-600 block mb-0.5">{label}</label>
                      <select value={config[key]} onChange={e => updateCfg({ [key]: e.target.value })}
                        className="w-full bg-gray-900 border border-gray-800 rounded p-1 text-[9px] text-gray-200 outline-none">
                        {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    </div>
                  ))}
                  {/* Preset ?? GPU encoders use p1-p7 naming (shown as CPU names, mapped server-side) */}
                  <div>
                    <label className="text-[8px] text-gray-600 block mb-0.5">FPS</label>
                    <select value={config.export_fps ?? ''} onChange={e => updateCfg({ export_fps: e.target.value ? parseInt(e.target.value) : null })}
                      className="w-full bg-gray-900 border border-gray-800 rounded p-1 text-[9px] text-gray-200 outline-none">
                      <option value="">Original</option><option value="30">30</option><option value="60">60</option>
                    </select>
                  </div>
                </div>
                <Slider label="CRF" value={config.export_crf} min={15} max={30} onChange={v => updateCfg({ export_crf: v })} />
                <Slider label="Threads" value={config.export_threads} min={1} max={8} onChange={v => updateCfg({ export_threads: v })} />
                <div className="pt-1.5 border-t border-gray-800/60 mt-1">
                  <Toggle
                    label="🧹 Dọn file tạm sau khi xuất (Auto-clean temp)"
                    value={config.auto_clean_temp !== false}
                    onChange={v => updateCfg({ auto_clean_temp: v })}
                  />
                </div>
              </Section>
            </>}
          </div>
        </div>

        {/* Center: Live PIL preview */}
        <div className="flex-1 flex flex-col items-center justify-start bg-[#07080f] gap-3 p-4 overflow-y-auto min-h-0">
          {selEditIdx < 0
            ? <div className="text-center text-gray-800 m-auto"><Film className="w-12 h-12 mx-auto mb-2 opacity-30" /><p className="text-xs">Select a clip from the Edit Queue →</p></div>
            : <>
              <p className="text-[10px] text-gray-500 truncate max-w-xs font-medium shrink-0">{currentEditItem?.title}</p>
              {/* Preview canvas — pointerdown starts drag or blur drawing */}
              {/* Outer wrapper: overflow-hidden, shrink-0 ensures canvas is never squished by flexbox */}
              <div ref={canvasRef}
                className={`relative shadow-2xl select-none overflow-hidden rounded-2xl shrink-0 ${
                  drawMode ? 'cursor-crosshair ring-2 ring-indigo-500/50' : 'cursor-ns-resize'
                }`}
                style={{ width: 324, height: 576 }}
                onPointerDown={handleCanvasPointerDown}>

                {/* Background clip layer — z-0 (outer div provides the overflow-hidden) */}
                <div className="absolute inset-0 pointer-events-none z-0">
                  {previewUrl ? (
                    <img src={previewUrl} alt="Edit Preview" draggable={false}
                      className="absolute inset-0 w-full h-full object-cover"
                      style={{ userSelect: 'none', WebkitUserSelect: 'none', transition: 'opacity 0.12s ease' }} />
                  ) : !isPlaying && (
                  <div className="absolute inset-0 bg-gray-950 flex items-center justify-center">
                    {previewErr
                      ? <div className="p-3 text-center"><AlertCircle className="w-6 h-6 text-red-500 mx-auto mb-1" /><p className="text-[9px] text-red-400">{previewErr}</p></div>
                      : <RefreshCw className="w-5 h-5 text-gray-700 animate-spin" />}
                  </div>
                )}

                </div>{/* ── end inner clip ── */}
                {/* ???? Layer 1: Transparent canvas ?? video frames rendered by RAF loop ???? */}
                {/* Canvas is transparent (clearRect each frame) so the blur-bg img shows through
                    the letterbox areas (where there is no video content). This is the only way to
                    composite video over the blur background without black bars from a <video> element. */}
                <canvas
                  ref={videoCanvasRef}
                  width={324}
                  height={576}
                  className="absolute inset-0 w-full h-full"
                  style={{ opacity: (isPlaying || videoLoaded) ? 1 : 0, pointerEvents: 'none' }}
                />

                {/* 🎞 Film Grain CSS overlay — approximates FFmpeg noise=alls=X filter.
                    SVG feTurbulence noise scaled by grain_strength for pixel-accurate feel. */}
                {editState?.add_grain && (
                  <div
                    className="absolute inset-0 pointer-events-none z-10"
                    style={{
                      backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='g'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23g)'/%3E%3C/svg%3E")`,
                      mixBlendMode: 'overlay',
                      opacity: Math.min(0.55, (editState.grain_strength || 3) * 0.055),
                    }}
                  />
                )}

                {/* ???? Layer 1b: Hidden <video> ?? provides decoded frames + audio for the canvas RAF loop ???? */}
                {/* Never unmounted so seek position is preserved across play/pause */}
                <video
                  ref={videoRef}
                  src={`${API}/stream?path=${encodeURIComponent(currentEditItem?.clip_path || currentEditItem?.path || '')}`}
                  playsInline
                  preload="auto"
                  onTimeUpdate={(e) => {
                    const st = editStateRef.current;
                    const vidDur = (st?.video_trim_dur > 0 && st.video_trim_dur < (duration || 9999))
                      ? st.video_trim_dur
                      : (duration || 9999);
                    if (e.target.currentTime <= vidDur) {
                      setCurrentTime(e.target.currentTime);
                    }
                  }}
                  onLoadedData={() => {
                    setVideoLoaded(true);
                    if (!isPlaying) paintFrame();
                  }}
                  onLoadedMetadata={(e) => {
                    setDuration(e.target.duration);
                    e.target.pause();
                    if (!isPlaying) paintFrame();
                  }}
                  onCanPlay={() => {
                    setVideoLoaded(true);
                    if (!isPlaying) paintFrame();
                  }}
                  onSeeked={() => {
                    if (!isPlaying) paintFrame();
                  }}
                  style={{ position: 'absolute', width: 1, height: 1, opacity: 0, pointerEvents: 'none' }}
                />

                {/* Hidden <audio> — provides decoded custom audio for synchronized preview */}
                <audio
                  ref={customAudioRef}
                  src={toAssetUrl(editState?.custom_audio_url || '')}
                  preload="auto"
                  style={{ position: 'absolute', width: 1, height: 1, opacity: 0, pointerEvents: 'none' }}
                />

                {/* Hidden bg image / video — loaded so bgImageRef or bgVideoRef is drawable in canvas paintFrame */}
                {editState?.bg_type === 'image' && editState?.bg_image_path && !/\.(mp4|mov|webm|mkv|avi|ts|m4v)$/i.test(editState.bg_image_path) && (
                  <img
                    ref={bgImageRef}
                    src={`${API}/stream?path=${encodeURIComponent(editState.bg_image_path)}`}
                    alt=""
                    style={{ position: 'absolute', width: 1, height: 1, opacity: 0, pointerEvents: 'none' }}
                  />
                )}

                {((editState?.bg_type === 'video' && editState?.bg_video_path) || (editState?.bg_type === 'image' && editState?.bg_image_path && /\.(mp4|mov|webm|mkv|avi|ts|m4v)$/i.test(editState.bg_image_path))) && (
                  <video
                    ref={bgVideoRef}
                    src={`${API}/stream?path=${encodeURIComponent(editState?.bg_type === 'video' ? editState.bg_video_path : editState.bg_image_path)}`}
                    muted
                    loop
                    playsInline
                    onLoadedMetadata={(e) => {
                      // Autoplay silently so background loops continuously in preview
                      e.target.play().catch(() => {});
                    }}
                    style={{ position: 'absolute', width: 1, height: 1, opacity: 0, pointerEvents: 'none' }}
                  />
                )}

                {/* Pre-buffer pool: disabled heavy auto-prefetching to prevent network starvation */}
                {editQueue
                  .filter((_, i) => i !== selEditIdx && Math.abs(i - selEditIdx) <= 1)
                  .map(item => {
                    const key = item.clip_path || item.path || '';
                    if (!key) return null;
                    return (
                      <video
                        key={`prefetch-${key}`}
                        src={`${API}/stream?path=${encodeURIComponent(key)}`}
                        preload="none"
                        muted
                        playsInline
                        style={{ position: 'absolute', width: 0, height: 0, opacity: 0, pointerEvents: 'none' }}
                      />
                    );
                  })}

                {/* 🎬 Main Video Layer: Selection Bounding Box & 8-Handle Freeform Crop Tool */}
                {selectedLayer?.type === 'video' && (() => {
                  const vf = videoFrameRef.current || { fgX: 0, fgY: 0, fgW: 324, fgH: 182, cropTop: 0, cropBottom: 0, cropLeft: 0, cropRight: 0 };
                  const cT = editState?.crop_top ?? editState?.source_mask_top ?? 0;
                  const cB = editState?.crop_bottom ?? ((editState?.source_mask_mode === 'bottom' || editState?.source_mask_mode === 'both') ? (editState?.source_mask_bottom ?? 0) : 0);
                  const cL = editState?.crop_left ?? 0;
                  const cR = editState?.crop_right ?? 0;

                  // Uncropped frame geometry
                  const rawX = vf.fgX;
                  const rawY = vf.fgY;
                  const rawW = vf.fgW;
                  const rawH = vf.fgH;

                  // Cropped visible geometry on canvas
                  const cropX = rawX + cL * rawW;
                  const cropY = rawY + cT * rawH;
                  const cropW = Math.max(10, rawW * (1 - cL - cR));
                  const cropH = Math.max(10, rawH * (1 - cT - cB));

                  return (
                    <>
                      {/* If Cropping Mode is Active: Show full uncropped outline + dark backdrop outside crop */}
                      {isCroppingVideo ? (
                        <div className="absolute inset-0 pointer-events-none z-25">
                          {/* Dimmed backdrop outside active crop */}
                          <div className="absolute left-0 right-0 top-0 bg-black/60 pointer-events-none" style={{ height: `${Math.max(0, cropY)}px` }} />
                          <div className="absolute left-0 right-0 bottom-0 bg-black/60 pointer-events-none" style={{ height: `${Math.max(0, 576 - (cropY + cropH))}px` }} />
                          <div className="absolute bg-black/60 pointer-events-none" style={{ top: `${cropY}px`, height: `${cropH}px`, left: 0, width: `${Math.max(0, cropX)}px` }} />
                          <div className="absolute bg-black/60 pointer-events-none" style={{ top: `${cropY}px`, height: `${cropH}px`, right: 0, width: `${Math.max(0, 324 - (cropX + cropW))}px` }} />

                          {/* Uncropped full footage outline (reference dashed frame) */}
                          <div
                            className="absolute border border-dashed border-gray-400/40 pointer-events-none"
                            style={{ left: `${rawX}px`, top: `${rawY}px`, width: `${rawW}px`, height: `${rawH}px` }}>
                            <span className="text-[6.5px] bg-black/70 text-gray-400 px-1 rounded absolute -top-3 left-0">Khung gốc</span>
                          </div>

                          {/* Active 8-Handle Crop Box with Rule of Thirds Grid */}
                          <div
                            className="absolute border-2 border-white shadow-2xl pointer-events-auto select-none"
                            style={{ left: `${cropX}px`, top: `${cropY}px`, width: `${cropW}px`, height: `${cropH}px` }}>
                            {/* Rule of Thirds Grid Lines */}
                            <div className="absolute inset-0 pointer-events-none grid grid-cols-3 grid-rows-3">
                              <div className="border-r border-b border-white/30" />
                              <div className="border-r border-b border-white/30" />
                              <div className="border-b border-white/30" />
                              <div className="border-r border-b border-white/30" />
                              <div className="border-r border-b border-white/30" />
                              <div className="border-b border-white/30" />
                              <div className="border-r border-b border-white/30" />
                              <div className="border-r border-b border-white/30" />
                              <div />
                            </div>

                            {/* Top Toolbar in Crop Mode */}
                            <div className="absolute -top-7 inset-x-0 flex items-center justify-between px-0.5 pointer-events-auto">
                              <span className="text-[7.5px] bg-amber-600 text-white font-bold px-1.5 py-0.5 rounded shadow flex items-center gap-1">
                                ✂️ Cắt Video
                              </span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setIsCroppingVideo(false);
                                }}
                                className="text-[7.5px] bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-2 py-0.5 rounded shadow transition cursor-pointer">
                                ✓ Xong
                              </button>
                            </div>

                            {/* 4 Corner Crop Handles */}
                            <div className="absolute -top-1.5 -left-1.5 w-3.5 h-3.5 bg-white border-2 border-amber-600 rounded-sm shadow cursor-nwse-resize hover:scale-125 transition-transform z-40"
                              onPointerDown={(e) => startVideoCrop(e, 'tl')} />
                            <div className="absolute -top-1.5 -right-1.5 w-3.5 h-3.5 bg-white border-2 border-amber-600 rounded-sm shadow cursor-nesw-resize hover:scale-125 transition-transform z-40"
                              onPointerDown={(e) => startVideoCrop(e, 'tr')} />
                            <div className="absolute -bottom-1.5 -left-1.5 w-3.5 h-3.5 bg-white border-2 border-amber-600 rounded-sm shadow cursor-nesw-resize hover:scale-125 transition-transform z-40"
                              onPointerDown={(e) => startVideoCrop(e, 'bl')} />
                            <div className="absolute -bottom-1.5 -right-1.5 w-3.5 h-3.5 bg-white border-2 border-amber-600 rounded-sm shadow cursor-nwse-resize hover:scale-125 transition-transform z-40"
                              onPointerDown={(e) => startVideoCrop(e, 'br')} />

                            {/* 4 Edge Crop Handles */}
                            <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-6 h-2 bg-white border border-amber-600 rounded-full shadow cursor-ns-resize hover:scale-110 transition-transform z-40"
                              onPointerDown={(e) => startVideoCrop(e, 't')} />
                            <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-6 h-2 bg-white border border-amber-600 rounded-full shadow cursor-ns-resize hover:scale-110 transition-transform z-40"
                              onPointerDown={(e) => startVideoCrop(e, 'b')} />
                            <div className="absolute top-1/2 -translate-y-1/2 -left-1 h-6 w-2 bg-white border border-amber-600 rounded-full shadow cursor-ew-resize hover:scale-110 transition-transform z-40"
                              onPointerDown={(e) => startVideoCrop(e, 'l')} />
                            <div className="absolute top-1/2 -translate-y-1/2 -right-1 h-6 w-2 bg-white border border-amber-600 rounded-full shadow cursor-ew-resize hover:scale-110 transition-transform z-40"
                              onPointerDown={(e) => startVideoCrop(e, 'r')} />
                          </div>
                        </div>
                      ) : (
                        /* Normal Video Selection Mode: Bounding Box + 4-Corner Scale + Drag Move */
                        <div
                          onPointerDown={startVideoMove}
                          className="absolute border-2 border-indigo-400/90 ring-1 ring-indigo-400/50 rounded-sm shadow-xl pointer-events-auto select-none cursor-move z-25 group"
                          style={{ left: `${cropX}px`, top: `${cropY}px`, width: `${cropW}px`, height: `${cropH}px` }}>

                          {/* Floating Top Mini Toolbar */}
                          <div className="absolute -top-7 inset-x-0 flex items-center justify-between px-0.5 pointer-events-auto">
                            <span className="text-[7.5px] bg-indigo-600 text-white font-bold px-1.5 py-0.5 rounded shadow flex items-center gap-1">
                              🎬 Video Chính
                            </span>
                            <div className="flex items-center gap-1">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setIsCroppingVideo(true);
                                }}
                                className="text-[7.5px] bg-amber-600 hover:bg-amber-500 text-white font-bold px-1.5 py-0.5 rounded shadow transition cursor-pointer flex items-center gap-0.5">
                                <Crop className="w-2 h-2" /> Crop
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  patchEdit({ video_x: 0, video_y: 0, video_w_scale: 1.0, video_h_scale: 1.0 });
                                }}
                                className="text-[7.5px] bg-gray-800 hover:bg-gray-700 text-gray-300 px-1 py-0.5 rounded shadow transition cursor-pointer">
                                ↺ Giữa
                              </button>
                            </div>
                          </div>

                          {/* 4 Corner Scale Handles */}
                          <div className="absolute -top-1.5 -left-1.5 w-3 h-3 bg-white border-2 border-indigo-600 rounded-sm shadow cursor-nwse-resize hover:scale-125 transition-transform z-40"
                            onPointerDown={(e) => startVideoScale(e, 'tl')} />
                          <div className="absolute -top-1.5 -right-1.5 w-3 h-3 bg-white border-2 border-indigo-600 rounded-sm shadow cursor-nesw-resize hover:scale-125 transition-transform z-40"
                            onPointerDown={(e) => startVideoScale(e, 'tr')} />
                          <div className="absolute -bottom-1.5 -left-1.5 w-3 h-3 bg-white border-2 border-indigo-600 rounded-sm shadow cursor-nesw-resize hover:scale-125 transition-transform z-40"
                            onPointerDown={(e) => startVideoScale(e, 'bl')} />
                          <div className="absolute -bottom-1.5 -right-1.5 w-3 h-3 bg-white border-2 border-indigo-600 rounded-sm shadow cursor-nwse-resize hover:scale-125 transition-transform z-40"
                            onPointerDown={(e) => startVideoScale(e, 'br')} />
                        </div>
                      )}
                    </>
                  );
                })()}

                {/* ???? CapCut-Style Interactive Text Box (Dashed Border + 4 Corner Handles + Rotate Handle + Double Click Edit) ???? */}
                {currentEditItem?.title && (() => {
                  const yPct = Math.max(0, Math.min(100, ((editState?.text_y ?? 60) / 1920) * 100));
                  const textX = (editState?.text_x || 0) * (324 / 1080);
                  const wrapPct = Math.max(0.3, Math.min(1.0, editState?.title_wrap_pct ?? 1.0));
                  const fullContainerW = 324 - 16; // ── 308px ────────────────────────────────────────────────────────
  // (mx-2 = 8px margin each side on 324px canvas)
                  const boxW = fullContainerW * wrapPct;
                  const scale = 324 / 1080;
                  const fontSize = Math.round((editState?.font_size || 52) * scale);
                  const boxHex = editState?.box_bg_color_hex || '#222222';
                  const boxAlpha = Math.round(((editState?.box_opacity ?? 90) / 100) * 255).toString(16).padStart(2, '0');
                  const fontFamily = (
                    { impact:          'Impact, "Arial Narrow", sans-serif',
                      arialbd:         '"Arial Black", Arial, sans-serif',
                      arial:           'Arial, sans-serif',
                      bebas:           '"Bebas Neue", Impact, sans-serif',
                      anton:           '"Anton", Impact, sans-serif',
                      ariblk:          '"Arial Black", Impact, sans-serif',
                      gothicb:         '"Century Gothic", Futura, sans-serif',
                      verdanab:        'Verdana, Geneva, sans-serif',
                      calibrib:        'Calibri, "Gill Sans", sans-serif',
                      comicbd:         '"Comic Sans MS", Chalkboard, sans-serif',
                      trebucbd:        '"Trebuchet MS", Tahoma, sans-serif',
  // ── Bundled fonts ──
  // loaded via @font-face or matched by name in browser
                      montserrat:      'Montserrat, "Trebuchet MS", sans-serif',
                      luckiestguy:     '"Luckiest Guy", Impact, cursive',
                      nunito:          'Nunito, "Century Gothic", sans-serif',
                      permanentmarker: '"Permanent Marker", "Comic Sans MS", cursive',
                    }[editState?.font_name]
                  ) || `"${editState?.font_name}", Impact, sans-serif`;
                  const rotation = editState?.text_rotation || 0;

                  const isTitleSelected = selectedLayer?.type === 'title';
                  return (
                    <div className={`absolute pointer-events-auto select-none z-30 transition-shadow ${
                      isTitleSelected ? 'ring-2 ring-cyan-400/80' : 'hover:ring-1 hover:ring-cyan-400/40'
                    }`}
                      style={{
                        top: `${yPct}%`,
                        left: '50%',
                        width: `${boxW}px`,
                        transform: `translate(calc(-50% + ${textX}px), -50%) rotate(${rotation}deg)`,
                        transformOrigin: 'center center'
                      }}
                      onPointerDown={(e) => {
                        selectAndFocusLayer('title');
                        if (e.target.dataset.handle) return;
                        dragRect.current      = canvasRef.current.getBoundingClientRect();
                        dragStartPos.current  = { x: e.clientX, y: e.clientY };
                        dragStartText.current = { x: editState?.text_x ?? 0, y: editState?.text_y ?? 60 };
                        dragActive.current    = true;
                        e.stopPropagation();
                        e.preventDefault();
                      }}
                      onDoubleClick={(e) => {
                        e.stopPropagation();
                        setIsEditingTitleInline(true);
                      }}>

                      {/* Title Background Box ?? Frame or CapCut per-line tight mode */}
                      {(() => {
                        const boxMode     = editState?.box_mode || 'frame';
                        const boxOpacity  = editState?.box_opacity ?? 90;
                        const boxRad      = editState?.box_radius ?? 40;
                        const boxRadPx    = Math.round(boxRad * scale);
                        const rawTitleText = currentEditItem?.title || '';
                        const titleText   = editState?.title_uppercase ? rawTitleText.toUpperCase() : rawTitleText;
                        const strokeEnabled = editState?.stroke_enabled !== false;
                        const strokeWidth = editState?.stroke_width ?? 0;
                        const strokeColor = editState?.stroke_color_hex || '#000000';
                        // Outer-only stroke via 8-direction text-shadow — matches PIL morphological dilation.
                        // Unlike -webkit-text-stroke (which strokes both inside/outside, thinning letters),
                        // this approach only adds shadow outside the letter boundary, identical to export.
                        const strokePx = strokeEnabled && strokeWidth > 0
                          ? Math.max(1, Math.round(strokeWidth * scale))
                          : 0;
                        const strokeShadow = strokePx > 0
                          ? [
                              [-strokePx, -strokePx], [strokePx, -strokePx],
                              [-strokePx,  strokePx], [strokePx,  strokePx],
                              [0,         -strokePx], [0,          strokePx],
                              [-strokePx,  0],        [strokePx,   0],
                            ].map(([dx, dy]) => `${dx}px ${dy}px 0 ${strokeColor}`).join(', ')
                          : 'none';
                        const textStyle   = {
                          fontFamily, fontSize: `${fontSize}px`,
                          color: editState?.text_color_hex || '#ffffff',
                          textShadow: strokeShadow,
                          textAlign: editState?.text_align || 'left',
                          fontWeight: editState?.font_bold ? 'bold' : 'normal',
                          fontStyle: editState?.font_italic ? 'italic' : 'normal',
                          lineHeight: editState?.line_height || 1.2,
                          letterSpacing: `${(editState?.letter_spacing ?? 0) * scale}px`,
                        };

                        const handles = isTitleSelected ? (
                          <>
                            {/* ── Rotate handle ── */}
                            <div className="absolute -top-7 left-1/2 -translate-x-1/2 flex flex-col items-center pointer-events-auto"
                              data-handle="rotate"
                              onPointerDown={(e) => {
                                e.stopPropagation();
                                const startX = e.clientX;
                                const startRot = rotation;
                                const onRotateMove = (re) => {
                                  const deltaX = re.clientX - startX;
                                  const newRot = Math.max(-45, Math.min(45, Math.round(startRot + deltaX * 0.5)));
                                  patchEdit({ text_rotation: newRot });
                                };
                                const onRotateUp = () => {
                                  window.removeEventListener('pointermove', onRotateMove);
                                  window.removeEventListener('pointerup', onRotateUp);
                                };
                                window.addEventListener('pointermove', onRotateMove);
                                window.addEventListener('pointerup', onRotateUp);
                              }}>
                              <div className="w-5 h-5 rounded-full bg-indigo-600 border border-indigo-300 text-white flex items-center justify-center shadow-lg hover:scale-125 transition-transform cursor-grab active:cursor-grabbing"
                                title="Drag left/right to rotate text box">
                                <RotateCw className="w-2.5 h-2.5" />
                              </div>
                              <div className="w-0.5 h-2 bg-cyan-400/80" />
                            </div>
                            {/* ── 4 corner resize handles ── */}
                            <div className="absolute -top-1.5 -left-1.5 w-3.5 h-3.5 rounded-sm bg-white border-2 border-cyan-500 shadow cursor-nwse-resize hover:scale-125 transition-transform z-40" data-handle="resize-tl" onPointerDown={(e) => startTitleCornerResize(e, 'tl')} />
                            <div className="absolute -top-1.5 -right-1.5 w-3.5 h-3.5 rounded-sm bg-white border-2 border-cyan-500 shadow cursor-nesw-resize hover:scale-125 transition-transform z-40" data-handle="resize-tr" onPointerDown={(e) => startTitleCornerResize(e, 'tr')} />
                            <div className="absolute -bottom-1.5 -left-1.5 w-3.5 h-3.5 rounded-sm bg-white border-2 border-cyan-500 shadow cursor-nesw-resize hover:scale-125 transition-transform z-40" data-handle="resize-bl" onPointerDown={(e) => startTitleCornerResize(e, 'bl')} />
                            <div className="absolute -bottom-1.5 -right-1.5 w-3.5 h-3.5 rounded-sm bg-white border-2 border-cyan-500 shadow cursor-nwse-resize hover:scale-125 transition-transform z-40" data-handle="resize-br" onPointerDown={(e) => startTitleCornerResize(e, 'br')} />
                          </>
                        ) : null;

                        const textContent = isEditingTitleInline ? (
                          <textarea autoFocus value={titleText}
                            onChange={(e) => {
                              const newTitle = e.target.value;
                              setEditQueue(prev => prev.map((item, idx) => idx === selEditIdx ? { ...item, title: newTitle } : item));
                            }}
                            onBlur={() => setIsEditingTitleInline(false)}
                            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); setIsEditingTitleInline(false); } }}
                            className="w-full bg-black/90 text-white rounded p-1 outline-none resize-none"
                            style={{ fontFamily, fontSize: `${fontSize}px`, textAlign: editState?.text_align || 'left', lineHeight: editState?.line_height || 1.2, letterSpacing: `${(editState?.letter_spacing ?? 0) * scale}px` }}
                          />
                        ) : null;

                        // Mode-specific padding matching app.py _make_title_image exactly at 1080px → scaled to preview
                        // Frame:  pad_x=40,              pad_y=26.67 (full box)
                        // CapCut: l_pad_x=fontSize*0.35, l_pad_y=lineH*0.16 (per-line bubble)
                        // Badges: l_pad_x=fontSize*0.35, l_pad_y=lineH*0.08 (per-line separate)
                        let padH, padV;
                        if (boxMode === 'frame') {
                          padH = Math.round(40 * scale);            // ≈ 12px
                          padV = Math.round(26.67 * scale);         // ≈ 8px
                        } else if (boxMode === 'capcut') {
                          padH = Math.max(3, Math.round(fontSize * 0.35));  // ≈ 5px, matches PIL l_pad_x
                          padV = Math.max(1, Math.round(fontSize * 0.16));  // ≈ 2px, matches PIL l_pad_y
                        } else {
                          // badges
                          padH = Math.max(3, Math.round(fontSize * 0.35));  // ≈ 5px
                          padV = Math.max(1, Math.round(fontSize * 0.08));  // ≈ 1px
                        }
                        const effRadPx = Math.round(boxRad * scale); // matches PIL: radius applied as-is
                        const frameAlign = editState?.text_align || 'center';


                        const wrapPct = Math.max(0.3, Math.min(1.0, editState?.title_wrap_pct ?? 1.0));
                        const fullContainerW = 1080 - 2 * 26.67;
                        const boxW1080 = fullContainerW * wrapPct;
                        const fontSize1080 = editState?.font_size || 52;
                        const isBubbleMode = (boxMode === 'capcut' || boxMode === 'badges');
                        const lPadX1080 = Math.max(6.0, Math.round(fontSize1080 * 0.35));
                        const padX1080 = isBubbleMode ? (20.0 + lPadX1080) : 40.0;
                        const maxTextW1080 = Math.max(50.0, boxW1080 - 2 * padX1080);
                        const fontSpec1080 = `${editState?.font_italic ? 'italic' : 'normal'} ${editState?.font_bold ? 'bold' : 'normal'} ${fontSize1080}px ${fontFamily}`;
                        const letterSp1080 = editState?.letter_spacing ?? 0;

                        const lines = (Array.isArray(editState?.title_lines) && editState.title_lines.length > 0)
                          ? editState.title_lines
                          : wrapTitleText(titleText, fontSpec1080, maxTextW1080, letterSp1080);

                        if (boxMode === 'capcut' && boxOpacity > 0) {
  // ── Authentic CapCut Continuous Bubble ──
  // (Hút chân không liền khối):
  // ── Uses CSS box-decoration-break clone ──
  // ── Wraps with exact lines matching canvas and PIL export 1:1 ──
                          return (
                            <div className="relative border-2 border-dashed border-cyan-400/80 hover:border-yellow-300 cursor-move transition-colors p-1"
                              style={{
                                width: `${boxW}px`,
                                textAlign: frameAlign,
                              }}>
                              {handles}
                              {textContent || (
                                <div style={{
                                  textAlign: frameAlign,
                                  lineHeight: editState?.line_height || 1.35,
                                  padding: `${padV}px ${padH}px`,
                                }}>
                                  <span style={{
                                    ...textStyle,
                                    display: 'inline',
                                    backgroundColor: `${boxHex}${boxAlpha}`,
                                    borderRadius: `${effRadPx}px`,
                                    boxDecorationBreak: 'clone',
                                    WebkitBoxDecorationBreak: 'clone',
                                    padding: `${padV}px ${padH}px`,
                                    boxShadow: `${padH}px 0 0 ${boxHex}${boxAlpha}, -${padH}px 0 0 ${boxHex}${boxAlpha}`,
                                    lineHeight: editState?.line_height || 1.35,
                                    wordBreak: 'break-word',
                                    whiteSpace: 'pre-line',
                                  }}>
                                    {lines.join('\n')}
                                  </span>
                                </div>
                              )}
                            </div>
                          );
                        }

                        if (boxMode === 'badges' && boxOpacity > 0) {
  // ── Separate Badges mode ──
  // (từng thanh rời có khe hở):
                          return (
                            <div className="relative border-2 border-dashed border-cyan-400/80 hover:border-yellow-300 cursor-move transition-colors p-1"
                              style={{ width: `${boxW}px` }}>
                              {handles}
                              {textContent || (
                                <div className="flex flex-col select-none" style={{
                                  alignItems: frameAlign === 'right' ? 'flex-end' : frameAlign === 'center' ? 'center' : 'flex-start',
                                }}>
                                  {lines.map((line, i) => (
                                    <div key={i} style={{
                                      display: 'flex',
                                      justifyContent: frameAlign === 'right' ? 'flex-end' : frameAlign === 'center' ? 'center' : 'flex-start',
                                      marginBottom: i < lines.length - 1 ? `${Math.max(2, Math.round(fontSize * 0.15))}px` : 0,
                                      maxWidth: '100%',
                                    }}>
                                      <span style={{
                                        ...textStyle,
                                        display: 'inline-block',
                                        backgroundColor: `${boxHex}${boxAlpha}`,
                                        borderRadius: `${effRadPx}px`,
                                        padding: `${padV}px ${padH}px`,
                                        lineHeight: 1.15,
                                        wordBreak: 'break-word',
                                        whiteSpace: 'pre-wrap',
                                      }}>{line || '\u00A0'}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        }

                        // ⬜ Frame mode (full-width rectangular box)
                        return (
                          <div className="relative border-2 border-dashed border-cyan-400/80 hover:border-yellow-300 cursor-move transition-colors"
                            style={{
                              width: `${boxW}px`,
                              backgroundColor: boxOpacity > 0 ? `${boxHex}${boxAlpha}` : 'transparent',
                              borderRadius: `${boxRadPx}px`,
                              padding: `${padV}px ${padH}px`,
                            }}>
                            {handles}
                            {textContent || (
                              <p style={{
                                ...textStyle,
                                textAlign: frameAlign,
                                wordBreak: 'break-word',
                                whiteSpace: 'pre-line',
                                lineHeight: editState?.line_height || 1.25,
                              }}>
                                {lines.join('\n')}
                              </p>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  );
                })()}

                {/* ???? Subtitle Overlay ?? live WYSIWYG preview matching sub_style, font, colors ???? */}
                {editState?.subtitles && (() => {
                  const subStyle = editState?.sub_style || 'Normal';
                  const marginPx = editState?.sub_margin_v || 200;
                  const subXPx   = editState?.sub_x || 0;
                  const bottomPct = Math.max(2, Math.min(80, (marginPx / 1920) * 100));
                  const subX = Math.round(subXPx * (324 / 1080));
                  const fontSize = Math.max(9, Math.round((editState?.sub_font_size || 36) * (324 / 1080)));
                  const highlightColor = editState?.sub_highlight_color || '#FFD700';
                  const dimColor = editState?.sub_dim_color || '#FFFFFF';
                  const subUppercase = editState?.sub_uppercase || false;
                  const subFontMap = {
                    arialbd:         '"Arial Bold", Arial, sans-serif',
                    impact:          'Impact, sans-serif',
                    bebas:           '"Bebas Neue", Impact, sans-serif',
                    anton:           '"Anton", Impact, sans-serif',
                    ariblk:          '"Arial Black", Arial, sans-serif',
                    gothicb:         '"Century Gothic", Arial, sans-serif',
                    verdanab:        '"Verdana", Arial, sans-serif',
                    arial:           'Arial, sans-serif',
  // ── Bundled fonts ──
  // loaded via @font-face from /api/font/file
                    montserrat:      'Montserrat, "Trebuchet MS", sans-serif',
                    luckiestguy:     '"Luckiest Guy", Impact, cursive',
                    nunito:          '"Nunito Light", "Century Gothic", sans-serif',
                    permanentmarker: '"Permanent Marker", "Comic Sans MS", cursive',
                  };
                  const subFF = subFontMap[editState?.sub_font_name || 'arialbd'] || 'Arial Bold';

                  let previewWords = ['Police', 'Officer', 'Exposes'];
                  if (editState?.words_data && editState.words_data.length >= 2) {
                    previewWords = editState.words_data.slice(0, 4).map(w => w.word);
                  } else if (editState?.srt_content) {
                    const lines = editState.srt_content.split(/\r?\n/).map(l => l.trim()).filter(l => l && !/^\d+$/.test(l) && !/-->/.test(l));
                    if (lines.length > 0) {
                      const parsed = lines[0].split(/\s+/).filter(Boolean);
                      if (parsed.length > 0) previewWords = parsed.slice(0, 4);
                    }
                  }
                  if (subUppercase) {
                    previewWords = previewWords.map(w => w.toUpperCase());
                  }
                  const sampleText = previewWords.join(' ');

  // ── Approximate ASS Outline ──
  // 3 Shadow=1 via CSS multi-shadow at preview scale
                  const bgBoxEnabled  = editState?.sub_bg_box || false;
                  const bgBoxColor    = editState?.sub_bg_box_color || '#000000';
                  const bgBoxOpacity  = (editState?.sub_bg_box_opacity ?? 80) / 100;
  // ── hex ──
                  const hexToRgba = (hex, alpha) => {
                    const h = hex.replace('#', '');
                    const r = parseInt(h.slice(0, 2), 16);
                    const g = parseInt(h.slice(2, 4), 16);
                    const b = parseInt(h.slice(4, 6), 16);
                    return `rgba(${r},${g},${b},${alpha})`;
                  };

  // ── When bg box is ──
  // active: no text-shadow outline; use colored background
                  const outlineShadow = bgBoxEnabled ? 'none' : [
                    '-1px -1px 0 #000', '1px -1px 0 #000',
                    '-1px  1px 0 #000', '1px  1px 0 #000',
                    ' 0px -1px 0 #000', '0px  1px 0 #000',
                    '-1px  0px 0 #000', '1px  0px 0 #000',
                    '2px 2px 4px rgba(0,0,0,0.75)',
                  ].join(', ');

  // ── CapCut box style shared props ──
const boxStyle = bgBoxEnabled ? {
                    display: 'inline-block',
                    backgroundColor: hexToRgba(bgBoxColor, bgBoxOpacity),
                    borderRadius: `${Math.round(fontSize * 0.25)}px`,
                    padding: `${Math.round(fontSize * 0.12)}px ${Math.round(fontSize * 0.28)}px`,
                    lineHeight: 1.25,
                  } : {};

                  const isSubSelected = selectedLayer?.type === 'subtitle';

                  return (
                    <div
                      onPointerDown={(e) => {
                        selectAndFocusLayer('subtitle');
                        if (e.target.dataset.handle) return;
                        if (!canvasRef.current) return;
                        dragRect.current      = canvasRef.current.getBoundingClientRect();
                        dragStartPos.current  = { x: e.clientX, y: e.clientY };
                        dragStartSub.current  = { margin_v: editState?.sub_margin_v ?? 200, x: editState?.sub_x ?? 0 };
                        subDragActive.current = true;
                        e.stopPropagation();
                        e.preventDefault();
                      }}
                      className={`absolute select-none z-30 transition-shadow pointer-events-auto cursor-grab active:cursor-grabbing text-center ${
                        isSubSelected
                          ? 'ring-2 ring-emerald-400/90 bg-emerald-950/25 rounded-md px-2.5 py-1.5 shadow-xl'
                          : 'hover:ring-1 hover:ring-emerald-400/50 rounded-md px-2 py-1'
                      }`}
                      style={{
                        bottom: `${bottomPct}%`,
                        left: '50%',
                        transform: `translateX(calc(-50% + ${subX}px))`,
                        maxWidth: '92%',
                        width: 'max-content',
                      }}>

                      {/* Subtitle Handles and Mini Toolbar when selected */}
                      {isSubSelected && (
                        <>
                          <div className="absolute -top-7 left-1/2 -translate-x-1/2 flex items-center gap-1.5 bg-gray-950/95 border border-emerald-500/60 text-emerald-300 text-[8px] font-bold px-2 py-0.5 rounded-full shadow-lg whitespace-nowrap z-50 pointer-events-auto">
                            <span className="flex items-center gap-1">💬 Phụ đề</span>
                            <span className="text-gray-500">•</span>
                            <span>Cỡ: {editState?.sub_font_size || 36}px</span>
                            <span className="text-gray-500">•</span>
                            <span>Y: {editState?.sub_margin_v || 200}px</span>
                            {(editState?.sub_x || 0) !== 0 && (
                              <>
                                <span className="text-gray-500">•</span>
                                <button
                                  type="button"
                                  onPointerDown={(e) => {
                                    e.stopPropagation();
                                    patchEdit({ sub_x: 0 });
                                  }}
                                  className="text-amber-300 hover:text-amber-200 underline cursor-pointer"
                                  title="Căn lại giữa ngang">
                                  ↺ Giữa
                                </button>
                              </>
                            )}
                          </div>

                          {/* 4 Corner Resize Handles for sub_font_size */}
                          <div
                            className="absolute -top-1.5 -left-1.5 w-3.5 h-3.5 rounded-sm bg-white border-2 border-emerald-500 shadow cursor-nwse-resize hover:scale-125 transition-transform z-40"
                            data-handle="resize-tl"
                            onPointerDown={(e) => startSubtitleCornerResize(e, 'tl')}
                            title="Kéo góc để chỉnh cỡ chữ phụ đề"
                          />
                          <div
                            className="absolute -top-1.5 -right-1.5 w-3.5 h-3.5 rounded-sm bg-white border-2 border-emerald-500 shadow cursor-nesw-resize hover:scale-125 transition-transform z-40"
                            data-handle="resize-tr"
                            onPointerDown={(e) => startSubtitleCornerResize(e, 'tr')}
                            title="Kéo góc để chỉnh cỡ chữ phụ đề"
                          />
                          <div
                            className="absolute -bottom-1.5 -left-1.5 w-3.5 h-3.5 rounded-sm bg-white border-2 border-emerald-500 shadow cursor-nesw-resize hover:scale-125 transition-transform z-40"
                            data-handle="resize-bl"
                            onPointerDown={(e) => startSubtitleCornerResize(e, 'bl')}
                            title="Kéo góc để chỉnh cỡ chữ phụ đề"
                          />
                          <div
                            className="absolute -bottom-1.5 -right-1.5 w-3.5 h-3.5 rounded-sm bg-white border-2 border-emerald-500 shadow cursor-nwse-resize hover:scale-125 transition-transform z-40"
                            data-handle="resize-br"
                            onPointerDown={(e) => startSubtitleCornerResize(e, 'br')}
                            title="Kéo góc để chỉnh cỡ chữ phụ đề"
                          />
                        </>
                      )}
                      {subStyle === 'Word Pop' || subStyle === 'Highlight Line' || subStyle === 'Viral Bounce' ? (
                        <p style={{
                          fontSize: `${fontSize}px`,
                          fontWeight: editState?.sub_bold !== false ? 'bold' : 'normal',
                          fontStyle: editState?.sub_italic ? 'italic' : 'normal',
                          fontFamily: subFF,
                          letterSpacing: '0.02em',
                          lineHeight: bgBoxEnabled ? 1.6 : 1.2,
                          textShadow: outlineShadow,
                          transform: subStyle === 'Viral Bounce' ? 'scale(1.04)' : 'none',
                        }}>
                          {bgBoxEnabled ? (
                            <>
                              {previewWords.map((pw, pwi) => {
                                const isHl = subStyle === 'Word Pop' || subStyle === 'Viral Bounce' || pwi === 0;
                                const clr = isHl ? highlightColor : dimColor;
                                return (
                                  <span
                                    key={pwi}
                                    style={{
                                      ...boxStyle,
                                      color: clr,
                                      marginRight: pwi < previewWords.length - 1 ? `${Math.round(fontSize * 0.12)}px` : 0
                                    }}>
                                    {pw}
                                  </span>
                                );
                              })}
                            </>
                          ) : (
                            <>
                              {previewWords.map((pw, pwi) => {
                                const isHl = subStyle === 'Word Pop' || subStyle === 'Viral Bounce' || pwi === 0;
                                const clr = isHl ? highlightColor : dimColor;
                                return (
                                  <React.Fragment key={pwi}>
                                    <span style={{ color: clr }}>{pw}</span>
                                    {pwi < previewWords.length - 1 && ' '}
                                  </React.Fragment>
                                );
                              })}
                            </>
                          )}
                        </p>
                      ) : (
  // ── Normal mode ──
bgBoxEnabled ? (
  // ── CapCut ──
  // box: wrapping container with bg, then text
                          <div style={{
                            display: 'inline-block',
                            textAlign: 'center',
                          }}>
                            <p style={{
                              ...boxStyle,
                              fontSize: `${fontSize}px`,
                              fontFamily: subFF,
                              fontWeight: editState?.sub_bold !== false ? 'bold' : 'normal',
                              fontStyle: editState?.sub_italic ? 'italic' : 'normal',
                              color: dimColor,
                              lineHeight: 1.25,
                              textShadow: 'none',
                              whiteSpace: 'normal',
                              wordBreak: 'break-word',
                            }}>
                              {sampleText}
                            </p>
                          </div>
                        ) : (
                          <p style={{
                            fontSize: `${fontSize}px`,
                            fontFamily: subFF,
                            fontWeight: editState?.sub_bold !== false ? 'bold' : 'normal',
                            fontStyle: editState?.sub_italic ? 'italic' : 'normal',
                            color: dimColor,
                            lineHeight: 1.2,
                            textShadow: outlineShadow,
                          }}>
                            {sampleText}
                          </p>
                        )
                      )}
                    </div>
                  );
                })()}



                {/* Blur Mask indicator lines — top/bottom crop guide on foreground video */}
                {(editState?.source_mask_top > 0 || editState?.source_mask_bottom > 0) && (() => {
                  const { fgX = 0, fgY = 0, fgW = 324, fgH = 182 } = videoFrameRef.current || {};
                  const topVal = editState?.source_mask_top || 0;
                  const botVal = (editState?.source_mask_mode === 'bottom' || editState?.source_mask_mode === 'both')
                                 ? (editState?.source_mask_bottom || 0) : 0;
                  const lineTopY = fgY + topVal * fgH;
                  const lineBotY = fgY + fgH - botVal * fgH;

                  return (
                    <>
                      {topVal > 0 && (
                        <div className="absolute border-b border-dashed border-cyan-400/80 pointer-events-none flex justify-end px-1 z-20"
                          style={{ left: `${fgX}px`, top: `${lineTopY}px`, width: `${fgW}px` }}>
                          <span className="text-[7px] bg-cyan-950/90 text-cyan-300 px-1 rounded -mt-2.5 font-bold shadow">
                            Top Mask {(topVal * 100).toFixed(0)}%
                          </span>
                        </div>
                      )}
                      {botVal > 0 && (
                        <div className="absolute border-t border-dashed border-cyan-400/80 pointer-events-none flex justify-end px-1 z-20"
                          style={{ left: `${fgX}px`, top: `${lineBotY}px`, width: `${fgW}px` }}>
                          <span className="text-[7px] bg-cyan-950/90 text-cyan-300 px-1 rounded -mb-2.5 font-bold shadow">
                            Bottom Mask {(botVal * 100).toFixed(0)}%
                          </span>
                        </div>
                      )}
                    </>
                  );
                })()}

                {/* ???? Multitrack Overlay Layers (Interactive Drag, Resize, Rotate & BiRefNet Cutout Preview) ???? */}
                {(editState?.overlays || []).map((ovl, idx) => {
                  if (ovl.enabled === false) return null;
                  const left = (ovl.x / 1080) * 100;
                  const top = (ovl.y / 1920) * 100;
                  const width = (ovl.w / 1080) * 100;
                  const height = (ovl.h / 1920) * 100;
                  const opacity = (ovl.opacity ?? 100) / 100;
                  const rotation = ovl.rotation ?? 0;
                  const isSelected = selOverlayIdx === idx;
                  const isImg = ovl.type !== 'video';
                  const assetUrl = toAssetUrl(ovl.remove_bg && ovl.remove_bg_url ? ovl.remove_bg_url : ovl.url);

  // ── Check timeline visibility ──
const stTime = ovl.start_time ?? 0;
                  const endTime = ovl.end_time ?? 0;
                  const hasTime = stTime > 0 || endTime > 0;
                  const isVisible = !hasTime || (currentTime >= stTime && (endTime > 0 ? currentTime <= endTime : true));

                  if (!isVisible && !isSelected) return null;

                  return (
                    <div
                      key={ovl.id || idx}
                      onPointerDown={(e) => {
                        selectAndFocusLayer('overlay', idx);
                        if (e.target.dataset.handle) return;
                        startOverlayMove(e, idx);
                      }}
                      className={`absolute select-none pointer-events-auto cursor-move transition-shadow ${
                        isSelected
                          ? !isVisible
                            ? 'ring-2 ring-dashed ring-amber-400 border border-dashed border-amber-300 z-35'
                            : 'ring-2 ring-pink-500 border border-pink-400 z-35 shadow-2xl'
                          : 'hover:ring-1 hover:ring-pink-400/60 z-25'
                      }`}
                      style={{
                        left: `${left}%`,
                        top: `${top}%`,
                        width: `${width}%`,
                        height: `${height}%`,
                        opacity: !isVisible && isSelected ? Math.min(opacity, 0.35) : opacity,
                        transform: `rotate(${rotation}deg)`,
                        transformOrigin: 'center center',
                      }}>
                      {/* ── Inactive timeline indicator badge when selected ── */}
                      {!isVisible && isSelected && (
                        <div className="absolute -top-4 inset-x-0 flex justify-center pointer-events-none z-50">
                          <span className="bg-amber-950/95 text-amber-300 border border-amber-500/60 text-[6px] font-bold px-1 py-0.2 rounded shadow whitespace-nowrap">
                            ?? Ẩn tại {currentTime.toFixed(1)}s (Chỉ hiện {stTime.toFixed(0)}s - {endTime > 0 ? endTime.toFixed(0) + 's' : 'Hết'})
                          </span>
                        </div>
                      )}
                      {/* ── Asset Media Element ── */}
                      {isImg ? (
                        <img
                          src={assetUrl}
                          alt=""
                          draggable={false}
                          className="w-full h-full object-contain pointer-events-none"
                          style={{ filter: isSelected ? 'drop-shadow(0 0 4px rgba(236,72,153,0.5))' : 'none' }}
                        />
                      ) : (
                        <video
                          src={assetUrl}
                          muted
                          playsInline
                          autoPlay
                          loop
                          className="w-full h-full object-contain pointer-events-none"
                        />
                      )}

                      {/* Selection Handles (Top Rotate Handle + 4 Corner Resize Handles) */}
                      {isSelected && (
                        <>
                          {/* ── Rotate Handle ── */}
                          <div
                            className="absolute -top-6 left-1/2 -translate-x-1/2 flex flex-col items-center pointer-events-auto z-40 cursor-grab active:cursor-grabbing"
                            data-handle="rotate"
                            onPointerDown={(e) => startOverlayRotate(e, idx)}>
                            <div className="w-4 h-4 rounded-full bg-pink-600 border border-pink-200 text-white flex items-center justify-center shadow-lg hover:scale-125 transition-transform"
                              title="Kéo sang trái/phải để xoay layer">
                              <RotateCw className="w-2.5 h-2.5" />
                            </div>
                            <div className="w-0.5 h-1.5 bg-pink-400/80" />
                          </div>

                          {/* ── 4 Corner Resize Handles ── */}
                          <div
                            className="absolute -top-1.5 -left-1.5 w-3 h-3 rounded-full bg-white border-2 border-pink-500 shadow cursor-nwse-resize hover:scale-125 transition-transform z-40"
                            data-handle="resize-tl"
                            onPointerDown={(e) => startOverlayResize(e, idx, 'tl')}
                          />
                          <div
                            className="absolute -top-1.5 -right-1.5 w-3 h-3 rounded-full bg-white border-2 border-pink-500 shadow cursor-nesw-resize hover:scale-125 transition-transform z-40"
                            data-handle="resize-tr"
                            onPointerDown={(e) => startOverlayResize(e, idx, 'tr')}
                          />
                          <div
                            className="absolute -bottom-1.5 -left-1.5 w-3 h-3 rounded-full bg-white border-2 border-pink-500 shadow cursor-nesw-resize hover:scale-125 transition-transform z-40"
                            data-handle="resize-bl"
                            onPointerDown={(e) => startOverlayResize(e, idx, 'bl')}
                          />
                          <div
                            className="absolute -bottom-1.5 -right-1.5 w-3 h-3 rounded-full bg-white border-2 border-pink-500 shadow cursor-nwse-resize hover:scale-125 transition-transform z-40"
                            data-handle="resize-br"
                            onPointerDown={(e) => startOverlayResize(e, idx, 'br')}
                          />
                        </>
                      )}
                    </div>
                  );
                })}

                {/* ── Active Blur Box Draw Rectangle  ── */}
                {drawMode && drawStart && drawCurrent && (() => {
                  const minX = Math.min(drawStart.x, drawCurrent.x);
                  const minY = Math.min(drawStart.y, drawCurrent.y);
                  const w = Math.abs(drawCurrent.x - drawStart.x);
                  const h = Math.abs(drawCurrent.y - drawStart.y);
                  return (
                    <div className="absolute border-2 border-dashed border-yellow-300 bg-yellow-400/20 z-40 pointer-events-none"
                      style={{ left: `${minX}px`, top: `${minY}px`, width: `${w}px`, height: `${h}px` }}>
                      <span className="text-[7px] bg-yellow-400 text-black font-bold px-1 rounded shadow">Drawing Blur Box</span>
                    </div>
                  );
                })()}

                {/* ── Existing Blur Boxes overlays (Interactive Drag to Move & 4-Corner Resize) ── */}
                {(editState?.blur_boxes || []).map((b, idx) => {
                  const { fgX, fgY, fgW, fgH } = videoFrameRef.current;
                  const boxStyle = b.video_rel
                    ? { left: `${fgX + b.x * fgW}px`, top: `${fgY + b.y * fgH}px`, width: `${b.w * fgW}px`, height: `${b.h * fgH}px` }
                    : { left: `${(b.x / 1080) * 100}%`, top: `${(b.y / 1920) * 100}%`, width: `${(b.w / 1080) * 100}%`, height: `${(b.h / 1920) * 100}%` };
                  const isSelected = selBlurBoxIdx === idx;
                  const modeIcon = b.mode === 'delogo' ? '🔍' : b.mode === 'inpaint' ? '🧹' : '🫧';

                  // ── Timed box activity check relative to currentTime ──
                  const stTime = b.start_time ?? 0;
                  const endTime = b.end_time ?? 0;
                  const hasTime = stTime > 0 || endTime > 0;
                  const isActive = !hasTime || (currentTime >= stTime && (endTime > 0 ? currentTime <= endTime : true));

                  return (
                    <div key={b.id || idx}
                      onPointerDown={(e) => {
                        selectAndFocusLayer('blur_box', idx);
                        startBlurBoxMove(e, idx);
                      }}
                      className={`blur-box-item absolute border-2 rounded-sm select-none pointer-events-auto flex items-start justify-between p-0.5 cursor-move transition-all ${
                        isSelected
                          ? 'border-yellow-400/90 bg-transparent z-30 shadow-lg ring-1 ring-yellow-400/40 opacity-100'
                          : isActive
                            ? 'border-cyan-400/70 bg-transparent z-20 hover:border-cyan-300 opacity-80'
                            : 'border-gray-500/30 bg-transparent z-10 opacity-20 hover:opacity-60'
                      }`}
                      style={boxStyle}>
                      
                      <span className="text-[7px] font-bold bg-black/80 text-cyan-300 px-1 rounded leading-none flex items-center gap-0.5">
                        {modeIcon} #{idx + 1}
                        {hasTime && <span className={isActive ? "text-amber-400 font-bold" : "text-gray-500"}>⏱{stTime.toFixed(1)}s-{endTime.toFixed(1)}s</span>}
                      </span>
                      
                      <button onClick={(e) => {
                        e.stopPropagation();
                        patchEdit({ blur_boxes: (editState?.blur_boxes || []).filter((_, i) => i !== idx) });
                        if (selBlurBoxIdx === idx) setSelBlurBoxIdx(-1);
                      }} className="text-[8px] font-bold text-white bg-red-600/90 hover:bg-red-600 rounded-full w-3.5 h-3.5 flex items-center justify-center leading-none">×</button>

                      {/* ── 4 Corner Resize Handles when selected ── */}
                      {isSelected && (
                        <>
                          <div className="absolute -top-1.5 -left-1.5 w-3 h-3 rounded-full bg-yellow-300 border-2 border-black shadow cursor-nwse-resize hover:scale-125 transition-transform z-40"
                            data-handle="resize-tl"
                            onPointerDown={(e) => startBlurBoxResize(e, idx, 'tl')} />
                          <div className="absolute -top-1.5 -right-1.5 w-3 h-3 rounded-full bg-yellow-300 border-2 border-black shadow cursor-nesw-resize hover:scale-125 transition-transform z-40"
                            data-handle="resize-tr"
                            onPointerDown={(e) => startBlurBoxResize(e, idx, 'tr')} />
                          <div className="absolute -bottom-1.5 -left-1.5 w-3 h-3 rounded-full bg-yellow-300 border-2 border-black shadow cursor-nesw-resize hover:scale-125 transition-transform z-40"
                            data-handle="resize-bl"
                            onPointerDown={(e) => startBlurBoxResize(e, idx, 'bl')} />
                          <div className="absolute -bottom-1.5 -right-1.5 w-3 h-3 rounded-full bg-yellow-300 border-2 border-black shadow cursor-nwse-resize hover:scale-125 transition-transform z-40"
                            data-handle="resize-br"
                            onPointerDown={(e) => startBlurBoxResize(e, idx, 'br')} />
                        </>
                      )}
                    </div>
                  );
                })}

                <div className="absolute bottom-2 inset-x-0 text-center pointer-events-none z-10">
                  <span className="bg-black/60 px-2 py-0.5 rounded-full text-[8px] text-gray-500">
                    {drawMode ? '✏️ Click & Drag on preview to draw blur box' : '↕ Drag to move title'}
                  </span>
                </div>

                {/* F6: Frame border — z-50, renders on TOP of all content (clips visual overflow) */}
                <div className="absolute inset-0 rounded-2xl border border-gray-700/70 pointer-events-none z-50" />
              </div>

              {/* CapCut-Style Media Control Bar & Multitrack Timeline */}
              {(() => {
                const origVidDur = duration || 16;
                const effectiveVideoDur = (editState?.video_trim_dur > 0 && editState.video_trim_dur < origVidDur)
                  ? editState.video_trim_dur
                  : origVidDur;
                const caOffset = editState?.custom_audio_offset || 0;
                const caTrimStart = editState?.custom_audio_trim_start || 0;
                const caRawDur = editState?.custom_audio_dur || 0;
                const caTrimDur = (editState?.custom_audio_trim_dur > 0)
                  ? editState.custom_audio_trim_dur
                  : Math.max(0, caRawDur - caTrimStart);
                const effectiveAudioEnd = editState?.custom_audio_path ? (caOffset + caTrimDur) : 0;

                // timelineScaleDur: The fixed visual time ruler across all tracks.
                // Must be based on origVidDur (not effectiveVideoDur) so trimming the video visibly shrinks the bar!
                const timelineScaleDur = Math.max(origVidDur, effectiveAudioEnd, 1);

                // masterTimelineDur: The actual playback duration of the current project.
                const masterTimelineDur = Math.max(effectiveVideoDur, effectiveAudioEnd, 1);
                const isAudioExtending = effectiveAudioEnd > effectiveVideoDur;

                return (
                  <>
                    <div className="w-full max-w-[324px] bg-gray-900/90 border border-gray-800/80 rounded-xl p-2 flex items-center gap-2 shadow-lg shrink-0">
                      <button
                        onClick={() => setIsPlaying(!isPlaying)}
                        className={`p-1.5 rounded-lg transition shadow flex items-center justify-center shrink-0 ${
                          isPlaying ? 'bg-amber-600 hover:bg-amber-500 text-white' : 'bg-indigo-600 hover:bg-indigo-500 text-white'
                        }`}
                        title={isPlaying ? 'Tạm dừng (Space)' : 'Phát (Space)'}>
                        {isPlaying ? <Square className="w-3.5 h-3.5 fill-current" /> : <Film className="w-3.5 h-3.5 fill-current" />}
                      </button>

                      <input
                        type="range"
                        min={0}
                        max={masterTimelineDur}
                        step={0.05}
                        value={Math.min(currentTime, masterTimelineDur)}
                        onChange={(e) => {
                          const t = parseFloat(e.target.value);
                          setCurrentTime(t);
                          if (videoRef.current) {
                            videoRef.current.currentTime = Math.min(t, effectiveVideoDur);
                          }
                        }}
                        className="flex-1 accent-indigo-500 h-1.5 bg-gray-800 rounded cursor-pointer"
                      />

                      <span className="text-[9px] font-mono text-indigo-300 shrink-0 min-w-[70px] text-right">
                        {currentTime.toFixed(1)}s / {masterTimelineDur.toFixed(1)}s
                      </span>
                    </div>

                    {/* ── CapCut-Style Multitrack Timeline Tracks ── */}
                    {Boolean(currentEditItem) && (
                      <div className="w-full max-w-[324px] bg-[#0c0d16] border border-gray-800/80 rounded-xl p-2.5 space-y-2 shadow-xl shrink-0 select-none">
                        {/* Header: Title & Total Info */}
                        <div className="flex items-center justify-between px-0.5 pb-1 border-b border-gray-800/60">
                          <div className="flex items-center gap-1.5">
                            <Layers className="w-3 h-3 text-pink-400" />
                            <span className="text-[9px] font-bold text-gray-300 tracking-wide uppercase">Timeline CapCut</span>
                          </div>
                          <div className="flex items-center gap-1 text-[8px] font-mono">
                            {isAudioExtending ? (
                              <span className="text-emerald-400 font-semibold bg-emerald-950/60 border border-emerald-800/60 px-1 py-0.5 rounded" title="Audio dài hơn video, phần cuối tự động bù màn đen">
                                ⏱️ {masterTimelineDur.toFixed(1)}s (Hình {effectiveVideoDur.toFixed(1)}s + Đen {(effectiveAudioEnd - effectiveVideoDur).toFixed(1)}s)
                              </span>
                            ) : (
                              <span className="text-gray-400">
                                ⏱️ Tổng: <strong className="text-indigo-300">{masterTimelineDur.toFixed(1)}s</strong>
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Tracks Area (Video + Audio + Overlays) */}
                        <div className="space-y-1.5 relative">
                          {/* Master Playhead Line across all tracks */}
                          <div
                            className="absolute top-0 bottom-0 w-0.5 bg-cyan-400 pointer-events-none z-30 shadow-[0_0_8px_rgba(34,211,238,0.8)]"
                            style={{ left: `${Math.max(0, Math.min(100, (currentTime / timelineScaleDur) * 100))}%` }}>
                            <div className="w-2 h-2 bg-cyan-400 rotate-45 -ml-[3px] -mt-1 rounded-[1px]" />
                          </div>

                          {/* ── Track 1: Video chính (Indigo Track with Right Trim Handle) ── */}
                          <div
                            onClick={() => selectAndFocusLayer('video')}
                            className={`group rounded-lg bg-gray-950/80 p-1 space-y-0.5 cursor-pointer transition ${
                              selectedLayer?.type === 'video'
                                ? 'border-2 border-indigo-400 ring-1 ring-indigo-500/40 shadow-lg'
                                : 'border border-indigo-900/50 hover:border-indigo-600'
                            }`}>
                            <div className="flex items-center justify-between text-[7px] px-0.5 text-gray-400">
                              <span className="flex items-center gap-1 font-bold text-indigo-300">
                                <Film className="w-2.5 h-2.5 text-indigo-400" /> Video chính
                                {editState?.video_trim_dur > 0 && (
                                  <span className="text-amber-400 font-normal">({effectiveVideoDur.toFixed(1)}s / gốc {origVidDur.toFixed(1)}s)</span>
                                )}
                              </span>
                              {editState?.video_trim_dur > 0 && (
                                <button
                                  onClick={() => patchEdit({ video_trim_dur: 0 })}
                                  className="text-amber-400 hover:text-amber-200 underline text-[7px]"
                                  title="Khôi phục độ dài video gốc">
                                  ↺ Khôi phục gốc
                                </button>
                              )}
                            </div>

                            {/* Video Track Bar Container */}
                            <div
                              className="relative h-6 bg-black/90 rounded border border-indigo-950/90 overflow-hidden cursor-pointer"
                              onClick={(e) => {
                                const rect = e.currentTarget.getBoundingClientRect();
                                const clickX = e.clientX - rect.left;
                                const newT = Math.max(0, Math.min(masterTimelineDur, (clickX / rect.width) * timelineScaleDur));
                                setCurrentTime(newT);
                                if (videoRef.current) videoRef.current.currentTime = Math.min(newT, effectiveVideoDur);
                              }}>
                              {/* Video Active Clip Block */}
                              <div
                                className="absolute top-0 bottom-0 left-0 rounded-l flex items-center bg-gradient-to-r from-indigo-700 via-indigo-600 to-purple-600 border border-indigo-400/60 shadow-md"
                                style={{ width: `${Math.max(2, (effectiveVideoDur / timelineScaleDur) * 100)}%` }}>
                                <span className="truncate px-1.5 text-[7px] font-bold text-white flex items-center gap-1 select-none pointer-events-none flex-1">
                                  🎬 {effectiveVideoDur.toFixed(1)}s
                                </span>

                                {/* Video Right Trim Handle (Kéo thu gọn đuôi Video) */}
                                <div
                                  onPointerDown={(e) => {
                                    e.stopPropagation();
                                    e.preventDefault();
                                    const trackContainer = e.currentTarget.parentElement?.parentElement;
                                    const rect = trackContainer ? trackContainer.getBoundingClientRect() : { left: 0, width: 280 };
                                    const scaleDur = timelineScaleDur;

                                    const onMove = (me) => {
                                      const mouseX = me.clientX - rect.left;
                                      const targetSec = (mouseX / rect.width) * scaleDur;
                                      let newDur = Math.max(0.5, Math.min(origVidDur, targetSec));
                                      if (newDur >= origVidDur - 0.2) {
                                        newDur = 0; // Snap to full original video
                                      } else {
                                        newDur = parseFloat(newDur.toFixed(2));
                                      }
                                      patchEdit({ video_trim_dur: newDur });
                                    };
                                    const onUp = () => {
                                      window.removeEventListener('pointermove', onMove);
                                      window.removeEventListener('pointerup', onUp);
                                    };
                                    window.addEventListener('pointermove', onMove);
                                    window.addEventListener('pointerup', onUp);
                                  }}
                                  className="w-3 h-full bg-white/20 hover:bg-white/50 active:bg-white text-indigo-950 rounded-r flex items-center justify-center cursor-ew-resize select-none shrink-0 transition"
                                  title="Kéo sang trái để thu gọn video, kéo sang phải để kéo dài">
                                  <div className="w-0.5 h-2.5 bg-white/90 rounded-full" />
                                </div>
                              </div>

                              {/* Black Screen padding indicator if audio extends */}
                              {isAudioExtending && (
                                <div
                                  className="absolute top-0 bottom-0 bg-black/90 border-l border-dashed border-gray-700 flex items-center justify-center text-[6.5px] text-gray-400 font-mono select-none pointer-events-none overflow-hidden"
                                  style={{
                                    left: `${(effectiveVideoDur / timelineScaleDur) * 100}%`,
                                    width: `${((effectiveAudioEnd - effectiveVideoDur) / timelineScaleDur) * 100}%`,
                                  }}>
                                  ⬛ Màn đen (+{(effectiveAudioEnd - effectiveVideoDur).toFixed(1)}s)
                                </div>
                              )}
                            </div>
                          </div>

                          {/* ── Track 2: Âm thanh lồng ghép (Emerald Track with Left & Right Trim Handles) ── */}
                          {editState?.custom_audio_path ? (
                            <div className="group rounded-lg bg-gray-950/80 border border-emerald-900/50 p-1 space-y-0.5">
                              <div className="flex items-center justify-between text-[7px] px-0.5 text-gray-400">
                                <span className="flex items-center gap-1 font-bold text-emerald-300">
                                  <Volume2 className="w-2.5 h-2.5 text-emerald-400" /> Audio: {editState.custom_audio_name || 'Lồng ngoài'}
                                  <span className="text-emerald-500 font-normal">({caTrimDur.toFixed(1)}s{caOffset > 0 ? ` @ +${caOffset.toFixed(1)}s` : ''})</span>
                                </span>
                                <div className="flex items-center gap-1.5">
                                  {(caTrimStart > 0 || (editState?.custom_audio_trim_dur > 0 && editState.custom_audio_trim_dur < caRawDur) || caOffset !== 0) && (
                                    <button
                                      onClick={() => patchEdit({ custom_audio_trim_start: 0, custom_audio_trim_dur: caRawDur, custom_audio_offset: 0 })}
                                      className="text-amber-400 hover:text-amber-200 underline text-[7px]"
                                      title="Khôi phục âm thanh gốc">
                                      ↺ Đặt lại
                                    </button>
                                  )}
                                  <button
                                    onClick={() => audioFileInputRef.current?.click()}
                                    className="text-gray-400 hover:text-gray-200 text-[7px]">
                                    Đổi
                                  </button>
                                  <button
                                    onClick={() => patchEdit({ custom_audio_path: '', custom_audio_name: '', custom_audio_url: '', custom_audio_dur: 0, orig_volume: 100 })}
                                    className="text-red-400 hover:text-red-300 text-[7px]">
                                    Xóa
                                  </button>
                                </div>
                              </div>

                              {/* Audio Track Bar Container */}
                              <div
                                className="relative h-6 bg-black/90 rounded border border-emerald-950/90 overflow-hidden cursor-pointer"
                                onClick={(e) => {
                                  const rect = e.currentTarget.getBoundingClientRect();
                                  const clickX = e.clientX - rect.left;
                                  const newT = Math.max(0, Math.min(masterTimelineDur, (clickX / rect.width) * timelineScaleDur));
                                  setCurrentTime(newT);
                                  if (videoRef.current) videoRef.current.currentTime = Math.min(newT, effectiveVideoDur);
                                }}>
                                {/* Audio Clip Block */}
                                <div
                                  className="absolute top-0 bottom-0 rounded flex items-center bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-700 border border-emerald-400/60 shadow-md"
                                  style={{
                                    left: `${(Math.max(0, caOffset) / timelineScaleDur) * 100}%`,
                                    width: `${Math.max(2, (caTrimDur / timelineScaleDur) * 100)}%`,
                                  }}>
                                  {/* Left Trim Handle (Trim In - Kéo thu gọn đầu audio) */}
                                  <div
                                    onPointerDown={(e) => {
                                      e.stopPropagation();
                                      e.preventDefault();
                                      const startX = e.clientX;
                                      const fullDur = caRawDur || 30;
                                      const initialTrimStart = editState?.custom_audio_trim_start || 0;
                                      const initialTrimDur = (editState?.custom_audio_trim_dur > 0)
                                        ? editState.custom_audio_trim_dur
                                        : (fullDur - initialTrimStart);
                                      const initialOffset = editState?.custom_audio_offset || 0;
                                      const trackContainer = e.currentTarget.parentElement?.parentElement;
                                      const trackWidth = trackContainer ? trackContainer.getBoundingClientRect().width : 280;
                                      const scaleDur = timelineScaleDur;

                                      const onMove = (me) => {
                                        const deltaPx = me.clientX - startX;
                                        const deltaSec = (deltaPx / trackWidth) * scaleDur;
                                        let newTrimStart = Math.max(0, Math.min(fullDur - 0.5, initialTrimStart + deltaSec));
                                        let actualDelta = newTrimStart - initialTrimStart;
                                        let newTrimDur = Math.max(0.5, initialTrimDur - actualDelta);
                                        let newOffset = initialOffset + actualDelta;

                                        patchEdit({
                                          custom_audio_trim_start: parseFloat(newTrimStart.toFixed(2)),
                                          custom_audio_trim_dur: parseFloat(newTrimDur.toFixed(2)),
                                          custom_audio_offset: parseFloat(newOffset.toFixed(2)),
                                        });
                                      };
                                      const onUp = () => {
                                        window.removeEventListener('pointermove', onMove);
                                        window.removeEventListener('pointerup', onUp);
                                      };
                                      window.addEventListener('pointermove', onMove);
                                      window.addEventListener('pointerup', onUp);
                                    }}
                                    className="w-3 h-full bg-white/20 hover:bg-white/50 active:bg-white text-emerald-950 rounded-l flex items-center justify-center cursor-ew-resize select-none shrink-0 transition"
                                    title="Kéo sang phải để cắt bỏ đoạn đầu của audio">
                                    <div className="w-0.5 h-2.5 bg-white/90 rounded-full" />
                                  </div>

                                  {/* Middle Body (Drag Offset/Position) */}
                                  <div
                                    onPointerDown={(e) => {
                                      e.stopPropagation();
                                      e.preventDefault();
                                      const startX = e.clientX;
                                      const initialOffset = editState?.custom_audio_offset || 0;
                                      const trackContainer = e.currentTarget.parentElement?.parentElement;
                                      const trackWidth = trackContainer ? trackContainer.getBoundingClientRect().width : 280;
                                      const scaleDur = timelineScaleDur;

                                      const onMove = (me) => {
                                        const deltaPx = me.clientX - startX;
                                        const deltaSec = (deltaPx / trackWidth) * scaleDur;
                                        let newOffset = Math.max(-10, Math.min(scaleDur + 10, initialOffset + deltaSec));
                                        patchEdit({
                                          custom_audio_offset: parseFloat(newOffset.toFixed(2)),
                                        });
                                      };
                                      const onUp = () => {
                                        window.removeEventListener('pointermove', onMove);
                                        window.removeEventListener('pointerup', onUp);
                                      };
                                      window.addEventListener('pointermove', onMove);
                                      window.addEventListener('pointerup', onUp);
                                    }}
                                    className="flex-1 h-full px-1 flex items-center justify-between text-[7px] font-bold text-emerald-100 cursor-grab active:cursor-grabbing select-none overflow-hidden"
                                    title="Giữ chuột kéo trượt trái / phải để dịch chuyển vị trí phát audio">
                                    <span className="truncate flex items-center gap-0.5">
                                      🎵 {editState.custom_audio_name || 'Audio'}
                                    </span>
                                    <span className="shrink-0 opacity-90 font-mono text-[6.5px]">
                                      {caOffset > 0 ? `+${caOffset.toFixed(1)}s` : `${caOffset.toFixed(1)}s`}
                                    </span>
                                  </div>

                                  {/* Right Trim Handle (Trim Out - Kéo thu gọn đuôi audio) */}
                                  <div
                                    onPointerDown={(e) => {
                                      e.stopPropagation();
                                      e.preventDefault();
                                      const startX = e.clientX;
                                      const fullDur = caRawDur || 30;
                                      const currentTrimStart = editState?.custom_audio_trim_start || 0;
                                      const initialTrimDur = (editState?.custom_audio_trim_dur > 0)
                                        ? editState.custom_audio_trim_dur
                                        : (fullDur - currentTrimStart);
                                      const maxAllowedDur = fullDur - currentTrimStart;
                                      const trackContainer = e.currentTarget.parentElement?.parentElement;
                                      const trackWidth = trackContainer ? trackContainer.getBoundingClientRect().width : 280;
                                      const scaleDur = timelineScaleDur;

                                      const onMove = (me) => {
                                        const deltaPx = me.clientX - startX;
                                        const deltaSec = (deltaPx / trackWidth) * scaleDur;
                                        let newTrimDur = Math.max(0.5, Math.min(maxAllowedDur, initialTrimDur + deltaSec));
                                        patchEdit({
                                          custom_audio_trim_dur: parseFloat(newTrimDur.toFixed(2)),
                                        });
                                      };
                                      const onUp = () => {
                                        window.removeEventListener('pointermove', onMove);
                                        window.removeEventListener('pointerup', onUp);
                                      };
                                      window.addEventListener('pointermove', onMove);
                                      window.addEventListener('pointerup', onUp);
                                    }}
                                    className="w-3 h-full bg-white/20 hover:bg-white/50 active:bg-white text-emerald-950 rounded-r flex items-center justify-center cursor-ew-resize select-none shrink-0 transition"
                                    title="Kéo sang trái để thu gọn đuôi audio">
                                    <div className="w-0.5 h-2.5 bg-white/90 rounded-full" />
                                  </div>
                                </div>
                              </div>
                            </div>
                          ) : (
                            /* Slot to Add Audio if none yet */
                            <button
                              onClick={() => audioFileInputRef.current?.click()}
                              className="w-full py-1.5 px-2 rounded-lg border border-dashed border-emerald-800/60 bg-emerald-950/20 hover:bg-emerald-950/40 hover:border-emerald-600 transition flex items-center justify-center gap-1.5 text-[8px] text-emerald-300 font-medium">
                              <Plus className="w-2.5 h-2.5" /> + Thêm Track Âm thanh / Video 1 (Kéo lồng CapCut)
                            </button>
                          )}

                          {/* ── Track 3+: Overlays (if any) ── */}
                          {editState?.overlays?.length > 0 && (
                            <div className="space-y-1 pt-1 border-t border-gray-800/50">
                              {editState.overlays.map((ovl, idx) => {
                                const st = Math.max(0, Math.min(timelineScaleDur, ovl.start_time || 0));
                                const et = (ovl.end_time && ovl.end_time > 0) ? Math.min(timelineScaleDur, ovl.end_time) : timelineScaleDur;
                                const leftPct = (st / timelineScaleDur) * 100;
                                const widthPct = Math.max(4, ((et - st) / timelineScaleDur) * 100);
                                const isSel = selOverlayIdx === idx;
                                const isVisible = (st <= 0 && (!ovl.end_time || ovl.end_time <= 0)) || (currentTime >= st && (ovl.end_time > 0 ? currentTime <= ovl.end_time : true));

                                return (
                                  <div
                                    key={ovl.id || idx}
                                    onClick={() => selectAndFocusLayer('overlay', idx)}
                                    className={`group flex items-center gap-1.5 p-1 rounded-lg border transition cursor-pointer ${
                                      isSel
                                        ? 'bg-pink-950/40 border-pink-500/70 ring-1 ring-pink-500/40'
                                        : 'bg-gray-900/60 border-gray-800/60 hover:bg-gray-800/50'
                                    }`}>
                                    <div className="w-4 h-4 rounded bg-black flex items-center justify-center overflow-hidden shrink-0 border border-gray-700/50">
                                      {ovl.type !== 'video' ? (
                                        <img src={toAssetUrl(ovl.remove_bg && ovl.remove_bg_url ? ovl.remove_bg_url : ovl.url)} alt="" className="w-full h-full object-contain" />
                                      ) : (
                                        <Film className="w-2.5 h-2.5 text-pink-400" />
                                      )}
                                    </div>
                                    <div className="flex-1 relative h-3.5 bg-black/80 rounded overflow-hidden border border-gray-800/80">
                                      <div
                                        className={`absolute top-0 bottom-0 rounded-sm transition-all flex items-center justify-between px-1 text-[6px] font-bold text-white ${
                                          isSel
                                            ? 'bg-gradient-to-r from-pink-500 to-rose-500 shadow-md'
                                            : isVisible
                                              ? 'bg-pink-600/70'
                                              : 'bg-gray-700/50'
                                        }`}
                                        style={{ left: `${leftPct}%`, width: `${widthPct}%` }}>
                                        <span className="truncate">{ovl.name || `Layer #${idx+1}`}</span>
                                        <span className="shrink-0 opacity-80">{st.toFixed(0)}s-{et.toFixed(0)}s</span>
                                      </div>
                                    </div>
                                    <span
                                      className={`w-1.5 h-1.5 rounded-full shrink-0 ${isVisible ? 'bg-emerald-400 shadow-sm shadow-emerald-500/50' : 'bg-gray-600'}`}
                                      title={isVisible ? 'Đang hiển thị' : 'Đang ẩn tại thời điểm này'}
                                    />
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </>
                );
              })()}

              {/* -- Also show suggested_titles -- */}
              {currentEditItem?.suggested_titles?.length > 0 && (
                <div className="w-full max-w-xs space-y-1 shrink-0 pb-4">
                  <p className="text-[8px] text-gray-600">Titles -- click to change:</p>
                  {currentEditItem.suggested_titles.map((t, i) => (
                    <button key={i}
                      onClick={() => setEditQueue(prev => prev.map((item, idx) => idx === selEditIdx ? { ...item, title: t } : item))}
                      className={`w-full text-left px-2 py-1 rounded text-[9px] transition ${currentEditItem.title === t ? 'bg-indigo-600/20 border border-indigo-500/40 text-white' : 'text-gray-500 hover:text-gray-300'}`}>
                      {i + 1}. {t.slice(0, 80)}{t.length > 80 ? "..." : ""}
                    </button>
                  ))}
                </div>
              )}
            </>}
        </div>

        {/* Right: Edit Queue */}
        <div className="w-64 shrink-0 border-l border-gray-800/70 bg-[#0d0e17] flex flex-col"
          onDragOver={e => e.preventDefault()} onDrop={handleDropTab2}>

          {/* ── BATCH TABS / QUẢN LÝ CỤM VIDEO ── */}
          <div className="px-2.5 py-1.5 border-b border-gray-800/60 bg-gray-950/60 shrink-0">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[8px] font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1">
                <Layers className="w-2.5 h-2.5" /> Cụm Video ({batches.length})
              </span>
              <button
                onClick={createNewBatch}
                className="px-1.5 py-0.5 bg-indigo-600/30 hover:bg-indigo-600 border border-indigo-500/40 rounded text-[8px] font-semibold text-indigo-200 flex items-center gap-0.5 transition"
                title="Tạo thêm cụm video mới">
                <Plus className="w-2.5 h-2.5" /> Thêm cụm
              </button>
            </div>

            {/* Batch tabs / chips */}
            <div className="flex items-center gap-1 overflow-x-auto pb-1 no-scrollbar">
              {batches.map(b => {
                const isActive = b.id === activeBatchId;
                return (
                  <div
                    key={b.id}
                    onClick={() => switchBatch(b.id)}
                    className={`shrink-0 px-2 py-0.5 rounded text-[8.5px] cursor-pointer flex items-center gap-1 border transition ${
                      isActive
                        ? 'bg-indigo-600 border-indigo-400 text-white font-bold shadow-sm'
                        : 'bg-gray-900 border-gray-800 text-gray-400 hover:text-gray-200 hover:bg-gray-800/60'
                    }`}
                    title={`${b.name} (${b.count || 0} clip)${b.output_folder ? '\nThư mục xuất riêng: ' + b.output_folder : ''}`}
                  >
                    <span className="max-w-[70px] truncate">{b.name}</span>
                    <span className={`px-1 py-0.2 rounded-full text-[7.5px] ${isActive ? 'bg-indigo-800 text-white' : 'bg-gray-800 text-gray-500'}`}>
                      {b.count || 0}
                    </span>
                    {batches.length > 1 && (
                      <button
                        onClick={(e) => deleteBatch(b.id, e)}
                        className={`hover:text-red-400 ml-0.5 ${isActive ? 'text-indigo-200' : 'text-gray-600'}`}
                        title="Xóa cụm này"
                      >
                        ×
                      </button>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Active batch info: rename + output folder */}
            {(() => {
              const curB = batches.find(b => b.id === activeBatchId);
              if (!curB) return null;
              return (
                <div className="mt-1 pt-1 border-t border-gray-800/40 flex flex-col gap-1">
                  <div className="flex items-center justify-between text-[8px]">
                    {isEditingBatchName ? (
                      <div className="flex items-center gap-1 w-full">
                        <input
                          type="text"
                          value={batchNameInput}
                          onChange={e => setBatchNameInput(e.target.value)}
                          onKeyDown={e => { if (e.key === 'Enter') saveBatchName(); if (e.key === 'Escape') setIsEditingBatchName(false); }}
                          className="flex-1 bg-black border border-indigo-500/60 rounded px-1 py-0.5 text-[8.5px] text-white outline-none"
                          autoFocus
                        />
                        <button onClick={saveBatchName} className="px-1.5 py-0.5 bg-indigo-600 text-white rounded text-[7.5px] font-bold">Lưu</button>
                        <button onClick={() => setIsEditingBatchName(false)} className="text-gray-500 text-[7.5px]">Hủy</button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between w-full">
                        <span className="text-gray-300 font-medium truncate flex-1">
                          📌 <strong className="text-white">{curB.name}</strong>
                        </span>
                        <button
                          onClick={() => { setBatchNameInput(curB.name); setIsEditingBatchName(true); }}
                          className="text-[7.5px] text-indigo-400 hover:underline shrink-0 ml-1">
                          Đổi tên
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Output folder for this batch */}
                  <div className="flex items-center gap-1 text-[7.5px] text-gray-400 bg-black/40 px-1.5 py-0.5 rounded border border-gray-800/50">
                    <span className="text-gray-500 shrink-0">📁 Xuất:</span>
                    <span
                      onClick={() => openOutput(curB.output_folder || null)}
                      className={`truncate flex-1 ${curB.output_folder ? 'text-amber-400/90 hover:underline cursor-pointer' : 'text-gray-400 hover:underline cursor-pointer'}`}
                      title={curB.output_folder ? `${curB.output_folder} (Bấm để mở thư mục)` : 'Theo thư mục chung của ứng dụng (Bấm để mở)'}
                    >
                      {curB.output_folder ? curB.output_folder : 'Chung (Default)'}
                    </span>
                    <button
                      onClick={() => pickBatchOutputFolder(curB.id)}
                      className="text-indigo-400 hover:text-indigo-300 shrink-0 text-[7.5px] font-medium"
                      title="Chọn thư mục riêng cho cụm này"
                    >
                      Đổi
                    </button>
                  </div>
                </div>
              );
            })()}
          </div>

          <div className="px-3 py-2 border-b border-gray-800/50 flex items-center justify-between shrink-0">
            <span className="text-[9px] font-bold text-gray-500 uppercase tracking-widest flex items-center gap-1">
              <Film className="w-2.5 h-2.5 text-emerald-400" />Queue ({editQueue.length})
            </span>
            <div className="flex gap-1 items-center">
              <button onClick={() => post('/dialog/pick_edit_files')}
                className="px-1.5 py-0.5 bg-indigo-900/60 hover:bg-indigo-700/80 border border-indigo-700/50 rounded text-[8px] font-bold text-indigo-200 transition flex items-center gap-0.5"
                title="Add Video directly to Edit Queue">
                <Plus className="w-2.5 h-2.5" /> + Add Video
              </button>
              <button onClick={() => post('/edit_queue/clear', {}).then(() => { setEditQueue([]); setSelEditIdx(-1); setSelEditIdxs(new Set()); })}
                className="text-[9px] text-gray-700 hover:text-red-400 transition p-0.5" title="Clear Queue"><Trash2 className="w-3 h-3" /></button>
            </div>
          </div>
          {/* ── Auto AI Title Toggle for Tab 2 Direct Import  ── */}
          <div className="px-3 py-1.5 border-b border-gray-800/40 bg-gray-950/40 flex items-center justify-between shrink-0">
            <div>
              <span className="text-[8px] font-bold text-gray-300 block">🤖 Tạo tiêu đề AI khi thả video</span>
              <span className="text-[7px] text-gray-500 block">{config.direct_import_gen_title !== false ? 'Bật: Gemini AI tạo title' : 'Tắt: Thêm nhanh (để trống tiêu đề)'}</span>
            </div>
            <Toggle
              label=""
              value={config.direct_import_gen_title !== false}
              onChange={v => updateCfg({ direct_import_gen_title: v })}
            />
          </div>

          {/* Compact Title Prompt */}
          <div className="px-3 py-2 border-b border-gray-800/50 shrink-0">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[8px] font-bold text-amber-400/80 flex items-center gap-1">
                <Sparkles className="w-2.5 h-2.5" />Title Prompt
              </span>
              <span className={`text-[7px] font-medium ${config.title_prompt ? 'text-emerald-400' : 'text-gray-600'}`}>
                {config.title_prompt ? '✨ Custom' : '○ Default'}
              </span>
            </div>
            <textarea
              value={titlePrompt}
              onChange={e => setTitlePrompt(e.target.value)}
              rows={3}
              placeholder={`Viết prompt tùy chỉnh.\nBiến: {old_title} {description} {highlight_reason}`}
              className="w-full bg-[#0a0b12] border border-gray-800 rounded p-1.5 text-[8px] font-mono text-gray-300 outline-none focus:border-amber-500/50 resize-none leading-relaxed placeholder:text-gray-700"
            />
            <div className="flex gap-1 mt-1">
              <button onClick={applyTitlePrompt}
                className="flex-1 py-1 bg-amber-800/50 hover:bg-amber-700/60 border border-amber-700/30 text-amber-200 rounded text-[8px] font-bold transition">
                ✅ Lưu prompt
              </button>
              <button onClick={() => { setTitlePrompt(''); post('/config', { title_prompt: null }); setConfig(p => ({ ...p, title_prompt: null })); }}
                className="px-2 py-1 bg-gray-800 hover:bg-gray-700 text-gray-500 rounded text-[8px] transition" title="Reset về mặc định">
                ✕
              </button>
            </div>
            {savedPresets.length > 0 && (
              <select onChange={e => e.target.value && loadPromptPreset(e.target.value)}
                defaultValue=""
                className="w-full mt-1.5 bg-gray-900 border border-gray-800 rounded px-1.5 py-1 text-[8px] text-gray-400 outline-none">
                <option value="">📂 Load preset…</option>
                {savedPresets.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            )}
          </div>

          {/* ── Failed titles retry banner ── */}
          {editQueue.some(c => c.title_error) && (
            <div className="px-3 py-1.5 bg-amber-950/60 border-b border-amber-800/60 flex items-center justify-between shrink-0">
              <span className="text-[8px] font-bold text-amber-300 flex items-center gap-1">
                <span>⚠️</span> {editQueue.filter(c => c.title_error).length} clip lỗi tiêu đề
              </span>
              <button
                onClick={retryAllFailedTitles}
                className="px-2 py-0.5 bg-amber-800/80 hover:bg-amber-700 text-amber-100 rounded text-[8px] font-bold transition flex items-center gap-1"
                title="Thử lại tạo tiêu đề AI cho tất cả clip lỗi (xoay key tự động)"
              >
                <RefreshCw className="w-2.5 h-2.5" /> Thử lại tất cả
              </button>
            </div>
          )}

          {/* ── Queue list (virtualized) ── */}
          <div className="flex-1 overflow-hidden">
            {editQueue.length === 0
              ? <div onClick={() => post('/dialog/pick_edit_files')} className="m-3 p-3 border-2 border-dashed border-gray-800/80 rounded-xl text-center text-gray-600 hover:border-indigo-500/40 hover:text-indigo-400 cursor-pointer transition text-[9px] flex flex-col items-center justify-center gap-1">
                  <Scissors className="w-6 h-6 opacity-30 text-indigo-400 mb-1" />
                  <span className="font-semibold text-gray-400">+ Add Video to Edit</span>
                  <span className="text-[8px] text-gray-600 leading-tight">Select or Drag &amp; Drop video files.<br />Gemini AI will analyze &amp; add highlight clip automatically!</span>
                </div>
              : <VirtualList
                  items={editQueue}
                  itemHeight={54}
                  containerHeight={Math.max(200, window.innerHeight - 380)}
                  renderItem={(clip, idx) => {
                    const isActive   = selEditIdx === idx;
                    const isMultiSel = selEditIdxs.has(idx);
                    return (
                      <div
                        onClick={(e) => {
                          if (e.shiftKey && lastSelEditIdxRef.current >= 0) {
                            const from = Math.min(lastSelEditIdxRef.current, idx);
                            const to   = Math.max(lastSelEditIdxRef.current, idx);
                            const range = new Set(); for (let i = from; i <= to; i++) range.add(i);
                            setSelEditIdxs(range);
                          } else if (e.ctrlKey || e.metaKey) {
                            setSelEditIdxs(prev => { const n = new Set(prev); n.has(idx) ? n.delete(idx) : n.add(idx); return n; });
                            lastSelEditIdxRef.current = idx;
                          } else {
                            setSelEditIdx(idx); lastSelEditIdxRef.current = idx; setSelEditIdxs(new Set());
                          }
                        }}
                        style={{ height: 54 }}
                        className={`px-3 py-2 border-b border-gray-800/30 cursor-pointer transition flex items-start gap-1.5 ${
                          isActive ? 'bg-indigo-600/20' : isMultiSel ? 'bg-indigo-900/25 border-l-2 border-l-indigo-500' : 'hover:bg-gray-800/40'
                        }`}>
                        <div className="flex-1 overflow-hidden">
                          <p className="text-[10px] font-medium text-gray-100 truncate">{clip.title || '—'}</p>
                          <p className="text-[9px] text-gray-600 truncate">{(clip.clip_path || clip.path || '').split(/[\\\/]/).pop()}</p>
                        </div>
                        <div className="flex items-center gap-0.5 shrink-0">
                          {clip.title_error ? (
                            <button
                              onClick={e => { e.stopPropagation(); regenTitle(idx); }}
                              disabled={regenningIdx === idx}
                              className="px-1.5 py-0.5 rounded bg-red-950/80 hover:bg-red-900/80 border border-red-800/70 text-red-300 text-[8px] font-bold flex items-center gap-1 transition shadow-sm"
                              title={clip.title_error_msg ? `Lỗi: ${clip.title_error_msg} — Click để thử lại AI Title` : 'Lỗi tạo tiêu đề — Click để thử lại'}
                            >
                              {regenningIdx === idx ? <RefreshCw className="w-2.5 h-2.5 animate-spin" /> : <span>⚠️ Thử lại</span>}
                            </button>
                          ) : (
                            <button
                              onClick={e => { e.stopPropagation(); regenTitle(idx); }}
                              disabled={regenningIdx === idx}
                              className="text-amber-500 hover:text-amber-300 disabled:opacity-40 p-0.5 text-[11px] transition"
                              title="Tạo lại tiêu đề bằng AI (Xoay key & Tự động Retry)"
                            >
                              {regenningIdx === idx ? '⏳' : '✨'}
                            </button>
                          )}
                          <button onClick={e => { e.stopPropagation(); removeEditClip(idx); }}
                            className="shrink-0 text-gray-700 hover:text-red-400 p-0.5"><Trash2 className="w-2.5 h-2.5" /></button>
                        </div>
                      </div>
                    );
                  }}
                />
            }
          </div>


          <div className="shrink-0 p-2.5 border-t border-gray-800/50 space-y-2">
            <button onClick={startExport} disabled={isExporting || editQueue.length === 0}
              className="w-full py-2 rounded-xl bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white font-bold text-xs flex items-center justify-center gap-2 transition">
              <Download className="w-3.5 h-3.5" />
              {isExporting ? `${exportProg.completed}/${exportProg.total} Exporting…` : `Xuất cụm hiện tại (${editQueue.length})`}
            </button>
            {batches.length > 1 && (
              <button onClick={startExportAllBatches} disabled={isExporting}
                className="w-full py-2 rounded-xl bg-indigo-700 hover:bg-indigo-600 disabled:opacity-40 text-white font-bold text-[11px] flex items-center justify-center gap-1.5 transition">
                <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                Xuất tất cả {batches.length} cụm ({batches.reduce((acc, b) => acc + (b.count || 0), 0)} clip)
              </button>
            )}
            {isExporting && <p className="text-[8px] text-emerald-400 text-center truncate">{exportProg.current}</p>}
          </div>
        </div>
      </div>
    );
  };

  // ── Main render ──
return (
    <div className="flex flex-col h-screen w-screen bg-[#07080f] text-gray-100 overflow-hidden"
      style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>

      {/* ── Header ── */}
      <header className="shrink-0 h-11 border-b border-gray-800/80 bg-[#0c0d16]/90 px-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
            <Film className="w-3.5 h-3.5 text-indigo-400" />
          </div>
          <span className="text-sm font-bold text-white">Viral Bodycam Clipper</span>
          <span className="text-[10px] text-gray-500 font-mono">v{updateStatus?.local_version || '2.8.6'}</span>
          {updateStatus?.has_update && (
            <button
              onClick={handleApplyUpdateInApp}
              disabled={updating}
              className="px-2 py-0.5 rounded-full bg-gradient-to-r from-amber-500/20 to-orange-500/20 border border-amber-500/40 text-amber-300 text-[10px] font-bold flex items-center gap-1 hover:border-amber-400 animate-pulse transition"
              title={updateStatus.changelog || 'Bấm để cập nhật bản mới ngay'}
            >
              <span>⚡ Có bản v{updateStatus.remote_version}</span>
              {updating ? <span className="animate-spin text-[8px]">⏳</span> : <span>[Cập nhật]</span>}
            </button>
          )}
        </div>

        {/* ── Tabs ── */}
        <div className="flex bg-gray-900 border border-gray-800/80 rounded-xl p-0.5 gap-0.5">
          <button onClick={() => setTab('analyze')}
            className={`px-4 py-1.5 rounded-lg text-xs font-medium transition ${tab === 'analyze' ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:text-gray-300'}`}>
            🔍 Analyze &amp; Select
          </button>
          <button onClick={() => setTab('edit')}
            className={`px-4 py-1.5 rounded-lg text-xs font-medium transition flex items-center gap-1.5 ${tab === 'edit' ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:text-gray-300'}`}>
            ?? Edit &amp; Export
            {editQueue.length > 0 && (
              <span className={`w-4 h-4 rounded-full text-[9px] flex items-center justify-center font-bold ${tab === 'edit' ? 'bg-white/20 text-white' : 'bg-emerald-600 text-white'}`}>{editQueue.length}</span>
            )}
          </button>
        </div>

        {/* ── YouTube Quick Button & Cookie Status in Header ── */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => { setShowYtModal(true); setYtBatchTab('single'); }}
            className="px-2.5 py-1 bg-red-950/40 hover:bg-red-900/50 border border-red-700/40 rounded-xl text-red-300 text-xs font-semibold flex items-center gap-1.5 transition shadow-sm hover:border-red-500/60"
            title="Nhập link YouTube và để Gemini soi hình ảnh tìm highlight"
          >
            <Youtube className="w-3.5 h-3.5 text-red-500" />
            <span>YouTube AI</span>
          </button>

          {ytCookiesStatus.has_cookies ? (
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 bg-emerald-950/30 border border-emerald-800/40 rounded-xl text-[11px] text-emerald-300">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span>Cookie: Đã nạp</span>
              <button
                onClick={handleQuickPasteCookiesFromClipboard}
                className="text-[10px] text-emerald-400 hover:text-emerald-200 underline ml-0.5"
                title="Dán đè Cookie mới trực tiếp từ Clipboard"
              >
                Dán mới
              </button>
            </div>
          ) : (
            <button
              onClick={handleQuickPasteCookiesFromClipboard}
              className="px-2.5 py-1 bg-amber-950/40 hover:bg-amber-900/60 border border-amber-600/40 rounded-xl text-amber-300 text-xs font-semibold flex items-center gap-1 transition shadow-sm hover:border-amber-400"
              title="Dán nhanh Cookie từ Clipboard (1-Click) để chống bot YouTube"
            >
              <span>🍪 Dán Cookie (1-Click)</span>
            </button>
          )}
        </div>

        {/* ── Actions ── */}
        <div className="flex items-center gap-2">
          {tab === 'analyze' && (
            isAnalyzing
              ? <button onClick={stopAnalysis} className="px-3 py-1.5 rounded-lg bg-red-700/80 hover:bg-red-600 text-white text-xs flex items-center gap-1.5 transition">
                <Square className="w-3 h-3" />STOP ALL
              </button>
              : <>
                  {/* Mode selector — hiển trước nút Analyze */}
                  <div className="flex items-center gap-1 bg-gray-900/60 border border-gray-700/50 rounded-lg p-0.5">
                    <button
                      onClick={() => { setAnalysisMode('short'); localStorage.setItem('analysisMode', 'short'); }}
                      className={`px-2 py-1 rounded text-[9px] font-bold transition ${
                        analysisMode === 'short'
                          ? 'bg-indigo-600 text-white'
                          : 'text-gray-500 hover:text-gray-300'
                      }`}
                      title="Tìm khoảnh khắc ngắn ~16s">
                      ⚡ Short
                    </button>
                    <button
                      onClick={() => { setAnalysisMode('story'); localStorage.setItem('analysisMode', 'story'); }}
                      className={`px-2 py-1 rounded text-[9px] font-bold transition ${
                        analysisMode === 'story'
                          ? 'bg-emerald-600 text-white'
                          : 'text-gray-500 hover:text-gray-300'
                      }`}
                      title="Tìm cảnh trọn vẹn 30–90s">
                      🎥 Story
                    </button>
                  </div>
                  <button onClick={startAnalysis} disabled={videos.length === 0}
                    className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-xs flex items-center gap-1.5 transition">
                    <Sparkles className="w-3 h-3" />{analysisMode === 'story' ? 'STORY ANALYZE' : 'ANALYZE ALL'}
                  </button>
                  {totalAllCandidates > 0 && (
                    <button onClick={sendAllVideosCandidatesToEdit}
                      disabled={sendAllVideosBusy || isAnalyzing}
                      className="px-3 py-1.5 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-40 text-white text-xs font-bold flex items-center gap-1.5 shadow-md shadow-emerald-950/40 transition"
                      title="Cắt toàn bộ candidate của tất cả các video có trong danh sách sang Tab 2">
                      {sendAllVideosBusy ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Scissors className="w-3 h-3 text-amber-300" />}
                      {sendAllVideosBusy ? 'Đang cắt tất cả…' : `CẮT TẤT CẢ VIDEO (${totalAllCandidates})`}
                    </button>
                  )}
                </>
          )}
          {videos.some(v => v.status === 'error') && (
            <button onClick={retryErrors} className="px-3 py-1.5 rounded-lg bg-amber-700/60 hover:bg-amber-600 text-white text-xs flex items-center gap-1.5 transition">
              <RefreshCw className="w-3 h-3" />Retry Errors
            </button>
          )}
          <button
            onClick={() => {
              const bFolder = tab === 'edit' ? (batches.find(b => b.id === activeBatchId)?.output_folder || null) : null;
              openOutput(bFolder);
            }}
            className="p-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg"
            title="Open Output Folder"
          >
            <FolderOpen className="w-3.5 h-3.5 text-amber-400" />
          </button>
          {tab === 'analyze' && (
            <button onClick={() => setShowLog(p => !p)}
              className={`relative p-1.5 rounded-lg border transition ${showLog ? 'bg-indigo-900/40 border-indigo-500/30' : 'bg-gray-800 border-gray-700'}`}>
              <Terminal className="w-3.5 h-3.5 text-gray-400" />
              {errLogs > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500 text-[8px] text-white flex items-center justify-center font-bold">
                  {errLogs > 9 ? '9+' : errLogs}
                </span>
              )}
            </button>
          )}
        </div>
      </header>

      {/* ── Export progress + cancel button ── */}
      {isExporting && (
        <div className="shrink-0 bg-emerald-900/20 border-b border-emerald-800/30 px-4 py-1.5 flex flex-col gap-1">
          <div className="flex items-center gap-2 text-[9px] text-emerald-300">
            <RefreshCw className="w-2.5 h-2.5 animate-spin shrink-0" />
            <span className="flex-1 truncate">
              {exportProg.clip_name
                ? `🎬 ${exportProg.clip_name}`
                : (exportProg.current || 'Processing…')}
            </span>
            <span className="text-emerald-500 shrink-0 tabular-nums">
              {exportProg.completed}/{exportProg.total}
            </span>
            <button
              onClick={stopExport}
              title="Stop export"
              className="flex items-center gap-1 px-2 py-0.5 rounded bg-red-800/70 hover:bg-red-700 text-red-200 transition text-[9px] shrink-0"
            >
              <Square className="w-2 h-2" />Stop
            </button>
          </div>
          {/* Per-clip progress bar */}
          <div className="w-full h-1 bg-emerald-950/60 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-400 rounded-full transition-all duration-300"
              style={{ width: `${Math.round((exportProg.clip_pct ?? 0) * 100)}%` }}
            />
          </div>
          <div className="text-[7px] text-emerald-700 text-right">
            {exportProg.clip_pct > 0
              ? `${Math.round((exportProg.clip_pct ?? 0) * 100)}% current clip`
              : exportProg.current || ''}
          </div>
        </div>
      )}

      {/* ── Failed exports panel ── */}
      {exportProg.status === 'done' && (exportProg.failed_items || []).length > 0 && (
        <div className="shrink-0 bg-red-950/40 border-b border-red-800/40 px-3 py-2">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[9px] font-bold text-red-300 flex items-center gap-1">
              <span className="text-red-400">⚠</span>
              {exportProg.failed_items.length} clip{exportProg.failed_items.length > 1 ? 's' : ''} failed to export
            </span>
            <button
              onClick={async () => {
                try {
                  const r = await fetch(`${API}/export/retry_failed`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items: [], threads: 2, crf: 20, preset: 'fast', encoder: 'libx264', resolution: '1080x1920' }),
                  });
                  if (!r.ok) { const e = await r.json(); alert(e.detail || 'Retry failed'); }
                } catch(e) { alert('Network error: ' + e.message); }
              }}
              className="flex items-center gap-1 px-2 py-0.5 rounded bg-orange-700/80 hover:bg-orange-600 text-white text-[9px] font-semibold transition"
            >
              🔄 Retry Failed
            </button>
          </div>
          <div className="space-y-0.5 max-h-20 overflow-y-auto pr-1">
            {(exportProg.failed_items || []).map((f, i) => (
              <div key={i} className="flex items-start gap-1.5 bg-red-900/30 rounded px-2 py-1">
                <span className="text-red-400 text-[8px] mt-0.5 shrink-0">✕</span>
                <div className="min-w-0">
                  <p className="text-[8px] text-red-200 font-mono truncate">{f.clip_path?.split(/[\/\\]/).pop()}</p>
                  <p className="text-[7px] text-red-400/80 truncate" title={f.error}>{f.error}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Call as functions, NOT as <Component/>, so React reconciles in-place
           and never unmounts/remounts the <video> element mid-playback */}
      {tab === 'analyze' ? AnalyzeTab() : EditTab()}

      {/* ── YouTube Direct Visual Analysis & Segment Download Modal ── */}
      {renderYouTubeModal()}
    </div>
  );
}
