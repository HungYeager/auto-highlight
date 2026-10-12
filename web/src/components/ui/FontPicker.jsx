import React, { useState, useEffect, useRef, useCallback } from 'react';
import { API } from '../../utils/api';

export const FONT_OPTIONS = [
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

export const FontPicker = ({ value, onChange }) => {
  const [open, setOpen] = useState(false);
  const [previews, setPreviews] = useState({});
  const ref = useRef(null);

  const fetchPreview = useCallback((key) => {
    if (_fontPreviewCache.has(key)) {
      setPreviews(p => ({ ...p, [key]: _fontPreviewCache.get(key) }));
      return;
    }
    const f = FONT_OPTIONS.find(x => x.key === key);
    if (!f) return;
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
  }, []);

  // Pre-fetch selected font on mount
  useEffect(() => { fetchPreview(value); }, [value, fetchPreview]);

  // Fetch all previews when dropdown opens
  useEffect(() => {
    if (!open) return;
    FONT_OPTIONS.forEach(({ key }) => fetchPreview(key));
  }, [open, fetchPreview]);

  // Close on outside click
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const selected = FONT_OPTIONS.find(f => f.key === value) || FONT_OPTIONS[0];

  const FontRow = ({ f, compact = false }) => (
    <div className="flex items-center gap-1.5 min-w-0 flex-1">
      {previews[f.key]
        ? <img
            src={previews[f.key]}
            alt={f.label}
            className={`${compact ? 'h-7' : 'h-9'} object-contain object-left`}
            style={{ imageRendering: 'crisp-edges', width: compact ? 160 : 200 }}
          />
        : <span className={`${compact ? 'text-[9px]' : 'text-[10px]'} text-slate-300`}>{f.label}</span>
      }
      {f.bundled && (
        <span className="text-[6px] font-bold text-violet-400 bg-violet-900/40 px-1 py-0.5 rounded shrink-0 leading-tight">NEW</span>
      )}
    </div>
  );

  return (
    <div ref={ref} className="relative w-full mb-1.5">
      {/* Trigger button */}
      <button type="button" onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between bg-gray-900 border border-gray-800 hover:border-indigo-600/60 rounded-lg px-2 py-1.5 text-left transition gap-1"
      >
        <FontRow f={selected} compact />
        <svg className={`w-3 h-3 text-gray-500 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7"/>
        </svg>
      </button>

      {/* Dropdown list */}
      {open && (
        <div className="absolute z-50 left-0 right-0 mt-1 bg-[#0f111c] border border-[#23283a] rounded-xl shadow-2xl overflow-hidden">
          {/* Bundled section header */}
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

            {/* System fonts section */}
            <div className="px-3 pt-2 pb-0.5 border-t border-gray-800/60 mt-1">
              <p className="text-[7px] text-gray-500 uppercase tracking-widest font-bold">System Fonts</p>
            </div>
            {FONT_OPTIONS.filter(f => !f.bundled).map(f => (
              <button key={f.key} type="button"
                onClick={() => { onChange(f.key); setOpen(false); }}
                className={`w-full flex items-center px-3 py-2 hover:bg-indigo-900/25 transition text-left gap-2 ${
                  value === f.key ? 'bg-indigo-900/35 border-l-2 border-indigo-500' : 'border-l-2 border-transparent'
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
export default FontPicker;
