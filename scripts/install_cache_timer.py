"""Preview or install the cache-only systemd timer for a deployed tree."""

import argparse
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path


SERVICE = "suicardgame-cache-cleanup.service"
TIMER = "suicardgame-cache-cleanup.timer"
UNIT_DIR = Path("/etc/systemd/system")


def run(*args):
    subprocess.run(args, check=True)


def roots_for(project):
    if not project.is_absolute() or not project.is_dir() or project.resolve() != project:
        raise ValueError("project root must be an existing, absolute, non-symlink path")
    script = project / "scripts" / "cleanup_cache.py"
    if not script.is_file() or script.is_symlink():
        raise ValueError(f"missing regular cleanup script: {script}")
    spec = importlib.util.spec_from_file_location("cleanup_cache", script)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    roots = sorted({path for path, _ in module.cache_roots(project)})
    for path in roots:
        if (not path.is_absolute() or path.resolve() != path
                or not path.is_relative_to(project)
                or any(character.isspace() or ord(character) < 32 for character in str(path))):
            raise ValueError(f"unsafe cache path: {path}")
    return roots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("/home/suicardgame"))
    parser.add_argument("--unit-source", type=Path, default=None,
                        help="directory containing the shipped service and timer")
    parser.add_argument("--apply", action="store_true", help="install and enable the timer")
    args = parser.parse_args()
    project = args.project_root
    source = args.unit_source or project / "scripts" / "systemd"
    roots = roots_for(project)
    if not roots:
        raise ValueError("no cache roots discovered; refusing an empty write allowlist")
    for name in (SERVICE, TIMER):
        if not (source / name).is_file():
            raise ValueError(f"missing unit source: {source / name}")
    calendar = [line.partition("=")[2].strip() for line in (source / TIMER).read_text().splitlines()
                if line.startswith("OnCalendar=")]
    if len(calendar) != 1:
        raise ValueError("timer must contain exactly one OnCalendar directive")
    dropin = "[Service]\n" + "".join(f"ReadWritePaths={path}\n" for path in roots)
    print(f"mode: {'apply' if args.apply else 'preview'}")
    print(f"project: {project}")
    print(f"unit source: {source}")
    print(f"cache roots ({len(roots)}):")
    for path in roots:
        print(f"  {path}")
    print(f"drop-in: {UNIT_DIR / (SERVICE + '.d') / 'cache-paths.conf'}")
    run("systemd-analyze", "calendar", calendar[0])
    if not args.apply:
        return
    if project != Path("/home/suicardgame"):
        raise ValueError("shipped service uses /home/suicardgame; refusing a different apply root")
    if not shutil.which("systemctl"):
        raise ValueError("systemctl is required")
    for name in (SERVICE, TIMER):
        shutil.copy2(source / name, UNIT_DIR / name)
    dropin_path = UNIT_DIR / (SERVICE + ".d") / "cache-paths.conf"
    dropin_path.parent.mkdir(parents=True, exist_ok=True)
    dropin_path.write_text(dropin)
    run("systemd-analyze", "verify", str(UNIT_DIR / SERVICE), str(UNIT_DIR / TIMER))
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", TIMER)
    run("systemctl", "is-enabled", TIMER)
    run("systemctl", "is-active", TIMER)


if __name__ == "__main__":
    main()
