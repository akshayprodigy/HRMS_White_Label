/**
 * Reports workspace: switches between catalog and viewer.
 */
import React, { useState } from 'react';
import { ReportsCatalogView } from './reports-catalog';
import { ReportViewer } from './reports-viewer';

interface ReportDesc {
  key: string; name: string; description: string;
  category: string; permission: string;
  is_sensitive: boolean; manager_scoped: boolean;
  filters: any[];
}

export const ReportsWorkspace: React.FC = () => {
  const [current, setCurrent] = useState<{ desc: ReportDesc; initial?: any } | null>(null);

  if (current) {
    return <ReportViewer
      report={current.desc}
      initialFilters={current.initial}
      onBack={() => setCurrent(null)}
    />;
  }
  return <ReportsCatalogView
    onOpenReport={(desc, initial) => setCurrent({ desc, initial })}
  />;
};
