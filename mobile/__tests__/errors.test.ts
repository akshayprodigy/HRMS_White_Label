import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { ApiError, normalizeError } from '../src/api/errors';

function axiosErr(status: number, data: unknown): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  const res = { status, data, statusText: '', headers: {}, config } as AxiosResponse;
  return new AxiosError('x', 'ERR_BAD_REQUEST', config, {}, res);
}

describe('normalizeError', () => {
  it('reads the backend error envelope', () => {
    const e = normalizeError(axiosErr(400, { error: { code: 'bad_thing', message: 'Nope' } }));
    expect(e).toBeInstanceOf(ApiError);
    expect([e.message, e.status, e.code]).toEqual(['Nope', 400, 'bad_thing']);
  });
  it('reads FastAPI validation detail arrays', () => {
    const e = normalizeError(axiosErr(422, { detail: [{ msg: 'field required' }, { msg: 'too short' }] }));
    expect(e.message).toBe('field required; too short');
    expect(e.status).toBe(422);
  });
  it('reads string detail', () => {
    expect(normalizeError(axiosErr(401, { detail: 'Incorrect email or password' })).message).toBe('Incorrect email or password');
  });
  it('falls back to status text and handles network errors', () => {
    expect(normalizeError(axiosErr(418, '<html>')).message).toBe('Request failed (418)');
    const net = normalizeError(new AxiosError('Network Error', 'ERR_NETWORK'));
    expect([net.status, net.code]).toEqual([0, 'network_error']);
  });
  it('never leaks server internals for 5xx or network failures', () => {
    const e = normalizeError(axiosErr(500, { error: { code: 'internal', message: 'Traceback: sqlalchemy.exc.OperationalError (1045)' } }));
    expect(e.message).toBe('The server is having trouble. Please try again in a moment.');
    expect(e.message).not.toMatch(/sqlalchemy|Traceback/);
    expect(e.status).toBe(500);
    expect(normalizeError(axiosErr(503, 'upstream connect error')).message).toMatch(/having trouble/);
    expect(normalizeError(new AxiosError('connect ECONNREFUSED 10.0.0.1:8005', 'ERR_NETWORK')).message).toBe("Can't reach the server. Check your connection.");
  });
});
