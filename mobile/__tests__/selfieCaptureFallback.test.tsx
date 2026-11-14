import { fireEvent, screen, waitFor } from '@testing-library/react-native';
import * as ImagePicker from 'expo-image-picker';
import { renderWithProviders } from '../test-utils';
import { SelfieCapture } from '../src/features/punch/SelfieCapture';

jest.mock('../src/config/tenant', () => ({ getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }), getApiBaseUrl: () => 'http://test/api/v1' }));
jest.mock('expo-image-picker', () => ({ launchCameraAsync: jest.fn(), CameraType: { front: 'front' } }));
jest.mock('expo-file-system', () => ({ File: class {}, Directory: class {}, Paths: {} }));
jest.mock('expo-image-manipulator', () => ({ manipulateAsync: jest.fn(), SaveFormat: { JPEG: 'jpeg' } }));
jest.mock('../src/features/punch/api', () => ({ compressSelfie: jest.fn(async (u: string) => u), withUprightCopy: jest.fn(async (u: string, check: (x: string) => unknown) => check(u)) }));
jest.mock('../src/features/punch/store', () => ({ selfieFiles: { remove: jest.fn(async () => undefined) } }));
jest.mock('expo-router', () => ({ useIsFocused: () => true }));
jest.mock('../src/features/punch/faceCameraLoader', () => ({ loadFaceCamera: () => null }));

describe('SelfieCapture without the native face module', () => {
  it('uses the system camera and reports liveness unknown (null), never true', async () => {
    (ImagePicker.launchCameraAsync as jest.Mock).mockResolvedValue({ canceled: false, assets: [{ uri: 'file:///sys.jpg' }] });
    const onDone = jest.fn();
    await renderWithProviders(<SelfieCapture onDone={onDone} onCancel={jest.fn()} />);
    await fireEvent.press(screen.getByTestId('selfie-capture'));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith({ uri: 'file:///sys.jpg', liveness_passed: null, liveness_score: null }));
  });
});
