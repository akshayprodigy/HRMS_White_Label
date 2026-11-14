import * as ImagePicker from 'expo-image-picker';
import { useIsFocused } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Linking, StyleSheet, View } from 'react-native';
import { Button, Card, Text } from '../../components/ui';
import { getTenant } from '../../config/tenant';
import { compressSelfie, type SelfieInput } from './api';
import { loadFaceCamera } from './faceCameraLoader';
import { createFaceSignal, type FaceLike } from './faceSignal';
import { selfieFiles } from './store';
import { getLivenessDetector, LivenessAbortedError, type CaptureSession, type LivenessResult } from './liveness';

/** Failed challenges allow this many retries; after that the punch can still be submitted (liveness_passed = false, flagged for HR). */
export const MAX_LIVENESS_RETRIES = 2;

const native = loadFaceCamera();
const NativeFaceCamera = native?.FaceCamera;
// Chosen once at module load, so the hook order is stable for the life of the app.
const useCameraPermission = native?.useCameraPermission ?? (() => ({ hasPermission: true, canRequestPermission: false, requestPermission: async () => true }));
const styles = StyleSheet.create({ preview: { height: 320, borderRadius: 12, overflow: 'hidden' }, camera: { flex: 1 }, prompt: { textAlign: 'center' } });

/**
 * Front-camera selfie + liveness (see liveness.ts). With the native face detector (VisionCamera + ML Kit) "Take selfie"
 * runs a random blink / head-turn challenge; if the native modules cannot load, the camera errors or there is no front
 * camera it falls back to the system camera with liveness = unknown (null). A failed challenge can be retried twice,
 * then submitted for HR review. Leaving the screen, cancelling or backgrounding the app aborts the run and deletes
 * any captured frames.
 */
