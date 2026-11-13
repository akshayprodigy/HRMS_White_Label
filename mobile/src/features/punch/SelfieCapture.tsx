import { CameraView, useCameraPermissions } from 'expo-camera';
import { useRef, useState } from 'react';
import { View } from 'react-native';
import { Button, Card, Text } from '../../components/ui';
import { getTenant } from '../../config/tenant';
import { compressSelfie, type SelfieInput } from './api';
import { getLivenessDetector, type CaptureSession } from './liveness';

/**
 * Front-camera selfie + liveness. The detector (see liveness.ts) decides what happens on "Capture":
 * a real challenge when a face-signal source is registered, otherwise two frames and liveness = unknown (null).
 */
export function SelfieCapture({ onDone, onCancel, allowSkip = true }: { onDone: (s: SelfieInput | null) => void; onCancel: () => void; allowSkip?: boolean }) {
  const [perm, requestPerm] = useCameraPermissions();
  const cam = useRef<CameraView>(null);
  const [prompt, setPrompt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const bypass = !!getTenant().features?.devLivenessBypass;

  const start = async () => {
    setBusy(true);
    setErr(null);
    try {
      const session: CaptureSession = {
        capture: async () => {
          const pic = await cam.current?.takePictureAsync({ quality: 0.8, skipProcessing: true });
          if (!pic?.uri) throw new Error('Camera not ready');
          return pic.uri;
        },
        sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
        setPrompt,
      };
      const { frameUri, result } = await getLivenessDetector({ devBypass: bypass }).run(session);
      const uri = await compressSelfie(frameUri);
      onDone({ uri, liveness_passed: result.passed, liveness_score: result.score });
    } catch {
      setErr("Couldn't take the photo. Try again.");
    } finally {
      setBusy(false);
      setPrompt(null);
    }
  };

  if (!perm) return <Card><Text muted>Checking camera…</Text></Card>;
  if (!perm.granted) {
    return (
      <Card style={{ gap: 8 }}>
        <Text weight="600">Camera access</Text>
        <Text muted size={14}>A selfie is used to verify your punch.</Text>
        <Button testID="camera-allow" title="Allow camera" onPress={() => void requestPerm()} />
        {allowSkip ? <Button testID="selfie-skip" variant="secondary" title="Continue without selfie" onPress={() => onDone(null)} /> : null}
        <Button variant="secondary" title="Cancel" onPress={onCancel} />
      </Card>
    );
  }
  return (
    <Card style={{ gap: 8 }}>
      <View style={{ height: 320, borderRadius: 12, overflow: 'hidden' }}>
        <CameraView ref={cam} style={{ flex: 1 }} facing="front" />
      </View>
      {prompt ? <Text weight="700" size={20} testID="liveness-prompt" style={{ textAlign: 'center' }}>{prompt}</Text> : null}
      {err ? <Text testID="selfie-error">{err}</Text> : null}
      <Button testID="selfie-capture" title="Take selfie" loading={busy} onPress={() => void start()} />
      {allowSkip ? <Button testID="selfie-skip" variant="secondary" title="Continue without selfie" onPress={() => onDone(null)} /> : null}
      <Button variant="secondary" title="Cancel" onPress={onCancel} />
    </Card>
  );
}
