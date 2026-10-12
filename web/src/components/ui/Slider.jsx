import React, { useState, useRef } from 'react';

export const Slider = ({ label, value, min, max, step = 1, onChange, unit = '' }) => {
  const isFloat = step < 1;
  const fmt = v => isFloat ? parseFloat(v).toFixed(2) : String(Math.round(v));

  const [editing, setEditing] = useState(false);
  const [draft,   setDraft]   = useState('');
  const inputRef = useRef(null);

  const startEdit = () => {
    setDraft(fmt(value));
    setEditing(true);
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
        <span className="text-[10px] text-slate-400">{label}</span>
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
export default Slider;
