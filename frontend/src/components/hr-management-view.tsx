import React, { useState } from 'react';
import { 
  Users, 
  Plus, 
  Search, 
  Filter, 
  DollarSign, 
  FileText, 
  Download, 
  ChevronRight, 
  Trash2, 
  Edit,
  ArrowUpRight,
  TrendingUp,
  UserPlus
} from 'lucide-react';
import { Card, Button, Badge, Input, cn } from './ui-elements';

const mockEmployees = [
  { id: 'E001', name: 'Sarah Johnson', role: 'Project Manager', dept: 'Operations', status: 'active', salary: 125000 },
  { id: 'E002', name: 'Alex Thompson', role: 'Sr. Developer', dept: 'Engineering', status: 'active', salary: 95000 },
  { id: 'E003', name: 'Emily Davis', role: 'UI/UX Lead', dept: 'Design', status: 'on-leave', salary: 85000 },
  { id: 'E004', name: 'Michael Ross', role: 'Backend Developer', dept: 'Engineering', status: 'active', salary: 90000 },
];

export const HRManagementView = () => {
  const [view, setView] = useState<'directory' | 'payroll'>('directory');

  return (
    <div className="p-8 space-y-8 max-w-[1400px] mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-[#0F172A]">HR & Payroll</h2>
          <p className="text-[#64748B]">Manage employee lifecycle, records, and monthly payroll processing.</p>
        </div>
        <div className="flex bg-[#F1F5F9] p-1 rounded-xl">
          <button 
            onClick={() => setView('directory')}
            className={cn("px-4 py-2 text-sm font-bold rounded-lg transition-all", view === 'directory' ? "bg-white shadow-sm text-blue-600" : "text-[#64748B]")}
          >
            Directory
          </button>
          <button 
            onClick={() => setView('payroll')}
            className={cn("px-4 py-2 text-sm font-bold rounded-lg transition-all", view === 'payroll' ? "bg-white shadow-sm text-blue-600" : "text-[#64748B]")}
          >
            Payroll
          </button>
        </div>
      </div>

      {view === 'directory' && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            {[
              { label: 'Total Headcount', value: '148', color: 'text-blue-600', bg: 'bg-blue-50' },
              { label: 'New This Month', value: '12', color: 'text-green-600', bg: 'bg-green-50' },
              { label: 'On Leave Today', value: '08', color: 'text-orange-600', bg: 'bg-orange-50' },
              { label: 'Pending Docs', value: '05', color: 'text-red-600', bg: 'bg-red-50' },
            ].map((stat, i) => (
              <Card key={i} className="p-6">
                <p className="text-xs font-bold text-[#64748B] uppercase mb-2">{stat.label}</p>
                <div className="flex items-center justify-between">
                  <h4 className="text-2xl font-black text-[#0F172A]">{stat.value}</h4>
                  <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center", stat.bg)}>
                    <Users size={16} className={stat.color} />
                  </div>
                </div>
              </Card>
            ))}
          </div>

          <Card className="overflow-hidden">
            <div className="p-4 border-b border-[#E5E7EB] flex flex-wrap items-center gap-4 justify-between">
              <div className="relative flex-1 min-w-[300px]">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748B]" />
                <input 
                  type="text" 
                  placeholder="Search by name, ID or department..." 
                  className="w-full pl-10 pr-4 py-2 border border-[#E5E7EB] rounded-lg text-sm bg-[#F9FAFB]"
                />
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm"><Filter size={16} className="mr-2" /> Filter</Button>
                <Button className="flex items-center">
                  <UserPlus size={16} className="mr-2" /> Add Employee
                </Button>
              </div>
            </div>
            
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-[#F9FAFB] border-b border-[#E5E7EB]">
                  <th className="px-6 py-4 text-xs font-bold text-[#374151] uppercase">Employee</th>
                  <th className="px-6 py-4 text-xs font-bold text-[#374151] uppercase">Department</th>
                  <th className="px-6 py-4 text-xs font-bold text-[#374151] uppercase">Role</th>
                  <th className="px-6 py-4 text-xs font-bold text-[#374151] uppercase">Status</th>
                  <th className="px-6 py-4 text-xs font-bold text-[#374151] uppercase text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E5E7EB]">
                {mockEmployees.map((emp) => (
                  <tr key={emp.id} className="hover:bg-[#F9FAFB] transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-slate-100 border border-slate-200" />
                        <div>
                          <p className="text-sm font-bold text-[#0F172A]">{emp.name}</p>
                          <p className="text-xs text-[#64748B]">{emp.id}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-[#334155]">{emp.dept}</td>
                    <td className="px-6 py-4 text-sm text-[#334155]">{emp.role}</td>
                    <td className="px-6 py-4">
                      <Badge variant={emp.status === 'active' ? 'success' : 'warning'}>
                        {emp.status.toUpperCase()}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button className="p-2 text-[#64748B] hover:text-blue-600 transition-colors"><Edit size={16} /></button>
                        <button className="p-2 text-[#64748B] hover:text-red-600 transition-colors"><Trash2 size={16} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}

      {view === 'payroll' && (
        <PayrollView />
      )}
    </div>
  );
};

const PayrollView = () => {
  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <Card className="lg:col-span-2 p-8">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-lg font-bold text-[#0F172A]">Run Payroll - February 2026</h3>
            <div className="flex gap-3">
              <Button variant="outline"><Download size={16} className="mr-2" /> Download Draft</Button>
              <Button>Process All</Button>
            </div>
          </div>

          <div className="space-y-6">
            <div className="p-6 bg-blue-50 border border-blue-100 rounded-2xl flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-blue-600 text-white rounded-xl">
                  <DollarSign size={24} />
                </div>
                <div>
                  <p className="text-sm font-bold text-blue-900">Total Monthly Disbursement</p>
                  <p className="text-3xl font-black text-blue-900">₹845,200.00</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs font-bold text-blue-600 uppercase tracking-widest">Status</p>
                <p className="text-sm font-black text-blue-900">AWAITING APPROVAL</p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-6">
              {[
                { label: 'Basic Salary', value: '₹650,000' },
                { label: 'Allowances', value: '₹125,000' },
                { label: 'Deductions', value: '-₹24,000' },
              ].map((item, i) => (
                <div key={i} className="p-4 bg-slate-50 border border-slate-100 rounded-xl">
                  <p className="text-xs text-[#64748B] font-bold uppercase mb-1">{item.label}</p>
                  <p className="text-lg font-black text-[#0F172A]">{item.value}</p>
                </div>
              ))}
            </div>

            <div className="space-y-4">
              <h4 className="text-xs font-bold text-[#94A3B8] uppercase tracking-wider">Exception Alerts</h4>
              {[
                { emp: 'Emily Davis', reason: 'Unpaid Leave (4 days)', amount: '-₹1,250' },
                { emp: 'Michael Ross', reason: 'Performance Bonus', amount: '+₹500' },
              ].map((ex, i) => (
                <div key={i} className="flex items-center justify-between p-4 border border-slate-100 rounded-xl">
                  <div>
                    <p className="text-sm font-bold text-[#0F172A]">{ex.emp}</p>
                    <p className="text-xs text-[#64748B]">{ex.reason}</p>
                  </div>
                  <span className={cn("text-sm font-bold", ex.amount.startsWith('-') ? "text-red-600" : "text-green-600")}>
                    {ex.amount}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <div className="space-y-8">
          <Card className="p-6">
            <h3 className="text-sm font-bold text-[#0F172A] mb-4">Payroll Calendar</h3>
            <div className="space-y-6">
              <div className="flex items-center gap-4">
                <div className="w-2 h-10 rounded-full bg-blue-600" />
                <div>
                  <p className="text-xs text-[#64748B]">Process Start</p>
                  <p className="text-sm font-bold text-[#0F172A]">Feb 20, 2026</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="w-2 h-10 rounded-full bg-purple-600" />
                <div>
                  <p className="text-xs text-[#64748B]">Bank Disbursement</p>
                  <p className="text-sm font-bold text-[#0F172A]">Feb 28, 2026</p>
                </div>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <h3 className="text-sm font-bold text-[#0F172A] mb-4">Salary Slips</h3>
            <div className="space-y-4">
              <div className="p-4 bg-slate-50 rounded-xl border border-slate-100 flex items-center justify-between group cursor-pointer hover:border-blue-200 transition-all">
                <div className="flex items-center gap-3">
                  <FileText size={18} className="text-[#64748B]" />
                  <span className="text-sm font-bold text-[#334155]">Jan 2026 Slips</span>
                </div>
                <Download size={16} className="text-[#94A3B8] group-hover:text-blue-600" />
              </div>
              <div className="p-4 bg-slate-50 rounded-xl border border-slate-100 flex items-center justify-between group cursor-pointer hover:border-blue-200 transition-all">
                <div className="flex items-center gap-3">
                  <FileText size={18} className="text-[#64748B]" />
                  <span className="text-sm font-bold text-[#334155]">Dec 2025 Slips</span>
                </div>
                <Download size={16} className="text-[#94A3B8] group-hover:text-blue-600" />
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
