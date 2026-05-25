import React, { useState, useEffect } from 'react';
import { 
  Users, 
  Briefcase, 
  Search, 
  Filter, 
  ChevronRight, 
  Clock, 
  CheckCircle2, 
  XCircle, 
  AlertCircle,
  MoreVertical,
  Plus,
  ArrowRight,
  UserPlus,
  FileBadge,
  MessageSquare,
  CalendarDays,
  Target,
  X,
  PlusCircle
} from 'lucide-react';
import { Card, Button, Badge, cn, Input } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { recruitmentApi } from '../api/recruitment';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

export const RecruitmentHR = () => {
  const [requisitions, setRequisitions] = useState<any[]>([]);
  const [candidates, setCandidates] = useState<any[]>([]);
  const [interviews, setInterviews] = useState<any[]>([]);
  const [departments, setDepartments] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isApplicantModalOpen, setIsApplicantModalOpen] = useState(false);
  const [isInterviewModalOpen, setIsInterviewModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState<any>(null);

  // Form state
  const [formData, setFormData] = useState({
    title: '',
    department: '',
    positions_count: 1,
    priority: 'medium',
    employment_type: 'full_time',
    reason: '',
    budget_range: '',
    job_description: '',
    qualifications: ''
  });

  const [applicantData, setApplicantData] = useState({
    requisition_id: '',
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    source: '',
    experience_years: 0
  });

  const [interviewData, setInterviewData] = useState({
    interview_type: 'technical',
    scheduled_at: '',
    interviewer_id: 1,
    notes: ''
  });

  useEffect(() => {
    fetchData();
    const loadDepartments = async () => {
      try {
        const res = await client.get(ENDPOINTS.ADMIN.DEPARTMENTS);
        setDepartments((res as any).data || []);
      } catch (err) {
        console.error('Failed to load departments', err);
      }
    };
    loadDepartments();
  }, []);

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const [reqsResponse, appsResponse] = await Promise.all([
        recruitmentApi.getRequisitions(),
        recruitmentApi.getApplicants()
      ]);
      setRequisitions(reqsResponse.data);
      setCandidates(appsResponse.data);
      
      // Extract interviews
      const allInterviews = appsResponse.data?.flatMap((a: any) => 
        (a.interviews || []).map((i: any) => ({ ...i, applicant: a }))
      ) || [];
      setInterviews(allInterviews.sort((a: any, b: any) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()));
    } catch (error) {
      console.error('Error fetching recruitment data:', error);
      toast.error('Failed to load recruitment data');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const response = await recruitmentApi.createRequisition(formData);
      // Automatically submit for approval
      await recruitmentApi.submitRequisition(response.data.id);
      toast.success('Requisition created and submitted for approval');
      setIsModalOpen(false);
      fetchData();
      setFormData({
        title: '',
        department: '',
        positions_count: 1,
        priority: 'medium',
        employment_type: 'full_time',
        reason: '',
        budget_range: '',
        job_description: '',
        qualifications: ''
      });
    } catch (error: any) {
      toast.error('Failed to create requisition');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleApplicantSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await recruitmentApi.createApplicant({
        ...applicantData,
        requisition_id: parseInt(applicantData.requisition_id)
      });
      toast.success('Candidate added successfully');
      setIsApplicantModalOpen(false);
      fetchData();
      setApplicantData({
        requisition_id: '',
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        source: '',
        experience_years: 0
      });
    } catch (error: any) {
      toast.error('Failed to add candidate', {
        description: error.response?.data?.error?.message || 'Check all fields'
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleInterviewSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCandidate) return;
    
    setIsSubmitting(true);
    try {
      await recruitmentApi.scheduleInterview({
        ...interviewData,
        applicant_id: selectedCandidate.id
      });
      toast.success('Interview scheduled successfully');
      setIsInterviewModalOpen(false);
      fetchData();
    } catch (error: any) {
      toast.error('Failed to schedule interview');
    } finally {
      setIsSubmitting(false);
    }
  };

  const timelineStages = [
    { id: 1, label: 'Applications', count: candidates.length, icon: Users, color: 'bg-blue-600' },
    { id: 2, label: 'Screening', count: candidates.filter(c => c.status === 'screening').length, icon: Filter, color: 'bg-purple-600' },
    { id: 3, label: 'Interviewing', count: candidates.filter(c => c.status === 'interview').length, icon: Clock, color: 'bg-amber-600' },
    { id: 4, label: 'Offer Phase', count: candidates.filter(c => c.status === 'offered').length, icon: FileBadge, color: 'bg-green-600' }
  ];

  return (
    <div className="p-8 space-y-8 max-w-[1600px] mx-auto animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Talent Acquisition</h2>
          <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Strategic Recruitment Pipeline & Candidate Lifecycle Tracking</p>
        </div>
        <div className="flex gap-3">
           <Button 
            onClick={() => setIsApplicantModalOpen(true)}
            variant="outline"
            className="font-black h-12 px-6 uppercase text-[10px] tracking-widest border-blue-200 text-blue-600"
           >
              <UserPlus className="w-4 h-4 mr-2" /> Add Candidate
           </Button>
           <Button 
            onClick={() => setIsModalOpen(true)}
            className="font-black h-12 px-6 uppercase text-[10px] tracking-widest bg-blue-600 shadow-lg shadow-blue-600/20"
           >
              <Plus className="w-4 h-4 mr-2" /> New Requisition
           </Button>
        </div>
      </div>

      {isApplicantModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <Card
            className="w-full max-w-lg bg-white shadow-2xl rounded-3xl overflow-hidden animate-in zoom-in duration-200"
            style={{
              maxHeight: "70vh",
              overflowY: "auto",
              overscrollBehavior: "contain",
              WebkitOverflowScrolling: "touch",
            }}
          >
            <div className="p-6 border-b border-slate-50 flex justify-between items-center">
              <div>
                <h2 className="text-xl font-black text-[#0F172A] tracking-tighter">ADD NEW CANDIDATE</h2>
                <p className="text-[9px] font-black text-[#64748B] uppercase tracking-widest mt-0.5">Application will be linked to an approved requisition</p>
              </div>
              <button onClick={() => setIsApplicantModalOpen(false)} className="p-2 hover:bg-slate-100 rounded-xl transition-all font-black">
                <X size={20} />
              </button>
            </div>
            
            <form onSubmit={handleApplicantSubmit} className="p-6 space-y-4">
              <div className="space-y-1.5">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Target Requisition</label>
                <select 
                  required
                  className="w-full h-11 bg-slate-50 border border-slate-100 rounded-xl px-4 text-xs font-black uppercase outline-none focus:ring-2 focus:ring-blue-500/10"
                  value={applicantData.requisition_id}
                  onChange={e => setApplicantData({...applicantData, requisition_id: e.target.value})}
                >
                  <option value="">Select Requisition</option>
                  {requisitions.filter(r => r.status === 'approved').map(r => (
                    <option key={r.id} value={r.id}>{r.req_id} - {r.title}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Input 
                  label="FIRST NAME" 
                  required 
                  value={applicantData.first_name}
                  onChange={e => setApplicantData({...applicantData, first_name: e.target.value})}
                />
                <Input 
                  label="LAST NAME" 
                  required 
                  value={applicantData.last_name}
                  onChange={e => setApplicantData({...applicantData, last_name: e.target.value})}
                />
              </div>

              <Input 
                label="EMAIL ADDRESS" 
                type="email"
                required 
                value={applicantData.email}
                onChange={e => setApplicantData({...applicantData, email: e.target.value})}
                placeholder="candidate@example.com"
              />

              <div className="grid grid-cols-2 gap-4">
                <Input 
                  label="PHONE" 
                  value={applicantData.phone}
                  onChange={e => setApplicantData({...applicantData, phone: e.target.value})}
                />
                <div className="space-y-1.5">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Experience (Years)</label>
                  <input 
                    type="number" 
                    step="0.5"
                    className="w-full h-11 bg-slate-50 border border-slate-100 rounded-xl px-4 text-xs font-black outline-none focus:ring-2 focus:ring-blue-500/10"
                    value={applicantData.experience_years}
                    onChange={e => setApplicantData({...applicantData, experience_years: parseFloat(e.target.value)})}
                  />
                </div>
              </div>

              <Input 
                label="SOURCE" 
                value={applicantData.source}
                onChange={e => setApplicantData({...applicantData, source: e.target.value})}
                placeholder="e.g. LinkedIn, Referral"
              />

              <Button 
                type="submit" 
                disabled={isSubmitting}
                className="w-full h-12 bg-blue-600 hover:bg-blue-700 font-black uppercase text-xs tracking-widest shadow-xl shadow-blue-600/20"
              >
                {isSubmitting ? 'Adding...' : 'Add to Pipeline'}
              </Button>
            </form>
          </Card>
        </div>
      )}

      {isModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <Card
            className="w-full max-w-2xl bg-white shadow-2xl rounded-3xl overflow-hidden animate-in zoom-in duration-200"
            style={{
              maxHeight: "70vh",
              overflowY: "auto",
              overscrollBehavior: "contain",
              WebkitOverflowScrolling: "touch",
            }}
          >
            <div className="p-6 border-b border-slate-50 flex justify-between items-center">
              <div>
                <h2 className="text-xl font-black text-[#0F172A] tracking-tighter">RAISE MANPOWER REQUISITION</h2>
                <p className="text-[9px] font-black text-[#64748B] uppercase tracking-widest mt-0.5">Approval workflow will be initiated automatically</p>
              </div>
              <button onClick={() => setIsModalOpen(false)} className="p-2 hover:bg-slate-100 rounded-xl transition-all font-black">
                <X size={20} />
              </button>
            </div>
            
            <form onSubmit={handleSubmit} className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
              <div className="grid grid-cols-2 gap-4">
                <Input 
                  label="JOB TITLE" 
                  required 
                  value={formData.title}
                  onChange={e => setFormData({...formData, title: e.target.value})}
                  placeholder="e.g. Senior Frontend Engineer"
                />
                <div className="space-y-1.5">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Department *</label>
                  <select
                    required
                    disabled={departments.length === 0}
                    className="w-full h-11 bg-slate-50 border border-slate-100 rounded-xl px-4 text-xs font-black uppercase outline-none focus:ring-2 focus:ring-blue-500/10 disabled:opacity-60"
                    value={formData.department}
                    onChange={e => setFormData({...formData, department: e.target.value})}
                  >
                    <option value="">
                      {departments.length === 0 ? 'No departments — add in System Administration' : 'Select department...'}
                    </option>
                    {departments.map((d: any) => (
                      <option key={d.id} value={d.name}>{d.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Positions</label>
                  <input 
                    type="number" 
                    min="1"
                    className="w-full h-11 bg-slate-50 border border-slate-100 rounded-xl px-4 text-xs font-black outline-none focus:ring-2 focus:ring-blue-500/10"
                    value={formData.positions_count}
                    onChange={e => setFormData({...formData, positions_count: parseInt(e.target.value)})}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Priority</label>
                  <select 
                    className="w-full h-11 bg-slate-50 border border-slate-100 rounded-xl px-4 text-xs font-black uppercase outline-none focus:ring-2 focus:ring-blue-500/10"
                    value={formData.priority}
                    onChange={e => setFormData({...formData, priority: e.target.value})}
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Type</label>
                  <select 
                    className="w-full h-11 bg-slate-50 border border-slate-100 rounded-xl px-4 text-xs font-black uppercase outline-none focus:ring-2 focus:ring-blue-500/10"
                    value={formData.employment_type}
                    onChange={e => setFormData({...formData, employment_type: e.target.value})}
                  >
                    <option value="full_time">Full Time</option>
                    <option value="part_time">Part Time</option>
                    <option value="contract">Contract</option>
                    <option value="intern">Intern</option>
                  </select>
                </div>
              </div>

              <Input 
                label="BUDGET RANGE" 
                value={formData.budget_range}
                onChange={e => setFormData({...formData, budget_range: e.target.value})}
                placeholder="e.g. ₹100k - ₹120k"
              />

              <div className="space-y-1.5">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Job Description</label>
                <textarea 
                  required
                  rows={3}
                  className="w-full bg-slate-50 border border-slate-100 rounded-xl p-4 text-xs font-bold outline-none focus:ring-2 focus:ring-blue-500/10"
                  value={formData.job_description}
                  onChange={e => setFormData({...formData, job_description: e.target.value})}
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Qualifications</label>
                <textarea 
                  rows={2}
                  className="w-full bg-slate-50 border border-slate-100 rounded-xl p-4 text-xs font-bold outline-none focus:ring-2 focus:ring-blue-500/10"
                  value={formData.qualifications}
                  onChange={e => setFormData({...formData, qualifications: e.target.value})}
                />
              </div>

              <Button 
                type="submit" 
                disabled={isSubmitting}
                className="w-full h-12 bg-blue-600 hover:bg-blue-700 font-black uppercase text-xs tracking-widest shadow-xl shadow-blue-600/20"
              >
                {isSubmitting ? 'Processing...' : 'Submit Requisition'}
              </Button>
            </form>
          </Card>
        </div>
      )}

      {isInterviewModalOpen && selectedCandidate && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <Card
            className="w-full max-w-lg bg-white shadow-2xl rounded-3xl overflow-hidden animate-in zoom-in duration-200"
            style={{
              maxHeight: "70vh",
              overflowY: "auto",
              overscrollBehavior: "contain",
              WebkitOverflowScrolling: "touch",
            }}
          >
            <div className="p-6 border-b border-slate-50 flex justify-between items-center">
              <div>
                <h2 className="text-xl font-black text-[#0F172A] tracking-tighter uppercase whitespace-nowrap overflow-hidden text-ellipsis max-w-[300px]">
                  Schedule: {selectedCandidate.first_name} {selectedCandidate.last_name}
                </h2>
                <p className="text-[9px] font-black text-[#64748B] uppercase tracking-widest mt-0.5">Moving to next stage in pipeline</p>
              </div>
              <button onClick={() => setIsInterviewModalOpen(false)} className="p-2 hover:bg-slate-100 rounded-xl transition-all font-black">
                <X size={20} />
              </button>
            </div>
            
            <form onSubmit={handleInterviewSubmit} className="p-6 space-y-4">
              <div className="space-y-1.5">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Interview Type</label>
                <select 
                  className="w-full h-11 bg-slate-50 border border-slate-100 rounded-xl px-4 text-xs font-black uppercase outline-none focus:ring-2 focus:ring-blue-500/10"
                  value={interviewData.interview_type}
                  onChange={e => setInterviewData({...interviewData, interview_type: e.target.value})}
                >
                  <option value="technical">Technical Round</option>
                  <option value="hr">HR Round</option>
                  <option value="manager">Managerial Round</option>
                  <option value="ceo">CEO/Leadership Round</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Date & Time</label>
                <input 
                  type="datetime-local" 
                  required
                  className="w-full h-11 bg-slate-50 border border-slate-100 rounded-xl px-4 text-xs font-black outline-none focus:ring-2 focus:ring-blue-500/10"
                  value={interviewData.scheduled_at}
                  onChange={e => setInterviewData({...interviewData, scheduled_at: e.target.value})}
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Notes / Briefing</label>
                <textarea 
                  rows={3}
                  className="w-full bg-slate-50 border border-slate-100 rounded-xl p-4 text-xs font-bold outline-none focus:ring-2 focus:ring-blue-500/10"
                  value={interviewData.notes}
                  onChange={e => setInterviewData({...interviewData, notes: e.target.value})}
                  placeholder="Points for the interviewer..."
                />
              </div>

              <Button 
                type="submit" 
                disabled={isSubmitting}
                className="w-full h-12 bg-blue-600 hover:bg-blue-700 font-black uppercase text-xs tracking-widest shadow-xl shadow-blue-600/20"
              >
                {isSubmitting ? 'Scheduling...' : 'Confirm Schedule'}
              </Button>
            </form>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        {timelineStages.map((stage) => (
          <Card key={stage.id} className="p-6 border-slate-200 shadow-sm hover:shadow-md transition-all group">
            <div className="flex items-center gap-4">
              <div className={cn("w-12 h-12 rounded-2xl flex items-center justify-center text-white shadow-lg", stage.color)}>
                <stage.icon size={20} />
              </div>
              <div>
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{stage.label}</p>
                <h3 className="text-2xl font-black text-[#0F172A] tracking-tighter">{stage.count}</h3>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
         {/* Candidate Pipeline Timeline View */}
         <Card className="lg:col-span-2 p-8 border-slate-200 shadow-sm space-y-8">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <h4 className="text-xl font-black text-[#0F172A] tracking-tight flex items-center gap-2">
                    <Target className="text-blue-600" /> Active Hiring Pipeline
                </h4>
                <div className="flex items-center gap-2">
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400" />
                        <input 
                            type="text"
                            placeholder="SEARCH CANDIDATES..."
                            className="h-9 pl-9 pr-4 rounded-xl bg-slate-50 border border-slate-100 text-[9px] font-black tracking-widest uppercase outline-none focus:ring-2 focus:ring-blue-500/10 w-48"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                        />
                    </div>
                </div>
            </div>

            <div className="space-y-6">
               {candidates.filter(c => 
                 `${c.first_name} ${c.last_name}`.toLowerCase().includes(searchQuery.toLowerCase()) ||
                 c.requisition?.title?.toLowerCase().includes(searchQuery.toLowerCase())
               ).length === 0 ? (
                 <div className="p-12 text-center">
                    <Users size={48} className="mx-auto text-slate-200 mb-4" />
                    <p className="text-sm font-black text-slate-400 uppercase tracking-widest">No candidates found matching search</p>
                 </div>
               ) : candidates
                  .filter(c => 
                    `${c.first_name} ${c.last_name}`.toLowerCase().includes(searchQuery.toLowerCase()) ||
                    c.requisition?.title?.toLowerCase().includes(searchQuery.toLowerCase())
                  )
                  .map((candidate) => (
                  <div key={candidate.id} className="group relative">
                    {/* Vertical Timeline Line */}
                    <div className="flex gap-6 items-start">
                        <div className="flex flex-col items-center">
                            <div className={cn(
                                "w-12 h-12 rounded-2xl flex items-center justify-center border-4 border-white shadow-md z-10 transition-all group-hover:bg-blue-600 group-hover:text-white",
                                candidate.status === 'screening' ? 'bg-amber-50 text-amber-600' : 'bg-blue-50 text-blue-600'
                            )}>
                                <span className="text-sm font-black">{candidate.first_name?.charAt(0)}</span>
                            </div>
                            <div className="w-0.5 h-full bg-slate-100 group-last:bg-transparent min-h-[60px]" />
                        </div>
                        
                        <Card className="flex-1 p-6 border-slate-100 hover:border-blue-200 hover:shadow-lg transition-all mb-4 relative overflow-hidden bg-slate-50 group-hover:bg-white">
                            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                                <div>
                                    <div className="flex items-center gap-2">
                                        <h5 className="text-lg font-black text-[#0F172A] tracking-tight">{candidate.first_name} {candidate.last_name}</h5>
                                        <Badge variant="neutral" className="text-[8px] font-black tracking-widest uppercase bg-slate-200">CAN-{candidate.id}</Badge>
                                    </div>
                                    <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest mt-0.5">{candidate.requisition?.title || 'Unknown Role'}</p>
                                    
                                    <div className="flex items-center gap-4 mt-4">
                                        <div className="flex items-center gap-1.5">
                                            <CalendarDays size={12} className="text-slate-400" />
                                            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{new Date(candidate.created_at).toLocaleDateString()}</span>
                                        </div>
                                        <div className="flex items-center gap-1.5">
                                            <UserPlus size={12} className="text-slate-400" />
                                            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Source: {candidate.source || 'Direct'}</span>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex flex-col md:items-end gap-3">
                                    <div className="flex items-center gap-2">
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Current Phase</p>
                                        <Badge className="text-[10px] px-3 font-black uppercase tracking-widest bg-blue-100 text-blue-700">
                                            {candidate.status}
                                        </Badge>
                                    </div>
                                    <div className="flex gap-2">
                                        <Button variant="ghost" size="sm" className="h-8 font-black uppercase text-[9px] tracking-widest text-slate-400 hover:text-blue-600">Details</Button>
                                        <Button 
                                            size="sm" 
                                            className="h-8 px-4 font-black uppercase text-[9px] tracking-widest bg-blue-600 hover:bg-blue-700"
                                            onClick={() => {
                                                setSelectedCandidate(candidate);
                                                setIsInterviewModalOpen(true);
                                            }}
                                        >
                                            Next Step
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        </Card>
                    </div>
                  </div>
               ))}
            </div>
            <Button variant="ghost" className="w-full font-black text-[10px] uppercase tracking-widest text-slate-400 hover:text-blue-600 mt-4">Load More Candidates <ArrowRight size={14} className="ml-2" /></Button>
         </Card>

         {/* Right Sidebar Widgets */}
         <div className="space-y-8">
            <Card className="p-8 border-slate-200 shadow-sm">
                <h4 className="text-lg font-black text-[#0F172A] tracking-tight mb-6 flex items-center gap-2">
                    <CalendarDays className="text-blue-600" /> Upcoming Interviews
                </h4>
                <div className="space-y-6">
                    {interviews.length === 0 ? (
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest text-center py-4">No interviews scheduled</p>
                    ) : interviews.slice(0, 5).map((item, i) => (
                        <div key={i} className="flex gap-4 p-4 rounded-2xl bg-slate-50 border border-slate-100 hover:border-blue-200 transition-all cursor-pointer">
                            <div className="w-12 h-12 bg-white rounded-xl shadow-sm flex flex-col items-center justify-center">
                                <span className="text-[10px] font-black text-blue-600 uppercase">
                                    {new Date(item.scheduled_at).toLocaleString('default', { month: 'short' })}
                                </span>
                                <span className="text-sm font-black text-[#0F172A]">
                                    {new Date(item.scheduled_at).getDate()}
                                </span>
                            </div>
                            <div>
                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                                    {new Date(item.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                </p>
                                <p className="text-sm font-black text-[#0F172A]">{item.applicant?.first_name} {item.applicant?.last_name}</p>
                                <p className="text-[9px] font-bold text-blue-600 uppercase tracking-widest">{item.interview_type} Round</p>
                            </div>
                        </div>
                    ))}
                </div>
                <Button variant="outline" className="w-full mt-6 h-11 border-slate-200 font-black uppercase text-[10px] tracking-widest">Full Schedule</Button>
            </Card>

            <Card className="p-8 border-slate-200 bg-slate-900 text-white overflow-hidden relative group">
                <div className="relative z-10">
                    <h4 className="text-lg font-black tracking-tight mb-2">Job Requisitions</h4>
                    <p className="text-slate-400 text-[10px] font-bold uppercase tracking-widest mb-6">Open positions status</p>
                    <div className="space-y-4">
                        <div className="flex justify-between items-center text-[10px] font-black uppercase tracking-widest">
                            <span>Open</span>
                            <span>{requisitions.filter(r => r.status === 'approved').length} Roles</span>
                        </div>
                        <div className="h-1 bg-white/10 rounded-full overflow-hidden">
                            <div className="h-full bg-blue-600" style={{ width: `${(requisitions.filter(r => r.status === 'approved').length / (requisitions.length || 1)) * 100}%` }} />
                        </div>
                        <div className="flex justify-between items-center text-[10px] font-black uppercase tracking-widest pt-2">
                            <span>Pending</span>
                            <span>{requisitions.filter(r => r.status === 'pending').length} Roles</span>
                        </div>
                        <div className="h-1 bg-white/10 rounded-full overflow-hidden">
                            <div className="h-full bg-amber-500" style={{ width: `${(requisitions.filter(r => r.status === 'pending').length / (requisitions.length || 1)) * 100}%` }} />
                        </div>
                    </div>
                    <Button className="mt-8 w-full bg-blue-600 hover:bg-blue-700 border-none font-black uppercase text-[10px] tracking-widest h-11 shadow-xl shadow-blue-600/20">Post New Role</Button>
                </div>
                <Briefcase size={140} className="absolute -right-8 -bottom-8 opacity-5 transform group-hover:rotate-12 transition-transform duration-700" />
            </Card>
         </div>
      </div>
    </div>
  );
};
