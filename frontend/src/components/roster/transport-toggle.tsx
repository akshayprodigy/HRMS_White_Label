import { useState } from 'react';
import { Car } from 'lucide-react';
import { toast } from 'sonner';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { cn } from '../ui-elements';
import { errMsg } from '../schedule-delegations-utils';

/** Small cab/transport toggle for a working roster cell. Not a schedule
 *  change: it never creates history, hits the lock window or needs an ack. */
export const TransportToggle = ({
  entryId, value, who, onChanged,
}: {
  entryId: number;
  value: boolean;
  who: string;
  onChanged: (v: boolean) => void;
}) => {
  const [busy, setBusy] = useState(false);
  const toggle = async () => {
    setBusy(true);
    try {
      await client.patch(ENDPOINTS.ROSTER.ENTRY_TRANSPORT(entryId), { required: !value });
      onChanged(!value);
    } catch (e) {
      toast.error(errMsg(e, 'Could not update transport'));
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-pressed={value}
      aria-label={`Transport for ${who}`}
      title={value ? 'Cab/transport arranged (click to clear)' : 'Mark cab/transport arranged'}
      className={cn(
        'absolute bottom-1 left-1 p-0.5 rounded leading-none',
        value ? 'text-indigo-700 bg-indigo-50' : 'text-gray-400'
      )}
    >
      <Car className="w-3 h-3" />
    </button>
  );
};
