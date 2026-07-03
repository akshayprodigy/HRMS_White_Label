/**
 * Role-based landing dashboard.
 *
 * One component driven by the /dashboard payload — the backend decides
 * which widgets a user sees, this file just renders each widget by its
 * key. New widgets don't require a new page; they just need a renderer
 * entry in the WIDGET_RENDERERS map.
 *
 * Multi-role users get a role-switcher along the top; the current
 * selection is passed to the backend as the `dashboard` query param so
 * the assembled widget set matches the picked cockpit.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  RefreshCw, ChevronRight, AlertTriangle, CheckCircle2, XCircle,
  Clock, Target, Users, Banknote, Receipt, ClipboardCheck,
  TrendingUp, Trophy, Sparkles,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  Card, Button, Badge, cn, errMsg, fmtInr, EmptyState, Loading,
} from './ui-elements';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface WidgetMeta {
  key: string;
  title: string;
  category: 'action' | 'data' | 'analytic';
  scope: 'self' | 'team' | 'org';
  permission: string | null;
  drill: { route: string; params: Record<string, any> };
}

interface DashboardData {
  landing_dashboard: string;
  active_dashboard: string;
  available_dashboards: string[];
  role_names: string[];
  widgets: WidgetMeta[];
  payloads: Record<string, any>;
  pending_count: number;
}

interface RoleDashboardProps {
  onNavigate?: (tab: string, params?: Record<string, any>) => void;
  /** Render as a section inside My Workspace: compact chrome, no page
   * padding, and hidden entirely for single-role employees with
   * nothing pending (their personal widgets already live there). */
  embedded?: boolean;
}

const DASHBOARD_LABELS: Record<string, string> = {
  'employee-dashboard': 'Employee',
  'manager-dashboard': 'Manager',
  'hr-dashboard': 'HR',
  'finance-dashboard': 'Finance',
  'executive-dashboard': 'Executive',
};

// ---------------------------------------------------------------------------
// Widget renderers — one per key
// ---------------------------------------------------------------------------

const CountTile: React.FC<{
  count: number; label: string; tone?: 'action' | 'good' | 'warn' | 'neutral';
}> = ({ count, label, tone = 'neutral' }) => {
  const toneClass = {
    action: 'text-blue-700 bg-blue-50 border-blue-200',
    good:   'text-green-700 bg-green-50 border-green-200',
    warn:   'text-amber-700 bg-amber-50 border-amber-200',
    neutral:'text-slate-700 bg-slate-50 border-slate-200',
  }[tone];
  return (
    <div className={cn('rounded border px-3 py-2', toneClass)}>
      <div className="text-2xl font-semibold">{count}</div>
      <div className="text-[11px] uppercase tracking-wide">{label}</div>
    </div>
  );
};

const WidgetShell: React.FC<{
  meta: WidgetMeta;
  onDrill?: () => void;
  children?: React.ReactNode;
  headerRight?: React.ReactNode;
}> = ({ meta, onDrill, children, headerRight }) => {
  const iconByCategory = {
    action: <AlertTriangle size={14} className="text-amber-600" />,
    data:   <Sparkles size={14} className="text-blue-600" />,
    analytic: <TrendingUp size={14} className="text-purple-600" />,
  };
  return (
    <Card className="p-4 flex flex-col gap-2 min-h-[140px]">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          {iconByCategory[meta.category]}
          <div className="text-sm font-semibold text-slate-700">{meta.title}</div>
        </div>
        {headerRight}
      </div>
      <div className="flex-1">{children}</div>
      {onDrill && (
        <button
          onClick={onDrill}
          className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1 self-start"
        >
          Open <ChevronRight size={12} />
        </button>
      )}
    </Card>
  );
};

