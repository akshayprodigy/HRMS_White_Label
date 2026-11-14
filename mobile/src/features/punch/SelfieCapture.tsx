import * as ImagePicker from 'expo-image-picker';
import { useCallback, useRef, useState } from 'react';
import { Linking, View } from 'react-native';
import { Button, Card, Text } from '../../components/ui';
import { getTenant } from '../../config/tenant';
import { compressSelfie, type SelfieInput } from './api';
import { loadFaceCamera } from './faceCameraLoader';
import { createFaceSignal } from './faceSignal';
import { selfieFiles } from './store';
import { getLivenessDetector, type CaptureSession, type LivenessResult } from './liveness';

/** Failed challenges allow this many retries; after that the punch can still be submitted (liveness_passed = false, flagged for HR). */
export const MAX_LIVENESS_RETRIES = 2;

const native = loadFaceCamera();
const NativeFaceCamera = native?.FaceCamera;
// Chosen once at module load, so the hook order is stable for the life of the app.
const useCameraPermission = native?.useCameraPermission ?? (() => ({ hasPermission: true, canRequestPermission: false, requestPermission: async () => true }));

/**
 * Front-camera selfie + liveness (see liveness.ts). With the native face detector (VisionCamera + ML Kit) "Take selfie"
 * runs a random blink / head-turn challenge; if the native modules cannot load it falls back to the system camera
 * with liveness = unknown (null). A failed challenge can be retried twice, then submitted for HR review.
 */
export function SelfieCapture({ onDone, onCancel, allowSkip = true }: { onDone: (s: SelfieInput | null) => void; onCancel: () => void; allowSkip?: boolean }) {
  const perm = useCameraPermission();
  const cam = useRef<{ takePhoto(): Promise<string> } | null>(null);
  const [signal] = useState(() => createFaceSignal());
  const onFaces = useCallback((faces: Parameters<typeof signal.pushFaces>[0]) => signal.pushFaces(faces), [signal]);
  const [camErr, setCamErr] = useState<string | null>(null);
  const onCamError = useCallback((e: Error) => setCamErr(e.message || 'Camera error'), []);
  const [prompt, setPrompt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [failures, setFailures] = useState(0);
  const [heldFrame, setHeldFrame] = useState<string | null>(null); // a failed-liveness still, kept once retries are used up
  const bypass = __DEV__ && !!getTenant().features?.devLivenessBypass;

  const finish = async (frameUri: string, result: LivenessResult) => {
    const uri = await compressSelfie(frameUri);
    if (uri !== frameUri) await selfieFiles.remove(frameUri); // drop the uncompressed camera frame
    onDone({ uri, liveness_passed: result.passed, liveness_score: result.score });
  };

  const start = async () => {
    setBusy(true);
    setErr(null);
    try {
      const session: CaptureSession = {
        capture: async () => {
          if (!cam.current) throw new Error('Camera not ready');
          return cam.current.takePhoto();
        },
        sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
        setPrompt,
      };
      const { frameUri, result } = await getLivenessDetector({ devBypass: bypass, source: signal.source }).run(session);
      if (result.passed === false) {
        const failed = failures + 1;
        setFailures(failed);
        if (failed <= MAX_LIVENESS_RETRIES) {
          await selfieFiles.remove(frameUri);
          setErr(`We could not confirm it is you. Face the camera in good light on your own and try again (${MAX_LIVENESS_RETRIES - failed + 1} ${MAX_LIVENESS_RETRIES - failed + 1 === 1 ? 'try' : 'tries'} left).`);
        } else {
          setHeldFrame(frameUri);
          setErr('We could not confirm it is you. You can submit this punch anyway; it will be flagged for HR review.');
        }
        return;
      }
      await finish(frameUri, result);
    } catch {
      setErr("Couldn't take the photo. Try again.");
    } finally {
      setBusy(false);
      setPrompt(null);
    }
  };

  const submitForReview = async () => {
    if (!heldFrame) return;
    setBusy(true);
    try {
      await finish(heldFrame, { passed: false, score: null, method: 'challenge' });
    } catch {
      setErr("Couldn't submit the photo. Try again.");
    } finally {
      setBusy(false);
    }
  };

  /** Native modules unavailable: system camera, liveness unknown (null). */
  const systemCamera = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], cameraType: ImagePicker.CameraType.front, quality: 0.8 });
      const a = res.canceled ? null : res.assets?.[0];
      if (a?.uri) await finish(a.uri, { passed: null, score: null, method: 'frames' });
    } catch {
      setErr("Couldn't take the photo. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const skip = allowSkip ? <Button testID="selfie-skip" variant="secondary" title="Continue without selfie" onPress={() => onDone(null)} /> : null;

  if (!NativeFaceCamera) {
    return (
      <Card style={{ gap: 8 }}>
        <Text muted size={14}>A selfie is used to verify your punch.</Text>
        {err ? <Text testID="selfie-error">{err}</Text> : null}
        <Button testID="selfie-capture" title="Take selfie" loading={busy} onPress={() => void systemCamera()} />
        {skip}
        <Button variant="secondary" title="Cancel" onPress={onCancel} />
      </Card>
    );
  }
  if (!perm.hasPermission) {
    return (
      <Card style={{ gap: 8 }}>
        <Text weight="600">Camera access</Text>
        <Text muted size={14}>
          {perm.canRequestPermission ? 'A selfie is used to verify your punch.' : 'Camera access is off. Turn it on in Settings to take a punch selfie.'}
        </Text>
        {perm.canRequestPermission
          ? <Button testID="camera-allow" title="Allow camera" onPress={() => void perm.requestPermission()} />
          : <Button testID="camera-open-settings" title="Open Settings" onPress={() => void Linking.openSettings()} />}
        {skip}
        <Button variant="secondary" title="Cancel" onPress={onCancel} />
      </Card>
    );
  }
  const exhausted = heldFrame != null;
  return (
    <Card style={{ gap: 8 }}>
      <View style={{ height: 320, borderRadius: 12, overflow: 'hidden' }} accessibilityLabel="Front camera preview">
        <NativeFaceCamera style={{ flex: 1 }} handleRef={cam} onFaces={onFaces} onError={onCamError} />
      </View>
      {prompt ? <Text weight="700" size={20} testID="liveness-prompt" accessibilityLiveRegion="polite" style={{ textAlign: 'center' }}>{prompt}</Text> : null}
      {err || camErr ? <Text testID="selfie-error" accessibilityRole="alert">{err ?? camErr}</Text> : null}
      {exhausted ? (
        <Button testID="selfie-submit-review" title="Submit for HR review" loading={busy} onPress={() => void submitForReview()} />
      ) : (
        <Button testID="selfie-capture" title={failures > 0 ? 'Try again' : 'Take selfie'} loading={busy} onPress={() => void start()} />
      )}
      {skip}
      <Button variant="secondary" title="Cancel" onPress={onCancel} />
    </Card>
  );
}
