import React, { useState } from 'react';

interface Props {
  label: string;
  confirmLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  tone?: 'danger' | 'neutral';
}

/** Two-step inline confirmation (no window.confirm). */
export const InlineConfirm: React.FC<Props> = ({
  label, confirmLabel = 'Yes', busy, onConfirm, tone = 'danger',
}) => {
  const [asking, setAsking] = useState(false);
  const color = tone === 'danger' ? 'text-rose-500 hover:text-rose-700' : 'text-slate-600 hover:text-slate-900';
  if (!asking) {
    return (
      <button type="button" onClick={() => setAsking(true)} disabled={busy}
        className={`text-[9px] font-black uppercase tracking-widest ${color}`}>
        {label}
      </button>
    );
  }
  return (
    <span className="inline-flex items-center gap-2 text-[9px] font-black uppercase tracking-widest">
      <span className="text-slate-500">Sure?</span>
      <button type="button" disabled={busy}
        onClick={() => { setAsking(false); onConfirm(); }}
        className="text-[9px] font-black uppercase tracking-widest text-rose-600 hover:text-rose-700">
        {confirmLabel}
      </button>
      <button type="button" onClick={() => setAsking(false)} className="text-[9px] font-black uppercase tracking-widest text-slate-500 hover:text-slate-600">
        No
      </button>
    </span>
  );
};
