import { ChallengeLivenessDetector, DevBypassLivenessDetector, FallbackLivenessDetector, createChallengeEvaluator, getLivenessDetector, pickChallenge, type CaptureSession, type FaceObservation } from '../src/features/punch/liveness';

function session() {
  const caps: number[] = [];
  const s: CaptureSession = { capture: jest.fn(async () => `file:///f${caps.push(1)}.jpg`), sleep: jest.fn(async () => undefined), setPrompt: jest.fn() };
  return s;
}
const o = (l: number, r = l, faceVisible = true): FaceObservation => ({ faceVisible, leftEyeOpen: l, rightEyeOpen: r });
function manualSource() {
  let emit: (x: FaceObservation) => void = () => undefined;
  return { source: { subscribe: (cb: (x: FaceObservation) => void) => { emit = cb; return () => undefined; } }, emit: (x: FaceObservation) => emit(x) };
}

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
    expect(ev(o(0.9))).toBe(false); // never blinked: not enough
    expect(ev(o(0.1))).toBe(false);
    expect(ev(o(0.9))).toBe(true);
  });
  it('blink: face lost mid-challenge (or several faces) resets progress', () => {
    const ev = createChallengeEvaluator('blink');
    expect(ev(o(0.9))).toBe(false);
    expect(ev(o(0.1))).toBe(false); // closed
    expect(ev({ faceVisible: false })).toBe(false); // lost
    expect(ev(o(0.9))).toBe(false); // open again, but the sequence restarted
    expect(ev(o(0.1))).toBe(false);
    expect(ev(o(0.9))).toBe(true);
  });
  it('blink ignores observations without eye probabilities', () => {
    expect(createChallengeEvaluator('blink')({ faceVisible: true, yaw: 0 })).toBe(false);
  });
  it('head turn needs a centred face first, then |yaw| past the threshold on either side', () => {
    for (const sign of [1, -1]) {
      const ev = createChallengeEvaluator('turn_head');
      expect(ev({ faceVisible: true, yaw: 30 * sign })).toBe(false); // started already turned: a photo held sideways
      expect(ev({ faceVisible: true, yaw: 2 })).toBe(false);
      expect(ev({ faceVisible: true, yaw: 15 * sign })).toBe(false); // not far enough
      expect(ev({ faceVisible: true, yaw: 25 * sign })).toBe(true);
    }
  });
  it('head turn: losing the face after centring resets the centre requirement', () => {
    const ev = createChallengeEvaluator('turn_head');
    expect(ev({ faceVisible: true, yaw: 0 })).toBe(false);
    expect(ev({ faceVisible: false })).toBe(false);
    expect(ev({ faceVisible: true, yaw: 40 })).toBe(false);
  });
  it('pickChallenge is random between blink and turn_head', () => {
    expect(pickChallenge(() => 0.1)).toBe('blink');
    expect(pickChallenge(() => 0.9)).toBe('turn_head');
  });

  it('challenge detector passes only when the source shows the challenge, fails on timeout', async () => {
    const { source, emit } = manualSource();
    const s = session();
    const p = new ChallengeLivenessDetector(source, 'blink', 50).run(s);
    for (const v of [0.9, 0.1, 0.9]) emit(o(v));
    expect((await p).result).toMatchObject({ passed: true, score: null, method: 'challenge' });
    expect(s.setPrompt).toHaveBeenCalledWith('Blink');
    const timedOut = await new ChallengeLivenessDetector(source, 'blink', 20).run(session());
    expect(timedOut.result.passed).toBe(false);
    expect(timedOut.frameUri).toBeTruthy(); // still captured so the punch can proceed (flagged)
  });
  it('detector times out when the face is lost mid-challenge and never recovers the sequence', async () => {
    const { source, emit } = manualSource();
    const p = new ChallengeLivenessDetector(source, 'blink', 30).run(session());
    emit(o(0.9)); emit(o(0.1)); emit({ faceVisible: false }); emit(o(0.9));
    expect((await p).result.passed).toBe(false);
  });

  it('uses a provided face source, and the dev bypass wins over it', () => {
    const source = { subscribe: () => () => undefined };
    expect(getLivenessDetector({ source })).toBeInstanceOf(ChallengeLivenessDetector);
    expect(getLivenessDetector({ source, devBypass: true })).toBeInstanceOf(DevBypassLivenessDetector);
  });
});
