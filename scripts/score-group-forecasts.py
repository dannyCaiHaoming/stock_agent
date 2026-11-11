"""组内方向预测评分：预测的排序能否区分同组里之后的强弱（确定性计算，不做判断）。

用法：
  .venv/bin/python -I scripts/score-group-forecasts.py <运行目录或通配符> ... [--out 文件.md]
      读每个运行目录的 group_forecasts.jsonl（direction-forecast Skill 的产物，取最后一条）。
  .venv/bin/python -I scripts/score-group-forecasts.py <运行目录...> --decisions evals/replay/sectors-2026h1.json
      读完整研究的 decisions.jsonl，按 JSON 里的分组归组；分数 = relative_return_60d（没有则 126d）
      的方向概率（跑输取 1 − p）。

口径（固定）：
  结果 = 截止日之后 20 / 60 个交易日的总收益（forward_returns，复权收盘价），与同组同日的中位数比较。
  排序能力 = 把分数与结果都减去组内均值后，合并所有组计算秩相关（“组内秩相关”）；另按日期分别列出。
  命中 = 分数 > 0.5 的股票结果高于组内中位数，或分数 < 0.5 的低于中位数（分数恰为 0.5 不计）。
  对照 = 同样的计算换成“之前 60 日涨幅”“之前 126 日涨幅”。预测要超过这两个对照才算有信息。
  同一天同一组的股票高度相关：一个（日期 × 组）只算一个观测，秩相关的误差按观测数而不是股票数理解。
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.mcp import calc_tools, data_tools  # noqa: E402

HORIZONS = (20, 60)
FEATURES = (("score", "预测"), ("m60", "之前 60 日涨幅"), ("m126", "之前 126 日涨幅"))


def rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out, i = [0.0] * len(values), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2
        i = j + 1
    return out


def spearman(a: list, b: list) -> float | None:
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pairs) < 5 or len({x for x, _ in pairs}) < 2 or len({y for _, y in pairs}) < 2:
        return None
    xs, ys = zip(*pairs)
    return round(st.correlation(rank(list(xs)), rank(list(ys))), 2)


def run_dirs(patterns: list[str]) -> list[Path]:
    out = []
    for pattern in patterns:
        out += [Path(p) for p in sorted(glob.glob(pattern))] or [Path(pattern)]
    return [p for p in out if p.is_dir()]


def last_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return json.loads(lines[-1]) if lines else None


def load(patterns: list[str], groups_file: str | None) -> list[dict]:
    """Rows of {date, group, ticker, score}; a later run for the same (date, group, ticker) replaces an earlier one."""
    rows: dict[tuple, dict] = {}
    sector = {}
    if groups_file:
        sector = {t: g for g, ts in json.loads(Path(groups_file).read_text()).items() if isinstance(ts, list) for t in ts}
    for run in run_dirs(patterns):
        if groups_file:
            d = last_json(run / "decisions.jsonl")
            if not d or d["ticker"] not in sector:
                continue
            f = {x["target"]: x for x in d.get("forecasts") or []}
            x = f.get("relative_return_60d") or f.get("relative_return_126d")
            if not x:
                continue
            p = float(x["probability"])
            rows[(d["data_as_of"], sector[d["ticker"]], d["ticker"])] = {
                "score": p if x["direction"] == "outperform" else 1 - p, "action": d["action"]}
        else:
            g = last_json(run / "group_forecasts.jsonl")
            if not g:
                continue
            for x in g["forecasts"]:
                rows[(g["data_as_of"], g["group"], x["ticker"])] = {"score": float(x["probability"])}
    return [{"date": k[0], "group": k[1], "ticker": k[2], **v} for k, v in sorted(rows.items())]


def add_prices(rows: list[dict]) -> None:
    for r in rows:
        try:
            fr = calc_tools.forward_returns(r["ticker"], [r["date"]], list(HORIZONS))["rows"][0]
            start = str(int(r["date"][:4]) - 1) + r["date"][4:]
            closes = [float(x[5]) for x in data_tools.get_price_history(r["ticker"], start=start, end=r["date"],
                                                                        as_of=r["date"], max_rows=400)["rows"]]
        except Exception as exc:  # noqa: BLE001 - one ticker failing must not stop the scoring
            print(f"WARN {r['ticker']} {r['date']}: {type(exc).__name__}: {exc}", file=sys.stderr)
            fr, closes = {}, []
        for h in HORIZONS:
            v = fr.get(f"ret_{h}d_pct")
            r[f"r{h}"] = float(v) if v is not None else None
        for n in (60, 126):
            r[f"m{n}"] = (closes[-1] / closes[-1 - n] - 1) * 100 if len(closes) > n else None


def demeaned(rows: list[dict], key: str) -> list:
    cells: dict[tuple, list[float]] = {}
    for r in rows:
        if r.get(key) is not None:
            cells.setdefault((r["date"], r["group"]), []).append(r[key])
    return [None if r.get(key) is None else r[key] - st.mean(cells[(r["date"], r["group"])]) for r in rows]


def hits(rows: list[dict], key: str, h: int) -> tuple[int, int]:
    """Calls above/below the cell's own median of `key` vs outcome above/below the cell median return."""
    cells: dict[tuple, list[dict]] = {}
    for r in rows:
        if r.get(key) is not None and r.get(f"r{h}") is not None:
            cells.setdefault((r["date"], r["group"]), []).append(r)
    hit = total = 0
    for cell in cells.values():
        if len(cell) < 4:
            continue
        mid_r = st.median(x[f"r{h}"] for x in cell)
        mid_k = 0.5 if key == "score" else st.median(x[key] for x in cell)
        for x in cell:
            if x[key] == mid_k or x[f"r{h}"] == mid_r:
                continue
            total += 1
            hit += (x[key] > mid_k) == (x[f"r{h}"] > mid_r)
    return hit, total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--decisions", metavar="GROUPS.json")
    parser.add_argument("--out")
    args = parser.parse_args()
    rows = load(args.inputs, args.decisions)
    if not rows:
        sys.exit("no forecasts found")
    add_prices(rows)
    dates = sorted({r["date"] for r in rows})
    cells = sorted({(r["date"], r["group"]) for r in rows})
    lines = ["# 组内方向预测评分", "",
             f"{len(rows)} 个预测，{len(dates)} 个日期，{len(cells)} 个（日期 × 组）。口径见 `scripts/score-group-forecasts.py` 文件头。", ""]
    for h in HORIZONS:
        scored = [r for r in rows if r.get(f"r{h}") is not None]
        if not scored:
            lines += [f"## 之后 {h} 日：结果尚未到期", ""]
            continue
        lines += [f"## 之后 {h} 日（已到期 {len(scored)} 个）", "",
                  "| | " + " | ".join(name for _, name in FEATURES) + " |", "|---|" + "---|" * len(FEATURES)]
        y = demeaned(scored, f"r{h}")
        lines.append("| 组内秩相关（全部合并） | " + " | ".join(str(spearman(demeaned(scored, k), y)) for k, _ in FEATURES) + " |")
        lines.append("| 命中 / 总数 | " + " | ".join("{}/{}".format(*hits(scored, k, h)) for k, _ in FEATURES) + " |")
        for d in dates:
            part = [r for r in scored if r["date"] == d]
            if part:
                yd = demeaned(part, f"r{h}")
                lines.append(f"| {d}（n={len(part)}） | " + " | ".join(str(spearman(demeaned(part, k), yd)) for k, _ in FEATURES) + " |")
        per_cell = []
        for c in cells:
            part = [r for r in scored if (r["date"], r["group"]) == c]
            v = spearman([r["score"] for r in part], [r[f"r{h}"] for r in part])
            if v is not None:
                per_cell.append(v)
        if per_cell:
            lines += ["", f"逐个（日期 × 组）的预测秩相关：{len(per_cell)} 个可算，均值 {round(st.mean(per_cell), 2)}，"
                          f"为正 {sum(v > 0 for v in per_cell)}/{len(per_cell)}。"]
        lines.append("")
    lines += ["## 明细", "", "| 日期 | 组 | 股票 | 预测 | 之前 60 日 | 之后 20 日 | 之后 60 日 |", "|---|---|---|---|---|---|---|"]
    fmt = lambda v: "—" if v is None else f"{v:+.1f}"  # noqa: E731
    for r in rows:
        lines.append(f"| {r['date']} | {r['group']} | {r['ticker']} | {r['score']:.2f} | {fmt(r['m60'])} | {fmt(r['r20'])} | {fmt(r['r60'])} |")
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        Path(args.out).with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
