import { ChallengeLivenessDetector, DevBypassLivenessDetector, FallbackLivenessDetector, LivenessAbortedError, createChallengeEvaluator, getLivenessDetector, pickChallenge, type CaptureSession, type FaceObservation } from '../src/features/punch/liveness';

function session(extra: Partial<CaptureSession> = {}) {
  const caps: number[] = [];
  const s: CaptureSession = { capture: jest.fn(async () => `file:///f${caps.push(1)}.jpg`), sleep: jest.fn(async () => undefined), setPrompt: jest.fn(), ...extra };
  return s;
}
const o = (l: number, r = l, faceVisible = true, trackingId?: number): FaceObservation => ({ faceVisible, leftEyeOpen: l, rightEyeOpen: r, trackingId });
function manualSource() {
  let emit: (x: FaceObservation) => void = () => undefined;
  const unsub = jest.fn();
  return { source: { subscribe: (cb: (x: FaceObservation) => void) => { emit = cb; return unsub; } }, emit: (x: FaceObservation) => emit(x), unsub };
}
const blinkSeq = (emit: (x: FaceObservation) => void, id?: number) => { for (const v of [0.9, 0.1, 0.9]) emit(o(v, v, true, id)); };

describe('liveness', () => {
  it('fallback captures two frames ~1s apart and never reports a pass', async () => {
    const s = session();
    const r = await new FallbackLivenessDetector().run(s);
    expect(s.capture).toHaveBeenCalledTimes(2);
    expect(s.sleep).toHaveBeenCalledWith(1000);
    expect(r.result).toEqual({ passed: null, score: null, method: 'frames' });
  });

  it('default detector is the fallback (passed null); the dev bypass is also null', async () => {
    expect(getLivenessDetector()).toBeInstanceOf(FallbackLivenessDetector);
    expect(getLivenessDetector({ devBypass: true })).toBeInstanceOf(DevBypassLivenessDetector);
    const r = await getLivenessDetector({ devBypass: true }).run(session());
    expect(r.result.passed).toBeNull();
  });

  it('blink needs open -> closed -> open with a visible face', () => {
    const ev = createChallengeEvaluator('blink');
    expect(ev(o(0.9))).toBe(false);
    expect(ev(o(0.9))).toBe(false);
    expect(ev(o(0.1))).toBe(false);
    expect(ev(o(0.9))).toBe(true);
  });
  it('blink: face lost mid-challenge (or several faces) resets progress', () => {
    const ev = createChallengeEvaluator('blink');
    expect(ev(o(0.9))).toBe(false);
    expect(ev(o(0.1))).toBe(false);
    expect(ev({ faceVisible: false })).toBe(false);
    expect(ev(o(0.9))).toBe(false);
    expect(ev(o(0.1))).toBe(false);
    expect(ev(o(0.9))).toBe(true);
  });
  it('blink: a tracking-id change mid-sequence resets progress (different face)', () => {
    const ev = createChallengeEvaluator('blink');
    expect(ev(o(0.9, 0.9, true, 1))).toBe(false);
    expect(ev(o(0.1, 0.1, true, 1))).toBe(false);
    expect(ev(o(0.9, 0.9, true, 2))).toBe(false); // other face: sequence restarts
    expect(ev(o(0.1, 0.1, true, 2))).toBe(false);
    expect(ev(o(0.9, 0.9, true, 2))).toBe(true);
  });
  it('blink ignores observations without eye probabilities', () => {
    expect(createChallengeEvaluator('blink')({ faceVisible: true, yaw: 0 })).toBe(false);
  });
  it('head turn is centre -> turned (either side) -> back to centre', () => {
    for (const sign of [1, -1]) {
      const ev = createChallengeEvaluator('turn_head');
      expect(ev({ faceVisible: true, yaw: 30 * sign })).toBe(false); // started already turned: a photo held sideways
      expect(ev({ faceVisible: true, yaw: 2 })).toBe(false);
      expect(ev({ faceVisible: true, yaw: 15 * sign })).toBe(false); // not far enough
      expect(ev({ faceVisible: true, yaw: 25 * sign })).toBe(false); // turned but not back yet
      expect(ev({ faceVisible: true, yaw: 3 })).toBe(true);
    }
  });
  it('head turn: losing the face or changing id mid-sequence resets', () => {
    const ev = createChallengeEvaluator('turn_head');
    ev({ faceVisible: true, yaw: 0, trackingId: 1 });
    ev({ faceVisible: true, yaw: 30, trackingId: 1 });
    expect(ev({ faceVisible: true, yaw: 0, trackingId: 2 })).toBe(false); // other face
    ev({ faceVisible: true, yaw: 30, trackingId: 2 });
    expect(ev({ faceVisible: false })).toBe(false);
    expect(ev({ faceVisible: true, yaw: 0 })).toBe(false); // had to start over
  });
  it('pickChallenge favours blink (~70/30)', () => {
    expect(pickChallenge(() => 0.1)).toBe('blink');
    expect(pickChallenge(() => 0.69)).toBe('blink');
    expect(pickChallenge(() => 0.71)).toBe('turn_head');
  });

  it('challenge detector passes only when the source shows the challenge, fails on timeout', async () => {
    const { source, emit } = manualSource();
    const s = session();
    const p = new ChallengeLivenessDetector(source, 'blink', 50).run(s);
    blinkSeq(emit);
    expect((await p).result).toMatchObject({ passed: true, score: null, method: 'challenge' });
    expect(s.setPrompt).toHaveBeenCalledWith('Blink');
    const timedOut = await new ChallengeLivenessDetector(source, 'blink', 20).run(session());
    expect(timedOut.result.passed).toBe(false);
    expect(timedOut.frameUri).toBeTruthy();
  });
  it('detector times out when the face is lost mid-challenge and never recovers the sequence', async () => {
    const { source, emit } = manualSource();
    const p = new ChallengeLivenessDetector(source, 'blink', 30).run(session());
    emit(o(0.9)); emit(o(0.1)); emit({ faceVisible: false }); emit(o(0.9));
    expect((await p).result.passed).toBe(false);
  });

  it('photo swap during capture (face lost) fails the check; subscription stays live across capture()', async () => {
    const { source, emit, unsub } = manualSource();
    let release: () => void = () => undefined;
    const s = session({ capture: jest.fn(() => new Promise<string>((r) => { release = () => r('file:///x.jpg'); })) });
    const p = new ChallengeLivenessDetector(source, 'blink', 1000).run(s);
    blinkSeq(emit, 5);
    await Promise.resolve();
    expect(unsub).not.toHaveBeenCalled(); // still subscribed while capturing
    emit({ faceVisible: false });
    release();
    expect((await p).result.passed).toBe(false);
    expect(unsub).toHaveBeenCalled();
  });
  it('a different tracking id during capture fails the check; the same id still passes', async () => {
    for (const [id, expected] of [[9, false], [5, true]] as const) {
      const { source, emit } = manualSource();
      let release: () => void = () => undefined;
      const s = session({ capture: jest.fn(() => new Promise<string>((r) => { release = () => r('file:///x.jpg'); })) });
      const p = new ChallengeLivenessDetector(source, 'blink', 1000).run(s);
      blinkSeq(emit, 5);
      await Promise.resolve();
      emit(o(0.9, 0.9, true, id));
      release();
      expect((await p).result.passed).toBe(expected);
    }
  });
  it('verifyStill must confirm exactly one face in the captured file, else passed=false', async () => {
    for (const [verdict, expected] of [[false, false], [true, true]] as const) {
      const { source, emit } = manualSource();
      const verifyStill = jest.fn(async () => verdict);
      const p = new ChallengeLivenessDetector(source, 'blink', 1000).run(session({ verifyStill }));
      blinkSeq(emit);
      const r = await p;
      expect(verifyStill).toHaveBeenCalledWith('file:///f1.jpg');
      expect(r.result.passed).toBe(expected);
    }
    // a throwing verifier fails safe
    const { source, emit } = manualSource();
    const p = new ChallengeLivenessDetector(source, 'blink', 1000).run(session({ verifyStill: async () => { throw new Error('ml kit'); } }));
    blinkSeq(emit);
    expect((await p).result.passed).toBe(false);
  });

  it('abort unsubscribes, clears the timer and never captures', async () => {
    jest.useFakeTimers();
    try {
      const { source, unsub } = manualSource();
      const s = session();
      const ac = new AbortController();
      const p = new ChallengeLivenessDetector(source, 'blink', 8000).run(s, ac.signal);
      const caught = p.catch((e) => e);
      ac.abort();
      expect(await caught).toBeInstanceOf(LivenessAbortedError);
      expect(unsub).toHaveBeenCalled();
      expect(s.capture).not.toHaveBeenCalled();
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      jest.useRealTimers();
    }
  });
  it('an already-aborted signal rejects immediately', async () => {
    const ac = new AbortController();
    ac.abort();
    const { source } = manualSource();
    await expect(new ChallengeLivenessDetector(source, 'blink').run(session(), ac.signal)).rejects.toBeInstanceOf(LivenessAbortedError);
  });

  it('uses a provided face source, and the dev bypass wins over it', () => {
    const source = { subscribe: () => () => undefined };
    expect(getLivenessDetector({ source })).toBeInstanceOf(ChallengeLivenessDetector);
    expect(getLivenessDetector({ source, devBypass: true })).toBeInstanceOf(DevBypassLivenessDetector);
  });
});
