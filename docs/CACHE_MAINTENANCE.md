# Server Cache Maintenance

The `suicardgame-cache-cleanup.timer` schedules cleanup each Monday at
03:30 Asia/Shanghai. `Persistent=true` runs a missed cleanup after startup.
The separate oneshot service runs as `twq`; it does not restart the game.

`scripts/cleanup_cache.py` defaults to a JSON-only dry run. `--apply` removes
regular files at least 30 days old from these cache locations:

- `.pyc` and `.pyo` files in `backend/**/__pycache__` and `scripts/**/__pycache__`.
- `nodeids`, `lastfailed`, and `stepwise` in `.pytest_cache/v/cache`.
- Files in `frontend/.vite` and `frontend/node_modules/.vite`.

Symbolic links and lock files are skipped. Cache directories are retained.
Active project Vite, pytest, mypy, or Ruff processes defer cleanup. Room
snapshots, source files, dependency packages, current and previous frontend
bundles, release archives, rollback backups, and audit evidence are excluded.

```bash
/home/miniconda3/envs/audio/bin/python -B /home/suicardgame/scripts/cleanup_cache.py
systemctl list-timers suicardgame-cache-cleanup.timer
systemctl show suicardgame-cache-cleanup.service -p Result -p ExecMainStatus
journalctl -u suicardgame-cache-cleanup.service --no-pager -n 10
```

Installation uses the deployed `scripts/install_cache_timer.py`.
Preview first; the apply step installs the service, timer, and a drop-in
containing only the cache directories discovered in the deployed tree:

```bash
/home/miniconda3/envs/audio/bin/python -B /home/suicardgame/scripts/install_cache_timer.py
sudo /home/miniconda3/envs/audio/bin/python -B /home/suicardgame/scripts/install_cache_timer.py --apply
```

Run the installer again after deployments that change cache directories.
The cleanup unit deliberately cannot write newly discovered cache directories
until its explicit write allowlist is refreshed; deletion errors return a
nonzero exit status and remain visible in the service journal.

Disable scheduling with
`sudo systemctl disable --now suicardgame-cache-cleanup.timer`.
This does not delete data or stop the game.
Gameplay rollback retains this independent cleanup mechanism and never
restores historical room snapshots. Active action stacks must be settled
before rolling gameplay code back to a version that does not support them.
