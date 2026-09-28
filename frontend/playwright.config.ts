import { defineConfig, devices } from '@playwright/test';

const e2eDataDir = process.env.STEP7F_E2E_DATA_DIR ?? `/tmp/suicardgame-step8-${process.pid}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: 'http://127.0.0.1:5174',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  webServer: [
    {
      command:
        `bash -lc 'umask 077; rm -rf "${e2eDataDir}"; mkdir -p "${e2eDataDir}"; source /home/miniconda3/etc/profile.d/conda.sh; conda activate audio; cd /home/suicardgame; TEST_MODE=1 SUICARDGAME_DATA_DIR="${e2eDataDir}" python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8122'`,
      url: 'http://127.0.0.1:8122/api/v1/health',
      timeout: 120_000,
      reuseExistingServer: false,
      stdout: 'ignore',
      stderr: 'ignore',
    },
    {
      command: 'VITE_BACKEND_TARGET=http://127.0.0.1:8122 npm run dev -- --port 5174',
      url: 'http://127.0.0.1:5174',
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
