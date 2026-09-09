from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/caihaoming/Documents/stock_agent").resolve()
OUTPUT = (ROOT / "evals/results/runtime-replay-and-eval-hardening-final-independent-v2-20260908").resolve()


def git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ).stdout


def excluded(path: Path) -> bool:
    resolved = path.resolve(strict=False)
    return path == ROOT / ".git" or ROOT / ".git" in path.parents or resolved == OUTPUT or OUTPUT in resolved.parents


def filtered_lines(data: bytes) -> bytes:
    marker = b"evals/results/runtime-replay-and-eval-hardening-final-independent-v2-20260908"
    return b"".join(line for line in data.splitlines(keepends=True) if marker not in line)


def capture(label: str) -> None:
    destination = OUTPUT / "source-tree-proof" / label
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "head.txt").write_bytes(git("rev-parse", "HEAD"))
    (destination / "branch.txt").write_bytes(git("branch", "--show-current"))
    status = filtered_lines(git("status", "--porcelain=v1", "--untracked-files=all"))
    (destination / "git-status-porcelain-v1.txt").write_bytes(status)
    (destination / "git-diff-unstaged.patch").write_bytes(git("diff", "--binary", "--no-ext-diff"))
    (destination / "git-diff-staged.patch").write_bytes(git("diff", "--cached", "--binary", "--no-ext-diff"))
    untracked = filtered_lines(git("ls-files", "--others", "--exclude-standard"))
    (destination / "untracked-files.protected.txt").write_bytes(untracked)

    rows: list[str] = []
    for current, dirs, files in os.walk(ROOT, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(d for d in dirs if not excluded(current_path / d))
        for name in sorted(files):
            path = current_path / name
            if excluded(path):
                continue
            rel = path.relative_to(ROOT).as_posix()
            mode = stat.S_IMODE(path.lstat().st_mode)
            if path.is_symlink():
                digest = hashlib.sha256(os.readlink(path).encode("utf-8")).hexdigest()
                kind = "symlink"
            else:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                kind = "file"
            rows.append(f"{rel}\t{kind}\t{oct(mode)}\t{digest}\n")
    manifest = "".join(rows).encode("utf-8")
    (destination / "source-tree-manifest.tsv").write_bytes(manifest)
    (destination / "source-tree.sha256").write_text(hashlib.sha256(manifest).hexdigest() + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"before", "after"}:
        raise SystemExit("usage: _capture_source_proof.py before|after")
    capture(sys.argv[1])
