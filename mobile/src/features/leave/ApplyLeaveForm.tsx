import { useRef, useState } from 'react';
import { Pressable, Switch, View } from 'react-native';
import { normalizeError } from '../../api/client';
import { Button, Card, Text, TextInput } from '../../components/ui';
import { fmtUtcDate as fmtIsoDate } from '../../lib/time';
import { useTheme } from '../../theme';
import { uploadAttachment, type LeaveType } from './api';
import { useApplyLeave } from './hooks';
import { ProofPicker } from './ProofPicker';
import { buildApplyPayload, certRequired, leaveDays, todayIso, validateLeaveForm, type LeaveFormErrors, type LeaveFormValues } from './validation';

export const EMERGENCY_HELP =
  'Use this for same-day or back-dated leave. Your company sets how many days back you can start (checked when you submit), and your scheduler is alerted to arrange cover. Proof is only needed when this leave type and length require a medical certificate; you can then upload it later from your leave history by the due date shown after you submit, otherwise the leave converts to loss of pay.';

function Chip({ label, selected, onPress, testID }: { label: string; selected: boolean; onPress: () => void; testID?: string }) {
  const { colors } = useTheme();
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={label}
      onPress={onPress}
      style={{ paddingVertical: 8, paddingHorizontal: 14, borderRadius: 20, borderWidth: 1, borderColor: colors.primary, backgroundColor: selected ? colors.primary : 'transparent' }}
    >
      <Text size={14} weight="600" style={{ color: selected ? colors.primaryText : colors.primary }}>{label}</Text>
    </Pressable>
  );
}

const EMPTY: LeaveFormValues = { typeId: null, start: '', end: '', halfDay: false, session: 'morning', reason: '', emergency: false, emergencyContact: '', attachment: null };

