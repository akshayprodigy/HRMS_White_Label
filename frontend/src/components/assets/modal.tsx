import React, { useEffect } from 'react';
import { Card } from '../ui-elements';

/** Minimal modal shell, same look as the biometric dialogs. */
export const Modal: React.FC<{
  title: React.ReactNode;
  label: string;
  onClose: () => void;
  busy?: boolean;
  wide?: boolean;
  children: React.ReactNode;
}> = ({ title, label, onClose, busy, wide, children }) => {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape' && !busy) onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose, busy]);
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(15,23,42,0.45)' }}
      role="dialog"
      aria-modal="true"
      aria-label={label}
    >
      <Card className={`w-full ${wide ? 'max-w-3xl' : 'max-w-lg'} p-5 space-y-4 max-h-full overflow-y-auto`}>
        <h3 className="text-base font-semibold text-gray-900">{title}</h3>
        {children}
      </Card>
    </div>
  );
};
