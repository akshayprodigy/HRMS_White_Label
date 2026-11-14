import { memo, useImperativeHandle, type Ref } from 'react';
import { StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { CommonResolutions, useCameraDevice, usePhotoOutput, useCameraPermission } from 'react-native-vision-camera';
import { Camera, type Face } from 'react-native-vision-camera-face-detector';

/**
 * Native-only module: VisionCamera front camera + ML Kit face detector. Imported lazily through loadFaceCamera()
 * (see faceCameraLoader.ts) so Jest and builds without the native modules never touch it.
 */
export type FaceCameraHandle = { takePhoto(): Promise<string> };
export { useCameraPermission };
export type FaceCameraProps = {
  /** Must be referentially stable: the detector output is rebuilt when this component re-renders. */
  onFaces: (faces: Face[]) => void;
  onError: (e: Error) => void;
  handleRef: Ref<FaceCameraHandle>;
  style?: StyleProp<ViewStyle>;
};

function FaceCameraImpl({ onFaces, onError, handleRef, style }: FaceCameraProps) {
  const device = useCameraDevice('front');
  // ~HD 4:3 still: with the 720px compression in compressSelfie this keeps uploads at today's size.
  const photoOutput = usePhotoOutput({ targetResolution: CommonResolutions.HD_4_3, quality: 0.8, qualityPrioritization: 'speed' });
  useImperativeHandle(handleRef, () => ({
    async takePhoto() {
      const file = await photoOutput.capturePhotoToFile({ flashMode: 'off', enableShutterSound: false }, {});
      return file.filePath.startsWith('file://') ? file.filePath : `file://${file.filePath}`;
    },
  }), [photoOutput]);
  if (!device) {
    return <View style={[style, styles.center]}><Text>No front camera found</Text></View>;
  }
  return (
    <Camera
      style={style}
      device={device}
      isActive
      outputs={[photoOutput]}
      cameraFacing="front"
      performanceMode="fast"
      runClassifications
      runLandmarks={false}
      runContours={false}
      trackingEnabled={false}
      onFacesDetected={onFaces}
      onError={onError}
    />
  );
}

export const FaceCamera = memo(FaceCameraImpl);
const styles = StyleSheet.create({ center: { alignItems: 'center', justifyContent: 'center' } });
