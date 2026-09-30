import { defineConfig, devices } from '@playwright/test';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const e2eDataDir = mkdtempSync(join(tmpdir(), 'suicardgame-step8-e2e-'));
const backendPort = Number(process.env.SUICARDGAME_E2E_BACKEND_PORT ?? 8122);
const frontendPort = Number(process.env.SUICARDGAME_E2E_FRONTEND_PORT ?? 5174);
const backendURL = `http://127.0.0.1:${backendPort}`;
const frontendURL = `http://127.0.0.1:${frontendPort}`;
const pythonBin = process.env.PYTHON_BIN ?? 'python';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: frontendURL,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  testIgnore: ['**/acceptance/production-card-render.spec.ts'],
  webServer: [
    {
      command: `"${pythonBin}" -m uvicorn backend.app.main:app --host 127.0.0.1 --port ${backendPort}`,
      cwd: repoRoot,
      env: { TEST_MODE: '1', SUICARDGAME_DATA_DIR: e2eDataDir },
      url: `${backendURL}/api/v1/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      stdout: 'ignore',
      stderr: 'ignore',
    },
    {
      command: `npm run dev -- --port ${frontendPort}`,
      env: { VITE_BACKEND_TARGET: backendURL },
      url: frontendURL,
      timeout: 120_000,
      reuseExistingServer: false,
      stdout: 'ignore',
      stderr: 'ignore',
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
