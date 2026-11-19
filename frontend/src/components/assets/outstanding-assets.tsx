import React from 'react';
import { fmtDate } from './asset-utils';

export interface OutstandingAsset {
  allocation_id: number;
  asset_id: number | null;
  asset_tag: string | null;
  name: string | null;
  category: string | null;
  issued_date: string | null;
}

/** Assets still held at exit. `hr` = blocking warning, otherwise informational for the employee. */
export const OutstandingAssets: React.FC<{ items?: OutstandingAsset[] | null; hr?: boolean }> = ({ items, hr }) => {
  if (!items || items.length === 0) return null;
  return (
    <div
      role={hr ? 'alert' : undefined}
      data-testid="outstanding-assets"
      className={`mt-6 p-4 rounded-xl border ${hr ? 'bg-amber-50 border-amber-200' : 'bg-slate-50 border-slate-200'}`}
    >
      <p className={`text-xs font-black uppercase tracking-widest ${hr ? 'text-amber-800' : 'text-slate-600'}`}>
        {hr ? 'Assets not yet returned — release is blocked' : 'Assets to return before you leave'}
      </p>
      <ul className="mt-2 space-y-1">
        {items.map((a) => (
          <li key={a.allocation_id} className="text-sm text-slate-700">
            <span className="font-bold">{a.asset_tag || '—'}</span> · {a.name || '—'} · {a.category || '—'} · issued {fmtDate(a.issued_date)}
          </li>
        ))}
      </ul>
    </div>
  );
};
