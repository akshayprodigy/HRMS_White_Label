import type { FaceObservation, FaceSignalSource } from './liveness';

/** The subset of the face detector's `Face` we read (kept structural so this file stays native-free and testable). */
export type FaceLike = { leftEyeOpenProbability?: number; rightEyeOpenProbability?: number; yawAngle: number };

/**
 * Detector output -> observation. Exactly one face counts as "visible": 0 faces = nobody there, and >1 faces is treated
 * as not visible so a bystander (or a photo of a face held next to the real one) cannot satisfy the challenge.
 */
export function facesToObservation(faces: readonly FaceLike[]): FaceObservation {
  if (faces.length !== 1) return { faceVisible: false };
  const f = faces[0];
  return { faceVisible: true, leftEyeOpen: f.leftEyeOpenProbability, rightEyeOpen: f.rightEyeOpenProbability, yaw: f.yawAngle };
}

export const OBSERVATION_INTERVAL_MS = 80; // ~12 observations per second

/**
 * A FaceSignalSource fed with push(). Observations are throttled (detector callbacks can be 30/s) but a change of
 * `faceVisible` is always delivered immediately so losing the face is never delayed or dropped.
 */
export function createFaceSignal(intervalMs = OBSERVATION_INTERVAL_MS, now: () => number = Date.now) {
  const subs = new Set<(o: FaceObservation) => void>();
  let lastAt = -Infinity;
  let lastVisible: boolean | null = null;
  const source: FaceSignalSource = {
    subscribe(cb) {
      subs.add(cb);
      return () => { subs.delete(cb); };
    },
  };
  const push = (o: FaceObservation) => {
    const t = now();
    if (o.faceVisible === lastVisible && t - lastAt < intervalMs) return;
    lastAt = t;
    lastVisible = o.faceVisible;
    for (const cb of [...subs]) cb(o);
  };
  return { source, push, pushFaces: (faces: readonly FaceLike[]) => push(facesToObservation(faces)) };
}
