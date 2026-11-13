import { isAxiosError } from 'axios';

export const MSG_SERVER = 'The server is having trouble. Please try again in a moment.';
export const MSG_NETWORK = "Can't reach the server. Check your connection.";

function devLog(detail: unknown) {
  if (__DEV__ && process.env.NODE_ENV !== 'test') console.warn('[api]', detail);
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/** Handles {"error":{code,message}}, FastAPI {detail:[{msg}]} / {detail:"..."}, and transport failures. */
export function normalizeError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  if (isAxiosError(err)) {
    const res = err.response;
    if (!res) {
      return new ApiError(
        err.code === 'ECONNABORTED' ? 'The request timed out. Please try again.' : MSG_NETWORK,
        0,
        'network_error',
      );
    }
    const data = res.data as unknown;
    if (res.status >= 500) {
      devLog({ status: res.status, data });
      const code = data && typeof data === 'object' ? (data as { error?: { code?: string } }).error?.code : undefined;
      return new ApiError(MSG_SERVER, res.status, code);
    }
    if (data && typeof data === 'object') {
      const d = data as { error?: { code?: string; message?: string }; detail?: unknown; message?: string };
      if (d.error && typeof d.error.message === 'string') return new ApiError(d.error.message, res.status, d.error.code);
      if (typeof d.detail === 'string') return new ApiError(d.detail, res.status);
      // Structured detail, e.g. the STRICT geofence 422: {error: "OUTSIDE_GEOFENCE", message, nearest_fence_name, ...}
      if (d.detail && typeof d.detail === 'object' && !Array.isArray(d.detail)) {
        const x = d.detail as { error?: unknown; message?: unknown };
        if (typeof x.message === 'string') return new ApiError(x.message, res.status, typeof x.error === 'string' ? x.error : undefined);
      }
      if (Array.isArray(d.detail)) {
        const msgs = d.detail
          .map((x) => (x && typeof x === 'object' && 'msg' in x ? String((x as { msg: unknown }).msg) : ''))
          .filter(Boolean);
        if (msgs.length) return new ApiError(msgs.join('; '), res.status, 'validation_error');
      }
      if (typeof d.message === 'string') return new ApiError(d.message, res.status);
    }
    return new ApiError(`Request failed (${res.status})`, res.status);
  }
  return new ApiError(err instanceof Error ? err.message : 'Unexpected error', 0);
}
