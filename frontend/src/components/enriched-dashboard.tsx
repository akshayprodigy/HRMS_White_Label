/**
 * Enriched HR dashboard: replaces static tiles with time-series charts
 * (headcount trend, attrition, OT trend, leave utilization) that
 * drill down to the underlying report on click.
 *
 * All chart data comes from the same report engine endpoints — no
 * duplicate computation.
 */
import React, { useEffect, useState } from 'react';
import {
  Users, TrendingUp, TrendingDown, Clock, CalendarDays,
  RefreshCw, ArrowRight,
} from 'lucide-react';
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ComposedChart,
} from 'recharts';
import { Card, Button } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface Props {
  onDrillDown?: (reportKey: string, filters?: any) => void;
}

const errMsg = (e: any, fb: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return e?.message || fb;
};

const CHART_COLORS = {
  joiners: '#16A34A',      // green-600
  leavers: '#DC2626',      // red-600
  net: '#2563EB',           // blue-600
  headcount: '#0F172A',     // slate-900
  attrition: '#7C3AED',    // violet-600
  ot: '#EA580C',            // orange-600
  leave_used: '#0891B2',    // cyan-600
  leave_quota: '#E5E7EB',   // gray-200
};

export const EnrichedDashboardView: React.FC<Props> = ({ onDrillDown }) => {
  const [loading, setLoading] = useState(true);
  const [headcount, setHeadcount] = useState<any[]>([]);
  const [attrition, setAttrition] = useState<any[]>([]);
  const [otData, setOtData] = useState<any[]>([]);
  const [leaveData, setLeaveData] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [hc, at, ot, leave] = await Promise.all([
        client.post(ENDPOINTS.REPORTS_ENGINE.RUN('headcount_trend'),
          {}, { params: { format: 'json' } }).catch(() => null),
        client.post(ENDPOINTS.REPORTS_ENGINE.RUN('attrition_report'),
          {}, { params: { format: 'json' } }).catch(() => null),
        client.post(ENDPOINTS.REPORTS_ENGINE.RUN('ot_report'),
          {}, { params: { format: 'json' } }).catch(() => null),
        client.post(ENDPOINTS.REPORTS_ENGINE.RUN('leave_utilization'),
          {}, { params: { format: 'json' } }).catch(() => null),
      ]);

      setHeadcount(hc?.data?.rows || []);
      setAttrition(at?.data?.rows || []);
      // OT — group by department for a bar chart
      const otByDept: Record<string, { department: string; total_amount: number; total_minutes: number }> = {};
      for (const r of ot?.data?.rows || []) {
        const dept = r.department || '—';
        if (!otByDept[dept]) otByDept[dept] = { department: dept, total_amount: 0, total_minutes: 0 };
        otByDept[dept].total_amount += (r.total_amount || 0);
        otByDept[dept].total_minutes += (r.total_minutes || 0);
      }
      setOtData(Object.values(otByDept));
      setLeaveData(leave?.data?.rows || []);
    } catch (e: any) { setError(errMsg(e, 'Failed to load dashboard')); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, []);

  const latestHc = headcount[headcount.length - 1];
  const latestAt = attrition[attrition.length - 1];
  const totalOtAmount = otData.reduce((s, r) => s + r.total_amount, 0);
  const totalLeaveUsed = leaveData.reduce((s: number, r: any) => s + (r.total_used || 0), 0);
  const totalLeaveQuota = leaveData.reduce((s: number, r: any) => s + (r.total_quota || 0), 0);
  const utilPct = totalLeaveQuota > 0
    ? Math.round((totalLeaveUsed / totalLeaveQuota) * 100)
    : 0;

  const drill = (key: string, filters?: any) => {
    if (onDrillDown) onDrillDown(key, filters);
    else toast.info('Drill-down opens the underlying report in the Reports catalog.');
  };

  const Tile: React.FC<{
    icon: any; label: string; value: React.ReactNode;
    tone: string; subline?: React.ReactNode;
    onClick?: () => void;
  }> = ({ icon: Icon, label, value, tone, subline, onClick }) => (
    <button onClick={onClick} disabled={!onClick}
      className={`text-left border rounded-lg p-4 w-full transition ${tone} ${onClick ? 'hover:shadow-md cursor-pointer' : ''}`}>
      <div className="text-[10px] uppercase font-semibold flex items-center gap-1 opacity-80">
        <Icon className="w-3 h-3" /> {label}
        {onClick && <ArrowRight className="w-3 h-3 ml-auto opacity-40" />}
      </div>
      <div className="text-2xl font-bold mt-1">{value}</div>
      {subline && <div className="text-[10px] mt-1 opacity-70">{subline}</div>}
    </button>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Enriched HR Dashboard</h1>
          <p className="text-sm text-slate-500 mt-1">
            Tiles are drill-ins. Click any tile or chart to open the underlying report with the same filter.
          </p>
        </div>
        <Button variant="outline" onClick={fetchAll}><RefreshCw className="w-4 h-4" /></Button>
      </div>

      {loading && (
        <Card className="p-12 text-center text-slate-500">Loading dashboards…</Card>
      )}

      {error && (
        <Card className="p-4 bg-red-50 border-red-200 text-red-700 text-sm">
          {error}
        </Card>
      )}

      {!loading && !error && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <Tile
              icon={Users} label="Current headcount"
              value={latestHc?.closing ?? '—'}
              tone="bg-slate-50 border-slate-200"
              subline={latestHc?.month_label}
              onClick={() => drill('headcount_trend')}
            />
            <Tile
              icon={TrendingUp} label="Joiners (last month)"
              value={latestHc?.joiners ?? 0}
              tone="bg-green-50 border-green-200 text-green-700"
              onClick={() => drill('headcount_trend')}
            />
            <Tile
              icon={TrendingDown} label="Leavers (last month)"
              value={latestHc?.leavers ?? 0}
              tone="bg-red-50 border-red-200 text-red-700"
              onClick={() => drill('attrition_report')}
            />
            <Tile
              icon={Users} label="Attrition rate"
              value={`${latestAt?.attrition_pct ?? 0}%`}
              tone="bg-violet-50 border-violet-200 text-violet-700"
              subline="Latest month"
              onClick={() => drill('attrition_report')}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="p-4">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-semibold">Headcount trend (12 months)</h2>
                <button onClick={() => drill('headcount_trend')}
                  className="text-xs text-blue-600 hover:underline">Open report →</button>
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <ComposedChart data={headcount}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                  <XAxis dataKey="month_label" fontSize={11} />
                  <YAxis fontSize={11} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="joiners" fill={CHART_COLORS.joiners} name="Joiners" />
                  <Bar dataKey="leavers" fill={CHART_COLORS.leavers} name="Leavers" />
                  <Line type="monotone" dataKey="closing" stroke={CHART_COLORS.headcount}
                    strokeWidth={2} name="Headcount" dot={{ r: 3 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </Card>

            <Card className="p-4">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-semibold">Attrition rate trend</h2>
                <button onClick={() => drill('attrition_report')}
                  className="text-xs text-blue-600 hover:underline">Open report →</button>
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={attrition}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                  <XAxis dataKey="month_label" fontSize={11} />
                  <YAxis fontSize={11}
                    tickFormatter={(v: any) => `${v}%`} />
                  <Tooltip formatter={(v: any) => `${v}%`} />
                  <Line type="monotone" dataKey="attrition_pct"
                    stroke={CHART_COLORS.attrition} strokeWidth={2}
                    name="Attrition %" dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </Card>

            <Card className="p-4">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-semibold flex items-center gap-2">
                  <Clock className="w-4 h-4" /> Overtime by department
                </h2>
                <button onClick={() => drill('ot_report')}
                  className="text-xs text-blue-600 hover:underline">Open report →</button>
              </div>
              {otData.length === 0 ? (
                <div className="py-12 text-center text-slate-500 text-sm">No OT in the selected window.</div>
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={otData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                    <XAxis dataKey="department" fontSize={11} />
                    <YAxis fontSize={11}
                      tickFormatter={(v: any) => `₹${Math.round(v / 1000)}k`} />
                    <Tooltip formatter={(v: any) => `₹${Math.round(v).toLocaleString('en-IN')}`} />
                    <Bar dataKey="total_amount" fill={CHART_COLORS.ot} name="OT amount" />
                  </BarChart>
                </ResponsiveContainer>
              )}
              <div className="mt-2 text-xs text-slate-500">
                Total OT payout: <span className="font-semibold">₹{Math.round(totalOtAmount).toLocaleString('en-IN')}</span>
              </div>
            </Card>

            <Card className="p-4">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-semibold flex items-center gap-2">
                  <CalendarDays className="w-4 h-4" /> Leave utilization by type
                </h2>
                <button onClick={() => drill('leave_utilization')}
                  className="text-xs text-blue-600 hover:underline">Open report →</button>
              </div>
              {leaveData.length === 0 ? (
                <div className="py-12 text-center text-slate-500 text-sm">No leave data.</div>
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={leaveData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                    <XAxis dataKey="leave_type" fontSize={11} />
                    <YAxis fontSize={11} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="total_quota" fill={CHART_COLORS.leave_quota} name="Quota" />
                    <Bar dataKey="total_used" fill={CHART_COLORS.leave_used} name="Used" />
                  </BarChart>
                </ResponsiveContainer>
              )}
              <div className="mt-2 text-xs text-slate-500">
                Org-wide utilization: <span className="font-semibold">{utilPct}%</span>
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
};
