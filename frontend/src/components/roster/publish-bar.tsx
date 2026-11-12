import React, { useState } from 'react';
import { Send, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogDescription,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog';
import { ReasonDialog } from './reason-dialog';
import type { PublishResult } from './roster-api';

interface Props {
  draftCount: number;
  canPublish: boolean;
  start: string;
  end: string;
  department: string;
  disabled?: boolean;
  lockedDraftCount?: number;
  lockDays?: number;
  onDone: () => void;
}

export const PublishBar = ({
  draftCount,
  canPublish,
  start,
  end,
  department,
  disabled,
  lockedDraftCount = 0,
  lockDays = 0,
  onDone,
}: Props) => {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [reqOpen, setReqOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const body = { start, end, department: department || null };

  const publish = async () => {
    setBusy(true);
    try {
      const { data } = await client.post<PublishResult>(
        ENDPOINTS.ROSTER.PUBLISH,
        { ...body, reason: reason.trim() || undefined }
      );
      const np = data.not_permitted.length;
      toast.success(
        `Published ${data.published} cell${data.published === 1 ? '' : 's'} for ${data.employees} employee${data.employees === 1 ? '' : 's'}` +
          (np ? `; ${np} not permitted` : '')
      );
      setConfirmOpen(false);
      setReason('');
      onDone();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to publish'));
    } finally {
      setBusy(false);
    }
  };

  const request = async (note: string) => {
    setBusy(true);
    try {
      await client.post(ENDPOINTS.ROSTER.PUBLISH_REQUESTS, {
        ...body,
        note: note || null,
      });
      toast.success('Publish request sent for approval');
      setReqOpen(false);
      onDone();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to request publish'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3 p-3 rounded-lg border border-dashed border-amber-300 bg-amber-50">
      <span className="text-sm text-amber-800 font-medium">
        {draftCount} draft cell{draftCount === 1 ? '' : 's'} in this view
      </span>
      <span className="text-xs text-amber-700 flex-1">
        Drafts are hidden from employees until published.
      </span>
      {canPublish ? (
        <Button
          size="sm"
          onClick={() => setConfirmOpen(true)}
          disabled={disabled || busy || draftCount === 0}
          className="bg-indigo-600 hover:bg-indigo-700 text-white gap-1.5"
        >
          {busy ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
          Publish
        </Button>
      ) : (
        <Button
          size="sm"
          onClick={() => setReqOpen(true)}
          disabled={disabled || busy || draftCount === 0}
          className="bg-indigo-600 hover:bg-indigo-700 text-white gap-1.5"
        >
          <Send className="w-4 h-4" />
          Request publish
        </Button>
      )}
      <Dialog open={confirmOpen} onOpenChange={(o: boolean) => !o && !busy && setConfirmOpen(false)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Publish drafts</DialogTitle>
            <DialogDescription className="sr-only">Confirm publishing the draft cells in this period.</DialogDescription>
          </DialogHeader>
          <p className="py-2 text-sm text-gray-700">
            Publish <b>{draftCount}</b> draft cell{draftCount === 1 ? '' : 's'} for{' '}
            <b>{start} → {end}</b>
            {department ? <> in <b>{department}</b></> : null}? Affected
            employees will be notified.
          </p>
          {lockedDraftCount > 0 && (
            <div className="space-y-1 pb-2">
              <p className="text-xs text-amber-700">
                {lockedDraftCount} of these fall inside the {lockDays}-day lock
                window: publishing them is an emergency change (employees must
                acknowledge).
              </p>
              <label htmlFor="publish-reason" className="text-sm font-medium text-gray-700">
                Emergency change reason
              </label>
              <input
                id="publish-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={500}
                className="w-full px-3 py-2 border rounded-lg text-sm"
              />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              onClick={publish}
              disabled={busy || (lockedDraftCount > 0 && reason.trim().length < 3)}
              className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
            >
              {busy && <RefreshCw className="w-4 h-4 animate-spin" />}
              Publish
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ReasonDialog
        open={reqOpen}
        title="Request publish"
        description={`Ask HR to publish drafts for ${start} → ${end}.`}
        label="Note for approver"
        confirmLabel="Send request"
        minLength={0}
        busy={busy}
        onConfirm={request}
        onClose={() => setReqOpen(false)}
      />
    </div>
  );
};
