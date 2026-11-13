import fs from 'fs';
import os from 'os';
import path from 'path';
import { buildConfig } from '../app.config';
import { validateTenant } from '../tenants/validate';
import { resolveApiBaseUrl } from '../src/config/tenant';

const good = JSON.parse(fs.readFileSync(path.join(__dirname, '../tenants/dev/tenant.json'), 'utf8'));

describe('validateTenant', () => {
  it('accepts the dev and acme tenants', () => {
    expect(validateTenant(good).slug).toBe('hrms-dev');
    const acme = JSON.parse(fs.readFileSync(path.join(__dirname, '../tenants/acme/tenant.json'), 'utf8'));
    expect(validateTenant(acme).ios.bundleIdentifier).toBe('com.acme.hr');
  });
  it('lists every problem at once', () => {
    const bad = { ...good, name: '', ios: {}, colors: { ...good.colors, primary: 'blue' }, apiBaseUrl: 'ftp://x' };
    expect(() => validateTenant(bad, 'bad')).toThrow(/Invalid tenant "bad"[\s\S]*name[\s\S]*ios\.bundleIdentifier[\s\S]*apiBaseUrl[\s\S]*colors\.primary/);
  });
  it('rejects non-boolean feature flags and missing features', () => {
    expect(() => validateTenant({ ...good, features: { x: 'yes' } })).toThrow(/features\.x/);
    const { features: _f, ...noFeatures } = good;
    expect(() => validateTenant(noFeatures)).toThrow(/features is required/);
  });
});

describe('buildConfig', () => {
  it('maps the dev tenant to expo config', () => {
    const c = buildConfig('dev');
    expect(c.name).toBe('HRMS Dev');
    expect(c.scheme).toBe('hrmsdev');
    expect(c.ios?.bundleIdentifier).toBe('com.innocore.hrms.dev');
    expect(c.android?.package).toBe('com.innocore.hrms.dev');
    expect(c.icon).toBe('./tenants/dev/icon.png');
    expect((c.extra as { tenant: { id: string; apiBaseUrl: string } }).tenant).toMatchObject({ id: 'dev', apiBaseUrl: 'http://localhost:8005/api/v1' });
  });
  it('fails fast for an unknown tenant, naming the available ones', () => {
    expect(() => buildConfig('nope')).toThrow(/Unknown tenant "nope"[\s\S]*Available: .*dev/);
  });
  it('fails fast when assets are missing or the tenant is invalid', () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'tenantroot-'));
    fs.mkdirSync(path.join(root, 'tenants/t1'), { recursive: true });
    fs.writeFileSync(path.join(root, 'tenants/t1/tenant.json'), JSON.stringify(good));
    expect(() => buildConfig('t1', root)).toThrow(/missing \.\/tenants\/t1\/icon\.png/);
    fs.writeFileSync(path.join(root, 'tenants/t1/tenant.json'), JSON.stringify({ ...good, slug: '' }));
    expect(() => buildConfig('t1', root)).toThrow(/slug is required/);
  });
});

describe('resolveApiBaseUrl', () => {
  it('uses 10.0.2.2 for localhost on Android emulators only', () => {
    expect(resolveApiBaseUrl('http://localhost:8005/api/v1', 'android', false)).toBe('http://10.0.2.2:8005/api/v1');
    expect(resolveApiBaseUrl('http://127.0.0.1:8005/x', 'android', false)).toBe('http://10.0.2.2:8005/x');
    expect(resolveApiBaseUrl('http://localhost:8005/api/v1', 'ios', false)).toBe('http://localhost:8005/api/v1');
    expect(resolveApiBaseUrl('http://localhost:8005/api/v1', 'android', true)).toBe('http://localhost:8005/api/v1');
    expect(resolveApiBaseUrl('https://hr.acme.com/api/v1', 'android', false)).toBe('https://hr.acme.com/api/v1');
  });
});
