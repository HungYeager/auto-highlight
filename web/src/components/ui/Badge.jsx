import React from 'react';
import { CheckCircle2, RefreshCw, Sparkles, AlertCircle } from 'lucide-react';

export const Badge = ({ status }) => ({
  done:      <span className="text-[9px] text-emerald-400 flex items-center gap-0.5"><CheckCircle2 className="w-2.5 h-2.5"/>Done</span>,
  uploading: <span className="text-[9px] text-amber-400 flex items-center gap-0.5 animate-pulse"><RefreshCw className="w-2.5 h-2.5 animate-spin"/>Uploading</span>,
  analyzing: <span className="text-[9px] text-indigo-400 flex items-center gap-0.5 animate-pulse"><Sparkles className="w-2.5 h-2.5"/>Analyzing</span>,
  error:     <span className="text-[9px] text-red-400 flex items-center gap-0.5"><AlertCircle className="w-2.5 h-2.5"/>Error</span>,
  queued:    <span className="text-[9px] text-gray-500">Queued</span>,
}[status] || <span className="text-[9px] text-gray-500">{status}</span>);

export default Badge;
