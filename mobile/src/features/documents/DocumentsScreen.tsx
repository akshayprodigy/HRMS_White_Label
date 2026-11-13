import { useQuery } from '@tanstack/react-query';
import { RefreshControl } from 'react-native';
import { normalizeError } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { Button, Card, Screen, Text } from '../../components/ui';
import { fmtUtcDate } from '../../lib/time';
import { useDownload } from '../../lib/useDownload';
import { useTheme } from '../../theme';
import { GateInline } from '../attendance/GateNotice';
import { isGateError, retryUnlessGate } from '../attendance/gate';
import { documentDownloadPath, DOCUMENTS_KEY, fetchForm16, fetchMyDocuments, form16DownloadPath, form16FileName, FORM16_KEY } from './api';

export function DocumentsScreen() {
  const { colors } = useTheme();
  const { user } = useAuth();
  const f16 = useQuery({ queryKey: FORM16_KEY, queryFn: fetchForm16, enabled: !!user, retry: retryUnlessGate });
  const docs = useQuery({ queryKey: DOCUMENTS_KEY, queryFn: fetchMyDocuments, enabled: !!user, retry: retryUnlessGate });
  const dl = useDownload();

  if ((f16.error && isGateError(f16.error)) || (docs.error && isGateError(docs.error))) {
    return (
      <Screen>
        <GateInline />
      </Screen>
    );
  }
  const refresh = () => void Promise.all([f16.refetch(), docs.refetch()]);
  const busy = dl.busyKey !== null;
  const forms = f16.data ?? [];
  const files = docs.data ?? [];

  return (
    <Screen scroll refreshControl={<RefreshControl refreshing={f16.isRefetching || docs.isRefetching} onRefresh={refresh} />} style={{ gap: 12 }}>
      {dl.error ? <Text testID="documents-download-error" accessibilityRole="alert" style={{ color: colors.danger }}>{dl.error}</Text> : null}

      <Text weight="700" size={18}>Form 16</Text>
      {f16.isPending ? <Text muted>Loading…</Text> : null}
      {f16.error && !f16.data ? <Text testID="form16-error" accessibilityRole="alert" style={{ color: colors.danger }}>{normalizeError(f16.error).message}</Text> : null}
      {f16.data && forms.length === 0 ? <Card><Text testID="form16-empty" muted>No Form 16 available yet.</Text></Card> : null}
      {forms.map((f) => (
        <Card key={f.id} testID={`form16-${f.id}`} style={{ gap: 4 }}>
          <Text weight="600">{`FY 20${f.fy}`}</Text>
          <Text muted size={13}>
            {f.reference_number ? `${f.reference_number} · ` : ''}
            {f.status}
            {f.issued_at ? ` · Issued ${fmtUtcDate(f.issued_at)}` : ''}
          </Text>
          {f.part_b_url ? (
            <Button
              testID={`form16-download-${f.id}`}
              variant="secondary"
              title={dl.busyKey === `f${f.id}` ? 'Preparing…' : 'Download PDF'}
              loading={dl.busyKey === `f${f.id}`}
              disabled={busy}
              onPress={() => void dl.run(`f${f.id}`, form16DownloadPath(f.id), form16FileName(f))}
            />
          ) : (
            <Text muted size={13}>Not generated yet.</Text>
          )}
        </Card>
      ))}

      <Text weight="700" size={18} style={{ marginTop: 8 }}>My documents</Text>
      {docs.isPending ? <Text muted>Loading…</Text> : null}
      {docs.error && !docs.data ? <Text testID="documents-error" accessibilityRole="alert" style={{ color: colors.danger }}>{normalizeError(docs.error).message}</Text> : null}
      {docs.data && files.length === 0 ? <Card><Text testID="documents-empty" muted>No documents on your profile yet.</Text></Card> : null}
      {files.map((d) => (
        <Card key={d.id} testID={`document-${d.id}`} style={{ gap: 4 }}>
          <Text weight="600">{d.doc_type}</Text>
          <Text muted size={13}>
            {d.original_filename}
            {d.uploaded_at ? ` · ${fmtUtcDate(d.uploaded_at)}` : ''}
          </Text>
          <Text size={13} style={{ color: d.verification_status === 'rejected' ? colors.danger : colors.mutedText }}>
            {d.verification_status === 'rejected' ? `Rejected${d.rejection_reason ? `: ${d.rejection_reason}` : ''}` : d.verification_status === 'verified' ? 'Verified' : 'Pending verification'}
          </Text>
          <Button
            testID={`document-download-${d.id}`}
            variant="secondary"
            title={dl.busyKey === `d${d.id}` ? 'Preparing…' : 'Download'}
            loading={dl.busyKey === `d${d.id}`}
            disabled={busy}
            onPress={() => void dl.run(`d${d.id}`, documentDownloadPath(d.id), d.original_filename)}
          />
        </Card>
      ))}
    </Screen>
  );
}
