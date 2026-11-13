import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, AppState, Linking, Switch, View } from 'react-native';
import { normalizeError } from '../../api/client';
import { Button, Card, Screen, Text } from '../../components/ui';
import { fmtUtcTime } from '../../lib/time';
import { useTheme } from '../../theme';
import { deleteMyData, giveConsent, MY_STATUS_KEY, revokeConsent } from './api';
import { MyHistory } from './MyHistory';
import { useMyTrackingStatus, useRecheckTracking } from './hooks';
import { beginRevoke, endRevoke, getPermissionLevel, requestPermissions, stopTracking, type PermissionLevel } from './tracking';
import { decideTracking, type Decision } from './window';

export const CONSENT_POINTS = [
  'Only during your rostered shifts: from 30 minutes before the shift starts until 30 minutes after it ends. Never on days off, holidays or leave.',
  'What is collected: your phone\'s location (coordinates, accuracy and speed) and the time of each reading.',
  'Who sees it: your scheduler and managers who are responsible for your team. Every view is recorded in an audit log.',
  'It is kept for 30 days and then deleted automatically. You can also delete it yourself at any time.',
  'You can revoke consent at any time here. Tracking stops immediately and nothing more is collected.',
];

const WHY: Record<Decision['reason'] | 'no_permission', string> = {
  in_window: 'Sharing now: you are inside your shift window.',
  before_window: 'Waiting: your shift window has not started yet.',
  after_window: 'Not sharing: your shift window has ended.',
  no_window: 'Not sharing: you have no rostered shift today.',
  disabled: 'Not sharing.',
  no_consent: 'Not sharing.',
  unknown: 'Not sharing.',
  no_permission: 'Not sharing: location permission is off for this app.',
};

