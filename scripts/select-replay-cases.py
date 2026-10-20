"""为历史回放挑选样本：起始日之后 N 个交易日相对 SPY 的超额收益，取赢家、输家与随机对照。

用法：.venv/bin/python -I scripts/select-replay-cases.py 2024-01-02 [--horizon 252] [--n 3] [--seed 0]
输出：evals/replay/cases/<起始日>.json（分组只用于事后复盘，回放研究时不能告诉模型）。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.mcp import calc_tools  # noqa: E402


def universe() -> list[str]:
    text = (REPO / "evals/replay/universe.txt").read_text()
    return list(dict.fromkeys(t for line in text.splitlines() if not line.startswith("#") for t in line.split()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("start")
    parser.add_argument("--horizon", type=int, default=252)
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rows, skipped = [], {}
    for ticker in universe():
        try:
            result = calc_tools.forward_returns(ticker, [args.start], horizons_days=[args.horizon])
            row = result["rows"][0] if result.get("rows") else None
            excess = row and row.get(f"excess_{args.horizon}d_pct")
            if excess is None:
                skipped[ticker] = "horizon not complete or no price"
                continue
            rows.append({"ticker": ticker, "base_date": row["base_date"],
                         "return_pct": float(row[f"ret_{args.horizon}d_pct"]), "excess_pct": float(excess)})
        except Exception as exc:  # noqa: BLE001 - record and continue
            skipped[ticker] = f"{type(exc).__name__}: {exc}"

    rows.sort(key=lambda r: r["excess_pct"], reverse=True)
    n = args.n
    winners, losers = rows[:n], rows[-n:]
    middle = rows[n:-n]
    controls = random.Random(f"{args.start}:{args.seed}").sample(middle, min(n, len(middle)))
    out = {
        "start": args.start, "horizon_days": args.horizon, "benchmark": "SPY", "seed": args.seed,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe_size": len(rows), "skipped": skipped,
        "limitations": ["幸存者偏差：候选池按 2026-10 的认知挑选。", "超额收益为复权价总回报减 SPY 总回报。"],
        "groups": {"winner": winners, "loser": losers, "control": controls},
        "all_ranked": rows,
    }
    path = REPO / "evals/replay/cases" / f"{args.start}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(path)
    for group, items in out["groups"].items():
        print(group, [(r["ticker"], r["excess_pct"]) for r in items])


if __name__ == "__main__":
    main()
