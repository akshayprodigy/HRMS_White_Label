/** The native face camera, or null when the VisionCamera/ML Kit native modules are unavailable (Jest, a build without them). */
export type FaceCameraModule = typeof import('./FaceCamera');

let cached: FaceCameraModule | null | undefined;
export function loadFaceCamera(): FaceCameraModule | null {
  if (cached !== undefined) return cached;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    cached = require('./FaceCamera') as FaceCameraModule;
  } catch {
    cached = null;
  }
  return cached;
}