const R = {
  my_attendance_today(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="space-y-1 text-sm">
          <div>Date: <span className="font-medium">{p?.date}</span></div>
          <div className="flex items-center gap-2">
            <span>Punched in:</span>
            {p?.punched_in
              ? <Badge className="bg-green-100 text-green-700 border-green-300 border">Yes</Badge>
              : <Badge className="bg-red-100 text-red-700 border-red-300 border">No</Badge>}
          </div>
          <div className="flex items-center gap-2">
            <span>Punched out:</span>
            {p?.punched_out
              ? <Badge className="bg-green-100 text-green-700 border-green-300 border">Yes</Badge>
              : <Badge className="bg-slate-100 text-slate-600 border-slate-300 border">No</Badge>}
          </div>
        </div>
      </WidgetShell>
    );
  },

  my_leave_balance(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="text-3xl font-semibold">{p?.total_balance ?? 0}<span className="text-xs text-slate-500 ml-1">days</span></div>
        <div className="text-xs text-slate-500 mt-2 space-y-0.5">
          {(p?.types || []).slice(0, 3).map((t: any, i: number) => (
            <div key={i} className="flex justify-between">
              <span>{t.leave_type}</span>
              <span>{t.balance} / used {t.used}</span>
            </div>
          ))}
        </div>
      </WidgetShell>
    );
  },

  my_pending_actions(meta: WidgetMeta, p: any) {
    const bd = p?.breakdown || {};
    return (
      <WidgetShell meta={meta}>
        <CountTile count={p?.count || 0} label="items on you" tone="action" />
        <div className="text-xs text-slate-500 mt-2 space-y-0.5">
          {Object.entries(bd).map(([k, v]) => (
            <div key={k} className="flex justify-between">
              <span>{k.replace(/_/g, ' ')}</span><span>{String(v)}</span>
            </div>
          ))}
        </div>
      </WidgetShell>
    );
  },

  my_active_goals(meta: WidgetMeta, p: any, drill: () => void) {
    const rag = p?.rag || {};
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="text-2xl font-semibold">{p?.count || 0}<span className="text-xs text-slate-500 ml-1">active</span></div>
        <div className="flex gap-2 mt-2 text-xs">
          <Badge className="bg-green-100 text-green-700 border-green-300 border">{rag.green || 0} green</Badge>
          <Badge className="bg-amber-100 text-amber-700 border-amber-300 border">{rag.amber || 0} amber</Badge>
          <Badge className="bg-red-100 text-red-700 border-red-300 border">{rag.red || 0} red</Badge>
        </div>
      </WidgetShell>
    );
  },

  my_1on1_actions(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <CountTile count={p?.count || 0} label="action items open" tone="action" />
        <div className="text-xs text-slate-500 mt-2 space-y-0.5">
          {(p?.top || []).slice(0, 3).map((a: any) => (
            <div key={a.id} className="truncate">• {a.description}</div>
          ))}
        </div>
      </WidgetShell>
    );
  },

  my_next_payslip(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        {p?.available ? (
          <div className="space-y-1 text-sm">
            <div>Run #{p?.run_id}</div>
            <div className="text-xs text-slate-500">{p?.run_month}/{p?.run_year} · {p?.status}</div>
          </div>
        ) : (
          <div className="text-sm text-slate-500">No payslip yet.</div>
        )}
      </WidgetShell>
    );
  },

  unified_approval_queue(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}
        headerRight={<Badge className="bg-blue-100 text-blue-700 border-blue-300 border">{p?.count || 0}</Badge>}>
        <div className="text-xs text-slate-500 flex gap-3 mt-1">
          <span>Legacy: {p?.legacy_count || 0}</span>
          <span>Chain: {p?.chain_count || 0}</span>
        </div>
        <div className="text-xs text-slate-500 mt-2 space-y-0.5">
          {(p?.top || []).slice(0, 4).map((row: any, i: number) => (
            <div key={i} className="truncate">
              • [{row.origin}] {row.entity_type || row.resource_type} #{row.entity_id || row.resource_id}
              {row.amount_paise != null && <span className="ml-1 text-slate-700">{fmtInr(row.amount_paise)}</span>}
            </div>
          ))}
        </div>
      </WidgetShell>
    );
  },

  team_attendance_today(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="text-2xl font-semibold">
          {p?.present || 0}<span className="text-sm text-slate-500 ml-1">/ {p?.total || 0}</span>
        </div>
        <div className="text-xs text-slate-500">{p?.percent}% present</div>
      </WidgetShell>
    );
  },

  team_on_leave_this_week(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <CountTile count={p?.count || 0} label="on leave" tone="warn" />
        <div className="text-xs text-slate-500 mt-2 space-y-0.5">
          {(p?.top || []).slice(0, 3).map((r: any, i: number) => (
            <div key={i}>#{r.employee_id}: {r.start_date}→{r.end_date}</div>
          ))}
        </div>
      </WidgetShell>
    );
  },

  team_reviews_owed(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <CountTile count={p?.count || 0} label="reviews you owe" tone="action" />
      </WidgetShell>
    );
  },

  team_1on1_coverage(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="text-2xl font-semibold">{p?.count_reportees || 0}<span className="text-xs text-slate-500 ml-1">reportees</span></div>
        <div className="mt-2 text-xs text-slate-500">
          {p?.no_meeting_30d || 0} haven't had a 1:1 in 30 days
        </div>
      </WidgetShell>
    );
  },

  hr_pending_verifications(meta: WidgetMeta, p: any, drill: () => void) {
    return <WidgetShell meta={meta} onDrill={drill}>
      <CountTile count={p?.count || 0} label="docs awaiting verify" tone="action" />
    </WidgetShell>;
  },
  hr_tax_declarations_pending(meta: WidgetMeta, p: any, drill: () => void) {
    return <WidgetShell meta={meta} onDrill={drill}>
      <CountTile count={p?.count || 0} label="declarations submitted" tone="action" />
    </WidgetShell>;
  },
  hr_flagged_attendance(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <CountTile
          count={p?.count || 0}
          label={`flagged last ${p?.window_days ?? 30}d`}
          tone="action"
        />
        <div className="text-xs text-slate-500 mt-2 space-y-0.5">
          {p?.geo_in != null && (
            <div className="flex justify-between">
              <span>Geo fail (punch-in)</span><span>{p.geo_in}</span>
            </div>
          )}
          {p?.geo_out != null && (
            <div className="flex justify-between">
              <span>Geo fail (punch-out)</span><span>{p.geo_out}</span>
            </div>
          )}
          {p?.attribution != null && (
            <div className="flex justify-between">
              <span>Attribution</span><span>{p.attribution}</span>
            </div>
          )}
        </div>
      </WidgetShell>
    );
  },
  hr_out_of_policy_expenses(meta: WidgetMeta, p: any, drill: () => void) {
    return <WidgetShell meta={meta} onDrill={drill}>
      <CountTile count={p?.count || 0} label="claims to inspect" tone="action" />
    </WidgetShell>;
  },
  hr_review_cycles_progress(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="text-2xl font-semibold">{p?.count || 0}<span className="text-xs text-slate-500 ml-1">in flight</span></div>
        <div className="text-xs text-slate-500 mt-2 space-y-0.5">
          {(p?.cycles || []).slice(0, 3).map((c: any) => (
            <div key={c.id} className="flex justify-between">
              <span className="truncate mr-2">{c.name}</span>
              <span>{c.percent}%</span>
            </div>
          ))}
        </div>
      </WidgetShell>
    );
  },
  hr_headcount_trend(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="text-3xl font-semibold">{p?.current || 0}</div>
        <div className="text-xs text-slate-500">active employees</div>
      </WidgetShell>
    );
  },
  hr_attrition_rate(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="text-sm">Since {p?.month_start}</div>
        <div className="text-xs text-slate-500 mt-2">
          Active: {p?.active} · Ever-inactive: {p?.leavers_ever}
        </div>
      </WidgetShell>
    );
  },
  hr_exceptions(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <CountTile count={p?.count || 0} label="data-quality issues" tone="warn" />
      </WidgetShell>
    );
  },

  finance_reimbursement_queue(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="text-2xl font-semibold">{p?.count || 0}</div>
        <div className="text-xs text-slate-500 mt-1">Total {fmtInr(p?.total_paise)}</div>
        <div className="text-xs text-slate-500 mt-2 space-y-0.5">
          {(p?.top || []).slice(0, 3).map((r: any) => (
            <div key={r.id} className="flex justify-between">
              <span className="truncate mr-2">{r.title}</span>
              <span>{fmtInr(r.amount_paise)}</span>
            </div>
          ))}
        </div>
      </WidgetShell>
    );
  },
  finance_travel_advance_outstanding(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="text-2xl font-semibold">{p?.count || 0}</div>
        <div className="text-xs text-slate-500">Outstanding {fmtInr(p?.total_paise)}</div>
      </WidgetShell>
    );
  },
  finance_payroll_status(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="text-xs text-slate-500 space-y-1">
          {(p?.recent || []).map((r: any) => (
            <div key={r.id} className="flex justify-between">
              <span>Run #{r.id}</span>
              <span>{r.status}</span>
            </div>
          ))}
          {!(p?.recent || []).length && <div>No runs.</div>}
        </div>
      </WidgetShell>
    );
  },
  finance_statutory_due(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <CountTile count={p?.count || 0} label="filings open" tone="action" />
      </WidgetShell>
    );
  },
  finance_cost_analytics(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        {p?.has_run ? (
          <div className="text-sm">Latest run #{p?.run_id} · {p?.status}</div>
        ) : (
          <div className="text-sm text-slate-500">No finalized run yet.</div>
        )}
      </WidgetShell>
    );
  },

  executive_rating_distribution(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="text-2xl font-semibold">{p?.total || 0}<span className="text-xs text-slate-500 ml-1">reviewed</span></div>
        <div className="mt-2 grid grid-cols-5 gap-1 text-[10px] text-center">
          {(p?.distribution || []).map((b: any) => (
            <div key={b.bucket} className="p-1 bg-slate-50 border border-slate-200 rounded">
              <div className="font-semibold">{b.bucket}</div>
              <div>{b.percent}%</div>
            </div>
          ))}
        </div>
      </WidgetShell>
    );
  },
  executive_headline_kpis(meta: WidgetMeta, p: any, drill: () => void) {
    return (
      <WidgetShell meta={meta} onDrill={drill}>
        <div className="grid grid-cols-3 gap-2">
          <CountTile count={p?.headcount || 0} label="headcount" tone="neutral" />
          <CountTile count={p?.goals_open || 0} label="goals open" tone="good" />
          <CountTile count={p?.goals_at_risk || 0} label="at-risk" tone="warn" />
        </div>
      </WidgetShell>
    );
  },
};

