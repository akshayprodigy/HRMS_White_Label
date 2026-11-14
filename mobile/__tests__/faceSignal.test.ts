import { createFaceSignal, facesToObservation } from '../src/features/punch/faceSignal';
import type { FaceObservation } from '../src/features/punch/liveness';

const face = (yawAngle = 0, l = 0.9, r = 0.9) => ({ yawAngle, leftEyeOpenProbability: l, rightEyeOpenProbability: r });

describe('faceSignal', () => {
  it('maps exactly one face to a visible observation', () => {
    expect(facesToObservation([face(12, 0.2, 0.3)])).toEqual({ faceVisible: true, leftEyeOpen: 0.2, rightEyeOpen: 0.3, yaw: 12 });
  });
  it('0 faces and >1 faces are not visible', () => {
    expect(facesToObservation([])).toEqual({ faceVisible: false });
    expect(facesToObservation([face(), face()])).toEqual({ faceVisible: false });
  });
  it('throttles but always delivers a visibility change, and unsubscribes', () => {
    let t = 0;
    const { source, pushFaces } = createFaceSignal(100, () => t);
    const got: FaceObservation[] = [];
    const unsub = source.subscribe((o) => got.push(o));
    pushFaces([face()]); // t=0 delivered
    t = 30; pushFaces([face()]); // dropped
    t = 60; pushFaces([]); // visibility flip: delivered despite throttle
    t = 70; pushFaces([]); // dropped
    t = 200; pushFaces([face()]); // delivered
    expect(got.map((o) => o.faceVisible)).toEqual([true, false, true]);
    unsub();
    t = 500; pushFaces([face()]);
    expect(got).toHaveLength(3);
  });
});
