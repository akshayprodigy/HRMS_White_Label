import { useState } from 'react';
import { View } from 'react-native';
import { Button, Text } from '../../components/ui';
import { useTheme } from '../../theme';
import type { PickedFile } from './api';
import { captureProofPhoto, pickProofDocument, PickError } from './pickers';

/** Camera / document buttons; reports the picked file (validation is the caller's job). */
export function ProofPicker({ onPick, disabled, testIDPrefix = 'proof' }: { onPick: (f: PickedFile) => void; disabled?: boolean; testIDPrefix?: string }) {
  const { colors } = useTheme();
  const [err, setErr] = useState<string | null>(null);
  const go = async (fn: () => Promise<PickedFile | null>) => {
    setErr(null);
    try {
      const f = await fn();
      if (f) onPick(f);
    } catch (e) {
      setErr(e instanceof PickError ? e.message : 'Could not open the picker. Please try again.');
    }
  };
  return (
    <View style={{ gap: 8 }}>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <View style={{ flex: 1 }}><Button testID={`${testIDPrefix}-camera`} variant="secondary" title="Take photo" disabled={disabled} onPress={() => void go(captureProofPhoto)} /></View>
        <View style={{ flex: 1 }}><Button testID={`${testIDPrefix}-file`} variant="secondary" title="Choose file" disabled={disabled} onPress={() => void go(pickProofDocument)} /></View>
      </View>
      {err ? <Text testID={`${testIDPrefix}-pick-error`} accessibilityRole="alert" size={13} style={{ color: colors.danger }}>{err}</Text> : null}
    </View>
  );
}
