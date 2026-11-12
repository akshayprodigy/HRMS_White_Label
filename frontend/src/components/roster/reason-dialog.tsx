import React, { useEffect, useId, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '../ui-elements';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogDescription,
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
  const fieldId = useId();
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
          <DialogDescription className="sr-only">{description || 'Provide a reason for this change.'}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-1">
          {description && (
            <p className="text-sm text-gray-500">{description}</p>
          )}
          <label htmlFor={fieldId} className="text-sm font-medium text-gray-700">
            {label}
            {minLength === 0 ? ' (optional)' : ''}
          </label>
          <textarea
            id={fieldId}
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={500}
            rows={3}
            className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
          <div aria-live="polite" className="text-xs text-red-600 min-h-[1rem]">
            {minLength > 0 && !valid && text.length > 0
              ? `At least ${minLength} characters required.`
              : ''}
          </div>
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
