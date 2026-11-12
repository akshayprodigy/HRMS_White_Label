import React, { useEffect, useState } from 'react';
import { PhoneCall } from 'lucide-react';
import { Card } from '../ui-elements';
import { fmtDate } from './my-schedule-api';
import { onCallApi, type OnCallDay } from '../roster/on-call-api';

/** Upcoming on-call (standby) days for the signed-in employee. */
export const MyOnCallCard: React.FC = () => {
  const [days, setDays] = useState<OnCallDay[]>([]);
  useEffect(() => {
    let live = true;
    onCallApi.mine().then((d) => live && setDays(d)).catch(() => live && setDays([]));
    return () => { live = false; };
  }, []);
  if (days.length === 0) return null;
  return (
    <Card className="p-5 border-slate-200 bg-white" data-testid="my-on-call">
      <p className="text-[10px] font-black uppercase tracking-widest text-[#0F172A] flex items-center gap-1.5 mb-3">
        <PhoneCall size={13} className="text-indigo-600" /> On-call · next 30 days
      </p>
      <ul className="space-y-1.5">
        {days.map((d) => (
          <li key={d.id} className="flex items-center gap-3 text-[12px]">
            <span className="font-black text-[#0F172A] w-24">{fmtDate(d.work_date)}</span>
            <span className="tabular-nums text-slate-600">
              {d.start_time}–{d.end_time}{d.is_overnight ? ' (+1 day)' : ''}
            </span>
            {d.note && <span className="text-slate-400 truncate">{d.note}</span>}
          </li>
        ))}
      </ul>
    </Card>
  );
};
