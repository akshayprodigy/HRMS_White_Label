import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import type { PickedFile } from './api';
import { ALLOWED_PROOF_TYPES } from './validation';

export class PickError extends Error {}

/** Camera capture (JPEG). Returns null if the user cancels; throws PickError when camera access is denied. */
export async function captureProofPhoto(): Promise<PickedFile | null> {
  const perm = await ImagePicker.requestCameraPermissionsAsync();
  if (!perm.granted) throw new PickError('Camera access is off. Enable it in Settings, or choose a file instead.');
  const res = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.7 });
  const a = res.canceled ? null : res.assets?.[0];
  if (!a) return null;
  return { uri: a.uri, name: a.fileName || `proof-${Date.now()}.jpg`, mimeType: a.mimeType || 'image/jpeg', size: a.fileSize ?? null };
}

/** PDF or image from the system document picker (copied to cache so it can be uploaded). */
export async function pickProofDocument(): Promise<PickedFile | null> {
  const res = await DocumentPicker.getDocumentAsync({ type: ALLOWED_PROOF_TYPES, copyToCacheDirectory: true, multiple: false });
  const a = res.canceled ? null : res.assets?.[0];
  if (!a) return null;
  return { uri: a.uri, name: a.name, mimeType: a.mimeType || 'application/octet-stream', size: a.size ?? null };
}
