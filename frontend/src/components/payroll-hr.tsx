import React, { useState, useEffect } from 'react';
import { 
  CreditCard, 
  Banknote, 
  FileCheck, 
  Calculator, 
  CheckCircle2, 
  Clock, 
  ArrowRight, 
  Plus, 
  Download, 
  Eye, 
  Mail, 
  ChevronRight,
  TrendingDown,
  TrendingUp,
  AlertCircle,
  Lock,
  ArrowLeft,
  Loader2
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { PayrollRun, PayrollLine, SalaryDisbursementRecord } from '../types/erp';

export const PayrollHR = () => {
  const [view, setView] = useState<'dashboard' | 'run' | 'payslips'>('dashboard');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [disburseModal, setDisburseModal] = useState<{ line: PayrollLine } | null>(null);
  const [disbursements, setDisbursements] = useState<SalaryDisbursementRecord[]>([]);
  const [confirmAction, setConfirmAction] = useState<'finalize' | 'publish' | null>(null);
  const [dashboardData, setDashboardData] = useState<{
    active_runs: PayrollRun[];
    last_finalized_run: PayrollRun | null;
    total_processed_ytd: number;
  } | null>(null);
  
  const [currentRun, setCurrentRun] = useState<PayrollRun | null>(null);
  const [runLines, setRunLines] = useState<PayrollLine[]>([]);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [editingLineId, setEditingLineId] = useState<number | null>(null);
  const [lineEditValues, setLineEditValues] = useState<{ arrear: string; incentive: string }>({ arrear: '0', incentive: '0' });
  const [savingLineId, setSavingLineId] = useState<number | null>(null);
  const [expandedLineId, setExpandedLineId] = useState<number | null>(null);

  const [exporting, setExporting] = useState(false);

  const exportSalaryRegister = async () => {
    if (!currentRun) return;
    setExporting(true);
    try {
      const res = await client.post(
        `${ENDPOINTS.REPORTS_ENGINE.RUN('salary_register')}?format=xlsx`,
        { payroll_run_id: currentRun.id },
        { responseType: 'blob' }
      );
      const url = URL.createObjectURL(new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `SalaryRegister_${currentRun.year}_${String(currentRun.month).padStart(2, '0')}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Salary register exported');
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Failed to export salary register'));
    } finally {
      setExporting(false);
    }
  };

  const saveLineEdit = async (line: PayrollLine) => {
    if (!currentRun) return;
    setSavingLineId(line.id);
    try {
      const res = await client.patch(ENDPOINTS.HR.PAYROLL.LINE_UPDATE(currentRun.id, line.id), {
        arrear: parseFloat(lineEditValues.arrear) || 0,
        incentive: parseFloat(lineEditValues.incentive) || 0,
      });
      setRunLines(prev => prev.map(l => l.id === line.id ? { ...l, ...res.data } : l));
      setEditingLineId(null);
      toast.success('Line updated');
    } catch {
      toast.error('Failed to update line');
    } finally {
      setSavingLineId(null);
    }
  };

  const [attendanceCheck, setAttendanceCheck] = useState<{
    period: string;
    total_active_employees: number;
    with_attendance: number;
    missing_attendance: number;
    missing: { employee_id: string; name: string; email: string }[];
  } | null>(null);
  const [attDetailRows, setAttDetailRows] = useState<{
    employee_id: string;
    name: string;
    email: string;
    days_present: number;
    total_working_days: number;
  }[]>([]);
  const [loadingAttCheck, setLoadingAttCheck] = useState(false);

  useEffect(() => {
    fetchDashboard();
  }, []);

  useEffect(() => {
    const shouldFetchLines =
      view === 'run' &&
      !!currentRun &&
      ['draft_generated', 'finalized', 'published'].includes(currentRun.status) &&
      runLines.length === 0;

    if (!shouldFetchLines) return;

    (async () => {
      try {
        const linesResponse = await client.get(
          ENDPOINTS.HR.PAYROLL.LINES(currentRun.id)
        );
        setRunLines(linesResponse.data);
      } catch (error: any) {
        toast.error(getErrorMessage(error, 'Failed to fetch payroll lines'));
      }
    })();
  }, [view, currentRun, runLines.length]);

  const getErrorMessage = (error: any, fallback: string) => {
    return (
      error?.response?.data?.error?.message ||
      error?.response?.data?.detail ||
      error?.message ||
      fallback
    );
  };

  const fetchDashboard = async () => {
    setLoading(true);
    try {
      const response = await client.get(ENDPOINTS.HR.PAYROLL.DASHBOARD);
      setDashboardData(response.data);
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Failed to fetch payroll dashboard'));
    } finally {
      setLoading(false);
    }
  };

  const startNewRun = async () => {
    setActionLoading(true);
    try {
      const response = await client.post(ENDPOINTS.HR.PAYROLL.CREATE_RUN, {
        month: selectedMonth,
        year: selectedYear
      });
      setCurrentRun(response.data);
      setRunLines([]);
      setAttendanceCheck(null);
      setAttDetailRows([]);
      setView('run');
      toast.success(`Payroll run for ${selectedMonth}/${selectedYear} initiated`);
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Failed to start payroll run'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleStatusTransition = async (action: 'lock-attendance' | 'lock-leaves' | 'generate-draft' | 'finalize' | 'publish') => {
    if (!currentRun) return;
    setActionLoading(true);
    try {
      let endpoint = '';
      switch (action) {
        case 'lock-attendance': endpoint = ENDPOINTS.HR.PAYROLL.LOCK_ATTENDANCE(currentRun.id); break;
        case 'lock-leaves': endpoint = ENDPOINTS.HR.PAYROLL.LOCK_LEAVES(currentRun.id); break;
        case 'generate-draft': endpoint = ENDPOINTS.HR.PAYROLL.GENERATE_DRAFT(currentRun.id); break;
        case 'finalize': endpoint = ENDPOINTS.HR.PAYROLL.FINALIZE(currentRun.id); break;
        case 'publish': endpoint = ENDPOINTS.HR.PAYROLL.PUBLISH(currentRun.id); break;
      }
      
      const response = await client.post(endpoint);
      setCurrentRun(response.data.run);
      toast.success(response.data.message);
      
      if (action === 'generate-draft') {
        const linesResponse = await client.get(ENDPOINTS.HR.PAYROLL.LINES(currentRun.id));
        setRunLines(linesResponse.data);
      }
      
      if (action === 'publish') {
         setView('dashboard');
         fetchDashboard();
      }
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Operation failed'));
    } finally {
      setActionLoading(false);
    }
  };

  const getStep = (status: string) => {
    switch (status) {
      case 'draft':
      case 'DRAFT':
        return 1;
      case 'attendance_locked':
      case 'ATTENDANCE_LOCKED':
        return 2;
      case 'leaves_locked':
      case 'LEAVES_LOCKED':
        return 3;
      case 'draft_generated':
      case 'DRAFT_GENERATED':
        return 4;
      case 'finalized':
      case 'FINALIZED':
        return 5;
      case 'published':
      case 'PUBLISHED':
        return 6;
      default: return 1;
    }
  };

  const currentStep = currentRun ? getStep(currentRun.status) : 1;

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (view === 'run' && currentRun) {
    return (
      <div className="p-8 max-w-[1200px] mx-auto animate-in slide-in-from-bottom duration-500">
        <div className="flex items-center gap-4 mb-10">
          <button onClick={() => setView('dashboard')} className="p-3 bg-white border border-slate-200 rounded-2xl hover:bg-slate-50 transition-colors">
            <ArrowLeft size={20} className="text-slate-600" />
          </button>
          <div>
            <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter">Payroll Run: {currentRun.month}/{currentRun.year}</h2>
            <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Status: {currentRun.status.replace('_', ' ')}</p>
          </div>
        </div>

        {/* Step Indicator */}
        <div className="flex items-center justify-between mb-12 px-4 relative">
          <div className="absolute top-1/2 left-0 w-full h-1 bg-slate-100 -translate-y-1/2 -z-10 rounded-full overflow-hidden">
             <div className="h-full bg-blue-600 transition-all duration-700" style={{ width: `${(currentStep - 1) * 25}%` }} />
          </div>
          {[1, 2, 3, 4, 5].map((step) => (
            <div key={step} className="flex flex-col items-center gap-3">
              <div className={cn(
                "w-12 h-12 rounded-2xl flex items-center justify-center font-black transition-all duration-500 border-4",
                currentStep === step ? "bg-blue-600 text-white border-blue-100 shadow-xl shadow-blue-600/20 scale-110" : 
                currentStep > step ? "bg-green-500 text-white border-green-100" : "bg-white text-slate-300 border-slate-50 shadow-sm"
              )}>
                {currentStep > step ? <CheckCircle2 size={20} /> : step}
              </div>
              <span className={cn("text-[10px] font-black uppercase tracking-widest", currentStep === step ? "text-blue-600" : "text-slate-400")}>
                {step === 1 ? 'Initialized' : step === 2 ? 'Attendance' : step === 3 ? 'Leaves' : step === 4 ? 'Draft' : 'Finalize'}
              </span>
            </div>
          ))}
        </div>

        <Card className="p-10 border-slate-200 shadow-2xl shadow-slate-200/50">
           {currentStep === 1 && (
              <div className="space-y-8">
                {/* Header row */}
                <div className="flex items-start justify-between gap-6">
                  <div>
                    <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest mb-1">Step 1 of 5</p>
                    <h3 className="text-2xl font-black text-[#0F172A] tracking-tight">Attendance Coverage Check</h3>
                    <p className="text-slate-500 font-bold text-sm mt-1.5">Verify all active employees have attendance marked for <span className="text-[#0F172A] font-black">{currentRun.month}/{currentRun.year}</span> before locking the period.</p>
                  </div>
                  <Button
                    variant="outline"
                    onClick={async () => {
                      if (!currentRun) return;
                      setLoadingAttCheck(true);
                      try {
                        // Compute date range for the payroll month
                        const pad = (n: number) => String(n).padStart(2, '0');
                        const daysInMonth = new Date(currentRun.year, currentRun.month, 0).getDate();
                        const dateFrom = `${currentRun.year}-${pad(currentRun.month)}-01`;
                        const dateTo   = `${currentRun.year}-${pad(currentRun.month)}-${pad(daysInMonth)}`;

                        // Working days (Mon–Sat) in the period
                        let workingDays = 0;
                        for (let d = 1; d <= daysInMonth; d++) {
                          const day = new Date(currentRun.year, currentRun.month - 1, d).getDay();
                          if (day !== 0) workingDays++; // exclude Sunday
                        }

                        const [checkRes, logsRes] = await Promise.all([
                          client.get(ENDPOINTS.HR.PAYROLL.ATTENDANCE_CHECK(currentRun.id)),
                          client.get(ENDPOINTS.ATTENDANCE.ALL, { params: { date_from: dateFrom, date_to: dateTo } }),
                        ]);

                        const checkData = checkRes.data;
                        setAttendanceCheck(checkData);

                        // Aggregate days present per employee from logs
                        const logs: any[] = logsRes.data;
                        const dayMap: Record<string, Set<string>> = {};
                        const nameMap: Record<string, { name: string; email: string }> = {};
                        logs.forEach((log: any) => {
                          const empId = String(log.employee_id || log.user?.employee_id || log.user_id);
                          const date  = (log.date || log.check_in || '').split('T')[0];
                          if (!dayMap[empId]) dayMap[empId] = new Set();
                          if (date) dayMap[empId].add(date);
                          if (!nameMap[empId]) {
                            nameMap[empId] = {
                              name:  log.user?.full_name || log.full_name || log.name || empId,
                              email: log.user?.email    || log.email    || '',
                            };
                          }
                        });

                        // Build rows: all employees from check (present + missing)
                        const missingSet = new Set(checkData.missing.map((m: any) => String(m.employee_id)));
                        const rows: typeof attDetailRows = [];

                        // Employees present in logs
                        Object.entries(dayMap).forEach(([empId, dates]) => {
                          rows.push({
                            employee_id:      empId,
                            name:             nameMap[empId]?.name  || empId,
                            email:            nameMap[empId]?.email || '',
                            days_present:     dates.size,
                            total_working_days: workingDays,
                          });
                        });

                        // Missing employees (0 days)
                        checkData.missing.forEach((m: any) => {
                          const alreadyAdded = rows.some(r => r.employee_id === String(m.employee_id));
                          if (!alreadyAdded) {
                            rows.push({
                              employee_id:      String(m.employee_id),
                              name:             m.name,
                              email:            m.email,
                              days_present:     0,
                              total_working_days: workingDays,
                            });
                          }
                        });

                        // Sort: missing first, then by name
                        rows.sort((a, b) => {
                          const aMissing = missingSet.has(a.employee_id) ? 0 : 1;
                          const bMissing = missingSet.has(b.employee_id) ? 0 : 1;
                          if (aMissing !== bMissing) return aMissing - bMissing;
                          return a.name.localeCompare(b.name);
                        });

                        setAttDetailRows(rows);
                      } catch { toast.error('Failed to fetch attendance check'); }
                      finally { setLoadingAttCheck(false); }
                    }}
                    disabled={loadingAttCheck}
                    className="h-11 px-6 font-black uppercase text-[9px] tracking-widest border-slate-200 shrink-0 flex items-center gap-2"
                  >
                    {loadingAttCheck ? <Loader2 size={14} className="animate-spin" /> : <AlertCircle size={14} />}
                    {loadingAttCheck ? 'Checking...' : attendanceCheck ? 'Re-check' : 'Run Check'}
                  </Button>
                </div>

                {/* Results */}
                {!attendanceCheck && !loadingAttCheck && (
                  <div className="py-12 flex flex-col items-center gap-4 bg-slate-50 rounded-3xl border-2 border-dashed border-slate-200">
                    <div className="w-16 h-16 bg-white rounded-2xl border border-slate-200 flex items-center justify-center shadow-sm">
                      <Clock size={28} className="text-slate-400" />
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-black text-slate-500 uppercase tracking-widest">Run a coverage check</p>
                      <p className="text-xs font-bold text-slate-400 mt-1">Click "Run Check" to see who has attendance marked this period</p>
                    </div>
                  </div>
                )}

                {loadingAttCheck && (
                  <div className="py-12 flex flex-col items-center gap-4 bg-slate-50 rounded-3xl">
                    <Loader2 size={32} className="text-blue-600 animate-spin" />
                    <p className="text-[10px] font-black uppercase text-slate-400 tracking-widest">Scanning attendance records...</p>
                  </div>
                )}

                {attendanceCheck && !loadingAttCheck && (() => {
                  const coveragePct = attendanceCheck.total_active_employees > 0
                    ? Math.round((attendanceCheck.with_attendance / attendanceCheck.total_active_employees) * 100)
                    : 0;
                  const allGood = attendanceCheck.missing_attendance === 0;
                  const missingSet = new Set(attendanceCheck.missing.map(m => String(m.employee_id)));
                  return (
                    <div className="space-y-5">
                      {/* Summary strip */}
                      <div className="grid grid-cols-4 gap-4">
                        <div className="p-4 bg-slate-50 border border-slate-100 rounded-2xl text-center">
                          <p className="text-2xl font-black text-[#0F172A]">{attendanceCheck.total_active_employees}</p>
                          <p className="text-[8px] font-black text-slate-400 uppercase tracking-widest mt-1">Total Active</p>
                        </div>
                        <div className="p-4 bg-green-50 border border-green-100 rounded-2xl text-center">
                          <p className="text-2xl font-black text-green-600">{attendanceCheck.with_attendance}</p>
                          <p className="text-[8px] font-black text-green-400 uppercase tracking-widest mt-1">Attendance Marked</p>
                        </div>
                        <div className={cn("p-4 rounded-2xl border text-center", attendanceCheck.missing_attendance > 0 ? "bg-red-50 border-red-100" : "bg-slate-50 border-slate-100")}>
                          <p className={cn("text-2xl font-black", attendanceCheck.missing_attendance > 0 ? "text-red-600" : "text-slate-300")}>{attendanceCheck.missing_attendance}</p>
                          <p className={cn("text-[8px] font-black uppercase tracking-widest mt-1", attendanceCheck.missing_attendance > 0 ? "text-red-400" : "text-slate-300")}>Missing</p>
                        </div>
                        <div className={cn("p-4 rounded-2xl border text-center", allGood ? "bg-green-50 border-green-100" : "bg-amber-50 border-amber-100")}>
                          <p className={cn("text-2xl font-black", allGood ? "text-green-600" : "text-amber-600")}>{coveragePct}%</p>
                          <p className={cn("text-[8px] font-black uppercase tracking-widest mt-1", allGood ? "text-green-400" : "text-amber-400")}>Coverage</p>
                        </div>
                      </div>

                      {/* Progress bar */}
                      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className={cn("h-full rounded-full transition-all duration-700", allGood ? "bg-green-500" : "bg-amber-500")}
                          style={{ width: `${coveragePct}%` }}
                        />
                      </div>

                      {/* All clear banner */}
                      {allGood && (
                        <div className="flex items-center gap-4 p-4 bg-green-50 border border-green-100 rounded-2xl">
                          <CheckCircle2 size={18} className="text-green-600 shrink-0" />
                          <p className="text-sm font-black text-green-800">All employees accounted for — safe to lock.</p>
                        </div>
                      )}

                      {/* Attendance table */}
                      {attDetailRows.length > 0 && (
                        <div className="border border-slate-200 rounded-2xl overflow-hidden">
                          <div className="max-h-72 overflow-y-auto">
                            <table className="w-full text-left border-collapse">
                              <thead className="sticky top-0 z-10 bg-slate-50 border-b border-slate-200">
                                <tr>
                                  <th className="px-5 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Employee</th>
                                  <th className="px-5 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest">Emp ID</th>
                                  <th className="px-5 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest text-center">Days Present</th>
                                  <th className="px-5 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest text-center">Working Days</th>
                                  <th className="px-5 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest text-center">Coverage</th>
                                  <th className="px-5 py-3 text-[9px] font-black text-slate-400 uppercase tracking-widest text-center">Status</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-50 bg-white">
                                {attDetailRows.map((row) => {
                                  const isMissing = missingSet.has(row.employee_id);
                                  const pct = row.total_working_days > 0
                                    ? Math.round((row.days_present / row.total_working_days) * 100)
                                    : 0;
                                  return (
                                    <tr key={row.employee_id} className={cn("transition-colors", isMissing ? "bg-red-50/40 hover:bg-red-50/60" : "hover:bg-slate-50/50")}>
                                      <td className="px-5 py-3">
                                        <div className="flex items-center gap-3">
                                          <div className={cn("w-8 h-8 rounded-xl flex items-center justify-center font-black text-xs shrink-0",
                                            isMissing ? "bg-red-100 text-red-500" : "bg-blue-50 text-blue-600"
                                          )}>
                                            {row.name?.charAt(0) || '?'}
                                          </div>
                                          <div className="min-w-0">
                                            <p className="text-sm font-black text-[#0F172A] truncate">{row.name}</p>
                                            <p className="text-[9px] font-bold text-slate-400 truncate">{row.email}</p>
                                          </div>
                                        </div>
                                      </td>
                                      <td className="px-5 py-3 text-[10px] font-bold text-slate-400 uppercase">{row.employee_id}</td>
                                      <td className="px-5 py-3 text-center">
                                        <span className={cn("text-sm font-black", isMissing ? "text-red-500" : "text-[#0F172A]")}>
                                          {row.days_present}
                                        </span>
                                      </td>
                                      <td className="px-5 py-3 text-center">
                                        <span className="text-sm font-black text-slate-500">{row.total_working_days}</span>
                                      </td>
                                      <td className="px-5 py-3">
                                        <div className="flex items-center gap-2 justify-center">
                                          <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                                            <div
                                              className={cn("h-full rounded-full", pct === 0 ? "bg-red-400" : pct < 70 ? "bg-amber-400" : "bg-green-500")}
                                              style={{ width: `${pct}%` }}
                                            />
                                          </div>
                                          <span className={cn("text-[10px] font-black w-8 text-right", pct === 0 ? "text-red-500" : pct < 70 ? "text-amber-500" : "text-green-600")}>
                                            {pct}%
                                          </span>
                                        </div>
                                      </td>
                                      <td className="px-5 py-3 text-center">
                                        {isMissing ? (
                                          <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-red-100 text-red-600 rounded-lg text-[9px] font-black uppercase tracking-widest">
                                            <AlertCircle size={10} /> No Record
                                          </span>
                                        ) : (
                                          <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-green-100 text-green-700 rounded-lg text-[9px] font-black uppercase tracking-widest">
                                            <CheckCircle2 size={10} /> Present
                                          </span>
                                        )}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}

                {/* Lock button */}
                <div className="flex justify-end pt-2 border-t border-slate-100">
                  <Button
                    onClick={() => handleStatusTransition('lock-attendance')}
                    disabled={actionLoading}
                    className={cn(
                      "h-12 px-10 rounded-2xl font-black uppercase text-[10px] tracking-widest shadow-lg",
                      attendanceCheck?.missing_attendance
                        ? "bg-amber-500 hover:bg-amber-600 shadow-amber-500/20"
                        : "bg-blue-600 hover:bg-blue-700 shadow-blue-600/20"
                    )}
                  >
                    {actionLoading ? <Loader2 className="animate-spin mr-2" size={16} /> : <Lock size={16} className="mr-2" />}
                    {attendanceCheck?.missing_attendance
                      ? `Lock Anyway — ${attendanceCheck.missing_attendance} Missing`
                      : 'Lock Attendance Period'}
                  </Button>
                </div>
              </div>
           )}

           {currentStep === 2 && (
              <div className="text-center space-y-6">
                <div className="w-20 h-20 bg-blue-50 rounded-3xl flex items-center justify-center text-blue-600 mx-auto">
                   <Lock size={40} />
                </div>
                <div>
                   <h3 className="text-xl font-black">Attendance Locked</h3>
                   <p className="text-slate-500 font-bold max-w-md mx-auto mt-2">Attendance logs are secured. Proceed to reconcile and lock approved leaves.</p>
                </div>
                <Button 
                  onClick={() => handleStatusTransition('lock-leaves')} 
                  disabled={actionLoading}
                  className="bg-blue-600 hover:bg-blue-700 h-14 px-10 rounded-2xl font-black"
                >
                  {actionLoading ? <Loader2 className="animate-spin mr-2" /> : "Next: Lock Leaves"}
                </Button>
              </div>
           )}

           {currentStep === 3 && (
              <div className="text-center space-y-6">
                <div className="w-20 h-20 bg-blue-50 rounded-3xl flex items-center justify-center text-blue-600 mx-auto">
                   <Calculator size={40} />
                </div>
                <div>
                   <h3 className="text-xl font-black">Compute Payroll Lines</h3>
                   <p className="text-slate-500 font-bold max-w-md mx-auto mt-2">Generate draft payroll lines based on locked data and LOP deductions.</p>
                </div>
                <Button 
                  onClick={() => handleStatusTransition('generate-draft')} 
                  disabled={actionLoading}
                  className="bg-blue-600 hover:bg-blue-700 h-14 px-10 rounded-2xl font-black"
                >
                  {actionLoading ? <Loader2 className="animate-spin mr-2" /> : "Generate Draft"}
                </Button>
              </div>
           )}

           {(currentStep === 4 || currentStep === 5) && (
              <div className="space-y-6">
                 <div className="flex justify-between items-end">
                    <div>
                       <h3 className="text-xl font-black">{currentStep === 4 ? 'Review & Disburse' : 'Finalized — Disburse Remaining'}</h3>
                       <p className="text-slate-500 font-bold">{currentStep === 4 ? 'Pay employees in full or partial amounts before finalizing.' : 'Disburse any remaining amounts, then publish payslips.'}</p>
                    </div>
                    <div className="flex items-end gap-4">
                      <Button
                        variant="outline"
                        onClick={exportSalaryRegister}
                        disabled={exporting}
                        className="h-11 px-5 rounded-xl font-black text-xs"
                      >
                        {exporting ? (
                          <Loader2 size={14} className="animate-spin mr-1.5" />
                        ) : (
                          <Download size={14} className="mr-1.5" />
                        )}
                        Export Excel
                      </Button>
                      <div className="text-right">
                         <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest block">Total Gross</span>
                         <span className="text-2xl font-black text-green-600">₹{currentRun.total_gross.toLocaleString('en-IN')}</span>
                      </div>
                    </div>
                 </div>

                 {/* Per-head salary breakdown */}
                 <div className="space-y-4 max-h-[620px] overflow-y-auto pr-1">
                   {runLines.map(line => {
                     const al = line.allowances || {};
                     const ded = line.deductions || {};
                     const payable = line.payable_amount ?? (line.net_pay - line.advance_deduction);
                     const pending = line.pending_amount ?? (payable - line.disbursed_amount);
                     const fullyPaid = pending <= 0.01;
                     const isEditing = editingLineId === line.id;
                     const isExpanded = expandedLineId === line.id;

                     const fmt = (v: number) => v > 0 ? `₹${Math.round(v).toLocaleString('en-IN')}` : '—';

                     return (
                       <div key={line.id} className={cn(
                         "rounded-2xl border overflow-hidden",
                         fullyPaid ? "border-green-100 bg-green-50/20" : "border-slate-100 bg-white"
                       )}>
                         {/* Header row */}
                         <div
                           className="flex items-center justify-between px-5 py-3 bg-slate-50 border-b border-slate-100 cursor-pointer hover:bg-slate-100 transition-colors select-none"
                           onClick={() => setExpandedLineId(isExpanded ? null : line.id)}
                         >
                           <div className="flex items-center gap-3">
                             <ChevronRight size={14} className={cn("text-slate-400 transition-transform duration-200 shrink-0", isExpanded && "rotate-90")} />
                             <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center font-black text-xs shrink-0">
                               {line.user_full_name?.charAt(0)}
                             </div>
                             <div>
                               <p className="text-sm font-black text-slate-900">{line.user_full_name}</p>
                               <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">
                                 {line.payable_days}d paid
                                 {line.lop_days > 0 && <span className="text-red-400 ml-1">· {line.lop_days}d LOP</span>}
                               </p>
                             </div>
                           </div>
                           <div className="flex items-center gap-6">
                             <div className="text-right">
                               <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Gross</p>
                               <p className="text-sm font-black text-slate-800">₹{Math.round(line.gross_pay).toLocaleString('en-IN')}</p>
                             </div>
                             <div className="text-right">
                               <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Net Pay</p>
                               <p className="text-sm font-black text-slate-800">₹{Math.round(line.net_pay).toLocaleString('en-IN')}</p>
                             </div>
                             <div className="text-right">
                               <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Payable</p>
                               <p className="text-sm font-black text-blue-700">₹{Math.round(payable).toLocaleString('en-IN')}</p>
                             </div>
                             <div className="text-right">
                               <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Status</p>
                               {fullyPaid
                                 ? <Badge className="bg-green-100 text-green-700 text-[9px] font-black">Paid</Badge>
                                 : <p className="text-sm font-black text-red-600">₹{Math.round(pending).toLocaleString('en-IN')}</p>
                               }
                             </div>
                             <button
                               onClick={async (e) => {
                                 e.stopPropagation();
                                 setDisburseModal({ line });
                                 try {
                                   const res = await client.get(ENDPOINTS.HR.DISBURSEMENTS(line.id));
                                   setDisbursements(res.data);
                                 } catch { setDisbursements([]); }
                               }}
                               className={cn(
                                 "text-[9px] font-black px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap",
                                 fullyPaid ? "text-slate-400 hover:text-slate-600 hover:bg-slate-100" : "text-white bg-blue-600 hover:bg-blue-700"
                               )}
                             >
                               {fullyPaid ? 'View' : 'Pay'}
                             </button>
                           </div>
                         </div>

                         {/* Breakdown grid — shown when expanded */}
                         {isExpanded && <div className="grid grid-cols-2 divide-x divide-slate-100">
                           {/* Earnings */}
                           <div className="p-4 space-y-1">
                             <p className="text-[8px] font-black text-green-600 uppercase tracking-[0.2em] mb-2">Earnings (Actual)</p>
                             {[
                               ['Basic', al.basic_salary_actual],
                               ['HRA', al.hra_actual],
                               ['Conveyance', al.conveyance_actual],
                               ['Other Allow.', al.other_allowance_actual],
                             ].map(([label, val]) => val > 0 && (
                               <div key={label as string} className="flex justify-between text-xs">
                                 <span className="text-slate-500 font-bold">{label}</span>
                                 <span className="font-black text-slate-700">{fmt(val as number)}</span>
                               </div>
                             ))}

                             {/* Arrear row — editable in step 4 */}
                             <div className="flex justify-between text-xs items-center">
                               <span className="text-slate-500 font-bold">Arrear</span>
                               {isEditing && currentStep === 4 ? (
                                 <input
                                   type="number"
                                   value={lineEditValues.arrear}
                                   onChange={e => setLineEditValues(v => ({ ...v, arrear: e.target.value }))}
                                   className="w-24 text-right text-xs font-black border border-blue-300 rounded-lg px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                                 />
                               ) : (
                                 <span className={cn("font-black", (line.arrear || 0) > 0 ? "text-blue-700" : "text-slate-400")}>
                                   {(line.arrear || 0) > 0 ? fmt(line.arrear!) : '—'}
                                 </span>
                               )}
                             </div>

                             {/* Incentive row — editable in step 4 */}
                             <div className="flex justify-between text-xs items-center">
                               <span className="text-slate-500 font-bold">Incentive</span>
                               {isEditing && currentStep === 4 ? (
                                 <input
                                   type="number"
                                   value={lineEditValues.incentive}
                                   onChange={e => setLineEditValues(v => ({ ...v, incentive: e.target.value }))}
                                   className="w-24 text-right text-xs font-black border border-blue-300 rounded-lg px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
                                 />
                               ) : (
                                 <span className={cn("font-black", (line.incentive || 0) > 0 ? "text-blue-700" : "text-slate-400")}>
                                   {(line.incentive || 0) > 0 ? fmt(line.incentive!) : '—'}
                                 </span>
                               )}
                             </div>

                             {/* OT + Night allowance injected from shift-engine entries (read-only) */}
                             {(al.overtime || 0) > 0 && (
                               <div className="flex justify-between text-xs items-center">
                                 <span className="text-slate-500 font-bold">
                                   Overtime
                                   {al.overtime_minutes ? (
                                     <span className="text-[9px] text-slate-400 font-normal ml-1">
                                       ({Math.round(al.overtime_minutes / 60 * 10) / 10}h)
                                     </span>
                                   ) : null}
                                 </span>
                                 <span className="font-black text-purple-700">{fmt(al.overtime)}</span>
                               </div>
                             )}
                             {(al.night_allowance || 0) > 0 && (
                               <div className="flex justify-between text-xs items-center">
                                 <span className="text-slate-500 font-bold">
                                   Night Allowance
                                   {al.night_minutes ? (
                                     <span className="text-[9px] text-slate-400 font-normal ml-1">
                                       ({Math.round(al.night_minutes / 60 * 10) / 10}h)
                                     </span>
                                   ) : null}
                                 </span>
                                 <span className="font-black text-indigo-700">{fmt(al.night_allowance)}</span>
                               </div>
                             )}

                             <div className="flex justify-between text-xs pt-1 border-t border-slate-100 mt-1">
                               <span className="font-black text-slate-700 uppercase text-[9px] tracking-widest">Total Gross</span>
                               <span className="font-black text-slate-900">₹{Math.round(line.gross_pay).toLocaleString('en-IN')}</span>
                             </div>

                             {/* Edit / Save / Cancel for step 4 */}
                             {currentStep === 4 && (
                               <div className="pt-2">
                                 {isEditing ? (
                                   <div className="flex gap-2">
                                     <button
                                       disabled={savingLineId === line.id}
                                       onClick={() => saveLineEdit(line)}
                                       className="flex-1 text-[9px] font-black bg-blue-600 text-white rounded-lg py-1 hover:bg-blue-700 disabled:opacity-50"
                                     >
                                       {savingLineId === line.id ? 'Saving…' : 'Save'}
                                     </button>
                                     <button
                                       onClick={() => setEditingLineId(null)}
                                       className="flex-1 text-[9px] font-black text-slate-500 border border-slate-200 rounded-lg py-1 hover:bg-slate-50"
                                     >
                                       Cancel
                                     </button>
                                   </div>
                                 ) : (
                                   <button
                                     onClick={() => {
                                       setEditingLineId(line.id);
                                       setLineEditValues({
                                         arrear: String(line.arrear || 0),
                                         incentive: String(line.incentive || 0),
                                       });
                                     }}
                                     className="w-full text-[9px] font-black text-blue-600 border border-blue-200 rounded-lg py-1 hover:bg-blue-50"
                                   >
                                     Edit Arrear / Incentive
                                   </button>
                                 )}
                               </div>
                             )}
                           </div>

                           {/* Deductions */}
                           <div className="p-4 space-y-1">
                             <p className="text-[8px] font-black text-red-500 uppercase tracking-[0.2em] mb-2">Deductions</p>
                             {[
                               ['ESI (0.75%)', ded.employee_esi],
                               ['PF (12%)', ded.employee_pf],
                               ['Voluntary PF', ded.voluntary_pf],
                               ['Prof. Tax', ded.professional_tax],
                               ['Guest House', ded.guest_house],
                               ['TDS', ded.tds],
                               ['Advance', line.advance_deduction],
                             ].map(([label, val]) => (
                               <div key={label as string} className="flex justify-between text-xs">
                                 <span className="text-slate-500 font-bold">{label}</span>
                                 <span className={cn("font-black", (val as number) > 0 ? "text-red-600" : "text-slate-300")}>
                                   {(val as number) > 0 ? fmt(val as number) : '—'}
                                 </span>
                               </div>
                             ))}
                             <div className="flex justify-between text-xs pt-1 border-t border-slate-100 mt-1">
                               <span className="font-black text-slate-700 uppercase text-[9px] tracking-widest">Total Deductions</span>
                               <span className="font-black text-red-700">
                                 ₹{Math.round((ded.total_deductions || 0) + (line.advance_deduction || 0)).toLocaleString('en-IN')}
                               </span>
                             </div>
                             <div className="flex justify-between text-xs pt-1 border-t border-slate-100 mt-1">
                               <span className="font-black text-slate-700 uppercase text-[9px] tracking-widest">Net Salary</span>
                               <span className="font-black text-slate-900">₹{Math.round(line.net_pay).toLocaleString('en-IN')}</span>
                             </div>
                             <div className="flex justify-between text-xs mt-2 pt-2 border-t border-dashed border-slate-200">
                               <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Employer PF</span>
                               <span className="font-bold text-slate-400">{fmt(ded.employer_pf || 0)}</span>
                             </div>
                             <div className="flex justify-between text-xs">
                               <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Employer ESIC</span>
                               <span className="font-bold text-slate-400">{fmt(ded.employer_esic || 0)}</span>
                             </div>
                             <div className="flex justify-between text-xs">
                               <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Total CTC</span>
                               <span className="font-bold text-slate-500">{fmt(ded.total_employer_cost || 0)}</span>
                             </div>
                           </div>
                         </div>}
                       </div>
                     );
                   })}
                 </div>

                 <div className="flex justify-end gap-3 pt-4">
                    {currentStep === 4 && (
                      <Button
                        onClick={() => setConfirmAction('finalize')}
                        disabled={actionLoading}
                        className="bg-green-600 hover:bg-green-700 h-14 px-10 rounded-2xl font-black"
                      >
                        Finalize & Approve
                      </Button>
                    )}
                    {currentStep === 5 && (
                      <Button
                        onClick={() => setConfirmAction('publish')}
                        disabled={actionLoading}
                        className="bg-green-600 hover:bg-green-700 h-14 px-10 rounded-2xl font-black"
                      >
                        Publish Payslips
                      </Button>
                    )}
                 </div>
              </div>
           )}
        </Card>

        {/* Disbursement Modal */}
        <Dialog open={!!disburseModal} onOpenChange={(open) => { if (!open) setDisburseModal(null); }}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle className="text-lg font-black">
                {disburseModal?.line.user_full_name} — Salary Disbursement
              </DialogTitle>
            </DialogHeader>

            {disburseModal && (() => {
              const line = disburseModal.line;
              const payable = line.payable_amount ?? (line.net_pay - line.advance_deduction);
              const pending = line.pending_amount ?? (payable - line.disbursed_amount);
              const fullyPaid = pending <= 0.01;

              return (
                <div className="space-y-5">
                  {/* Summary */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="bg-slate-50 rounded-xl p-3 text-center">
                      <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest block">Payable</span>
                      <span className="text-lg font-black text-slate-900">₹{payable.toLocaleString('en-IN')}</span>
                    </div>
                    <div className="bg-green-50 rounded-xl p-3 text-center">
                      <span className="text-[9px] font-black text-green-500 uppercase tracking-widest block">Disbursed</span>
                      <span className="text-lg font-black text-green-600">₹{line.disbursed_amount.toLocaleString('en-IN')}</span>
                    </div>
                    <div className={cn("rounded-xl p-3 text-center", fullyPaid ? "bg-green-50" : "bg-red-50")}>
                      <span className={cn("text-[9px] font-black uppercase tracking-widest block", fullyPaid ? "text-green-500" : "text-red-400")}>Pending</span>
                      <span className={cn("text-lg font-black", fullyPaid ? "text-green-600" : "text-red-600")}>
                        {fullyPaid ? 'Fully Paid' : `₹${pending.toLocaleString('en-IN')}`}
                      </span>
                    </div>
                  </div>

                  {/* Disbursement History */}
                  {disbursements.length > 0 && (
                    <div>
                      <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Payment History</h4>
                      <div className="border border-slate-100 rounded-xl overflow-hidden max-h-40 overflow-y-auto">
                        <table className="w-full text-left text-xs">
                          <thead className="bg-slate-50">
                            <tr>
                              <th className="px-3 py-2 font-bold text-slate-400">#</th>
                              <th className="px-3 py-2 font-bold text-slate-400">Amount</th>
                              <th className="px-3 py-2 font-bold text-slate-400">Mode</th>
                              <th className="px-3 py-2 font-bold text-slate-400">Ref</th>
                              <th className="px-3 py-2 font-bold text-slate-400">Date</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-50">
                            {disbursements.map((d, i) => (
                              <tr key={d.id}>
                                <td className="px-3 py-2 text-slate-500">{i + 1}</td>
                                <td className="px-3 py-2 font-bold text-green-600">₹{d.amount.toLocaleString('en-IN')}</td>
                                <td className="px-3 py-2 text-slate-600">{d.payment_mode}</td>
                                <td className="px-3 py-2 text-slate-400">{d.reference || '—'}</td>
                                <td className="px-3 py-2 text-slate-400">{new Date(d.disbursed_at).toLocaleDateString()}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* New Disbursement Form */}
                  {!fullyPaid && (
                    <form
                      onSubmit={async (e) => {
                        e.preventDefault();
                        const form = e.target as HTMLFormElement;
                        const amount = parseFloat((form.elements.namedItem('amount') as HTMLInputElement).value);
                        const payment_mode = (form.elements.namedItem('payment_mode') as HTMLInputElement).value;
                        const reference = (form.elements.namedItem('reference') as HTMLInputElement).value;
                        const remarks = (form.elements.namedItem('remarks') as HTMLInputElement).value;

                        if (!amount || amount <= 0) { toast.error('Enter a valid amount'); return; }
                        if (amount > pending + 0.01) { toast.error('Amount exceeds pending balance'); return; }

                        setActionLoading(true);
                        try {
                          await client.post(ENDPOINTS.HR.DISBURSE(line.id), {
                            amount,
                            payment_mode,
                            reference: reference || undefined,
                            remarks: remarks || undefined,
                          });
                          toast.success('Disbursement recorded');
                          // Refresh lines and disbursement history
                          const [linesRes, disbRes] = await Promise.all([
                            client.get(ENDPOINTS.HR.PAYROLL.LINES(currentRun!.id)),
                            client.get(ENDPOINTS.HR.DISBURSEMENTS(line.id)),
                          ]);
                          setRunLines(linesRes.data);
                          setDisbursements(disbRes.data);
                          // Update the modal line reference
                          const updatedLine = linesRes.data.find((l: PayrollLine) => l.id === line.id);
                          if (updatedLine) setDisburseModal({ line: updatedLine });
                          form.reset();
                        } catch (error: any) {
                          toast.error(getErrorMessage(error, 'Failed to record disbursement'));
                        } finally {
                          setActionLoading(false);
                        }
                      }}
                      className="space-y-3"
                    >
                      <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Record Payment</h4>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-[10px] font-bold text-slate-500 block mb-1">Amount *</label>
                          <Input name="amount" type="number" step="0.01" max={pending} placeholder={`Max ₹${pending.toLocaleString('en-IN')}`} required className="rounded-lg" />
                        </div>
                        <div>
                          <label className="text-[10px] font-bold text-slate-500 block mb-1">Payment Mode</label>
                          <select name="payment_mode" defaultValue="bank_transfer" className="w-full h-10 px-3 border border-slate-200 rounded-lg text-sm font-bold">
                            <option value="bank_transfer">Bank Transfer</option>
                            <option value="cash">Cash</option>
                            <option value="cheque">Cheque</option>
                            <option value="upi">UPI</option>
                          </select>
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-[10px] font-bold text-slate-500 block mb-1">Reference #</label>
                          <Input name="reference" placeholder="Transaction ID" className="rounded-lg" />
                        </div>
                        <div>
                          <label className="text-[10px] font-bold text-slate-500 block mb-1">Remarks</label>
                          <Input name="remarks" placeholder="Optional note" className="rounded-lg" />
                        </div>
                      </div>
                      <Button type="submit" disabled={actionLoading} className="w-full bg-blue-600 hover:bg-blue-700 h-11 rounded-xl font-black">
                        {actionLoading ? <Loader2 className="animate-spin mr-2" /> : null}
                        Record Disbursement
                      </Button>
                    </form>
                  )}
                </div>
              );
            })()}
          </DialogContent>
        </Dialog>

        {/* Finalize / Publish Confirmation Dialog */}
        <Dialog open={!!confirmAction} onOpenChange={(open) => { if (!open) setConfirmAction(null); }}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="text-lg font-black">
                {confirmAction === 'finalize' ? 'Finalize Payroll Run?' : 'Publish Payslips?'}
              </DialogTitle>
            </DialogHeader>
            {(() => {
              const withSalary = runLines.filter(l => (l.payable_amount ?? (l.net_pay - l.advance_deduction)) > 0.01);
              const fullyPaidCount = withSalary.filter(l => (l.pending_amount ?? ((l.payable_amount ?? (l.net_pay - l.advance_deduction)) - l.disbursed_amount)) <= 0.01).length;
              const partialCount = withSalary.filter(l => {
                const pending = l.pending_amount ?? ((l.payable_amount ?? (l.net_pay - l.advance_deduction)) - l.disbursed_amount);
                const payable = l.payable_amount ?? (l.net_pay - l.advance_deduction);
                return pending > 0.01 && l.disbursed_amount > 0.01 && pending < payable - 0.01;
              }).length;
              const unpaidCount = withSalary.filter(l => l.disbursed_amount <= 0.01 && (l.payable_amount ?? (l.net_pay - l.advance_deduction)) > 0.01).length;
              const totalPending = withSalary.reduce((s, l) => s + (l.pending_amount ?? ((l.payable_amount ?? (l.net_pay - l.advance_deduction)) - l.disbursed_amount)), 0);

              return (
                <div className="space-y-4 mt-2">
                  <div className="grid grid-cols-3 gap-3">
                    <div className="bg-green-50 rounded-xl p-3 text-center">
                      <span className="text-2xl font-black text-green-600">{fullyPaidCount}</span>
                      <span className="text-[9px] font-black text-green-500 uppercase tracking-widest block mt-1">Fully Paid</span>
                    </div>
                    <div className={cn("rounded-xl p-3 text-center", partialCount > 0 ? "bg-amber-50" : "bg-slate-50")}>
                      <span className={cn("text-2xl font-black", partialCount > 0 ? "text-amber-600" : "text-slate-300")}>{partialCount}</span>
                      <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest block mt-1">Partial</span>
                    </div>
                    <div className={cn("rounded-xl p-3 text-center", unpaidCount > 0 ? "bg-red-50" : "bg-slate-50")}>
                      <span className={cn("text-2xl font-black", unpaidCount > 0 ? "text-red-600" : "text-slate-300")}>{unpaidCount}</span>
                      <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest block mt-1">Unpaid</span>
                    </div>
                  </div>

                  {totalPending > 0.01 && (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
                      <AlertCircle size={18} className="text-amber-600 mt-0.5 shrink-0" />
                      <div>
                        <p className="text-sm font-black text-amber-800">
                          ₹{totalPending.toLocaleString('en-IN')} still pending
                        </p>
                        <p className="text-xs text-amber-600 font-bold mt-1">
                          {confirmAction === 'finalize'
                            ? 'You can still disburse remaining amounts after finalizing.'
                            : 'Payslips will be published. Remaining amounts can still be disbursed.'}
                        </p>
                      </div>
                    </div>
                  )}

                  {totalPending <= 0.01 && (
                    <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
                      <p className="text-sm font-black text-green-700">All salaries fully disbursed</p>
                    </div>
                  )}

                  <DialogFooter className="gap-3 pt-2">
                    <Button variant="outline" onClick={() => setConfirmAction(null)} className="rounded-xl font-bold">
                      Cancel
                    </Button>
                    <Button
                      onClick={() => {
                        handleStatusTransition(confirmAction!);
                        setConfirmAction(null);
                      }}
                      disabled={actionLoading}
                      className="bg-green-600 hover:bg-green-700 rounded-xl font-black"
                    >
                      {actionLoading ? <Loader2 className="animate-spin mr-2" size={16} /> : null}
                      {confirmAction === 'finalize' ? 'Confirm Finalize' : 'Confirm Publish'}
                    </Button>
                  </DialogFooter>
                </div>
              );
            })()}
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-[1400px] mx-auto animate-in fade-in duration-700">
      <div className="flex justify-between items-start mb-12">
        <div>
          <h1 className="text-4xl font-black text-[#0F172A] tracking-tighter">Financial Payroll Center</h1>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Enterprise-grade Disbursement & Reconciliation Engine</p>
        </div>
        <div className="flex gap-4">
           <div className="flex gap-2">
              <Select value={selectedMonth.toString()} onValueChange={(v) => setSelectedMonth(parseInt(v))}>
                 <SelectTrigger className="w-32 bg-white border-slate-200 rounded-xl font-bold">
                    <SelectValue />
                 </SelectTrigger>
                 <SelectContent>
                    {[1,2,3,4,5,6,7,8,9,10,11,12].map(m => (
                       <SelectItem key={m} value={m.toString()}>{new Date(0, m-1).toLocaleString('default', { month: 'long' })}</SelectItem>
                    ))}
                 </SelectContent>
              </Select>
              <Select value={selectedYear.toString()} onValueChange={(v) => setSelectedYear(parseInt(v))}>
                 <SelectTrigger className="w-32 bg-white border-slate-200 rounded-xl font-bold">
                    <SelectValue />
                 </SelectTrigger>
                 <SelectContent>
                    {[2024, 2025, 2026].map(y => (
                       <SelectItem key={y} value={y.toString()}>{y}</SelectItem>
                    ))}
                 </SelectContent>
              </Select>
           </div>
           <Button onClick={startNewRun} disabled={actionLoading} className="bg-blue-600 hover:bg-blue-700 h-12 px-8 rounded-xl font-black shadow-lg shadow-blue-600/20">
             {actionLoading ? <Loader2 className="animate-spin" /> : <><Plus size={20} className="mr-2" /> Start New Run</>}
           </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
        {[
          { label: 'YTD Total Gross', value: `₹${dashboardData?.total_processed_ytd.toLocaleString('en-IN')}`, trend: '+4.2%', icon: Banknote, color: 'text-blue-600' },
          { label: 'Active Runs', value: dashboardData?.active_runs?.length || 0, trend: 'Manual Step', icon: Clock, color: 'text-amber-600' },
          { label: 'Last Finalized', value: dashboardData?.last_finalized_run ? `${dashboardData.last_finalized_run.month}/${dashboardData.last_finalized_run.year}` : 'N/A', trend: 'Finance Dept', icon: FileCheck, color: 'text-green-600' },
          { label: 'Next Processing', value: 'Drafting', trend: 'Automated', icon: CreditCard, color: 'text-slate-600' },
        ].map((stat, i) => (
          <Card key={i} className="p-6 border-slate-200 hover:shadow-xl hover:shadow-slate-200/50 transition-all duration-500 group">
             <div className="flex justify-between items-start mb-4">
                <div className={cn("p-3 rounded-2xl bg-slate-50 transition-colors group-hover:bg-white", stat.color)}>
                   <stat.icon size={24} />
                </div>
                <Badge variant="outline" className="text-[10px] font-black border-slate-100">{stat.trend}</Badge>
             </div>
             <div>
                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{stat.label}</span>
                <h4 className="text-2xl font-black text-slate-900 mt-1">{stat.value}</h4>
             </div>
          </Card>
        ))}
      </div>

      <div className="space-y-6">
        <h3 className="text-xl font-black text-slate-900">Active Payroll Runs</h3>
        <div className="grid grid-cols-1 gap-4">
            {((dashboardData?.active_runs || []) as any[]).length === 0 ? (
             <div className="p-12 border-2 border-dashed border-slate-200 rounded-3xl text-center">
                <p className="font-bold text-slate-400">No active payroll runs found.</p>
             </div>
            ) : ((dashboardData?.active_runs || []) as any[]).map(run => (
              <Card key={run.id} className="p-6 border-slate-200 flex justify-between items-center group hover:border-blue-200 transition-colors">
                 <div className="flex gap-6 items-center">
                    <div className="w-14 h-14 bg-slate-50 rounded-2xl flex items-center justify-center text-slate-600 group-hover:bg-blue-50 group-hover:text-blue-600 transition-colors">
                       <Calculator size={28} />
                    </div>
                    <div>
                       <h5 className="text-lg font-black text-slate-900">{new Date(0, run.month-1).toLocaleString('default', { month: 'long' })} {run.year}</h5>
                       <div className="flex gap-3 mt-1">
                          <Badge className="bg-blue-100 text-blue-700 text-[9px] font-black">{run.status}</Badge>
                          <span className="text-[11px] font-bold text-slate-400">Created: {new Date(run.created_at).toLocaleDateString()}</span>
                       </div>
                    </div>
                 </div>
                  <Button onClick={() => { setCurrentRun(run); setRunLines([]); setView('run'); }} variant="outline" className="rounded-xl font-black h-12 px-6 hover:bg-slate-900 hover:text-white transition-all">
                    Continue Execution <ChevronRight size={18} className="ml-2" />
                 </Button>
              </Card>
           ))}
        </div>
      </div>
    </div>
  );
};
