import Constants from 'expo-constants';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import type { Tenant } from '../../tenants/validate';

export type RuntimeTenant = Tenant & { id: string };

export function getTenant(): RuntimeTenant {
  const t = Constants.expoConfig?.extra?.tenant as RuntimeTenant | undefined;
  if (!t) throw new Error('Tenant config missing from expo extra (check app.config.ts)');
  return t;
}

/** Android emulators cannot reach the host via localhost; they use 10.0.2.2. */
export function resolveApiBaseUrl(url: string, os: string, isPhysicalDevice: boolean): string {
  if (os !== 'android' || isPhysicalDevice) return url;
  return url.replace(/^(https?:\/\/)(localhost|127\.0\.0\.1)(?=[:/]|$)/, '$110.0.2.2');
}

export function getApiBaseUrl(): string {
  return resolveApiBaseUrl(getTenant().apiBaseUrl, Platform.OS, Device.isDevice);
}
