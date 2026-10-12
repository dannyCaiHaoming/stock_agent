"""从冻结日线复用现有技术/市场数学，不生成研究判断。"""
from __future__ import annotations
import copy
from typing import Any, Mapping, Sequence

from product.runtime.hashing import canonical_hash
from product.deterministic.market_analysis import (
    calculate_technical_statistics, calculate_market_state_statistics, calculate_market_breadth,
)

class PrecomputedResearchError(ValueError):
    pass

MultidimensionalStageError = PrecomputedResearchError

def _technical_rows(
    evidence: Sequence[Mapping[str, Any]], *, security_id: str,
) -> list[dict[str, Any]]:
    """把冻结的字段事实还原为确定性计算所需的逐交易日行。"""

    by_date: dict[str, dict[str, Any]] = {}
    field_map = {
        "historical_close_price": "close",
        "adjusted_close_price": "adjusted_close",
        "share_volume": "volume",
        "stock_split_ratio": "stock_split",
    }
    for fact in evidence:
        if fact.get("security_id") != security_id:
            continue
        target = field_map.get(str(fact.get("semantic_field", "")))
        if target is None:
            continue
        metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
        day = metadata.get("trading_date")
        if not isinstance(day, str):
            as_of = fact.get("as_of")
            day = str(as_of)[:10] if isinstance(as_of, str) and len(as_of) >= 10 else None
        if not isinstance(day, str):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_TECHNICAL_DATE_MISSING")
        row = by_date.setdefault(
            day,
            {
                "date": day,
                "close": None,
                "adjusted_close": None,
                "volume": None,
                "stock_split": 0,
                "evidence_ids": [],
            },
        )
        if row[target] not in {None, 0}:
            raise MultidimensionalStageError(
                f"MULTIDIMENSIONAL_TECHNICAL_FIELD_DUPLICATE:{security_id}:{day}:{target}"
            )
        row[target] = fact.get("value")
        row["evidence_ids"].append(str(fact["evidence_id"]))
    return [
        row for _, row in sorted(by_date.items())
        if row["close"] is not None
    ]

def prepare_statistics(gate, *, capability, security_id, benchmark_id):
    if capability not in {"TECHNICAL_STRUCTURE", "MARKET_STATE"}:
        return []
    facts = gate["allowed_evidence"]
    artifacts = []
    if benchmark_id:
        benchmark = _technical_rows(facts, security_id=benchmark_id)
        if capability == "TECHNICAL_STRUCTURE":
            rows = _technical_rows(facts, security_id=security_id)
            if rows and benchmark:
                artifacts.append(calculate_technical_statistics(rows, benchmark,
                    security_id=security_id, benchmark_id=benchmark_id, as_of=gate["decision_cutoff"]))
        elif benchmark:
            artifacts.append(calculate_market_state_statistics(benchmark,
                market_id=benchmark_id, as_of=gate["decision_cutoff"]))
    if capability == "MARKET_STATE":
        candidates = [fact for fact in facts if fact.get("security_id") == "US:MARKET"
                      and fact.get("semantic_field") == "moomoo_us_rise_fall_distribution"]
        if candidates:
            fact = max(candidates, key=lambda f: (f["as_of"], f["retrieved_at"], f["evidence_id"]))
            artifacts.append(calculate_market_breadth(fact))
    return artifacts


def statistics_catalog(task, *, root=None):
    result = {}
    for artifact in task.get("precomputed", []):
        if root is not None:
            from product.tools.research import _read_json
            if _read_json(root / "precomputed" / (artifact["artifact_hash"] + ".json")) != artifact:
                raise ValueError("NATIVE_RESEARCH_PRECOMPUTED_FILE_DRIFT")
        if artifact.get("artifact_hash") != canonical_hash({k:v for k,v in artifact.items() if k!="artifact_hash"}):
            raise ValueError("NATIVE_RESEARCH_PRECOMPUTED_HASH_INVALID")
        values = []
        for window in artifact.get("windows", []):
            if window["status"] == "COMPLETE":
                for metric, value in window["metrics"].items():
                    unit = "ratio" if metric not in {"window_high", "window_low", "average_volume"} else None
                    values.append((f"{window['window_sessions']}_sessions/{metric}", value, unit))
        for metric, value in artifact.get("counts", {}).items():
            values.append(("counts/"+metric, str(value), artifact["unit"]))
        for path, value, unit in values:
            binding = {"task_hash":task["task_hash"],"artifact_hash":artifact["artifact_hash"],"result_path":path}
            digest = canonical_hash(binding)
            ref = f"k.{task['task_hash'][:12]}.{digest[:24]}"
            result[ref] = {"calculation_ref":ref,"receipt_hash":artifact["artifact_hash"],
                "calculation":{"calculation_id":"calculation-"+digest[:24],
                    "method":artifact["schema_version"]+":"+path,"value":value,"unit":unit,
                    "input_evidence_refs":copy.deepcopy(artifact["evidence_fact_ids"]),
                    "artifact_ref":"precomputed/"+artifact["artifact_hash"]+".json"}}
    return result
