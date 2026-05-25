import { Mail, Phone, MapPin, Edit, MessageSquare, UserX, FileDown, MoreVertical, Star } from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Card } from './ui/card';
import { Avatar, AvatarFallback, AvatarImage } from './ui/avatar';
import { Employee } from '../types/employee';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';

interface EmployeeHeaderProps {
  employee: Employee;
}

export function EmployeeHeader({ employee }: EmployeeHeaderProps) {
  const statusColors = {
    active: 'bg-green-100 text-green-800 border-green-200',
    suspended: 'bg-red-100 text-red-800 border-red-200',
    'on-leave': 'bg-yellow-100 text-yellow-800 border-yellow-200',
    terminated: 'bg-gray-100 text-gray-800 border-gray-200',
  };

  return (
    <Card className="border-0 shadow-sm">
      <div className="p-6">
        <div className="flex items-start justify-between mb-6">
          {/* Profile Section */}
          <div className="flex gap-6">
            <Avatar className="w-24 h-24 border-4 border-white shadow-md">
              <AvatarImage src={employee.profileImage} alt={`${employee.firstName} ${employee.lastName}`} />
              <AvatarFallback className="bg-gradient-to-br from-blue-500 to-teal-500 text-white">
                {employee.firstName[0]}{employee.lastName[0]}
              </AvatarFallback>
            </Avatar>
            
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2">
                <h1 className="text-slate-900">{employee.firstName} {employee.lastName}</h1>
                <Badge className={statusColors[employee.employmentStatus]} variant="outline">
                  {employee.employmentStatus.charAt(0).toUpperCase() + employee.employmentStatus.slice(1)}
                </Badge>
              </div>
              
              <p className="text-slate-600 mb-3">{employee.jobTitle} · {employee.department}</p>
              
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-slate-600">
                <div className="flex items-center gap-2">
                  <Mail className="w-4 h-4" />
                  <span>{employee.email}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Phone className="w-4 h-4" />
                  <span>{employee.phone}</span>
                </div>
                <div className="flex items-center gap-2">
                  <MapPin className="w-4 h-4" />
                  <span>{employee.location}</span>
                </div>
              </div>
              
              <div className="mt-3 text-slate-500">
                Employee ID: <span className="text-slate-700">{employee.id}</span>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-2">
            <Button variant="outline" size="sm">
              <Edit className="w-4 h-4 mr-2" />
              Edit Profile
            </Button>
            <Button variant="outline" size="sm">
              <MessageSquare className="w-4 h-4 mr-2" />
              Message
            </Button>
            <Button variant="outline" size="sm">
              <FileDown className="w-4 h-4 mr-2" />
              Report
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm">
                  <MoreVertical className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem>
                  <UserX className="w-4 h-4 mr-2" />
                  Suspend Account
                </DropdownMenuItem>
                <DropdownMenuItem>Reset Password</DropdownMenuItem>
                <DropdownMenuItem>Archive Profile</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4 border border-blue-200">
            <div className="text-slate-600 mb-1">Monthly Salary</div>
            <div className="text-blue-900">₹{employee.salary.toLocaleString('en-IN')}</div>
          </div>
          
          <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-lg p-4 border border-green-200">
            <div className="text-slate-600 mb-1">Attendance Rate</div>
            <div className="text-green-900">{employee.attendanceRate}%</div>
          </div>
          
          <div className="bg-gradient-to-br from-amber-50 to-amber-100 rounded-lg p-4 border border-amber-200">
            <div className="text-slate-600 mb-1">Performance Rating</div>
            <div className="flex items-center gap-1 text-amber-900">
              <Star className="w-4 h-4 fill-amber-500 text-amber-500" />
              {employee.performanceRating}
            </div>
          </div>
          
          <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-lg p-4 border border-purple-200">
            <div className="text-slate-600 mb-1">Leave Balance</div>
            <div className="text-purple-900">{employee.leaveBalance} days</div>
          </div>
        </div>
      </div>
    </Card>
  );
}
