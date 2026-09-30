# Production Deployment Plan

## Authorization Boundary

This is a design document, not deployment authorization. Do not copy templates into system directories, expose public ports, request certificates, or start services until the user explicitly provides `DEPLOY_CONFIRM`, `确认正式部署`, or `允许配置 systemd / Nginx` and approves the final values listed below.

## Recommended Architecture

- Backend: FastAPI/Uvicorn running as a dedicated unprivileged service user.
- Frontend: artifacts from the Vite build served directly by Nginx.
- Reverse proxy: Nginx routes `/api/` and WebSocket upgrades to the backend.
- Transport security: HTTPS on the public endpoint.
- Runtime persistence: `/home/suicardgame/runtime/data/rooms`, never served by Nginx and kept mode `700`.
- Process supervision: systemd manages only the backend process.

```text
Internet -> 80/443 Nginx -> static frontend/dist
                         -> /api/ and WebSocket -> 127.0.0.1:8012 Uvicorn
```

## Recommended Ports

| Purpose | Address | Exposure |
| --- | --- | --- |
| Backend | `127.0.0.1:8012` | local only |
| Frontend static files | Nginx filesystem root | no Vite dev server |
| Public HTTP | `80` | redirect to HTTPS after certificate setup |
| Public HTTPS | `443` | public only after explicit approval |

The Vite development server on 5173 and Playwright ports 5174/8122 are not production services.

## Service User And Permissions

Create a dedicated `suicardgame` user and group only after approval. The account should have no interactive shell, read access to application code and `/home/miniconda3`, and write access only to the private runtime directories. Keep these directories at mode `700`:

- `/home/suicardgame/runtime`
- `/home/suicardgame/runtime/data/rooms`
- `/home/suicardgame/data/rooms`

Do not make runtime data world-readable to satisfy Nginx or systemd. Nginx needs access only to `/home/suicardgame/frontend/dist`.

## systemd Draft

Template: `deploy_templates/suicardgame.service.template`

- Service name: `suicardgame.service`
- `WorkingDirectory=/home/suicardgame`
- Environment: `SUICARDGAME_DATA_DIR=/home/suicardgame/runtime/data/rooms`
- `ExecStart`: `/home/miniconda3/envs/audio/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8012 --no-access-log`
- User and group: dedicated `suicardgame` account.
- Restart: `on-failure`, with a bounded restart delay.
- Resource limits: memory, CPU quota, task count, and file descriptors sized for the 2 vCPU / 2 GiB host.
- Security: private temporary directory, no new privileges, read-only project tree with explicit runtime write paths, and restrictive umask.

Before installation, run `systemd-analyze verify` against the reviewed unit. Do not run `systemctl enable` or `systemctl start` during preflight.

## Nginx Draft

Template: `deploy_templates/nginx-suicardgame.conf.template`

- Static root: `/home/suicardgame/frontend/dist`.
- `/api/` proxies to `http://127.0.0.1:8012`.
- WebSocket upgrade headers are forwarded.
- Security headers are set on public responses.
- Requests for `.env`, hidden files, `runtime`, `data/rooms`, and `audits` are denied.
- The template contains `REPLACE_WITH_DOMAIN` and certificate placeholders that must be replaced before use.

Run `nginx -t` before any authorized reload. Never expose the project root as the Nginx static root.

## HTTPS Plan

If a real domain resolves to the server and public deployment is approved, obtain a certificate with the distribution-supported certbot workflow or another approved ACME client. Confirm the exact domain, email/contact policy, renewal method, and permission to open ports 80/443 first.

If no domain is available, do not treat a bare-IP public endpoint as a finished HTTPS deployment. Do not expose session or reconnect tokens over unencrypted HTTP.

## Logs

- Backend lifecycle and application diagnostics: `journalctl -u suicardgame.service` after systemd is authorized.
- Nginx access/error logs: use the distribution defaults or explicitly reviewed per-site files.
- Access logs must not retain session or reconnect credentials. The backend template disables Uvicorn access logs.
- Configure log rotation and retention before public traffic.

## Backup And Rollback

The existing handoff archive is not a full source release. It contains documentation, scripts, and audit evidence, so it can restore those materials but cannot restore the complete application.

Before deployment:

1. Create a full source release archive containing backend source, frontend source, lock files, scripts, docs, and deployment templates.
2. Exclude `.env`, runtime data, room JSON, `node_modules`, browser caches, build output, and `.git`.
3. Record and verify its SHA-256 checksum.
4. Build the frontend from that release and run local health and multiplayer checks.
5. Keep the previous full source release and reviewed service configuration available.

Rollback sequence after authorization:

1. Stop public traffic or place the site in maintenance mode.
2. Stop `suicardgame.service` gracefully.
3. Restore the previous full source release without overwriting private runtime data.
4. Rebuild static assets from the restored lock file.
5. Restore the previously reviewed templates, run `systemd-analyze verify` and `nginx -t`, then start the backend on `127.0.0.1:8012`.
6. Verify `/api/v1/health`, WebSocket reconnect, and a local multiplayer flow before restoring public traffic.

Detailed operator steps are in `deploy_templates/rollback_checklist.md`.

## Security Requirements

- Never use `TEST_MODE=1` on a public listener.
- Never expose Playwright reports or browser traces publicly.
- Never expose `runtime/data/rooms` or `data/rooms`.
- Never place `.env` in the frontend static directory.
- Never publish the `audits` directory.
- Never log or archive session tokens, reconnect tokens, room JSON bodies, or player hands.
- Keep the backend bound to localhost behind Nginx.

## Required Confirmations Before Actual Deployment

The user must confirm all of the following:

1. Public access is allowed.
2. Exact domain name.
3. External HTTP/HTTPS ports.
4. Internal backend port, recommended `8012`.
5. Frontend delivery method, recommended Nginx static files.
6. Permission to configure Nginx.
7. Permission to configure systemd.
8. Permission to request and renew an HTTPS certificate with certbot or an approved alternative.
9. Permission to create the dedicated `suicardgame` service user and group.
10. Log rotation and retention requirements.
11. Automatic restart policy.
12. Permission to reload or restart related services.
13. Full source release backup path and verified checksum.
