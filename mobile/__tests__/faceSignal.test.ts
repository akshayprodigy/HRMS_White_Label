import { createFaceSignal, facesToObservation } from '../src/features/punch/faceSignal';
import { createChallengeEvaluator, type FaceObservation } from '../src/features/punch/liveness';

const face = (yawAngle = 0, l = 0.9, r = 0.9, trackingId = 1) => ({ yawAngle, leftEyeOpenProbability: l, rightEyeOpenProbability: r, trackingId });

describe('faceSignal', () => {
  it('maps exactly one face to a visible observation, carrying the tracking id', () => {
    expect(facesToObservation([face(12, 0.2, 0.3, 7)])).toEqual({ faceVisible: true, leftEyeOpen: 0.2, rightEyeOpen: 0.3, yaw: 12, trackingId: 7 });
  });
  it('0 faces and >1 faces are not visible', () => {
    expect(facesToObservation([])).toEqual({ faceVisible: false });
    expect(facesToObservation([face(), face()])).toEqual({ faceVisible: false });
  });
  it('delivers every callback (no throttle) so a one-sample closed-eye reading is not dropped, and unsubscribes', () => {
    const { source, pushFaces } = createFaceSignal();
    const got: FaceObservation[] = [];
    const ev = createChallengeEvaluator('blink');
    let passed = false;
    const unsub = source.subscribe((o) => { got.push(o); if (ev(o)) passed = true; });
    pushFaces([face(0, 0.9, 0.9)]);
    pushFaces([face(0, 0.1, 0.1)]); // a single, immediate closed sample
    pushFaces([face(0, 0.9, 0.9)]);
    expect(got).toHaveLength(3);
    expect(passed).toBe(true);
    unsub();
    pushFaces([face()]);
    expect(got).toHaveLength(3);
  });
});
