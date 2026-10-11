# Project Baseline

Verified on 2026-10-11 in Asia/Shanghai. This baseline records observed facts,
not a deployment instruction or permission to interrupt live games.

## Goal and Workspace

- Product: multiplayer UNO with Sui special cards and a shop, 2-5 human/bot players.
- Active workspace: E:/suicardgame.
- Source: backend/ (FastAPI/Python) and frontend/ (React/TypeScript/Vite).
- Git remote: origin, git@github.com:aruveletton-rgb/suicardgame.git.
- Initial audit base: main/origin/main at 5e3d68e9c69717742ceda9f7bbf94397a6a42170.
- Repair and synchronization branch: codex/audit-fixes-20261011. User authorized GitHub synchronization after the repairs on 2026-10-11.
- Local VERSION: suicardgame-v1.5. Existing uncommitted changes must be preserved.
- Current player-facing rules: docs/PLAYER_MANUAL.md; architecture and traceability were corrected during audit repair.

## Scope and Data

- For verification, write evidence under audit/ and isolated test data under temp/ or an OS temporary directory.
- Always set SUICARDGAME_DATA_DIR for tests; never test against existing data/ or runtime/ room snapshots.
- Preserve credentials, room data, unrelated files/services, and prior audit evidence.
- User approved maintenance deployment and public reverification, followed by local/GitHub synchronization. Record the concrete interruption and verification evidence for each deployment.
- Preserve room data and rollback snapshots. Cache cleanup is limited to the explicit regenerable-cache allowlist in docs/CACHE_MAINTENANCE.md.

## Run and Verify

Run from the repository root:

```powershell
$env:SUICARDGAME_DATA_DIR = Join-Path $env:TEMP 'suicardgame-dev-rooms'
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8012
```

Run the frontend in another shell:

```powershell
$env:VITE_BACKEND_TARGET = 'http://127.0.0.1:8012'
npm --prefix frontend run dev -- --port 5174
```

Existing verification commands:

```powershell
python -m pytest -q backend/tests
python scripts/validate-card-assets.py
npm --prefix frontend run build
npm --prefix frontend run test:e2e -- --config=playwright.config.ts
npm --prefix frontend run test:e2e:production-card
python scripts/bot_simulation.py --games 300
```

- Dependencies: requirements.txt, requirements-dev.txt, frontend/package-lock.json.
- Card validation regenerates frontend/src/data/cardManifest.json; use isolated output for a read-only audit.
- Playwright configs create isolated backend data and TEST_MODE servers; use unique free ports.
- Existing E2E tests include direct HTTP/test-state setup and session access; they are not exclusively UI-driven.
- Simulation now reports primary rejections and fallback outcomes, with stable winner seats for seed-repeat comparisons.

## Remote Environment

- SSH alias: suicardgame-server; deployed files: /home/suicardgame (no Git metadata).
- Public entry points: http://139.196.13.53/ and http://139.196.13.53:8000/.
- Nginx serves frontend/dist and proxies /api/ and WebSocket to 127.0.0.1:8012.
- Active service: suicardgame.service; Python: /home/miniconda3/envs/audio/bin/python; owner: twq.
- Live data directory: /home/suicardgame/data/rooms. The old runtime/data/rooms directory is preserved and is not the service's active store.
- Health endpoint: GET /api/v1/health. Older API-memory paths are obsolete.
- HTTP/IP deployment is the established project choice. No TLS or DuckDNS setup was changed.
- Latest gameplay release: /home/twq/suicardgame-releases/chongyue-flow-20261011. Source hashes were checked before promotion; public JS/CSS/index matched the release manifest on ports 80 and 8000.
- Latest service verification: active/running, PID 121184, NRestarts=0. All four original room snapshots and both ACTIVE games were preserved with unchanged game IDs and hands at the immediate post-restart check.
- Public Chongyue verification used three new rooms with normal seeded START_GAME (no test-state injection): successful challenge and early stop, qualified-source penalty and continuation, and an actual Reverse followed by directional displays. All three passed, including 24 one-card draw clicks and desktop/mobile layouts; QA rooms were closed afterward.
- Cache timer: enabled/active, Mondays 03:30 Asia/Shanghai. First run deleted 20 eligible cache files (5908380 bytes), errors=0; next scheduled run 2026-10-12 03:30 CST.
- Normalize CRLF to LF before comparing text source hashes across Windows/Linux.

## Deliverables and Acceptance

- Timestamped Markdown and JSON audit reports, matching conclusions and evidence, plus latest pointers.
- Check backend rules/lifecycle/auth/privacy/bots, build, card assets, desktop/mobile browser flows,
  public availability, deployed-source consistency, and process supervision.
- Record each failed or unverified check explicitly. Passing existing tests is not proof of all rule combinations.
- Initial audit: audit/20261011_171307_verification/. It found a two-player self-turn deadline bug,
  an outdated production test expectation, mixed deployment, and missing service supervision.
- Repair evidence and deployment candidates: audit/20261011_173927_fixes/.
- Initial observations of a mixed v1.2 frontend/manual backend process were corrected by the audit release; retained historical reports describe that earlier state.
- Shop UI evidence: audit/20261011_shop_ui/.
- Latest rules, bot-delay, cache, deployment, and public verification evidence: audit/20261011_manual_draw/.
- Chongyue repairs and latest deployment evidence: audit/20261011_chongyue_fixes/. Verification: 373 backend tests passed, one Windows symlink skip; 12 impacted Chromium cases passed; 300 bot games finished without stalls or rejected commands. Required reveal/draw steps use 180 seconds and pause on timeout; optional challenge steps use 10 seconds. Legacy phase-less Chongyue prompts keep their original resolution protocol.
- Gameplay rollback must settle ACTIVE action stacks and new Chongyue phases before loading the old engine; historical room snapshots must not overwrite current room data. Cache maintenance is independent and remains installed. The stopped-writer room archive is private on the server; source rollback and failure-path evidence are recorded in the Chongyue release directory.