export function ConsentScreen() {
  const { colors } = useTheme();
  const qc = useQueryClient();
  const q = useMyTrackingStatus();
  const recheck = useRecheckTracking();
  const [perm, setPerm] = useState<PermissionLevel | null>(null);
  const [busy, setBusy] = useState<null | 'consent' | 'revoke' | 'delete' | 'perm'>(null);
  const [msg, setMsg] = useState<{ kind: 'error' | 'info'; text: string } | null>(null);
  const lock = useRef(false);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30_000); return () => clearInterval(t); }, []);

  const refreshPerm = useCallback(() => { void getPermissionLevel().then(setPerm).catch(() => setPerm('none')); }, []);
  useEffect(() => {
    refreshPerm();
    const sub = AppState.addEventListener('change', (s) => { if (s === 'active') refreshPerm(); });
    return () => sub.remove();
  }, [refreshPerm]);

  /** Double-tap guard: a ref flips synchronously, unlike state. */
  const act = useCallback(async (kind: NonNullable<typeof busy>, fn: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(kind);
    setMsg(null);
    try {
      await fn();
    } catch (e) {
      setMsg({ kind: 'error', text: normalizeError(e).message });
    } finally {
      await qc.invalidateQueries({ queryKey: MY_STATUS_KEY }).catch(() => undefined);
      lock.current = false;
      setBusy(null);
    }
  }, [qc]);

  const agree = () => act('consent', async () => {
    await giveConsent();
    const level = await requestPermissions(); // the explanation above has been read; now the OS prompts
    setPerm(level);
    if (level === 'none') setMsg({ kind: 'info', text: 'Consent saved, but location permission was not granted, so nothing is shared. You can allow it in Settings.' });
    await recheck();
  });
  const allowAlways = () => act('perm', async () => {
    setPerm(await requestPermissions());
    await recheck();
  });
  const revoke = () => Alert.alert(
    'Stop sharing location?',
    'Tracking stops immediately and any location waiting to be sent is discarded. Already stored history stays until it expires after 30 days, unless you delete it.',
    [
      { text: 'Keep sharing', style: 'cancel' },
      {
        text: 'Revoke consent',
        style: 'destructive',
        onPress: () => void act('revoke', async () => {
          beginRevoke(); // the lifecycle must not restart tracking on the stale "consented" status meanwhile
          try {
            await stopTracking({ clear: true }); // local first: nothing more may leave the phone even if the call fails
            await revokeConsent();
          } finally {
            endRevoke();
            // Success: status now says not consented, so everything stays off. Failure: consent is still active, so
            // tracking resumes legitimately. Either way the device is made to match the server.
            await recheck().catch(() => null);
          }
        }),
      },
    ],
  );
  const eraseData = () => Alert.alert(
    'Delete my location data?',
    'This permanently deletes the location history stored for you on the server. It cannot be undone.',
    [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => void act('delete', async () => {
          const r = await deleteMyData();
          setMsg({ kind: 'info', text: `Deleted ${r.deleted?.pings ?? 0} location point${r.deleted?.pings === 1 ? '' : 's'}.` });
        }),
      },
    ],
  );

  if (q.isPending) return <Screen><Text muted testID="tracking-loading">Loading…</Text></Screen>;
  if (q.error || !q.data) {
    return (
      <Screen>
        <Card style={{ gap: 8 }}>
          <Text testID="tracking-error" accessibilityRole="alert" style={{ color: colors.danger }}>{normalizeError(q.error).message}</Text>
          <Button variant="secondary" title="Try again" onPress={() => void q.refetch()} />
        </Card>
      </Screen>
    );
  }
  const s = q.data;
  const decision = decideTracking(s, now);
  const sharing = decision.run && perm !== 'none';
  const w = s.window;

  return (
    <Screen scroll style={{ gap: 12 }}>
      {msg ? (
        <Card><Text testID={msg.kind === 'error' ? 'tracking-msg-error' : 'tracking-msg'} accessibilityRole={msg.kind === 'error' ? 'alert' : 'summary'} style={msg.kind === 'error' ? { color: colors.danger } : undefined}>{msg.text}</Text></Card>
      ) : null}

      <Card style={{ gap: 8 }}>
        <Text weight="600" size={18}>Shift location sharing</Text>
        {!s.required ? (
          <Text testID="tracking-status" muted>Not turned on for your role. Your company has not enabled location sharing for you, so nothing is collected.</Text>
        ) : !s.consented ? (
          <Text testID="tracking-status" muted>Your company has turned on shift location sharing for you. It starts only after you agree below.</Text>
        ) : (
          <>
            <Text testID="tracking-status" weight="600">{sharing ? 'Consented · sharing now' : 'Consented · idle'}</Text>
            <Text testID="tracking-why" muted>{perm === 'none' && decision.run ? WHY.no_permission : WHY[decision.reason]}</Text>
            {w ? <Text muted size={13}>Shift {fmtUtcTime(w.shift_start)} to {fmtUtcTime(w.shift_end)} (sharing runs 30 min either side).</Text> : null}
          </>
        )}
      </Card>

      {s.required && !s.consented ? (
        <Card style={{ gap: 10 }} testID="tracking-explainer">
          <Text weight="600">Before you agree</Text>
          {CONSENT_POINTS.map((p) => <Text key={p} size={14}>{`• ${p}`}</Text>)}
          <Text muted size={13}>Next, your phone asks for location access. Choose &quot;Allow all the time&quot; (Android) or &quot;Always&quot; (iOS) so sharing works with the screen off. If you only allow while using the app, location is shared only while the app is open.</Text>
          <Button testID="tracking-agree" title="I agree" loading={busy === 'consent'} disabled={busy !== null} onPress={() => void agree()} />
        </Card>
      ) : null}

      {s.consented ? (
        <Card style={{ gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <Text style={{ flex: 1 }}>Share my location during shifts</Text>
            <Switch testID="tracking-switch" accessibilityLabel="Share my location during shifts" value disabled={busy !== null} onValueChange={(v) => { if (!v) revoke(); }} />
          </View>
          {perm === 'none' ? (
            <>
              <Text testID="tracking-perm-warning" size={13} style={{ color: colors.danger }}>Location permission is off, so nothing can be shared.</Text>
              <Button testID="tracking-allow" variant="secondary" title="Allow location" loading={busy === 'perm'} disabled={busy !== null} onPress={() => void allowAlways()} />
              <Button testID="tracking-open-settings" variant="secondary" title="Open Settings" onPress={() => void Linking.openSettings()} />
            </>
          ) : perm === 'foreground' ? (
            <>
              <Text testID="tracking-perm-warning" size={13}>Background location is not allowed, so your location is shared only while the app is open. For sharing with the screen off, choose &quot;Allow all the time&quot; / &quot;Always&quot;.</Text>
              <Button testID="tracking-allow-always" variant="secondary" title="Allow all the time" loading={busy === 'perm'} disabled={busy !== null} onPress={() => void allowAlways()} />
              <Button testID="tracking-open-settings" variant="secondary" title="Open Settings" onPress={() => void Linking.openSettings()} />
            </>
          ) : null}
        </Card>
      ) : null}

      {s.required || s.consented ? <MyHistory /> : null}

      {s.required || s.consented ? (
        <Card style={{ gap: 8 }}>
          <Text weight="600">Your data</Text>
          <Text muted size={13}>Location history is kept for 30 days. You can erase what is stored for you now.</Text>
          <Button testID="tracking-delete-data" variant="secondary" title="Delete my location data" loading={busy === 'delete'} disabled={busy !== null} onPress={eraseData} />
        </Card>
      ) : null}
    </Screen>
  );
}
