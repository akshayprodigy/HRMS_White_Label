import React, { useEffect, useMemo, useState } from 'react';
import { Edit2, RefreshCw, UserCog, Users } from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogTitle, DialogFooter } from './ui/dialog';

interface Dept {
  id: number;
  name: string;
  is_active: boolean;
  head_user_id: number | null;
  deputy_head_user_id: number | null;
}

interface Candidate {
  user_id: number;
  full_name: string;
}

const errMsg = (err: any, fallback: string): string => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ');
  return err?.message || fallback;
};

const selectCls =
  'mt-1.5 w-full h-11 px-3 bg-slate-50 border border-slate-200 rounded-xl text-sm font-bold text-[#0F172A] outline-none focus:ring-2 focus:ring-blue-600/10';

export const DepartmentHeadsAdmin: React.FC = () => {
  const [depts, setDepts] = useState<Dept[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Dept | null>(null);
  const [head, setHead] = useState('');
  const [deputy, setDeputy] = useState('');
  const [saving, setSaving] = useState(false);

  const nameById = useMemo(() => {
    const m: Record<number, string> = {};
    candidates.forEach(c => { m[c.user_id] = c.full_name; });
    return m;
  }, [candidates]);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [dRes, eRes] = await Promise.all([
        client.get(ENDPOINTS.HR.FH_DEPARTMENTS),
        client.get(ENDPOINTS.HR.EMPLOYEES, { params: { limit: 500 } }),
      ]);
      setDepts(dRes.data || []);
      const items = eRes.data?.items ?? (Array.isArray(eRes.data) ? eRes.data : []);
      const cands: Candidate[] = items
        .filter((e: any) => e?.user)
        .map((e: any) => ({ user_id: e.user.id, full_name: e.user.full_name || e.user.email }));
      // de-dupe by user_id
      const seen = new Set<number>();
      setCandidates(cands.filter(c => (seen.has(c.user_id) ? false : (seen.add(c.user_id), true))));
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load departments'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const openEdit = (d: Dept) => {
    setEditing(d);
    setHead(d.head_user_id ? String(d.head_user_id) : '');
    setDeputy(d.deputy_head_user_id ? String(d.deputy_head_user_id) : '');
  };

  const save = async () => {
    if (!editing) return;
    if (head && deputy && head === deputy) {
      toast.error('Head and deputy must be different people');
      return;
    }
    setSaving(true);
    try {
      await client.patch(ENDPOINTS.HR.FH_ASSIGN_HEAD(editing.id), {
        head_user_id: head ? Number(head) : null,
        deputy_head_user_id: deputy ? Number(deputy) : null,
      });
      toast.success(`Heads updated for ${editing.name}`);
      setEditing(null);
      fetchAll();
    } catch (e: any) {
      toast.error(errMsg(e, 'Save failed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-8 space-y-6 max-w-[1400px] mx-auto animate-in fade-in duration-300">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">
            Department Heads
          </h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">
            Functional Head &amp; Deputy Per Department · Drives Approvals &amp; My-Team
          </p>
        </div>
        <button
          type="button"
          onClick={fetchAll}
          className="p-2 text-slate-400 hover:text-blue-600 transition-colors self-end"
          title="Refresh"
          aria-label="Refresh"
        >
          <RefreshCw size={16} className={cn(loading && 'animate-spin')} />
        </button>
      </div>

      <Card className="p-0 border-slate-200 overflow-hidden bg-white">
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/40">
          <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase flex items-center gap-2">
            <UserCog size={16} /> Departments {!loading && <span className="text-slate-400 font-bold text-[10px]">({depts.length})</span>}
          </h4>
        </div>
        {loading ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400 animate-pulse">Loading…</div>
        ) : depts.length === 0 ? (
          <div className="py-16 text-center text-[10px] font-black uppercase tracking-widest text-slate-400">No departments</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="bg-white border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Department</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Functional Head</th>
                  <th className="px-6 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Deputy Head</th>
                  <th className="px-6 py-3 text-right text-[9px] font-black text-slate-400 uppercase tracking-widest w-28">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {depts.map(d => (
                  <tr key={d.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="px-6 py-3 text-sm font-black text-[#0F172A]">
                      {d.name}
                      {!d.is_active && <Badge variant="neutral" className="ml-2 text-[8px] uppercase">Inactive</Badge>}
                    </td>
                    <td className="px-6 py-3">
                      {d.head_user_id ? (
                        <span className="text-sm font-bold text-[#0F172A]">{nameById[d.head_user_id] || `User #${d.head_user_id}`}</span>
                      ) : (
                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-300">Unassigned</span>
                      )}
                    </td>
                    <td className="px-6 py-3">
                      {d.deputy_head_user_id ? (
                        <span className="text-sm font-bold text-slate-600">{nameById[d.deputy_head_user_id] || `User #${d.deputy_head_user_id}`}</span>
                      ) : (
                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => openEdit(d)}
                        className="inline-flex items-center px-2.5 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest text-slate-600 hover:bg-slate-100"
                      >
                        <Edit2 size={11} className="mr-1" /> Assign
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-md p-0 overflow-hidden">
          <div className="bg-blue-600 px-6 py-5 text-white">
            <DialogTitle className="text-lg font-black uppercase tracking-tight flex items-center gap-2">
              <Users size={18} /> {editing?.name}
            </DialogTitle>
            <p className="text-blue-100 text-[10px] font-bold uppercase tracking-widest mt-1">
              Assign functional head &amp; deputy
            </p>
          </div>
          <div className="p-6 space-y-4">
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Functional Head</label>
              <select value={head} onChange={e => setHead(e.target.value)} className={selectCls}>
                <option value="">Unassigned</option>
                {candidates.map(c => <option key={c.user_id} value={c.user_id}>{c.full_name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Deputy Head (fallback)</label>
              <select value={deputy} onChange={e => setDeputy(e.target.value)} className={selectCls}>
                <option value="">None</option>
                {candidates.map(c => <option key={c.user_id} value={c.user_id}>{c.full_name}</option>)}
              </select>
              <p className="text-[9px] font-bold text-slate-400 mt-1">
                Used when the head is inactive or unavailable.
              </p>
            </div>
          </div>
          <DialogFooter className="px-6 py-4 bg-slate-50 border-t border-slate-100">
            <Button variant="ghost" onClick={() => setEditing(null)} className="text-[10px] font-black uppercase tracking-widest">Cancel</Button>
            <Button onClick={save} isLoading={saving} className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-black uppercase tracking-widest">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
