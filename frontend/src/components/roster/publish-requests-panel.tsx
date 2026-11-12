import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronRight, Inbox, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { Card, Button, Badge, cn } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import type { PublishRequest } from './roster-api';

interface Props {
  isAdmin: boolean;
  refreshKey: number;
  onChanged: () => void;
}

export const PublishRequestsPanel = ({ isAdmin, refreshKey, onChanged }: Props) => {
  const [items, setItems] = useState<PublishRequest[]>([]);
  const [open, setOpen] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [rejectId, setRejectId] = useState<number | null>(null);
  const [rejectNote, setRejectNote] = useState('');
  const reqId = useRef(0);

  const load = useCallback(async () => {
    const id = ++reqId.current;
    try {
      const { data } = await client.get<PublishRequest[]>(
        ENDPOINTS.ROSTER.PUBLISH_REQUESTS,
        { params: { status: 'pending' } }
      );
      if (id === reqId.current) setItems(data || []);
    } catch (err: any) {
      // keep the previous list; just tell the user
      if (id === reqId.current) toast.error(errMsg(err, 'Failed to load publish requests'));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  // Auto-expand when pending items appear (initial load or 0 -> >0); after
  // that the user's manual toggle is respected.
  const prevCount = useRef(0);
  useEffect(() => {
    if (prevCount.current === 0 && items.length > 0) setOpen(true);
    prevCount.current = items.length;
  }, [items.length]);

  const decide = async (r: PublishRequest, approve: boolean, note?: string) => {
    setBusyId(r.id);
    try {
      const { data } = await client.post<PublishRequest>(
        ENDPOINTS.ROSTER.PUBLISH_REQUEST_DECIDE(r.id),
        { approve, note: note || null }
      );
      toast.success(
        data.message || (approve ? 'Request approved and published' : 'Request rejected')
      );
      setRejectId(null);
      setRejectNote('');
      await load();
      onChanged();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to decide request'));
    } finally {
      setBusyId(null);
    }
  };

  const cancel = async (r: PublishRequest) => {
    setBusyId(r.id);
    try {
      await client.post(ENDPOINTS.ROSTER.PUBLISH_REQUEST_CANCEL(r.id));
      toast.success('Request cancelled');
      await load();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to cancel request'));
    } finally {
      setBusyId(null);
    }
  };

  if (items.length === 0 && !isAdmin) return null;

  return (
    <Card className="p-3">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-center gap-2 w-full text-left text-sm font-medium text-gray-800"
      >
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        <Inbox className="w-4 h-4 text-indigo-600" />
        {isAdmin ? 'Publish requests' : 'My publish requests'}
        <Badge className="bg-indigo-50 text-indigo-700 border-indigo-200">
          {items.length}
        </Badge>
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          {items.length === 0 && (
            <p className="text-sm text-gray-400">No pending requests.</p>
          )}
          {items.map((r) => (
            <div key={r.id} className="p-2.5 border rounded-lg text-sm">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="font-medium text-gray-900">
                  {r.requester_name || `User #${r.requested_by_id}`}
                </span>
                <span className="text-gray-600">
                  {r.start} → {r.end}
                </span>
                <span className="text-gray-500">
                  {r.department || 'All departments'}
                  {r.employee_ids.length > 0 && ` · ${r.employee_ids.length} employees`}
                </span>
                <Badge className="bg-amber-50 text-amber-700 border-amber-200">
                  {r.draft_count ?? 0} drafts
                </Badge>
                <div className="flex-1" />
                {isAdmin ? (
                  <>
                    <Button
                      size="sm"
                      disabled={busyId === r.id}
                      onClick={() => decide(r, true)}
                      className="bg-indigo-600 hover:bg-indigo-700 text-white gap-1.5"
                    >
                      {busyId === r.id && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busyId === r.id}
                      onClick={() => {
                        setRejectId(rejectId === r.id ? null : r.id);
                        setRejectNote('');
                      }}
                    >
                      Reject
                    </Button>
                  </>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busyId === r.id}
                    onClick={() => cancel(r)}
                  >
                    Cancel
                  </Button>
                )}
              </div>
              {r.note && <p className="mt-1 text-xs text-gray-500">Note: {r.note}</p>}
              {isAdmin && rejectId === r.id && (
                <div className={cn('mt-2 flex flex-wrap items-center gap-2')}>
                  <input
                    value={rejectNote}
                    onChange={(e) => setRejectNote(e.target.value)}
                    maxLength={500}
                    placeholder="Reason for rejection (required)"
                    className="flex-1 min-w-[200px] px-3 py-1.5 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
                  />
                  <Button
                    size="sm"
                    disabled={busyId === r.id || !rejectNote.trim()}
                    onClick={() => decide(r, false, rejectNote.trim())}
                    className="bg-red-600 hover:bg-red-700 text-white"
                  >
                    Confirm reject
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};
