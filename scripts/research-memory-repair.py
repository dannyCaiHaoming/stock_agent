#!/usr/bin/env python3
"""只读预检或显式修复 Research View 的悬空事实引用。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from product.runtime.research_memory_repair import (
    apply_view_reference_repairs,
    inspect_view_references,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Research View 引用预检与离线修复")
    value.add_argument("--memory-root", type=Path, required=True)
    value.add_argument("--security-id", required=True)
    value.add_argument("--apply", action="store_true", help="显式执行；默认仅只读预检")
    value.add_argument("--backup-root", type=Path, help="执行前创建的恢复副本目录；--apply 时必填且必须不存在")
    value.add_argument("--verbose", action="store_true", help="输出逐条 hash 映射；默认只显示计数")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.apply:
        if args.backup_root is None:
            raise SystemExit("--apply requires --backup-root")
        result = apply_view_reference_repairs(
            args.memory_root, security_id=args.security_id, backup_root=args.backup_root,
        )
    else:
        result = inspect_view_references(args.memory_root, security_id=args.security_id)
    if not args.verbose:
        result = dict(result)
        result["views"] = [{
            key: value for key, value in item.items()
            if key not in {"mapping", "ambiguous", "unresolved", "new_view"}
        } for item in result["views"]]
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
