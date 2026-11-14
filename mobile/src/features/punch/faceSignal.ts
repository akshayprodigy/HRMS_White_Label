import type { FaceObservation, FaceSignalSource } from './liveness';

/** The subset of the face detector's `Face` we read (kept structural so this file stays native-free and testable). */
export type FaceLike = { leftEyeOpenProbability?: number; rightEyeOpenProbability?: number; yawAngle: number; trackingId?: number };

/**
 * Detector output -> observation. Exactly one face counts as "visible": 0 faces = nobody there, and >1 faces is treated
 * as not visible so a bystander (or a photo of a face held next to the real one) cannot satisfy the challenge.
 */
export function facesToObservation(faces: readonly FaceLike[]): FaceObservation {
  if (faces.length !== 1) return { faceVisible: false };
  const f = faces[0];
  return { faceVisible: true, leftEyeOpen: f.leftEyeOpenProbability, rightEyeOpen: f.rightEyeOpenProbability, yaw: f.yawAngle, trackingId: f.trackingId };
}

/**
 * A FaceSignalSource fed with push(). Every detector callback is delivered (no throttling): ML Kit already keeps only
 * the latest frame, and dropping samples could swallow a short closed-eye reading and miss a real blink.
 */
export function createFaceSignal() {
  const subs = new Set<(o: FaceObservation) => void>();
  const source: FaceSignalSource = {
    subscribe(cb) {
      subs.add(cb);
      return () => { subs.delete(cb); };
    },
  };
  const push = (o: FaceObservation) => {
    for (const cb of [...subs]) cb(o);
  };
  return { source, push, pushFaces: (faces: readonly FaceLike[]) => push(facesToObservation(faces)) };
}
