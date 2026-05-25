import { Card } from '../ui/card';
import { Badge } from '../ui/badge';
import { Calendar, Clock, TrendingUp } from 'lucide-react';
import { LeaveRequest } from '../../types/employee';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';

interface AttendanceTabProps {
  attendanceRate: number;
  leaveRequests: LeaveRequest[];
  attendanceData: any[];
}

export function AttendanceTab({ attendanceRate, leaveRequests, attendanceData }: AttendanceTabProps) {
  const statusColors = {
    approved: 'bg-green-100 text-green-800 border-green-200',
    pending: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    rejected: 'bg-red-100 text-red-800 border-red-200',
  };

  const leaveUsageData = [
    { name: 'Annual Leave', value: 12, color: '#3b82f6' },
    { name: 'Sick Leave', value: 4, color: '#ef4444' },
    { name: 'Personal Leave', value: 2, color: '#8b5cf6' },
    { name: 'Remaining', value: 8, color: '#e5e7eb' },
  ];

  // Calculate attendance stats
  const presentDays = attendanceData.filter(d => d.status === 'present').length;
  const lateDays = attendanceData.filter(d => d.status === 'late').length;
  const absentDays = attendanceData.filter(d => d.status === 'absent').length;

  return (
    <div className="space-y-6">
      {/* Stats Overview */}
      <div className="grid grid-cols-3 gap-6">
        <Card className="border-l-4 border-l-green-500">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-green-600" />
              </div>
              <div className="text-slate-600">Attendance Rate</div>
            </div>
            <div className="text-slate-900">{attendanceRate}%</div>
            <div className="text-slate-500 mt-1">This month</div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-blue-500">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <Calendar className="w-5 h-5 text-blue-600" />
              </div>
              <div className="text-slate-600">Present Days</div>
            </div>
            <div className="text-slate-900">{presentDays} days</div>
            <div className="text-slate-500 mt-1">October 2024</div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-amber-500">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                <Clock className="w-5 h-5 text-amber-600" />
              </div>
              <div className="text-slate-600">Late Arrivals</div>
            </div>
            <div className="text-slate-900">{lateDays} days</div>
            <div className="text-slate-500 mt-1">October 2024</div>
          </div>
        </Card>
      </div>

      {/* Attendance Calendar Heatmap */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">October 2024 Attendance</h3>
          
          <div className="grid grid-cols-7 gap-2">
            {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day) => (
              <div key={day} className="text-center text-slate-600 p-2">
                {day}
              </div>
            ))}
            
            {/* Days */}
            {Array.from({ length: 31 }, (_, i) => i + 1).map((day) => {
              const dateStr = `2024-10-${String(day).padStart(2, '0')}`;
              const attendance = attendanceData.find(d => d.date === dateStr);
              const isWeekend = new Date(dateStr).getDay() === 0 || new Date(dateStr).getDay() === 6;
              
              let bgColor = 'bg-slate-100';
              if (isWeekend) bgColor = 'bg-slate-50';
              else if (attendance?.status === 'present') bgColor = 'bg-green-100 border-green-300';
              else if (attendance?.status === 'late') bgColor = 'bg-amber-100 border-amber-300';
              else if (attendance?.status === 'absent') bgColor = 'bg-red-100 border-red-300';
              
              return (
                <div
                  key={day}
                  className={`aspect-square flex items-center justify-center rounded-lg border ${bgColor} text-slate-700 hover:shadow-sm transition-shadow cursor-pointer`}
                >
                  {day}
                </div>
              );
            })}
          </div>
          
          <div className="flex gap-6 mt-6 justify-center">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded bg-green-100 border border-green-300" />
              <span className="text-slate-600">Present</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded bg-amber-100 border border-amber-300" />
              <span className="text-slate-600">Late</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded bg-red-100 border border-red-300" />
              <span className="text-slate-600">Absent</span>
            </div>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-6">
        {/* Leave Usage Chart */}
        <Card>
          <div className="p-6">
            <h3 className="text-slate-900 mb-6">Leave Usage (2024)</h3>
            
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={leaveUsageData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {leaveUsageData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Leave Requests */}
        <Card>
          <div className="p-6">
            <h3 className="text-slate-900 mb-6">Recent Leave Requests</h3>
            
            <div className="space-y-3">
              {leaveRequests.map((leave) => (
                <div key={leave.id} className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                  <div className="flex items-start justify-between mb-2">
                    <div className="text-slate-900">{leave.type}</div>
                    <Badge variant="outline" className={statusColors[leave.status]}>
                      {leave.status.charAt(0).toUpperCase() + leave.status.slice(1)}
                    </Badge>
                  </div>
                  <div className="text-slate-600">
                    {new Date(leave.startDate).toLocaleDateString()} - {new Date(leave.endDate).toLocaleDateString()}
                  </div>
                  <div className="text-slate-500 mt-1">{leave.days} days</div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
