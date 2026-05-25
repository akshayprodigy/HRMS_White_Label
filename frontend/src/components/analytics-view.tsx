import React, { useState, useEffect } from 'react';
import { 
  BarChart3, 
  TrendingUp, 
  ArrowUpRight, 
  ArrowDownRight, 
  Users, 
  Clock, 
  DollarSign,
  PieChart as PieChartIcon,
  AlertCircle
} from 'lucide-react';
import { Card, Badge } from './ui-elements';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie
} from 'recharts';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { toast } from 'sonner';

const COLORS = ['#2563EB', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6'];

export const AnalyticsView = () => {
  const [data, setData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const fetchAnalytics = async () => {
    try {
      setIsLoading(true);
      const [reportsRes, statsRes] = await Promise.all([
        client.get(ENDPOINTS.REPORTS.SUMMARY),
        client.get(ENDPOINTS.HR.DASHBOARD_STATS)
      ]);
      setData({
        reports: reportsRes.data,
        stats: statsRes.data
      });
    } catch (error) {
      toast.error("Failed to load analytics data");
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const attendanceChartData = data?.reports?.attendance_compliance?.map((d: any) => ({
    name: new Date(d.date).toLocaleDateString(undefined, { weekday: 'short' }),
    present: d.present,
    absent: d.absent
  })) || [];

  const utilizationChartData = data?.reports?.project_utilization?.map((p: any) => ({
    name: p.project_name.substring(0, 10) + (p.project_name.length > 10 ? '...' : ''),
    score: p.utilization_score
  })) || [];

  const leaveChartData = data?.reports?.leave_balance_summary?.map((l: any) => ({
    name: l.department,
    value: l.avg_balance
  })) || [];

  const stats = [
    { label: 'Total Employees', value: data?.stats?.summary?.total_employees || 0, trend: '+4.5%', positive: true, icon: Users },
    { label: 'Present Today', value: data?.stats?.summary?.attendance_today?.present || 0, trend: '+1.2%', positive: true, icon: TrendingUp },
    { label: 'Active Projects', value: data?.reports?.project_utilization?.length || 0, trend: '+2.4%', positive: true, icon: BarChart3 },
    { label: 'Avg. Utilization', value: `${(utilizationChartData.reduce((acc: number, curr: any) => acc + curr.score, 0) / (utilizationChartData.length || 1)).toFixed(1)}%`, trend: '-0.5%', positive: false, icon: Clock },
  ];

  return (
    <div className="p-8 space-y-8 max-w-[1400px] mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-[#0F172A]">Company Analytics</h2>
        <p className="text-[#64748B]">Real-time insights and data visualizations for HR metrics.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat, idx) => (
          <Card key={idx} className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="p-2 bg-[#F1F5F9] rounded-lg">
                <stat.icon className="w-5 h-5 text-[#2563EB]" />
              </div>
              <Badge variant={stat.positive ? 'success' : 'error'} className="flex items-center">
                {stat.positive ? <ArrowUpRight className="w-3 h-3 mr-1" /> : <ArrowDownRight className="w-3 h-3 mr-1" />}
                {stat.trend}
              </Badge>
            </div>
            <h4 className="text-2xl font-black text-[#0F172A]">{stat.value}</h4>
            <p className="text-sm font-medium text-[#64748B] mt-1">{stat.label}</p>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <Card className="p-6">
          <h3 className="font-bold text-[#0F172A] mb-6 flex items-center">
            <BarChart3 className="w-5 h-5 mr-2 text-[#2563EB]" /> Team Attendance (Last 7 Days)
          </h3>
          <div className="h-72 w-full min-h-[300px] relative">
            <ResponsiveContainer width="100%" height="300">
              <BarChart data={attendanceChartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fontSize: 12, fill: '#94A3B8'}} />
                <YAxis axisLine={false} tickLine={false} tick={{fontSize: 12, fill: '#94A3B8'}} />
                <Tooltip />
                <Bar dataKey="present" fill="#2563EB" radius={[4, 4, 0, 0]} />
                <Bar dataKey="absent" fill="#EF4444" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-6">
          <h3 className="font-bold text-[#0F172A] mb-6 flex items-center">
            <Clock className="w-5 h-5 mr-2 text-[#2563EB]" /> Project Utilization Score
          </h3>
          <div className="h-72 w-full min-h-[300px] relative">
            <ResponsiveContainer width="100%" height="300">
              <BarChart data={utilizationChartData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#F1F5F9" />
                <XAxis type="number" hide />
                <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{fontSize: 12, fill: '#94A3B8'}} width={100} />
                <Tooltip />
                <Bar dataKey="score" fill="#10B981" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <Card className="p-6 lg:col-span-1">
          <h3 className="font-bold text-[#0F172A] mb-6 flex items-center">
            <PieChartIcon className="w-5 h-5 mr-2 text-[#2563EB]" /> Avg. Leave Balance by Dept.
          </h3>
          <div className="h-64 w-full min-h-[300px] relative">
            <ResponsiveContainer width="100%" height="300">
              <PieChart>
                <Pie
                  data={leaveChartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {leaveChartData.map((_entry: any, index: number) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 space-y-2">
            {leaveChartData.map((d: any, i: number) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <div className="flex items-center">
                  <div className="w-3 h-3 rounded-full mr-2" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                  <span className="text-[#64748B]">{d.name}</span>
                </div>
                <span className="font-bold text-[#0F172A]">{d.value.toFixed(1)} days</span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-6 lg:col-span-2">
          <h3 className="font-bold text-[#0F172A] mb-6 flex items-center">
            <AlertCircle className="w-5 h-5 mr-2 text-[#F59E0B]" /> Cost Variance Analysis
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-[#F1F5F9]">
                  <th className="pb-4 font-semibold text-[#0F172A]">Project</th>
                  <th className="pb-4 font-semibold text-[#0F172A]">Variance (%)</th>
                  <th className="pb-4 font-semibold text-[#0F172A]">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#F1F5F9]">
                {data?.reports?.cost_variance?.map((item: any, i: number) => (
                  <tr key={i}>
                    <td className="py-4 text-[#64748B]">{item.project_name}</td>
                    <td className="py-4 font-medium text-[#0F172A]">
                      {item.variance > 0 ? '+' : ''}{item.variance.toFixed(1)}%
                    </td>
                    <td className="py-4">
                      <Badge variant={item.variance > 10 ? 'error' : item.variance > 0 ? 'warning' : 'success'}>
                        {item.variance > 10 ? 'Critical' : item.variance > 0 ? 'Watching' : 'On Track'}
                      </Badge>
                    </td>
                  </tr>
                ))}
                {(!data?.reports?.cost_variance || data.reports.cost_variance.length === 0) && (
                  <tr>
                    <td colSpan={3} className="py-8 text-center text-gray-500 italic">No variance data available</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
};
