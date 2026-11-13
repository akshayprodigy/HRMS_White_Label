import * as SecureStore from 'expo-secure-store';

export type Tokens = { accessToken: string; refreshToken: string };

const ACCESS = 'hrms.access_token';
const REFRESH = 'hrms.refresh_token';
const ME = 'hrms.me'; // last verified user profile (cached for offline restore)

export const tokenStorage = {
  async load(): Promise<Tokens | null> {
    const [accessToken, refreshToken] = await Promise.all([
      SecureStore.getItemAsync(ACCESS),
      SecureStore.getItemAsync(REFRESH),
    ]);
    return accessToken && refreshToken ? { accessToken, refreshToken } : null;
  },
  async save(t: Tokens): Promise<void> {
    await Promise.all([SecureStore.setItemAsync(ACCESS, t.accessToken), SecureStore.setItemAsync(REFRESH, t.refreshToken)]);
  },
  async clear(): Promise<void> {
    await Promise.all([
      SecureStore.deleteItemAsync(ACCESS),
      SecureStore.deleteItemAsync(REFRESH),
      SecureStore.deleteItemAsync(ME),
    ]);
  },
  async saveMe(me: unknown): Promise<void> {
    await SecureStore.setItemAsync(ME, JSON.stringify(me));
  },
  async loadMe<T>(): Promise<T | null> {
    try {
      const raw = await SecureStore.getItemAsync(ME);
      return raw ? (JSON.parse(raw) as T) : null;
    } catch {
      return null;
    }
  },
};
