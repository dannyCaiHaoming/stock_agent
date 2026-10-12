#!/usr/bin/env python3
"""操作方为明确既有任务准备可转交小包；不执行研究或修改任务。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from product.tools.prepare import agent_grant, _validate_grant_outputs
from product.tools.research import ResearchTools, _read_json, _write_json


def enriched_agent_grant(grant):
    packet = agent_grant(grant)
    return {**packet,
            "mcp_arguments": {key: packet[key] for key in ("task_ref", "task_token")},
            "specialist_args": json.dumps(packet, ensure_ascii=False, sort_keys=True, allow_nan=False)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--agent-grant", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        _validate_grant_outputs((args.output,))
        original = _read_json(args.agent_grant)
        if args.task_root.name != original["task_ref"]:
            raise ValueError("NATIVE_AGENT_GRANT_TASK_MISMATCH")
        task, _gate = ResearchTools(args.task_root, access_token=original["task_token"])._authorize()
        grant = {"task_ref": original["task_ref"], "task_token": original["task_token"], "task": task}
        packet = enriched_agent_grant(grant)
        for key in ("source_id", "as_of", "task_ref", "task_token", "role", "capability",
                    "security_id", "decision_cutoff", "task_hash"):
            if original[key] != packet[key]:
                raise ValueError("NATIVE_AGENT_GRANT_BINDING_INVALID")
        _write_json(args.output, packet)
    except (ValueError, OSError, KeyError, TypeError):
        print("NATIVE_AGENT_GRANT_PREPARATION_REJECTED", file=sys.stderr)
        return 1
    print(json.dumps({"status": "AGENT_GRANT_PREPARED_NOT_RESEARCHED", "task_ref": packet["task_ref"],
                      "source_id": packet["source_id"], "as_of": packet["as_of"],
                      "retrieved_at": packet["retrieved_at"], "model_calls": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
