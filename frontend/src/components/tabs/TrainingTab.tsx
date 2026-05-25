import { Card } from '../ui/card';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Progress } from '../ui/progress';
import { BookOpen, Award, Play, CheckCircle2 } from 'lucide-react';

interface TrainingTabProps {
  courses: any[];
  skillsData: any[];
}

export function TrainingTab({ courses, skillsData }: TrainingTabProps) {
  const certificates = [
    { name: 'Advanced Figma Certification', issuer: 'Figma Academy', date: '2024-08-15' },
    { name: 'UX Research Professional', issuer: 'Nielsen Norman Group', date: '2024-03-10' },
    { name: 'Leadership Essentials', issuer: 'LinkedIn Learning', date: '2024-06-20' },
  ];

  const recommendations = [
    { name: 'Advanced CSS & Animation', provider: 'Frontend Masters', duration: '8 hours', match: 92 },
    { name: 'Strategic Product Design', provider: 'Interaction Design Foundation', duration: '12 hours', match: 88 },
    { name: 'Inclusive Design Principles', provider: 'Coursera', duration: '6 hours', match: 85 },
  ];

  return (
    <div className="space-y-6">
      {/* Training Stats */}
      <div className="grid grid-cols-3 gap-6">
        <Card className="border-l-4 border-l-blue-500">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <BookOpen className="w-5 h-5 text-blue-600" />
              </div>
              <div className="text-slate-600">Courses Completed</div>
            </div>
            <div className="text-slate-900">12 courses</div>
            <div className="text-slate-500 mt-1">This year</div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-green-500">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                <Award className="w-5 h-5 text-green-600" />
              </div>
              <div className="text-slate-600">Certificates Earned</div>
            </div>
            <div className="text-slate-900">3 certificates</div>
            <div className="text-slate-500 mt-1">Professional level</div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-purple-500">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
                <Play className="w-5 h-5 text-purple-600" />
              </div>
              <div className="text-slate-600">Learning Hours</div>
            </div>
            <div className="text-slate-900">48 hours</div>
            <div className="text-slate-500 mt-1">Total invested</div>
          </div>
        </Card>
      </div>

      {/* Current & Assigned Courses */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">Assigned & Active Courses</h3>
          
          <div className="space-y-4">
            {courses.map((course, index) => {
              const statusConfig = {
                completed: { color: 'bg-green-100 text-green-800 border-green-200', icon: CheckCircle2 },
                'in-progress': { color: 'bg-blue-100 text-blue-800 border-blue-200', icon: Play },
                assigned: { color: 'bg-slate-100 text-slate-800 border-slate-200', icon: BookOpen },
              };

              const config = statusConfig[course.status as keyof typeof statusConfig];
              const StatusIcon = config.icon;

              return (
                <div key={index} className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-start gap-3 flex-1">
                      <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-500 rounded-lg flex items-center justify-center flex-shrink-0">
                        <StatusIcon className="w-5 h-5 text-white" />
                      </div>
                      <div className="flex-1">
                        <div className="text-slate-900 mb-1">{course.name}</div>
                        {course.completedDate && (
                          <div className="text-slate-600">
                            Completed: {new Date(course.completedDate).toLocaleDateString()}
                          </div>
                        )}
                      </div>
                    </div>
                    <Badge variant="outline" className={config.color}>
                      {course.status.replace('-', ' ')}
                    </Badge>
                  </div>
                  
                  <div className="flex items-center gap-3">
                    <Progress value={course.progress} className="flex-1" />
                    <span className="text-slate-600 min-w-[3rem] text-right">{course.progress}%</span>
                  </div>
                  
                  {course.status !== 'completed' && (
                    <Button variant="link" className="mt-2 p-0 h-auto">
                      {course.status === 'assigned' ? 'Start Course' : 'Continue Learning'}
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </Card>

      {/* Certificates */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">Earned Certificates</h3>
          
          <div className="grid grid-cols-2 gap-4">
            {certificates.map((cert, index) => (
              <div key={index} className="bg-gradient-to-br from-blue-50 to-purple-50 border-2 border-blue-200 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-purple-500 rounded-lg flex items-center justify-center flex-shrink-0">
                    <Award className="w-6 h-6 text-white" />
                  </div>
                  <div className="flex-1">
                    <div className="text-slate-900 mb-1">{cert.name}</div>
                    <div className="text-slate-600">{cert.issuer}</div>
                    <div className="text-slate-500 mt-2">
                      {new Date(cert.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long' })}
                    </div>
                  </div>
                </div>
                <Button variant="link" className="mt-3 p-0 h-auto">
                  View Certificate →
                </Button>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* AI Recommendations */}
      <Card>
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-slate-900">Recommended Courses</h3>
            <Badge className="bg-purple-100 text-purple-800 border-purple-200" variant="outline">
              AI Powered
            </Badge>
          </div>
          
          <div className="space-y-3">
            {recommendations.map((rec, index) => (
              <div key={index} className="bg-slate-50 border border-slate-200 rounded-lg p-4 hover:border-blue-300 hover:shadow-sm transition-all cursor-pointer">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="text-slate-900 mb-1">{rec.name}</div>
                    <div className="text-slate-600">{rec.provider} · {rec.duration}</div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <Badge className="bg-green-100 text-green-800 border-green-200" variant="outline">
                      {rec.match}% match
                    </Badge>
                    <Button size="sm" variant="outline">Enroll</Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Skills Progress */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">Skills Proficiency</h3>
          
          <div className="space-y-4">
            {skillsData.map((skill, index) => (
              <div key={index}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-slate-900">{skill.skill}</span>
                  <span className="text-slate-600">{skill.proficiency}%</span>
                </div>
                <Progress value={skill.proficiency} />
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
