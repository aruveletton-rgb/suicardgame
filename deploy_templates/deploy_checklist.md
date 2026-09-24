# Deployment Checklist

This checklist is inactive until the user sends `DEPLOY_CONFIRM`, `确认正式部署`, or `允许配置 systemd / Nginx` and approves every concrete value below.

## Required Decisions

- [ ] Confirm public access is allowed.
- [ ] Confirm the exact domain.
- [ ] Confirm external ports and the internal backend port.
- [ ] Confirm the HTTPS certificate and renewal method.
- [ ] Confirm Nginx and systemd are allowed.
- [ ] Confirm creation of a dedicated service user and group.
- [ ] Confirm log rotation and retention.
- [ ] Confirm automatic restart behavior.
- [ ] Confirm permission to reload or restart related services.

## Backup And Build

- [ ] Create a full source release that excludes secrets and runtime data.
- [ ] Verify the release checksum and record the rollback release.
- [ ] Confirm `.env`, room JSON, `node_modules`, browser caches, `dist`, and `.git` are absent from the release archive.
- [ ] Build the frontend from the locked dependencies.
- [ ] Run backend tests, asset validation, smoke, and Playwright before changing traffic.

## Service Preparation

- [ ] Create the dedicated `suicardgame` service user only after approval.
- [ ] Give the service user read access to code and write access only to private runtime directories.
- [ ] Keep runtime room directories mode `700`.
- [ ] Review `suicardgame.service.template` and replace no paths unless explicitly approved.
- [ ] Run `systemd-analyze verify` on the proposed unit before installation.
- [ ] Review `nginx-suicardgame.conf.template` and replace `REPLACE_WITH_DOMAIN`.
- [ ] Confirm the static root is `/home/suicardgame/frontend/dist`, not the project root.
- [ ] Run `nginx -t` before any authorized reload.

## HTTPS And Launch

- [ ] Confirm DNS points to the intended server.
- [ ] Request the HTTPS certificate only after authorization.
- [ ] Confirm renewal and failure alerting.
- [ ] Verify Nginx denies `.env`, runtime, room data, audits, hidden files, and Playwright artifacts.
- [ ] Start the backend on localhost and verify health before enabling public routing.
- [ ] Run public E2E for HTTP, WebSocket, reconnect, and multiplayer behavior.
- [ ] Confirm rollback steps and responsible operator before declaring launch complete.
