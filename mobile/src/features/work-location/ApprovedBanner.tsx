import { Card, Text } from '../../components/ui';
import { useOrgTime } from '../../lib/org-time';
import { useMyRequests } from './hooks';
import { approvedBannerText, approvedToday } from './logic';

/** Punch tab: shown only when today (org-local) has an APPROVED request. Nothing for pending. */
export function ApprovedBanner() {
  const { today, ready } = useOrgTime();
  const q = useMyRequests();
  const r = ready ? approvedToday(q.data, today) : null;
  if (!r) return null;
  return (
    <Card testID="wl-approved-banner" accessibilityRole="summary">
      <Text weight="600">{approvedBannerText(r)}</Text>
    </Card>
  );
}