const WIDGET_RENDERERS: Record<string, (m: WidgetMeta, p: any, drill: () => void) => React.ReactNode> = R;

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

// Section M B3: persist the multi-role user's last-selected cockpit.
// Restored on next login. The backend still validates the choice
// against `available_dashboards` — an invalid saved value falls back
// to the role-priority landing without user impact.
const COCKPIT_STORAGE_KEY = 'erp:last-cockpit';

const readSavedCockpit = (): string | null => {
  try {
    return window.localStorage.getItem(COCKPIT_STORAGE_KEY);
  } catch {
    return null;
  }
};

const writeSavedCockpit = (v: string | null) => {
  try {
    if (v) window.localStorage.setItem(COCKPIT_STORAGE_KEY, v);
    else window.localStorage.removeItem(COCKPIT_STORAGE_KEY);
  } catch {
    // ignore quota/privacy errors
  }
};

export const RoleDashboard: React.FC<RoleDashboardProps> = ({ onNavigate, embedded = false }) => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [picked, setPicked] = useState<string | null>(null);

  const fetchIt = async (dashboard?: string) => {
    setLoading(true);
    try {
      const r = await client.get(ENDPOINTS.DASHBOARD.ROOT, {
        params: dashboard ? { dashboard } : {},
      });
      setData(r.data);
      setPicked(r.data.active_dashboard);
      // Persist only when the backend accepted our explicit ask —
      // r.data.active_dashboard reflects post-validation reality.
      if (dashboard) writeSavedCockpit(r.data.active_dashboard);
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load dashboard'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Restore saved cockpit on first mount.
    fetchIt(readSavedCockpit() || undefined);
  }, []);

  const grouped = useMemo(() => {
    if (!data) return { action: [], data: [], analytic: [] };
    const g: Record<string, WidgetMeta[]> = { action: [], data: [], analytic: [] };
    for (const w of data.widgets) g[w.category].push(w);
    return g;
  }, [data]);

  if (loading || !data) {
    if (embedded) return null;
    return <div className="p-6"><Loading label="Loading your cockpit…" /></div>;
  }

  // Inside My Workspace, a single-role employee with nothing pending
  // gets no Command Center — the page already covers their day.
  if (
    embedded
    && data.available_dashboards.length <= 1
    && data.active_dashboard === 'employee-dashboard'
    && data.pending_count === 0
  ) {
    return null;
  }

  const drillFor = (meta: WidgetMeta) => () => {
    if (onNavigate) onNavigate(meta.drill.route, meta.drill.params);
  };

  const render = (meta: WidgetMeta) => {
    const renderer = WIDGET_RENDERERS[meta.key];
    const payload = data.payloads[meta.key];
    if (!renderer) {
      return (
        <WidgetShell meta={meta}>
          <div className="text-xs text-slate-400">No renderer for {meta.key} yet.</div>
        </WidgetShell>
      );
    }
    if (payload && payload.error) {
      return (
        <WidgetShell meta={meta}>
          <div className="text-xs text-red-600">Widget errored server-side.</div>
        </WidgetShell>
      );
    }
    return renderer(meta, payload, drillFor(meta));
  };

  return (
    <div
      className={embedded
        ? 'p-8 bg-white border border-slate-100 rounded-2xl shadow-sm space-y-6'
        : 'p-6 space-y-6'}
    >
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div className="flex items-center gap-3">
          {embedded && (
            <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center text-[#2563EB] border border-blue-100">
              <ClipboardCheck size={16} />
            </div>
          )}
          <div>
            <div className={embedded
              ? 'text-lg font-black text-[#0F172A] uppercase tracking-tight'
              : 'text-xl font-semibold text-slate-800'}>
              {embedded
                ? 'Command Center'
                : `${DASHBOARD_LABELS[data.active_dashboard] || 'Dashboard'} Cockpit`}
            </div>
            <div className="text-xs text-slate-500">
              {embedded
                ? `${DASHBOARD_LABELS[data.active_dashboard] || 'Role'} view · ${data.pending_count} pending`
                : `Signed in as ${data.role_names.join(', ')} · ${data.pending_count} pending`}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {data.available_dashboards.length > 1 && (
            <div className="flex items-center gap-1 bg-slate-100 rounded p-1 text-xs">
              {data.available_dashboards.map(d => (
                <button
                  key={d}
                  onClick={() => fetchIt(d)}
                  className={cn(
                    'px-2 py-1 rounded transition-colors',
                    d === picked ? 'bg-white shadow-sm font-semibold text-slate-800' : 'text-slate-500 hover:text-slate-700',
                  )}
                >
                  {DASHBOARD_LABELS[d] || d}
                </button>
              ))}
            </div>
          )}
          <Button variant="secondary" onClick={() => fetchIt(picked || undefined)}>
            <RefreshCw size={14} className="mr-1" />Refresh
          </Button>
        </div>
      </div>

      {grouped.action.length > 0 && (
        <section>
          <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">
            Actions Awaiting You
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {grouped.action.map(w => (
              <React.Fragment key={w.key}>{render(w)}</React.Fragment>
            ))}
          </div>
        </section>
      )}

      {grouped.data.length > 0 && (
        <section>
          <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">
            Your Data
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {grouped.data.map(w => (
              <React.Fragment key={w.key}>{render(w)}</React.Fragment>
            ))}
          </div>
        </section>
      )}

      {grouped.analytic.length > 0 && (
        <section>
          <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">
            Analytics
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {grouped.analytic.map(w => (
              <React.Fragment key={w.key}>{render(w)}</React.Fragment>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

export default RoleDashboard;
