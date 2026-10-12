import React, { useState, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';

export const Section = ({ title, icon, children, defaultOpen = false, id, active = false }) => {
  const [open, setOpen] = useState(defaultOpen);
  useEffect(() => {
    if (active) setOpen(true);
  }, [active]);

  return (
    <div id={id} className={`border rounded-xl overflow-hidden transition-all scroll-mt-2 ${active ? 'border-indigo-500/70 ring-1 ring-indigo-500/40 shadow-lg' : 'border-[#23283a]'}`}>
      <button onClick={() => setOpen(p => !p)}
        className={`w-full flex items-center justify-between px-3 py-2 transition ${active ? 'bg-indigo-950/40 hover:bg-indigo-900/40 text-white' : 'bg-[#151822] hover:bg-[#1c202e] text-slate-200'}`}>
        <span className="flex items-center gap-2 text-xs font-semibold">{icon}{title}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${open ? '' : '-rotate-90'}`} />
      </button>
      {open && <div className="px-3 py-2.5 bg-[#10121a]/95 space-y-2.5 border-t border-[#23283a]">{children}</div>}
    </div>
  );
};
export default Section;
