import { File } from 'expo-file-system';
import { manipulateAsync, SaveFormat } from 'expo-image-manipulator';
import { api } from '../../api/client';
import { ApiError, normalizeError } from '../../api/errors';
import type { AttendanceRow } from '../../api/types';
import { PunchQueue, isAlreadyRecorded, isRetryable, type PunchKind, type QueuedPunch, type SyncDeps, type SyncResult } from './queue';
import { fileStore, selfieFiles } from './store';

export { friendlyReason } from './queue';

export const MAX_SELFIE_BYTES = 3 * 1024 * 1024;

let queue: PunchQueue | null = null;
export function getPunchQueue(): PunchQueue {
  return (queue ??= new PunchQueue(fileStore(), selfieFiles));
}
/** Test hook. */
export function setPunchQueue(q: PunchQueue | null) {
  queue = q;
}

/** Resize + JPEG-compress until under the server's 3 MB limit. */
export async function compressSelfie(uri: string): Promise<string> {
  let out = uri;
  for (const [width, compress] of [[720, 0.7], [480, 0.5], [320, 0.4]] as const) {
    const r = await manipulateAsync(uri, [{ resize: { width } }], { compress, format: SaveFormat.JPEG });
    out = r.uri;
    let size = 0;
    try { size = new File(out).size ?? 0; } catch { size = 0; }
    if (size <= MAX_SELFIE_BYTES) break;
  }
  return out;
}

/** POST /attendance/selfie (multipart `file`) -> selfie_id. */
export async function uploadSelfie(uri: string): Promise<number> {
  const form = new FormData();
  form.append('file', { uri, name: 'selfie.jpg', type: 'image/jpeg' } as unknown as Blob);
  const res = await api.post<{ selfie_id: number }>('/attendance/selfie', form, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 });
  return res.data.selfie_id;
}

export const syncDeps: SyncDeps = {
  uploadSelfie,
  async syncPunches(punches) {
    const res = await api.post<{ results: SyncResult[] }>('/attendance/offline-sync', { punches });
    return res.data.results;
  },
};

export type Fix = { latitude: number; longitude: number; accuracy: number | null; isMock: boolean };
export type SelfieInput = { uri: string; liveness_passed: boolean | null; liveness_score: number | null };
/** `capturedAt` is stamped when the user taps Punch (not when the request finally goes out). */
export type PunchInput = { kind: PunchKind; fix: Fix | null; selfie?: SelfieInput | null; uuid: () => string; capturedAt?: string };

export type PunchOutcome =
  | { status: 'ok'; attendance: AttendanceRow & { geo_flag?: string | null; attribution_flag?: string | null }; flag: string | null }
  | { status: 'queued'; item: QueuedPunch; behind?: boolean }
  | { status: 'already' }
  | { status: 'error'; error: ApiError; needsSelfie: boolean };

export function selfieRequired(e: ApiError): boolean {
  return e.status === 400 && /selfie is required/i.test(e.message);
}

/**
 * Online punch with an offline fallback. 4xx responses (geofence 422, selfie required 400, ...) are real
 * rejections and are shown, never queued; only transport failure / 5xx / 429 queue the punch for /offline-sync.
 */
export async function submitPunch(input: PunchInput, q: PunchQueue = getPunchQueue()): Promise<PunchOutcome> {
  const capturedAt = input.capturedAt ?? new Date().toISOString();
  const { fix, selfie } = input;
  const cleanup = () => (selfie ? selfieFiles.remove(selfie.uri) : undefined);
  const queueIt = async (selfieId: number | null, behind = false): Promise<PunchOutcome> => {
    const item = await q.enqueue({
      client_uuid: input.uuid(),
      kind: input.kind,
      captured_at: capturedAt,
      latitude: fix?.latitude ?? null,
      longitude: fix?.longitude ?? null,
      accuracy: fix?.accuracy ?? null,
      is_mock_location: fix?.isMock ?? false,
      selfie_uri: selfie?.uri ?? null,
      selfie_id: selfieId,
      liveness_passed: selfie?.liveness_passed ?? null,
      liveness_score: selfie?.liveness_score ?? null,
    });
    await cleanup(); // the queue keeps its own copy
    return { status: 'queued', item, behind };
  };

  // Order matters (in before out): while anything is pending, new punches join the queue instead of racing it.
  await q.ready();
  if (q.getSnapshot().items.length > 0) return queueIt(null, true);

  let selfieId: number | null = null;
  if (selfie) {
    try {
      selfieId = await uploadSelfie(selfie.uri);
    } catch (e) {
      const err = normalizeError(e);
      if (isRetryable(err)) return queueIt(null);
      return { status: 'error', error: err, needsSelfie: false };
    }
  }
  const body = {
    ...(input.kind === 'in' ? { mode: 'mobile' } : {}),
    latitude: fix?.latitude ?? null,
    longitude: fix?.longitude ?? null,
    accuracy: fix?.accuracy ?? null,
    is_mock_location: fix?.isMock ?? false,
    selfie_id: selfieId,
    liveness_passed: selfie?.liveness_passed ?? null,
    liveness_score: selfie?.liveness_score ?? null,
  };
  try {
    const res = await api.post(input.kind === 'in' ? '/attendance/mark' : '/attendance/punch-out', body);
    const att = res.data as AttendanceRow & { geo_flag?: string | null; attribution_flag?: string | null };
    await cleanup();
    return { status: 'ok', attendance: att, flag: att.geo_flag ?? att.attribution_flag ?? null };
  } catch (e) {
    const err = normalizeError(e);
    if (isRetryable(err)) return queueIt(selfieId);
    if (isAlreadyRecorded(err.message)) { await cleanup(); return { status: 'already' }; }
    return { status: 'error', error: err, needsSelfie: selfieRequired(err) };
  }
}

/** Human text for the flagged-result notice. */
export function flagNotice(flag: string | null): string | null {
  if (!flag) return null;
  return `Punch recorded, but flagged for review (${flag.replace(/_/g, ' ').toLowerCase()}).`;
}
