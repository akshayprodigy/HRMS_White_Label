import React from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { Clock, Play, Pause, Square } from "lucide-react";
import { toast } from "sonner";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?:
    | "primary"
    | "secondary"
    | "outline"
    | "ghost"
    | "danger";
  size?: "sm" | "md" | "lg" | "icon";
  isLoading?: boolean;
}

export const Button = ({
  className,
  variant = "primary",
  size = "md",
  isLoading,
  children,
  ...props
}: ButtonProps) => {
  const variants = {
    primary:
      "bg-[#2563EB] text-white hover:bg-[#1D4ED8] focus:ring-4 focus:ring-[#2563EB]/25",
    secondary: "bg-[#F1F5F9] text-[#0F172A] hover:bg-[#E2E8F0]",
    outline:
      "border border-[#D1D5DB] bg-transparent text-[#374151] hover:bg-[#F1F5F9] focus:ring-4 focus:ring-[#2563EB]/10",
    ghost:
      "text-[#64748B] hover:bg-[#F1F5F9] hover:text-[#0F172A]",
    danger:
      "bg-[#DC2626] text-white hover:bg-[#B91C1C] focus:ring-4 focus:ring-[#DC2626]/25",
  };

  const sizes = {
    sm: "px-3 py-1.5 text-sm rounded-md",
    md: "px-4 py-2 rounded-lg font-medium",
    lg: "px-6 py-3 rounded-xl font-semibold",
    icon: "p-2 rounded-lg",
  };

  return (
    <button
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap flex-shrink-0 leading-normal overflow-visible transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed",
        variants[variant],
        sizes[size],
        className,
      )}
      disabled={isLoading}
      {...props}
    >
      {isLoading ? (
        <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : null}
      {children}
    </button>
  );
};

export const Card = ({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "bg-white border border-[#E5E7EB] rounded-xl overflow-hidden shadow-sm",
      className,
    )}
    {...props}
  >
    {children}
  </div>
);

export const Badge = ({
  children,
  variant = "info",
  className,
}: {
  children: React.ReactNode;
  variant?:
    | "success"
    | "warning"
    | "error"
    | "info"
    | "neutral";
  className?: string;
}) => {
  const variants = {
    success: "bg-[#DCFCE7] text-[#16A34A]",
    warning: "bg-[#FEF3C7] text-[#D97706]",
    error: "bg-[#FEE2E2] text-[#DC2626]",
    info: "bg-[#DBEAFE] text-[#2563EB]",
    neutral: "bg-[#F1F5F9] text-[#64748B]",
  };

  return (
    <span
      className={cn(
        "px-2.5 py-0.5 rounded-full text-xs font-medium",
        variants[variant],
        className,
      )}
    >
      {children}
    </span>
  );
};

// ---------------------------------------------------------------------------
// Section M shared primitives — extracted from ~25 duplicated call sites so
// every workspace renders the same visual for the same intent.
// ---------------------------------------------------------------------------

/** Normalize any axios/backend error into a user-safe string. */
export const errMsg = (e: any, fallback: string): string => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    return d.map((x: any) => x?.msg || JSON.stringify(x)).join('; ');
  }
  if (d && typeof d === 'object') return d.message || JSON.stringify(d);
  return e?.message || fallback;
};

/** Indian-grouping ₹ formatter over paise. `null`/`undefined` → em-dash. */
export const fmtInr = (
  paise?: number | null,
  opts: { showZero?: boolean; symbol?: boolean } = {},
): string => {
  const { showZero = true, symbol = true } = opts;
  if (paise == null) return '—';
  if (paise === 0 && !showZero) return '';
  const rupees = paise / 100;
  const num = rupees.toLocaleString('en-IN', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  return symbol ? '₹' + num : num;
};

/** ISO date string → dd MMM yyyy (Indian convention). */
export const fmtDate = (iso?: string | Date | null): string => {
  if (!iso) return '—';
  const d = typeof iso === 'string' ? new Date(iso) : iso;
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  });
};

