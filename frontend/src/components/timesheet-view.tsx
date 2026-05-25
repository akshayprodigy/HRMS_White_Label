import React, { useState, useEffect } from 'react';
import {
  CheckCircle2,
  Clock,
  Calendar as CalendarIcon,
  AlertCircle,
  ChevronRight,
  ChevronLeft,
  Search,
  Send,
  Printer,
  FileCheck,
  History,
  Download,
  MoreVertical,
  Plus,
  FileText,
  ExternalLink
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { ManualEntryModal } from './manual-entry-modal';

export const TimesheetView = () => {
    const [timesheetData, setTimesheetData] = useState<any>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [range, setRange] = useState<'weekly' | 'monthly'>('weekly');
    const [isManualModalOpen, setIsManualModalOpen] = useState(false);

    useEffect(() => {
        fetchTimesheetData();
    }, [range]);

    const fetchTimesheetData = async () => {
        setIsLoading(true);
        try {
            const response = await client.get(ENDPOINTS.TIMESHEET.MY, {
                params: { range }
            });
            setTimesheetData(response.data);
        } catch (error) {
            toast.error("Failed to fetch timesheet data");
        } finally {
            setIsLoading(false);
        }
    };

    const getRangeString = () => {
        if (!timesheetData) return "";
        const start = new Date(timesheetData.start_date);
        const end = new Date(timesheetData.end_date);
        const options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
        return `${start.toLocaleDateString(undefined, options)} - ${end.toLocaleDateString(undefined, options)}, ${start.getFullYear()}`;
    };

    const formatDuration = (seconds: number) => {
        const hrs = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        return `${hrs}h ${mins}m`;
    };

    if (isLoading && !timesheetData) {
        return <div className="p-8 text-center uppercase tracking-widest font-black text-slate-400">Loading Timesheet Protocol...</div>;
    }

    const dailyStats = timesheetData?.daily_data || [];
    const totalHours = (timesheetData?.total_seconds || 0) / 3600;

  const handlePrint = () => {
    toast.success("Preparing PDF document...");
    setTimeout(() => {
      window.print();
    }, 500);
  };

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto animate-in fade-in duration-500 print:p-0">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 print:hidden">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter">My Timesheets</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Formal verification of operational hours for payroll processing</p>
        </div>
        <div className="flex gap-3">
           <Button 
            variant="primary" 
            className="font-black h-12 px-6 uppercase text-[10px] tracking-widest"
            onClick={() => setIsManualModalOpen(true)}
           >
              <Plus className="w-4 h-4 mr-2" /> Log Manual Time
           </Button>
           <Button 
            variant="outline" 
            className="font-black h-12 px-6 uppercase text-[10px] tracking-widest border-slate-200"
            onClick={handlePrint}
           >
              <Printer className="w-4 h-4 mr-2" /> Print Timesheet
           </Button>
        </div>
      </div>

      <div className="flex items-center justify-between bg-white p-6 rounded-2xl border border-slate-200 shadow-sm print:border-none print:shadow-none">
        <div className="flex items-center gap-6">
           <div className="flex bg-slate-100 p-1 rounded-xl print:hidden">
              <button 
                onClick={() => setRange('weekly')} 
                className={cn("px-4 py-2 font-black text-[10px] tracking-widest rounded-lg transition-all", range === 'weekly' ? "bg-white text-blue-600 shadow-sm" : "text-slate-500 hover:text-slate-700")}
                >
                    WEEKLY
                </button>
              <button 
                onClick={() => setRange('monthly')} 
                className={cn("px-4 py-2 font-black text-[10px] tracking-widest rounded-lg transition-all", range === 'monthly' ? "bg-white text-blue-600 shadow-sm" : "text-slate-500 hover:text-slate-700")}
                >
                    MONTHLY
                </button>
           </div>
           <div>
              <h3 className="text-lg font-black text-[#0F172A] tracking-tight">{getRangeString()}</h3>
           </div>
        </div>
        <div className="flex items-center gap-10">
           <div className="text-right">
              <p className="text-[10px] font-black text-[#94A3B8] uppercase tracking-widest">Total Hours</p>
              <p className="text-2xl font-black text-blue-600 tabular-nums">{totalHours.toFixed(1)}h</p>
           </div>
           <div className="h-10 w-px bg-slate-100" />
           <div className="text-right">
              <p className="text-[10px] font-black text-[#94A3B8] uppercase tracking-widest">Status</p>
              <Badge variant="success" className="h-8 px-4 font-black text-[10px] uppercase">
                 Verified
              </Badge>
           </div>
        </div>
      </div>

      <div className={cn("grid gap-4", range === 'weekly' ? "grid-cols-1 md:grid-cols-7" : "grid-cols-1 md:grid-cols-4 lg:grid-cols-6")}>
        {dailyStats.map((dayData: any, idx: number) => {
          const date = new Date(dayData.day);
          const dayName = date.toLocaleDateString(undefined, { weekday: 'short' });
          const dayDate = date.toLocaleDateString(undefined, { day: '2-digit', month: 'short' });
          
          return (
            <Card key={idx} className={cn(
              "p-6 bg-white border-slate-200 hover:border-blue-600 transition-all text-center group",
              dayData.total_seconds === 0 ? "bg-slate-50/50 grayscale opacity-60" : ""
            )}>
              <p className="text-[10px] font-black text-[#64748B] uppercase tracking-widest mb-1">{dayName}</p>
              <p className="text-xs font-black text-[#0F172A] mb-4">{dayDate}</p>
              <div className="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center mx-auto mb-4 group-hover:bg-blue-600 transition-all">
                 <span className="text-xl font-black text-blue-600 group-hover:text-white uppercase">
                    {formatDuration(dayData.total_seconds)}
                 </span>
              </div>
              <p className="text-[10px] font-bold text-[#94A3B8] uppercase tracking-widest truncate">
                {dayData.entries.length > 0 ? `${dayData.entries.length} Sessions` : 'No Activity'}
              </p>
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 bg-white border-slate-200 overflow-hidden">
           <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <h3 className="font-black text-[#0F172A] tracking-tight flex items-center gap-2">
                 <History size={18} className="text-blue-600" /> Activity Breakdown
              </h3>
              <span className="text-[10px] font-black text-[#94A3B8] uppercase tracking-widest">Week Summary</span>
           </div>
           <div className="p-0 overflow-x-auto">
              <table className="w-full text-left">
                 <thead>
                    <tr className="border-b border-slate-50">
                       <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Date</th>
                       <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Project</th>
                       <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Task Name</th>
                       <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest">Duration</th>
                       <th className="px-6 py-4 text-[9px] font-black text-slate-400 uppercase tracking-widest text-right">Action</th>
                    </tr>
                 </thead>
                 <tbody className="divide-y divide-slate-50">
                    {dailyStats.flatMap((day: any) => 
                      day.entries.map((entry: any) => ({
                        ...entry,
                        day: day.day
                      }))
                    ).length > 0 ? (
                      dailyStats.flatMap((day: any) => 
                        day.entries.map((entry: any) => ({
                          ...entry,
                          day: day.day
                        }))
                      ).map((item: any, i: number) => (
                        <tr key={i} className="hover:bg-slate-50/50 transition-colors">
                            <td className="px-6 py-4 text-[10px] font-black text-slate-400 uppercase whitespace-nowrap">
                              {new Date(item.day).toLocaleDateString(undefined, { day: '2-digit', month: 'short' })}
                            </td>
                            <td className="px-6 py-4 text-[10px] font-black text-blue-600 uppercase whitespace-nowrap">{item.project_name || 'General'}</td>
                            <td className="px-6 py-4 text-xs font-bold text-slate-600 truncate max-w-[200px]">{item.manual_reason || 'Recorded via Timer'}</td>
                            <td className="px-6 py-4 text-xs font-black text-slate-900 tabular-nums">{formatDuration(item.duration_seconds)}</td>
                            <td className="px-6 py-4 text-right">
                              <button className="text-slate-300 hover:text-slate-600 transition-colors print:hidden"><MoreVertical size={16} /></button>
                            </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={5} className="px-6 py-12 text-center text-slate-400 italic text-sm">
                          No activity recorded for this period.
                        </td>
                      </tr>
                    )}
                 </tbody>
              </table>
           </div>
        </Card>

        <PolicyRemindersCard />
      </div>

      <ManualEntryModal 
        isOpen={isManualModalOpen} 
        onClose={() => setIsManualModalOpen(false)} 
        onSuccess={fetchTimesheetData}
      />

      <style dangerouslySetInnerHTML={{ __html: `
        @media print {
          body { background: white !important; }
          .print\\:hidden { display: none !important; }
          .print\\:border-none { border: none !important; }
          .print\\:shadow-none { shadow: none !important; }
          main { margin-left: 0 !important; }
          header, footer, aside { display: none !important; }
        }
      `}} />
    </div>
  );
};


// ─── Dynamic Policy Reminders Card ──────────────────────────

const PolicyRemindersCard = () => {
    const [policies, setPolicies] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        (async () => {
            try {
                const res = await client.get(ENDPOINTS.HR.POLICIES);
                setPolicies(res.data);
            } catch {
                // silently fail — this is a secondary card
            } finally {
                setLoading(false);
            }
        })();
    }, []);

    const handleViewPdf = async (policy: any) => {
        try {
            const res = await client.get(ENDPOINTS.HR.POLICY_DOWNLOAD(policy.id), { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
            window.open(url, '_blank');
        } catch {
            toast.error("Failed to open policy");
        }
    };

    const colors = [
        { bg: 'bg-amber-50', border: 'border-amber-100', title: 'text-amber-800', text: 'text-amber-700', icon: 'text-amber-500' },
        { bg: 'bg-blue-50', border: 'border-blue-100', title: 'text-blue-800', text: 'text-blue-700', icon: 'text-blue-500' },
        { bg: 'bg-emerald-50', border: 'border-emerald-100', title: 'text-emerald-800', text: 'text-emerald-700', icon: 'text-emerald-500' },
        { bg: 'bg-purple-50', border: 'border-purple-100', title: 'text-purple-800', text: 'text-purple-700', icon: 'text-purple-500' },
        { bg: 'bg-rose-50', border: 'border-rose-100', title: 'text-rose-800', text: 'text-rose-700', icon: 'text-rose-500' },
    ];

    return (
        <Card className="bg-white border-slate-200 overflow-hidden print:hidden">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                <h3 className="font-black text-[#0F172A] tracking-tight flex items-center gap-2">
                    <AlertCircle size={18} className="text-amber-500" /> Policy Reminders
                </h3>
                <Badge variant="neutral" className="bg-slate-100 text-slate-500 text-[8px] font-black uppercase">
                    {policies.length} {policies.length === 1 ? 'Policy' : 'Policies'}
                </Badge>
            </div>
            <div className="p-6 space-y-3">
                {loading ? (
                    <div className="py-8 text-center text-slate-400 text-xs font-bold uppercase tracking-widest animate-pulse">Loading policies...</div>
                ) : policies.length === 0 ? (
                    <div className="py-8 text-center text-slate-300 text-xs font-bold uppercase tracking-widest">No active policies</div>
                ) : (
                    policies.map((policy, idx) => {
                        const c = colors[idx % colors.length];
                        return (
                            <button
                                key={policy.id}
                                onClick={() => handleViewPdf(policy)}
                                className={`w-full p-4 ${c.bg} border ${c.border} rounded-2xl flex items-center gap-4 hover:opacity-80 transition-all text-left group`}
                            >
                                <FileText size={18} className={c.icon} />
                                <div className="flex-1 min-w-0">
                                    <p className={`text-[10px] font-black ${c.title} uppercase tracking-widest`}>{policy.title}</p>
                                    {policy.description && (
                                        <p className={`text-[10px] font-medium ${c.text} leading-relaxed mt-0.5 truncate`}>{policy.description}</p>
                                    )}
                                </div>
                                <ExternalLink size={14} className={`${c.icon} opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0`} />
                            </button>
                        );
                    })
                )}
            </div>
        </Card>
    );
};
