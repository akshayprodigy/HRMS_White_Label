/**
 * Liveness (anti-spoof) for selfie punches.
 *
 * SDK 58 / expo-camera has NO face detection (expo-face-detector was removed), and a robust blink / head-turn
 * detector needs a native frame processor (react-native-vision-camera + a face-detector plugin), which is not
 * installed (no native builds here). So this module is a pluggable seam:
 *  - ChallengeLivenessDetector: complete, tested challenge logic (blink / turn head) over a FaceSignalSource.
 *    A vision-camera/ML Kit based source is registered with registerFaceSignalSource() once a dev build has one.
 *  - FallbackLivenessDetector (default): captures 2 frames ~1s apart and reports liveness_passed = null (UNKNOWN).
 *  - Dev bypass (tenant flag devLivenessBypass): one frame, liveness_passed = null.
 * Nothing in here ever returns `passed: true` without a face signal source actually observing the challenge.
 */
export type LivenessChallenge = 'blink' | 'turn_left';

export type LivenessResult = {
  /** true = challenge observed, false = challenge failed/timed out, null = unknown (no detector). */
  passed: boolean | null;
  score: number | null;
  method: 'challenge' | 'frames' | 'dev-bypass';
};

export type FaceObservation = { faceVisible: boolean; leftEyeOpen?: number; rightEyeOpen?: number; /** degrees, + = turned to the user's left */ yaw?: number };
export type FaceSignalSource = { subscribe(cb: (o: FaceObservation) => void): () => void };

/** What a detector gets from the camera screen. */
export type CaptureSession = {
  /** Take a still, returns a local file uri. */
  capture(): Promise<string>;
  sleep(ms: number): Promise<void>;
  setPrompt(text: string): void;
};
export type LivenessCapture = { frameUri: string; result: LivenessResult };
export interface LivenessDetector {
  readonly id: string;
  /** True when this detector really observes a challenge (UI can say "Blink now"). */
  readonly challenge: boolean;
  run(session: CaptureSession): Promise<LivenessCapture>;
}

export const CHALLENGE_TIMEOUT_MS = 8000;

const EYE_OPEN = 0.6;
const EYE_CLOSED = 0.3;
const TURN_DEG = 20;

/** Pure evaluator: feed observations, it reports when the challenge is satisfied. */
export function createChallengeEvaluator(challenge: LivenessChallenge) {
  let sawOpen = false;
  let sawClosed = false;
  let sawCentre = false;
  return (o: FaceObservation): boolean => {
    if (!o.faceVisible) return false;
    if (challenge === 'blink') {
      const l = o.leftEyeOpen, r = o.rightEyeOpen;
      if (l == null || r == null) return false;
      if (!sawClosed) {
        if (l > EYE_OPEN && r > EYE_OPEN) sawOpen = true;
        else if (sawOpen && l < EYE_CLOSED && r < EYE_CLOSED) sawClosed = true;
        return false;
      }
      return l > EYE_OPEN && r > EYE_OPEN; // open -> closed -> open
    }
    if (o.yaw == null) return false;
    if (Math.abs(o.yaw) < 10) sawCentre = true;
    return sawCentre && o.yaw >= TURN_DEG;
  };
}

export class ChallengeLivenessDetector implements LivenessDetector {
  readonly id = 'challenge';
  readonly challenge = true;
  constructor(
    private source: FaceSignalSource,
    private kind: LivenessChallenge = 'blink',
    private timeoutMs = CHALLENGE_TIMEOUT_MS,
  ) {}

  async run(session: CaptureSession): Promise<LivenessCapture> {
    session.setPrompt(this.kind === 'blink' ? 'Blink' : 'Turn head left');
    const evaluate = createChallengeEvaluator(this.kind);
    let unsub: () => void = () => undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const passed = await new Promise<boolean>((resolve) => {
      timer = setTimeout(() => resolve(false), this.timeoutMs);
      unsub = this.source.subscribe((o) => {
        if (evaluate(o)) resolve(true);
      });
    });
    clearTimeout(timer);
    unsub();
    const frameUri = await session.capture();
    return { frameUri, result: { passed, score: passed ? 1 : 0, method: 'challenge' } };
  }
}

/** Default: no face detection available. Two frames 1s apart, liveness UNKNOWN (null). Never claims a pass. */
export class FallbackLivenessDetector implements LivenessDetector {
  readonly id = 'frames';
  readonly challenge = false;
  async run(session: CaptureSession): Promise<LivenessCapture> {
    session.setPrompt('Look at the camera');
    await session.capture(); // frame 1
    await session.sleep(1000);
    const frameUri = await session.capture(); // frame 2 (the one submitted)
    return { frameUri, result: { passed: null, score: null, method: 'frames' } };
  }
}

export class DevBypassLivenessDetector implements LivenessDetector {
  readonly id = 'dev-bypass';
  readonly challenge = false;
  async run(session: CaptureSession): Promise<LivenessCapture> {
    return { frameUri: await session.capture(), result: { passed: null, score: null, method: 'dev-bypass' } };
  }
}

let faceSource: FaceSignalSource | null = null;
/** A dev build with a native face detector calls this once at startup (see README, "Liveness"). */
export function registerFaceSignalSource(s: FaceSignalSource | null) {
  faceSource = s;
}
export function getLivenessDetector(opts: { devBypass?: boolean } = {}): LivenessDetector {
  if (opts.devBypass) return new DevBypassLivenessDetector();
  if (faceSource) return new ChallengeLivenessDetector(faceSource);
  return new FallbackLivenessDetector();
}
