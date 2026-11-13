import * as Crypto from 'expo-crypto';
import { useCallback, useEffect, useState } from 'react';
import { Linking } from 'react-native';
import { Button, Card, Screen, Text } from '../../components/ui';
import { fmtUtcTime } from '../../lib/time';
import { useTheme } from '../../theme';
import { useAttendanceGate } from '../attendance/gate';
import { flagNotice, submitPunch, type Fix, type PunchOutcome, type SelfieInput } from './api';
import { useInvalidateAfterPunch, usePunchQueueSync } from './hooks';
import { checkPermission, getFix, requestPermission, type PermState } from './location';
import { PendingBanner } from './PendingBanner';
import { RunningLateCard } from './RunningLateCard';
import { SelfieCapture } from './SelfieCapture';

export function PunchScreen() {
  const { colors } = useTheme();
  const { today, query } = useAttendanceGate();
  const invalidate = useInvalidateAfterPunch();
  usePunchQueueSync();
  const [perm, setPerm] = useState<PermState>('unknown');
  const [fix, setFix] = useState<Fix | null>(null);
  const [fixError, setFixError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [selfie, setSelfie] = useState<SelfieInput | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PunchOutcome | null>(null);

  const att = today?.attendance ?? null;
  const kind = !att ? 'in' : !att.punch_out_time ? 'out' : null;

  const locate = useCallback(async () => {
    setLocating(true);
    setFixError(null);
    try {
      let p = await checkPermission();
      if (p !== 'granted') p = await requestPermission();
      setPerm(p);
      if (p === 'granted') setFix(await getFix());
    } catch {
      setFixError("Couldn't get your location. Move to an open area and try again.");
    } finally {
      setLocating(false);
    }
  }, []);
  useEffect(() => {
    const id = setTimeout(() => void locate(), 0);
    return () => clearTimeout(id);
  }, [locate]);

  const doPunch = async (s: SelfieInput | null) => {
    if (!kind) return;
    setCapturing(false);
    setSelfie(s);
    setBusy(true);
    try {
      // Refresh the fix right before punching so the geofence check uses current coordinates.
      let f = fix;
      try { if (perm === 'granted') f = await getFix(); } catch { /* fall back to the last fix */ }
      setFix(f);
      const out = await submitPunch({ kind, fix: f, selfie: s, uuid: () => Crypto.randomUUID() });
      setResult(out);
      if (out.status === 'error' && out.needsSelfie) setCapturing(true);
      if (out.status !== 'error') { setSelfie(null); await invalidate(); }
    } finally {
      setBusy(false);
    }
  };

  const statusText = !today
    ? query.isError ? 'Status unavailable' : 'Checking…'
    : !att ? 'Not punched in' : att.punch_out_time ? `Punched out at ${fmtUtcTime(att.punch_out_time)}` : `Punched in at ${fmtUtcTime(att.captured_at)}`;

  return (
    <Screen scroll style={{ gap: 12 }}>
      <Card style={{ gap: 8 }}>
        <Text weight="600" size={18}>Punch</Text>
        <Text testID="punch-tab-status">{statusText}</Text>
      </Card>

      <PendingBanner />

      <Card style={{ gap: 6 }}>
        <Text weight="600">Location</Text>
        {perm === 'blocked' ? (
          <>
            <Text testID="loc-blocked">Location access is turned off. Enable it in Settings to punch.</Text>
            <Button variant="secondary" title="Open Settings" onPress={() => void Linking.openSettings()} />
          </>
        ) : perm === 'denied' ? (
          <>
            <Text testID="loc-denied">We need your location to verify where you punch.</Text>
            <Button testID="loc-allow" title="Allow location" onPress={() => void locate()} />
          </>
        ) : fix ? (
          <>
            <Text testID="loc-fix">{`${fix.latitude.toFixed(5)}, ${fix.longitude.toFixed(5)}`}</Text>
            <Text muted size={13} testID="loc-accuracy">{fix.accuracy != null ? `Accuracy ±${Math.round(fix.accuracy)} m` : 'Accuracy unknown'}</Text>
            {fix.isMock ? <Text testID="mock-warning" style={{ color: colors.danger }} size={13}>Mock location detected. This punch will be flagged.</Text> : null}
          </>
        ) : (
          <Text muted testID="loc-pending">{locating ? 'Getting your location…' : fixError ?? 'Location not available yet'}</Text>
        )}
        {perm === 'granted' ? <Button variant="secondary" title="Refresh location" loading={locating} onPress={() => void locate()} /> : null}
      </Card>

      {capturing ? (
        <SelfieCapture onDone={(s) => void doPunch(s)} onCancel={() => setCapturing(false)} />
      ) : kind ? (
        <Button
          testID="punch-button"
          title={kind === 'in' ? 'Punch in' : 'Punch out'}
          loading={busy}
          disabled={!today}
          onPress={() => setCapturing(true)}
        />
      ) : today ? (
        <Text muted testID="punch-done">You have completed your punches for today.</Text>
      ) : null}
      {selfie && !capturing ? <Text size={12} muted>Selfie attached</Text> : null}

      {result ? <ResultNotice result={result} /> : null}

      <RunningLateCard isMarked={today?.is_marked} />
    </Screen>
  );
}

function ResultNotice({ result }: { result: PunchOutcome }) {
  const { colors } = useTheme();
  if (result.status === 'ok') {
    const flag = flagNotice(result.flag);
    return (
      <Card testID="punch-result" style={{ gap: 4 }}>
        <Text weight="600">Punch recorded</Text>
        {flag ? <Text testID="punch-flag" style={{ color: colors.danger }}>{flag}</Text> : null}
      </Card>
    );
  }
  if (result.status === 'queued') {
    return (
      <Card testID="punch-queued" style={{ gap: 4 }}>
        <Text weight="600">Saved offline</Text>
        <Text size={14}>{"We couldn't reach the server. Your punch is saved and will sync automatically."}</Text>
      </Card>
    );
  }
  return (
    <Card testID="punch-error" style={{ borderColor: colors.danger, gap: 4 }}>
      <Text weight="600">Punch not accepted</Text>
      <Text testID="punch-error-message">{result.error.message}</Text>
      {result.error.code ? <Text muted size={12} testID="punch-error-code">{result.error.code}</Text> : null}
    </Card>
  );
}
