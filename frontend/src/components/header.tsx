import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Bell, 
  Search, 
  ChevronDown, 
  LogOut, 
  Settings, 
  UserCircle, 
  CheckCircle2, 
  AlertCircle,
  FileText,
  Clock,
  Briefcase
} from 'lucide-react';
import { cn } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client, setAccessToken } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Notification } from '../types/erp';

interface HeaderProps {
  title: string;
  userName: string;
  userRole: string;
  avatarUrl: string;
  onLogout?: () => void;
  onNavigate?: (tab: string) => void;
  isImpersonated?: boolean;
}

export const Header = ({ title, userName, userRole, avatarUrl, onLogout, onNavigate, isImpersonated }: HeaderProps) => {
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [notifications, setNotifications] = useState<Notification[]>([]);

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 60000); // Polling every minute
    return () => clearInterval(interval);
  }, []);

  const fetchNotifications = async () => {
    try {
      const response = await client.get(ENDPOINTS.NOTIFICATIONS.LIST);
      setNotifications(response.data);
    } catch (error) {
      console.error('Failed to fetch notifications');
    }
  };

  const markRead = async (id: number) => {
    try {
      await client.post(ENDPOINTS.NOTIFICATIONS.MARK_READ(id));
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n));
    } catch (error) {
      toast.error('Failed to mark notification as read');
    }
  };

  const markAllRead = async () => {
    try {
      await client.post(ENDPOINTS.NOTIFICATIONS.MARK_ALL_READ);
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
      toast.success('All notifications marked as read');
    } catch (error) {
      toast.error('Failed to mark all as read');
    }
  };

  const unreadCount = (notifications || []).filter(n => !n.is_read).length;

  const handleNotificationClick = (n: Notification) => {
    if (!n.is_read) markRead(n.id);
    if (n.resource_type === 'leave') onNavigate?.('leave');
    else if (n.resource_type === 'task') onNavigate?.('tasks');
    else if (n.resource_type === 'timesheet') onNavigate?.('timesheet');
    else if (n.resource_type === 'payroll') onNavigate?.('payroll');
    setShowNotifications(false);
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.toLowerCase().includes('task')) onNavigate?.('tasks');
    else if (searchQuery.toLowerCase().includes('log') || searchQuery.toLowerCase().includes('hour')) onNavigate?.('worklog');
    else if (searchQuery.toLowerCase().includes('leave')) onNavigate?.('leave');
    else if (searchQuery.toLowerCase().includes('setting')) onNavigate?.('admin');
    else toast?.info?.("Search Result", { description: "Navigating to relevant operational module..." });
  };

  const handleStopImpersonation = async () => {
    try {
      const response = await client.post(ENDPOINTS.AUTH.STOP_IMPERSONATION);
      const { access_token, refresh_token } = response.data;
      setAccessToken(access_token);
      localStorage.setItem('refresh_token', refresh_token);
      toast.success("Returned to Super Admin profile");
      window.location.href = '/admin';
    } catch (error) {
      toast.error("Failed to stop impersonation");
    }
  };

  return (
    <header className="bg-white border-b border-[#E5E7EB] flex flex-col sticky top-0 z-40 shadow-sm transition-all">
      {isImpersonated && (
        <div className="bg-amber-600 text-white px-10 py-2 flex items-center justify-between text-[10px] font-black uppercase tracking-[0.2em]">
           <div className="flex items-center gap-3">
              <span className="flex h-2 w-2 rounded-full bg-white animate-pulse" />
              Viewing as {userName} ({userRole})
           </div>
           <button 
             onClick={handleStopImpersonation}
             className="bg-white/20 hover:bg-white/30 px-3 py-1 rounded-lg border border-white/30 transition-colors"
           >
             Return to Admin Auth
           </button>
        </div>
      )}
      <div className="h-20 flex items-center justify-between px-10">
        <div className="flex items-center gap-6">
          <h1 className="text-xl font-black text-[#0F172A] tracking-tighter uppercase whitespace-nowrap">{title}</h1>
          <div className="h-6 w-px bg-slate-200 hidden md:block" />
          <form onSubmit={handleSearch} className="relative hidden lg:block">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#94A3B8]" />
            <>
              <input
                type="text"
                list="search-suggestions"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search (tasks, logs, leave, admin)..."
                className="pl-12 pr-4 py-2.5 bg-[#F8FAFC] border border-[#E5E7EB] rounded-xl text-xs font-bold text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-blue-600/10 w-80 transition-all focus:w-96 placeholder:uppercase placeholder:tracking-widest"
              />
              <datalist id="search-suggestions">
                <option value="Tasks & Subtasks" />
                <option value="Worklogs & History" />
                <option value="Timesheet Audit" />
                <option value="Leave Balance" />
                <option value="System Administration" />
                <option value="Executive Insights" />
              </datalist>
            </>
          </form>
        </div>

        <div className="flex items-center space-x-6">
          <div className="relative">
            <button 
              onClick={() => setShowNotifications(!showNotifications)}
              className={cn(
                "relative p-3 text-[#64748B] hover:bg-slate-50 rounded-xl transition-all border border-transparent",
                showNotifications && "bg-slate-50 border-slate-200 text-[#2563EB]"
              )}
            >
              <Bell className="w-5 h-5" />
              {unreadCount > 0 && (
                <span className="absolute top-2 right-2 w-2.5 h-2.5 bg-red-600 border-2 border-white rounded-full"></span>
              )}
            </button>

            <AnimatePresence>
              {showNotifications && (
                <motion.div
                  initial={{ opacity: 0, y: 15, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 15, scale: 0.95 }}
                  className="absolute right-0 mt-3 w-96 bg-white border border-[#E5E7EB] rounded-2xl shadow-2xl overflow-hidden py-0 z-50"
                >
                  <div className="px-6 py-5 border-b border-[#E5E7EB] flex items-center justify-between bg-slate-50/50">
                    <span className="font-black text-xs text-[#0F172A] uppercase tracking-widest">Notification Center</span>
                    {unreadCount > 0 && (
                      <button 
                        onClick={markAllRead}
                        className="text-[10px] text-blue-600 font-black uppercase tracking-widest hover:underline"
                      >
                        Mark all read
                      </button>
                    )}
                  </div>
                  <div className="max-h-[400px] overflow-y-auto">
                    {notifications.length > 0 ? (
                      notifications.map((n) => (
                        <div 
                          key={n.id} 
                          onClick={() => handleNotificationClick(n)}
                          className={cn(
                            "px-6 py-5 hover:bg-slate-50 cursor-pointer transition-colors border-b border-[#F1F5F9] last:border-0 group",
                            !n.is_read && "bg-blue-50/30"
                          )}
                        >
                          <div className="flex gap-4">
                            <div className={cn(
                              "w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-transform group-hover:scale-110",
                              n.resource_type === 'payroll' ? "bg-green-50 text-green-600" : 
                              n.resource_type === 'leave' ? "bg-amber-50 text-amber-600" : 
                              "bg-blue-50 text-blue-600"
                            )}>
                              {n.resource_type === 'payroll' ? <FileText size={18} /> : 
                               n.resource_type === 'leave' ? <AlertCircle size={18} /> : 
                               <Bell size={18} />}
                            </div>
                            <div className="flex-1">
                              <div className="flex justify-between items-start gap-2">
                                <p className="text-sm font-black text-[#0F172A] tracking-tight group-hover:text-blue-600 transition-colors">{n.title}</p>
                                {!n.is_read && <div className="w-2 h-2 bg-blue-600 rounded-full shrink-0" />}
                              </div>
                              <p className="text-xs text-[#64748B] mt-1 font-medium leading-relaxed">{n.message}</p>
                              <p className="text-[10px] text-[#94A3B8] font-black uppercase mt-2 flex items-center gap-1.5">
                                <Clock size={10} /> {new Date(n.created_at).toLocaleDateString()}
                              </p>
                            </div>
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="px-6 py-10 text-center">
                        <p className="text-xs text-[#64748B] font-bold uppercase tracking-widest">No notifications yet</p>
                      </div>
                    )}
                  </div>
                  <button 
                     onClick={() => onNavigate?.('dashboard')}
                     className="w-full py-4 text-[10px] font-black text-[#64748B] hover:text-[#0F172A] bg-slate-50/50 border-t border-[#E5E7EB] uppercase tracking-[0.2em] transition-colors"
                  >
                    View Operational Overview
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <div className="relative flex items-center space-x-4 border-l border-[#E5E7EB] pl-6">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-black text-[#0F172A] tracking-tight">{userName}</p>
              <p className="text-[10px] text-[#64748B] font-bold uppercase tracking-widest mt-1">{userRole}</p>
            </div>
            <button 
              onClick={() => setShowProfileMenu(!showProfileMenu)}
              className="flex items-center space-x-2 group focus:outline-none"
            >
              <div className={cn(
                "w-11 h-11 rounded-xl overflow-hidden border-2 transition-all shadow-sm",
                showProfileMenu ? "border-blue-600 ring-4 ring-blue-50" : "border-slate-100 group-hover:border-blue-600"
              )}>
                <img src={avatarUrl} alt={userName} className="w-full h-full object-cover" />
              </div>
              <ChevronDown className={cn("w-4 h-4 text-[#64748B] transition-transform duration-300", showProfileMenu && "rotate-180")} />
            </button>

            <AnimatePresence>
              {showProfileMenu && (
                <motion.div
                  initial={{ opacity: 0, y: 15, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 15, scale: 0.95 }}
                  className="absolute right-0 top-full mt-3 w-64 bg-white border border-[#E5E7EB] rounded-2xl shadow-2xl overflow-hidden py-1 z-50"
                >
                  <div className="px-6 py-5 border-b border-[#E5E7EB] bg-slate-50/50">
                    <p className="text-sm font-black text-[#0F172A] tracking-tight">{userName}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <div className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
                      <p className="text-[9px] text-[#64748B] font-black uppercase tracking-widest">Session Active</p>
                    </div>
                  </div>
                  
                  <div className="p-2 space-y-1">
                    <button 
                      onClick={() => { onNavigate?.('profile'); setShowProfileMenu(false); }}
                      className="w-full flex items-center px-4 py-3 text-xs font-black text-[#334155] hover:bg-blue-50 hover:text-blue-600 rounded-xl transition-all uppercase tracking-widest"
                    >
                      <UserCircle className="w-4 h-4 mr-3 opacity-70" />
                      My Identity
                    </button>
                    <button 
                      onClick={() => { onNavigate?.('admin'); setShowProfileMenu(false); }}
                      className="w-full flex items-center px-4 py-3 text-xs font-black text-[#334155] hover:bg-blue-50 hover:text-blue-600 rounded-xl transition-all uppercase tracking-widest"
                    >
                      <Settings className="w-4 h-4 mr-3 opacity-70" />
                      System Access
                    </button>
                    
                    <div className="h-px bg-slate-100 my-2 mx-2" />
                    
                    <button 
                      onClick={() => { onLogout?.(); setShowProfileMenu(false); }}
                      className="w-full flex items-center px-4 py-3 text-xs font-black text-red-600 hover:bg-red-50 rounded-xl transition-all uppercase tracking-widest"
                    >
                      <LogOut className="w-4 h-4 mr-3 opacity-70" />
                      Terminate Session
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </header>
  );
};
