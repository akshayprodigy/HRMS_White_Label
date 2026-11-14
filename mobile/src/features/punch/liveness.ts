/**
 * Liveness (anti-spoof) for selfie punches.
 *
 * Real on-device face detection: react-native-vision-camera + react-native-vision-camera-face-detector (Google
 * ML Kit) run in FaceCamera.tsx and feed FaceObservations (see faceSignal.ts) into a FaceSignalSource. This module
 * stays pure and native-free so it is unit-testable:
 *  - ChallengeLivenessDetector: prompts a random challenge (blink ~70%, or turn the head to a side and back), waits
 *    for observations that satisfy it (8 s timeout), captures the still, and only passes if the same single face
 *    stayed in view during the capture and (when the session supplies verifyStill) the still itself has exactly
 *    one face. Abortable (AbortSignal): cancel/unmount/backgrounding throws LivenessAbortedError, no result.
 *    passed = true/false.
 *  - FallbackLivenessDetector: no face signal available. Two frames ~1 s apart, passed = null (UNKNOWN).
 *  - DevBypassLivenessDetector (tenant flag devLivenessBypass): one frame, passed = null.
 * Nothing in here ever returns `passed: true` without a face signal source actually observing the challenge.
 * Limits: this is a challenge-response check, not a certified presentation-attack detector; a replayed video of the
 * user performing the challenge could pass. The server stores passed/score and flags false for HR review. Score is null
 * (ML Kit gives no liveness confidence).
 *
 * Head turn is SIGN-AGNOSTIC: ML Kit's yaw sign differs between Android/iOS and with front-camera mirroring, so
 * the challenge is "face centred, then |yaw| >= 20 degrees to either side, then centred again" and never depends on the sign.
 */
export type LivenessChallenge = 'blink' | 'turn_head';

export type LivenessResult = {
  /** true = challenge observed, false = challenge failed/timed out, null = unknown (no detector). */
  passed: boolean | null;
  score: number | null;
  method: 'challenge' | 'frames' | 'dev-bypass';
};

export type FaceObservation = { faceVisible: boolean; leftEyeOpen?: number; rightEyeOpen?: number; /** degrees; the sign is platform dependent, only |yaw| is used */ yaw?: number; /** detector's id for this face; a change means a different face */ trackingId?: number };
export type FaceSignalSource = { subscribe(cb: (o: FaceObservation) => void): () => void };

/** What a detector gets from the camera screen. */
export type CaptureSession = {
  /** Take a still, returns a local file uri. */
  capture(): Promise<string>;
  sleep(ms: number): Promise<void>;
  setPrompt(text: string): void;
  /** Optional check on the captured still: true only if it shows exactly one face. A false/throwing check fails liveness. */
  verifyStill?(uri: string): Promise<boolean>;
};
export type LivenessCapture = { frameUri: string; result: LivenessResult };
/** Thrown by run() when its AbortSignal fires (cancel, unmount, app backgrounded). No result, and no retry is consumed. */
export class LivenessAbortedError extends Error {
  constructor() {
    super('Liveness check aborted');
    this.name = 'LivenessAbortedError';
  }
}
export interface LivenessDetector {
  readonly id: string;
  /** True when this detector really observes a challenge (UI can say "Blink now"). */
  readonly challenge: boolean;
  run(session: CaptureSession, signal?: AbortSignal): Promise<LivenessCapture>;
}

export const CHALLENGE_TIMEOUT_MS = 8000;

const EYE_OPEN = 0.6;
const EYE_CLOSED = 0.3;
const TURN_DEG = 20;
const CENTRE_DEG = 10;

/**
 * Pure evaluator: feed observations, it reports when the challenge is satisfied. Losing the face, a second face, or a
 * change of tracking id (a different face) resets progress, so only one continuous single-face sequence can pass.
 */
export function createChallengeEvaluator(challenge: LivenessChallenge) {
  let sawOpen = false;
  let sawClosed = false;
  let sawCentre = false;
  let sawTurned = false;
  let id: number | undefined;
  const reset = () => {
    sawOpen = false;
    sawClosed = false;
    sawCentre = false;
    sawTurned = false;
    id = undefined;
  };
  return (o: FaceObservation): boolean => {
    if (!o.faceVisible) {
      reset();
      return false;
    }
    if (o.trackingId != null) {
      if (id != null && id !== o.trackingId) reset();
      id = o.trackingId;
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
    // centre -> turned (either side) -> back to centre
    if (!sawTurned) {
      if (yaw < CENTRE_DEG) sawCentre = true;
      else if (sawCentre && yaw >= TURN_DEG) sawTurned = true;
      return false;
    }
    return yaw < CENTRE_DEG;
  };
}

/** Blink is the easier, more reliable challenge: ~70% blink, ~30% head turn. */
export function pickChallenge(rng: () => number = Math.random): LivenessChallenge {
  return rng() < 0.7 ? 'blink' : 'turn_head';
}

const PROMPTS: Record<LivenessChallenge, string> = { blink: 'Blink', turn_head: 'Turn your head to one side, then back' };

export class ChallengeLivenessDetector implements LivenessDetector {
  readonly id = 'challenge';
  readonly challenge = true;
  constructor(
    private source: FaceSignalSource,
    private kind: LivenessChallenge = 'blink',
    private timeoutMs = CHALLENGE_TIMEOUT_MS,
  ) {}

  async run(session: CaptureSession, signal?: AbortSignal): Promise<LivenessCapture> {
    if (signal?.aborted) throw new LivenessAbortedError();
    session.setPrompt(PROMPTS[this.kind]);
    const evaluate = createChallengeEvaluator(this.kind);
    let unsub: () => void = () => undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let onAbort: () => void = () => undefined;
    let capturing = false;
    let swapped = false; // the face changed/was lost between the challenge passing and the still being taken
    let passId: number | undefined;
    const outcome = await new Promise<'pass' | 'timeout' | 'abort'>((resolve) => {
      timer = setTimeout(() => resolve('timeout'), this.timeoutMs);
      onAbort = () => resolve('abort');
      signal?.addEventListener('abort', onAbort);
      unsub = this.source.subscribe((o) => {
        if (capturing) {
          // Subscription stays live across capture(): exactly the same single face must stay in view.
          if (!o.faceVisible || (passId != null && o.trackingId != null && o.trackingId !== passId)) swapped = true;
        } else if (evaluate(o)) {
          capturing = true;
          passId = o.trackingId;
          resolve('pass');
        }
      });
    });
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
    if (outcome === 'abort') {
      unsub();
      throw new LivenessAbortedError();
    }
    if (outcome === 'timeout') unsub();
    let frameUri: string;
    try {
      // The still is taken right after the challenge outcome (same moment the user's face is in view).
      frameUri = await session.capture();
    } finally {
      unsub();
    }
    if (signal?.aborted) throw new LivenessAbortedError();
    let passed = outcome === 'pass' && !swapped;
    if (passed && session.verifyStill) passed = await session.verifyStill(frameUri).catch(() => false);
    if (signal?.aborted) throw new LivenessAbortedError();
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
