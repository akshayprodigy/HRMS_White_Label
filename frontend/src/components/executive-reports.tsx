import React, { useState, useEffect } from 'react';
import { 
  Clock, 
  Calendar, 
  CheckCircle2, 
  AlertCircle, 
  BarChart2,
  PieChart as PieIcon,
  Filter,
  DollarSign,
  TrendingUp,
  Loader2,
  Briefcase,
  Users,
  Target,
  ArrowUpRight,
  TrendingDown
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area, Cell, PieChart, Pie, LineChart, Line
} from 'recharts';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { ReportsSummary } from '../types/erp';

const COLORS = ['#2563EB', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6'];

export const ExecutiveReports = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ReportsSummary | null>(null);
  const [activeSegment, setActiveSegment] = useState<'all' | 'hr' | 'projects' | 'bd'>('all');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchReports();
  }, []);

  const fetchReports = async () => {
    try {
      setError(null);
      setLoading(true);
      const response = await client.get(ENDPOINTS.REPORTS.SUMMARY);
      setData(response.data);
    } catch (err: any) {
      const status = err?.response?.status;
      const msg = status >= 500
        ? 'Server error while loading reports.'
        : (err?.response?.data?.error?.message || 'No data found.');
      setData(null);
      setError(msg);
      console.error("Failed to fetch reports", err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-200px)]">
        <Loader2 className="w-12 h-12 text-blue-600 animate-spin mb-4" />
        <p className="text-slate-500 font-bold uppercase tracking-widest text-xs">Assembling Executive Intelligence...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-8 space-y-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-20">
        <Card className="p-10 border-2 border-dashed border-slate-200 text-center">
          <AlertCircle className="w-10 h-10 mx-auto text-red-500 mb-4" />
          <p className="text-sm font-black text-slate-700 uppercase tracking-widest">{error || 'No data found'}</p>
          <p className="text-xs text-slate-500 font-medium mt-2">Try refreshing. If it persists, check server logs.</p>
          <div className="mt-6">
            <Button variant="outline" onClick={fetchReports} className="h-11 px-6 font-black uppercase text-[10px] tracking-widest border-slate-200 bg-white">
              Refresh
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const attendanceCompliance = Array.isArray((data as any).attendance_compliance) ? (data as any).attendance_compliance : [];
  const projectUtilization = Array.isArray((data as any).project_utilization) ? (data as any).project_utilization : [];
  const costVariance = Array.isArray((data as any).cost_variance) ? (data as any).cost_variance : [];

  const attendanceChartData = attendanceCompliance.map((item: any) => ({
    day: new Date(item.date).toLocaleDateString('en-US', { weekday: 'short' }),
    rate: item.compliance_percentage
  })).reverse() || [];

  const projectHoursData = projectUtilization.map((item: any) => ({
    name: item.project_name,
    hours: item.total_hours
  })) || [];

  const costVarianceData = costVariance.map((item: any) => ({
    name: item.category,
    budget: item.budgeted_cost,
    actual: item.actual_cost
  })) || [];

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-20">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-[#0F172A] flex items-center justify-center text-white">
              <TrendingUp size={20} />
            </div>
            <h2 className="text-4xl font-black text-[#0F172A] tracking-tighter uppercase italic">Executive Radar</h2>
          </div>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] ml-13">United Exploration Global Performance Dashboard</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex bg-slate-100 p-1 rounded-xl mr-2">
            {(['all', 'hr', 'projects', 'bd'] as const).map((seg) => (
              <button
                key={seg}
                onClick={() => setActiveSegment(seg)}
                className={cn(
                  "px-6 py-2 rounded-lg text-[9px] font-black uppercase tracking-widest transition-all",
                  activeSegment === seg ? "bg-white shadow-sm text-blue-600" : "text-slate-500 hover:text-slate-700"
                )}
              >
                {seg}
              </button>
            ))}
          </div>
          <Button variant="outline" onClick={fetchReports} className="h-11 px-6 font-black uppercase text-[10px] tracking-widest border-slate-200 bg-white">
            Refresh
          </Button>
          <Button className="h-11 px-6 font-black uppercase text-[10px] tracking-widest bg-blue-600 shadow-lg shadow-blue-200">
            Export Master Report
          </Button>
        </div>
      </div>

      {/* High-Level KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {[
          { label: 'Enterprise Assets', value: data?.attendance_compliance[0]?.total_employees || 0, icon: Users, color: 'text-slate-900', trend: '+2% M/M' },
          { label: 'Operational Compliance', value: `${(data?.attendance_compliance.reduce((a,c) => a+c.compliance_percentage, 0) / (data?.attendance_compliance.length || 1)).toFixed(1)}%`, icon: CheckCircle2, color: 'text-green-600', trend: 'Optimal' },
          { label: 'Total Precision Hours', value: data?.project_utilization.reduce((a,c) => a+c.total_hours, 0).toFixed(0), icon: Clock, color: 'text-blue-600', trend: '+124h' },
          { label: 'Active Initiatives', value: data?.project_utilization.length, icon: Briefcase, color: 'text-amber-600', trend: '3 Pipeline' },
        ].map((kpi, i) => (
          <Card key={i} className="p-6 border-slate-100 bg-white shadow-sm hover:shadow-md transition-all group overflow-hidden relative">
            <div className="absolute -right-4 -bottom-4 opacity-[0.03] group-hover:opacity-[0.05] transition-opacity">
              <kpi.icon size={100} />
            </div>
            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">{kpi.label}</p>
            <div className="flex items-end justify-between">
              <h3 className={cn("text-3xl font-black tracking-tight", kpi.color)}>{kpi.value}</h3>
              <Badge variant="info" className="text-[8px] font-black">{kpi.trend}</Badge>
            </div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Attendance & Human Capital (HR Segment) */}
        {(activeSegment === 'all' || activeSegment === 'hr') && (
          <Card className="p-8 border-slate-200 shadow-sm bg-white space-y-8">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase italic">Human Capital Utilization</h4>
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">7-Day Attendance & Availability Matrix</p>
              </div>
              <Users className="text-slate-200" size={32} />
            </div>
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={attendanceChartData}>
                  <defs>
                    <linearGradient id="colorRate" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#2563EB" stopOpacity={0.1}/>
                      <stop offset="95%" stopColor="#2563EB" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />
                  <XAxis 
                    dataKey="day" 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{fill: '#64748B', fontSize: 10, fontWeight: 900}} 
                  />
                  <YAxis 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{fill: '#64748B', fontSize: 10, fontWeight: 900}} 
                  />
                  <Tooltip 
                    contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)'}}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="rate" 
                    stroke="#2563EB" 
                    strokeWidth={4}
                    fillOpacity={1} 
                    fill="url(#colorRate)" 
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>
        )}

        {/* Project Resource Allocation (Projects Segment) */}
        {(activeSegment === 'all' || activeSegment === 'projects') && (
          <Card className="p-8 border-slate-200 shadow-sm bg-white space-y-8">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase italic">Project Bandwidth Distribution</h4>
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">Resource allocation by project total hours</p>
              </div>
              <Briefcase className="text-slate-200" size={32} />
            </div>
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={projectHoursData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#F1F5F9" />
                  <XAxis type="number" hide />
                  <YAxis 
                    dataKey="name" 
                    type="category" 
                    axisLine={false} 
                    tickLine={false} 
                    width={100}
                    tick={{fill: '#64748B', fontSize: 9, fontWeight: 900}} 
                  />
                  <Tooltip />
                  <Bar dataKey="hours" radius={[0, 4, 4, 0]}>
                    {projectHoursData.map((_, index) => (
                      <Cell key={index} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        )}

        {/* Financial Governance (General) */}
        {(activeSegment === 'all' || activeSegment === 'projects') && (
          <Card className="p-8 border-slate-200 shadow-sm bg-white space-y-8">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase italic">Financial Governance Matrix</h4>
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">Variance analysis: Budgeted vs Actuals</p>
              </div>
              <DollarSign className="text-slate-200" size={32} />
            </div>
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={costVarianceData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />
                  <XAxis 
                    dataKey="name" 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{fill: '#64748B', fontSize: 10, fontWeight: 900}} 
                  />
                  <YAxis 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{fill: '#64748B', fontSize: 10, fontWeight: 900}} 
                  />
                  <Tooltip />
                  <Bar dataKey="budget" fill="#E2E8F0" radius={[4, 4, 0, 0]} name="Budgeted" />
                  <Bar dataKey="actual" fill="#2563EB" radius={[4, 4, 0, 0]} name="Actual" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        )}

        {/* Pipeline & Strategic Growth (BD Segment) */}
        {(activeSegment === 'all' || activeSegment === 'bd') && (
          <Card className="p-8 border-slate-200 shadow-sm bg-white space-y-8 flex flex-col items-center justify-center min-h-[400px]">
            <Target className="text-blue-100 mb-4" size={64} />
            <h4 className="text-lg font-black text-[#0F172A] uppercase tracking-tight">Strategic Growth Pipeline</h4>
            <p className="text-xs text-slate-400 font-bold uppercase tracking-widest text-center max-w-sm">
              Lead generation, conversion rates, and valuation metrics are currently being aggregated from Global CRM.
            </p>
            <div className="mt-8 grid grid-cols-2 gap-4 w-full">
              <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100 text-center">
                <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Weighted Value</p>
                <p className="text-xl font-black text-slate-900">₹1.2M</p>
              </div>
              <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100 text-center">
                <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Win Probability</p>
                <p className="text-xl font-black text-green-600">68%</p>
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* Detail Table Area */}
      {activeSegment !== 'all' && (
        <Card className="border-slate-200 bg-white overflow-hidden shadow-sm animate-in slide-in-from-bottom-5 duration-500">
          <div className="p-6 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
            <h5 className="text-[10px] font-black text-[#0F172A] uppercase tracking-[0.2em]">Detailed {activeSegment.toUpperCase()} Report</h5>
            <div className="flex gap-2">
              <Badge variant="neutral" className="text-[8px] font-black uppercase tracking-widest">{data?.attendance_compliance.length || 0} Records Found</Badge>
              <Button variant="outline" size="sm" className="h-8 px-4 font-black uppercase text-[8px] tracking-widest bg-white">
                Download CSV
              </Button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-slate-50/50">
                  <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Dimension</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest text-center">Metric A</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest text-center">Metric B</th>
                  <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {activeSegment === 'hr' && attendanceCompliance.map((item: any, idx: number) => (
                  <tr key={idx} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-6 py-4 font-bold text-slate-700 text-sm">{new Date(item.date).toLocaleDateString()}</td>
                    <td className="px-6 py-4 text-center font-black text-blue-600">{item.total_employees} Empl.</td>
                    <td className="px-6 py-4 text-center font-black text-slate-900">{item.compliance_percentage}%</td>
                    <td className="px-6 py-4 text-right">
                      <Badge variant={item.compliance_percentage > 90 ? 'success' : 'warning'} className="text-[9px] font-black">
                        {item.compliance_percentage > 90 ? 'COMPLIANT' : 'REVIEW'}
                      </Badge>
                    </td>
                  </tr>
                ))}
                {activeSegment === 'projects' && projectUtilization.map((item: any, idx: number) => (
                  <tr key={idx} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-6 py-4 font-bold text-slate-700 text-sm">{item.project_name}</td>
                    <td className="px-6 py-4 text-center font-black text-blue-600">{item.total_hours.toFixed(1)} HRS</td>
                    <td className="px-6 py-4 text-center font-black text-slate-900">{item.active_employees} Staff</td>
                    <td className="px-6 py-4 text-right">
                      <Badge variant="info" className="text-[9px] font-black uppercase">Active</Badge>
                    </td>
                  </tr>
                ))}
                {activeSegment === 'bd' && (
                  <tr>
                    <td colSpan={4} className="px-6 py-20 text-center text-[10px] font-black text-slate-400 uppercase tracking-widest">
                      Granular Pipeline Data Loading from BD Service...
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
};
