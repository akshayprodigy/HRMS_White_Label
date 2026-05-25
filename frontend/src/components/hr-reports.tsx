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
  Loader2
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area, Cell, PieChart, Pie
} from 'recharts';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { ReportsSummary } from '../types/erp';

const COLORS = ['#2563EB', '#10B981', '#F59E0B', '#EF4444'];

export const HRReports = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ReportsSummary | null>(null);
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
        <p className="text-slate-500 font-bold uppercase tracking-widest text-xs">Generating Real-time Intelligence...</p>
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
                     Refresh Data
                  </Button>
               </div>
            </Card>
         </div>
      );
   }

   const attendanceCompliance = Array.isArray((data as any).attendance_compliance) ? (data as any).attendance_compliance : [];
   const projectUtilization = Array.isArray((data as any).project_utilization) ? (data as any).project_utilization : [];
   const costVariance = Array.isArray((data as any).cost_variance) ? (data as any).cost_variance : [];
   const leaveBalances = Array.isArray((data as any).leave_balances) ? (data as any).leave_balances : [];

   const attendanceChartData = attendanceCompliance.map((item: any) => ({
    day: new Date(item.date).toLocaleDateString('en-US', { weekday: 'short' }),
    rate: item.compliance_percentage
  })).reverse() || [];

   const presenceAvg = attendanceCompliance.length 
      ? (attendanceCompliance.reduce((acc: number, curr: any) => acc + (curr.compliance_percentage || 0), 0) / attendanceCompliance.length).toFixed(1)
    : "0";

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-20">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Enterprise Intelligence Reports</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Consolidated Operational Analytics</p>
        </div>
        <div className="flex gap-2">
           <Button variant="outline" onClick={fetchReports} className="h-11 px-6 font-black uppercase text-[10px] tracking-widest border-slate-200 bg-white">
              Refresh Data
           </Button>
           <Button className="h-11 px-6 font-black uppercase text-[10px] tracking-widest bg-blue-600">
              Export PDF
           </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Card className="p-6 border-slate-200 bg-white">
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Total Assets</p>
              <h3 className="text-3xl font-black text-[#0F172A]">{attendanceCompliance[0]?.total_employees || 0}</h3>
          </Card>
          <Card className="p-6 border-slate-200 bg-white">
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">7D Presence Avg.</p>
              <h3 className="text-3xl font-black text-green-600">{presenceAvg}%</h3>
          </Card>
          <Card className="p-6 border-slate-200 bg-white">
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Project Hours</p>
              <h3 className="text-3xl font-black text-blue-600">{projectUtilization.reduce((acc: number, curr: any) => acc + (curr.total_hours || 0), 0).toFixed(1)}</h3>
          </Card>
          <Card className="p-6 border-slate-200 bg-white">
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Active Projects</p>
              <h3 className="text-3xl font-black text-amber-600">{projectUtilization.length}</h3>
          </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
         {/* Attendance Trend */}
         <Card className="p-8 border-slate-200 shadow-sm bg-white space-y-8">
            <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase flex items-center gap-2">
                <BarChart2 className="text-blue-600" /> Attendance Compliance Trend
            </h4>
            <div className="h-[300px] w-full min-h-[300px]">
               <ResponsiveContainer width="99%" height="100%">
                  <AreaChart data={attendanceChartData}>
                     <defs>
                        <linearGradient id="colorRate" x1="0" y1="0" x2="0" y2="1">
                           <stop offset="5%" stopColor="#2563EB" stopOpacity={0.1}/>
                           <stop offset="95%" stopColor="#2563EB" stopOpacity={0}/>
                        </linearGradient>
                     </defs>
                     <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />
                     <XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fontSize: 10, fontWeight: 900, fill: '#94A3B8' }} />
                     <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fontWeight: 900, fill: '#94A3B8' }} domain={[0, 100]} />
                     <Tooltip />
                     <Area type="monotone" dataKey="rate" stroke="#2563EB" strokeWidth={4} fillOpacity={1} fill="url(#colorRate)" />
                  </AreaChart>
               </ResponsiveContainer>
            </div>
         </Card>

         {/* Project Utilization */}
         <Card className="p-8 border-slate-200 shadow-sm bg-white space-y-8">
            <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase flex items-center gap-2">
                <TrendingUp className="text-blue-600" /> Project Resource Allocation
            </h4>
            <div className="h-[300px] w-full min-h-[300px]">
               <ResponsiveContainer width="99%" height="100%">
                  <BarChart data={projectUtilization}>
                     <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />
                     <XAxis dataKey="project_name" axisLine={false} tickLine={false} tick={{ fontSize: 10, fontWeight: 900, fill: '#94A3B8' }} />
                     <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fontWeight: 900, fill: '#94A3B8' }} />
                     <Tooltip />
                     <Bar dataKey="total_hours" fill="#2563EB" radius={[4, 4, 0, 0]} />
                  </BarChart>
               </ResponsiveContainer>
            </div>
         </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Cost Variance */}
          <Card className="border-slate-200 shadow-sm bg-white overflow-hidden">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
               <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase flex items-center gap-2">
                  <DollarSign className="w-4 h-4 text-emerald-600" /> Financial Variance Tracker
               </h4>
               <Badge className="bg-emerald-50 text-emerald-700 border-emerald-100">Live Budgeting</Badge>
            </div>
            <div className="overflow-x-auto">
               <table className="w-full text-left">
                  <thead>
                     <tr className="bg-white border-b border-slate-50">
                        <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Project Name</th>
                        <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Budget</th>
                        <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Actual</th>
                        <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-right">Variance</th>
                     </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                     {costVariance.map((item: any, idx: number) => (
                        <tr key={idx} className="hover:bg-slate-50 transition-colors">
                           <td className="px-6 py-4">
                              <span className="text-sm font-black text-[#0F172A]">{item.category}</span>
                           </td>
                           <td className="px-6 py-4">
                              <span className="text-xs font-bold text-slate-600">₹{item.budgeted_cost.toLocaleString('en-IN')}</span>
                           </td>
                           <td className="px-6 py-4">
                              <span className="text-xs font-bold text-slate-600">₹{item.actual_cost.toLocaleString('en-IN')}</span>
                           </td>
                           <td className="px-6 py-4 text-right">
                              <span className={cn(
                                "text-xs font-black px-2 py-1 rounded-full",
                                item.variance >= 0 ? "text-emerald-600 bg-emerald-50" : "text-rose-600 bg-rose-50"
                              )}>
                                {item.variance >= 0 ? '+' : ''}{item.variance.toLocaleString()} ({item.variance_percentage}%)
                              </span>
                           </td>
                        </tr>
                     ))}
                  </tbody>
               </table>
            </div>
          </Card>

          {/* Leave Balances */}
          <Card className="border-slate-200 shadow-sm bg-white overflow-hidden">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
               <h4 className="text-sm font-black text-[#0F172A] tracking-tight uppercase flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-blue-600" /> Leave Balance Registry
               </h4>
               <Badge className="bg-blue-50 text-blue-700 border-blue-100">Annual Quota</Badge>
            </div>
            <div className="overflow-x-auto">
               <table className="w-full text-left">
                  <thead>
                     <tr className="bg-white border-b border-slate-50">
                        <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Employee</th>
                        <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest">Type</th>
                        <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-right">Allotted</th>
                        <th className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-right">Remaining</th>
                     </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                          {leaveBalances.slice(0, 10).map((item: any, idx: number) => (
                        <tr key={idx} className="hover:bg-slate-50 transition-colors">
                           <td className="px-6 py-4">
                              <span className="text-sm font-black text-[#0F172A]">{item.employee_name}</span>
                           </td>
                           <td className="px-6 py-4">
                              <Badge variant="outline" className="text-[10px] font-black uppercase tracking-tighter">{item.leave_type}</Badge>
                           </td>
                           <td className="px-6 py-4 text-right">
                              <span className="text-xs font-bold text-slate-600">{item.total_allotted} Days</span>
                           </td>
                           <td className="px-6 py-4 text-right">
                              <span className="text-xs font-black text-blue-600">{item.remaining} Days</span>
                           </td>
                        </tr>
                     ))}
                  </tbody>
               </table>
            </div>
          </Card>
      </div>
    </div>
  );
};
