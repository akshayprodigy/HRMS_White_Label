import { act, render } from '@testing-library/react-native';
import { useState, createRef } from 'react';
import { StyleSheet } from 'react-native';
import type { FaceCameraHandle } from '../src/features/punch/FaceCamera';

const mockCreateOutput = jest.fn((_o: unknown) => ({ kind: 'face-output' }));
const mockCameraRender = jest.fn();
const mockPhotoOutput = { capturePhotoToFile: jest.fn(async () => ({ filePath: '/tmp/p.jpg' })) };
const mockDetect = jest.fn(() => [{}]);
const mockCreateImage = jest.fn((_o: unknown) => ({ detectFaces: mockDetect }));

jest.mock('react-native-vision-camera', () => ({
  Camera: (props: unknown) => { mockCameraRender(props); return null; },
  CommonResolutions: { HD_4_3: { width: 768, height: 1024 } },
  useCameraDevice: () => ({ id: 'front' }),
  useCameraPermission: () => ({ hasPermission: true }),
  usePhotoOutput: () => mockPhotoOutput,
}));
jest.mock('react-native-vision-camera-face-detector', () => ({
  createFaceDetectorOutput: (o: unknown) => mockCreateOutput(o),
  createImageFaceDetector: (o: unknown) => mockCreateImage(o),
}));

import { FaceCamera, stillHasExactlyOneFace } from '../src/features/punch/FaceCamera';

const style = StyleSheet.create({ s: { flex: 1 } }).s;
const noop = () => undefined;
const ref = createRef<FaceCameraHandle>();
let bump: () => void = () => undefined;
function Parent() {
  const [, setN] = useState(0);
  bump = () => setN((n) => n + 1);
  return <FaceCamera style={style} handleRef={ref} onFaces={noop} onError={noop} onNoDevice={noop} isActive />;
}

describe('FaceCamera', () => {
  beforeEach(() => jest.clearAllMocks());

  it('a parent re-render neither re-renders the camera nor rebuilds the detector output', async () => {
    await render(<Parent />);
    expect(mockCreateOutput).toHaveBeenCalledTimes(1);
    expect(mockCreateOutput).toHaveBeenCalledWith(expect.objectContaining({ trackingEnabled: true, runClassifications: true, runLandmarks: false, runContours: false, performanceMode: 'fast', cameraFacing: 'front' }));
    expect(mockCameraRender).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 3; i++) await act(async () => { bump(); });
    expect(mockCreateOutput).toHaveBeenCalledTimes(1);
    expect(mockCameraRender).toHaveBeenCalledTimes(1);
  });

  it('takePhoto returns a file:// uri from the photo output (flash off)', async () => {
    await render(<Parent />);
    await expect(ref.current?.takePhoto()).resolves.toBe('file:///tmp/p.jpg');
    expect(mockPhotoOutput.capturePhotoToFile).toHaveBeenCalledWith(expect.objectContaining({ flashMode: 'off' }), {});
  });

  it('stillHasExactlyOneFace requires exactly one face and fails closed', () => {
    mockDetect.mockReturnValueOnce([{}]);
    expect(stillHasExactlyOneFace('file:///a.jpg')).toBe(true);
    mockDetect.mockReturnValueOnce([{}, {}]);
    expect(stillHasExactlyOneFace('file:///a.jpg')).toBe(false);
    mockDetect.mockReturnValueOnce([]);
    expect(stillHasExactlyOneFace('file:///a.jpg')).toBe(false);
    mockDetect.mockImplementationOnce(() => { throw new Error('ml kit'); });
    expect(stillHasExactlyOneFace('file:///a.jpg')).toBe(false);
  });
});
