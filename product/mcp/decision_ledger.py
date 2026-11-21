"""decision/v2 records: one scoreable trade decision per card, saved before the outcome is known.

Records go to <STOCK_AGENT_DATA_DIR>/trade_decisions.jsonl (default <repo>/.local/data) and the full card to
<STOCK_AGENT_DATA_DIR>/trade-reports/<YYYY-MM-DD>/<TICKER>-<decision_id>.md. The old decisions.jsonl and
decision_log.save_decision are untouched. Mechanical fields (id, timestamps, w0/w1, horizon, code version, sha)
are produced here and are refused when the caller tries to pass them. Rules: evals/forward/decision-protocol-v1.md.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from product.mcp import settings
from product.mcp.decision_log import CAUSES, DecisionLogError, _code_version
from product.mcp.provenance import iso_utc

# Decision-card report: every one of these "## " headings must be present (any order). E0 may write 不适用 under
# 消息归因, but the heading stays. Fixed by the main session (T5).
REQUIRED_SECTIONS = ("结论", "概率与收益", "消息归因", "上次决策", "复核条件", "数据缺口", "来源")

SCHEMA = "decision/v2"
FILL_RULE = "next_regular_open_after_decided_at"
NY = ZoneInfo("America/New_York")
DAY_END = time(23, 59, 59)  # a bare date means that day's end in New York, as in data_tools._cutoff

SOURCES = ("scan", "on_demand")
POSITION_STATES = ("held", "not_held")
GROUPS = ("E0", "E1", "E2")
HORIZON_DAYS = {"E0": 60, "E1": 20, "E2": 60}  # protocol v1 §2: E1 earnings 20d, the rest 60d
ACTIONS = {"held": ("ADD", "HOLD", "REDUCE", "EXIT"), "not_held": ("BUY", "WAIT")}
W1 = {"EXIT": 0.0, "REDUCE": 0.5, "HOLD": 1.0, "ADD": 1.5, "WAIT": 0.0, "BUY": 0.5}  # protocol v1 §4
W0 = {"held": 1.0, "not_held": 0.0}
CASH_DESTINATIONS = ("cash", "sector_etf")
HOLD_TYPES = ("no_edge", "has_view")
NO_SECTOR = "no_sector"
# Fields the tool writes itself; passing any of them is refused.
GENERATED_FIELDS = ("schema", "decision_id", "decided_at", "decided_at_effective", "info_cutoff", "w0", "w1",
                    "horizon_days", "fill_rule", "code_version", "report_sha256", "report_path", "replay")


def _text(name: str, value: Any, *, single_line: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecisionLogError(f"{name.upper()}_REQUIRED")
    value = value.strip()
    if single_line and "\n" in value:
        raise DecisionLogError(f"{name.upper()}_MUST_BE_ONE_LINE")
    return value


def _opt_text(value: Any) -> str | None:
    return str(value).strip() or None if value is not None else None


def _iso_date(name: str, value: Any) -> str:
    text = str(value).strip() if isinstance(value, str) else ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise DecisionLogError(f"{name.upper()}_INVALID: use YYYY-MM-DD")
    try:
        date.fromisoformat(text)
    except ValueError:
        raise DecisionLogError(f"{name.upper()}_INVALID: not a calendar date") from None
    return text


def _probability(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise DecisionLogError(f"{name.upper()}_INVALID: number between 0 and 1, e.g. 0.55 (0.5 is allowed)")
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise DecisionLogError(f"{name.upper()}_INVALID: number between 0 and 1, e.g. 0.55") from None
    if not number.is_finite() or not 0 <= number <= 1:
        raise DecisionLogError(f"{name.upper()}_INVALID: number between 0 and 1")
    return float(number)


def _only_keys(name: str, obj: dict, allowed: tuple[str, ...]) -> None:
    unknown = sorted(set(obj) - set(allowed))
    if unknown:
        raise DecisionLogError(f"{name.upper()}_UNKNOWN_FIELDS: {unknown}; allowed {list(allowed)}")


def _event(value: Any, group: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DecisionLogError("EVENT_REQUIRED: {event_date, moment?, deviation_z?, d0?, accession?}")
    _only_keys("event", value, ("event_date", "moment", "deviation_z", "d0", "accession"))
    out: dict[str, Any] = {"event_date": _iso_date("event_date", value.get("event_date"))}
    if value.get("moment") is not None:
        out["moment"] = _text("event.moment", value["moment"])
    if value.get("deviation_z") is not None:
        z = value["deviation_z"]
        if isinstance(z, bool) or not isinstance(z, (int, float)) or z != z or abs(z) == float("inf"):
            raise DecisionLogError("EVENT_DEVIATION_Z_INVALID: finite number")
        out["deviation_z"] = float(z)
    if value.get("d0") is not None:
        out["d0"] = _iso_date("event.d0", value["d0"])
    if value.get("accession") is not None:
        out["accession"] = _text("event.accession", value["accession"])
    if group == "E2" and "deviation_z" not in out:
        # B1 (protocol §5) needs the deviation direction, so an E2 record must carry it.
        raise DecisionLogError("EVENT_DEVIATION_Z_REQUIRED: an E2 event needs deviation_z (from classify_decision_event)")
    return out


def _p_outperform(value: Any, benchmark: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DecisionLogError("P_OUTPERFORM_REQUIRED: {baseline, case, basis}")
    _only_keys("p_outperform", value, ("baseline", "case", "basis"))
    basis = _text("p_outperform.basis", value.get("basis"))
    if benchmark == NO_SECTOR:
        # no sector ETF, so no relative probability: record it as missing rather than invent 0.5
        if value.get("baseline") is not None or value.get("case") is not None:
            raise DecisionLogError("P_OUTPERFORM_NOT_APPLICABLE: no_sector has no sector ETF; set baseline and case "
                                   "to null and say so in basis")
        return {"baseline": None, "case": None, "basis": basis}
    return {"baseline": _probability("p_outperform.baseline", value.get("baseline")),
            "case": _probability("p_outperform.case", value.get("case")),
            "basis": basis}


def _attribution(value: Any, group: str) -> dict[str, Any] | None:
    if value is None:
        if group in ("E1", "E2"):
            raise DecisionLogError("ATTRIBUTION_REQUIRED: E1/E2 need {primary_cause, company_cause, explicit_guidance_cut}")
        return None
    if not isinstance(value, dict):
        raise DecisionLogError("ATTRIBUTION_INVALID: {primary_cause, company_cause, explicit_guidance_cut}")
    _only_keys("attribution", value, ("primary_cause", "company_cause", "explicit_guidance_cut"))
    cause = value.get("primary_cause")
    if cause not in CAUSES:
        raise DecisionLogError(f"PRIMARY_CAUSE_INVALID: one of {CAUSES}")
    company = value.get("company_cause")
    if not (isinstance(company, bool) or company == "unconfirmed"):
        raise DecisionLogError("COMPANY_CAUSE_INVALID: true, false or \"unconfirmed\"")
    cut = value.get("explicit_guidance_cut")
    if not isinstance(cut, bool):
        raise DecisionLogError("EXPLICIT_GUIDANCE_CUT_INVALID: true or false")
    return {"primary_cause": cause, "company_cause": company, "explicit_guidance_cut": cut}


def _review_triggers(value: Any) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise DecisionLogError("REVIEW_TRIGGERS_MUST_BE_LIST_OF_TEXT")
    items = [v.strip() for v in value]
    if len(items) < 2:
        raise DecisionLogError("REVIEW_TRIGGERS_TOO_FEW: at least two conditions for re-deciding")
    if not any(re.search(r"\d", v) for v in items):
        raise DecisionLogError("REVIEW_TRIGGERS_NO_NUMBER: at least one trigger must carry a number (a price level)")
    return items


def _check_report(report: Any) -> str:
    report = _text("report_markdown", report)
    headings = ["".join(line[3:].split()) for line in report.splitlines() if line.startswith("## ")]
    missing = [n for n in REQUIRED_SECTIONS if not any(h.startswith("".join(n.split())) for h in headings)]
    if missing:
        raise DecisionLogError("REPORT_SECTIONS_MISSING: rewrite the card with the decision-card template headings "
                               "(\"## <name>\"), then save again. Missing: " + ", ".join(missing))
    return report


def _decision_times(replay_as_of: str | None) -> tuple[datetime, datetime]:
    """(decided_at, decided_at_effective). A replay pins the effective time to just after 16:00 New York on the
    replay date so the paper fill (next regular open) lands where a real decision that day would have."""
    now = datetime.now(UTC)
    configured = settings.replay_as_of()
    if replay_as_of is None:
        replay_as_of = configured
    elif configured and _iso_date("replay_as_of", replay_as_of) != configured:
        raise DecisionLogError(f"REPLAY_AS_OF_MISMATCH: this session is a replay as of {configured}")
    if replay_as_of is None:
        return now, now
    day = date.fromisoformat(_iso_date("replay_as_of", replay_as_of))
    if day >= now.astimezone(NY).date():
        # the replay cutoff is the end of that New York day, so the day must be over
        raise DecisionLogError("REPLAY_AS_OF_INVALID: must be a finished New York day (before today)")
    # Same instant the point-in-time tools use for a bare date (23:59:59 New York), so info_cutoff matches what the
    # card could see; the paper fill (next regular open) is unchanged.
    effective = datetime.combine(day, DAY_END, tzinfo=NY).astimezone(UTC)
    return now, effective


def _prior_record(path, decision_id: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            if record.get("decision_id") == decision_id:
                return record
    return None


def _when(record: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(record.get("decided_at_effective") or record["decided_at"]).replace("Z", "+00:00"))


def save_trade_decision(ticker: str, source: str, position_state: str, group: str, event: dict[str, Any],
                        benchmark: str, action: str, cash_destination: str, p_outperform: dict[str, Any],
                        review_triggers: list[str], thesis: str, report_markdown: str,
                        attribution: dict[str, Any] | None = None, hold_type: str | None = None,
                        prior_decision_id: str | None = None, replay_as_of: str | None = None,
                        host: str | None = None, model: str | None = None, **extra: Any) -> dict[str, Any]:
    """Validate and append one decision/v2 record (see module docstring). Returns the generated fields."""
    if extra:
        generated = sorted(set(extra) & set(GENERATED_FIELDS))
        if generated:
            raise DecisionLogError(f"GENERATED_FIELD_NOT_ACCEPTED: {generated} are written by the tool, never by "
                                   "the caller; remove them and save again")
        raise DecisionLogError(f"UNKNOWN_FIELDS: {sorted(extra)}")
    ticker = str(ticker).strip().upper().replace(".", "-")
    if not re.fullmatch(r"[A-Z][A-Z0-9\-]{0,9}", ticker):
        raise DecisionLogError("TICKER_INVALID")
    if source not in SOURCES:
        raise DecisionLogError(f"SOURCE_INVALID: one of {SOURCES}")
    if position_state not in POSITION_STATES:
        raise DecisionLogError(f"POSITION_STATE_INVALID: one of {POSITION_STATES}")
    if group not in GROUPS:
        raise DecisionLogError(f"GROUP_INVALID: one of {GROUPS}")
    if action not in ACTIONS[position_state]:
        raise DecisionLogError(f"ACTION_INVALID: {position_state} allows {ACTIONS[position_state]}")
    if source == "scan" and position_state != "held":
        raise DecisionLogError("SCAN_REQUIRES_HELD: scan events assume one held standard position (protocol §4)")
    if cash_destination not in CASH_DESTINATIONS:
        raise DecisionLogError(f"CASH_DESTINATION_INVALID: one of {CASH_DESTINATIONS}")
    benchmark = str(benchmark).strip().upper().replace(".", "-") if isinstance(benchmark, str) else ""
    benchmark = benchmark if benchmark != NO_SECTOR.upper() else NO_SECTOR
    if benchmark != NO_SECTOR and not re.fullmatch(r"[A-Z][A-Z0-9\-]{0,9}", benchmark):
        raise DecisionLogError("BENCHMARK_INVALID: a sector ETF ticker, or \"no_sector\"")
    if benchmark == NO_SECTOR and group == "E2":
        raise DecisionLogError("E2_REQUIRES_SECTOR: a stock without a sector mapping cannot be E2 (protocol §7)")
    if benchmark == NO_SECTOR and cash_destination == "sector_etf":
        raise DecisionLogError("SECTOR_ETF_WITHOUT_BENCHMARK: no sector ETF to move into; use cash_destination=cash")
    event = _event(event, group)
    p_outperform = _p_outperform(p_outperform, benchmark)
    attribution = _attribution(attribution, group)
    if action in ("HOLD", "WAIT"):
        if hold_type not in HOLD_TYPES:
            raise DecisionLogError(f"HOLD_TYPE_REQUIRED: {action} needs hold_type, one of {HOLD_TYPES}")
    elif hold_type is not None:
        raise DecisionLogError(f"HOLD_TYPE_NOT_ALLOWED: only HOLD/WAIT carry hold_type; leave it null for {action}")
    review_triggers = _review_triggers(review_triggers)
    thesis = _text("thesis", thesis, single_line=True)
    report = _check_report(report_markdown)
    decided_at, effective = _decision_times(replay_as_of)
    if event["event_date"] > effective.astimezone(NY).date().isoformat():
        raise DecisionLogError("EVENT_DATE_IN_FUTURE: event_date is after the decision date")
    root = settings.data_dir()
    log_path = root / "trade_decisions.jsonl"
    if prior_decision_id is not None:
        prior_decision_id = _text("prior_decision_id", prior_decision_id)
        prior = _prior_record(log_path, prior_decision_id)
        if prior is None:
            raise DecisionLogError(f"PRIOR_DECISION_NOT_FOUND: {prior_decision_id} is not in trade_decisions.jsonl")
        prior_when = _when(prior)
        if prior.get("ticker") != ticker or prior_when >= effective or bool(prior.get("replay")) != (effective != decided_at):
            raise DecisionLogError("PRIOR_DECISION_INVALID: the prior card must be the same ticker, decided before this "
                                   "one, and both live or both replay; use get_prior_trade_decision")
    report_text = report.rstrip() + "\n"
    stamp = iso_utc(decided_at)
    effective_stamp = iso_utc(effective)
    record = {
        "schema": SCHEMA, "ticker": ticker, "source": source, "position_state": position_state, "group": group,
        "event": event, "benchmark": benchmark, "action": action, "cash_destination": cash_destination,
        "p_outperform": p_outperform, "attribution": attribution, "hold_type": hold_type,
        "review_triggers": review_triggers, "thesis": thesis, "prior_decision_id": prior_decision_id,
        "host": _opt_text(host), "model": _opt_text(model),
        # generated below this line
        "decided_at": stamp, "decided_at_effective": effective_stamp, "replay": effective != decided_at,
        "info_cutoff": effective_stamp, "w0": W0[position_state], "w1": W1[action],
        "horizon_days": HORIZON_DAYS[group], "fill_rule": FILL_RULE, "code_version": _code_version(),
        "report_sha256": hashlib.sha256(report_text.encode("utf-8")).hexdigest(),
    }
    record["decision_id"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:12]
    report_dir = root / "trade-reports" / stamp[:10]
    report_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    report_path = report_dir / f"{ticker}-{record['decision_id']}.md"
    with report_path.open("x", encoding="utf-8") as handle:
        handle.write(report_text)
    record["report_path"] = str(report_path)
    fd = os.open(log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return {"saved": True, "decision_id": record["decision_id"], "decided_at": stamp,
            "decided_at_effective": effective_stamp, "replay": record["replay"], "w0": record["w0"],
            "w1": record["w1"], "horizon_days": record["horizon_days"], "report_sha256": record["report_sha256"],
            "report_path": str(report_path), "decision_log": str(log_path)}


PRIOR_FIELDS = ("decision_id", "decided_at_effective", "replay", "source", "position_state", "group", "event",
                "horizon_days", "benchmark", "action", "w0", "w1", "hold_type", "p_outperform", "attribution",
                "review_triggers", "thesis", "report_path")


def get_prior_trade_decision(ticker: str, before: str | None = None) -> dict[str, Any]:
    """Latest decision card for `ticker` whose effective decision time is strictly before `before` (ISO date =
    that day's 16:00 New York close; ISO datetime as given; default now, or the replay date's close in a replay).
    Returns {"found": False} when there is none. The card is the earlier advice, not proof the user acted on it."""
    ticker = _text("ticker", ticker).upper().replace(".", "-")
    replay = settings.replay_as_of()
    raw = before or replay
    if raw is None:
        cutoff = datetime.now(UTC)
    elif len(str(raw)) == 10:
        cutoff = datetime.combine(date.fromisoformat(_iso_date("before", raw)), DAY_END,
                                  tzinfo=NY).astimezone(UTC)
    else:
        try:
            cutoff = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            raise DecisionLogError("BEFORE_INVALID: YYYY-MM-DD or ISO datetime") from None
        if cutoff.tzinfo is None:
            raise DecisionLogError("BEFORE_INVALID: datetime needs a timezone")
    if replay:
        cutoff = min(cutoff, datetime.combine(date.fromisoformat(replay), DAY_END, tzinfo=NY).astimezone(UTC))
    path = settings.data_dir() / "trade_decisions.jsonl"
    best = None
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("ticker") != ticker or bool(r.get("replay")) != bool(replay):
                continue  # live cards only see live cards, replays only replays
            when = _when(r)
            if when < cutoff and (best is None or when > best[0]):
                best = (when, r)
    if best is None:
        return {"found": False, "ticker": ticker, "before": cutoff.isoformat()}
    record = best[1]
    out = {"found": True, "ticker": ticker, "before": cutoff.isoformat(), **{k: record.get(k) for k in PRIOR_FIELDS}}
    report = record.get("report_path")
    if report and Path(report).exists():
        out["report_markdown"] = Path(report).read_text(encoding="utf-8")
    return out