/** Consistent empty-state placeholder. */
export const EmptyState: React.FC<{
  title?: string;
  hint?: string;
  className?: string;
  children?: React.ReactNode;
}> = ({ title = 'Nothing to show', hint, className, children }) => (
  <div
    className={cn(
      'py-10 px-4 text-center rounded-lg border border-dashed border-slate-200 bg-slate-50/50',
      className,
    )}
  >
    <div className="text-sm text-slate-600 font-medium">{title}</div>
    {hint && <div className="text-xs text-slate-500 mt-1">{hint}</div>}
    {children && <div className="mt-3">{children}</div>}
  </div>
);

/** Consistent loading placeholder. Use `inline` for row-level spinners. */
export const Loading: React.FC<{
  label?: string;
  inline?: boolean;
  className?: string;
}> = ({ label = 'Loading…', inline = false, className }) => (
  <div
    role="status"
    aria-live="polite"
    className={cn(
      inline
        ? 'text-xs text-slate-400 inline-flex items-center gap-2'
        : 'text-center text-slate-400 py-8',
      className,
    )}
  >
    {label}
  </div>
);

/**
 * Status chip with a canonical color map. Pass a raw status string —
 * green for approved/success/reimbursed/completed; red for
 * rejected/failed/dead_letter/cancelled; blue for pending/queued/
 * submitted/running; amber for warn/skipped_*; slate for the rest.
 */
export type StatusTone = 'good' | 'bad' | 'info' | 'warn' | 'neutral';

const STATUS_TONE_MAP: Record<string, StatusTone> = {
  approved: 'good', sent: 'good', reimbursed: 'good',
  pushed_to_payroll: 'good', completed: 'good', success: 'good',
  active: 'good', released: 'good', ready: 'good',
  rejected: 'bad', failed: 'bad', dead_letter: 'bad',
  cancelled: 'bad', blocked: 'bad',
  pending: 'info', queued: 'info', submitted: 'info', running: 'info',
  draft: 'info', in_progress: 'info', launched: 'info',
  warn: 'warn', warning: 'warn', at_risk: 'warn',
  skipped_pref: 'warn', skipped_quiet: 'warn', flagged: 'warn',
};

const TONE_CLASS: Record<StatusTone, string> = {
  good: 'bg-green-100 text-green-700 border-green-300',
  bad: 'bg-red-100 text-red-700 border-red-300',
  info: 'bg-blue-100 text-blue-700 border-blue-300',
  warn: 'bg-amber-100 text-amber-700 border-amber-300',
  neutral: 'bg-slate-100 text-slate-600 border-slate-300',
};

export const statusTone = (s?: string | null): StatusTone => {
  if (!s) return 'neutral';
  return STATUS_TONE_MAP[String(s).toLowerCase()] || 'neutral';
};

export const StatusChip: React.FC<{
  status?: string | null;
  label?: string;
  tone?: StatusTone;
  className?: string;
}> = ({ status, label, tone, className }) => {
  const t = tone ?? statusTone(status);
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border capitalize',
        TONE_CLASS[t],
        className,
      )}
    >
      {label ?? status ?? '—'}
    </span>
  );
};

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement> & {
    label?: string;
    error?: string;
  }
>(({ label, error, className, ...props }, ref) => (
  <div className="space-y-1.5 w-full">
    {label && (
      <label className="text-sm font-medium text-[#374151] block">
        {label}
      </label>
    )}
    <input
      ref={ref}
      className={cn(
        "w-full bg-white border border-[#D1D5DB] rounded-lg px-4 py-2 text-[#0F172A] placeholder:text-[#94A3B8] outline-none transition-all duration-200",
        "focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB]",
        error &&
          "border-[#DC2626] focus:border-[#DC2626] focus:ring-[#DC2626]",
        className,
      )}
      {...props}
    />
    {error && (
      <p className="text-xs text-[#DC2626] mt-1">{error}</p>
    )}
  </div>
));
Input.displayName = "Input";

