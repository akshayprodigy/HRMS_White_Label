/**
 * Liveness (anti-spoof) for selfie punches.
 *
 * Real on-device face detection: react-native-vision-camera + react-native-vision-camera-face-detector (Google
 * ML Kit) run in FaceCamera.tsx and feed FaceObservations (see faceSignal.ts) into a FaceSignalSource. This module
 * stays pure and native-free so it is unit-testable:
 *  - ChallengeLivenessDetector: prompts a random challenge (blink, or turn the head to either side), waits for
 *    observations that satisfy it (8 s timeout) and then captures the still. passed = true/false.
 *  - FallbackLivenessDetector: no face signal available. Two frames ~1 s apart, passed = null (UNKNOWN).
 *  - DevBypassLivenessDetector (tenant flag devLivenessBypass): one frame, passed = null.
 * Nothing in here ever returns `passed: true` without a face signal source actually observing the challenge.
 * Limits: this is a challenge-response check, not a certified presentation-attack detector; a replayed video of the
 * user performing the challenge could pass. The server stores passed/score and flags false for HR review. Score is null
 * (ML Kit gives no liveness confidence).
 *
 * Head turn is SIGN-AGNOSTIC: ML Kit's yaw sign differs between Android/iOS and with front-camera mirroring, so
 * the challenge is "face centred, then |yaw| >= 20 degrees to either side" and never depends on the sign.
 */
export type LivenessChallenge = 'blink' | 'turn_head';

export type LivenessResult = {
  /** true = challenge observed, false = challenge failed/timed out, null = unknown (no detector). */
  passed: boolean | null;
  score: number | null;
  method: 'challenge' | 'frames' | 'dev-bypass';
};

export type FaceObservation = { faceVisible: boolean; leftEyeOpen?: number; rightEyeOpen?: number; /** degrees; the sign is platform dependent, only |yaw| is used */ yaw?: number };
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
const CENTRE_DEG = 10;

/** Pure evaluator: feed observations, it reports when the challenge is satisfied. Losing the face resets progress. */
export function createChallengeEvaluator(challenge: LivenessChallenge) {
  let sawOpen = false;
  let sawClosed = false;
  let sawCentre = false;
  return (o: FaceObservation): boolean => {
    if (!o.faceVisible) {
      // No face (or several): progress must be one continuous, single-face sequence, so a photo swap can't complete it.
      sawOpen = false;
      sawClosed = false;
      sawCentre = false;
      return false;
    }
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
    const yaw = Math.abs(o.yaw);
    if (yaw < CENTRE_DEG) sawCentre = true;
    return sawCentre && yaw >= TURN_DEG;
  };
}

export function pickChallenge(rng: () => number = Math.random): LivenessChallenge {
  return rng() < 0.5 ? 'blink' : 'turn_head';
}

const PROMPTS: Record<LivenessChallenge, string> = { blink: 'Blink', turn_head: 'Turn your head left or right' };

export class ChallengeLivenessDetector implements LivenessDetector {
  readonly id = 'challenge';
  readonly challenge = true;
  constructor(
    private source: FaceSignalSource,
    private kind: LivenessChallenge = 'blink',
    private timeoutMs = CHALLENGE_TIMEOUT_MS,
  ) {}

  async run(session: CaptureSession): Promise<LivenessCapture> {
    session.setPrompt(PROMPTS[this.kind]);
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
    // The still is taken right after the challenge outcome (same moment the user's face is in view).
    const frameUri = await session.capture();
    return { frameUri, result: { passed, score: null, method: 'challenge' } };
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

export function getLivenessDetector(opts: { devBypass?: boolean; source?: FaceSignalSource | null; challenge?: LivenessChallenge } = {}): LivenessDetector {
  if (opts.devBypass) return new DevBypassLivenessDetector();
  if (opts.source) return new ChallengeLivenessDetector(opts.source, opts.challenge ?? pickChallenge());
  return new FallbackLivenessDetector();
}
