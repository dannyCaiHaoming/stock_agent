"""Explicit local commands for the Tiger read-only broker integration."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Sequence

from .adapter import TigerReadOnlyAdapter
from .analysis import analyze_history
from .config import preflight_config
from .ledger import PrivateBrokerLedger
from .normalization import build_account_snapshot, persist_snapshot
from .sync import sync_history


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
HOST_LAUNCH_MARKER = "STOCK_AGENT_TIGER_HOST_LAUNCH"


class TigerCliError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Tiger HK 严格只读账户数据接入")
    commands = value.add_subparsers(dest="command", required=True)

    preflight = commands.add_parser("preflight", help="仅检查仓库外配置状态，不连接账户或输出金融数据")
    preflight.add_argument("--config-dir", type=Path, required=True)

    snapshot = commands.add_parser("snapshot", help="经宿主 launcher 读取并保存一次当前账户快照")
    snapshot.add_argument("--config-dir", type=Path, required=True)
    snapshot.add_argument("--ledger-root", type=Path, required=True)

    sync = commands.add_parser("sync", help="经宿主 launcher 执行有界显式历史同步")
    sync.add_argument("--config-dir", type=Path, required=True)
    sync.add_argument("--ledger-root", type=Path, required=True)
    sync.add_argument("--history-start", required=True)
    sync.add_argument("--history-start-accuracy", choices=("EXACT", "APPROXIMATE"), required=True)
    sync.add_argument("--window-end", required=True)

    analyze = commands.add_parser("analyze", help="只读冻结账本输入并写入确定性分析包；不连接 Tiger")
    analyze.add_argument("--ledger-root", type=Path, required=True)
    analyze.add_argument("--account-ref", required=True)
    analyze.add_argument("--cutoff", required=True)
    return value


def _require_host_launcher() -> None:
    if os.environ.get(HOST_LAUNCH_MARKER) != "1":
        raise TigerCliError("TIGER_HOST_LAUNCHER_REQUIRED")


def _emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _error_code(exc: Exception) -> str:
    candidate = str(exc).split(":", 1)[0]
    if (
        re.fullmatch(r"[A-Z][A-Z0-9_]{2,79}", candidate)
        and candidate.startswith(("TIGER_", "BROKER_LEDGER_", "CONTRACT_", "PORTFOLIO_"))
    ):
        return candidate
    return "TIGER_COMMAND_FAILED"


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "preflight":
            result = preflight_config(args.config_dir, repository_root=REPOSITORY_ROOT)
            _emit(result.to_dict())
            return 0 if result.status == "READY" else 2
        if args.command in {"snapshot", "sync"}:
            _require_host_launcher()
            ledger = PrivateBrokerLedger(args.ledger_root, repository_root=REPOSITORY_ROOT, create=True)
            account_ref = ledger.get_or_create_account_ref()
            adapter = TigerReadOnlyAdapter.from_config(args.config_dir, repository_root=REPOSITORY_ROOT)
            retrieved_at = utc_now()
            if args.command == "snapshot":
                snapshot = build_account_snapshot(adapter, account_ref=account_ref, retrieved_at=retrieved_at)
                results = persist_snapshot(ledger, snapshot, batch_id=snapshot["snapshot_id"])
                _emit({
                    "status": "READY",
                    "command": "snapshot",
                    "account_ref": account_ref,
                    "snapshot_hash": snapshot["content_hash"],
                    "visible_position_count": snapshot["coverage"]["visible_position_count"],
                    "supported_position_count": snapshot["coverage"]["supported_position_count"],
                    "excluded_position_count": snapshot["coverage"]["excluded_position_count"],
                    "write_count": len(results),
                })
                return 0
            manifest = sync_history(
                adapter, ledger, account_ref=account_ref,
                history_start=args.history_start,
                history_start_accuracy=args.history_start_accuracy,
                window_end=args.window_end,
                retrieved_at=retrieved_at,
            )
            _emit({
                "status": manifest["coverage_status"],
                "command": "sync",
                "account_ref": account_ref,
                "manifest_hash": manifest["content_hash"],
                "window_count": len(manifest["windows"]),
                "gap_count": len(manifest["gaps"]),
                "category_counts": manifest["category_counts"],
                "duplicate_count": manifest["duplicate_count"],
                "revision_count": manifest["revision_count"],
            })
            return 0 if not manifest["gaps"] else 3
        ledger = PrivateBrokerLedger(args.ledger_root, repository_root=REPOSITORY_ROOT, create=False)
        analysis = analyze_history(
            ledger, account_ref=args.account_ref, cutoff=args.cutoff, retrieved_at=utc_now(),
        )
        _emit({
            "status": analysis["coverage_status"],
            "command": "analyze",
            "account_ref": args.account_ref,
            "analysis_hash": analysis["content_hash"],
            "ledger_hash": analysis["ledger_hash"],
            "metric_count": len(analysis["metrics"]),
            "chart_count": len(analysis["charts"]),
            "excluded_count": analysis["excluded_count"],
            "unknown_count": analysis["unknown_count"],
        })
        return 0
    except Exception as exc:
        _emit({"status": "BLOCKED", "command": args.command, "code": _error_code(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
