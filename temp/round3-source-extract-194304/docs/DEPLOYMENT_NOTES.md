# Deployment Notes

## Current Deployment State

The project has completed local and server-internal regression validation. It is not currently exposed as a public production service.

- Public ingress is not enabled.
- Nginx is not configured.
- systemd is not configured.
- Redis, PostgreSQL, Kafka, and other new infrastructure are not installed for this project.
- The supported handoff scripts bind backend and development frontend services to `127.0.0.1` by default.

Use the current commands only for local or server-internal operation:

```bash
cd /home/suicardgame
./scripts/start_backend.sh
./scripts/start_frontend_dev.sh
```

The frontend development server is not a production deployment mechanism.

## Required Steps Before Public Launch

Public launch requires a separate, explicitly authorized change. Recommended order:

1. Back up the project, audit reports, and any required private runtime state.
2. Create a dedicated least-privilege service user rather than relying on an interactive account.
3. Confirm internal backend and frontend ports and ensure they remain bound to localhost.
4. Configure a reverse proxy with correct WebSocket upgrade headers.
5. Configure HTTPS certificates and secure HTTP headers.
6. Define and review a systemd unit, restart policy, and environment loading strategy.
7. Configure log rotation without logging session or reconnect credentials.
8. Add CPU, memory, process, and file-descriptor limits appropriate for the 2 vCPU / 2 GiB server.
9. Recheck ownership and permissions for `.env`, `runtime`, `runtime/data/rooms`, and `data/rooms`.
10. Run public-path API, WebSocket, reconnect, and multiplayer E2E only after the security review is approved.

This document describes a future plan only. It does not authorize or activate Nginx, systemd, public firewall rules, or public listeners.

## Sensitive Data Policy

- Never print or archive `.env`, session tokens, reconnect tokens, or room JSON bodies.
- Keep `/home/suicardgame/runtime`, `/home/suicardgame/runtime/data/rooms`, and `/home/suicardgame/data/rooms` at mode `700`.
- Do not make runtime room data world-readable.
- Keep backend access logs disabled unless a reviewed redaction policy is in place.
- Store production secrets outside source control and outside distributable archives.

## Test Mode

The deterministic `TEST_MODE=1` path exists only for automated E2E fixtures. Do not expose test mode on a public or production listener.

## Rollback Preparation

Before a future deployment, record the exact release archive checksum, database or runtime migration assumptions, service configuration, and rollback commands. Validate rollback on a non-public port before changing public traffic.
