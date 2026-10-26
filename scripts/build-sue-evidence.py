"""逐事件点时 GAAP 季度 EPS 证据链（供 H1/SUE 检验使用，本脚本不计算 SUE 或任何收益统计）。

流水线（程序 → LLM 确认 → 程序校验）：
  events   事件表：events-8k.jsonl 的全部 8k_item_2.02 + 同批 ticker 的 2017-01-01..2018-12-31 业绩 8-K（Item 2.02）
  fetch    每个 8-K 的 EX-99.x（经 SecClient：缓存、<=2 请求/秒、SEC_USER_AGENT 取自 .mcp.json）
  extract  从 HTML 表格抽候选行（表号、行号、标签、数值列、表头）
  llm      Claude Haiku（本机 claude CLI，无工具）只做确认：是否 GAAP、哪一列是当季三个月、哪一列是去年同季、是否完整业绩公告
  verify   程序核对：LLM 给出的列索引取出的数值必须与其回显一致且为表格单元格；期间日期必须出现在公告文本中
  report   去重（每个财季保留第一份完整业绩公告）、XBRL 仅核对、覆盖率报告

用法：.venv/bin/python -I scripts/build-sue-evidence.py --stage all [--pilot 40] [--limit-tickers N]
来源规则：EPS 只来自该事件信号时点之前公开的 8-K 业绩公告附件本身；XBRL 只用于核对；缺失就是缺失。
产物：.local/cache/derived/sue/{events.jsonl,eps-evidence.jsonl,eps-excluded.jsonl,html/,llm/}，报告 .local/runs/sue-build/。
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import datetime as D
import gzip
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

from product.mcp import data_tools as dt  # noqa: E402
from product.mcp import settings  # noqa: E402
from product.mcp.live.attachments import _Rows  # noqa: E402
from product.mcp.live.sec_client import SecClient  # noqa: E402

SUE = settings.cache().root / "derived" / "sue"
RUN = REPO / ".local" / "runs" / "sue-build"
EVENTS_8K = settings.cache().root / "derived" / "signals" / "events-8k.jsonl"
for p in (SUE, SUE / "html", SUE / "llm", SUE / "docs", RUN, RUN / "llmcwd"):
    p.mkdir(parents=True, exist_ok=True)

PROMPT_VERSION = "v1"
MODEL = "claude-haiku-5-5"
LOCK = threading.Lock()


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- events
def stage_events(limit_tickers: int | None) -> list[dict]:
    old = collections.defaultdict(list)
    bench: dict[str, str] = {}
    for line in EVENTS_8K.open():
        if '"8k_item_2.02"' not in line[:40]:
            continue
        e = json.loads(line)
        old[e["ticker"]].append(e)
        bench[e["ticker"]] = e.get("benchmark")
    tickers = sorted(old)[:limit_tickers] if limit_tickers else sorted(old)
    client = SecClient(settings.cache(), user_agent=settings.sec_user_agent(), request_budget=10**6)
    cutoff = dt._cutoff(None)
    out = []
    for k, t in enumerate(tickers):
        have = {e["detail"]["accession"] for e in old[t]}
        for e in old[t]:
            out.append(dict(ticker=t, accession=e["detail"]["accession"], accepted_ny=e["detail"]["accepted_ny"],
                            signal_date=e["signal_date"], benchmark=bench[t], items=e["detail"].get("items"),
                            source="events-8k"))
        try:
            ident = dt.resolve_company(t)
            filings, _ = dt._submissions(ident, client, cutoff, history_years=10)
        except Exception as exc:  # noqa: BLE001
            log("submissions error", t, str(exc)[:100])
            continue
        n_new = 0
        for f in filings.values():
            if f["form"] not in ("8-K", "8-K/A") or "2.02" not in (f.get("items") or []):
                continue
            pub = f["published_at"][:10]
            if not ("2017-01-01" <= pub <= "2018-12-31") or f["accession"] in have:
                continue
            acc = dt.parse_timestamp(f["published_at"]).astimezone(dt.NEW_YORK)
            out.append(dict(ticker=t, accession=f["accession"], accepted_ny=acc.strftime("%Y-%m-%dT%H:%M"),
                            signal_date=acc.strftime("%Y-%m-%d"), benchmark=bench[t], items=f.get("items"),
                            source="history-2017-18"))
            n_new += 1
        log(f"events {k+1}/{len(tickers)} {t}: old={len(old[t])} new_2017_18={n_new}")
    out.sort(key=lambda e: (e["ticker"], e["accepted_ny"]))
    with (SUE / "events.jsonl").open("w") as fh:
        for e in out:
            fh.write(json.dumps(e) + "\n")
    return out


def load_events() -> list[dict]:
    return [json.loads(l) for l in (SUE / "events.jsonl").open()]


# ---------------------------------------------------------------- fetch
def _read_gz(p: Path) -> str:
    return gzip.decompress(p.read_bytes()).decode("utf-8")


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("windows-1252", "replace")


class _Limiter:
    """Global cap across all fetch threads: one request per MIN_GAP seconds in total (<= ~3.3 req/s, SEC fair access is 10/s)."""
    MIN_GAP = 0.3

    def __init__(self):
        self.lock, self.last = threading.Lock(), 0.0

    def wait(self):
        with self.lock:
            d = time.monotonic() - self.last
            if d < self.MIN_GAP:
                time.sleep(self.MIN_GAP - d)
            self.last = time.monotonic()


LIMITER = _Limiter()


def _limited_get(url, user_agent):
    from product.mcp.live.sec_client import http_get
    LIMITER.wait()
    return http_get(url, user_agent)


class Fetcher:
    def __init__(self):
        self.client = SecClient(settings.cache(), user_agent=settings.sec_user_agent(), request_budget=10**7, transport=_limited_get)
        self.cutoff = dt._cutoff(None)
        self.filings: dict[str, dict] = {}
        self.cur = None

    def filing(self, ticker: str, accession: str) -> dict | None:
        if self.cur != ticker:
            ident = dt.resolve_company(ticker)
            self.filings, _ = dt._submissions(ident, self.client, self.cutoff, history_years=10)
            self.cur = ticker
        return self.filings.get(accession)

    def fetch_event(self, ev: dict) -> dict:
        """Write docs/<acc>.json and html/<acc>.<n>.htm.gz; errors are not persisted (retried next run)."""
        acc = ev["accession"]
        meta_p = SUE / "docs" / f"{acc}.json"
        if meta_p.exists():
            return json.loads(meta_p.read_text())
        f = self.filing(ev["ticker"], acc)
        if not f:
            raise RuntimeError("accession_not_in_submissions")
        prefix = f["document_url"].rsplit("/", 1)[0]
        idx = self.client.read_document(dict(f, document_url=f"{prefix}/{f['accession']}-index.html"), max_age_seconds=365 * 86400)
        p = _Rows()
        p.feed(self.client.cache.read(idx["cache_record"]).decode("utf-8", "replace"))
        p.close()
        docs = [dict(seq=c[0], desc=c[1], name=l[0].rsplit("/", 1)[-1], type=c[3])
                for c, l in p.rows if len(c) == 5 and c[0] != "Seq" and l]
        ex = [d for d in docs if d["type"].upper().startswith("EX-99")]
        ex.sort(key=lambda d: (d["type"].upper() != "EX-99.1", d["type"], d["name"]))
        rec = dict(accession=acc, docs=docs, exhibits=[], index_url=f"{prefix}/{f['accession']}-index.html", prefix=prefix)
        for d in ex[:3]:
            if not dt.DOCUMENT_NAME.fullmatch(d["name"]):
                continue
            r = self.client.read_document(dict(f, document_url=f"{prefix}/{d['name']}"), max_age_seconds=365 * 86400)
            html = _decode(self.client.cache.read(r["cache_record"]))
            n = len(rec["exhibits"])
            (SUE / "html" / f"{acc}.{n}.htm.gz").write_bytes(gzip.compress(html.encode("utf-8")))
            rec["exhibits"].append(dict(n=n, type=d["type"], name=d["name"], url=f"{prefix}/{d['name']}"))
            if has_eps_candidates(html):
                break  # this exhibit already carries an EPS table; skip the others
        meta_p.write_text(json.dumps(rec))
        return rec


def stage_fetch(events: list[dict], workers: int = 8) -> None:
    todo = [e for e in events if not (SUE / "docs" / f"{e['accession']}.json").exists()]
    log(f"fetch: {len(todo)} of {len(events)} events to fetch")
    errs, done = collections.Counter(), [0]
    by = collections.defaultdict(list)
    for e in todo:
        by[e["ticker"]].append(e)

    def work(evs):
        fx = Fetcher()  # one SecClient per thread; all share LIMITER
        for ev in evs:
            try:
                fx.fetch_event(ev)
            except Exception as exc:  # noqa: BLE001
                with LOCK:
                    errs[str(exc)[:60]] += 1
                log("fetch error", ev["ticker"], ev["accession"], str(exc)[:100])
            with LOCK:
                done[0] += 1
                if done[0] % 50 == 0:
                    log(f"fetch {done[0]}/{len(todo)} errors={sum(errs.values())}")
    with cf.ThreadPoolExecutor(workers) as ex:
        for f in cf.as_completed([ex.submit(work, v) for v in by.values()]):
            f.result()
    log("fetch done; errors:", dict(errs))


# ---------------------------------------------------------------- html tables
class Tables(HTMLParser):
    def __init__(s):
        super().__init__()
        s.tables, s.stack, s.cell, s.row, s.text = [], [], None, None, []

    def handle_starttag(s, t, a):
        if t == "table":
            s.stack.append([])
        elif t == "tr" and s.stack:
            s.row = []
        elif t in ("td", "th") and s.stack:
            s.cell = []
        elif t in ("br", "p", "div"):
            s.text.append(" ")

    def handle_endtag(s, t):
        if t in ("td", "th") and s.stack and s.cell is not None and s.row is not None:
            s.row.append(re.sub(r"\s+", " ", "".join(s.cell).replace("\xa0", " ")).strip())
            s.cell = None
        elif t == "tr" and s.stack and s.row is not None:
            s.stack[-1].append(s.row)
            s.row = None
        elif t == "table" and s.stack:
            s.tables.append(s.stack.pop())

    def handle_data(s, d):
        if s.cell is not None:
            s.cell.append(d)
        s.text.append(d)


def tonum(c: str):
    c = c.replace("$", "").replace(" ", "").replace("\xa0", "")
    if c in ("", "—", "-", "–", "—)", "(", ")"):
        return None
    neg = c.startswith("(") or c.startswith("-") or c.endswith(")")
    c = c.strip("()-").replace(",", "")
    try:
        v = float(c)
    except ValueError:
        return None
    return -v if neg else v


def row_nums(cells):
    out = []
    for c in cells[1:]:
        cc = c.replace("$", "").replace("\xa0", "").strip()
        if cc in ("", ")", "%") or cc.endswith("%"):
            continue
        v = tonum(cc)
        if v is not None:
            out.append(v)
    return out


NONGAAP = re.compile(r"non-?gaap|adjusted|excluding|excl\.|core|normalized|operating (earnings|income) per|before (special|unusual|restructuring)|ex-", re.I)
EPS_LABEL = re.compile(r"(diluted|basic)", re.I)
EPS_CTX = re.compile(r"per\s+(common\s+)?(share|unit|ads)|eps|earnings|income|loss", re.I)
ANNUAL = re.compile(r"twelve months|nine months|six months|year ended|years ended|fiscal year|full year|full-year|12 months|9 months|6 months|year to date|ytd|year-to-date", re.I)
QTR = re.compile(r"three months|quarter|\b[1-4]q|qtr", re.I)
YEAR = re.compile(r"\b(?:19|20)\d\d\b")
GUID = re.compile(r"guidance|outlook|expected|forecast|projected|estimate|target range", re.I)
INC = re.compile(r"net (income|earnings|loss|\(loss\))|revenue|total sales|net sales|income before|operating income", re.I)


def hdr_rows(t):
    rows = []
    for r in t[:12]:
        if row_nums(r) and re.search(r"\d\.\d\d", " ".join(r)) and not YEAR.search(" ".join(r)):
            break
        s = " | ".join(c for c in r if c)
        if s:
            rows.append(s[:160])
    return rows[:8]


def parse_html(html: str) -> dict:
    P = Tables()
    P.feed(html)
    text = re.sub(r"\s+", " ", "".join(P.text).replace("\xa0", " ")).strip()
    cands = []
    for ti, t in enumerate(P.tables):
        top = " ".join(" ".join(r) for r in t[:5])
        full = " ".join(" ".join(r) for r in t[:80])
        hr = hdr_rows(t)
        hj = " ".join(hr)
        am, qm = ANNUAL.search(hj), QTR.search(hj)
        annual_first = bool(am and (not qm or am.start() < qm.start()))
        tng = bool(re.search(r"reconciliation|non-gaap", " ".join(" ".join(r) for r in t[:2]), re.I))
        sect = ""
        for ri, r in enumerate(t):
            if not r:
                continue
            label = (r[0] or (r[1] if len(r) > 1 else "")).strip()
            if not label:
                continue
            nums = row_nums(r)
            if not nums:
                sect = label
                continue
            lab_ok = EPS_LABEL.search(label) or (
                re.search(r"per (common )?(share|unit)|earnings per|income per|loss per", label, re.I)
                and not re.search(r"dividend|book value|ffo|affo|cash", label, re.I)) or (
                re.search(r"net (income|earnings|loss)", label, re.I) and re.search(r"per share", sect + " " + label, re.I)
                and re.search(r"basic|diluted", sect, re.I))
            if not lab_ok or not (EPS_CTX.search(label) or EPS_CTX.search(sect) or "per share" in full.lower()):
                continue
            if len(label) > 180:
                continue
            if re.search(r"shares|weighted|number", label, re.I) and not re.search(r"per share|eps", label, re.I):
                continue
            if re.search(r"shares|weighted", sect, re.I) and not re.search(r"per share", sect + label, re.I):
                continue
            if abs(nums[0]) >= 1000:
                continue
            cands.append(dict(table=ti, row=ri, label=label, section=sect[:80], nums=nums, cells=r[:14],
                              nongaap_hint=bool(NONGAAP.search(label) or NONGAAP.search(sect) or tng),
                              guidance_hint=bool(GUID.search(top)), income_table=bool(INC.search(full)),
                              header_rows=hr, annual_first=annual_first))
    return dict(text=text, n_tables=len(P.tables), cands=cands)


def has_eps_candidates(html: str) -> bool:
    return any(not c["nongaap_hint"] and not c["guidance_hint"] for c in parse_html(html)["cands"])


# ---------------------------------------------------------------- extract (candidate pack for LLM)
def build_pack(ev: dict) -> dict | None:
    meta_p = SUE / "docs" / f"{ev['accession']}.json"
    if not meta_p.exists():
        return None
    meta = json.loads(meta_p.read_text())
    pack = dict(id=ev["accession"], ticker=ev["ticker"], filed=ev["accepted_ny"])
    parsed = []
    for ex in meta["exhibits"]:
        parsed.append((ex, parse_html(_read_gz(SUE / "html" / f"{ev['accession']}.{ex['n']}.htm.gz"))))
    if not parsed:
        return dict(pack, no_exhibit=True, doc_types=[d["type"] for d in meta["docs"]])
    ex, pr = (next(((e, p) for e, p in parsed if any(not c["nongaap_hint"] and not c["guidance_hint"] for c in p["cands"])), None)
              or next(((e, p) for e, p in parsed if p["cands"]), None) or parsed[0])
    pack["exhibit"] = dict(n=ex["n"], type=ex["type"], name=ex["name"], url=ex["url"])
    pack["text_head"] = pr["text"][:600]
    m = re.search(r"(?:quarter|three months|fiscal quarter|thirteen weeks|13 weeks|three-month period|period)\s+ended\s+([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})", pr["text"], re.I)
    pack["period_text"] = m.group(0)[:100] if m else None
    by = collections.OrderedDict()
    for c in pr["cands"]:
        if not c["guidance_hint"]:
            by.setdefault(c["table"], []).append(c)

    def trank(item):
        ti, cs = item
        return (any(c["annual_first"] for c in cs), all(c["nongaap_hint"] for c in cs), not any(c["income_table"] for c in cs), ti)
    pack["tables"] = []
    pack["_cands"] = {}
    for ti, cs in sorted(by.items(), key=trank)[:4]:
        cs = sorted(cs, key=lambda c: (not re.search("diluted", c["label"] + c["section"], re.I), c["row"]))[:4]
        pack["tables"].append(dict(table=ti, header_rows=cs[0]["header_rows"],
                                   rows=[dict(row=c["row"], label=c["label"], section=c["section"], nums=c["nums"],
                                              hint_nongaap=c["nongaap_hint"]) for c in sorted(cs, key=lambda c: c["row"])]))
        for c in cs:
            pack["_cands"][f"{ti}:{c['row']}"] = c
    pack["_text"] = pr["text"]
    return pack


def llm_view(pack: dict) -> dict:
    return {k: v for k, v in pack.items() if not k.startswith("_")}


# ---------------------------------------------------------------- LLM
SYSTEM = "You are a careful financial-document reader. You locate and confirm; you never compute or invent numbers. Output strict JSON only, no prose, no code fences."
INSTR = """For each event below (an SEC 8-K Item 2.02 earnings exhibit), confirm the quarterly GAAP earnings per share (EPS) from the candidate table rows provided. Rules:
- Use ONLY the candidate rows given (identified by table and row). Never output a number that is not literally in a row's `nums` array. Values are taken from nums[idx] by the program; your cur_value / yago_value must equal those entries.
- GAAP means as reported under US GAAP (net income attributable to common shareholders per share). Adjusted, non-GAAP, core, normalized, FFO, "excluding items" rows are NOT GAAP. If no GAAP row exists, set diluted to null.
- cur_idx = index in nums of the CURRENT fiscal quarter, three-month (or 13-week) column. Not year-to-date, six/nine/twelve-month, full-year, or percent-change columns. In a fiscal Q4 release, pick the three-month column.
- yago_idx = index in nums of the SAME quarter one year earlier, if it is shown in the same table; else null. Do not use the prior sequential quarter.
- cur_header / yago_header = short verbatim quote (<=60 chars) copied from the table's header_rows identifying that column (e.g. "Three Months Ended September 30, 2024" or "2Q24"). If headers have no date or label for the column, quote what is there; use null only if truly absent.
- period_end = end date (YYYY-MM-DD) of the current three-month quarter; yago_period_end likewise for the year-ago column (null if you cannot tell).
- diluted: the GAAP diluted EPS row. If the company only reports one combined "basic and diluted" row, use it as diluted and set is_combined_basic_and_diluted true. basic: the GAAP basic EPS row in the same table, or null.
- release_kind: "full_results" (quarterly results incl. income statement or EPS), "preannouncement" (preliminary/partial results), "guidance_only", "operating_update" (deliveries/volumes/KPIs only), "annual_only" (only full-year results), or "other".
- note: mention any restatement, stock split, spin-off, change in fiscal year, or ambiguity that affects comparability of current vs year-ago; else "".
Return a JSON array, one object per event, in the same order, with keys:
{"id","release_kind","period_end","diluted":null|{"table","row","cur_idx","yago_idx","cur_value","yago_value","cur_header","yago_header","yago_period_end","is_gaap","is_combined_basic_and_diluted"},"basic":null|{"table","row","cur_idx","yago_idx","cur_value","yago_value"},"note"}
Events:
"""


def event_key(view: dict) -> str:
    return hashlib.sha256((PROMPT_VERSION + MODEL + json.dumps(view, sort_keys=True)).encode()).hexdigest()[:24]


def run_claude(prompt: str) -> str:
    env = dict(os.environ, CLAUDE_CODE_DISABLE_CLAUDE_MDS="1")
    r = subprocess.run(["claude", "-p", "--model", MODEL, "--output-format", "json", "--tools", "", "--no-session-persistence",
                        "--disable-slash-commands", "--setting-sources", "", "--system-prompt", SYSTEM],
                       input=prompt, capture_output=True, text=True, cwd=RUN / "llmcwd", env=env, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"claude rc={r.returncode}: {r.stderr[:200]}")
    body = json.loads(r.stdout)
    if body.get("is_error"):
        raise RuntimeError("claude error: " + str(body.get("result"))[:200])
    return body["result"]


def parse_json_array(txt: str):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt.strip())
    return json.loads(t[t.find("["):t.rfind("]") + 1])


CALLS = [0]


def llm_batch(views: list[dict]) -> dict[str, dict]:
    prompt = INSTR + json.dumps(views, ensure_ascii=False)
    bh = hashlib.sha256((PROMPT_VERSION + MODEL + prompt).encode()).hexdigest()[:24]
    bp = SUE / "llm" / f"batch-{bh}.json"
    if bp.exists():
        raw = json.loads(bp.read_text())["result"]
    else:
        raw = run_claude(prompt)
        with LOCK:
            CALLS[0] += 1
        bp.write_text(json.dumps(dict(model=MODEL, prompt_version=PROMPT_VERSION, n=len(views), ids=[v["id"] for v in views], result=raw)))
    ids = {v["id"] for v in views}
    return {a["id"]: a for a in parse_json_array(raw) if isinstance(a, dict) and a.get("id") in ids}


def stage_llm(packs: list[dict], batch_size: int, workers: int) -> None:
    need = [v for v in (llm_view(p) for p in packs) if not (SUE / "llm" / f"ev-{event_key(v)}.json").exists()]
    log(f"llm: {len(need)} events need LLM ({len(packs)-len(need)} cached)")
    batches = [need[i:i + batch_size] for i in range(0, len(need), batch_size)]

    def work(views, depth=0):
        try:
            res = llm_batch(views)
        except Exception as exc:  # noqa: BLE001
            log("llm batch failed", len(views), str(exc)[:120])
            if depth < 1 and len(views) > 1:
                h = len(views) // 2
                work(views[:h], depth + 1)
                work(views[h:], depth + 1)
            return
        for v in views:
            if v["id"] in res:
                (SUE / "llm" / f"ev-{event_key(v)}.json").write_text(json.dumps(res[v["id"]]))
        miss = [v for v in views if v["id"] not in res]
        if miss and depth < 1:
            work(miss, depth + 1)

    done = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        for f in cf.as_completed([ex.submit(work, b) for b in batches]):
            f.result()
            done += 1
            log(f"llm batches {done}/{len(batches)} calls={CALLS[0]}")


def llm_answer(pack: dict) -> dict | None:
    p = SUE / "llm" / f"ev-{event_key(llm_view(pack))}.json"
    return json.loads(p.read_text()) if p.exists() else None


# ---------------------------------------------------------------- verify
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def date_in_text(date_s: str | None, text: str) -> bool:
    if not date_s:
        return False
    try:
        d = D.date.fromisoformat(date_s)
    except ValueError:
        return False
    m = MONTHS[d.month - 1]
    pats = [rf"{m[:3]}[a-z]*\.?\s+0?{d.day},?\s+{d.year}", rf"0?{d.day}\s+{m[:3]}[a-z]*\.?,?\s+{d.year}",
            rf"\b0?{d.month}/0?{d.day}/(?:{d.year}|{d.year % 100:02d})\b", rf"{d.year}-{d.month:02d}-{d.day:02d}"]
    return any(re.search(p, text, re.I) for p in pats)


def year_tokens(s: str) -> list[int]:
    return [int(y) for y in YEAR.findall(s or "")]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def quote_in_header(quote: str | None, header_rows: list[str]) -> bool:
    """Every '|'-separated part of the quote (letters/digits only) must occur in the header block."""
    h = norm(" ".join(header_rows))
    parts = [norm(p) for p in (quote or "").split("|")]
    parts = [p for p in parts if p]
    return bool(parts) and all(p in h for p in parts)


YEAR_CELL = re.compile(r"^(?:FY\s?)?((?:19|20)\d\d)(?:\s*\(\w+\))?$", re.I)
PCT_CELL = re.compile(r"%|percent|change|inc\s*/?\s*\(dec|increase|decrease|currency|constant|variance|\bvs\b", re.I)


QLAB = re.compile(r"^(?:(?:1st|2nd|3rd|4th)\s+Qtr\.?|Q[1-4])$", re.I)
ANNLAB = re.compile(r"^(?:Full[\s-]?Year|FY|YTD|Year)$", re.I)


def header_alignment(header_rows: list[str], n: int) -> dict | None:
    """Map numeric columns to a year (and group/quarter label) from the header block.
    Mode A: a year row (2024 | 2023 | [change cols]) whose year count <= n, extra cells being change columns.
    Mode B: a quarter-label row (1st Qtr .. 4th Qtr | Full Year | ... | YTD) split into year groups by a year row.
    Returns dict(years=[...], groups=[text]|None, labels=[...]|None) or None (then the quote check is used)."""
    rows = [[c.strip() for c in hr.split(" | ") if c.strip()] for hr in header_rows]
    # mode B
    for hi, cells in enumerate(rows):
        if len(cells) == n and n >= 4 and all(QLAB.match(c) or ANNLAB.match(c) for c in cells):
            ylist = None
            for other in rows:
                ys = [int(YEAR_CELL.match(c).group(1)) for c in other if YEAR_CELL.match(c)]
                if ys and len(ys) == len(other):
                    ylist = ys
                    break
            if not ylist:
                continue
            groups, cur = [], []
            for c in cells:
                cur.append(c)
                if ANNLAB.match(c):
                    groups.append(cur)
                    cur = []
            if cur:
                groups.append(cur)
            order = sorted(ylist) if len(ylist) == len(groups) and ylist == sorted(ylist) else ylist
            if len(order) != len(groups):
                continue
            years, labels = [], []
            for yv, g in zip(order, groups):
                years += [yv] * len(g)
                labels += g
            return dict(years=years, groups=["Quarter" if QLAB.match(l) else "Annual YTD" for l in labels], labels=labels)
    # mode A
    for hi, cells in enumerate(rows):
        years = [int(YEAR_CELL.match(c).group(1)) for c in cells if YEAR_CELL.match(c)]
        others = [c for c in cells if not YEAR_CELL.match(c)]
        if len(years) > n >= 2:  # several column groups in the header (e.g. Consolidated | GE Industrial); data row only fills the first
            years = years[:n]
        if len(years) >= 2 and len(years) <= n and all(PCT_CELL.search(c) or len(c) < 4 or re.search(r"^(consolidated|ge\b)", c, re.I) for c in others[1:] if c) \
                and (n == len(years) or n - len(years) <= max(1, len(others))):
            groups = None
            if hi > 0:
                gcells = [c for c in rows[hi - 1] if re.search(r"months|weeks|quarter|year|ended", c, re.I)]
                if gcells and len(years) % len(gcells) == 0:
                    per = len(years) // len(gcells)
                    groups = [gcells[i // per] for i in range(len(years))] + ["change"] * (n - len(years))
            return dict(years=years + [0] * (n - len(years)), groups=groups, labels=None)
    # mode C: header cells are month-day dates without a year (e.g. TMO: "September 30, | % of | October 1, | % of")
    MD = re.compile(r"^([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),?$")
    for hi, cells in enumerate(rows):
        dates = [MD.match(c) for c in cells if MD.match(c) and MD.match(c).group(1)[:3].lower() in _MN3]
        rest = [c for c in cells if not (MD.match(c) and MD.match(c).group(1)[:3].lower() in _MN3)]
        if len(dates) >= 2 and len(dates) == n and all(PCT_CELL.search(c) or len(c) < 4 for c in rest) \
                and any(QTR.search(" ".join(r)) for r in rows[:hi]):
            md = [(_MN3.index(m.group(1)[:3].lower()) + 1, int(m.group(2))) for m in dates]
            return dict(years=[0] * n, groups=["Quarter"] * n, labels=None, md=md)
    return None


_MN3 = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _doy_gap(a, b):
    da = D.date(2001, a[0], min(a[1], 28 if a[0] == 2 else 30 if a[0] in (4, 6, 9, 11) else 31))
    db = D.date(2001, b[0], min(b[1], 28 if b[0] == 2 else 30 if b[0] in (4, 6, 9, 11) else 31))
    g = abs((da - db).days)
    return min(g, 365 - g)


def infer_calendar_period(text: str, accepted_ny: str) -> str | None:
    """Only when the release gives no period date: ordinal-quarter label in the text -> calendar quarter end,
    accepted by period_ok only if 0 < filing - quarter_end <= 130 days (so fiscal-offset companies are rejected)."""
    ords = {"first": (3, 31), "second": (6, 30), "third": (9, 30), "fourth": (12, 31)}
    m = re.search(r"\b(first|second|third|fourth)[- ]quarter(?: of)?\s+(20\d\d)", text, re.I)
    if not m:
        return None
    mo, dd = ords[m.group(1).lower()]
    return f"{int(m.group(2))}-{mo:02d}-{dd:02d}"


def period_ok(pe: str | None, text: str, accepted_ny: str) -> bool:
    """Full date in the text, or (month+day and year both present in text); and 0 < filing - period_end <= 130 days."""
    if not pe:
        return False
    try:
        d = D.date.fromisoformat(pe)
        gap = (D.date.fromisoformat(accepted_ny[:10]) - d).days
    except ValueError:
        return False
    if not (0 < gap <= 130):
        return False
    if date_in_text(pe, text):
        return True
    m = MONTHS[d.month - 1]
    if re.search(rf"{m[:3]}[a-z]*\.?\s*0?{d.day}\b", text, re.I) and str(d.year) in text:
        return True
    # calendar quarter-end named only as "first/second/third/fourth quarter <year>" (e.g. JNJ, PFE, MRK releases)
    q = {3: "first", 6: "second", 9: "third", 12: "fourth"}.get(d.month)
    if q and (d.month, d.day) in ((3, 31), (6, 30), (9, 30), (12, 31)):
        return bool(re.search(rf"\b{q}[- ]?quarter[^.]{{0,40}}{d.year}|\bQ{(d.month)//3}\s*'?(?:{d.year}|{d.year%100:02d})\b|\b{(d.month)//3}Q'?(?:{d.year}|{d.year%100:02d})\b", text, re.I))
    return False


def verify_event(ev: dict, pack: dict | None, ans: dict | None) -> dict:
    """Return the evidence row. status: verified | unverified | missing:<reason>."""
    row = dict(ticker=ev["ticker"], accession=ev["accession"], accepted_ny=ev["accepted_ny"], signal_date=ev["signal_date"],
               benchmark=ev.get("benchmark"), source=ev["source"], fiscal_period_end=None, eps_current=None, eps_year_ago=None,
               basic_eps_current=None, basic_eps_year_ago=None, evidence=None, status=None, notes=[], release_kind=None)
    if pack is None:
        row["status"] = "missing:fetch_failed"
        return row
    if pack.get("no_exhibit"):
        row["status"], row["release_kind"] = "missing:no_ex99_htm_exhibit", "no_exhibit"
        return row
    if ans is None:
        row["status"] = "missing:llm_no_answer"
        return row
    row["release_kind"] = ans.get("release_kind")
    row["notes"] = [ans["note"]] if ans.get("note") else []
    text = pack["_text"]
    pe = ans.get("period_end")
    if not pe and ans.get("diluted"):
        pe = infer_calendar_period(text, ev["accepted_ny"])
        if pe:
            row["notes"].append("period_end_inferred_from_quarter_label_and_filing_date")
    if pe and period_ok(pe, text, ev["accepted_ny"]):
        row["fiscal_period_end"] = pe
    elif pe:
        row["notes"].append("period_end_not_in_text")
    dil = ans.get("diluted")
    if row["release_kind"] != "full_results":
        row["status"] = f"missing:not_full_results({row['release_kind']})"
        return row
    if not dil:
        row["status"] = "missing:no_gaap_eps_row_in_tables" if pack.get("tables") else "missing:no_eps_table"
        return row
    if dil.get("is_gaap") is False:
        row["status"] = "missing:only_non_gaap_eps"
        return row
    cand = pack["_cands"].get(f"{dil.get('table')}:{dil.get('row')}")
    if cand is None:
        row["status"] = "unverified"
        row["notes"].append("llm_row_not_a_candidate")
        return row
    nums = cand["nums"]
    ci, yi = dil.get("cur_idx"), dil.get("yago_idx")
    if not isinstance(ci, int) or not 0 <= ci < len(nums):
        row["status"] = "unverified"
        row["notes"].append("bad_cur_idx")
        return row
    problems = []
    if cand["nongaap_hint"]:
        problems.append("program_hint_nongaap_table_or_label")
    cur = nums[ci]
    if not isinstance(dil.get("cur_value"), (int, float)) or abs(dil["cur_value"] - cur) > 1e-9:
        problems.append("cur_value_mismatch_cell")
    ch, yh = dil.get("cur_header"), dil.get("yago_header")
    al = header_alignment(cand["header_rows"], len(nums))
    if not row["fiscal_period_end"] and al and al["years"][ci]:
        mq = re.search(r"\b(first|second|third|fourth)[- ]?quarter", text, re.I)
        if mq:
            mo, dd = {"first": (3, 31), "second": (6, 30), "third": (9, 30), "fourth": (12, 31)}[mq.group(1).lower()]
            cand_pe = f"{al['years'][ci]}-{mo:02d}-{dd:02d}"
            if period_ok(cand_pe, text, ev["accepted_ny"]):
                row["fiscal_period_end"] = cand_pe
                row["notes"].append("period_end_inferred_from_quarter_label_and_column_year_and_filing_date")
    py = int(row["fiscal_period_end"][:4]) if row["fiscal_period_end"] else None
    if not row["fiscal_period_end"]:
        problems.append("period_not_verified")
    ev_ = dict(exhibit_type=pack["exhibit"]["type"], exhibit_file=pack["exhibit"]["name"], exhibit_url=pack["exhibit"]["url"],
               table_index=cand["table"], row_index=cand["row"], row_label=cand["label"], row_section=cand["section"],
               row_cells=cand["cells"], cur_idx=ci, cur_value=cur, cur_header=ch, header_rows=cand["header_rows"],
               is_combined_basic_and_diluted=bool(dil.get("is_combined_basic_and_diluted")),
               column_check=("md_dates" if al and al.get("md") else "structural") if al else "quote")
    row["evidence"] = ev_
    row["eps_basis"] = "continuing_operations" if re.search(r"continuing", cand["label"] + " " + cand["section"], re.I) else "as_labelled"

    def is_quarter_col(i, quote):
        if al and al["groups"]:
            g = al["groups"][i]
            return bool(QTR.search(g)) and not (ANNUAL.search(g) and not QTR.search(g))
        return bool(quote) and not (ANNUAL.search(quote) and not QTR.search(quote))
    if not is_quarter_col(ci, ch):
        problems.append("cur_col_not_quarterly")
    if al and al.get("md"):
        pe_d = D.date.fromisoformat(row["fiscal_period_end"]) if row["fiscal_period_end"] else None
        if pe_d and _doy_gap(al["md"][ci], (pe_d.month, pe_d.day)) > 4:
            problems.append("cur_col_date_differs_from_period")
    elif al and py:
        if al["years"][ci] != py:
            problems.append("cur_col_year_differs_from_period")
    elif py:
        ys = year_tokens(ch or "")
        if not quote_in_header(ch, cand["header_rows"]):
            problems.append("cur_header_quote_not_in_header")
        elif ys and ys[0] != py and py not in ys:
            problems.append("cur_header_year_differs_from_period")
    yago, yago_ok = None, False
    if isinstance(yi, int) and 0 <= yi < len(nums) and yi != ci:
        yago = nums[yi]
        ev_.update(yago_idx=yi, yago_value=yago, yago_header=yh)
        if not isinstance(dil.get("yago_value"), (int, float)) or abs(dil["yago_value"] - yago) > 1e-9:
            row["notes"].append("yago_value_mismatch_cell")
        elif py:
            if al and al.get("md"):
                yago_ok = ci < yi and _doy_gap(al["md"][yi], al["md"][ci]) <= 10
            elif al:
                yago_ok = al["years"][yi] == py - 1 and is_quarter_col(yi, yh)
                if al.get("md"):
                    pass
                elif al.get("labels"):
                    yago_ok = yago_ok and al["labels"][yi] == al["labels"][ci]
                elif al["groups"] and al["groups"][yi] != al["groups"][ci]:
                    yago_ok = False
            else:
                yh_ok = quote_in_header(yh, cand["header_rows"])
                ys = year_tokens(yh or "")
                two = [int(x) for x in re.findall(r"(?<!\d)(\d{2})(?!\d)", yh or "")]
                yd, date_ok = dil.get("yago_period_end"), False
                if yd:
                    try:
                        gap = (D.date.fromisoformat(row["fiscal_period_end"]) - D.date.fromisoformat(yd)).days
                        date_ok = 350 <= gap <= 380 and date_in_text(yd, text)
                    except ValueError:
                        pass
                year_ok = bool(ys and ys[0] == py - 1) or bool(not ys and two and two[-1] == (py - 1) % 100)
                yago_ok = yh_ok and (date_ok or year_ok) and is_quarter_col(yi, yh)
            if not yago_ok:
                row["notes"].append("yago_unverified:" + ("year_mismatch_or_not_quarterly" if al else "quote_year_or_date_check_failed"))
    elif yi is not None:
        row["notes"].append("bad_yago_idx")
    else:
        row["notes"].append("no_year_ago_column_in_table")
    bas = ans.get("basic")
    if bas:
        bc = pack["_cands"].get(f"{bas.get('table')}:{bas.get('row')}")
        if bc and isinstance(bas.get("cur_idx"), int) and 0 <= bas["cur_idx"] < len(bc["nums"]) \
                and isinstance(bas.get("cur_value"), (int, float)) and abs(bas["cur_value"] - bc["nums"][bas["cur_idx"]]) < 1e-9:
            row["basic_eps_current"] = bc["nums"][bas["cur_idx"]]
            ev_["basic"] = dict(table_index=bc["table"], row_index=bc["row"], row_label=bc["label"], cur_idx=bas["cur_idx"])
            bi = bas.get("yago_idx")
            if isinstance(bi, int) and 0 <= bi < len(bc["nums"]) and yago_ok:
                row["basic_eps_year_ago"] = bc["nums"][bi]
                ev_["basic"]["yago_idx"] = bi
    if problems:
        row["status"] = "unverified"
        row["notes"] += problems
        row["eps_current_unverified_value"] = cur
        return row
    row["eps_current"] = cur
    if yago_ok:
        row["eps_year_ago"] = yago
        row["status"] = "verified"
    else:
        row["status"] = "unverified"
        row["notes"].append("current_verified_year_ago_not")
    return row


# ---------------------------------------------------------------- tier 2: sentences / flattened text (no usable EPS table)
SNIP = re.compile(r"(per (?:diluted |basic )?(?:common )?(?:share|ADS|unit)|diluted (?:earnings|EPS|net (?:income|loss))|earnings per (?:diluted )?share|\bEPS\b)", re.I)
INSTR2 = """For each event below (an SEC 8-K Item 2.02 earnings exhibit) no usable EPS table was found, so EPS may only appear in sentences. Confirm the quarterly GAAP diluted EPS from the text snippets provided. Rules:
- Use ONLY the snippets given. Quotes must be copied verbatim (<=160 chars) from one snippet and must contain the number you report, as written (e.g. "$0.19 per diluted share"). Never report a number that is not literally inside your quote.
- GAAP = as reported under US GAAP (net income attributable to common shareholders per diluted share, or total/continuing-operations GAAP EPS as headlined). Adjusted / non-GAAP / core / FFO / excluding-items figures are NOT GAAP; if only those exist set diluted to null.
- cur: the CURRENT fiscal quarter (three months/13 weeks), not full-year, YTD or guidance. yago: the same quarter one year earlier, if a snippet states it (e.g. "compared to $0.40 for the third quarter of 2020"); else null with yago_quote null. Signed values: net loss per share is negative.
- If the company states EPS only in cents (e.g. "95 cents"), give the value in dollars (0.95) and keep the quote as written.
- period_end = end date YYYY-MM-DD of the current quarter; yago_period_end likewise (null if unclear).
- release_kind as before: full_results | preannouncement | guidance_only | operating_update | annual_only | other.
Return a JSON array, one object per event in order: {"id","release_kind","period_end","diluted":null|{"cur_quote","cur_value","yago_quote","yago_value","yago_period_end","is_gaap"},"note"}
Events:
"""


def build_text_view(pack: dict) -> dict | None:
    text = pack.get("_text") or ""
    snips, last = [], -1000
    for m in SNIP.finditer(text):
        if m.start() - last < 240:
            continue
        w = text[max(0, m.start() - 220): m.end() + 220]
        if re.search(r"\$\s?\d|\d+\s?cents|\d\.\d\d", w):
            snips.append(w)
            last = m.start()
    if not snips:
        return None
    return dict(id=pack["id"], ticker=pack["ticker"], filed=pack["filed"], text_head=pack["text_head"],
                period_text=pack.get("period_text"), snippets=snips[:8], mode="text_snippets")


def key2(view):
    return hashlib.sha256(("T2" + PROMPT_VERSION + MODEL + json.dumps(view, sort_keys=True)).encode()).hexdigest()[:24]


def llm_batch2(views):
    prompt = INSTR2 + json.dumps(views, ensure_ascii=False)
    bh = hashlib.sha256(("T2" + PROMPT_VERSION + MODEL + prompt).encode()).hexdigest()[:24]
    bp = SUE / "llm" / f"batch2-{bh}.json"
    if bp.exists():
        raw = json.loads(bp.read_text())["result"]
    else:
        raw = run_claude(prompt)
        with LOCK:
            CALLS[0] += 1
        bp.write_text(json.dumps(dict(model=MODEL, prompt_version=PROMPT_VERSION, tier=2, ids=[v["id"] for v in views], result=raw)))
    ids = {v["id"] for v in views}
    return {a["id"]: a for a in parse_json_array(raw) if isinstance(a, dict) and a.get("id") in ids}


def tier1_failed(row: dict) -> bool:
    return row["status"] in ("missing:no_eps_table", "missing:no_gaap_eps_row_in_tables")


def stage_llm2(events, batch_size, workers):
    """Run tier 2 only for events whose tier-1 outcome is missing an EPS table / GAAP row."""
    views = []
    for ev in events:
        pack = build_pack(ev)
        if not pack or pack.get("no_exhibit"):
            continue
        row = verify_event(ev, pack, llm_answer(pack))
        if not tier1_failed(row) and not (row["status"] == "missing:llm_no_answer"):
            continue
        v = build_text_view(pack)
        if v and not (SUE / "llm" / f"ev2-{key2(v)}.json").exists():
            views.append(v)
    log(f"llm tier2: {len(views)} events")
    batches = [views[i:i + batch_size] for i in range(0, len(views), batch_size)]

    def work(vs, depth=0):
        try:
            res = llm_batch2(vs)
        except Exception as exc:  # noqa: BLE001
            log("llm2 batch failed", len(vs), str(exc)[:120])
            if depth < 1 and len(vs) > 1:
                work(vs[:len(vs) // 2], depth + 1)
                work(vs[len(vs) // 2:], depth + 1)
            return
        for v in vs:
            if v["id"] in res:
                (SUE / "llm" / f"ev2-{key2(v)}.json").write_text(json.dumps(res[v["id"]]))
    with cf.ThreadPoolExecutor(workers) as ex:
        for k, f in enumerate(cf.as_completed([ex.submit(work, b) for b in batches])):
            f.result()
            log(f"llm2 batches {k+1}/{len(batches)} calls={CALLS[0]}")


def quote_ok(quote, text):
    return bool(quote) and norm(quote) in norm(text)


def num_in_quote(v, quote):
    a = abs(v)
    pats = [f"{a:.2f}", f"{a:.3f}".rstrip("0"), str(round(a * 100)) + " cents", str(round(a * 100)) + "\u00a2"]
    return any(p in quote for p in pats) or (a < 1 and f"{a:.2f}".lstrip("0") in quote)


def verify_text(ev, pack, row):
    """Tier 2: upgrade a tier-1 missing row using verbatim sentences. Evidence kind = prose_sentence."""
    view = build_text_view(pack)
    if not view:
        return row
    p = SUE / "llm" / f"ev2-{key2(view)}.json"
    if not p.exists():
        return row
    ans = json.loads(p.read_text())
    text = pack["_text"]
    r = dict(row, notes=list(row["notes"]), evidence=None, tier=2)
    r["release_kind"] = ans.get("release_kind") or r["release_kind"]
    if ans.get("note"):
        r["notes"].append(ans["note"])
    pe = ans.get("period_end")
    r["fiscal_period_end"] = pe if pe and period_ok(pe, text, ev["accepted_ny"]) else None
    if r["release_kind"] != "full_results":
        r["status"] = f"missing:not_full_results({r['release_kind']})"
        return r
    d = ans.get("diluted")
    if not d or d.get("is_gaap") is False:
        r["status"] = "missing:no_gaap_eps_in_text"
        return r
    cq, cv = d.get("cur_quote"), d.get("cur_value")
    problems = []
    if not isinstance(cv, (int, float)) or not quote_ok(cq, text) or not num_in_quote(cv, cq):
        problems.append("cur_quote_or_number_not_verbatim")
    elif re.search(r"non-?gaap|adjusted|excluding|core\b|before ", cq, re.I):
        problems.append("cur_quote_mentions_adjusted")
    elif (cv < 0 and not re.search(r"loss|\(|-|negative", cq, re.I)) or (cv > 0 and re.search(r"net loss|loss per share|loss of", cq, re.I)):
        problems.append("cur_sign_inconsistent_with_quote")
    if not r["fiscal_period_end"]:
        problems.append("period_not_verified")
    r["evidence"] = dict(kind="prose_sentence", exhibit_type=pack["exhibit"]["type"], exhibit_file=pack["exhibit"]["name"],
                         exhibit_url=pack["exhibit"]["url"], table_index=None, row_label=cq, cur_value=cv, cur_header=None,
                         yago_quote=d.get("yago_quote"), yago_value=d.get("yago_value"))
    if problems:
        r["status"] = "unverified"
        r["notes"] += problems
        return r
    r["eps_current"] = cv
    yq, yv = d.get("yago_quote"), d.get("yago_value")
    py = int(r["fiscal_period_end"][:4])
    if isinstance(yv, (int, float)) and quote_ok(yq, text) and num_in_quote(yv, yq) \
            and not re.search(r"non-?gaap|adjusted|excluding", yq, re.I) \
            and (str(py - 1) in yq or re.search(r"prior[- ]year|year[- ]ago|compared (to|with)|a year (earlier|ago)|from \$", yq, re.I)) \
            and not ((yv < 0 and not re.search(r"loss|\(|-|negative", yq, re.I)) or (yv > 0 and re.search(r"net loss|loss per share|loss of", yq, re.I))):
        r["eps_year_ago"] = yv
        r["status"] = "verified"
    else:
        r["status"] = "unverified"
        r["notes"].append("current_verified_year_ago_not")
    return r


# ---------------------------------------------------------------- finalize (dedupe), XBRL check, chains, report
NON_EARNINGS = ("preannouncement", "guidance_only", "operating_update", "annual_only", "other", "no_exhibit")


def dedupe(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    keep, excl = [], []
    by = collections.defaultdict(list)
    for r in rows:
        by[r["ticker"]].append(r)
    for rs in by.values():
        rs.sort(key=lambda r: r["accepted_ny"])
        seen: dict[str, str] = {}
        for r in rs:
            kind = r["release_kind"]
            if kind in NON_EARNINGS:
                r["exclusion"] = f"non_earnings_release:{kind}"
                excl.append(r)
                continue
            pe = r["fiscal_period_end"]
            if pe and kind == "full_results":
                if pe in seen:
                    r["exclusion"] = f"duplicate_of:{seen[pe]}"
                    excl.append(r)
                    continue
                seen[pe] = r["accession"]
            keep.append(r)
    keep.sort(key=lambda r: (r["ticker"], r["accepted_ny"]))
    return keep, excl


_xb_cache: dict[str, dict] = {}


def xbrl_quarters(client: SecClient, ticker: str) -> dict:
    if ticker in _xb_cache:
        return _xb_cache[ticker]
    out = {}
    try:
        ident = dt.resolve_company(ticker)
        rec = client.companyfacts(ident["cik"], max_age_seconds=30 * 86400)
        body = json.loads(client.cache.read(rec))
        for tag in ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"):
            for arr in body.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).values():
                for f in arr:
                    if "start" not in f:
                        continue
                    days = (D.date.fromisoformat(f["end"]) - D.date.fromisoformat(f["start"])).days
                    kind = "q" if 80 <= days <= 100 else "9m" if 255 <= days <= 290 else "fy" if 350 <= days <= 380 else None
                    if kind:
                        d = out.setdefault(tag + ":" + kind if kind != "q" else tag, {})
                        cur = d.get(f["end"])
                        if cur is None or f["filed"] < cur["filed"]:
                            d[f["end"]] = dict(val=f["val"], filed=f["filed"], accn=f["accn"])
    except Exception as exc:  # noqa: BLE001
        log("xbrl error", ticker, str(exc)[:80])
    _xb_cache[ticker] = out
    return out


def xbrl_check(rows: list[dict]) -> None:
    """Cross-check only: never feeds status or values."""
    client = SecClient(settings.cache(), user_agent=settings.sec_user_agent(), request_budget=10**6)

    def near(d: dict, end: str, tol=4):
        e = D.date.fromisoformat(end)
        return next((v for k, v in d.items() if abs((D.date.fromisoformat(k) - e).days) <= tol), None)
    for r in rows:
        r["xbrl_check"] = None
        pe = r["fiscal_period_end"]
        v = r["eps_current"] if r["eps_current"] is not None else r.get("eps_current_unverified_value")
        if not pe or v is None:
            continue
        q = xbrl_quarters(client, r["ticker"])
        cands = [q.get(tag, {}) for tag in ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted")]
        hit = [h for h in (near(c, pe) for c in cands) if h]
        if not hit:
            r["xbrl_check"] = dict(cur="uncheckable_no_quarterly_xbrl")
            # fiscal Q4: approximate FY - 9M (EPS is not additive; check only, tolerance 0.06)
            for tag in ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"):
                fy, n9 = near(q.get(tag + ":fy", {}), pe), None
                if fy:
                    n9 = next((x for k, x in q.get(tag + ":9m", {}).items()
                               if 80 <= (D.date.fromisoformat(pe) - D.date.fromisoformat(k)).days <= 100), None)
                if fy and n9:
                    r["xbrl_check"] = dict(cur="approx_match" if abs(fy["val"] - n9["val"] - v) <= 0.06 else "approx_far",
                                           xbrl=[round(fy["val"] - n9["val"], 2)])
                    break
        else:
            r["xbrl_check"] = dict(cur="match" if any(abs(h["val"] - v) < 0.005 for h in hit) else "mismatch", xbrl=[h["val"] for h in hit])
        yv = r["eps_year_ago"]
        if yv is not None:
            ye = (D.date.fromisoformat(pe) - D.timedelta(days=365)).isoformat()
            yh = [h for h in (near(c, ye, 8) for c in cands) if h]
            if yh:
                r["xbrl_check"]["yago"] = "match" if any(abs(h["val"] - yv) < 0.005 for h in yh) else "mismatch"
                r["xbrl_check"]["yago_xbrl"] = [h["val"] for h in yh]
            else:
                r["xbrl_check"]["yago"] = "uncheckable_no_quarterly_xbrl"


def chain_flags(keep: list[dict]) -> None:
    by = collections.defaultdict(list)
    for r in keep:
        if r["fiscal_period_end"] and r["release_kind"] == "full_results":
            by[r["ticker"]].append(r)
    for rs in by.values():
        rs.sort(key=lambda r: r["fiscal_period_end"])
        for i, r in enumerate(rs):
            n = 0
            if r["status"] == "verified":
                n, j = 1, i
                while j > 0:
                    gap = (D.date.fromisoformat(rs[j]["fiscal_period_end"]) - D.date.fromisoformat(rs[j - 1]["fiscal_period_end"])).days
                    if rs[j - 1]["status"] == "verified" and 75 <= gap <= 110:
                        n, j = n + 1, j - 1
                    else:
                        break
            r["consecutive_verified_through_q"] = n
            r["chain9_ok"] = n >= 9


def stage_report(events: list[dict], pilot_ids: set[str] | None = None) -> None:
    rows = []
    for ev in events:
        if pilot_ids is not None and ev["accession"] not in pilot_ids:
            continue
        pack = build_pack(ev)
        ans = llm_answer(pack) if pack and not pack.get("no_exhibit") else None
        row = verify_event(ev, pack, ans)
        if pack and not pack.get("no_exhibit") and tier1_failed(row):
            row = verify_text(ev, pack, row)
        rows.append(row)
    keep, excl = dedupe(rows)
    xbrl_check(keep)
    chain_flags(keep)
    tag = "-pilot" if pilot_ids is not None else ""
    with (SUE / f"eps-evidence{tag}.jsonl").open("w") as fh:
        for r in keep:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (SUE / f"eps-excluded{tag}.jsonl").open("w") as fh:
        for r in excl:
            fh.write(json.dumps({k: r[k] for k in ("ticker", "accession", "accepted_ny", "release_kind", "status", "exclusion")}, ensure_ascii=False) + "\n")
    write_coverage(keep, excl, tag)


def write_coverage(keep, excl, tag):
    L = []
    P = L.append
    n = len(keep)
    P(f"# SUE 证据链覆盖率{' (pilot)' if tag else ''}\n")
    P(f"生成：{time.strftime('%Y-%m-%d %H:%M')}。口径：每个财季一行（第一份完整业绩公告）；`verified` = 当季与去年同季 GAAP EPS 均通过程序核对。\n")
    P(f"- 去重后业绩事件：{n}；被排除（非业绩公告/重复）：{len(excl)}")
    c = collections.Counter(r["status"].split("(")[0] if r["status"].startswith("missing") else r["status"] for r in keep)
    P("\n## 状态\n\n| 状态 | 数 | 占比 |\n|---|---|---|")
    for k, v in c.most_common():
        P(f"| {k} | {v} | {v/max(n,1):.1%} |")
    ex = collections.Counter(re.sub(r"duplicate_of:.*", "duplicate_of", r["exclusion"]) for r in excl)
    P("\n## 排除原因\n\n| 原因 | 数 |\n|---|---|")
    for k, v in ex.most_common():
        P(f"| {k} | {v} |")
    insample = [r for r in keep if r["source"] == "events-8k"]
    P(f"\n检验窗口内事件（来自 events-8k，2019 起）：{len(insample)}；其中 verified {sum(1 for r in insample if r['status']=='verified')}，"
      f"其前 8 个季度也全部 verified（连续 9 季）{sum(1 for r in insample if r.get('chain9_ok'))}")
    unv = collections.Counter(nn for r in keep if r["status"] == "unverified" for nn in r["notes"] if "_" in nn and len(nn) < 60)
    P("\n## unverified 备注（一事件可有多个）\n\n| 备注 | 数 |\n|---|---|")
    for k, v in unv.most_common(15):
        P(f"| {k} | {v} |")

    def table(title, keyf, src):
        g = collections.defaultdict(lambda: [0, 0, 0])
        for r in src:
            x = g[keyf(r)]
            x[0] += 1
            x[1] += r["status"] == "verified"
            x[2] += bool(r.get("chain9_ok"))
        P(f"\n## {title}\n\n| 键 | 事件 | verified | 连续9季 |\n|---|---|---|---|")
        for k in sorted(g):
            P(f"| {k} | {g[k][0]} | {g[k][1]} | {g[k][2]} |")
    table("按年份（检验窗口，signal_date 年）", lambda r: r["signal_date"][:4], insample)
    table("按年份（含 2017-18 历史事件）", lambda r: r["signal_date"][:4], keep)
    table("按板块 ETF（benchmark）", lambda r: r["benchmark"] or "unknown", insample)
    table("按 ticker（检验窗口）", lambda r: r["ticker"], insample)
    P("\n## XBRL 核对（仅核对，不是来源）\n")
    cc, cy, byyr = collections.Counter(), collections.Counter(), collections.defaultdict(collections.Counter)
    for r in keep:
        xc = r.get("xbrl_check")
        if not xc:
            continue
        cc[xc["cur"]] += 1
        byyr[r["signal_date"][:4]][xc["cur"]] += 1
        if "yago" in xc:
            cy[xc["yago"]] += 1
    P("| 项 | match | mismatch | uncheckable |\n|---|---|---|---|")
    P(f"| 当季 EPS | {cc['match']} | {cc['mismatch']} | {cc['uncheckable_no_quarterly_xbrl']} |")
    P(f"| 当季 EPS，财年 Q4 用 FY−9M 近似（容差 0.06，EPS 不可加，仅参考） | {cc['approx_match']} | {cc['approx_far']} | |")
    P(f"| 去年同季 EPS（XBRL 为首次披露值；8-K 同列可能是重述/拆股调整值） | {cy['match']} | {cy['mismatch']} | {cy['uncheckable_no_quarterly_xbrl']} |")
    P(f"\n当季可核对准确率：{cc['match']/max(cc['match']+cc['mismatch'],1):.1%}（n={cc['match']+cc['mismatch']}）；"
      f"去年同季：{cy['match']/max(cy['match']+cy['mismatch'],1):.1%}（n={cy['match']+cy['mismatch']}）")
    P("\n| 年份 | match | mismatch | approx_match(Q4) | approx_far(Q4) | uncheckable |\n|---|---|---|---|---|---|")
    for y in sorted(byyr):
        b = byyr[y]
        P(f"| {y} | {b['match']} | {b['mismatch']} | {b['approx_match']} | {b['approx_far']} | {b['uncheckable_no_quarterly_xbrl']} |")
    (RUN / f"sue-coverage{tag}.md").write_text("\n".join(L) + "\n")
    log("wrote", RUN / f"sue-coverage{tag}.md")


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["events", "fetch", "llm", "llm2", "report", "all"])
    ap.add_argument("--pilot", type=int, default=0, help="only run N random 2019+ events (seed 20261027)")
    ap.add_argument("--limit-tickers", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--fetch-workers", type=int, default=8)
    a = ap.parse_args()
    t0 = time.time()
    if a.stage in ("events", "all") and not (a.pilot and (SUE / "events.jsonl").exists()) or not (SUE / "events.jsonl").exists():
        events = stage_events(a.limit_tickers)
    else:
        events = load_events()
    pilot_ids, work = None, events
    if a.pilot:
        pool = [e for e in events if e["source"] == "events-8k"]
        work = random.Random(20261027).sample(pool, a.pilot)
        pilot_ids = {e["accession"] for e in work}
        log("pilot events", len(work))
    if a.stage in ("fetch", "all"):
        stage_fetch(work, a.fetch_workers)
    if a.stage in ("llm", "all"):
        packs = [p for p in (build_pack(e) for e in work) if p and not p.get("no_exhibit")]
        stage_llm(packs, a.batch_size, a.workers)
    if a.stage in ("llm2", "all"):
        stage_llm2(work, a.batch_size, a.workers)
    if a.stage in ("report", "all"):
        stage_report(events, pilot_ids)
    log(f"done in {time.time()-t0:.0f}s; haiku calls this run={CALLS[0]}")


if __name__ == "__main__":
    main()
