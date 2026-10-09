# suicardgame v1.2 on jingxichangunit: 8080

Date: 2026-09-28. Source commit: `0559f48800aa589df32440a7d8e7c270da1cc64d` (`codex/suicardgame-v1.2`).

## Deployment

- Copied a `git archive` of all 229 tracked source files to `/home/twq/suicardgame-v1.2`; excluded local `temp/`, `.git`, dependencies and existing room data. Archive SHA-256: `ebf7be1555b935d3238222d80c65b9fde6aa07ccd7ef832e924bb8774f3772a4` on both ends.
- Built the frontend remotely with `npm ci --no-audit --no-fund` and `npm run build`; output is `frontend/dist`.
- Created an isolated Python 3.11 venv from `requirements.txt`. The host default Python 3.10 cannot import `StrEnum`.
- A small deployment-only `serve_v12_8080.py` mounts the built static frontend after the existing FastAPI routes. It is not in the Git commit.
- One Uvicorn process (PID at verification: `974118`) binds `0.0.0.0:8080` without reload or access logging. Room data stays in `/home/twq/suicardgame-v1.2/runtime/data/rooms`, permission `0700`; test mode is disabled.
- Existing `/home/twq/suicardgame`, `suicardgame.service`, Nginx, and port 8012 were not changed or restarted.

## Verification

| Check | Result |
| --- | --- |
| Remote Python compile | Passed |
| Remote frontend build | Passed |
| On-host `GET /` and `GET /api/v1/health` | HTTP 200; health `{"status":"ok"}` |
| CSS asset | HTTP 200 |
| Two-player live smoke | Create/join, first-frame WebSocket authentication for both players, both ready and start game passed |
| Local SSH tunnel to 8080 | Home, CSS and health returned HTTP 200 |
| Existing service | `suicardgame.service` active, port 8012 health passed |
| Direct public `20.89.102.21:8080` | Timed out; not externally usable |

At final check, process RSS was 56,476 KiB, CPU snapshot 0.1%, host memory available 375 MiB of 898 MiB, one Uvicorn worker. This is a point-in-time observation, not a capacity test. The host has no swap. The Azure instance metadata reports private IP `10.1.1.4` and no public IP on its NIC. No cloud inbound rule or host firewall was changed; the exact external network block was not proven because those rules were not accessible for inspection.

## Access and rollback

Until inbound TCP 8080 is explicitly opened, use an SSH tunnel from the client:

```powershell
ssh -L 18080:127.0.0.1:8080 jingxichangunit
```

Open `http://127.0.0.1:18080/` while the tunnel is connected. This also avoids sending session credentials over plain public HTTP.

The process was launched with `nohup`, so it survives SSH logout but is not configured to restart after host reboot. To stop only this v1.2 instance, verify the recorded PID belongs to `/home/twq/suicardgame-v1.2/.venv/bin/python -m uvicorn serve_v12_8080:app`, then signal that PID. Leave the version directory and its room data intact for recovery. No systemd or Nginx configuration was changed.
