from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path


ROOT = Path("/Users/caihaoming/Documents/stock_agent")
OUT = ROOT / "evals/results/runtime-replay-and-eval-hardening-final-independent-v2-20260908/commands"


parser = argparse.ArgumentParser()
parser.add_argument("label")
parser.add_argument("--cwd", default=str(ROOT))
parser.add_argument("--stdin")
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
if args.command and args.command[0] == "--":
    args.command = args.command[1:]
if not args.command:
    raise SystemExit("missing command")

started = dt.datetime.now(dt.timezone.utc).isoformat()
stdin_bytes = Path(args.stdin).read_bytes() if args.stdin else None
env = os.environ.copy()
env["TMPDIR"] = "/private/tmp/stock-agent-final-independent-v2-20260908"
env["PYTHONDONTWRITEBYTECODE"] = "1"
proc = subprocess.run(
    args.command,
    cwd=args.cwd,
    env=env,
    input=stdin_bytes,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
ended = dt.datetime.now(dt.timezone.utc).isoformat()
stdout_path = OUT / f"{args.label}.stdout.log"
stderr_path = OUT / f"{args.label}.stderr.log"
stdout_path.write_bytes(proc.stdout)
stderr_path.write_bytes(proc.stderr)
event = {
    "schema_version": "independent-command-event/1.0.0",
    "label": args.label,
    "command": args.command,
    "cwd": args.cwd,
    "tmpdir": env["TMPDIR"],
    "started_at": started,
    "ended_at": ended,
    "exit_code": proc.returncode,
    "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
    "stderr_sha256": hashlib.sha256(proc.stderr).hexdigest(),
    "stdin_path": args.stdin,
    "stdin_sha256": hashlib.sha256(stdin_bytes).hexdigest() if stdin_bytes is not None else None,
}
(OUT / f"{args.label}.event.json").write_text(json.dumps(event, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(event, ensure_ascii=False, indent=2))
if proc.stdout:
    print("--- stdout tail ---")
    print(proc.stdout.decode("utf-8", "replace")[-4000:])
if proc.stderr:
    print("--- stderr tail ---")
    print(proc.stderr.decode("utf-8", "replace")[-4000:])
raise SystemExit(proc.returncode)
