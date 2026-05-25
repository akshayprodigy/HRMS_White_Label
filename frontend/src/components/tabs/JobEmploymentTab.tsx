import { Card } from '../ui/card';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { Employee } from '../../types/employee';
import { Calendar, Briefcase, MapPin, Clock } from 'lucide-react';

interface JobEmploymentTabProps {
  employee: Employee;
}

export function JobEmploymentTab({ employee }: JobEmploymentTabProps) {
  const promotionHistory = [
    { date: '2024-01-15', from: 'Product Designer', to: 'Senior Product Designer', reason: 'Outstanding performance and leadership' },
    { date: '2022-06-01', from: 'Junior Designer', to: 'Product Designer', reason: 'Completed 18 months, strong portfolio' },
    { date: '2021-03-15', from: null, to: 'Junior Designer', reason: 'Initial hire' },
  ];

  return (
    <div className="space-y-6">
      {/* Current Position */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">Current Position</h3>
          
          <div className="grid grid-cols-2 gap-6">
            <div>
              <Label className="text-slate-600">Job Title</Label>
              <Input value={employee.jobTitle} readOnly className="mt-2" />
            </div>
            <div>
              <Label className="text-slate-600">Department</Label>
              <Input value={employee.department} readOnly className="mt-2" />
            </div>
            <div>
              <Label className="text-slate-600">Manager</Label>
              <Input value={employee.manager} readOnly className="mt-2" />
            </div>
            <div>
              <Label className="text-slate-600">Employment Type</Label>
              <Input value={employee.employmentType} readOnly className="mt-2" />
            </div>
          </div>
        </div>
      </Card>

      {/* Employment Details */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">Employment Details</h3>
          
          <div className="grid grid-cols-2 gap-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <Calendar className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <div className="text-slate-600">Hire Date</div>
                <div className="text-slate-900">{new Date(employee.hireDate).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}</div>
              </div>
            </div>
            
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                <Briefcase className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <div className="text-slate-600">Contract Term</div>
                <div className="text-slate-900">{employee.contractTerm}</div>
              </div>
            </div>
            
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
                <MapPin className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <div className="text-slate-600">Work Location</div>
                <div className="text-slate-900">{employee.workLocation}</div>
              </div>
            </div>
            
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                <Clock className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <div className="text-slate-600">Shift</div>
                <div className="text-slate-900">{employee.shift}</div>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Promotion History */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">Career Timeline</h3>
          
          <div className="relative">
            {/* Timeline line */}
            <div className="absolute left-4 top-4 bottom-4 w-0.5 bg-slate-200" />
            
            <div className="space-y-6">
              {promotionHistory.map((promo, index) => (
                <div key={index} className="relative pl-12">
                  <div className="absolute left-0 w-8 h-8 bg-blue-500 rounded-full border-4 border-white shadow-md flex items-center justify-center">
                    <div className="w-2 h-2 bg-white rounded-full" />
                  </div>
                  
                  <div className="bg-slate-50 rounded-lg p-4 border border-slate-200">
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        {promo.from ? (
                          <div>
                            <span className="text-slate-500 line-through">{promo.from}</span>
                            <span className="text-slate-400 mx-2">→</span>
                            <span className="text-slate-900">{promo.to}</span>
                          </div>
                        ) : (
                          <div className="text-slate-900">{promo.to}</div>
                        )}
                      </div>
                      <Badge variant="outline" className="bg-white">
                        {new Date(promo.date).toLocaleDateString('en-US', { year: 'numeric', month: 'short' })}
                      </Badge>
                    </div>
                    <p className="text-slate-600">{promo.reason}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