export const TimerCard = ({
  title = "Deliverable Session Tracker",
  onStop,
  onStart,
  onPause,
  onResume,
  projectOptions = [],
  taskOptions = {},
  className,
  headerActions,
  footerStats,
  status: externalStatus,
}: {
  title?: string;
  onStop?: (duration: number, project: string, task: string) => void;
  onStart?: (project: string, task: string) => Promise<void>;
  onPause?: () => Promise<void>;
  onResume?: () => Promise<void>;
  projectOptions?: { id: number | string, name: string }[];
  taskOptions?: Record<
    string,
    Array<string | { id: number | string; name: string }>
  >;
  className?: string;
  /** Extra controls rendered beside the status badge (e.g. Punch Out). */
  headerActions?: React.ReactNode;
  /** Real footer metrics (replaces the old hardcoded demo tiles). */
  footerStats?: { label: string; value: string; accent?: boolean }[];
  status?: {
    isActive: boolean;
    isPaused: boolean;
    seconds: number;
    project_id?: number | string;
    project?: string;
    task?: string;
    task_id?: number | string;
    task_label?: string;
  }
}) => {
  const [seconds, setSeconds] = React.useState(externalStatus?.seconds || 0);
  const [isActive, setIsActive] = React.useState(externalStatus?.isActive || false);
  const [isPaused, setIsPaused] = React.useState(externalStatus?.isPaused || false);
  const [project, setProject] = React.useState(externalStatus?.project_id?.toString() || "");
  const [task, setTask] = React.useState(
    externalStatus?.task_id?.toString() || externalStatus?.task || ""
  );

  const taskLabel = React.useMemo(() => {
    if (externalStatus?.task_label) return externalStatus.task_label;
    if (!task) return "";
    const options = taskOptions[project] || [];
    const match = options.find((opt) => {
      if (typeof opt === 'string') return opt === task;
      return opt.id?.toString() === task;
    });
    if (!match) return task;
    return typeof match === 'string' ? match : match.name;
  }, [externalStatus?.task_label, project, task, taskOptions]);

  React.useEffect(() => {
    if (projectOptions.length > 0 && !project && !externalStatus?.project_id) {
      const firstId = projectOptions[0]?.id;
      if (firstId !== undefined && firstId !== null) {
        setProject(firstId.toString());
      }
    }
  }, [projectOptions, project, externalStatus]);

  React.useEffect(() => {
    if (externalStatus) {
      setSeconds(externalStatus.seconds);
      setIsActive(externalStatus.isActive);
      setIsPaused(externalStatus.isPaused);
      if (externalStatus.project_id !== undefined && externalStatus.project_id !== null) {
        setProject(externalStatus.project_id.toString());
      }
      if (externalStatus.task_id !== undefined && externalStatus.task_id !== null) {
        setTask(externalStatus.task_id.toString());
      } else if (externalStatus.task) {
        setTask(externalStatus.task);
      }
    }
  }, [externalStatus]);

  React.useEffect(() => {
    let interval: any;
    if (isActive && !isPaused) {
      interval = setInterval(() => setSeconds(s => s + 1), 1000);
    }
    return () => clearInterval(interval);
  }, [isActive, isPaused]);

  const displayTime = () => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const handleStartInternal = async () => {
    if (!task && taskOptions[project] && taskOptions[project].length > 0) {
      toast.error("Task Selection Required");
      return;
    }
    
    if (onStart) {
      await onStart(project, task);
    } else {
      setIsActive(true);
      setIsPaused(false);
      toast.success("Timer Started", { 
        description: `Tracking: ${taskLabel || project}`,
        style: { background: "#2563EB", color: "#fff" }
      });
    }
  };

  const handlePauseResumeInternal = async () => {
    if (isPaused) {
      if (onResume) await onResume();
      else setIsPaused(false);
    } else {
      if (onPause) await onPause();
      else setIsPaused(true);
    }
  };

  const handleStopInternal = async () => {
    if (onStop) await onStop(seconds, project, task);
    if (!onStop) {
      setSeconds(0);
      setIsActive(false);
      setIsPaused(false);
      setTask("");
      toast.success("Worklog Recorded", { description: "Session synchronized with enterprise database." });
    }
  };

  return (
    <Card className={cn("p-10 bg-white border-slate-100 shadow-sm relative overflow-hidden flex flex-col justify-between min-h-[400px]", className)}>
      <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-[#2563EB]" />
      
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-8">
        <div className="flex flex-wrap items-center gap-4">
          <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center text-[#2563EB]">
            <Clock size={20} />
          </div>
          <h2 className="text-xl font-black text-[#0F172A] tracking-tight uppercase">{title}</h2>
          
          {projectOptions.length > 0 && (
            <div className="flex gap-3 ml-0 lg:ml-4">
              <select 
                value={project} 
                onChange={(e) => { setProject(e.target.value); setTask(""); }} 
                disabled={isActive}
                className="h-10 w-[200px] bg-slate-50 border border-slate-100 rounded-xl px-4 text-[10px] font-black uppercase tracking-widest text-slate-600 outline-none focus:ring-2 focus:ring-blue-500/10"
              >
                {projectOptions.map((p, idx) => (
                  <option key={p.id || idx} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>

              <select 
                value={task} 
                onChange={(e) => setTask(e.target.value)} 
                disabled={isActive}
                className="h-10 w-[200px] bg-slate-50 border border-slate-100 rounded-xl px-4 text-[10px] font-black uppercase tracking-widest text-slate-600 outline-none focus:ring-2 focus:ring-blue-500/10"
              >
                <option value="">Select Task</option>
                {(() => {
                  const list = taskOptions[project] || [];
                  if (list.length === 0) {
                    return <option value="" disabled>No tasks assigned</option>;
                  }
                  return list.map((t, idx) => {
                    const value = typeof t === 'string' ? t : t.id?.toString();
                    const label = typeof t === 'string' ? t : t.name;
                    return (
                      <option key={value || idx} value={value}>
                        {label}
                      </option>
                    );
                  });
                })()}
              </select>
            </div>
          )}
        </div>
        
        <div className="flex items-center gap-2 w-fit">
          {headerActions}
          <Badge variant="neutral" className="bg-slate-100 text-slate-500 font-black text-[10px] uppercase tracking-[0.2em] px-4 py-1.5 rounded-full border-none w-fit">
            {isActive ? (isPaused ? "PAUSED" : "ACTIVE") : "STANDBY"}
          </Badge>
        </div>
      </div>

      <div className="flex flex-col items-center justify-center flex-1 py-4">
        <div className={cn(
          "text-[100px] font-black leading-none tracking-tighter tabular-nums mb-10 transition-all duration-500",
          isActive && !isPaused ? "text-[#2563EB] scale-105 drop-shadow-[0_0_20px_rgba(37,99,235,0.2)]" : "text-slate-300"
        )}>
          {displayTime()}
        </div>
        
        <div className="flex gap-4">
          {!isActive ? (
            <Button 
              onClick={handleStartInternal}
              className="h-16 px-12 bg-[#2563EB] hover:bg-blue-700 text-white font-black uppercase text-[12px] tracking-widest rounded-2xl shadow-xl shadow-blue-600/20"
            >
              <Play size={20} className="mr-3 fill-current" /> Start Session
            </Button>
          ) : (
            <div className="flex gap-4">
              <Button 
                onClick={handlePauseResumeInternal}
                className="h-16 px-12 bg-slate-900 hover:bg-black text-white font-black uppercase text-[12px] tracking-widest rounded-2xl shadow-xl"
              >
                {isPaused ? <Play size={20} className="mr-3 fill-current" /> : <Pause size={20} className="mr-3 fill-current" />}
                {isPaused ? "Resume" : "Pause Session"}
              </Button>
              <Button 
                onClick={handleStopInternal}
                className="h-16 px-12 bg-red-600 hover:bg-red-700 text-white font-black uppercase text-[12px] tracking-widest rounded-2xl shadow-xl shadow-red-600/20"
              >
                <Square size={20} className="mr-3 fill-current" /> Stop & Sync
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="mt-8 pt-6 border-t border-slate-50 flex items-center justify-between">
        <div className="flex gap-12">
          {(footerStats || []).map((s, i) => (
            <div key={i}>
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">{s.label}</p>
              <span className={cn('text-xl font-black', s.accent ? 'text-[#2563EB]' : 'text-[#0F172A]')}>{s.value}</span>
            </div>
          ))}
        </div>
        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest italic">
          {isActive ? `Recording activity for: ${taskLabel || project}` : "Please select project and task to begin tracking."}
        </p>
      </div>
    </Card>
  );
};
