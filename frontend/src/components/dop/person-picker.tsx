import React, { useEffect, useRef, useState } from 'react';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { Person, dopErr, inputCls, labelCls } from './dop-utils';

/** Search active people by name or email. Late answers to older searches are dropped. */
export const PersonPicker: React.FC<{
  id: string; label: string; value: Person | null; onChange: (p: Person | null) => void; required?: boolean;
}> = ({ id, label, value, onChange, required }) => {
  const [q, setQ] = useState('');
  const [rows, setRows] = useState<Person[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const seq = useRef(0);

  useEffect(() => { if (value) setQ(''); }, [value]);

  useEffect(() => {
    if (!open || value) return;
    const n = ++seq.current;
    setLoading(true);
    const t = window.setTimeout(async () => {
      try {
        const r = await client.get<Person[]>(ENDPOINTS.DOP.PEOPLE, { params: { q: q.trim() } });
        if (n !== seq.current) return;
        setRows(r.data); setErr(null);
      } catch (e: any) {
        if (n === seq.current) { setRows([]); setErr(dopErr(e, 'Could not search people')); }
      } finally {
        if (n === seq.current) setLoading(false);
      }
    }, 250);
    return () => window.clearTimeout(t);
  }, [q, open, value]);

  if (value) {
    return (
      <div>
        <span className={labelCls} id={`${id}-l`}>{label}{required ? ' *' : ''}</span>
        <div className="flex items-center justify-between text-sm border border-gray-200 rounded-lg px-3 py-2" aria-labelledby={`${id}-l`}>
          <span>{value.name} <span className="text-xs text-gray-500">{value.email}</span></span>
          <button type="button" className="text-xs text-indigo-600" onClick={() => { onChange(null); setQ(''); }}>Change</button>
        </div>
      </div>
    );
  }
  return (
    <div className="relative">
      <label className={labelCls} htmlFor={id}>{label}{required ? ' *' : ''}</label>
      <input
        id={id} className={`${inputCls} w-full`} placeholder="Type a name or email" autoComplete="off"
        role="combobox" aria-expanded={open} aria-controls={`${id}-list`}
        value={q} onFocus={() => setOpen(true)}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onKeyDown={(e) => {
          if (e.key === 'Escape' && open) { e.stopPropagation(); setOpen(false); }
          if (e.key === 'ArrowDown') { e.preventDefault(); (document.querySelector(`#${id}-list button`) as HTMLElement | null)?.focus(); }
        }}
      />
      {open && (
        <ul id={`${id}-list`} role="listbox" aria-label={label} className="absolute z-10 left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-56 overflow-y-auto">
          {loading && <li className="px-3 py-2 text-sm text-gray-500">Searching…</li>}
          {err && <li role="alert" className="px-3 py-2 text-sm text-red-700">{err}</li>}
          {!loading && !err && rows.length === 0 && <li className="px-3 py-2 text-sm text-gray-500">No one found.</li>}
          {rows.map((p) => (
            <li key={p.id} role="presentation">
              <button
                type="button" role="option" aria-selected={false} className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                onClick={() => { onChange(p); setOpen(false); }}
                onKeyDown={(e) => {
                  const li = (e.currentTarget.parentElement as HTMLElement);
                  if (e.key === 'ArrowDown') { e.preventDefault(); (li.nextElementSibling?.querySelector('button') as HTMLElement | null)?.focus(); }
                  if (e.key === 'ArrowUp') { e.preventDefault(); ((li.previousElementSibling?.querySelector('button') as HTMLElement | null) ?? document.getElementById(id))?.focus(); }
                  if (e.key === 'Escape') { e.stopPropagation(); setOpen(false); document.getElementById(id)?.focus(); }
                }}
              >
                {p.name} <span className="text-xs text-gray-500">{p.email}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
