import React from 'react';
import { cn } from '../ui-elements';

export type RosterView = 'planner' | 'requests' | 'delegations';

const LABEL: Record<RosterView, string> = {
  planner: 'Planner',
  requests: 'Requests',
  delegations: 'Delegations',
};

interface Props {
  view: RosterView;
  onChange: (v: RosterView) => void;
  showDelegations: boolean;
  pending: number;
}

export const ViewToggle: React.FC<Props> = ({ view, onChange, showDelegations, pending }) => {
  const views: RosterView[] = showDelegations
    ? ['planner', 'requests', 'delegations']
    : ['planner', 'requests'];
  return (
    <div role="group" aria-label="Roster view" className="flex rounded-lg border border-gray-200 overflow-hidden w-fit">
      {views.map((v) => (
        <button
          key={v}
          onClick={() => onChange(v)}
          aria-pressed={view === v}
          className={cn(
            'px-3 py-1.5 text-sm font-medium inline-flex items-center gap-1.5',
            view === v ? 'bg-indigo-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
          )}
        >
          {LABEL[v]}
          {v === 'requests' && pending > 0 && (
            <span
              aria-label={`${pending} pending`}
              className="w-5 h-5 rounded-full bg-red-600 text-white text-[10px] inline-flex items-center justify-center"
            >
              {pending}
            </span>
          )}
        </button>
      ))}
    </div>
  );
};
