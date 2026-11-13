/* eslint-disable import/no-named-as-default-member */
import axios from 'axios';

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
  if (axios.isAxiosError(err)) {
    const res = err.response;
    if (!res) {
      return new ApiError(
        err.code === 'ECONNABORTED' ? 'The request timed out. Please try again.' : 'Cannot reach the server. Check your connection.',
        0,
        'network_error',
      );
    }
    const data = res.data as unknown;
    if (data && typeof data === 'object') {
      const d = data as { error?: { code?: string; message?: string }; detail?: unknown; message?: string };
      if (d.error && typeof d.error.message === 'string') return new ApiError(d.error.message, res.status, d.error.code);
      if (typeof d.detail === 'string') return new ApiError(d.detail, res.status);
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
