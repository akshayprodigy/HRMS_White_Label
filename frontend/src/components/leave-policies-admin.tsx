import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw, Check, X, Wand2 } from 'lucide-react';
import { Card, Button, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface ET { id: number; code: string; name: string; }
interface LT { id: number; code: string | null; name: string; default_quota: number | null; unpaid_allowed: boolean; }
interface Cell { id: number; employment_type_id: number; leave_type_id: number; is_eligible: boolean; annual_quota: number | null; }

const errMsg = (e: any, f: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  return e?.message || f;
};

export const LeavePoliciesAdmin: React.FC = () => {
  const [ets, setEts] = useState<ET[]>([]);
  const [lts, setLts] = useState<LT[]>([]);
  const [cells, setCells] = useState<Cell[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);

  const cellMap = useMemo(() => {
    const m: Record<string, Cell> = {};
    cells.forEach(c => { m[`${c.employment_type_id}:${c.leave_type_id}`] = c; });
    return m;
  }, [cells]);

  const fetch = async () => {
    setLoading(true);
    try {
      const res = await client.get(ENDPOINTS.HR.LEAVE_POLICY_MATRIX);
      setEts(res.data.employment_types || []);
      setLts(res.data.leave_types || []);
      setCells(res.data.cells || []);
    } catch (e: any) { toast.error(errMsg(e, 'Failed to load matrix')); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetch(); }, []);

  // Missing cell = eligible (fallback).
  const isEligible = (etId: number, ltId: number) => {
    const c = cellMap[`${etId}:${ltId}`];
    return c ? c.is_eligible : true;
  };

  const toggle = async (etId: number, ltId: number) => {
    const key = `${etId}:${ltId}`;
    setSaving(key);
    try {
      await client.put(ENDPOINTS.HR.LEAVE_POLICIES, {
        employment_type_id: etId, leave_type_id: ltId,
        is_eligible: !isEligible(etId, ltId), annual_quota: cellMap[key]?.annual_quota ?? null,
      });
      await fetch();
    } catch (e: any) { toast.error(errMsg(e, 'Save failed')); }
    finally { setSaving(null); }
  };

  const allocate = async (etId: number) => {
    try {
      const res = await client.post(ENDPOINTS.HR.LEAVE_POLICY_ALLOCATE, { employment_type_id: etId, overwrite: false });
      toast.success(`Allocated balances: ${res.data.users} employee(s), ${res.data.ledgers_touched} ledgers`);
    } catch (e: any) { toast.error(errMsg(e, 'Allocation failed')); }
  };

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto animate-in fade-in duration-300">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Leave Policy Matrix</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Which Leave Types Each Employment Type Can Take · Blank = Eligible (Fallback)
          </p>
        </div>
        <button type="button" onClick={fetch} className="p-2 text-slate-400 hover:text-blue-600 self-end" title="Refresh" aria-label="Refresh">
          <RefreshCw size={16} className={cn(loading && 'animate-spin')} />
        </button>
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        {loading ? <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">Loading…</div> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Leave Type</th>
                  {ets.map(e => (
                    <th key={e.id} className="px-6 py-3 text-center text-[9px] font-black text-slate-400 uppercase tracking-widest">{e.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {lts.map(l => (
                  <tr key={l.id} className="hover:bg-slate-50/60">
                    <td className="px-6 py-3 text-sm font-black text-[#0F172A]">
                      {l.name}
                      {l.unpaid_allowed && <span className="ml-2 text-[8px] font-black uppercase text-amber-600">unpaid</span>}
                      <span className="ml-2 text-[10px] font-bold text-slate-400">quota {l.default_quota ?? '—'}</span>
                    </td>
                    {ets.map(e => {
                      const key = `${e.id}:${l.id}`;
                      const elig = isEligible(e.id, l.id);
                      return (
                        <td key={e.id} className="px-6 py-3 text-center">
                          <button type="button" onClick={() => toggle(e.id, l.id)} disabled={saving === key}
                            className={cn('inline-flex items-center justify-center w-9 h-9 rounded-xl transition-colors',
                              elig ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100' : 'bg-rose-50 text-rose-600 hover:bg-rose-100',
                              saving === key && 'opacity-50')}
                            title={elig ? 'Eligible — click to block' : 'Blocked — click to allow'}>
                            {elig ? <Check size={16} /> : <X size={16} />}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-slate-100 bg-slate-50/40">
                  <td className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Allocate balances</td>
                  {ets.map(e => (
                    <td key={e.id} className="px-6 py-3 text-center">
                      <Button onClick={() => allocate(e.id)} variant="ghost" className="h-8 border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 font-black uppercase text-[9px] tracking-widest">
                        <Wand2 size={12} className="mr-1" /> Allocate
                      </Button>
                    </td>
                  ))}
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </Card>
      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
        Green = eligible · Red = blocked. "Allocate" seeds leave balances for all active employees of that type (never lowers below used).
      </p>
    </div>
  );
};
