import { memo, useEffect, useImperativeHandle, useMemo, useRef, type Ref } from 'react';
import { StyleSheet, type StyleProp, type ViewStyle } from 'react-native';
import { Camera, CommonResolutions, useCameraDevice, useCameraPermission, usePhotoOutput } from 'react-native-vision-camera';
import { createFaceDetectorOutput, createImageFaceDetector, type Face, type ImageFaceDetector } from 'react-native-vision-camera-face-detector';

/**
 * Native-only module: VisionCamera front camera + ML Kit face detector. Imported lazily through loadFaceCamera()
 * (see faceCameraLoader.ts) so Jest and builds without the native modules never touch it.
 *
 * The detector output is created ONCE (useMemo with constant options) and routed through refs. The package's own
 * <Camera>/useFaceDetectorOutput rebuild the output whenever their host re-renders, which would restart the camera
 * session mid-challenge; every prop here must therefore stay referentially stable.
 */
export type FaceCameraHandle = { takePhoto(): Promise<string> };
export { useCameraPermission };
export type FaceCameraProps = {
  /** Called for every detector callback (module never re-subscribes, so identity changes are fine but keep it stable anyway). */
  onFaces: (faces: Face[]) => void;
  onError: (e: Error) => void;
  /** Called once when the device has no front camera. */
  onNoDevice: () => void;
  handleRef: Ref<FaceCameraHandle>;
  /** Camera runs only while true (screen focused and app in the foreground). */
  isActive: boolean;
  style?: StyleProp<ViewStyle>;
};

function FaceCameraImpl({ onFaces, onError, onNoDevice, handleRef, isActive, style }: FaceCameraProps) {
  const device = useCameraDevice('front');
  const onFacesRef = useRef(onFaces);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    onFacesRef.current = onFaces;
    onErrorRef.current = onError;
  }, [onFaces, onError]);

  // The refs are only read inside the detector's callbacks (never during render); the output itself must be built once.
  /* eslint-disable react-hooks/refs */
  const faceOutput = useMemo(
    () => createFaceDetectorOutput({
      onFacesDetected: (faces) => onFacesRef.current(faces),
      onError: (e) => onErrorRef.current(e),
      outputResolution: 'preview',
      cameraFacing: 'front',
      performanceMode: 'fast',
      runClassifications: true, // eye-open probabilities
      runLandmarks: false,
      runContours: false,
      trackingEnabled: true, // trackingId: a change mid-challenge means a different face
    }),
    [],
  );
  /* eslint-enable react-hooks/refs */
  // ~HD 4:3 still: with the 720px compression in compressSelfie this keeps uploads at today's size.
  const photoOutput = usePhotoOutput({ targetResolution: CommonResolutions.HD_4_3, quality: 0.8, qualityPrioritization: 'speed' });
  const outputs = useMemo(() => [faceOutput, photoOutput], [faceOutput, photoOutput]);

  useImperativeHandle(handleRef, () => ({
    async takePhoto() {
      const file = await photoOutput.capturePhotoToFile({ flashMode: 'off', enableShutterSound: false }, {});
      return file.filePath.startsWith('file://') ? file.filePath : `file://${file.filePath}`;
    },
  }), [photoOutput]);

  const hasDevice = device != null;
  useEffect(() => {
    if (!hasDevice) onNoDevice();
  }, [hasDevice, onNoDevice]);
  if (!device) return null;
  return <Camera style={style ?? styles.fill} device={device} isActive={isActive} outputs={outputs} onError={onError} />;
}

export const FaceCamera = memo(FaceCameraImpl);
const styles = StyleSheet.create({ fill: { flex: 1 } });

let imageDetector: ImageFaceDetector | null = null;
/**
 * Runs ML Kit's still-image detector on the captured file: true only for exactly one face. Any failure -> false
 * (fail closed: liveness then reports false and the punch is flagged for review rather than passing unverified).
 */
export function stillHasExactlyOneFace(uri: string): boolean {
  try {
    imageDetector ??= createImageFaceDetector({ performanceMode: 'fast', runClassifications: false, runLandmarks: false, runContours: false });
    return imageDetector.detectFaces(uri).length === 1;
  } catch {
    return false;
  }
}
