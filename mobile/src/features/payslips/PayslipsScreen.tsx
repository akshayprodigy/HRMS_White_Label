import { useQuery } from '@tanstack/react-query';
import { RefreshControl, View } from 'react-native';
import { normalizeError } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { Button, Card, Screen, Text } from '../../components/ui';
import { fmtUtcDate } from '../../lib/time';
import { useDownload } from '../../lib/useDownload';
import { useTheme } from '../../theme';
import { GateInline } from '../attendance/GateNotice';
import { isGateError, retryUnlessGate } from '../attendance/gate';
import { fetchPayslips, fmtRupees, monthLabel, payslipDownloadPath, payslipFileName, PAYSLIPS_KEY } from './api';

export function PayslipsScreen() {
  const { colors } = useTheme();
  const { user } = useAuth();
  const q = useQuery({ queryKey: PAYSLIPS_KEY, queryFn: fetchPayslips, enabled: !!user, retry: retryUnlessGate });
  const dl = useDownload();

  if (q.error && isGateError(q.error)) {
    return (
      <Screen>
        <GateInline />
      </Screen>
    );
  }
  const slips = q.data ?? [];
  return (
    <Screen scroll refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => void q.refetch()} />} style={{ gap: 12 }}>
      {q.isPending ? <Text muted testID="payslips-loading">Loading payslips…</Text> : null}
      {q.error && !q.data ? (
        <Card style={{ gap: 8 }}>
          <Text testID="payslips-error" accessibilityRole="alert" style={{ color: colors.danger }}>{normalizeError(q.error).message}</Text>
          <Button variant="secondary" title="Try again" onPress={() => void q.refetch()} />
        </Card>
      ) : null}
      {dl.error ? <Text testID="payslips-download-error" accessibilityRole="alert" style={{ color: colors.danger }}>{dl.error}</Text> : null}
      {q.data && slips.length === 0 ? (
        <Card><Text testID="payslips-empty" muted>No payslips yet. Once HR publishes a payroll run, your payslip appears here.</Text></Card>
      ) : null}
      {slips.map((s) => (
        <Card key={s.id} testID={`payslip-${s.id}`} style={{ gap: 6 }}>
          <Text size={12} weight="600" muted>{monthLabel(s).toUpperCase()}</Text>
          <Text size={22} weight="700">{fmtRupees(s.net_pay)}</Text>
          <Text muted size={13}>
            Gross {fmtRupees(s.gross_pay)}
            {s.advance_deduction > 0 ? ` · Advance ${fmtRupees(s.advance_deduction)}` : ''}
          </Text>
          <Text muted size={13}>
            {s.payable_days} days paid{s.lop_days > 0 ? ` · ${s.lop_days} LOP` : ''}
            {s.published_at ? ` · Published ${fmtUtcDate(s.published_at)}` : ''}
          </Text>
          <View style={{ marginTop: 6 }}>
            <Button
              testID={`payslip-download-${s.id}`}
              variant="secondary"
              title={dl.busyKey === `p${s.id}` ? 'Preparing…' : 'Download PDF'}
              loading={dl.busyKey === `p${s.id}`}
              disabled={dl.busyKey !== null}
              onPress={() => void dl.run(`p${s.id}`, payslipDownloadPath(s.id), payslipFileName(s))}
            />
          </View>
        </Card>
      ))}
    </Screen>
  );
}
