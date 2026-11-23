import { useState } from 'react';
import { normalizeError } from '../../api/client';
import { Button, Card, Text, TextInput } from '../../components/ui';
import { fmtUtcDate } from '../../lib/time';
import { useTheme } from '../../theme';
import { fmtRange, KIND_LABEL } from '../work-location/logic';
import type { TeamPick, TeamWorkLocation } from './api';
import { useDecidePick, useDecideWorkLocation, useTeamPicks, useTeamWorkLocation } from './hooks';

function DecideRow({ testKey, title, lines, decide, pending }: {
  testKey: string; title: string; lines: string[];
  decide: (approve: boolean, note: string) => Promise<unknown>; pending: boolean;
}) {
  const { colors } = useTheme();
  const [mode, setMode] = useState<'approve' | 'reject' | null>(null);
  const [note, setNote] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    if (!mode) return;
    setErr(null);
    try {
      await decide(mode === 'approve', note);
    } catch (e) {
      setErr(normalizeError(e).message); // 409 and friends, verbatim
      setMode(null);
    }
  };
  return (
    <Card testID={`team-${testKey}`} style={{ gap: 4 }}>
      <Text weight="600">{title}</Text>
      {lines.filter(Boolean).map((l) => <Text key={l} muted size={13}>{l}</Text>)}
      {mode ? (
        <>
          <TextInput testID={`team-note-${testKey}`} label="Note (optional)" value={note} onChangeText={setNote} maxLength={500} multiline />
          <Button testID={`team-confirm-${testKey}`} title={mode === 'approve' ? 'Confirm approve' : 'Confirm reject'} loading={pending} onPress={() => void go()} />
          <Button testID={`team-back-${testKey}`} variant="secondary" title="Back" onPress={() => setMode(null)} />
        </>
      ) : (
        <>
          <Button testID={`team-approve-${testKey}`} title="Approve" onPress={() => setMode('approve')} />
          <Button testID={`team-reject-${testKey}`} variant="secondary" title="Reject" onPress={() => setMode('reject')} />
        </>
      )}
      {err ? <Text testID={`team-error-${testKey}`} accessibilityRole="alert" size={13} style={{ color: colors.danger }}>{err}</Text> : null}
    </Card>
  );
}

const wlLines = (r: TeamWorkLocation) => [fmtRange(r), r.place ?? '', r.purpose];

export function TeamRequests() {
  const { colors } = useTheme();
  const wl = useTeamWorkLocation();
  const picks = useTeamPicks();
  const decideWl = useDecideWorkLocation();
  const decidePk = useDecidePick();
  const wlRows = wl.data ?? [];
  const pickRows = picks.data ?? [];
  const errors = [wl.error, picks.error].filter(Boolean).map((e) => normalizeError(e).message);
  if (!wlRows.length && !pickRows.length && !errors.length) return null; // not an approver, or nothing waiting: hide quietly
  return (
    <>
      <Text weight="700" testID="team-requests-title">Team requests</Text>
      <Text muted size={13}>Nothing is taken until you approve it.</Text>
      {errors.map((m) => <Text key={m} testID="team-requests-error" accessibilityRole="alert" size={13} style={{ color: colors.danger }}>{m}</Text>)}
      {wlRows.map((r) => (
        <DecideRow key={`wl-${r.id}`} testKey={`wl-${r.id}`} title={`${r.user_name ?? 'Employee'} · ${KIND_LABEL[r.kind] ?? r.kind}`} lines={wlLines(r)} pending={decideWl.isPending}
          decide={(approve, note) => decideWl.mutateAsync({ id: r.id, approve, note })} />
      ))}
      {pickRows.map((p: TeamPick) => (
        <DecideRow key={`pick-${p.id}`} testKey={`pick-${p.id}`} title={`${p.user_name ?? 'Employee'} · Optional holiday`}
          lines={[p.holiday ? `${p.holiday.name} · ${fmtUtcDate(p.holiday.date)}` : '', p.reason ?? '']} pending={decidePk.isPending}
          decide={(approve, note) => decidePk.mutateAsync({ id: p.id, approve, note })} />
      ))}
    </>
  );
}
