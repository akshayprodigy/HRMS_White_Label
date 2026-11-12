import React, { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { CalendarSync, Copy } from 'lucide-react';
import { Card, Button, Badge } from '../ui-elements';
import { errMsg, parseServerDate } from '../schedule-delegations-utils';
import { CalendarFeedStatus, inputCls, mySchedule } from './my-schedule-api';
import { InlineConfirm } from './inline-confirm';

export const CalendarFeedCard: React.FC = () => {
  const [status, setStatus] = useState<CalendarFeedStatus | null>(null);
  const [url, setUrl] = useState<string | null>(null); // shown once, never persisted
  const [busy, setBusy] = useState<'rotate' | 'off' | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await mySchedule.feedStatus());
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to load calendar feed status'));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const rotate = async () => {
    setBusy('rotate');
    try {
      const r = await mySchedule.rotateFeed();
      setUrl(r.url);
      toast.success('Calendar link created');
      await load();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to create calendar link'));
    } finally {
      setBusy(null);
    }
  };

  const turnOff = async () => {
    setBusy('off');
    try {
      await mySchedule.deleteFeed();
      setUrl(null);
      toast.success('Calendar feed turned off');
      await load();
    } catch (e: any) {
      toast.error(errMsg(e, 'Failed to turn off calendar feed'));
    } finally {
      setBusy(null);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url || '');
      toast.success('Link copied');
    } catch {
      input.current?.focus();
      input.current?.select();
      toast.message('Press Ctrl/Cmd+C to copy the selected link');
    }
  };

  return (
    <Card className="p-5 border-slate-200 bg-white space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
            <CalendarSync size={18} />
          </div>
          <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A]">Calendar feed</p>
            <p className="text-[10px] text-slate-500 mt-0.5 max-w-xl">
              Subscribe to your roster from Google Calendar, Outlook or Apple Calendar. The feed contains only
              published roster shifts — a shift that comes purely from a default assignment is not included.
            </p>
          </div>
        </div>
        {status && (
          <Badge variant={status.active ? 'success' : 'neutral'} className="text-[8px] uppercase">
            {status.active ? 'Active' : 'Off'}
          </Badge>
        )}
      </div>

      {status?.active && status.created_at && !url && (
        <p className="text-[10px] text-slate-500">
          Link created {parseServerDate(status.created_at).toLocaleString('en-IN')}. For security the link
          cannot be shown again; regenerate it to get a new one (the old link stops working).
        </p>
      )}

      {url && (
        <div className="space-y-2 border border-amber-200 bg-amber-50 rounded-xl p-3">
          <p className="text-[10px] font-black uppercase tracking-widest text-amber-700">
            Copy this link now — it will not be shown again
          </p>
          <div className="flex gap-2">
            <input ref={input} readOnly value={url} aria-label="Calendar feed URL"
              onFocus={(e) => e.currentTarget.select()} className={inputCls + ' font-mono text-xs'} />
            <Button variant="outline" onClick={copy} className="h-10 shrink-0" aria-label="Copy calendar link">
              <Copy size={14} className="mr-1.5" /> Copy
            </Button>
          </div>
          <p className="text-[10px] text-slate-600">
            Subscribe by URL: Google Calendar → Other calendars → From URL · Outlook → Add calendar →
            Subscribe from web · Apple Calendar → File → New Calendar Subscription.
          </p>
        </div>
      )}

      {status?.active ? (
        <div className="flex flex-col items-start gap-1.5">
          <div className="flex items-center gap-4 flex-wrap">
            <InlineConfirm label="Regenerate link" confirmLabel="Regenerate" tone="neutral"
              ariaLabel="Regenerate calendar link" busy={busy !== null} onConfirm={rotate} />
            <InlineConfirm label="Turn off" confirmLabel="Turn off" ariaLabel="Turn off calendar feed"
              busy={busy !== null} onConfirm={turnOff} />
          </div>
          <span className="text-[10px] text-slate-500">
            Regenerating makes existing calendar subscriptions stop updating.
          </span>
        </div>
      ) : (
        <Button onClick={rotate} isLoading={busy === 'rotate'} className="h-9">
          Create link
        </Button>
      )}
    </Card>
  );
};
