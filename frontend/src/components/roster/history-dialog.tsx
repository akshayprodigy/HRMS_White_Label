import React, { useEffect, useRef, useState } from 'react';
import { History } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { HistoryRow, sideLabel } from './roster-api';

interface Props {
  employee: { id: number; name: string } | null;
  onClose: () => void;
}

export const HistoryDialog = ({ employee, onClose }: Props) => {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const reqId = useRef(0);

  useEffect(() => {
    if (!employee) return;
    const id = ++reqId.current;
    setLoading(true);
    setRows([]);
    client
      .get<HistoryRow[]>(ENDPOINTS.ROSTER.HISTORY, {
        params: { employee_id: employee.id },
      })
      .then((r) => id === reqId.current && setRows(r.data || []))
      .catch((e) => id === reqId.current && toast.error(errMsg(e, 'Failed to load history')))
      .finally(() => id === reqId.current && setLoading(false));
  }, [employee]);

  return (
    <Dialog open={!!employee} onOpenChange={(o: boolean) => !o && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <History className="w-5 h-5 text-indigo-600" />
            Change history — {employee?.name}
          </DialogTitle>
        </DialogHeader>
        <p className="text-xs text-gray-500">Changes in the last 30 days.</p>
        <div className="max-h-96 overflow-y-auto overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="py-1.5 pr-2">When</th>
                <th className="pr-2">Action</th>
                <th className="pr-2">Date</th>
                <th className="pr-2">Change</th>
                <th className="pr-2">Reason</th>
                <th>By</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-gray-400">
                    Loading…
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-gray-400">
                    No changes recorded.
                  </td>
                </tr>
              ) : (
                rows.map((h) => (
                  <tr key={h.id} className="border-b align-top">
                    <td className="py-1.5 pr-2 whitespace-nowrap text-gray-500">
                      {new Date(h.changed_at).toLocaleString()}
                    </td>
                    <td className="pr-2 capitalize">{h.action}</td>
                    <td className="pr-2 whitespace-nowrap">{h.work_date}</td>
                    <td className="pr-2">
                      {sideLabel(h.old_shift_name, h.old_is_week_off)} →{' '}
                      {h.action === 'delete'
                        ? 'removed'
                        : sideLabel(h.new_shift_name, h.new_is_week_off)}
                    </td>
                    <td className="pr-2 text-gray-600">{h.reason || '—'}</td>
                    <td className="text-gray-600">{h.changed_by_name || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </DialogContent>
    </Dialog>
  );
};
