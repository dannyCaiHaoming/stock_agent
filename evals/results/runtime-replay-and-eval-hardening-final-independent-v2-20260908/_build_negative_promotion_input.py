from __future__ import annotations

import hashlib
import json
from pathlib import Path


OUT = Path("/Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-independent-v2-20260908")
payload = json.loads((OUT / "promotion/input.json").read_text(encoding="utf-8"))
path = OUT / "test-evidence/assertion-negative/result.json"
payload["gate_id"] = "rrh-final-independent-v2-negative-assertion-20260908"
payload["artifacts"]["deterministic_tests"] = {
    "path": str(path),
    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
}
(OUT / "promotion/input-negative-assertion.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(OUT / "promotion/input-negative-assertion.json")
