import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertOctagon, AlertTriangle, Info } from 'lucide-react';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { useVisiblePoll } from '../../hooks/use-visible-poll';

export interface MyBroadcast {
  id: number;
  title: string;
  message: string;
  severity: 'info' | 'warning' | 'critical';
  requires_ack: boolean;
  safety_check: boolean;
  created_at: string | null;
  read_at: string | null;
  acked_at: string | null;
  safety_status: 'safe' | 'need_help' | null;
  safety_note: string | null;
  pending: boolean;
}

const BANNER_SLOT_ID = 'broadcast-banner-slot';
const POLL_MS = 60_000;
const POLL_CRITICAL_MS = 20_000; // faster while a critical alert is pending

const TONE = {
  info: { box: 'bg-blue-50 border-blue-200 text-blue-900', Icon: Info },
  warning: { box: 'bg-amber-50 border-amber-300 text-amber-900', Icon: AlertTriangle },
  critical: { box: 'bg-red-50 border-red-300 text-red-900', Icon: AlertOctagon },
} as const;

/** Active broadcasts that still need this user's response. Mounted app-wide
 * (desktop App + mobile shell). Critical = blocking modal, others = banner.
 * Rendered above the attendance gate: the endpoints are not attendance-gated. */
export const BroadcastAlerts: React.FC = () => {
  const [items, setItems] = useState<MyBroadcast[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [helpFor, setHelpFor] = useState<number | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await client.get(ENDPOINTS.BROADCASTS.MY);
      setItems(Array.isArray(res.data) ? res.data : []);
    } catch {
      /* silent: transient / logged-out */
    }
  }, []);

  const act = async (id: number, path: string, body?: object) => {
    setBusy(id);
    setError(null);
    try {
      const res = await client.post(path, body);
      setItems((prev) => prev.map((b) => (b.id === id ? res.data : b)));
      setHelpFor(null);
      setNote('');
    } catch (err: any) {
      setError(errMsg(err, 'Could not send your response'));
    } finally {
      setBusy(null);
    }
  };

  const pending = items.filter((b) => b.pending);
  const critical = pending.find((b) => b.severity === 'critical');
  const banners = pending.filter((b) => b !== critical);
  useVisiblePoll(load, critical ? POLL_CRITICAL_MS : POLL_MS);

  // Critical modal a11y: focus first action, trap Tab, make the rest of the
  // app inert / aria-hidden while open, restore focus afterwards.
  const dialogRef = useRef<HTMLDivElement>(null);
  const criticalId = critical?.id;
  useEffect(() => {
    if (criticalId === undefined) return;
    const prev = document.activeElement as HTMLElement | null;
    const root = document.getElementById('root');
    root?.setAttribute('inert', '');
    root?.setAttribute('aria-hidden', 'true');
    const focusFirst = () =>
      dialogRef.current?.querySelector<HTMLElement>('button, textarea')?.focus();
    focusFirst();
    return () => {
      root?.removeAttribute('inert');
      root?.removeAttribute('aria-hidden');
      prev?.focus?.();
    };
  }, [criticalId]);
  // keep focus inside when the action area changes (e.g. help-note form opens)
  useEffect(() => {
    if (criticalId !== undefined && !dialogRef.current?.contains(document.activeElement)) {
      dialogRef.current?.querySelector<HTMLElement>('button, textarea')?.focus();
    }
  }, [criticalId, helpFor, busy]);
  const trapTab = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab') return;
    const f = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), textarea:not([disabled])') ?? []);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  const renderActions = (b: MyBroadcast) => {
    const disabled = busy === b.id;
    const btn = 'px-3 py-2 rounded-lg text-sm font-semibold disabled:opacity-50';
    return (
      <div className="mt-3">
        {helpFor === b.id ? (
          <div className="space-y-2">
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
              rows={2}
              placeholder="Where are you / what do you need? (optional)"
              aria-label="Help note"
              className="w-full rounded-lg border border-red-300 bg-white p-2 text-sm text-slate-900"
            />
            <div className="flex gap-2">
              <button type="button" disabled={disabled}
                onClick={() => act(b.id, ENDPOINTS.BROADCASTS.SAFETY(b.id), { status: 'need_help', note })}
                className={`${btn} bg-red-600 text-white`}>
                Send help request
              </button>
              <button type="button" onClick={() => setHelpFor(null)}
                className={`${btn} bg-white border border-slate-300 text-slate-700`}>
                Back
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {b.safety_check ? (
              <>
                <button type="button" disabled={disabled}
                  onClick={() => act(b.id, ENDPOINTS.BROADCASTS.SAFETY(b.id), { status: 'safe' })}
                  className={`${btn} bg-green-600 text-white`}>
                  I'm safe
                </button>
                <button type="button" disabled={disabled} onClick={() => setHelpFor(b.id)}
                  className={`${btn} bg-red-600 text-white`}>
                  Need help
                </button>
              </>
            ) : null}
            {b.requires_ack && !b.safety_check ? (
              <button type="button" disabled={disabled}
                onClick={() => act(b.id, ENDPOINTS.BROADCASTS.ACK(b.id))}
                className={`${btn} bg-blue-600 text-white`}>
                Acknowledge
              </button>
            ) : null}
            {!b.requires_ack && !b.safety_check ? (
              <button type="button" disabled={disabled}
                onClick={() => act(b.id, ENDPOINTS.BROADCASTS.READ(b.id))}
                className={`${btn} bg-white border border-slate-300 text-slate-700`}>
                Dismiss
              </button>
            ) : null}
          </div>
        )}
      </div>
    );
  };

  if (!pending.length) return null;
  const bannerBox = banners.length > 0 && (
    <div className="p-2 space-y-2 max-h-[40vh] overflow-y-auto bg-[#F8FAFC] border-b border-slate-200"
      role="region" aria-label="Broadcast alerts">
      {banners.map((b) => {
        const { box, Icon } = TONE[b.severity] ?? TONE.info;
        return (
          <div key={b.id} role="alert"
            className={`mx-auto max-w-3xl rounded-xl border p-3 shadow-sm ${box}`}>
            <div className="flex items-start gap-2">
              <Icon className="w-5 h-5 mt-0.5 flex-shrink-0" />
              <div className="min-w-0">
                <p className="font-bold text-sm">{b.title}</p>
                <p className="text-sm whitespace-pre-wrap break-words">{b.message}</p>
              </div>
            </div>
            {renderActions(b)}
          </div>
        );
      })}
      {error && <p role="alert" className="text-xs text-red-700 text-center">{error}</p>}
    </div>
  );
  // Non-critical banners live in normal flow at the top of the main content
  // area (below the header) via the layout's slot; fixed overlay as a fallback.
  const slot = banners.length > 0 ? document.getElementById(BANNER_SLOT_ID) : null;
  return (
    <>
      {bannerBox && (slot ? createPortal(bannerBox, slot)
        : <div className="fixed top-0 left-0 right-0 z-[150]">{bannerBox}</div>)}
      {critical && createPortal(
        <div className="fixed inset-0 z-[200] bg-slate-900/80 flex items-center justify-center p-4"
          role="alertdialog" aria-modal="true"
          aria-labelledby={`bc-title-${critical.id}`} aria-describedby={`bc-msg-${critical.id}`}
          ref={dialogRef} onKeyDown={trapTab}>
          <div className="w-full max-w-md max-h-full overflow-y-auto rounded-2xl bg-white border-4 border-red-500 p-5 shadow-2xl">
            <div className="flex items-center gap-2 text-red-700">
              <AlertOctagon className="w-6 h-6" aria-hidden="true" />
              <span className="text-xs font-black uppercase tracking-widest">Emergency broadcast</span>
            </div>
            <h2 id={`bc-title-${critical.id}`} className="mt-2 text-xl font-black text-slate-900">{critical.title}</h2>
            <p id={`bc-msg-${critical.id}`} className="mt-2 text-sm text-slate-700 whitespace-pre-wrap break-words">{critical.message}</p>
            {renderActions(critical)}
            {error && <p role="alert" className="mt-2 text-xs text-red-700">{error}</p>}
            {pending.length > 1 && (
              <p className="mt-3 text-xs text-slate-500">{pending.length - 1} more alert(s) waiting</p>
            )}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
};
