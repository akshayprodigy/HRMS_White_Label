import React, { useState, useEffect } from 'react';
import { 
  CheckCircle2, 
  XCircle, 
  HelpCircle, 
  MessageSquare, 
  DollarSign, 
  TrendingUp,
  AlertTriangle,
  Clock,
  User,
  ExternalLink,
  Filter,
  Search,
  Briefcase
} from 'lucide-react';
import { Card, Button, Badge, Input, cn } from './ui-elements';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { toast } from 'sonner@2.0.3';

interface CostChangeRequest {
  id: number;
  project_id: number;
  project_name?: string;
  baseline_amount: number;
  proposed_amount: number;
  percent_change: number;
  reason: string;
  impact: string;
  status: 'submitted' | 'approved' | 'rejected' | 'needs_clarification';
  created_at: string;
  created_by_name?: string;
}

export const CostApprovalsView = () => {
  const [requests, setRequests] = useState<CostChangeRequest[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRequest, setSelectedRequest] = useState<CostChangeRequest | null>(null);
  const [remarks, setRemarks] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);

  const fetchInbox = async () => {
    try {
      setIsLoading(true);
      const response = await client.get(ENDPOINTS.PROJECTS.COST_APPROVAL_INBOX);
      setRequests(response.data);
    } catch (error) {
      console.error("Failed to fetch cost approvals:", error);
      toast.error("Failed to load approval queue");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchInbox();
  }, []);

  const handleAction = async (status: CostChangeRequest['status']) => {
    if (!selectedRequest) return;
    try {
      setIsProcessing(true);
      await client.post(ENDPOINTS.PROJECTS.COST_APPROVAL_ACTION(selectedRequest.id), {
        status,
        remarks
      });
      toast.success(`Request ${status} successfully`);
      setSelectedRequest(null);
      setRemarks('');
      fetchInbox();
    } catch (error: any) {
      toast.error(error.response?.data?.error?.message || "Action failed");
    } finally {
      setIsProcessing(false);
    }
  };

  const filteredRequests = requests.filter(r => 
    r.reason.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (r.project_name?.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm font-black text-slate-400 uppercase tracking-widest">Synchronizing Queue...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-8 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Cost Approval Engine</h2>
          <p className="text-[11px] font-bold text-slate-400 uppercase tracking-[0.2em] mt-1">Delegated Authority Processing Queue</p>
        </div>
        <div className="flex gap-3">
          <div className="relative group">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-600 transition-colors" size={18} />
            <Input 
              placeholder="FILTER BY PROJECT OR REASON..." 
              className="pl-12 w-64 md:w-80 h-12 bg-white border-slate-200 focus:border-blue-600 font-bold text-xs"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <Button variant="outline" className="h-12 w-12 p-0 border-slate-200">
             <Filter size={18} className="text-slate-600" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Inbox List */}
        <div className="lg:col-span-1 space-y-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Active Requests ({filteredRequests.length})</h3>
          </div>
          
          <div className="space-y-3 overflow-y-auto max-h-[calc(100vh-250px)] pr-2 custom-scrollbar">
            {filteredRequests.map((req) => (
              <Card 
                key={req.id} 
                className={cn(
                  "p-5 cursor-pointer transition-all border-slate-200 hover:border-blue-400 group relative overflow-hidden",
                  selectedRequest?.id === req.id ? "border-blue-600 bg-blue-50/30 ring-1 ring-blue-600/10" : "bg-white"
                )}
                onClick={() => setSelectedRequest(req)}
              >
                {req.percent_change > 0.1 && (
                  <div className="absolute top-0 right-0 px-2 py-0.5 bg-red-600 text-[8px] font-black text-white uppercase tracking-tighter rounded-bl-lg">
                    High Variance
                  </div>
                )}
                <div className="space-y-3">
                  <div className="flex justify-between items-start">
                    <div className="flex items-center gap-2">
                       <Briefcase size={12} className="text-blue-600" />
                       <span className="text-[10px] font-black text-slate-500 uppercase tracking-tight truncate max-w-[150px]">
                         {req.project_name || `Project #${req.project_id}`}
                       </span>
                    </div>
                    <span className="text-[10px] font-bold text-slate-400">{new Date(req.created_at).toLocaleDateString()}</span>
                  </div>
                  
                  <h4 className="text-sm font-black text-[#0F172A] leading-tight line-clamp-2 uppercase">
                    {req.reason}
                  </h4>
                  
                  <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                    <div className="flex items-center gap-1.5">
                      <TrendingUp size={14} className={req.percent_change > 0 ? "text-red-500" : "text-green-500"} />
                      <span className={cn("text-sm font-black", req.percent_change > 0 ? "text-red-600" : "text-green-600")}>
                        {(req.percent_change * 100).toFixed(1)}%
                      </span>
                    </div>
                    <Badge variant="neutral" className="text-[8px] px-2 py-0">SUBMITTED</Badge>
                  </div>
                </div>
              </Card>
            ))}
            
            {filteredRequests.length === 0 && (
              <div className="p-12 text-center border-2 border-dashed border-slate-200 rounded-2xl">
                 <CheckCircle2 size={32} className="mx-auto text-slate-200 mb-4" />
                 <p className="text-xs font-black text-slate-400 uppercase tracking-widest leading-relaxed">No pending cost actions<br/>at this authorization level</p>
              </div>
            )}
          </div>
        </div>

        {/* Detail View */}
        <div className="lg:col-span-2">
          {selectedRequest ? (
            <Card className="p-0 border-slate-200 h-full flex flex-col overflow-hidden bg-white shadow-xl shadow-slate-200/50">
               <div className="p-8 border-b border-slate-100 bg-slate-50/50">
                  <div className="flex justify-between items-start mb-6">
                    <div>
                      <Badge variant="info" className="mb-2 text-[9px] px-3 font-black tracking-widest uppercase">Request #{selectedRequest.id}</Badge>
                      <h3 className="text-2xl font-black text-[#0F172A] tracking-tight uppercase leading-none">{selectedRequest.reason}</h3>
                      <div className="flex items-center gap-3 mt-3">
                         <div className="flex items-center gap-1.5">
                            <Briefcase size={14} className="text-blue-600" />
                            <span className="text-xs font-bold text-slate-600 uppercase tracking-tight">{selectedRequest.project_name || `Project #${selectedRequest.project_id}`}</span>
                         </div>
                         <div className="w-1 h-1 bg-slate-300 rounded-full" />
                         <div className="flex items-center gap-1.5">
                            <User size={14} className="text-slate-400" />
                            <span className="text-xs font-bold text-slate-600 uppercase tracking-tight">{selectedRequest.created_by_name || 'System User'}</span>
                         </div>
                      </div>
                    </div>
                    <div className="text-right">
                       <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Time Elapsed</p>
                       <p className="text-sm font-black text-slate-700 tracking-tight flex items-center justify-end gap-1.5">
                         <Clock size={14} className="text-blue-600" />
                         2.5 HOURS
                       </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                     <div className="p-6 bg-white rounded-2xl border border-slate-200 shadow-sm">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.15em] mb-2">Baseline</p>
                        <h4 className="text-2xl font-black text-[#0F172A]">₹{selectedRequest.baseline_amount.toLocaleString('en-IN')}</h4>
                     </div>
                     <div className="p-6 bg-white rounded-2xl border border-blue-200 shadow-sm ring-1 ring-blue-600/5 transition-transform hover:scale-[1.02]">
                        <p className="text-[10px] font-black text-blue-500 uppercase tracking-[0.15em] mb-2">Proposed</p>
                        <h4 className="text-2xl font-black text-blue-600">₹{selectedRequest.proposed_amount.toLocaleString('en-IN')}</h4>
                     </div>
                     <div className="p-6 rounded-2xl border border-red-100 bg-red-50/50 shadow-sm">
                        <p className="text-[10px] font-black text-red-500 uppercase tracking-[0.15em] mb-2">Variance</p>
                        <div className="flex items-center gap-2">
                           <h4 className="text-2xl font-black text-red-600">{(selectedRequest.percent_change * 100).toFixed(1)}%</h4>
                           {selectedRequest.percent_change > 0.1 && <AlertTriangle size={18} className="text-red-500" />}
                        </div>
                     </div>
                  </div>
               </div>

               <div className="p-8 flex-1 space-y-8 overflow-y-auto">
                  <div className="space-y-4">
                     <h4 className="text-[11px] font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
                        <ExternalLink size={14} /> IMPACT ANALYSIS
                     </h4>
                     <div className="p-6 bg-slate-50 rounded-2xl border border-slate-100 italic font-medium text-slate-600 leading-relaxed">
                        "{selectedRequest.impact}"
                     </div>
                  </div>

                  <div className="space-y-4">
                     <h4 className="text-[11px] font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
                        <MessageSquare size={14} /> ADJUDICATION REMARKS
                     </h4>
                     <textarea 
                        className="w-full h-32 p-6 bg-white border-2 border-slate-100 rounded-2xl focus:border-blue-600 focus:outline-none font-bold text-sm tracking-tight placeholder:italic transition-all"
                        placeholder="PROVIDE JUSTIFICATION FOR APPROVAL OR REJECTION..."
                        value={remarks}
                        onChange={(e) => setRemarks(e.target.value)}
                     />
                  </div>
               </div>

               <div className="p-8 border-t border-slate-100 flex items-center justify-between bg-slate-50/30">
                  <div className="flex gap-3">
                     <Button 
                        variant="outline" 
                        className="h-12 px-8 font-black uppercase text-xs tracking-widest border-amber-200 text-amber-600 hover:bg-amber-50"
                        onClick={() => handleAction('needs_clarification')}
                        disabled={isProcessing}
                     >
                        <HelpCircle size={18} className="mr-2" /> RE-ROUTE FOR CLARIFICATION
                     </Button>
                  </div>
                  <div className="flex gap-4">
                     <Button 
                        variant="outline" 
                        className="h-12 px-8 font-black uppercase text-xs tracking-widest border-red-200 text-red-600 hover:bg-red-50"
                        onClick={() => handleAction('rejected')}
                        disabled={isProcessing}
                     >
                        <XCircle size={18} className="mr-2" /> DENY REQUEST
                     </Button>
                     <Button 
                        className="h-12 px-12 font-black uppercase text-xs tracking-widest bg-blue-600 shadow-lg shadow-blue-500/20 hover:scale-[1.02] active:scale-[0.98]"
                        onClick={() => handleAction('approved')}
                        disabled={isProcessing}
                     >
                        <CheckCircle2 size={18} className="mr-2" /> AUTHORIZE EXPENDITURE
                     </Button>
                  </div>
               </div>
            </Card>
          ) : (
            <div className="h-full flex flex-col items-center justify-center p-20 text-center space-y-6">
               <div className="w-24 h-24 bg-slate-50 rounded-full flex items-center justify-center border border-slate-100">
                  <DollarSign size={40} className="text-slate-200" />
               </div>
               <div className="space-y-2 max-w-sm">
                  <h3 className="text-xl font-black text-slate-300 uppercase tracking-tight">System Waiting</h3>
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-widest leading-relaxed">
                    Select a budget change request from the queue to initiate authorization procedures
                  </p>
               </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
