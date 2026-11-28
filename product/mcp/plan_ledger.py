"""plan/v1 records: paper trade plans (candidate -> plan -> revision -> review -> choice), append-only.

Records go to <STOCK_AGENT_DATA_DIR>/trade_plans.jsonl (default <repo>/.local/data); a plan card and each review
report go to <STOCK_AGENT_DATA_DIR>/plan-reports/<YYYY-MM-DD>/<TICKER>-<id>.md. decision/v2 (trade_decisions.jsonl)
is untouched. Mechanical fields (ids, timestamps, shares, R0, rules, code version, report hashes) are produced here and
are refused when the caller passes them. Design: fucxxx-codex-spec/designs/position-lifecycle.md.

Time model, as in decision_ledger: a live record is effective "now"; a replay record is effective at 23:59:59 New York
on the replay date. Live records only see live records and replay records only replay records; a tool called by plan_id
in the wrong kind of session is refused (PLAN_REPLAY_MISMATCH). Every read first cuts the records at the session cutoff
(live: now; replay: 23:59:59 New York on the replay date): a record effective after it does not exist for that read.
Writers take a file lock (trade_plans.jsonl.lock) around check + append, so the 8-plan limit, one-per-ticker and version
numbers hold when two sessions write at once.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
import fcntl
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from product.mcp import settings
from product.mcp.decision_ledger import DAY_END, NY, _decision_times, _iso_date, _only_keys, _opt_text, _text
from product.mcp.decision_log import DecisionLogError, _code_version
from product.mcp.provenance import iso_utc

SCHEMA = "plan/v1"
FILL_RULE = "next_regular_open_after_frozen_at"
STOP_RULE = "close_at_or_below_then_next_open"
COST_BPS_PER_SIDE = 10
TEMPLATES = ("catalyst_event",)
CANDIDATE_OUTCOMES = ("wait", "not_formed")  # outcome=plan is written by save_trade_plan itself
VIEWS = ("full", "thesis")
VERDICTS = ("strengthened", "unchanged", "weakened", "broken", "insufficient")
ACTIONS = ("HOLD", "REDUCE", "EXIT")
EVIDENCE_KINDS = ("filing", "news", "price", "other")
CHOICES = ("followed", "declined", "abandoned")
REVISABLE = ("price_invalidation", "hold_basis", "review_dates", "abandon_facts")
MAX_ACTIVE = 8
MAX_HORIZON_DAYS = 120

PLAN_SECTIONS = ("论点", "催化剂", "放弃理由的事实", "价格失效位与预算亏损", "持有依据与复核日", "数据缺口", "来源")
REVIEW_SECTIONS = ("论点复核", "价格与动作", "数据缺口", "来源")
# Fields the tool writes itself; passing any of them to save_trade_plan is refused.
GENERATED_FIELDS = ("schema", "kind", "plan_id", "candidate_id", "decided_at", "frozen_at", "replay", "shares_planned",
                    "r0", "fill_rule", "stop_rule", "cost_bps_per_side", "code_version", "model_recorded",
                    "report_path", "report_sha256")


# ---------------------------------------------------------------------------------------------- small helpers

def _ticker(value: Any) -> str:
    ticker = str(value).strip().upper().replace(".", "-")
    if not re.fullmatch(r"[A-Z][A-Z0-9\-]{0,9}", ticker):
        raise DecisionLogError("TICKER_INVALID")
    return ticker


def _positive(name: str, value: Any) -> float:
    """Finite number > 0 (int, float or numeric text; never bool)."""
    code = f"{name.upper()}_INVALID"
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise DecisionLogError(f"{code}: a positive number")
    try:
        number = float(str(value).strip()) if isinstance(value, str) else float(value)
    except ValueError:
        raise DecisionLogError(f"{code}: a positive number") from None
    if not math.isfinite(number) or number <= 0:
        raise DecisionLogError(f"{code}: a positive finite number")
    return number


def _model_recorded(model: Any) -> dict[str, Any]:
    run_model = os.environ.get("STOCK_AGENT_RUN_MODEL", "").strip()
    if run_model:
        return {"value": run_model, "source": "run_env"}
    return {"value": _opt_text(model), "source": "self_reported"}


def _check_sections(report: Any, required: tuple[str, ...], what: str) -> str:
    report = _text("report_markdown", report)
    headings = ["".join(line[3:].split()) for line in report.splitlines() if line.startswith("## ")]
    missing = [n for n in required if not any(h.startswith("".join(n.split())) for h in headings)]
    if missing:
        raise DecisionLogError(f"REPORT_SECTIONS_MISSING: rewrite the {what} with the template headings "
                               "(\"## <name>\"), then save again. Missing: " + ", ".join(missing))
    return report


def _abandon_facts(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise DecisionLogError("ABANDON_FACTS_REQUIRED: at least one {document, fact}: a public fact that would "
                               "make you drop the plan")
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise DecisionLogError("ABANDON_FACTS_INVALID: each item is {document, fact}")
        _only_keys("abandon_facts", item, ("document", "fact"))
        for key in ("document", "fact"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise DecisionLogError(f"ABANDON_FACTS_INVALID: every item needs a non-empty {key}")
        out.append({"document": item["document"].strip(), "fact": item["fact"].strip()})
    return out


def _review_dates(value: Any, after: date) -> list[str]:
    if not isinstance(value, list) or not value:
        raise DecisionLogError("REVIEW_DATES_REQUIRED: at least one YYYY-MM-DD review date")
    out = []
    for item in value:
        text = _iso_date("review_dates", item)
        if date.fromisoformat(text) <= after:
            raise DecisionLogError(f"REVIEW_DATES_INVALID: {text} is not after the decision date {after.isoformat()}")
        out.append(text)
    return out


def _horizon(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_HORIZON_DAYS:
        raise DecisionLogError(f"HORIZON_CAP_DAYS_INVALID: integer 1..{MAX_HORIZON_DAYS} calendar days")
    return value


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


_ISO_DATETIME_TZ = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})")


def _evidence_bounds(value: Any) -> tuple[datetime, datetime, bool]:
    """published_at -> (earliest, latest, is_bare_date). Only two forms are accepted. YYYY-MM-DD means "some time that
    New York day": [00:00:00, 23:59:59]. A full ISO datetime must carry a timezone (Z or +hh:mm) and is exact.
    Anything else (20260303, a datetime without timezone, ...) is PUBLISHED_AT_INVALID."""
    text = str(value).strip() if isinstance(value, str) else ""
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            day = date.fromisoformat(text)
            return (datetime.combine(day, datetime.min.time(), tzinfo=NY).astimezone(UTC),
                    datetime.combine(day, DAY_END, tzinfo=NY).astimezone(UTC), True)
        if not _ISO_DATETIME_TZ.fullmatch(text):
            raise ValueError(text)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise DecisionLogError("EVIDENCE_PUBLISHED_AT_INVALID: PUBLISHED_AT_INVALID: use YYYY-MM-DD or a full ISO "
                               "datetime with a timezone (e.g. 2026-03-03T10:00:00-05:00)") from None
    if parsed.tzinfo is None:
        raise DecisionLogError("EVIDENCE_PUBLISHED_AT_INVALID: PUBLISHED_AT_INVALID: the datetime needs a timezone")
    exact = parsed.astimezone(UTC)
    return exact, exact, False


def _evidence(value: Any, effective: datetime) -> tuple[list[dict[str, str]], list[tuple[str, datetime]]]:
    """Validated evidence items and [(kind, earliest publication time)] for the "newer than the last review" test.
    "Already public" uses the latest possible time: a bare date that could still be after the review's effective time
    (same New York day, review earlier than the day's end) is EVIDENCE_TIME_AMBIGUOUS, a later day EVIDENCE_AFTER_REVIEW."""
    if not isinstance(value, list) or not value:
        raise DecisionLogError("EVIDENCE_REQUIRED: at least one {kind, source, published_at, claim, original_condition}")
    items, times = [], []
    for item in value:
        if not isinstance(item, dict):
            raise DecisionLogError("EVIDENCE_INVALID: each item is {kind, source, published_at, claim, original_condition}")
        _only_keys("evidence", item, ("kind", "source", "published_at", "claim", "original_condition"))
        if item.get("kind") not in EVIDENCE_KINDS:
            raise DecisionLogError(f"EVIDENCE_KIND_INVALID: one of {EVIDENCE_KINDS}")
        clean = {key: _text(f"evidence_{key}", item.get(key)) for key in
                 ("source", "published_at", "claim", "original_condition")}
        earliest, latest, bare = _evidence_bounds(clean["published_at"])
        if earliest > effective:
            raise DecisionLogError(f"EVIDENCE_AFTER_REVIEW: {clean['published_at']} is later than the review's effective "
                                   f"time {iso_utc(effective)}")
        if latest > effective:
            raise DecisionLogError(f"EVIDENCE_TIME_AMBIGUOUS: {clean['published_at']} is a bare date and may be later than "
                                   f"the review's effective time {iso_utc(effective)}; give the exact publication time "
                                   "(ISO datetime) or review after that day ends")
        items.append({"kind": item["kind"], **clean})
        times.append((item["kind"], earliest))
    return items, times


# ---------------------------------------------------------------------------------------------- storage

def _log_path() -> Path:
    return settings.data_dir() / "trade_plans.jsonl"


def _read_rows() -> list[dict[str, Any]]:
    path = _log_path()
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            raise DecisionLogError(f"LEDGER_CORRUPT: trade_plans.jsonl line {number} is not JSON") from None
    return rows


def _append(*records: dict[str, Any]) -> None:
    """One O_APPEND write for all records, so a plan and its candidate row are never split."""
    path = _log_path()
    data = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records).encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


