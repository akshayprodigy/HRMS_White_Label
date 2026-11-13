import fs from 'fs';
import path from 'path';
import type { ExpoConfig } from 'expo/config';
import { validateTenant } from './tenants/validate';

export function buildConfig(tenantName: string, root: string = __dirname): ExpoConfig {
  const dir = path.join(root, 'tenants', tenantName);
  const file = path.join(dir, 'tenant.json');
  if (!fs.existsSync(file)) {
    const tdir = path.join(root, 'tenants');
    const available = fs.existsSync(tdir)
      ? fs.readdirSync(tdir, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name)
      : [];
    throw new Error(`Unknown tenant "${tenantName}": ${file} not found. Available: ${available.join(', ') || 'none'}`);
  }
  const tenant = validateTenant(JSON.parse(fs.readFileSync(file, 'utf8')), tenantName);
  const icon = `./tenants/${tenantName}/icon.png`;
  const splash = `./tenants/${tenantName}/splash.png`;
  const adaptive = `./tenants/${tenantName}/adaptive-icon.png`;
  for (const asset of [icon, splash, adaptive]) {
    if (!fs.existsSync(path.join(root, asset))) throw new Error(`Tenant "${tenantName}" is missing ${asset}`);
  }

  // Plain-http API (dev/localhost only; validateTenant forbids it elsewhere) needs Android cleartext traffic.
  const cleartext = /^http:\/\//i.test(tenant.apiBaseUrl);

  return {
    name: tenant.name,
    slug: tenant.slug,
    scheme: tenant.scheme,
    version: tenant.version ?? '1.0.0',
    orientation: 'portrait',
    icon,
    userInterfaceStyle: 'automatic',
    ios: { bundleIdentifier: tenant.ios.bundleIdentifier, supportsTablet: false, buildNumber: String(tenant.buildNumber ?? 1) },
    android: {
      package: tenant.android.package,
      versionCode: tenant.buildNumber ?? 1,
      adaptiveIcon: { foregroundImage: adaptive, backgroundColor: tenant.colors.primary },
    },
    plugins: [
      'expo-router',
      'expo-secure-store',
      ['expo-location', { locationWhenInUsePermission: 'Allow $(PRODUCT_NAME) to use your location to verify where you punch in and out.' }],
      ['expo-camera', { cameraPermission: 'Allow $(PRODUCT_NAME) to use the camera for your punch selfie.', microphonePermission: false, recordAudioAndroid: false }],
      ...(cleartext ? [['expo-build-properties', { android: { usesCleartextTraffic: true } }] as [string, object]] : []),
      ['expo-splash-screen', { image: splash, imageWidth: 160, backgroundColor: tenant.colors.primary }],
    ],
    experiments: { typedRoutes: true },
    extra: { tenant: { ...tenant, id: tenantName } },
  };
}

/** Release builds must name their tenant explicitly; silently defaulting to dev would ship the wrong app. */
export function resolveTenantName(env: Record<string, string | undefined>): string {
  if (env.TENANT) return env.TENANT;
  if (env.EAS_BUILD_PROFILE === 'production') throw new Error('TENANT must be set for production builds (e.g. TENANT=acme eas build --local --profile production)');
  return 'dev';
}

export default (): ExpoConfig => buildConfig(resolveTenantName(process.env));
