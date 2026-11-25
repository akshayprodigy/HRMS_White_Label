import React, { useState } from 'react';
import { Button } from '../ui-elements';
import { Modal } from '../assets/modal';
import { Notice, dopErr, useGuard } from './dop-utils';

/** In-page confirmation (no browser dialogs). `onConfirm` throws to show its message. */
export const ConfirmDialog: React.FC<{
  title: string; body: React.ReactNode; confirmText: string; danger?: boolean;
  onConfirm: () => Promise<void>; onClose: () => void;
}> = ({ title, body, confirmText, danger, onConfirm, onClose }) => {
  const { busy, run } = useGuard();
  const [err, setErr] = useState<string | null>(null);
  const go = () => run(async () => {
    setErr(null);
    try { await onConfirm(); } catch (e: any) { setErr(dopErr(e, 'That did not work')); }
  });
  return (
    <Modal title={title} label={title} onClose={onClose} busy={busy}>
      <div className="text-sm text-gray-700 space-y-2">{body}</div>
      {err && <Notice>{err}</Notice>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant={danger ? 'danger' : 'primary'} onClick={go} isLoading={busy}>{confirmText}</Button>
      </div>
    </Modal>
  );
};
