import { act, fireEvent, screen } from '@testing-library/react-native';
import * as ImagePicker from 'expo-image-picker';
import { AppState } from 'react-native';
import { renderWithProviders } from '../test-utils';
import type { FaceLike } from '../src/features/punch/faceSignal';
import { selfieFiles } from '../src/features/punch/store';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
jest.mock('expo-router', () => ({ useIsFocused: () => true }));
jest.mock('expo-image-picker', () => ({ launchCameraAsync: jest.fn(), CameraType: { front: 'front' } }));
jest.mock('expo-file-system', () => ({ File: class {}, Directory: class {}, Paths: {} }));
jest.mock('expo-image-manipulator', () => ({ manipulateAsync: jest.fn(), SaveFormat: { JPEG: 'jpeg' } }));
jest.mock('../src/features/punch/api', () => ({ compressSelfie: jest.fn(async (u: string) => u), withUprightCopy: jest.fn(async (u: string, check: (x: string) => unknown) => check(u)) }));
jest.mock('../src/features/punch/store', () => ({ selfieFiles: { remove: jest.fn(async () => undefined) } }));

let mockOnFaces: (f: FaceLike[]) => void = () => undefined;
let mockPerm = { hasPermission: true, canRequestPermission: true, requestPermission: jest.fn(async () => true) };
let mockPhotos = 0;
let mockTake: () => Promise<string> = async () => `file:///shot${++mockPhotos}.jpg`;
let mockStillOk = true;
let mockCameraError = false;
let mockActive = true;
jest.mock('../src/features/punch/faceCameraLoader', () => {
  const { View } = require('react-native');
  const { useEffect, useImperativeHandle } = require('react');
  return {
    loadFaceCamera: () => ({
      useCameraPermission: () => mockPerm,
      stillHasExactlyOneFace: () => mockStillOk,
      FaceCamera: ({ onFaces, onError, handleRef, isActive }: { onFaces: (f: FaceLike[]) => void; onError: (e: Error) => void; handleRef: React.Ref<unknown>; isActive: boolean }) => {
        mockOnFaces = onFaces;
        mockActive = isActive;
        useImperativeHandle(handleRef, () => ({ takePhoto: () => mockTake() }), []);
        useEffect(() => { if (mockCameraError) onError(new Error('boom')); }, [onError]);
        return <View testID="fake-camera" />;
      },
    }),
  };
});

import { SelfieCapture } from '../src/features/punch/SelfieCapture';

const face = (l: number, trackingId = 1): FaceLike => ({ yawAngle: 0, leftEyeOpenProbability: l, rightEyeOpenProbability: l, trackingId });
const blink = async () => { for (const v of [0.9, 0.1, 0.9]) await act(async () => { mockOnFaces([face(v)]); }); };
const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });
const removeMock = selfieFiles.remove as jest.Mock;

