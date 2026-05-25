import { Card } from '../ui/card';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Edit } from 'lucide-react';
import { Employee } from '../../types/employee';

interface PersonalInfoTabProps {
  employee: Employee;
}

export function PersonalInfoTab({ employee }: PersonalInfoTabProps) {
  return (
    <div className="space-y-6">
      {/* Personal Details */}
      <Card>
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-slate-900">Personal Details</h3>
            <Button variant="ghost" size="sm">
              <Edit className="w-4 h-4 mr-2" />
              Edit
            </Button>
          </div>
          
          <div className="grid grid-cols-2 gap-6">
            <div>
              <Label className="text-slate-600">First Name</Label>
              <Input value={employee.firstName} readOnly className="mt-2" />
            </div>
            <div>
              <Label className="text-slate-600">Last Name</Label>
              <Input value={employee.lastName} readOnly className="mt-2" />
            </div>
            <div>
              <Label className="text-slate-600">Date of Birth</Label>
              <Input value={employee.dateOfBirth} readOnly className="mt-2" />
            </div>
            <div>
              <Label className="text-slate-600">Gender</Label>
              <Input value={employee.gender} readOnly className="mt-2" />
            </div>
            <div>
              <Label className="text-slate-600">Marital Status</Label>
              <Input value={employee.maritalStatus} readOnly className="mt-2" />
            </div>
            <div>
              <Label className="text-slate-600">Employee ID</Label>
              <Input value={employee.id} readOnly className="mt-2" />
            </div>
            <div className="col-span-2">
              <Label className="text-slate-600">Address</Label>
              <Input value={employee.address} readOnly className="mt-2" />
            </div>
          </div>
        </div>
      </Card>

      {/* Contact Information */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">Contact Information</h3>
          
          <div className="grid grid-cols-2 gap-6">
            <div>
              <Label className="text-slate-600">Email Address</Label>
              <Input value={employee.email} readOnly className="mt-2" />
            </div>
            <div>
              <Label className="text-slate-600">Phone Number</Label>
              <Input value={employee.phone} readOnly className="mt-2" />
            </div>
            <div>
              <Label className="text-slate-600">Location</Label>
              <Input value={employee.location} readOnly className="mt-2" />
            </div>
          </div>
        </div>
      </Card>

      {/* Emergency Contact */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">Emergency Contact</h3>
          
          <div className="grid grid-cols-2 gap-6">
            <div>
              <Label className="text-slate-600">Contact Name</Label>
              <Input value={employee.emergencyContact.name} readOnly className="mt-2" />
            </div>
            <div>
              <Label className="text-slate-600">Relationship</Label>
              <Input value={employee.emergencyContact.relationship} readOnly className="mt-2" />
            </div>
            <div>
              <Label className="text-slate-600">Phone Number</Label>
              <Input value={employee.emergencyContact.phone} readOnly className="mt-2" />
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
