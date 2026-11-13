import { ChallengeLivenessDetector, DevBypassLivenessDetector, FallbackLivenessDetector, createChallengeEvaluator, getLivenessDetector, registerFaceSignalSource, type CaptureSession, type FaceObservation } from '../src/features/punch/liveness';

function session() {
  const caps: number[] = [];
  const s: CaptureSession = { capture: jest.fn(async () => `file:///f${caps.push(1)}.jpg`), sleep: jest.fn(async () => undefined), setPrompt: jest.fn() };
  return s;
}

describe('liveness', () => {
  afterEach(() => registerFaceSignalSource(null));

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
    const o = (l: number, r = l, faceVisible = true): FaceObservation => ({ faceVisible, leftEyeOpen: l, rightEyeOpen: r });
    expect(ev(o(0.9))).toBe(false);
    expect(ev(o(0.9))).toBe(false); // never blinked: not enough
    expect(ev(o(0.1, 0.1, false))).toBe(false);
    expect(ev(o(0.1))).toBe(false);
    expect(ev(o(0.9))).toBe(true);
  });
  it('head turn needs a centred face first, then yaw past the threshold', () => {
    const ev = createChallengeEvaluator('turn_left');
    expect(ev({ faceVisible: true, yaw: 30 })).toBe(false); // started already turned: a photo held sideways
    expect(ev({ faceVisible: true, yaw: 2 })).toBe(false);
    expect(ev({ faceVisible: true, yaw: 25 })).toBe(true);
  });

  it('challenge detector passes only when the source shows the challenge, fails on timeout', async () => {
    let emit: (o: FaceObservation) => void = () => undefined;
    const source = { subscribe: (cb: (o: FaceObservation) => void) => { emit = cb; return () => undefined; } };
    const s = session();
    const p = new ChallengeLivenessDetector(source, 'blink', 50).run(s);
    for (const v of [0.9, 0.1, 0.9]) emit({ faceVisible: true, leftEyeOpen: v, rightEyeOpen: v });
    expect((await p).result).toMatchObject({ passed: true, method: 'challenge' });
    expect(s.setPrompt).toHaveBeenCalledWith('Blink');
    const timedOut = await new ChallengeLivenessDetector(source, 'blink', 20).run(session());
    expect(timedOut.result.passed).toBe(false);
  });

  it('uses a registered face source', () => {
    registerFaceSignalSource({ subscribe: () => () => undefined });
    expect(getLivenessDetector()).toBeInstanceOf(ChallengeLivenessDetector);
  });
});
