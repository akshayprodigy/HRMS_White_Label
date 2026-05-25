import { Card } from '../ui/card';
import { Badge } from '../ui/badge';
import { Progress } from '../ui/progress';
import { Star, Target, TrendingUp } from 'lucide-react';
import { PerformanceReview } from '../../types/employee';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from 'recharts';

interface PerformanceTabProps {
  reviews: PerformanceReview[];
  performanceTrend: any[];
  skillsData: any[];
}

export function PerformanceTab({ reviews, performanceTrend, skillsData }: PerformanceTabProps) {
  const goals = [
    { name: 'Complete Design System V2', progress: 85, status: 'on-track' },
    { name: 'Lead UX Research Initiative', progress: 60, status: 'on-track' },
    { name: 'Mentor 2 Junior Designers', progress: 100, status: 'completed' },
    { name: 'Improve Accessibility Score', progress: 45, status: 'at-risk' },
  ];

  const statusColors = {
    'on-track': 'bg-green-100 text-green-800 border-green-200',
    'at-risk': 'bg-red-100 text-red-800 border-red-200',
    'completed': 'bg-blue-100 text-blue-800 border-blue-200',
  };

  return (
    <div className="space-y-6">
      {/* Performance Overview */}
      <div className="grid grid-cols-3 gap-6">
        <Card className="border-l-4 border-l-amber-500">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                <Star className="w-5 h-5 text-amber-600" />
              </div>
              <div className="text-slate-600">Current Rating</div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-slate-900">4.6</span>
              <div className="flex">
                {[1, 2, 3, 4, 5].map((star) => (
                  <Star
                    key={star}
                    className={`w-4 h-4 ${star <= 4.6 ? 'fill-amber-500 text-amber-500' : 'text-slate-300'}`}
                  />
                ))}
              </div>
            </div>
            <div className="text-slate-500 mt-1">Q3 2024</div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-green-500">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                <Target className="w-5 h-5 text-green-600" />
              </div>
              <div className="text-slate-600">Goals Completed</div>
            </div>
            <div className="text-slate-900">3 of 4</div>
            <div className="text-slate-500 mt-1">This quarter</div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-blue-500">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-blue-600" />
              </div>
              <div className="text-slate-600">Rating Trend</div>
            </div>
            <div className="text-slate-900">+0.3</div>
            <div className="text-slate-500 mt-1">vs. last quarter</div>
          </div>
        </Card>
      </div>

      {/* Performance Trend */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">Performance Trend</h3>
          
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={performanceTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="quarter" stroke="#64748b" />
              <YAxis domain={[0, 5]} stroke="#64748b" />
              <Tooltip />
              <Line type="monotone" dataKey="rating" stroke="#3b82f6" strokeWidth={3} dot={{ fill: '#3b82f6', r: 6 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-6">
        {/* Skills Assessment */}
        <Card>
          <div className="p-6">
            <h3 className="text-slate-900 mb-6">Skills Assessment</h3>
            
            <ResponsiveContainer width="100%" height={300}>
              <RadarChart data={skillsData}>
                <PolarGrid stroke="#e5e7eb" />
                <PolarAngleAxis dataKey="skill" stroke="#64748b" />
                <PolarRadiusAxis domain={[0, 100]} stroke="#64748b" />
                <Radar name="Proficiency" dataKey="proficiency" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.6} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Goals & KPIs */}
        <Card>
          <div className="p-6">
            <h3 className="text-slate-900 mb-6">Current Goals & KPIs</h3>
            
            <div className="space-y-4">
              {goals.map((goal, index) => (
                <div key={index} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-900">{goal.name}</span>
                    <Badge variant="outline" className={statusColors[goal.status]}>
                      {goal.status.replace('-', ' ')}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3">
                    <Progress value={goal.progress} className="flex-1" />
                    <span className="text-slate-600 min-w-[3rem] text-right">{goal.progress}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      {/* Performance Reviews */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">Recent Performance Reviews</h3>
          
          <div className="space-y-4">
            {reviews.map((review, index) => (
              <div key={index} className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="text-slate-900 mb-1">{review.quarter}</div>
                    <div className="text-slate-600">Reviewed by: {review.reviewer}</div>
                  </div>
                  <div className="flex items-center gap-1">
                    <Star className="w-5 h-5 fill-amber-500 text-amber-500" />
                    <span className="text-slate-900">{review.rating}</span>
                  </div>
                </div>
                <p className="text-slate-700">{review.feedback}</p>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
