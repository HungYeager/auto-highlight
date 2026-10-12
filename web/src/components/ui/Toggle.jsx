import React from 'react';

export const Toggle = ({ label, value, onChange, icon }) => (
  <label className="flex items-center justify-between cursor-pointer py-0.5">
    <span className="flex items-center gap-1.5 text-[11px] text-slate-300">{icon}{label}</span>
    <div onClick={() => onChange(!value)}
      className={`w-8 h-4 rounded-full relative cursor-pointer transition-colors ${value ? 'bg-indigo-600' : 'bg-gray-700'}`}>
      <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-all ${value ? 'left-[18px]' : 'left-0.5'}`} />
    </div>
  </label>
);

export const ColorPicker = ({ label, value, onChange, presets = [] }) => (
  <div className="flex items-center gap-2">
    <span className="text-[10px] text-slate-400 flex-1">{label}</span>
    <input type="color" value={value} onChange={e => onChange(e.target.value)}
      className="w-6 h-6 rounded cursor-pointer border border-gray-700 bg-transparent" />
    {presets.map(c => (
      <button key={c} onClick={() => onChange(c)} style={{ backgroundColor: c }}
        className={`w-4 h-4 rounded-full border-2 transition ${value === c ? 'border-white' : 'border-transparent'}`} />
    ))}
  </div>
);

export default Toggle;
