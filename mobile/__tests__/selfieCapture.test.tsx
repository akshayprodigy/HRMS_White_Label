import { act, fireEvent, screen } from '@testing-library/react-native';
import { renderWithProviders } from '../test-utils';
import type { FaceLike } from '../src/features/punch/faceSignal';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
jest.mock('expo-image-picker', () => ({ launchCameraAsync: jest.fn(), CameraType: { front: 'front' } }));
jest.mock('expo-file-system', () => ({ File: class {}, Directory: class {}, Paths: {} }));
jest.mock('expo-image-manipulator', () => ({ manipulateAsync: jest.fn(), SaveFormat: { JPEG: 'jpeg' } }));
jest.mock('../src/features/punch/api', () => ({ compressSelfie: jest.fn(async (u: string) => u) }));
jest.mock('../src/features/punch/store', () => ({ selfieFiles: { remove: jest.fn(async () => undefined) } }));

let mockOnFaces: (f: FaceLike[]) => void = () => undefined;
let mockPerm = { hasPermission: true, canRequestPermission: true, requestPermission: jest.fn(async () => true) };
let mockPhotos = 0;
jest.mock('../src/features/punch/faceCameraLoader', () => {
  const { View } = require('react-native');
  const { useImperativeHandle } = require('react');
  return {
    loadFaceCamera: () => ({
      useCameraPermission: () => mockPerm,
      FaceCamera: ({ onFaces, handleRef }: { onFaces: (f: FaceLike[]) => void; handleRef: React.Ref<unknown> }) => {
        mockOnFaces = onFaces;
        useImperativeHandle(handleRef, () => ({ takePhoto: async () => `file:///shot${++mockPhotos}.jpg` }), []);
        return <View testID="fake-camera" />;
      },
    }),
  };
});

import { SelfieCapture } from '../src/features/punch/SelfieCapture';

const face = (l: number): FaceLike => ({ yawAngle: 0, leftEyeOpenProbability: l, rightEyeOpenProbability: l });

describe('SelfieCapture (native face camera)', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.spyOn(Math, 'random').mockReturnValue(0.1); // blink challenge
    mockPhotos = 0;
    mockPerm = { hasPermission: true, canRequestPermission: true, requestPermission: jest.fn(async () => true) };
  });
  afterEach(() => { jest.useRealTimers(); jest.restoreAllMocks(); });

  it('a blink passes the challenge: onDone gets liveness_passed true', async () => {
    const onDone = jest.fn();
    await renderWithProviders(<SelfieCapture onDone={onDone} onCancel={jest.fn()} />);
    await fireEvent.press(screen.getByTestId('selfie-capture'));
    expect(screen.getByTestId('liveness-prompt').props.children).toBe('Blink');
    let t = 0;
    for (const v of [0.9, 0.1, 0.9]) {
      t += 200; jest.setSystemTime(Date.now() + t);
      await act(async () => { mockOnFaces([face(v)]); });
    }
    expect(onDone).toHaveBeenCalledWith({ uri: 'file:///shot1.jpg', liveness_passed: true, liveness_score: null });
  });

  it('two retries after a timeout, then submit-for-review sends liveness_passed false', async () => {
    const onDone = jest.fn();
    await renderWithProviders(<SelfieCapture onDone={onDone} onCancel={jest.fn()} />);
    for (let i = 0; i < 2; i++) {
      await fireEvent.press(screen.getByTestId('selfie-capture'));
      await act(async () => { jest.advanceTimersByTime(8100); });
      expect(screen.getByTestId('selfie-error')).toBeTruthy();
      expect(screen.getByText('Try again')).toBeTruthy();
      expect(onDone).not.toHaveBeenCalled();
    }
    await fireEvent.press(screen.getByTestId('selfie-capture'));
    await act(async () => { jest.advanceTimersByTime(8100); });
    expect(screen.queryByTestId('selfie-capture')).toBeNull(); // retries used up
    await fireEvent.press(screen.getByTestId('selfie-submit-review'));
    expect(onDone).toHaveBeenCalledWith({ uri: 'file:///shot3.jpg', liveness_passed: false, liveness_score: null });
  });

  it('denied permission explains and offers settings; skip still works', async () => {
    mockPerm = { hasPermission: false, canRequestPermission: false, requestPermission: jest.fn() };
    const onDone = jest.fn();
    await renderWithProviders(<SelfieCapture onDone={onDone} onCancel={jest.fn()} />);
    expect(screen.getByTestId('camera-open-settings')).toBeTruthy();
    await fireEvent.press(screen.getByTestId("selfie-skip"));
    expect(onDone).toHaveBeenCalledWith(null);
  });
});