@contextmanager
def _ledger_lock():
    """Exclusive cross-process lock for check + append. flock is per open file, so threads of one process also
    exclude each other. Never nest."""
    fd = os.open(settings.data_dir() / "trade_plans.jsonl.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # closing releases the lock


def _write_report(ticker: str, rid: str, stamp: str, report_text: str) -> Path:
    report_dir = settings.data_dir() / "plan-reports" / stamp[:10]
    report_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = report_dir / f"{ticker}-{rid}.md"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(report_text)
    return path


def _hash_id(record: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:12]


def _group(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """plan_id -> {"plan", "revisions" (by version), "reviews" (by effective time), "choices"}, in file order."""
    bundles: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("kind") == "plan":
            bundles[row["plan_id"]] = {"plan": row, "revisions": [], "reviews": [], "choices": []}
    for row in rows:
        bundle = bundles.get(row.get("plan_id"))
        if bundle is None:
            continue
        if row.get("kind") == "revision":
            bundle["revisions"].append(row)
        elif row.get("kind") == "review":
            bundle["reviews"].append(row)
        elif row.get("kind") == "choice":
            bundle["choices"].append(row)
    for bundle in bundles.values():
        bundle["revisions"].sort(key=lambda r: r["version"])
        bundle["reviews"].sort(key=lambda r: _dt(r["reviewed_at_effective"]))
    return bundles


def _choice_time(choice: dict[str, Any]) -> datetime:
    return _dt(choice.get("effective_at") or choice["recorded_at"])


def _end_of_day(day: date) -> datetime:
    return datetime.combine(day, DAY_END, tzinfo=NY).astimezone(UTC)


def _cut(bundle: dict[str, Any], cutoff: datetime) -> dict[str, Any] | None:
    """The bundle as it was at `cutoff`: records effective after it are dropped; None if the plan was not frozen yet."""
    if _dt(bundle["plan"]["frozen_at"]) > cutoff:
        return None
    return {"plan": bundle["plan"],
            "revisions": [r for r in bundle["revisions"] if _dt(r["effective_at"]) <= cutoff],
            "reviews": [r for r in bundle["reviews"] if _dt(r["reviewed_at_effective"]) <= cutoff],
            "choices": [c for c in bundle["choices"] if _choice_time(c) <= cutoff]}


def _status(bundle: dict[str, Any], today_ny: date, as_of: datetime) -> tuple[bool, str]:
    """In progress = frozen, not abandoned, no EXIT review, and decision day + horizon_cap_days not yet passed
    (New York dates). Abandon and EXIT only count when effective on or before `as_of`. Records only; no prices."""
    plan = bundle["plan"]
    if _dt(plan["frozen_at"]) > as_of:
        return False, "not_yet_frozen"
    if any(c.get("choice") == "abandoned" and _choice_time(c) <= as_of for c in bundle["choices"]):
        return False, "abandoned"
    if any(r.get("action") == "EXIT" and _dt(r["reviewed_at_effective"]) <= as_of for r in bundle["reviews"]):
        return False, "exit_review"
    if today_ny > _cap_date(plan):
        return False, "cap_passed"
    return True, "active"


def _cap_date(plan: dict[str, Any]) -> date:
    return _dt(plan["frozen_at"]).astimezone(NY).date() + timedelta(days=int(plan["horizon_cap_days"]))


def _session() -> tuple[bool, date, datetime]:
    """(replay session?, New York 'today', read cutoff). Live: now. Replay (STOCK_AGENT_REPLAY_AS_OF): that day's end."""
    configured = settings.replay_as_of()
    if configured:
        day = date.fromisoformat(configured)
        return True, day, _end_of_day(day)
    now = datetime.now(UTC)
    return False, now.astimezone(NY).date(), now


def _check_session(plan: dict[str, Any], replay_session: bool) -> None:
    if bool(plan.get("replay")) != replay_session:
        raise DecisionLogError("PLAN_REPLAY_MISMATCH: a replay plan is only read and written in a replay session "
                               "(STOCK_AGENT_REPLAY_AS_OF / replay_as_of), a live plan only in a live session")


def active_plans(today_ny: date, replay: bool, as_of: datetime | None = None) -> list[dict[str, Any]]:
    """Plan records in progress on `today_ny`, among records of the same kind (replay with replay, live with live).
    `as_of` (default: end of today_ny in New York) is the cutoff: records effective after it are invisible."""
    if as_of is None:
        as_of = _end_of_day(today_ny)
    out = []
    for raw in _group(_read_rows()).values():
        if bool(raw["plan"].get("replay")) != bool(replay):
            continue
        bundle = _cut(raw, as_of)
        if bundle is not None and _status(bundle, today_ny, as_of)[0]:
            out.append(dict(bundle["plan"]))
    return out


def _bundle(plan_id: Any) -> dict[str, Any]:
    """The full bundle (all records, for ordering and numbering checks when writing)."""
    plan_id = _text("plan_id", plan_id)
    bundle = _group(_read_rows()).get(plan_id)
    if bundle is None:
        raise DecisionLogError(f"PLAN_NOT_FOUND: {plan_id} is not in trade_plans.jsonl")
    return bundle


def _current(bundle: dict[str, Any]) -> dict[str, Any]:
    plan = bundle["plan"]
    current = {"version": 1, "price_invalidation": plan["price_invalidation"], "hold_basis": plan["hold_basis"],
               "review_dates": plan["review_dates"], "abandon_facts": plan["abandon_facts"]}
    for revision in bundle["revisions"]:
        current.update(revision["changes"])
        current["version"] = revision["version"]
    return current


def _effective_for(bundle: dict[str, Any], replay_as_of: str | None, *, same_time_ok: bool = False
                   ) -> tuple[datetime, datetime]:
    """(decided_at, effective) for a follow-up record on an existing plan; replay-ness must match the plan.

    A write is refused when the plan already has any revision, review or choice effective after this effective
    time: in a replay that is the future, and the message says nothing about what the later records are.
    `same_time_ok` (choices only) lets the effective time equal the freeze time of the plan it refers to."""
    plan = bundle["plan"]
    decided_at, effective = _decision_times(replay_as_of)
    _check_session(plan, effective != decided_at)
    later = [_dt(r["effective_at"]) for r in bundle["revisions"]] \
        + [_dt(r["reviewed_at_effective"]) for r in bundle["reviews"]] + [_choice_time(c) for c in bundle["choices"]]
    if any(moment > effective for moment in later):
        raise DecisionLogError("HISTORY_WRITE_CONFLICT: this plan has records after the replay cutoff")
    if effective < _dt(plan["frozen_at"]) or (effective == _dt(plan["frozen_at"]) and not same_time_ok):
        raise DecisionLogError("EFFECTIVE_NOT_AFTER_FROZEN: the follow-up must be effective after the plan was frozen")
    return decided_at, effective


def _require_active(bundle: dict[str, Any], effective: datetime) -> None:
    active, reason = _status(bundle, effective.astimezone(NY).date(), effective)
    if not active:
        raise DecisionLogError(f"PLAN_NOT_ACTIVE: {bundle['plan']['plan_id']} is not in progress ({reason})")


def _read_report(record: dict[str, Any], rid: str) -> tuple[str | None, str]:
    """(text, integrity). The file is found under <data_dir>/plan-reports/*/<TICKER>-<id>.md, never by the stored path.
    integrity: ok (sha256 matches the frozen hash) | missing | mismatch (text withheld)."""
    base = (settings.data_dir() / "plan-reports").resolve()
    for path in sorted(base.glob(f"*/{record['ticker']}-{rid}.md")) if base.is_dir() else []:
        resolved = path.resolve()
        if resolved.parent.parent != base or not resolved.is_file():
            continue
        data = resolved.read_bytes()
        if hashlib.sha256(data).hexdigest() != record.get("report_sha256"):
            return None, "mismatch"
        return data.decode("utf-8"), "ok"
    return None, "missing"


# ---------------------------------------------------------------------------------------------- tools

def size_trade_plan(entry_ref: float, price_invalidation: float, risk_budget: float = 1000) -> dict[str, Any]:
    """Risk arithmetic for a plan: {"risk_per_share", "shares", "r0"} (read-only, writes nothing)."""
    from product.deterministic.plan_math import PlanMathError, size_position
    try:
        return size_position(entry_ref, price_invalidation, risk_budget)
    except PlanMathError as exc:
        raise DecisionLogError(str(exc)) from None


def save_plan_candidate(ticker: str, outcome: str, reason: str, replay_as_of: str | None = None,
                        host: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Record an opportunity that did not become a plan (outcome wait / not_formed) so the funnel stays complete."""
    ticker = _ticker(ticker)
    if outcome not in CANDIDATE_OUTCOMES:
        raise DecisionLogError(f"OUTCOME_INVALID: one of {CANDIDATE_OUTCOMES} (a plan is recorded by save_trade_plan)")
    reason = _text("reason", reason)
    created_at, effective = _decision_times(replay_as_of)
    record = {"kind": "candidate", "ticker": ticker, "outcome": outcome, "reason": reason, "plan_id": None,
              "created_at": iso_utc(created_at), "created_at_effective": iso_utc(effective),
              "replay": effective != created_at, "host": _opt_text(host), "model": _opt_text(model),
              "model_recorded": _model_recorded(model), "code_version": _code_version()}
    record["candidate_id"] = _hash_id(record)
    _append(record)
    return {"saved": True, "candidate_id": record["candidate_id"], "outcome": outcome,
            "created_at": record["created_at"], "created_at_effective": record["created_at_effective"],
            "replay": record["replay"], "plan_log": str(_log_path())}


def save_trade_plan(ticker: str, template: str, thesis: str, market_misread: str, catalyst: str,
                    abandon_facts: list[dict[str, str]], price_invalidation: float, entry_ref: float,
                    entry_band: list[float], hold_basis: str, review_dates: list[str], horizon_cap_days: int,
                    report_markdown: str, risk_budget: float = 1000, replay_as_of: str | None = None,
                    host: str | None = None, model: str | None = None, **extra: Any) -> dict[str, Any]:
    """Validate and freeze one plan/v1 record (plus its candidate row with outcome=plan). Returns the generated fields."""
    if extra:
        generated = sorted(set(extra) & set(GENERATED_FIELDS))
        if generated:
            raise DecisionLogError(f"GENERATED_FIELD_NOT_ACCEPTED: {generated} are written by the tool, never by "
                                   "the caller; remove them and save again")
        raise DecisionLogError(f"UNKNOWN_FIELDS: {sorted(extra)}")
    ticker = _ticker(ticker)
    if template not in TEMPLATES:
        raise DecisionLogError(f"TEMPLATE_INVALID: one of {TEMPLATES}")
    thesis = _text("thesis", thesis, single_line=True)
    market_misread = _text("market_misread", market_misread)
    catalyst = _text("catalyst", catalyst)
    hold_basis = _text("hold_basis", hold_basis)
    facts = _abandon_facts(abandon_facts)
    stop = _positive("price_invalidation", price_invalidation)
    ref = _positive("entry_ref", entry_ref)
    budget = _positive("risk_budget", risk_budget)
    if not isinstance(entry_band, (list, tuple)) or len(entry_band) != 2:
        raise DecisionLogError("ENTRY_BAND_INVALID: [lo, hi]")
    lo, hi = _positive("entry_band_lo", entry_band[0]), _positive("entry_band_hi", entry_band[1])
    if lo > hi:
        raise DecisionLogError("ENTRY_BAND_ORDER: lo must not exceed hi")
    if not lo <= ref <= hi:
        raise DecisionLogError("ENTRY_REF_OUTSIDE_BAND: need lo <= entry_ref <= hi")
    if stop >= lo:
        raise DecisionLogError("PRICE_INVALIDATION_NOT_BELOW_BAND: price_invalidation must be below the whole entry band")
    cap_days = _horizon(horizon_cap_days)
    report = _check_sections(report_markdown, PLAN_SECTIONS, "plan card")
    with _ledger_lock():
        return _save_trade_plan_locked(
            ticker, template, thesis, market_misread, catalyst, facts, stop, ref, budget, lo, hi, hold_basis,
            review_dates, cap_days, report, replay_as_of, host, model)


def _save_trade_plan_locked(ticker, template, thesis, market_misread, catalyst, facts, stop, ref, budget, lo, hi,
                            hold_basis, review_dates, cap_days, report, replay_as_of, host, model) -> dict[str, Any]:
    decided_at, effective = _decision_times(replay_as_of)
    today = effective.astimezone(NY).date()
    dates = _review_dates(review_dates, today)
    sizing = size_trade_plan(ref, stop, budget)
    replay = effective != decided_at
    live = active_plans(today, replay, as_of=effective)
    if any(p["ticker"] == ticker for p in live):
        raise DecisionLogError(f"ACTIVE_PLAN_EXISTS: {ticker} already has a plan in progress; review it to EXIT or "
                               "record choice=abandoned first")
    if len(live) >= MAX_ACTIVE:
        raise DecisionLogError(f"ACTIVE_PLAN_LIMIT: {len(live)} plans are in progress (max {MAX_ACTIVE}); finish or "
                               "abandon one first")
    report_text = report.rstrip() + "\n"
    stamp, effective_stamp = iso_utc(decided_at), iso_utc(effective)
    candidate_core = {"kind": "candidate", "ticker": ticker, "outcome": "plan", "reason": thesis,
                      "created_at": stamp, "created_at_effective": effective_stamp, "replay": replay}
    candidate_id = _hash_id(candidate_core)
    record = {
        "schema": SCHEMA, "kind": "plan", "ticker": ticker, "template": template, "thesis": thesis,
        "market_misread": market_misread, "catalyst": catalyst, "abandon_facts": facts,
        "price_invalidation": stop, "entry_ref": ref, "entry_band": [lo, hi], "risk_budget": budget,
        "hold_basis": hold_basis, "review_dates": dates, "horizon_cap_days": cap_days,
        "host": _opt_text(host), "model": _opt_text(model),
        # generated below this line
        "model_recorded": _model_recorded(model), "candidate_id": candidate_id, "decided_at": stamp,
        "frozen_at": effective_stamp, "replay": replay, "shares_planned": sizing["shares"], "r0": sizing["r0"],
        "fill_rule": FILL_RULE, "stop_rule": STOP_RULE, "cost_bps_per_side": COST_BPS_PER_SIDE,
        "code_version": _code_version(),
        "report_sha256": hashlib.sha256(report_text.encode("utf-8")).hexdigest(),
    }
    record["plan_id"] = _hash_id(record)
    report_path = _write_report(ticker, record["plan_id"], stamp, report_text)
    record["report_path"] = str(report_path)
    _append({**candidate_core, "candidate_id": candidate_id, "plan_id": record["plan_id"], "host": _opt_text(host),
             "model": _opt_text(model)}, record)
    return {"saved": True, "plan_id": record["plan_id"], "candidate_id": candidate_id, "frozen_at": effective_stamp,
            "replay": replay, "shares_planned": record["shares_planned"], "r0": record["r0"],
            "risk_per_share": sizing["risk_per_share"], "report_sha256": record["report_sha256"],
            "report_path": str(report_path), "plan_log": str(_log_path())}


def revise_trade_plan(plan_id: str, reason: str, sources: list[Any], changes: dict[str, Any],
                      replay_as_of: str | None = None) -> dict[str, Any]:
    """Append a revision after a new fact. Only price_invalidation, hold_basis, review_dates and abandon_facts can
    change; r0, shares_planned, entry_* and thesis never do. A later price_invalidation (even above cost) is allowed,
    since r0 stays the original budget."""
    if not isinstance(changes, dict) or not changes:
        raise DecisionLogError("CHANGES_REQUIRED: {price_invalidation?, hold_basis?, review_dates?, abandon_facts?}")
    forbidden = sorted(set(changes) - set(REVISABLE))
    if forbidden:
        raise DecisionLogError(f"REVISION_FIELD_NOT_ALLOWED: {forbidden}; only {list(REVISABLE)} can be revised "
                               "(r0, shares_planned, entry_ref, entry_band, thesis never change)")
    reason = _text("reason", reason)
    if not isinstance(sources, list) or not sources or any(
            not (isinstance(s, str) and s.strip()) and not (isinstance(s, dict) and str(s.get("source", "")).strip())
            for s in sources):
        raise DecisionLogError("SOURCES_REQUIRED: at least one source (text, or {source, ...})")
    with _ledger_lock():
        bundle = _bundle(plan_id)
        decided_at, effective = _effective_for(bundle, replay_as_of)
        _require_active(bundle, effective)
        previous = [_dt(r["effective_at"]) for r in bundle["revisions"]]
        if previous and effective <= max(previous):
            raise DecisionLogError("EFFECTIVE_NOT_AFTER_PREVIOUS: a revision must be effective after the previous revision")
        clean: dict[str, Any] = {}
        if "price_invalidation" in changes:
            clean["price_invalidation"] = _positive("price_invalidation", changes["price_invalidation"])
        if "hold_basis" in changes:
            clean["hold_basis"] = _text("hold_basis", changes["hold_basis"])
        if "review_dates" in changes:
            clean["review_dates"] = _review_dates(changes["review_dates"], effective.astimezone(NY).date())
        if "abandon_facts" in changes:
            clean["abandon_facts"] = _abandon_facts(changes["abandon_facts"])
        plan = bundle["plan"]
        record = {"kind": "revision", "plan_id": plan["plan_id"], "ticker": plan["ticker"],
                  "version": len(bundle["revisions"]) + 2, "reason": reason,
                  "sources": [s.strip() if isinstance(s, str) else s for s in sources], "changes": clean,
                  "effective_at": iso_utc(effective), "recorded_at": iso_utc(decided_at),
                  "replay": effective != decided_at}
        _append(record)
    merged = _current({**bundle, "revisions": bundle["revisions"] + [record]})
    return {"saved": True, "plan_id": plan["plan_id"], "version": record["version"],
            "effective_at": record["effective_at"], "replay": record["replay"], "current": merged,
            "r0": plan["r0"], "shares_planned": plan["shares_planned"]}


def save_plan_review(plan_id: str, thesis_verdict: str, evidence: list[dict[str, str]], action: str,
                     action_reason: str, report_markdown: str, plan_deviation: bool = False,
                     deviation_reason: str | None = None, replay_as_of: str | None = None,
                     host: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Append one review. A changed thesis_verdict needs at least one non-price evidence item published after the
    previous review (or the plan freeze). REDUCE sells half the remaining shares (floor, at least 1); EXIT sells all."""
    if thesis_verdict not in VERDICTS:
        raise DecisionLogError(f"THESIS_VERDICT_INVALID: one of {VERDICTS}")
    if action not in ACTIONS:
        raise DecisionLogError(f"ACTION_INVALID: one of {ACTIONS}")
    action_reason = _text("action_reason", action_reason)
    if not isinstance(plan_deviation, bool):
        raise DecisionLogError("PLAN_DEVIATION_INVALID: true or false")
    if plan_deviation:
        deviation_reason = _text("deviation_reason", deviation_reason)
    elif deviation_reason is not None:
        raise DecisionLogError("DEVIATION_REASON_NOT_ALLOWED: set plan_deviation=true to give a deviation_reason")
    report = _check_sections(report_markdown, REVIEW_SECTIONS, "review report")
    with _ledger_lock():
        bundle = _bundle(plan_id)
        plan = bundle["plan"]
        decided_at, effective = _effective_for(bundle, replay_as_of)
        _require_active(bundle, effective)
        items, times = _evidence(evidence, effective)
        previous = bundle["reviews"][-1] if bundle["reviews"] else None
        if previous is not None and effective <= _dt(previous["reviewed_at_effective"]):
            raise DecisionLogError("EFFECTIVE_NOT_AFTER_PREVIOUS: a review must be effective after the previous review")
        prior_verdict = previous["thesis_verdict"] if previous else "unchanged"
        prior_time = _dt(previous["reviewed_at_effective"]) if previous else _dt(plan["frozen_at"])
        if thesis_verdict != prior_verdict and not any(kind != "price" and t > prior_time for kind, t in times):
            raise DecisionLogError(
                f"NEW_EVIDENCE_REQUIRED: the verdict changes from {prior_verdict} to {thesis_verdict}, so at least one "
                f"non-price evidence item (filing, news or other) must be published after {iso_utc(prior_time)}; a "
                "price move does not change the thesis conclusion (handle price in the action)")
        report_text = report.rstrip() + "\n"
        stamp, effective_stamp = iso_utc(decided_at), iso_utc(effective)
        record = {
            "kind": "review", "plan_id": plan["plan_id"], "ticker": plan["ticker"], "thesis_verdict": thesis_verdict,
            "evidence": items, "action": action, "action_reason": action_reason, "plan_deviation": plan_deviation,
            "deviation_reason": deviation_reason, "host": _opt_text(host), "model": _opt_text(model),
            "model_recorded": _model_recorded(model), "reviewed_at": stamp, "reviewed_at_effective": effective_stamp,
            "replay": effective != decided_at, "code_version": _code_version(),
            "report_sha256": hashlib.sha256(report_text.encode("utf-8")).hexdigest(),
        }
        record["review_id"] = _hash_id(record)
        report_path = _write_report(plan["ticker"], record["review_id"], stamp, report_text)
        record["report_path"] = str(report_path)
        _append(record)
    return {"saved": True, "review_id": record["review_id"], "plan_id": plan["plan_id"],
            "reviewed_at_effective": effective_stamp, "replay": record["replay"], "action": action,
            "thesis_verdict": thesis_verdict, "report_sha256": record["report_sha256"],
            "report_path": str(report_path), "plan_log": str(_log_path())}


def record_plan_choice(plan_id: str, ref_id: str, choice: str, note: str) -> dict[str, Any]:
    """Record what the user did with a plan or one review (ref_id = plan_id or review_id). Effective like a review: now in
    a live session, 23:59:59 New York on the replay date in a replay session (STOCK_AGENT_REPLAY_AS_OF); the session
    must match the plan (PLAN_REPLAY_MISMATCH)."""
    if choice not in CHOICES:
        raise DecisionLogError(f"CHOICE_INVALID: one of {CHOICES}")
    ref_id = _text("ref_id", ref_id)
    if not isinstance(note, str) or (choice != "followed" and not note.strip()):
        raise DecisionLogError("NOTE_REQUIRED: say why (a note is optional only for choice=followed)")
    with _ledger_lock():
        bundle = _bundle(plan_id)
        plan = bundle["plan"]
        recorded_at, effective = _effective_for(bundle, None, same_time_ok=True)
        visible = {r["review_id"] for r in bundle["reviews"] if _dt(r["reviewed_at_effective"]) <= effective}
        if ref_id != plan["plan_id"] and ref_id not in visible:
            raise DecisionLogError(f"REF_ID_NOT_FOUND: {ref_id} is neither this plan_id nor one of its review_ids")
        if choice == "abandoned":
            if any(r["action"] == "EXIT" and _dt(r["reviewed_at_effective"]) <= effective for r in bundle["reviews"]):
                raise DecisionLogError("ABANDON_AFTER_EXIT: the plan already has an EXIT review, so it is finished; "
                                       "abandoned is only for a plan without one")
            if any(c["choice"] == "abandoned" and _choice_time(c) <= effective for c in bundle["choices"]):
                raise DecisionLogError("ALREADY_ABANDONED: this plan was already recorded as abandoned")
        record = {"kind": "choice", "plan_id": plan["plan_id"], "ticker": plan["ticker"], "ref_id": ref_id,
                  "choice": choice, "note": note.strip(), "recorded_at": iso_utc(recorded_at),
                  "effective_at": iso_utc(effective), "replay": bool(plan.get("replay"))}
        _append(record)
    return {"saved": True, "plan_id": plan["plan_id"], "ref_id": ref_id, "choice": choice,
            "recorded_at": record["recorded_at"], "effective_at": record["effective_at"]}


def _thesis_view(plan: dict[str, Any], bundle: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Step one of a review: the original operating thesis and non-price facts only. No report text, no price fields
    (entry, price_invalidation, r0, shares), no action or action_reason."""
    keys = ("thesis", "market_misread", "catalyst", "abandon_facts", "hold_basis", "review_dates", "frozen_at")
    return {"found": True, "plan_id": plan["plan_id"], "view": "thesis", "ticker": plan["ticker"],
            "plan": {k: plan[k] for k in keys}, "cap_date": _cap_date(plan).isoformat(),
            "current": {k: current[k] for k in ("version", "hold_basis", "review_dates", "abandon_facts")},
            "reviews": [{"review_id": r["review_id"], "thesis_verdict": r["thesis_verdict"],
                         "reviewed_at_effective": r["reviewed_at_effective"],
                         "evidence": [e for e in r["evidence"] if e.get("kind") != "price"]}
                        for r in bundle["reviews"]]}


def get_trade_plan(plan_id: str, view: str = "full") -> dict[str, Any]:
    """One plan as of the session cutoff. view=full: the frozen plan, its version chain, the current version, reviews,
    choices and the report (with report_integrity). view=thesis: operating thesis and non-price evidence only."""
    plan_id = _text("plan_id", plan_id)
    if view not in VIEWS:
        raise DecisionLogError(f"VIEW_INVALID: one of {VIEWS}")
    replay_session, today, cutoff = _session()
    raw = _group(_read_rows()).get(plan_id)
    if raw is None:
        return {"found": False, "plan_id": plan_id}
    _check_session(raw["plan"], replay_session)
    bundle = _cut(raw, cutoff)
    if bundle is None:
        return {"found": False, "plan_id": plan_id}  # frozen after the cutoff: does not exist yet
    plan, current = bundle["plan"], _current(bundle)
    if view == "thesis":
        return _thesis_view(plan, bundle, current)
    active, reason = _status(bundle, today, cutoff)
    report, integrity = _read_report(plan, plan["plan_id"])
    return {"found": True, "plan_id": plan_id, "plan": plan, "revisions": bundle["revisions"], "current": current,
            "reviews": bundle["reviews"], "choices": bundle["choices"], "active": active, "active_reason": reason,
            "cap_date": _cap_date(plan).isoformat(), "report_markdown": report, "report_integrity": integrity}


def list_trade_plans(ticker: str | None = None, active_only: bool = True) -> dict[str, Any]:
    """Plan summaries (no report text) as of the session cutoff. A replay session lists replay plans only; otherwise
    only live plans. `active_count` counts every in-progress plan of that kind, whatever the ticker filter."""
    wanted = _ticker(ticker) if ticker else None
    replay_session, today, cutoff = _session()
    plans, active_count = [], 0
    for raw in _group(_read_rows()).values():
        if bool(raw["plan"].get("replay")) != replay_session:
            continue
        bundle = _cut(raw, cutoff)
        if bundle is None:
            continue
        plan = bundle["plan"]
        active, reason = _status(bundle, today, cutoff)
        active_count += active
        if (wanted and plan["ticker"] != wanted) or (active_only and not active):
            continue
        current, last = _current(bundle), (bundle["reviews"][-1] if bundle["reviews"] else None)
        plans.append({"plan_id": plan["plan_id"], "ticker": plan["ticker"], "thesis": plan["thesis"],
                      "frozen_at": plan["frozen_at"], "replay": bool(plan.get("replay")),
                      "shares_planned": plan["shares_planned"], "r0": plan["r0"],
                      "entry_band": plan["entry_band"], "horizon_cap_days": plan["horizon_cap_days"],
                      "cap_date": _cap_date(plan).isoformat(), "version": current["version"],
                      "price_invalidation": current["price_invalidation"], "review_count": len(bundle["reviews"]),
                      "last_review": ({"review_id": last["review_id"], "action": last["action"],
                                       "thesis_verdict": last["thesis_verdict"],
                                       "reviewed_at_effective": last["reviewed_at_effective"]} if last else None),
                      "choices": [c["choice"] for c in bundle["choices"]], "active": active,
                      "active_reason": reason, "report_path": plan.get("report_path")})
    return {"plans": plans, "count": len(plans), "active_count": active_count, "active_max": MAX_ACTIVE}
