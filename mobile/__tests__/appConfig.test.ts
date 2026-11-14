import fs from 'fs';
import os from 'os';
import path from 'path';
import { buildConfig, resolveTenantName } from '../app.config';
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

describe('production safety rules', () => {
  it('rejects plain http for non-local hosts unless the tenant is dev', () => {
    const remote = { ...good, apiBaseUrl: 'http://hr.acme.com/api/v1' };
    expect(() => validateTenant(remote, 'acme')).toThrow(/must use https/);
    expect(() => validateTenant(remote, 'dev')).not.toThrow();
    expect(() => validateTenant({ ...good, apiBaseUrl: 'http://10.0.2.2:8005/api/v1' }, 'acme')).not.toThrow();
    expect(() => validateTenant({ ...good, apiBaseUrl: 'https://hr.acme.com/api/v1' }, 'acme')).not.toThrow();
  });
  it('validates version and buildNumber', () => {
    expect(() => validateTenant({ ...good, version: '1.2' })).toThrow(/version/);
    expect(() => validateTenant({ ...good, buildNumber: 0 })).toThrow(/buildNumber/);
    expect(() => validateTenant({ ...good, version: '2.1.0', buildNumber: 7 })).not.toThrow();
  });
  it('requires TENANT for production EAS builds, defaults to dev otherwise', () => {
    expect(resolveTenantName({})).toBe('dev');
    expect(resolveTenantName({ TENANT: 'acme' })).toBe('acme');
    expect(() => resolveTenantName({ EAS_BUILD_PROFILE: 'production' })).toThrow(/TENANT must be set/);
  });
  it('maps version, build numbers and the adaptive icon', () => {
    const c = buildConfig('acme');
    expect(c.version).toBe('1.0.0');
    expect(c.ios?.buildNumber).toBe('1');
    expect(c.android?.versionCode).toBe(1);
    expect(c.android?.adaptiveIcon?.foregroundImage).toBe('./tenants/acme/adaptive-icon.png');
  });
});

describe('cleartext traffic', () => {
  const plugin = (c: ReturnType<typeof buildConfig>) =>
    (c.plugins as unknown[]).find((p) => Array.isArray(p) && p[0] === 'expo-build-properties');
  it('enables Android cleartext only for the http dev tenant', () => {
    expect((plugin(buildConfig('dev')) as [string, { android: Record<string, unknown> }])[1].android.usesCleartextTraffic).toBe(true);
    expect((plugin(buildConfig('acme')) as [string, { android: Record<string, unknown> }])[1].android.usesCleartextTraffic).toBeUndefined();
  });
  it('always ships the R8 keep rules for the WorkManager Room database (release launch crash)', () => {
    for (const t of ['dev', 'acme']) {
      const rules = ((plugin(buildConfig(t)) as [string, { android: { extraProguardRules: string } }])[1]).android.extraProguardRules;
      expect(rules).toContain('-keep class androidx.work.impl.WorkDatabase_Impl { *; }');
      expect(rules).toContain('-keep class * extends androidx.room.RoomDatabase { *; }');
    }
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

describe('shift location tracking config', () => {
  const loc = (c: ReturnType<typeof buildConfig>) => (c.plugins as unknown[]).find((p) => Array.isArray(p) && p[0] === 'expo-location') as [string, Record<string, unknown>];
  it('enables background location on both platforms with permission strings', () => {
    const [, o] = loc(buildConfig('dev'));
    expect(o).toMatchObject({ isAndroidBackgroundLocationEnabled: true, isAndroidForegroundServiceEnabled: true, isIosBackgroundLocationEnabled: true });
    expect(String(o.locationAlwaysAndWhenInUsePermission)).toMatch(/rostered shifts/);
    expect(String(o.locationAlwaysPermission)).toMatch(/agreed/);
  });
  it('wires the Google Maps key from the build env only, and flags map availability', () => {
    const none = buildConfig('dev', undefined, {});
    expect(none.android?.config).toBeUndefined();
    expect((none.extra as { mapsEnabled: boolean }).mapsEnabled).toBe(false);
    const withKey = buildConfig('dev', undefined, { GOOGLE_MAPS_API_KEY: ' AIza-test ' });
    expect(withKey.android?.config?.googleMaps?.apiKey).toBe('AIza-test');
    expect((withKey.extra as { mapsEnabled: boolean }).mapsEnabled).toBe(true);
  });
});

describe('camera permissions (VisionCamera selfie)', () => {
  const c = buildConfig('dev');
  const plugins = c.plugins as unknown[];
  const named = (n: string) => plugins.find((p) => p === n || (Array.isArray(p) && p[0] === n));
  it('declares the iOS camera usage string and Android CAMERA, with no microphone', () => {
    const picker = named('expo-image-picker') as [string, { cameraPermission: string; microphonePermission: unknown }];
    expect(picker[1].cameraPermission).toMatch(/camera for your punch selfie/);
    expect(picker[1].microphonePermission).toBe(false);
    expect(c.android?.permissions).toContain('android.permission.CAMERA');
    expect(c.android?.permissions).not.toContain('android.permission.RECORD_AUDIO');
    expect(JSON.stringify(c.ios?.infoPlist ?? {})).not.toMatch(/NSMicrophoneUsageDescription/);
  });
  it('no longer uses expo-camera', () => {
    expect(named('expo-camera')).toBeUndefined();
    expect(JSON.stringify(c)).not.toContain('expo-camera');
  });
});
