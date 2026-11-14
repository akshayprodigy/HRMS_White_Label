import fs from 'fs';
import path from 'path';
import type { ExpoConfig } from 'expo/config';
import { validateTenant } from './tenants/validate';

/**
 * R8 (minified release) strips WorkManager's generated Room database, which crashes the app at launch
 * (androidx.startup InitializationProvider -> WorkDatabase). WorkManager comes in via expo-task-manager / expo-location.
 * vision-camera, face-detector and nitro-* annotate their JNI classes with @DoNotStrip and ML Kit ships consumer rules,
 * so they need nothing here.
 */
export const ANDROID_PROGUARD_RULES = [
  '-keep class androidx.work.impl.WorkDatabase_Impl { *; }',
  '-keep class * extends androidx.room.RoomDatabase { *; }',
].join('\n');

export function buildConfig(tenantName: string, root: string = __dirname, env: Record<string, string | undefined> = process.env): ExpoConfig {
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

  // Android's Google Maps SDK needs a key at build time (never committed: set GOOGLE_MAPS_API_KEY in the build env / EAS
  // secret). Without one the Field team screen is list-only; iOS uses Apple Maps and needs nothing.
  const mapsKey = env.GOOGLE_MAPS_API_KEY?.trim() || undefined;

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
      permissions: ['android.permission.CAMERA'],
      adaptiveIcon: { foregroundImage: adaptive, backgroundColor: tenant.colors.primary },
      ...(mapsKey ? { config: { googleMaps: { apiKey: mapsKey } } } : {}),
    },
    plugins: [
      'expo-router',
      'expo-secure-store',
      // Accent colour for the Android notification small icon; the tenant's own white-on-transparent icon is not generated yet.
      ['expo-notifications', { color: tenant.colors.primary }],
      [
        'expo-location',
        {
          locationWhenInUsePermission: 'Allow $(PRODUCT_NAME) to use your location to verify where you punch in and out, and to share it during your rostered shift if you agree.',
          locationAlwaysAndWhenInUsePermission: 'Allow $(PRODUCT_NAME) to share your location during your rostered shifts, even when the app is closed, only if you have agreed to shift location sharing.',
          locationAlwaysPermission: 'Allow $(PRODUCT_NAME) to share your location during your rostered shifts, even when the app is closed, only if you have agreed to shift location sharing.',
          isAndroidBackgroundLocationEnabled: true,
          isAndroidForegroundServiceEnabled: true,
          isIosBackgroundLocationEnabled: true, // adds UIBackgroundModes: location
        },
      ],
      // react-native-vision-camera (+ face detector) and react-native-nitro-* ship no Expo config plugin: they autolink, and the
      // camera permission is declared here (Android CAMERA below, iOS NSCameraUsageDescription via this plugin's cameraPermission).
      ['expo-image-picker', { cameraPermission: 'Allow $(PRODUCT_NAME) to use the camera for your punch selfie and to photograph leave proof such as a medical certificate.', microphonePermission: false, photosPermission: false }],
      ['expo-build-properties', { android: { ...(cleartext ? { usesCleartextTraffic: true } : {}), extraProguardRules: ANDROID_PROGUARD_RULES } }],
      ['expo-splash-screen', { image: splash, imageWidth: 160, backgroundColor: tenant.colors.primary }],
    ],
    experiments: { typedRoutes: true },
    extra: { tenant: { ...tenant, id: tenantName }, mapsEnabled: !!mapsKey },
  };
}

/** Release builds must name their tenant explicitly; silently defaulting to dev would ship the wrong app. */
export function resolveTenantName(env: Record<string, string | undefined>): string {
  if (env.TENANT) return env.TENANT;
  if (env.EAS_BUILD_PROFILE === 'production') throw new Error('TENANT must be set for production builds (e.g. TENANT=acme eas build --local --profile production)');
  return 'dev';
}

export default (): ExpoConfig => buildConfig(resolveTenantName(process.env), __dirname, process.env);
