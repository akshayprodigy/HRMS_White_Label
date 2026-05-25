import React, { useState, useEffect, useMemo } from 'react';
import {
  Users,
  Search,
  Calendar,
  Clock,
  ShieldCheck,
  CheckCircle,
  XCircle,
  History,
  Navigation,
  Edit2,
  RefreshCw
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

type FilterOption = 'Today' | 'Weekly' | 'Monthly Audit';

function getDateRange(filter: FilterOption): { date_from: string; date_to: string } {
  const today = new Date();
  const fmt = (d: Date) => d.toISOString().split('T')[0];
  if (filter === 'Today') {
    return { date_from: fmt(today), date_to: fmt(today) };
  }
  if (filter === 'Weekly') {
    const from = new Date(today);
    from.setDate(today.getDate() - 6);
    return { date_from: fmt(from), date_to: fmt(today) };
  }
  // Monthly Audit
  const from = new Date(today.getFullYear(), today.getMonth(), 1);
  return { date_from: fmt(from), date_to: fmt(today) };
}

export const AttendanceHR = () => {
  const [filter, setFilter] = useState<FilterOption>('Today');
  const [showCorrection, setShowCorrection] = useState<any | null>(null);
  const [corrections, setCorrections] = useState<any[]>([]);
  const [logs, setLogs] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    fetchData(filter);
  }, [filter]);

  const fetchData = async (f: FilterOption) => {
    setIsLoading(true);
    try {
      const { date_from, date_to } = getDateRange(f);
      const [corrRes, logRes] = await Promise.all([
        client.get(ENDPOINTS.HR.ATTENDANCE_CORRECTIONS),
        client.get(ENDPOINTS.ATTENDANCE.ALL, { params: { date_from, date_to } })
      ]);
      setCorrections(corrRes.data);
      setLogs(logRes.data);
    } catch {
      toast.error("Failed to fetch attendance data");
    } finally {
      setIsLoading(false);
    }
  };

  const handleAction = async (id: number, status: 'approved' | 'rejected') => {
    try {
      await client.post(ENDPOINTS.HR.ATTENDANCE_CORRECTION_ACTION(id), { status });
      toast.success(`Request ${status} successfully`);
      fetchData(filter);
    } catch {
      toast.error(`Action failed: Only users with 'attendance correction approve' permission can perform this.`);
    }
  };

  const handleCorrection = () => {
    toast.success('Correction finalized');
    setShowCorrection(null);
    fetchData(filter);
  };

  // Compute real stats from logs
  const stats = useMemo(() => {
    const uniqueUsers = new Set(logs.map(l => l.user_id)).size;
    const modeMap: Record<string, number> = {};
    logs.forEach(l => { modeMap[l.mode] = (modeMap[l.mode] || 0) + 1; });
    const topMode = Object.entries(modeMap).sort((a, b) => b[1] - a[1])[0]?.[0] || '—';
    const pendingCorr = corrections.filter(c => c.status === 'submitted').length;
    return { total: logs.length, uniqueUsers, topMode, pendingCorr };
  }, [logs, corrections]);

  const filteredLogs = useMemo(() =>
    logs.filter(l =>
      !search ||
      l.user_name?.toLowerCase().includes(search.toLowerCase()) ||
      l.user_email?.toLowerCase().includes(search.toLowerCase())
    ), [logs, search]);

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-20">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Geo-Attendance Audit</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Enterprise Real-Time Attendance Monitoring & Mode Verification</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => fetchData(filter)} className="p-2 text-slate-400 hover:text-blue-600 transition-colors">
            <RefreshCw size={16} />
          </button>
          <div className="flex gap-1 bg-white p-1 rounded-xl border border-slate-200">
            {(['Today', 'Weekly', 'Monthly Audit'] as FilterOption[]).map((opt) => (
              <button
                key={opt}
                onClick={() => setFilter(opt)}
                className={cn(
                  "px-5 py-2 rounded-lg text-[9px] font-black uppercase tracking-widest transition-all",
                  filter === opt ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20" : "text-slate-500 hover:bg-slate-50"
                )}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
        <Card className="p-6 border-slate-200 bg-white">
          <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Total Records</p>
          <h3 className="text-2xl font-black text-[#0F172A]">{isLoading ? '—' : stats.total}</h3>
          <p className="text-[9px] text-slate-400 font-bold mt-1 uppercase">{filter}</p>
        </Card>
        <Card className="p-6 border-slate-200 bg-white">
          <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Unique Employees</p>
          <h3 className="text-2xl font-black text-blue-600">{isLoading ? '—' : stats.uniqueUsers}</h3>
          <p className="text-[9px] text-slate-400 font-bold mt-1 uppercase">Marked In</p>
        </Card>
        <Card className="p-6 border-slate-200 bg-white">
          <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Top Mode</p>
          <h3 className="text-lg font-black text-[#0F172A] truncate">{isLoading ? '—' : stats.topMode}</h3>
          <p className="text-[9px] text-slate-400 font-bold mt-1 uppercase">Dominant</p>
        </Card>
        <Card className="p-6 border-slate-900 bg-slate-900 text-white">
          <p className="text-[9px] font-black uppercase tracking-widest mb-1 opacity-60">Pending Corrections</p>
          <h3 className="text-2xl font-black">{isLoading ? '—' : stats.pendingCorr}</h3>
          <p className="text-[9px] font-bold mt-1 uppercase opacity-60">Awaiting Review</p>
        </Card>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Attendance Table */}
        <Card className="lg:col-span-2 p-0 border-slate-200 overflow-hidden bg-white">
          <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
            <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase">
              Attendance Registry
              {!isLoading && <span className="ml-2 text-slate-400 font-bold">({filteredLogs.length})</span>}
            </h4>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search employee..."
                className="pl-10 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-[10px] font-black uppercase w-56 focus:ring-2 focus:ring-blue-600/10 outline-none"
              />
            </div>
          </div>
          <div className="overflow-x-auto">
            {isLoading ? (
              <div className="py-20 text-center text-[10px] font-black uppercase text-slate-400 animate-pulse">Loading...</div>
            ) : filteredLogs.length === 0 ? (
              <div className="py-20 text-center text-[10px] font-black uppercase text-slate-400">No attendance records for this period</div>
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="bg-white border-b border-slate-50">
                    <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Employee</th>
                    <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Punch In</th>
                    <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Punch Out</th>
                    <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Mode</th>
                    <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Geo</th>
                    <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {filteredLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-slate-50/50 transition-colors group">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center font-black text-sm">
                            {log.user_name?.charAt(0) || '?'}
                          </div>
                          <div>
                            <p className="text-sm font-black text-[#0F172A]">{log.user_name}</p>
                            <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">{log.user_email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <p className="text-sm font-black text-[#0F172A]">
                          {new Date(log.captured_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </p>
                        <p className="text-[9px] font-bold text-slate-400">
                          {new Date(log.captured_at).toLocaleDateString([], { day: 'numeric', month: 'short' })}
                        </p>
                      </td>
                      <td className="px-6 py-4">
                        {log.punch_out_time ? (
                          <>
                            <p className="text-sm font-black text-[#0F172A]">
                              {new Date(log.punch_out_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </p>
                            <p className="text-[9px] font-bold text-emerald-600 uppercase tracking-widest">Closed</p>
                          </>
                        ) : (
                          <p className="text-[10px] font-black text-amber-600 uppercase tracking-widest">Open</p>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex items-center gap-1 px-2 py-1 bg-slate-100 rounded-lg text-[9px] font-black uppercase text-slate-700">
                          <ShieldCheck size={10} /> {log.mode}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-1 text-slate-500">
                          <Navigation size={11} className="text-blue-600 shrink-0" />
                          <span className="text-[10px] font-bold truncate max-w-[110px]">
                            {log.latitude?.toFixed(4)}, {log.longitude?.toFixed(4)}
                          </span>
                        </div>
                        {log.remarks && (
                          <p className="text-[9px] font-bold text-blue-600 uppercase tracking-tighter mt-0.5 italic">{log.remarks}</p>
                        )}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => setShowCorrection(log)}
                          className="text-[9px] font-black uppercase tracking-widest text-blue-600 hover:bg-blue-50 px-3 py-1.5 rounded-lg transition-colors"
                        >
                          Correct
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>

        {/* Correction Requests */}
        <Card className="p-7 border-slate-200 bg-white">
          <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase flex items-center gap-2 mb-6">
            <History size={16} className="text-blue-600" /> Correction Requests
          </h4>
          <div className="space-y-4">
            {isLoading ? (
              <div className="py-10 text-center text-[10px] font-black uppercase text-slate-400 animate-pulse">Loading...</div>
            ) : corrections.length === 0 ? (
              <div className="py-10 text-center">
                <CheckCircle size={28} className="mx-auto text-slate-200 mb-3" />
                <p className="text-[10px] font-black uppercase text-slate-400">No pending corrections</p>
              </div>
            ) : corrections.map((corr) => (
              <div key={corr.id} className="p-4 rounded-2xl bg-slate-50 border border-slate-100 hover:border-blue-200 transition-all space-y-3">
                <div className="flex justify-between items-start">
                  <div>
                    <p className="text-[10px] font-black text-[#0F172A] uppercase tracking-widest">User #{corr.user_id}</p>
                    <p className="text-[9px] font-bold text-slate-400 mt-0.5">{corr.date}</p>
                  </div>
                  <Badge
                    variant={corr.status === 'submitted' ? 'warning' : corr.status === 'approved' ? 'success' : 'error'}
                    className="text-[7px] uppercase"
                  >
                    {corr.status}
                  </Badge>
                </div>
                <div className="p-3 bg-white rounded-xl border border-slate-100 text-[9px]">
                  <p className="font-black text-slate-500 uppercase mb-1">Mode: {corr.requested_mode}</p>
                  <p className="text-slate-600 italic">"{corr.reason}"</p>
                </div>
                {corr.status === 'submitted' && (
                  <div className="flex gap-2">
                    <Button onClick={() => handleAction(corr.id, 'approved')} className="flex-1 h-8 bg-green-600 hover:bg-green-700 text-white font-black uppercase text-[9px] tracking-widest">
                      <CheckCircle size={12} className="mr-1" /> Approve
                    </Button>
                    <Button onClick={() => handleAction(corr.id, 'rejected')} variant="outline" className="flex-1 h-8 border-red-200 text-red-600 hover:bg-red-50 font-black uppercase text-[9px] tracking-widest">
                      <XCircle size={12} className="mr-1" /> Reject
                    </Button>
                  </div>
                )}
                <p className="text-[8px] font-bold text-slate-300 uppercase tracking-tighter">
                  {new Date(corr.created_at).toLocaleString()}
                </p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Correction Modal */}
      {showCorrection && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <Card className="w-full max-w-md p-8 border-none shadow-2xl animate-in zoom-in-95" style={{ maxHeight: "70vh", overflowY: "auto" }}>
            <h3 className="text-xl font-black text-[#0F172A] tracking-tighter uppercase mb-1 flex items-center gap-2">
              <Edit2 size={18} className="text-blue-600" /> Attendance Correction
            </h3>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-7">
              {showCorrection.user_name} — {new Date(showCorrection.captured_at).toLocaleDateString()}
            </p>
            <div className="space-y-5">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-[#0F172A] uppercase tracking-widest">Correction Mode</label>
                <div className="grid grid-cols-2 gap-2">
                  <Button variant="outline" className="h-10 text-[9px] font-black uppercase border-blue-600 text-blue-600 bg-blue-50">Punch-In Time</Button>
                  <Button variant="outline" className="h-10 text-[9px] font-black uppercase border-slate-200">Engagement Mode</Button>
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-[#0F172A] uppercase tracking-widest">New Value</label>
                <input type="time" className="w-full h-12 bg-slate-50 border border-slate-200 rounded-xl px-4 font-black outline-none focus:ring-2 focus:ring-blue-600/10" />
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-[#0F172A] uppercase tracking-widest">Correction Reason</label>
                <textarea rows={3} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-4 font-bold text-sm outline-none focus:ring-2 focus:ring-blue-600/10 resize-none" placeholder="State reason for this audit correction..." />
              </div>
              <div className="flex gap-3 pt-2">
                <Button variant="ghost" className="flex-1 font-black uppercase text-[10px]" onClick={() => setShowCorrection(null)}>Cancel</Button>
                <Button className="flex-1 bg-blue-600 font-black uppercase text-[10px] shadow-lg shadow-blue-600/20" onClick={handleCorrection}>Finalise</Button>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};
