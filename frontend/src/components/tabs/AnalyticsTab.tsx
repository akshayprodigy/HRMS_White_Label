import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { Download, TrendingUp, TrendingDown } from 'lucide-react';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface AnalyticsTabProps {
  salaryGrowth: any[];
  performanceTrend: any[];
}

export function AnalyticsTab({ salaryGrowth, performanceTrend }: AnalyticsTabProps) {
  const leaveTypeData = [
    { name: 'Annual', value: 12, color: '#3b82f6' },
    { name: 'Sick', value: 4, color: '#ef4444' },
    { name: 'Personal', value: 2, color: '#8b5cf6' },
    { name: 'Other', value: 1, color: '#f59e0b' },
  ];

  const attendanceTrendData = [
    { month: 'Apr', rate: 94 },
    { month: 'May', rate: 96 },
    { month: 'Jun', rate: 95 },
    { month: 'Jul', rate: 97 },
    { month: 'Aug', rate: 96 },
    { month: 'Sep', rate: 98 },
    { month: 'Oct', rate: 96 },
  ];

  const employeeHealthScore = 87; // Out of 100

  return (
    <div className="space-y-6">
      {/* Key Metrics */}
      <div className="grid grid-cols-4 gap-6">
        <Card className="border-l-4 border-l-green-500">
          <div className="p-6">
            <div className="text-slate-600 mb-2">Employee Health Score</div>
            <div className="flex items-center gap-2">
              <span className="text-slate-900">{employeeHealthScore}/100</span>
              <TrendingUp className="w-4 h-4 text-green-600" />
            </div>
            <div className="text-slate-500 mt-1">Excellent</div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-blue-500">
          <div className="p-6">
            <div className="text-slate-600 mb-2">Productivity Index</div>
            <div className="flex items-center gap-2">
              <span className="text-slate-900">92%</span>
              <TrendingUp className="w-4 h-4 text-blue-600" />
            </div>
            <div className="text-slate-500 mt-1">+3% from last month</div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-purple-500">
          <div className="p-6">
            <div className="text-slate-600 mb-2">Engagement Score</div>
            <div className="flex items-center gap-2">
              <span className="text-slate-900">4.2/5</span>
              <TrendingDown className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-slate-500 mt-1">-0.1 from last quarter</div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-amber-500">
          <div className="p-6">
            <div className="text-slate-600 mb-2">Retention Risk</div>
            <div className="flex items-center gap-2">
              <span className="text-slate-900">Low</span>
              <div className="w-2 h-2 bg-green-500 rounded-full"></div>
            </div>
            <div className="text-slate-500 mt-1">High performer</div>
          </div>
        </Card>
      </div>

      {/* Salary Growth */}
      <Card>
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-slate-900">Salary Growth Over Time</h3>
            <Button variant="outline" size="sm">
              <Download className="w-4 h-4 mr-2" />
              Export
            </Button>
          </div>
          
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={salaryGrowth}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="year" stroke="#64748b" />
              <YAxis stroke="#64748b" />
              <Tooltip />
              <Bar dataKey="salary" fill="#3b82f6" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Performance & Attendance */}
      <div className="grid grid-cols-2 gap-6">
        <Card>
          <div className="p-6">
            <h3 className="text-slate-900 mb-6">Performance Rating Trend</h3>
            
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={performanceTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="quarter" stroke="#64748b" />
                <YAxis domain={[0, 5]} stroke="#64748b" />
                <Tooltip />
                <Line type="monotone" dataKey="rating" stroke="#8b5cf6" strokeWidth={3} dot={{ fill: '#8b5cf6', r: 6 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <div className="p-6">
            <h3 className="text-slate-900 mb-6">Attendance Trend (Last 7 Months)</h3>
            
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={attendanceTrendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="month" stroke="#64748b" />
                <YAxis domain={[90, 100]} stroke="#64748b" />
                <Tooltip />
                <Line type="monotone" dataKey="rate" stroke="#10b981" strokeWidth={3} dot={{ fill: '#10b981', r: 6 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Leave Distribution */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">Leave Distribution by Type</h3>
          
          <div className="grid grid-cols-2 gap-6">
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={leaveTypeData}
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  dataKey="value"
                  label
                >
                  {leaveTypeData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            
            <div className="flex flex-col justify-center space-y-3">
              {leaveTypeData.map((item, index) => (
                <div key={index} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 rounded" style={{ backgroundColor: item.color }}></div>
                    <span className="text-slate-900">{item.name} Leave</span>
                  </div>
                  <span className="text-slate-600">{item.value} days</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* Insights & Recommendations */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">AI-Generated Insights</h3>
          
          <div className="space-y-3">
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <TrendingUp className="w-5 h-5 text-green-600 mt-0.5" />
                <div>
                  <div className="text-green-900 mb-1">Strong Performance Trajectory</div>
                  <p className="text-green-700">
                    Sarah has shown consistent performance improvement over the last 4 quarters. Consider for leadership development programs.
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <TrendingUp className="w-5 h-5 text-blue-600 mt-0.5" />
                <div>
                  <div className="text-blue-900 mb-1">High Engagement & Reliability</div>
                  <p className="text-blue-700">
                    Attendance rate of 96% and minimal leave usage indicates strong commitment and engagement.
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <TrendingUp className="w-5 h-5 text-purple-600 mt-0.5" />
                <div>
                  <div className="text-purple-900 mb-1">Career Growth Opportunity</div>
                  <p className="text-purple-700">
                    Based on skills assessment and performance, Sarah is ready for senior leadership roles or cross-functional projects.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Export Options */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-4">Export Reports</h3>
          
          <div className="flex gap-3">
            <Button variant="outline">
              <Download className="w-4 h-4 mr-2" />
              Full Profile Report (PDF)
            </Button>
            <Button variant="outline">
              <Download className="w-4 h-4 mr-2" />
              Analytics Data (CSV)
            </Button>
            <Button variant="outline">
              <Download className="w-4 h-4 mr-2" />
              Performance Summary
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