export function SelfieCapture({ onDone, onCancel, allowSkip = true }: { onDone: (s: SelfieInput | null) => void; onCancel: () => void; allowSkip?: boolean }) {
  const perm = useCameraPermission();
  const cam = useRef<{ takePhoto(): Promise<string> } | null>(null);
  const [signal] = useState(() => createFaceSignal());
  const onFaces = useCallback((faces: readonly FaceLike[]) => signal.pushFaces(faces), [signal]);
  const [camFailed, setCamFailed] = useState(false);
  const onCamError = useCallback(() => setCamFailed(true), []);
  const [prompt, setPrompt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [failures, setFailures] = useState(0);
  const [heldFrame, setHeldFrame] = useState<string | null>(null); // a failed-liveness still, kept once retries are used up
  const bypass = __DEV__ && !!getTenant().features?.devLivenessBypass;

  // Camera only runs while this screen is focused and the app is in the foreground.
  const focused = useIsFocused();
  const [appForeground, setAppForeground] = useState(AppState.currentState !== 'background' && AppState.currentState !== 'inactive');
  useEffect(() => {
    const sub = AppState.addEventListener('change', (s) => setAppForeground(s !== 'background' && s !== 'inactive'));
    return () => sub.remove();
  }, []);
  const active = focused && appForeground;

  // Every still we took and have not delivered, so cancel/skip/unmount/failure can delete them.
  const shots = useRef(new Set<string>());
  const abortRef = useRef<AbortController | null>(null);
  const reasonRef = useRef<'inactive' | 'user' | null>(null);
  const discard = useCallback(async (uri: string) => {
    shots.current.delete(uri);
    try { await selfieFiles.remove(uri); } catch { /* best effort */ }
  }, []);
  const discardAll = useCallback(async () => {
    await Promise.all([...shots.current].map((u) => discard(u)));
  }, [discard]);
  const abortRun = useCallback((reason: 'inactive' | 'user') => {
    reasonRef.current = reason;
    abortRef.current?.abort();
  }, []);
  useEffect(() => () => { abortRef.current?.abort(); void discardAll(); }, [discardAll]);
  useEffect(() => { if (!active) abortRun('inactive'); }, [active, abortRun]);

  const finish = async (frameUri: string, result: LivenessResult) => {
    try {
      const uri = await compressSelfie(frameUri);
      shots.current.delete(frameUri);
      await discardAll(); // any other stills from this session (e.g. the fallback's first frame)
      if (uri !== frameUri) await discard(frameUri); // drop the uncompressed camera frame
      onDone({ uri, liveness_passed: result.passed, liveness_score: result.score });
    } catch (e) {
      await discard(frameUri);
      throw e;
    }
  };

  const start = async () => {
    setBusy(true);
    setErr(null);
    setHeldFrame(null);
    reasonRef.current = null;
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      const session: CaptureSession = {
        capture: async () => {
          if (!cam.current) throw new Error('Camera not ready');
          const uri = await cam.current.takePhoto();
          shots.current.add(uri);
          return uri;
        },
        sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
        setPrompt,
        verifyStill: native ? async (uri) => native.stillHasExactlyOneFace(uri) : undefined,
      };
      const { frameUri, result } = await getLivenessDetector({ devBypass: bypass, source: signal.source }).run(session, ac.signal);
      if (result.passed === false) {
        const failed = failures + 1;
        setFailures(failed);
        if (failed <= MAX_LIVENESS_RETRIES) {
          await discard(frameUri);
          const left = MAX_LIVENESS_RETRIES - failed + 1;
          setErr(`We could not confirm it is you. Make sure only your face is in view, in good light, then try again (${left} ${left === 1 ? 'try' : 'tries'} left).`);
        } else {
          setHeldFrame(frameUri);
          setErr('We could not confirm it is you. You can submit this punch anyway; it will be flagged for HR review.');
        }
        return;
      }
      await finish(frameUri, result);
    } catch (e) {
      await discardAll();
      if (e instanceof LivenessAbortedError) {
        // Aborted (not failed): no retry consumed. Say so only when the app/screen went inactive.
        if (reasonRef.current === 'inactive') setErr('The check was paused because the app was in the background. Tap Take selfie to start again.');
      } else {
        setErr("Couldn't take the photo. Try again.");
      }
    } finally {
      if (abortRef.current === ac) abortRef.current = null;
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
      setHeldFrame(null);
      setErr("Couldn't submit the photo. Try again.");
    } finally {
      setBusy(false);
    }
  };

  /** Native face camera unavailable or failed: system camera, liveness unknown (null). */
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

  const cancel = async () => {
    abortRun('user');
    await discardAll();
    onCancel();
  };
  const skip = async () => {
    abortRun('user');
    await discardAll();
    onDone(null);
  };
  const skipButton = allowSkip ? <Button testID="selfie-skip" variant="secondary" title="Continue without selfie" onPress={() => void skip()} /> : null;
  const cancelButton = <Button variant="secondary" title="Cancel" onPress={() => void cancel()} />;

  if (!NativeFaceCamera || camFailed) {
    return (
      <Card style={{ gap: 8 }}>
        <Text muted size={14}>A selfie is used to verify your punch.</Text>
        {camFailed ? <Text testID="selfie-camera-problem" accessibilityRole="alert">The face camera is not available right now. You can use the regular camera instead.</Text> : null}
        {err ? <Text testID="selfie-error">{err}</Text> : null}
        <Button testID="selfie-capture" title="Take selfie" loading={busy} onPress={() => void systemCamera()} />
        {NativeFaceCamera ? <Button testID="selfie-retry-camera" variant="secondary" title="Try the face camera again" onPress={() => setCamFailed(false)} /> : null}
        {skipButton}
        {cancelButton}
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
        {skipButton}
        {cancelButton}
      </Card>
    );
  }
  const exhausted = heldFrame != null;
  return (
    <Card style={{ gap: 8 }}>
      <View style={styles.preview} accessibilityLabel="Front camera preview">
        <NativeFaceCamera style={styles.camera} handleRef={cam} onFaces={onFaces} onError={onCamError} onNoDevice={onCamError} isActive={active} />
      </View>
      {prompt ? <Text weight="700" size={20} testID="liveness-prompt" accessibilityLiveRegion="polite" style={styles.prompt}>{prompt}</Text> : null}
      {err ? <Text testID="selfie-error" accessibilityRole="alert">{err}</Text> : null}
      {exhausted ? (
        <Button testID="selfie-submit-review" title="Submit for HR review" loading={busy} onPress={() => void submitForReview()} />
      ) : (
        <Button testID="selfie-capture" title={failures > 0 ? 'Try again' : 'Take selfie'} loading={busy} onPress={() => void start()} />
      )}
      {skipButton}
      {cancelButton}
    </Card>
  );
}