export function ApplyLeaveForm({ types, onDone, onCancel, now }: { types: LeaveType[]; onDone: (message: string) => void; onCancel: () => void; now?: () => Date }) {
  const { colors } = useTheme();
  const apply = useApplyLeave();
  const [v, setV] = useState<LeaveFormValues>(EMPTY);
  const [errors, setErrors] = useState<LeaveFormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const inFlight = useRef(false); // synchronous: two taps before a re-render must not submit twice
  const uploaded = useRef<{ uri: string; url: string } | null>(null); // survives a failed apply so a retry does not re-upload
  const set = (p: Partial<LeaveFormValues>) => setV((cur) => ({ ...cur, ...p }));
  const type = types.find((t) => t.id === v.typeId);
  const days = leaveDays(v.start, v.halfDay ? v.start : v.end, v.halfDay);
  const needsCert = certRequired(type, days, v.emergency);
  const deferredCert = v.emergency && !!type?.requires_medical_cert_after && days >= type.requires_medical_cert_after;
  const today = () => todayIso(now?.());

  const submit = async () => {
    if (inFlight.current) return;
    setServerError(null);
    const e = validateLeaveForm(v, type, today());
    setErrors(e);
    if (Object.keys(e).length) return;
    inFlight.current = true;
    try {
      let attachmentUrl: string | null = null;
      const file = type?.requires_medical_cert_after ? v.attachment : null;
      if (file) {
        if (uploaded.current?.uri !== file.uri) uploaded.current = { uri: file.uri, url: await uploadAttachment(file) };
        attachmentUrl = uploaded.current.url;
      }
      const created = await apply.mutateAsync({ payload: buildApplyPayload(v, attachmentUrl), file: null });
      onDone(
        created.proof_due_date
          ? `Leave submitted. Upload your proof by ${fmtIsoDate(created.proof_due_date)}, or it converts to loss of pay.`
          : 'Leave submitted for approval.',
      );
    } catch (err) {
      setServerError(normalizeError(err).message);
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <Card style={{ gap: 12 }} testID="apply-form">
      <Text weight="700" size={18}>Apply for leave</Text>

      <View style={{ gap: 6 }}>
        <Text size={14} weight="600">Leave type</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {types.map((t) => (
            <Chip key={t.id} testID={`type-${t.id}`} label={t.name} selected={v.typeId === t.id} onPress={() => { if (t.id !== v.typeId) set({ typeId: t.id, attachment: null }); }} />
          ))}
        </View>
        {errors.type ? <Text testID="error-type" accessibilityRole="alert" size={13} style={{ color: colors.danger }}>{errors.type}</Text> : null}
      </View>

      <View>
        <TextInput
          label="Start date (YYYY-MM-DD)"
          testID="input-start"
          value={v.start}
          error={errors.start}
          placeholder="2026-11-16"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="numbers-and-punctuation"
          onChangeText={(s) => set({ start: s, ...(v.halfDay ? { end: s } : {}) })}
        />
        <TextInput
          label="End date (YYYY-MM-DD)"
          testID="input-end"
          value={v.halfDay ? v.start : v.end}
          error={errors.end}
          editable={!v.halfDay}
          placeholder="2026-11-16"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="numbers-and-punctuation"
          onChangeText={(s) => set({ end: s })}
        />
        <Button testID="use-today" variant="secondary" title="Use today" onPress={() => set({ start: today(), end: today() })} />
      </View>

      <View style={{ gap: 6 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <Text weight="600">Half day</Text>
          <Switch testID="toggle-half" accessibilityLabel="Half day" value={v.halfDay} onValueChange={(on) => set({ halfDay: on, ...(on ? { end: v.start } : {}) })} />
        </View>
        {v.halfDay ? (
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Chip testID="session-morning" label="Morning" selected={v.session === 'morning'} onPress={() => set({ session: 'morning' })} />
            <Chip testID="session-afternoon" label="Afternoon" selected={v.session === 'afternoon'} onPress={() => set({ session: 'afternoon' })} />
          </View>
        ) : null}
        {errors.half ? <Text testID="error-half" accessibilityRole="alert" size={13} style={{ color: colors.danger }}>{errors.half}</Text> : null}
      </View>

      <TextInput label="Reason" testID="input-reason" value={v.reason} error={errors.reason} multiline onChangeText={(s) => set({ reason: s })} />
      <TextInput label="Emergency contact (optional)" testID="input-contact" value={v.emergencyContact} onChangeText={(s) => set({ emergencyContact: s })} />

      <View style={{ gap: 6 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <Text weight="600" style={{ flex: 1 }}>Emergency (same-day / back-dated)</Text>
          <Switch
            testID="toggle-emergency"
            accessibilityLabel="Emergency leave"
            value={v.emergency}
            onValueChange={(on) => set({ emergency: on, ...(on && !v.start ? { start: today(), end: today() } : {}) })}
          />
        </View>
        {v.emergency ? <Text testID="emergency-help" muted size={13}>{EMERGENCY_HELP}</Text> : null}
      </View>

      {type?.requires_medical_cert_after ? (
        <View style={{ gap: 6 }}>
          <Text size={14} weight="600">{needsCert ? 'Medical certificate (required)' : 'Medical certificate'}</Text>
          {deferredCert ? <Text testID="proof-deferred" muted size={13}>You can attach it now or upload it later by the due date shown after you submit.</Text> : null}
          {!needsCert && !deferredCert ? <Text muted size={13}>{`Required for ${type.requires_medical_cert_after}+ days of ${type.name}.`}</Text> : null}
          {v.attachment ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Text testID="attachment-name" style={{ flex: 1 }} numberOfLines={1}>{v.attachment.name}</Text>
              <Button testID="attachment-clear" variant="secondary" title="Remove" onPress={() => set({ attachment: null })} />
            </View>
          ) : (
            <ProofPicker testIDPrefix="attach" onPick={(f) => set({ attachment: f })} />
          )}
          {errors.attachment ? <Text testID="error-attachment" accessibilityRole="alert" size={13} style={{ color: colors.danger }}>{errors.attachment}</Text> : null}
        </View>
      ) : null}

      <Text testID="days-total" muted>{`Total: ${days} day${days === 1 ? '' : 's'}`}</Text>
      {serverError ? <Text testID="apply-error" accessibilityRole="alert" style={{ color: colors.danger }}>{serverError}</Text> : null}
      <Button testID="submit-leave" title="Submit" loading={apply.isPending} onPress={() => void submit()} />
      <Button testID="cancel-apply" variant="secondary" title="Close" disabled={apply.isPending} onPress={onCancel} />
    </Card>
  );
}
