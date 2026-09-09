from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path("/Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-independent-v2-20260908/source-tree-proof")
names = [
    "head.txt",
    "branch.txt",
    "git-status-porcelain-v1.txt",
    "git-diff-unstaged.patch",
    "git-diff-staged.patch",
    "untracked-files.protected.txt",
    "source-tree-manifest.tsv",
    "source-tree.sha256",
]
rows = []
all_equal = True
for name in names:
    before = (ROOT / "before" / name).read_bytes()
    after = (ROOT / "after" / name).read_bytes()
    equal = before == after
    all_equal = all_equal and equal
    rows.append(f"{name}_byte_equal={str(equal).lower()}")
manifest = (ROOT / "after/source-tree-manifest.tsv").read_bytes()
rows.extend([
    f"before_tree_hash={(ROOT / 'before/source-tree.sha256').read_text().strip()}",
    f"after_tree_hash={(ROOT / 'after/source-tree.sha256').read_text().strip()}",
    f"before_manifest_entries={len((ROOT / 'before/source-tree-manifest.tsv').read_text().splitlines())}",
    f"after_manifest_entries={len(manifest.splitlines())}",
    f"all_protected_source_bytes_equal={str(all_equal).lower()}",
])
(ROOT / "comparison.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
print("\n".join(rows))
raise SystemExit(0 if all_equal else 1)
