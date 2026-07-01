import React, { useState } from 'react';
import { 
  Users, 
  Search, 
  Filter, 
  Plus, 
  Eye, 
  Edit2, 
  ArrowLeft,
  ArrowRight,
  Mail,
  Phone,
  MapPin,
  Briefcase,
  Building2,
  Calendar,
  CreditCard,
  ShieldCheck,
  FileText,
  Clock,
  ChevronRight,
  TrendingUp,
  AlertCircle,
  FileUp,
  CheckCircle2,
  History,
  DollarSign,
  Laptop,
  Monitor,
  HardDrive,
  Trash2,
  MoreVertical,
  UserCheck,
  Fingerprint,
  ChevronDown
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Input } from './ui/input';

export const AttendanceManagement = () => {
  const [mode, setMode] = useState<'Office' | 'Remote' | 'On-site' | 'Others'>('Office');
  const [remarks, setRemarks] = useState('');
  const [hasCheckedIn, setHasCheckedIn] = useState(false);

  const handleCheckIn = () => {
    if (mode === 'Others' && !remarks) {
      toast.error("Remarks compulsory for 'Others' mode.");
      return;
    }
    setHasCheckedIn(true);
    toast.success("Attendance Marked Successfully", {
      description: `Mode: ${mode} • Geo-location Verified • Time: ${new Date().toLocaleTimeString()}`
    });
  };

  return (
    <div className="p-8 space-y-8 max-w-[1200px] mx-auto animate-in fade-in duration-500">
      <div className="text-center space-y-2 mb-10">
        <h2 className="text-4xl font-black text-[#0F172A] tracking-tighter uppercase">Professional Presence</h2>
        <p className="text-[#64748B] font-bold uppercase tracking-widest text-xs">Mark attendance to synchronize operational worklogs</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Card className="p-8 border-slate-200 shadow-xl bg-white space-y-8">
           <div className="space-y-4">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Select Deployment Mode</label>
              <div className="grid grid-cols-2 gap-4">
                 {['Office', 'Remote', 'On-site', 'Others'].map((m: any) => (
                    <button
                      key={m}
                      onClick={() => setMode(m)}
                      className={cn(
                        "p-5 rounded-2xl border-2 transition-all flex flex-col items-center gap-2",
                        mode === m 
                          ? "border-blue-600 bg-blue-50 text-blue-700 shadow-md" 
                          : "border-slate-100 bg-slate-50 text-slate-400 hover:border-blue-200"
                      )}
                    >
                       <Badge variant="neutral" className={cn("text-[8px] font-black uppercase", mode === m ? "bg-blue-600 text-white" : "bg-white")}>{m}</Badge>
                       <span className="text-xs font-black uppercase tracking-widest">{m}</span>
                    </button>
                 ))}
              </div>
           </div>

           {mode === 'Others' && (
              <div className="space-y-2 animate-in slide-in-from-top duration-300">
                 <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Compulsory Remarks</label>
                 <Input 
                   placeholder="Specify reason for Others mode (e.g. Travel, Client Site B)..." 
                   value={remarks}
                   onChange={(e) => setRemarks(e.target.value)}
                   className="h-14 font-bold rounded-2xl border-slate-200 focus:ring-blue-600/10"
                 />
              </div>
           )}

           <div className="p-6 bg-slate-50 rounded-2xl border border-slate-100 space-y-4">
              <div className="flex items-center justify-between">
                 <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Geo-fencing Status</span>
                 <Badge variant="success" className="bg-green-100 text-green-700 border-none font-black text-[9px] uppercase px-3">Inside Perimeter</Badge>
              </div>
              <div className="flex items-center gap-3 text-[10px] font-bold text-slate-500 uppercase">
                 <MapPin size={14} className="text-blue-600" /> Site-HQ Kolkata (Verified)
              </div>
           </div>

           <Button 
             disabled={hasCheckedIn}
             onClick={handleCheckIn}
             className={cn(
               "w-full h-16 font-black uppercase tracking-widest text-sm shadow-xl transition-all",
               hasCheckedIn ? "bg-green-600 opacity-80" : "bg-blue-600 hover:bg-blue-700 shadow-blue-600/20"
             )}
           >
              {hasCheckedIn ? (
                <span className="flex items-center gap-2"><CheckCircle2 size={20} /> Attendance Verified</span>
              ) : (
                <span className="flex items-center gap-2"><Fingerprint size={20} /> Mark Attendance Now</span>
              )}
           </Button>
        </Card>

        <Card className="p-8 border-slate-200 shadow-sm bg-white space-y-8 h-fit">
           <h4 className="text-xl font-black text-[#0F172A] tracking-tight uppercase flex items-center gap-2">
              <History size={18} className="text-blue-600" /> Recent Attendance History
           </h4>
           <div className="space-y-4">
              {[
                { date: 'Feb 08, 2026', mode: 'Office', time: '09:15 AM', status: 'Present' },
                { date: 'Feb 07, 2026', mode: 'Remote', time: '09:30 AM', status: 'Present' },
                { date: 'Feb 06, 2026', mode: 'Others', time: '10:45 AM', status: 'Late' },
              ].map((log, i) => (
                <div key={i} className="flex items-center justify-between p-4 bg-slate-50 rounded-2xl border border-slate-100 group hover:border-blue-200 transition-all">
                   <div>
                      <p className="text-sm font-black text-[#0F172A]">{log.date}</p>
                      <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">{log.mode} • In: {log.time}</p>
                   </div>
                   <Badge variant={log.status === 'Present' ? 'success' : 'warning'} className="text-[9px] font-black uppercase px-3">{log.status}</Badge>
                </div>
              ))}
           </div>
           <Button variant="ghost" className="w-full font-black text-[10px] uppercase tracking-widest text-slate-400 hover:text-blue-600">Request Correction <ArrowRight size={14} className="ml-2" /></Button>
        </Card>
      </div>

      <Card className="p-8 bg-slate-900 border-none rounded-[32px] overflow-hidden relative shadow-2xl">
         <div className="relative z-10 flex flex-col md:flex-row items-center justify-between gap-8">
            <div className="flex items-center gap-6">
               <div className="w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center">
                  <ShieldCheck size={32} className="text-amber-400" />
               </div>
               <div>
                  <h4 className="text-2xl font-black text-white tracking-tighter uppercase">Audit Policy Enforcement</h4>
                  <p className="text-slate-400 text-[11px] font-bold uppercase tracking-widest mt-1">All attendance logs are recorded with immutable geo-spatial identifiers.</p>
               </div>
            </div>
            <Button variant="outline" className="border-white/10 text-white hover:bg-white/10 font-black uppercase text-[10px] tracking-widest h-12 px-10 transition-all">View Audit Trail</Button>
         </div>
      </Card>
    </div>
  );
};
