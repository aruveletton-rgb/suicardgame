# SERVER_REBUILD_AUDIT

- Time: Thu Jun 25 08:24:42 PM CST 2026
- User: twq
- Hostname: iZuf66sk4zqzeu5i9k6wzdZ
- Target project: /home/suicardgame
- Target Miniconda: /home/miniconda3
- Conda env: audio
- Migration tar: /tmp/suicardgame_migration_source.tar.gz
- Cleanup order: create non-sensitive migration tar first, then delete old /home/twq/miniconda* and /home/twq/suicardgame contents before rebuilding
- Password policy: user enters SSH password once in their own real PowerShell session; password is not stored, printed, scripted, or logged.


## Initial server state
- Uptime: 20:24:42 up 62 days,  2:37,  0 users,  load average: 0.03, 0.14, 0.09
- Disk checked: / and /home
- Existing listen check: inspected 8011/8012 without modifying processes
- Directory candidates checked without modification
- Resource check 1/10: passed, load1=0.03, mem_available_kb=1076428
- Migration source: existing validated tar because old source root is already empty
- Migration tar: reused and validated at /tmp/suicardgame_migration_source.tar.gz
- Resource check 1/10: passed, load1=0.03, mem_available_kb=1077016
- Old project cleanup before rebuild: deleted all contents under /home/twq/suicardgame
- Resource check 1/10: passed, load1=0.19, mem_available_kb=1073760
- Old Miniconda cleanup before rebuild: not found /home/twq/miniconda
- Old Miniconda cleanup before rebuild: not found /home/twq/miniconda3
- Reused existing valid /home/miniconda3
- Wrote /etc/profile.d/home-miniconda.sh for global conda initialization
- Conda env audio: reused existing env

## Environment
- Conda root: /home/miniconda3
- Conda env: audio
- Conda: /home/miniconda3/condabin/conda ; conda 26.3.2
- Python: /home/miniconda3/envs/audio/bin/python ; Python 3.11.15
- Pip: /home/miniconda3/envs/audio/bin/pip ; pip 26.1.2 from /home/miniconda3/envs/audio/lib/python3.11/site-packages/pip (python 3.11)
- Node: /usr/bin/node ; v20.20.2
- NPM: /usr/bin/npm ; 10.8.2
- /home/suicardgame already exists
- Project reconstructed from migration tar into /home/suicardgame
- Resource check 1/10: passed, load1=0.26, mem_available_kb=1084008
- Python dependencies: installed from requirements.txt
- Resource check 1/10: passed, load1=0.23, mem_available_kb=1071564
- Test dependencies: installed from requirements-dev.txt
- Resource check 1/10: passed, load1=0.00, mem_available_kb=1101604
- Frontend dependencies: installed in frontend/
- Resource check 1/10: passed, load1=0.16, mem_available_kb=1089376

## Validation
- pytest: ......................                                                   [100%] 22 passed in 2.16s 
- Resource check 1/10: passed, load1=0.31, mem_available_kb=1075692
- asset validation: validated 68 assets 
- Resource check 1/10: passed, load1=0.29, mem_available_kb=1082704
- frontend build:  vite v8.0.16 building client environment for production... [2Ktransforming...✓ 1744 modules transformed. rendering chunks... computing gzip size... dist/index.html                   0.39 kB │ gzip:  0.28 kB dist/assets/index-B82Hcdqs.css    4.74 kB │ gzip:  1.52 kB dist/assets/index-D0YPBK_L.js   219.22 kB │ gzip: 70.61 kB  ✓ built in 766ms 
- Resource check 1/10: passed, load1=0.66, mem_available_kb=1065184
- smoke check: {"status":"ok"}

## Permissions
- /home/suicardgame: 755
- Code/docs/static files: world-readable where non-sensitive
- /home/miniconda3: world-readable and world-executable where applicable
- runtime and data/rooms: 700 if present
- .env: 600 if present

## Explicitly not done
- Did not open public network access.
- Did not configure Nginx.
- Did not configure systemd.
- Did not kill other users' processes.
- Did not print or package runtime room data.
- Did not print reconnect_token/session token/.env content.
- Did not install Redis/PostgreSQL/Kafka or other new infrastructure.
- Did not store SSH password.

## Next recommended steps
1. Complete command guard: action_id, game_id, game_epoch, expected_state_version.
2. Complete UNO declaration/catch and Wild Draw Four challenge.
3. Implement unified prompt/effect queue.
4. Implement special cards one by one with tests first.
5. Add Playwright E2E.
6. Before production exposure, separately authorize Nginx/systemd/log rotation/rollback plan.

## Result
Server rebuild completed. Old /home/twq/suicardgame contents and old /home/twq Miniconda were deleted before reconstruction after non-sensitive migration tar validation.