describe('SelfieCapture (native face camera)', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.spyOn(Math, 'random').mockReturnValue(0.1); // blink challenge
    mockPhotos = 0;
    mockTake = async () => `file:///shot${++mockPhotos}.jpg`;
    mockStillOk = true;
    mockCameraError = false;
    mockPerm = { hasPermission: true, canRequestPermission: true, requestPermission: jest.fn(async () => true) };
    removeMock.mockClear();
  });
  afterEach(() => { jest.useRealTimers(); jest.restoreAllMocks(); });

  it('a blink passes the challenge: onDone gets liveness_passed true', async () => {
    const onDone = jest.fn();
    await renderWithProviders(<SelfieCapture onDone={onDone} onCancel={jest.fn()} />);
    await fireEvent.press(screen.getByTestId('selfie-capture'));
    expect(screen.getByTestId('liveness-prompt').props.children).toBe('Blink');
    await blink();
    await flush();
    expect(onDone).toHaveBeenCalledWith({ uri: 'file:///shot1.jpg', liveness_passed: true, liveness_score: null });
  });

  it('a still that does not show exactly one face fails liveness', async () => {
    mockStillOk = false;
    const onDone = jest.fn();
    await renderWithProviders(<SelfieCapture onDone={onDone} onCancel={jest.fn()} />);
    await fireEvent.press(screen.getByTestId('selfie-capture'));
    await blink();
    await flush();
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.getByTestId('selfie-error')).toBeTruthy();
    expect(removeMock).toHaveBeenCalledWith('file:///shot1.jpg'); // the failed still is deleted
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

  it('cancel mid-challenge aborts the run without capturing and deletes nothing it did not take', async () => {
    const onCancel = jest.fn();
    await renderWithProviders(<SelfieCapture onDone={jest.fn()} onCancel={onCancel} />);
    await fireEvent.press(screen.getByTestId('selfie-capture'));
    await fireEvent.press(screen.getByText('Cancel'));
    await flush();
    expect(onCancel).toHaveBeenCalled();
    expect(mockPhotos).toBe(0);
    await act(async () => { jest.advanceTimersByTime(9000); }); // the old timer must not fire a capture
    expect(mockPhotos).toBe(0);
  });

  it('skip during a held (failed) still deletes it', async () => {
    const onDone = jest.fn();
    await renderWithProviders(<SelfieCapture onDone={onDone} onCancel={jest.fn()} />);
    for (let i = 0; i < 3; i++) {
      await fireEvent.press(screen.getByTestId('selfie-capture'));
      await act(async () => { jest.advanceTimersByTime(8100); });
    }
    removeMock.mockClear();
    await fireEvent.press(screen.getByTestId('selfie-skip'));
    await flush();
    expect(onDone).toHaveBeenCalledWith(null);
    expect(removeMock).toHaveBeenCalledWith('file:///shot3.jpg');
  });

  it('unmounting while the still is being taken deletes that still', async () => {
    let release: (u: string) => void = () => undefined;
    mockTake = () => new Promise<string>((r) => { release = r; });
    const view = await renderWithProviders(<SelfieCapture onDone={jest.fn()} onCancel={jest.fn()} />);
    await fireEvent.press(screen.getByTestId('selfie-capture'));
    await blink();
    await flush();
    await view.unmount();
    await act(async () => { release('file:///late.jpg'); });
    await flush();
    expect(removeMock).toHaveBeenCalledWith('file:///late.jpg');
  });

  it('backgrounding the app pauses the run without consuming a retry', async () => {
    let handler: (s: string) => void = () => undefined;
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((_: string, h: (s: string) => void) => { handler = h; return { remove: jest.fn() }; }) as never);
    await renderWithProviders(<SelfieCapture onDone={jest.fn()} onCancel={jest.fn()} />);
    await fireEvent.press(screen.getByTestId('selfie-capture'));
    await act(async () => { handler('background'); });
    await flush();
    expect(mockActive).toBe(false);
    expect(mockPhotos).toBe(0);
    expect(screen.getByTestId('selfie-error')).toBeTruthy();
    expect(screen.getByText('Take selfie')).toBeTruthy(); // not "Try again": no failure counted
    await act(async () => { handler('active'); });
    expect(mockActive).toBe(true);
  });

  it('a camera error falls back to the system camera with liveness null, and the face camera can be retried', async () => {
    mockCameraError = true;
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValue({ canceled: false, assets: [{ uri: 'file:///sys.jpg' }] });
    const onDone = jest.fn();
    await renderWithProviders(<SelfieCapture onDone={onDone} onCancel={jest.fn()} />);
    expect(screen.getByTestId('selfie-camera-problem')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('selfie-capture'));
    await flush();
    expect(onDone).toHaveBeenCalledWith({ uri: 'file:///sys.jpg', liveness_passed: null, liveness_score: null });
    mockCameraError = false;
    await fireEvent.press(screen.getByTestId('selfie-retry-camera'));
    expect(screen.getByTestId('fake-camera')).toBeTruthy();
  });

  it('denied permission explains and offers settings; skip still works', async () => {
    mockPerm = { hasPermission: false, canRequestPermission: false, requestPermission: jest.fn() };
    const onDone = jest.fn();
    await renderWithProviders(<SelfieCapture onDone={onDone} onCancel={jest.fn()} />);
    expect(screen.getByTestId('camera-open-settings')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('selfie-skip'));
    expect(onDone).toHaveBeenCalledWith(null);
  });
});

describe('withUprightCopy', () => {
  it('runs the check on an upright re-encoded copy and deletes the copy', async () => {
    const actual = jest.requireActual('../src/features/punch/api') as typeof import('../src/features/punch/api');
    const manip = require('expo-image-manipulator').manipulateAsync as jest.Mock;
    manip.mockResolvedValueOnce({ uri: 'file:///upright.jpg' });
    const deleted: string[] = [];
    const fs = require('expo-file-system');
    fs.File = class { constructor(public uri: string) {} delete() { deleted.push(this.uri); } };
    const seen: string[] = [];
    const ok = await actual.withUprightCopy('file:///raw.jpg', (u) => { seen.push(u); return true; });
    expect(ok).toBe(true);
    expect(manip).toHaveBeenCalledWith('file:///raw.jpg', [{ resize: { width: 720 } }], expect.objectContaining({ format: 'jpeg' }));
    expect(seen).toEqual(['file:///upright.jpg']);
    expect(deleted).toEqual(['file:///upright.jpg']);
  });
});
