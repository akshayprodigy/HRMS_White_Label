import React, { useState } from 'react';
import { Copy, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import type { BulkResult } from './roster-api';

interface Props {
  open: boolean;
  source: { start: string; end: string } | null;
  target: { start: string; end: string };
  department: string;
  onClose: () => void;
  onDone: () => void;
}

export const CopyDialog = ({ open, source, target, department, onClose, onDone }: Props) => {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (!source) return;
    setBusy(true);
    try {
      const { data } = await client.post<BulkResult>(ENDPOINTS.ROSTER.COPY, {
        source_start: source.start,
        source_end: source.end,
        target_start: target.start,
        department: department || null,
        overwrite: false,
      });
      toast.success(
        `Copied as drafts — ${data.created} created, ${data.updated} updated, ${data.skipped} skipped` +
          (data.out_of_scope.length ? `, ${data.out_of_scope.length} out of scope` : '')
      );
      if (data.errors.length) toast.error(data.errors.slice(0, 3).join('; '));
      onClose();
      onDone();
    } catch (err: any) {
      toast.error(errMsg(err, 'Failed to copy period'));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={(o: boolean) => !o && !busy && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Copy className="w-5 h-5 text-indigo-600" />
            Copy previous period
          </DialogTitle>
        </DialogHeader>
        <div className="py-2 text-sm text-gray-700 space-y-2">
          <p>
            Copy <b>{source?.start} → {source?.end}</b> into{' '}
            <b>{target.start} → {target.end}</b> as drafts.
          </p>
          <p className="text-xs text-gray-500">
            Existing cells in the target period are kept; published cells are never overwritten.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            onClick={run}
            disabled={busy || !source}
            className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
          >
            {busy && <RefreshCw className="w-4 h-4 animate-spin" />}
            Copy as drafts
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
