import React, { useEffect, useRef } from 'react';
import { Card } from '../ui-elements';

// Open modals, top-most last: only the top one reacts to Escape.
const stack: symbol[] = [];

/** Minimal modal shell, same look as the biometric dialogs. */
export const Modal: React.FC<{
  title: React.ReactNode;
  label: string;
  onClose: () => void;
  busy?: boolean;
  wide?: boolean;
  children: React.ReactNode;
}> = ({ title, label, onClose, busy, wide, children }) => {
  const ref = useRef<HTMLDivElement>(null);
  const live = useRef({ onClose, busy });
  live.current = { onClose, busy };

  useEffect(() => {
    const id = Symbol('modal');
    const prev = document.activeElement as HTMLElement | null;
    stack.push(id);
    ref.current?.focus();
    const h = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || stack[stack.length - 1] !== id || live.current.busy) return;
      live.current.onClose();
    };
    window.addEventListener('keydown', h);
    return () => {
      window.removeEventListener('keydown', h);
      const i = stack.indexOf(id);
      if (i >= 0) stack.splice(i, 1);
      if (prev && document.contains(prev)) prev.focus();
    };
  }, []);

  return (
    <div
      ref={ref}
      tabIndex={-1}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 focus:outline-none"
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
