import { defineConfig } from '@playwright/test';

const baseURL = process.env.E2E_BASE_URL || 'http://localhost:5173';
const headed = ['1', 'true', 'yes'].includes((process.env.E2E_HEADED || '').toLowerCase());
const slowMo = Number(process.env.E2E_SLOWMO || 0);

export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    headless: !headed,
    permissions: ['geolocation'],
    geolocation: { latitude: 28.6139, longitude: 77.2090 },
    launchOptions: {
      slowMo: Number.isFinite(slowMo) ? slowMo : 0,
    },
  },
  projects: [
    {
      name: 'Desktop HD',
      use: { viewport: { width: 1280, height: 720 } },
    },
    {
      name: 'Desktop FHD',
      use: { viewport: { width: 1920, height: 1080 } },
    },
    {
      name: 'Laptop',
      use: { viewport: { width: 1366, height: 768 } },
    },
    {
      name: 'MacBook 14',
      use: { viewport: { width: 1512, height: 982 } },
    },
  ],
  retries: process.env.CI ? 1 : 0,
});
