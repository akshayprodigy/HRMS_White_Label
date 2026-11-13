import { fireEvent, screen, waitFor } from '@testing-library/react-native';
import type MockAdapter from 'axios-mock-adapter';
import { DocumentsScreen } from '../src/features/documents/DocumentsScreen';
import { PayslipsScreen } from '../src/features/payslips/PayslipsScreen';
import { fmtRupees, monthLabel, payslipFileName } from '../src/features/payslips/api';
import { downloadAndShare, downloadToCache, mimeForName, safeFileName } from '../src/lib/download';
import { GATE_BODY, renderWithProviders, setupApiMock, teardownApiMock } from '../test-utils';

jest.mock('../src/config/tenant', () => ({
  getTenant: () => ({ ...require('../tenants/dev/tenant.json'), id: 'dev' }),
  getApiBaseUrl: () => 'http://test/api/v1',
}));
jest.mock('../src/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 1, email: 'a@x.com' }, unverified: false }) }));
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
jest.mock('expo-router', () => ({ useRouter: () => ({ navigate: jest.fn(), push: jest.fn() }) }));

const mockDownload = jest.fn();
const mockDelete = jest.fn();
const mockShare = jest.fn();
const mockAvailable = jest.fn();
jest.mock('expo-file-system', () => {
  class Directory { create = jest.fn(); }
  class File {
    uri: string; name: string;
    constructor(_dir: unknown, name: string) { this.name = name; this.uri = `file:///cache/downloads/${name}`; }
    static downloadFileAsync = (...a: unknown[]) => mockDownload(...a);
    delete = () => mockDelete(this.name);
  }
  return { File, Directory, Paths: { cache: 'cache' } };
});
jest.mock('expo-sharing', () => ({ isAvailableAsync: () => mockAvailable(), shareAsync: (...a: unknown[]) => mockShare(...a) }));

let mock: MockAdapter;
beforeEach(() => {
  mock = setupApiMock();
  mockDownload.mockReset(); mockDelete.mockReset(); mockShare.mockReset(); mockAvailable.mockReset();
  mockAvailable.mockResolvedValue(true);
  mockDownload.mockImplementation(async (_u: string, dest: { name: string; uri: string }) => dest);
  mockShare.mockResolvedValue(undefined);
  mock.onGet('/attendance/today').reply(200, { is_marked: true, attendance: null });
});
afterEach(teardownApiMock);

describe('helpers', () => {
  it('sanitises file names and guesses mime types', () => {
    expect(safeFileName('../../etc/pass wd.pdf', 'x')).toBe('etc_pass_wd.pdf');
    expect(safeFileName('///', 'x')).toBe('x');
    expect(mimeForName('a.PDF')).toBe('application/pdf');
    expect(mimeForName('a.bin')).toBe('application/octet-stream');
  });
  it('formats payslip fields', () => {
    expect(monthLabel({ month: 3, year: 2026 })).toBe('March 2026');
    expect(payslipFileName({ month: 3, year: 2026 })).toBe('Payslip_2026_03.pdf');
    expect(fmtRupees(123456.5)).toBe('₹1,23,456.5');
  });
});

describe('downloadToCache / downloadAndShare', () => {
  it('sends the bearer token to the API base URL', async () => {
    await downloadToCache('/hr/payroll/payslips/3/download', 'Payslip_2026_03.pdf');
    expect(mockDownload).toHaveBeenCalledWith('http://test/api/v1/hr/payroll/payslips/3/download', expect.objectContaining({ name: 'Payslip_2026_03.pdf' }), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer t' }), idempotent: true }));
  });
  it('refreshes the token once on a 401 and retries', async () => {
    mock.onPost('/auth/refresh').reply(200, { access_token: 'new', refresh_token: 'r2' });
    mockDownload.mockRejectedValueOnce(new Error('Unable to download file: HTTP 401'));
    await downloadToCache('/x', 'a.pdf');
    expect(mockDownload).toHaveBeenCalledTimes(2);
    expect(mockDownload.mock.calls[1][2].headers.Authorization).toBe('Bearer new');
  });
  it('maps HTTP failures to friendly errors', async () => {
    mockDownload.mockRejectedValueOnce(new Error('Unable to download file: HTTP 404'));
    await expect(downloadToCache('/x', 'a.pdf')).rejects.toMatchObject({ status: 404, message: expect.stringMatching(/no longer available/) });
    mockDownload.mockRejectedValueOnce(new Error('Network request failed'));
    await expect(downloadToCache('/x', 'a.pdf')).rejects.toMatchObject({ code: 'network_error' });
  });
  it('shares the file and always deletes the cached copy', async () => {
    await downloadAndShare('/x', 'a.pdf');
    expect(mockShare).toHaveBeenCalledWith('file:///cache/downloads/a.pdf', expect.objectContaining({ mimeType: 'application/pdf' }));
    expect(mockDelete).toHaveBeenCalledWith('a.pdf');
    mockShare.mockRejectedValueOnce(new Error('boom'));
    await expect(downloadAndShare('/x', 'b.pdf')).rejects.toThrow('boom');
    expect(mockDelete).toHaveBeenCalledWith('b.pdf');
  });
  it('fails clearly when sharing is unavailable', async () => {
    mockAvailable.mockResolvedValue(false);
    await expect(downloadAndShare('/x', 'a.pdf')).rejects.toThrow(/isn't supported/);
    expect(mockDelete).toHaveBeenCalled();
  });
});

const slip = { id: 3, file_url: '/payslips/PAY-202610-1.pdf', published_at: '2026-11-01T08:00:00', month: 10, year: 2026, gross_pay: 50000, net_pay: 45000.5, advance_deduction: 1000, disbursed_amount: 0, payable_days: 30, lop_days: 1 };

describe('PayslipsScreen', () => {
  it('lists payslips and downloads the authenticated PDF (not file_url)', async () => {
    mock.onGet('/hr/payroll/my-payslips').reply(200, [slip]);
    await renderWithProviders(<PayslipsScreen />);
    const card = await screen.findByTestId('payslip-3');
    expect(card).toHaveTextContent(/OCTOBER 2026/);
    expect(card).toHaveTextContent(/₹45,000.5/);
    expect(card).toHaveTextContent(/Advance ₹1,000/);
    expect(card).toHaveTextContent(/1 LOP/);
    await fireEvent.press(screen.getByTestId('payslip-download-3'));
    await waitFor(() => expect(mockShare).toHaveBeenCalled());
    expect(mockDownload.mock.calls[0][0]).toBe('http://test/api/v1/hr/payroll/payslips/3/download');
    expect(mockShare.mock.calls[0][1]).toMatchObject({ dialogTitle: 'Payslip_2026_10.pdf' });
  });
  it('shows a friendly error when the download fails', async () => {
    mock.onGet('/hr/payroll/my-payslips').reply(200, [slip]);
    mockDownload.mockRejectedValue(new Error('Unable to download file: HTTP 403'));
    await renderWithProviders(<PayslipsScreen />);
    await fireEvent.press(await screen.findByTestId('payslip-download-3'));
    expect(await screen.findByTestId('payslips-download-error')).toHaveTextContent(/don't have access/);
  });
  it('shows an empty state', async () => {
    mock.onGet('/hr/payroll/my-payslips').reply(200, []);
    await renderWithProviders(<PayslipsScreen />);
    expect(await screen.findByTestId('payslips-empty')).toBeTruthy();
  });
  it('shows a load error with retry', async () => {
    mock.onGet('/hr/payroll/my-payslips').reply(500, {});
    await renderWithProviders(<PayslipsScreen />);
    expect(await screen.findByTestId('payslips-error')).toBeTruthy();
  });
  it('shows the gate notice on ATTENDANCE_REQUIRED', async () => {
    mock.onGet('/hr/payroll/my-payslips').reply(403, GATE_BODY);
    await renderWithProviders(<PayslipsScreen />);
    expect(await screen.findByTestId('gate-notice')).toBeTruthy();
  });
});

describe('DocumentsScreen', () => {
  const f16 = [
    { id: 7, fy: '25-26', reference_number: 'F16/25-26/001', part_b_url: '/tax/form16/part_b/x.pdf', part_b_generated_at: '2026-06-01T00:00:00', status: 'issued', issued_at: '2026-06-15T00:00:00' },
    { id: 8, fy: '24-25', reference_number: null, part_b_url: null, part_b_generated_at: null, status: 'draft', issued_at: null },
  ];
  const docs = [{ id: 5, doc_type: 'PAN', original_filename: 'pan card.jpg', remark: null, uploaded_at: '2026-01-02T00:00:00', uploaded_by_name: 'HR', verification_status: 'rejected', rejection_reason: 'Blurry' }];
  it('lists Form 16 and documents and downloads each via its own endpoint', async () => {
    mock.onGet('/tax/form16/my').reply(200, f16);
    mock.onGet('/hr/employees/me/documents').reply(200, docs);
    await renderWithProviders(<DocumentsScreen />);
    expect(await screen.findByTestId('form16-7')).toHaveTextContent(/FY 2025-26/);
    expect(screen.queryByTestId('form16-download-8')).toBeNull();
    expect(await screen.findByTestId('document-5')).toHaveTextContent(/Rejected: Blurry/);
    await fireEvent.press(screen.getByTestId('form16-download-7'));
    await waitFor(() => expect(mockShare).toHaveBeenCalledTimes(1));
    expect(mockDownload.mock.calls[0][0]).toBe('http://test/api/v1/tax/form16/7/download');
    await fireEvent.press(screen.getByTestId('document-download-5'));
    await waitFor(() => expect(mockShare).toHaveBeenCalledTimes(2));
    expect(mockDownload.mock.calls[1][0]).toBe('http://test/api/v1/hr/employees/me/documents/5/download');
    expect(mockDownload.mock.calls[1][1]).toMatchObject({ name: 'pan_card.jpg' });
  });
  it('shows empty states and a per-section error', async () => {
    mock.onGet('/tax/form16/my').reply(200, []);
    mock.onGet('/hr/employees/me/documents').reply(404, { detail: 'Employee record not found' });
    await renderWithProviders(<DocumentsScreen />);
    expect(await screen.findByTestId('form16-empty')).toBeTruthy();
    expect(await screen.findByTestId('documents-error')).toHaveTextContent(/Employee record not found/);
  });
});
