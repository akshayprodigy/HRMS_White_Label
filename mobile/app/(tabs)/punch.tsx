import { Card, Screen, Text } from '../../src/components/ui';
import { useAttendanceGate } from '../../src/features/attendance/gate';
import { fmtUtcTime } from '../../src/lib/time';
import { t } from '../../src/i18n';

/** Task 7 replaces the body with the geofence/selfie punch flow; the status card stays. */
export default function PunchTab() {
  const { today, query } = useAttendanceGate();
  const att = today?.attendance ?? null;
  const status = !today
    ? query.isError ? 'Status unavailable' : 'Checking…'
    : !att ? 'Not punched in' : att.punch_out_time ? `Punched out at ${fmtUtcTime(att.punch_out_time)}` : `Punched in at ${fmtUtcTime(att.captured_at)}`;
  return (
    <Screen>
      <Card style={{ gap: 8 }}>
        <Text weight="600" size={18}>Punch</Text>
        <Text testID="punch-tab-status">{status}</Text>
        <Text muted>{t('common.comingSoon')}</Text>
      </Card>
    </Screen>
  );
}
