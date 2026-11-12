import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { fmtDate } from './my-schedule-api';
import type { ScheduleAck } from '../roster/roster-api';

const cellText = (name: string | null, off: boolean) => (off ? 'Week off' : name || '—');

/** "Your schedule changed" banner: emergency (lock-window) changes the
 *  employee still has to acknowledge. Renders nothing when there are none. */
export const MyAcksBanner: React.FC<{ onChanged?: () => void }> = ({ onChanged }) => {
  const [acks, setAcks] = useState<ScheduleAck[]>([]);
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const { data } = await client.get<ScheduleAck[]>(ENDPOINTS.ROSTER.MY_ACKS);
      setAcks(data || []);
    } catch {
      setAcks([]);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const ack = async (id: number) => {
    setBusy(id);
    try {
      await client.post(ENDPOINTS.ROSTER.MY_ACK(id));
      toast.success('Thanks, schedule change acknowledged');
      await load();
      onChanged?.();
    } catch (e: any) {
      toast.error(errMsg(e, 'Could not acknowledge'));
    } finally {
      setBusy(null);
    }
  };

  if (acks.length === 0) return null;
  return (
    <div
      role="alert"
      data-testid="my-acks-banner"
      className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 space-y-2"
    >
      <p className="text-[11px] font-black uppercase tracking-widest text-amber-900 flex items-center gap-1.5">
        <AlertTriangle size={14} aria-hidden="true" /> Your schedule changed
      </p>
      <ul className="space-y-2">
        {acks.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center gap-3 text-[12px] text-amber-900">
            <div className="flex-1 min-w-[220px]">
              <span className="font-black">{fmtDate(a.work_date)}</span>{' '}
              {cellText(a.old_shift_name, a.old_is_week_off)} →{' '}
              <b>{cellText(a.new_shift_name, a.new_is_week_off)}</b>
              {a.reason && <span className="text-amber-700"> · {a.reason}</span>}
            </div>
            <Button
              size="sm"
              isLoading={busy === a.id}
              disabled={busy !== null}
              aria-label={`Acknowledge schedule change on ${a.work_date}`}
              onClick={() => ack(a.id)}
            >
              Acknowledge
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
};
