import React, { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '../ui-elements';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog';

interface Props {
  open: boolean;
  title: string;
  description?: string;
  label: string;
  confirmLabel: string;
  minLength?: number; // 0 = optional
  busy?: boolean;
  onConfirm: (text: string) => void;
  onClose: () => void;
}

/** Small text prompt used for edit reasons and publish-request notes. */
export const ReasonDialog = ({
  open,
  title,
  description,
  label,
  confirmLabel,
  minLength = 3,
  busy,
  onConfirm,
  onClose,
}: Props) => {
  const [text, setText] = useState('');
  useEffect(() => {
    if (open) setText('');
  }, [open]);
  const trimmed = text.trim();
  const valid = trimmed.length >= minLength;
  return (
    <Dialog open={open} onOpenChange={(o: boolean) => !o && !busy && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-2 py-1">
          {description && (
            <p className="text-sm text-gray-500">{description}</p>
          )}
          <label className="text-sm font-medium text-gray-700">
            {label}
            {minLength === 0 ? ' (optional)' : ''}
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={500}
            rows={3}
            className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
          {minLength > 0 && !valid && text.length > 0 && (
            <p className="text-xs text-red-600">
              At least {minLength} characters required.
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            onClick={() => onConfirm(trimmed)}
            disabled={busy || !valid}
            className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
          >
            {busy && <RefreshCw className="w-4 h-4 animate-spin" />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
