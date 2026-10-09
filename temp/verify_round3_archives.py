import hashlib
import pathlib
import tarfile
import zipfile

root = pathlib.Path(r"E:\suicardgame")
audit = root / "artifacts/SUICARDGAME_AUDIT_EVIDENCE_20260929_ROUND3.zip"
source = root / "artifacts/SUICARDGAME_SOURCE_a7f7ac1.zip"
modes = root / "artifacts/SUICARDGAME_SOURCE_a7f7ac1_modes.tar.gz"
list_path = root / "temp/round3-evidence-list.txt"
listed = [p.strip().replace("\\", "/") for p in list_path.read_text(encoding="utf-8").splitlines() if p.strip()]

with zipfile.ZipFile(audit) as z:
    assert z.testzip() is None
    names = z.namelist()
    assert len(names) == 53, len(names)
    assert len(names) == len(set(names)), "duplicate names"
    assert all("\\" not in n for n in names)
    assert "round3-evidence-list.txt" in names
    for rel in listed:
        assert rel in names, rel
        assert z.read(rel) == (root / rel).read_bytes(), rel
    print("audit_members", len(names))
    print("audit_crc", "ok")
    print("audit_backslash_members", sum("\\" in n for n in names))
    print("audit_list_byte_matches", len(listed))
    print("audit_sha256", hashlib.sha256(audit.read_bytes()).hexdigest())

with zipfile.ZipFile(source) as z:
    assert z.testzip() is None
    source_names = z.namelist()
    assert all("\\" not in n for n in source_names)
    forbidden = [
        n for n in source_names
        if any(part in {"node_modules", "dist", "test-results", "__pycache__"}
               for part in pathlib.PurePosixPath(n).parts)
    ]
    shell = [n for n in source_names if n.startswith("scripts/") and n.endswith(".sh")]
    mode_missing = []
    for n in shell:
        mode = (z.getinfo(n).external_attr >> 16) & 0o777
        if mode != 0o755:
            mode_missing.append((n, oct(mode)))
    assert not forbidden, forbidden[:5]
    print("source_members", len(source_names))
    print("source_backslash_members", 0)
    print("source_forbidden_generated_members", len(forbidden))
    print("source_shell_members", len(shell))
    print("source_shell_mode_missing", len(mode_missing))
    print("source_sha256", hashlib.sha256(source.read_bytes()).hexdigest())

with tarfile.open(modes, "r:gz") as t:
    tar_names = t.getnames()
    assert all("\\" not in n for n in tar_names)
    shell_modes = [
        (m.name, oct(m.mode & 0o777))
        for m in t.getmembers()
        if m.name.lstrip("./").startswith("scripts/") and m.name.endswith(".sh")
    ]
    assert shell_modes and all(mode == "0o755" for _, mode in shell_modes), shell_modes
    print("mode_tar_members", len(tar_names))
    print("mode_tar_shell_members", len(shell_modes))
    print("mode_tar_shell_mode_missing", sum(mode != "0o755" for _, mode in shell_modes))
    print("mode_tar_sha256", hashlib.sha256(modes.read_bytes()).hexdigest())
