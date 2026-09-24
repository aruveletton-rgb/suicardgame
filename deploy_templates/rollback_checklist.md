# Rollback Checklist

## Required Artifact

The handoff archive is not a full source release and cannot restore the complete application. Before deployment, create a full source release with backend/frontend source, lock files, scripts, docs, and templates while excluding secrets and runtime data.

- [ ] Record the active full source release path and SHA-256 checksum.
- [ ] Record the previous full source release path and checksum.
- [ ] Record the reviewed systemd and Nginx configuration checksums.
- [ ] Confirm the handoff archive remains available for documentation and audit recovery only.

## Rollback Trigger

- [ ] Identify the failed health, WebSocket, reconnect, build, or multiplayer check.
- [ ] Decide whether to stop public traffic immediately.
- [ ] Notify the responsible operator and preserve non-sensitive error evidence.

## Stop And Restore

The following commands are examples for an already authorized deployment; do not execute them during preflight.

- [ ] Stop or drain Nginx public traffic according to the approved maintenance plan.
- [ ] Gracefully stop `suicardgame.service`; do not kill unrelated processes.
- [ ] Restore the previous full source release without replacing `.env`, `runtime`, or room data.
- [ ] Rebuild frontend static files from the restored lock file.
- [ ] Restore the previously reviewed service and Nginx configuration.
- [ ] Run `systemd-analyze verify` and `nginx -t` before restarting anything.

## Validate Before Restoring Traffic

- [ ] Start the backend only on `127.0.0.1:8012`.
- [ ] Verify the `/api/v1/health` response.
- [ ] Verify WebSocket connection and reconnect behavior locally.
- [ ] Run a focused multiplayer flow without exposing test mode publicly.
- [ ] Confirm runtime permissions remain `700`.
- [ ] Confirm no unexpected test port remains listening.
- [ ] Restore public traffic only after all rollback health checks pass.
