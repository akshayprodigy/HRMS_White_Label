import * as Crypto from 'expo-crypto';
import { useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Linking } from 'react-native';
import { Button, Card, Screen, Text } from '../../components/ui';
import { fmtOrgTime, useOrgTime } from '../../lib/org-time';
import { useTheme } from '../../theme';
import { useAttendanceGate } from '../attendance/gate';
import { flagNotice, submitPunch, type Fix, type PunchOutcome, type SelfieInput } from './api';
import { useInvalidateAfterPunch, usePunchQueue, useSyncNow } from './hooks';
import { checkPermission, getFix, requestPermission, type PermState } from './location';
import { PendingBanner } from './PendingBanner';
import { ApprovedBanner } from '../work-location/ApprovedBanner';
import { RunningLateCard } from './RunningLateCard';
import { SelfieCapture } from './SelfieCapture';

export function PunchScreen() {
  useOrgTime();
  const { colors } = useTheme();
  const router = useRouter();
  const { today, query } = useAttendanceGate();
  const invalidate = useInvalidateAfterPunch();
  const { items: pending, rejected } = usePunchQueue();
  const syncNow = useSyncNow();
  const [perm, setPerm] = useState<PermState>('unknown');
  const [fix, setFix] = useState<Fix | null>(null);
  const [fixError, setFixError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [selfie, setSelfie] = useState<SelfieInput | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PunchOutcome | null>(null);
  const tapAt = useRef<string | null>(null);

  const att = today?.attendance ?? null;
  // Effective state = server record + not-yet-synced punches (queued punches are not on the server yet).
  const lastPending = pending.length ? pending[pending.length - 1] : null;
  const kind: 'in' | 'out' | null = lastPending
    ? (lastPending.kind === 'in' ? 'out' : null)
    : !att ? 'in' : !att.punch_out_time ? 'out' : null;

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
    const capturedAt = tapAt.current ?? new Date().toISOString();
    setCapturing(false);
    setSelfie(s);
    setBusy(true);
    try {
      // Always a fresh reading, never a stale one: if it fails we punch WITHOUT coordinates (the server flags it).
      let f: Fix | null = null;
      setFixError(null);
      if (perm === 'granted') {
        try { f = await getFix(); } catch { setFixError("Couldn't get your location, so this punch is sent without it and will be flagged for review."); }
      }
      setFix(f);
      const out = await submitPunch({ kind, fix: f, selfie: s, uuid: () => Crypto.randomUUID(), capturedAt });
      setResult(out);
      if (out.status === 'error' && out.needsSelfie) setCapturing(true);
      if (out.status !== 'error') {
        setSelfie(null);
        tapAt.current = null;
        await invalidate();
        if (out.status === 'queued') void syncNow(out.behind).catch(() => undefined);
      }
    } finally {
      setBusy(false);
    }
  };

  const statusText = lastPending
    ? lastPending.kind === 'in' ? 'Punched in (pending sync)' : 'Punched out (pending sync)'
    : !today
    ? query.isError ? 'Status unavailable' : 'Checking…'
    : !att ? 'Not punched in' : att.punch_out_time ? `Punched out at ${fmtOrgTime(att.punch_out_time)}` : `Punched in at ${fmtOrgTime(att.captured_at)}`;

  return (
    <Screen scroll style={{ gap: 12 }}>
      <Card style={{ gap: 8 }}>
        <Text weight="600" size={18}>Punch</Text>
        <Text testID="punch-tab-status">{statusText}</Text>
      </Card>

      <PendingBanner />
      <ApprovedBanner />

      <Card style={{ gap: 6 }}>
        <Text weight="600">Location</Text>
        {perm === 'blocked' ? (
          <>
            <Text testID="loc-blocked">Location access is turned off. Enable it in Settings, or punch without it and the punch will be flagged for review.</Text>
            <Button variant="secondary" title="Open Settings" onPress={() => void Linking.openSettings()} />
          </>
        ) : perm === 'denied' ? (
          <>
            <Text testID="loc-denied">We need your location to verify where you punch. If you punch without it, the punch will be flagged for review.</Text>
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

      {perm !== 'granted' && perm !== 'unknown' && kind ? <Text size={13} testID="no-location-warning" style={{ color: colors.danger }}>No location: this punch will be flagged.</Text> : null}
      {capturing ? (
        <SelfieCapture onDone={(s) => void doPunch(s)} onCancel={() => setCapturing(false)} />
      ) : kind ? (
        <Button
          testID="punch-button"
          title={kind === 'in' ? 'Punch in' : 'Punch out'}
          loading={busy}
          disabled={!today && !lastPending}
          onPress={() => { tapAt.current = new Date().toISOString(); setCapturing(true); }}
        />
      ) : today || lastPending ? (
        <Text muted testID="punch-done">You have completed your punches for today.</Text>
      ) : null}
      {selfie && !capturing ? <Text size={12} muted>Selfie attached</Text> : null}

      {result ? <ResultNotice result={result} pendingIds={pending.map((p) => p.client_uuid)} rejectedIds={rejected.map((r) => r.client_uuid)} /> : null}

      <RunningLateCard isMarked={today?.is_marked} />
      <Button testID="working-remotely" variant="secondary" title="Working remotely?" onPress={() => router.push('/work-location' as never)} />
    </Screen>
  );
}

function ResultNotice({ result, pendingIds, rejectedIds }: { result: PunchOutcome; pendingIds: string[]; rejectedIds: string[] }) {
  const { colors } = useTheme();
  if (result.status === 'ok') {
    const flag = flagNotice(result.flag);
    return (
      <Card testID="punch-result" accessibilityRole="alert" style={{ gap: 4 }}>
        <Text weight="600">Punch recorded</Text>
        {/* The punch SUCCEEDED; a flag is only a review note, so it is neutral (not the error red). */}
        {flag ? <Text testID="punch-flag" muted size={14}>{flag}</Text> : null}
      </Card>
    );
  }
  if (result.status === 'already') {
    return (
      <Card testID="punch-already" accessibilityRole="alert" style={{ gap: 4 }}>
        <Text weight="600">Already recorded</Text>
        <Text size={14}>This punch was already on record, so nothing changed.</Text>
      </Card>
    );
  }
  if (result.status === 'queued') {
    const id = result.item.client_uuid;
    // Left the queue: a rejection is shown by the pending banner; anything else was accepted by the server.
    if (!pendingIds.includes(id)) {
      if (rejectedIds.includes(id)) return null;
      return (
        <Card testID="punch-synced" accessibilityRole="alert" style={{ gap: 4 }}>
          <Text weight="600">Synced</Text>
          <Text size={14}>Your offline punch has been sent to the server.</Text>
        </Card>
      );
    }
    return (
      <Card testID="punch-queued" accessibilityRole="alert" style={{ gap: 4 }}>
        <Text weight="600">Saved offline</Text>
        <Text size={14}>{result.behind ? 'Earlier punches are still waiting to sync. This one is saved behind them and will sync in order.' : "We couldn't reach the server. Your punch is saved and will sync automatically."}</Text>
      </Card>
    );
  }
  return (
    <Card testID="punch-error" accessibilityRole="alert" style={{ borderColor: colors.danger, gap: 4 }}>
      <Text weight="600">Punch not accepted</Text>
      <Text testID="punch-error-message">{result.error.message}</Text>
      {result.error.code ? <Text muted size={12} testID="punch-error-code">{result.error.code}</Text> : null}
    </Card>
  );
}
