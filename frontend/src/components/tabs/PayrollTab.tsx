import { Card } from '../ui/card';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Download, DollarSign, TrendingUp, AlertCircle } from 'lucide-react';
import { PayrollRecord } from '../../types/employee';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';

interface PayrollTabProps {
  payrollHistory: PayrollRecord[];
  currentSalary: number;
}

export function PayrollTab({ payrollHistory, currentSalary }: PayrollTabProps) {
  const statusColors = {
    paid: 'bg-green-100 text-green-800 border-green-200',
    pending: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    processing: 'bg-blue-100 text-blue-800 border-blue-200',
  };

  const totalAllowances = payrollHistory.reduce((sum, record) => sum + record.allowances, 0);
  const totalDeductions = payrollHistory.reduce((sum, record) => sum + record.deductions, 0);

  return (
    <div className="space-y-6">
      {/* Salary Breakdown */}
      <div className="grid grid-cols-3 gap-6">
        <Card className="border-l-4 border-l-blue-500">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <DollarSign className="w-5 h-5 text-blue-600" />
              </div>
              <div className="text-slate-600">Base Salary</div>
            </div>
            <div className="text-slate-900">₹{currentSalary.toLocaleString('en-IN')}/month</div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-green-500">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-green-600" />
              </div>
              <div className="text-slate-600">Total Allowances</div>
            </div>
            <div className="text-slate-900">₹{totalAllowances.toLocaleString('en-IN')}</div>
            <div className="text-slate-500 mt-1">Last 5 months</div>
          </div>
        </Card>

        <Card className="border-l-4 border-l-red-500">
          <div className="p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center">
                <AlertCircle className="w-5 h-5 text-red-600" />
              </div>
              <div className="text-slate-600">Total Deductions</div>
            </div>
            <div className="text-slate-900">₹{totalDeductions.toLocaleString('en-IN')}</div>
            <div className="text-slate-500 mt-1">Last 5 months</div>
          </div>
        </Card>
      </div>

      {/* Payroll History */}
      <Card>
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-slate-900">Payroll History</h3>
            <Button variant="outline" size="sm">
              <Download className="w-4 h-4 mr-2" />
              Export All
            </Button>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Period</TableHead>
                <TableHead>Base Salary</TableHead>
                <TableHead>Allowances</TableHead>
                <TableHead>Deductions</TableHead>
                <TableHead>Net Pay</TableHead>
                <TableHead>Status</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {payrollHistory.map((record, index) => (
                <TableRow key={index}>
                  <TableCell>{record.month}</TableCell>
                  <TableCell>₹{record.base.toLocaleString('en-IN')}</TableCell>
                  <TableCell className="text-green-600">+₹{record.allowances.toLocaleString('en-IN')}</TableCell>
                  <TableCell className="text-red-600">-₹{record.deductions.toLocaleString('en-IN')}</TableCell>
                  <TableCell>₹{record.net.toLocaleString('en-IN')}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={statusColors[record.status]}>
                      {record.status.charAt(0).toUpperCase() + record.status.slice(1)}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm">
                      <Download className="w-4 h-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>

      {/* Payment Method */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-6">Payment Method</h3>
          
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-slate-900 mb-2">Bank Transfer</div>
                <div className="text-slate-600">Account: •••• •••• •••• 4892</div>
                <div className="text-slate-600">Bank: Chase Bank</div>
                <div className="text-slate-600">Routing: •••• 1234</div>
              </div>
              <Badge className="bg-green-100 text-green-800 border-green-200" variant="outline">Verified</Badge>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
