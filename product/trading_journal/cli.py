"""Explicit local entrypoints for the two independent Skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from .common import JournalError, canonical_hash, canonical_json, iso_datetime, utc_now
from .privacy import PrivacyError, private_root, repository_root, write_private


def _json(path: Path):
    if path.is_symlink():
        raise PrivacyError("JOURNAL_SYMLINK_FORBIDDEN")
    return json.loads(path.read_text(encoding="utf-8"))


def _account(args, ledger):
    if args.account_ref:
        if not args.account_ref.startswith("account-") or len(args.account_ref) > 80:
            raise JournalError("ACCOUNT_REFERENCE_INVALID", "请使用随机本地账户引用，不要传完整账户号。")
        return args.account_ref
    if getattr(args, "new_account", False):
        return "account-" + uuid4().hex
    accounts = ledger.accounts()
    if len(accounts) != 1:
        raise JournalError("ACCOUNT_SELECTION_REQUIRED", "请明确选择已保存账户；首次导入使用新随机引用。")
    return accounts[0]


def _collection_lineage(storage, capture, normalized_csv_hash=None):
    """Persist bounded sanitized actions and the AX/export to CSV conversion."""
    identity = "collection-" + uuid4().hex
    original = capture.get("source_hash") or capture.get("export", {}).get("source_hash")
    data = {"receipt_id": identity, "source_id": capture["source_id"], "as_of": capture["as_of"],
            "retrieved_at": capture["retrieved_at"], "window": capture.get("window"),
            "original_source_hash": original, "normalized_csv_hash": normalized_csv_hash,
            "parent_receipt_id": capture.get("receipt_id"), "parent_receipt_hash": capture.get("receipt_hash"),
            "actions": [{key: entry[key] for key in ("action", "at", "status", "code") if key in entry}
                        for entry in capture.get("actions", [])],
            "pages": [{key: entry[key] for key in ("page_index", "page_hash", "row_count", "end_proven") if key in entry}
                      for entry in capture.get("pages", [])]}
    digest = canonical_hash(data)
    write_private(storage / "sources" / (identity + ".json"), canonical_json(data))
    return {key: data[key] for key in ("receipt_id", "source_id", "as_of", "retrieved_at",
                                     "original_source_hash", "normalized_csv_hash")} | {"content_hash": digest}


def build_parser():
    parser = argparse.ArgumentParser(description="独立个人交易账本与复盘，只读账户")
    parser.add_argument("--repo", type=Path, required=True, help="用户选定的绝对仓库根")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("window", "import", "collect", "chart", "prepare-reflection"):
        command = commands.add_parser(name)
        command.add_argument("--account-ref")
        command.add_argument("--period", choices=["week", "month", "half_year", "year", "lifetime", "custom"],
                             metavar="{custom,week,month,half_year,year}",
                             help="自选起止日期或四种快捷期间；旧 lifetime 参数仅兼容历史调用")
        command.add_argument("--start")
        command.add_argument("--end")
        command.add_argument("--timezone", default="Asia/Tokyo")
        command.add_argument("--account-opened-at", help=argparse.SUPPRESS)
        if name in {"import", "collect"}:
            command.add_argument("--new-account", action="store_true")
        if name == "import":
            command.add_argument("--input", type=Path, required=True)
            command.add_argument("--computer-use-receipt", type=Path,
                                 help="私人 sources 中与正式导出文件、期间和来源时区绑定的脱敏观察回执")
            command.add_argument("--exchange-timezone")
            command.add_argument("--source-timezone", help="已核验的客户端/导出显示时区")
            command.add_argument("--activity-type", choices=["FILL", "ORDER"], help="仅在已核验官方导出视图类型时提供")
        if name == "collect":
            command.add_argument("--profile", type=Path, required=True)
        if name == "chart":
            command.add_argument("--snapshot-id")
            command.add_argument("--fetch-market", action="store_true")
            command.add_argument("--market-input", type=Path)
        if name == "prepare-reflection":
            command.add_argument("--snapshot-id")
            command.add_argument("--evidence", type=Path)
            command.add_argument("--diary", type=Path)
            command.add_argument("--batch-size", type=int, default=20)
            command.add_argument("--chart-ref", action="append", default=[])
    for name in ("init", "list", "desktop-probe", "desktop-layout", "desktop-open"):
        commands.add_parser(name)
    navigation = commands.add_parser("desktop-navigate")
    navigation.add_argument("--target", choices=["account_nav", "history", "statement_nav"], required=True)
    navigation.add_argument("--nav-proof", type=Path, required=True)
    clean = commands.add_parser("prepare-clean-source")
    clean.add_argument("--baseline", type=Path, required=True)
    clean.add_argument("--baseline-hash", required=True)
    clean.add_argument("--overlay-hashes", type=Path, required=True, help="已审阅的三个目录hash对象")
    clean.add_argument("--activate", action="store_true")
    installed = commands.add_parser("verify-installed-source")
    installed.add_argument("--installed-copy", type=Path, required=True)
    submit = commands.add_parser("save-reflection")
    submit.add_argument("--packet", type=Path, required=True)
    submit.add_argument("--research", type=Path, required=True)
    submit.add_argument("--model-version", required=True)
    review = commands.add_parser("review-reflection", help="查看已保存复盘与冻结图表，不采集或联网")
    review.add_argument("--report-id", required=True)
    serve = commands.add_parser("serve-review", help="显式启动固定复盘版本的短时本机只读查看器")
    serve.add_argument("--report-id", required=True)
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--lifetime-seconds", type=int, default=900)
    journal = commands.add_parser("serve-journal", help="显式启动持续运行的本机交易与复盘工作区")
    journal.add_argument("--account-ref")
    journal.add_argument("--port", type=int, default=8765)
    counterfactual = commands.add_parser("prepare-counterfactuals")
    counterfactual.add_argument("--packet", type=Path, required=True)
    counterfactual.add_argument("--requests", type=Path, required=True)
    return parser


def run(args):
    root = repository_root(args.repo)
    if args.command.startswith("desktop-"):
        from .desktop import TigerDesktopCollector
        collector = TigerDesktopCollector()
        if args.command == "desktop-navigate":
            return collector.navigate_history(args.target, _json(args.nav_proof))
        operation = {"desktop-probe": collector.probe, "desktop-layout": collector.inspect_layout,
                     "desktop-open": collector.open_app}[args.command]
        return operation()
    if args.command == "prepare-clean-source":
        from .packaging import prepare_clean_source
        return prepare_clean_source(root, args.baseline, expected_baseline_hash=args.baseline_hash,
                                    expected_overlay_hashes=_json(args.overlay_hashes),
                                    activate=args.activate)
    if args.command == "verify-installed-source":
        from .packaging import verify_installed_source
        return verify_installed_source(root, args.installed_copy)
    if args.command == "window":
        if not args.period:
            raise JournalError("TIME_WINDOW_REQUIRED", "请选择开始日期和截止日期，或使用一周、一个月、半年、一年的快捷期间。")
        from .windows import resolve_window
        return resolve_window(args.period, timezone_name=args.timezone, start=args.start,
                              end=args.end, account_opened_at=args.account_opened_at)
    if args.command == "serve-journal":
        from .ledger import Ledger
        from .app import serve_journal
        with Ledger(private_root(root, create=False, real=False), read_only=True) as existing:
            account = _account(args, existing)
        return serve_journal(root, account, port=args.port, real=True)
    from .windows import resolve_window
    computer_export = args.command == "import" and getattr(args, "computer_use_receipt", None) is not None
    if computer_export:
        try:
            iso_datetime(args.end)
        except JournalError as exc:
            raise JournalError("COMPUTER_USE_FROZEN_END_REQUIRED", "computer-use 导入必须用 --end 传入导出前冻结的完整 ISO 截止时刻。") from exc
    window = None
    if getattr(args, "period", None):
        window = resolve_window(args.period, timezone_name=args.timezone, start=args.start,
                                end=args.end, account_opened_at=args.account_opened_at)
    if args.command in {"import", "collect"} and window is None:
        raise JournalError("TIME_WINDOW_REQUIRED", "导入或采集前必须明确期间。")
    # All CLI writes (including user-provided official exports) require the real
    # isolation proof. Tests call pure modules in their synthetic temp roots.
    storage = private_root(root, create=args.command in {"init", "import", "collect"} and not computer_export,
                           real=args.command != "list")
    if args.command == "init":
        from .ledger import Ledger
        with Ledger(storage):
            pass
        return {"status": "INITIALIZED", "private_root": str(storage)}
    from .ledger import Ledger
    prepared, prepared_records, prepared_account, prepared_coverage = None, None, None, None
    if computer_export:
        from .computer_use import parse_export, persist_receipt, validate_export
        prepared = validate_export(storage, args.input, args.computer_use_receipt, window,
                                   getattr(args, "source_timezone", None))
        if args.account_ref or args.new_account:
            prepared_account = _account(args, None)
        else:
            with Ledger(storage, read_only=True) as existing:
                prepared_account = _account(args, existing)
        prepared_records = parse_export(prepared, storage, account_ref=prepared_account,
                                        exchange_timezone=args.exchange_timezone,
                                        activity_type=args.activity_type)
        if not prepared_records:
            raise JournalError("NO_RECORDS_IN_WINDOW", "导出没有可准入所选窗口的交易，不能证明完整空历史。")
        capture = persist_receipt(prepared)
        prepared_coverage = {"collection_receipt": _collection_lineage(storage, capture, prepared["source_hash"])}
    with Ledger(storage, read_only=args.command in {"list", "review-reflection", "serve-review"}) as ledger:
        if args.command == "list":
            return {"accounts": ledger.accounts(), "snapshots": ledger.snapshots()}
        if args.command == "review-reflection":
            from .review import save_review
            return save_review(storage, args.report_id, load_snapshot=ledger.load_snapshot)
        if args.command == "serve-review":
            from .viewer import serve_review
            return serve_review(storage, args.report_id, load_snapshot=ledger.load_snapshot,
                                port=args.port, lifetime_seconds=args.lifetime_seconds)
        snapshot_id = getattr(args, "snapshot_id", None)
        loaded_snapshot = ledger.load_snapshot(snapshot_id) if snapshot_id else None
        if loaded_snapshot:
            if (args.account_ref and args.account_ref != loaded_snapshot["account_ref"]) or window is not None:
                raise JournalError("FROZEN_SNAPSHOT_SELECTION_CONFLICT", "指定冻结版本时不能改变账户或期间。")
            account = loaded_snapshot["account_ref"]
            window = loaded_snapshot["coverage"].get("requested_window")
        else:
            account = prepared_account or (_account(args, ledger) if args.command not in {"save-reflection", "prepare-counterfactuals"} else None)
        if args.command in {"import", "collect"}:
            if window is None:
                raise JournalError("TIME_WINDOW_REQUIRED", "导入或采集前必须明确期间。")
            from .normalization import parse_csv
            now, coverage, mode = utc_now(), None, "USER_ASSISTED"
            source_timezone = getattr(args, "source_timezone", None)
            activity_type = getattr(args, "activity_type", None)
            if computer_export:
                coverage, mode = prepared_coverage, "COMPUTER_USE_EXPORT"
            if args.command == "collect":
                from .desktop import TigerDesktopCollector
                profile = _json(args.profile)
                capture = TigerDesktopCollector().capture(repository_root=root, window=window,
                                                          profile=profile)
                if not capture.get("export") and not capture.get("rows"):
                    lineage = _collection_lineage(storage, capture)
                    return {"status": "DATA_BLOCKED", "gaps": capture.get("gaps", []),
                            "collection_receipt": lineage}
                mode = "VERIFIED_DESKTOP"
                source_timezone, activity_type = profile.get("source_timezone"), "FILL"
                coverage = {"gaps": capture.get("gaps", []), "pagination_end_proven": capture.get("pagination_end_proven", False)}
                if capture.get("export"):
                    input_path = Path(capture["export"]["path"])
                else:
                    import csv
                    import io
                    rows = capture["rows"]
                    output = io.StringIO()
                    headings = {"occurred_at": "Trade Time", "symbol": "Symbol", "side": "Side",
                                "quantity": "Quantity", "price": "Price", "asset_class": "Asset Type",
                                "execution_id": "Execution ID", "option_right": "Call/Put",
                                "order_id": "Order ID",
                                "expiry": "Expiry", "strike": "Strike", "multiplier": "Multiplier",
                                "underlying": "Underlying", "currency": "Currency", "market": "Market",
                                "fee": "Other Fees", "commission": "Commission", "total_fees": "Total Fees",
                                "position_effect": "Position Effect",
                                "adjustment_status": "Adjustment Status"}
                    keys = [key for key in headings if any(key in row for row in rows)]
                    writer = csv.DictWriter(output, fieldnames=[headings[key] for key in keys])
                    writer.writeheader()
                    for row in rows:
                        # Native "Fees/费用" may already include commission.
                        # Keep these raw facts in AX source/receipt, never invent
                        # a subtotal by adding overlapping fee components.
                        ambiguous = row.get("fee") not in {None, ""} and row.get("total_fees") in {None, ""}
                        writer.writerow({headings[key]: "" if ambiguous and key in {"fee", "commission"}
                                         else row.get(key, "") for key in keys})
                    input_path = storage / "sources" / ("capture-" + uuid4().hex + ".csv")
                    write_private(input_path, output.getvalue())
            else:
                input_path = args.input
            if input_path.is_symlink() or not input_path.is_file():
                raise JournalError("IMPORT_SOURCE_INVALID", "导入需要普通官方文件。")
            digest = prepared["source_hash"] if computer_export else hashlib.sha256(input_path.read_bytes()).hexdigest()
            if args.command == "collect":
                coverage["collection_receipt"] = _collection_lineage(storage, capture, digest)
            records = prepared_records if computer_export else parse_csv(
                input_path, account_ref=account, source_id="tiger-source:" + digest,
                as_of=window["end"], retrieved_at=now,
                exchange_timezone=getattr(args, "exchange_timezone", None),
                source_timezone=source_timezone, activity_type=activity_type)
            from .windows import record_in_window
            # Every import mode respects the exact frozen user interval before
            # ledger persistence, even when an export contains wider dates.
            records = [record for record in records if record_in_window(record, window)]
            if not input_path.resolve().is_relative_to(storage):
                destination = storage / "sources" / (digest + ".csv")
                if not destination.exists():
                    write_private(destination, input_path.read_bytes())
            receipt = ledger.import_records(records, source_hash=digest, requested_window=window,
                                            coverage=coverage, mode=mode)
            snapshot = ledger.freeze_snapshot(account, window=window)
            return {"status": "SAVED", "account_ref": account, "receipt": receipt,
                    "snapshot_id": snapshot["snapshot_id"], "input_hash": snapshot["input_hash"]}
        if args.command == "save-reflection":
            from .reflection import assemble_report, save_report
            packet, research = _json(args.packet), _json(args.research)
            allowed = {"findings", "improvement_plan", "phase_coverage", "analyzed_episode_ids", "limitations", "case_lessons"}
            if not isinstance(research, dict) or set(research) - allowed:
                raise JournalError("RESEARCH_FIELDS_NOT_ALLOWED", "仅接受研究字段，技术身份由工具装配。")
            trusted = ledger.load_snapshot(packet.get("snapshot", {}).get("snapshot_id", ""))
            if packet.get("snapshot") != trusted:
                raise JournalError("REFLECTION_SNAPSHOT_NOT_IN_LEDGER", "复盘输入必须匹配本地冻结版本。")
            report = assemble_report(packet, model_version=args.model_version, skill_version="1.4.0",
                                     **research)
            return save_report(storage, report, packet)
        if args.command == "prepare-counterfactuals":
            from .reflection import prepare_counterfactuals, save_packet
            packet = _json(args.packet)
            trusted = ledger.load_snapshot(packet.get("snapshot", {}).get("snapshot_id", ""))
            if packet.get("snapshot") != trusted:
                raise JournalError("REFLECTION_SNAPSHOT_NOT_IN_LEDGER", "复盘输入必须匹配本地冻结版本。")
            packet = prepare_counterfactuals(packet, _json(args.requests))
            return {"packet_path": str(save_packet(storage, packet)), "packet_hash": packet["packet_hash"]}
        snapshot = loaded_snapshot or ledger.freeze_snapshot(account, window=window)
        if args.command == "chart":
            market = _json(args.market_input) if args.market_input else snapshot.get("market", [])
            if args.fetch_market:
                from .market import fetch_market
                times = [record["occurred_at"][:10] for record in snapshot["records"]]
                if not times:
                    raise JournalError("NO_RECORDS_FOR_MARKET", "当前版本没有可查询行情的证券记录。")
                start = (date.fromisoformat(min(times)) - timedelta(days=90)).isoformat()
                from zoneinfo import ZoneInfo
                zone = ZoneInfo((window or {}).get("timezone", "Asia/Tokyo"))
                end = datetime.fromisoformat(utc_now().replace("Z", "+00:00")).astimezone(zone).date().isoformat()
                instruments = {record["instrument"]["key"]: record["instrument"] for record in snapshot["records"]}
                market = [fetch_market(instrument, start, end) for instrument in instruments.values()]
            if market != snapshot.get("market", []):
                snapshot = ledger.derive_snapshot(snapshot["snapshot_id"], market=market)
            from .charts import render_chart
            rendered = render_chart(snapshot)
            # A reader update creates a new view of the same frozen facts.
            # The previous snapshot.html remains immutable and readable.
            view_hash = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
            output = storage / "artifacts" / (snapshot["snapshot_id"] + "-chart-" + view_hash + ".html")
            if not output.exists():
                write_private(output, rendered)
            elif (output.is_symlink() or not output.is_file() or output.stat().st_mode & 0o777 != 0o600
                  or output.read_text(encoding="utf-8") != rendered):
                raise PrivacyError("JOURNAL_CHART_ARTIFACT_CONFLICT")
            return {"snapshot_id": snapshot["snapshot_id"], "chart_path": str(output), "content_hash": view_hash,
                    "coverage": snapshot["coverage"]["status"]}
        if args.command == "prepare-reflection":
            from .reflection import prepare_reflection, save_packet
            packet = prepare_reflection(snapshot, evidence=_json(args.evidence) if args.evidence else [],
                                        diary=_json(args.diary) if args.diary else [], cutoff=utc_now(),
                                        batch_size=args.batch_size, chart_refs=args.chart_ref)
            return {"packet_path": str(save_packet(storage, packet)), "packet_hash": packet["packet_hash"],
                    "scope": packet["scope"], "progress": packet["progress"]}
    raise JournalError("UNKNOWN_COMMAND", "入口命令未支持。")


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
        return 0
    except (JournalError, PrivacyError) as exc:
        result = {"status": "BLOCKED", "code": exc.code}
        if args.command == "desktop-navigate" and isinstance(exc, JournalError):
            details = exc.details
            if isinstance(details, dict) and "nav_audit" in details:
                from .desktop import _safe_navigation_audit
                try:
                    result["nav_audit"] = _safe_navigation_audit(details["nav_audit"])
                except JournalError:
                    # Missing or invalid audit means the issued state is unknown;
                    # never substitute false or echo arbitrary exception details.
                    pass
        print(json.dumps(result, ensure_ascii=False))
        return 2
    except (OSError, ValueError, KeyError, TypeError):
        # Never print raw source fields, credentials, paths from exception text.
        print(json.dumps({"status": "BLOCKED", "code": "JOURNAL_INPUT_OR_STORAGE_INVALID"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
