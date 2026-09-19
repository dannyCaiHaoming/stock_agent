"""Research Browser 命令行入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from product.web.app import ResearchBrowser, build_server
from product.web.read_only import ArtifactCatalog, BrowserDataError, ReadOnlyResearchMemory


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="只读浏览本机已保存投研资料")
    value.add_argument("--memory-root", type=Path, required=True, help="现有 Research Memory 根目录（不会创建或迁移）")
    value.add_argument("--run-dir", type=Path, action="append", default=[], help="显式冻结运行目录，可重复")
    value.add_argument("--run-root", type=Path, action="append", default=[], help="只发现直属 manifest 子目录的运行根目录，可重复")
    value.add_argument("--port", type=int, default=8765, help="本机端口，默认 8765")
    value.add_argument("--check", action="store_true", help="只执行配置与只读诊断")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not 0 <= args.port <= 65535:
        raise SystemExit("port must be between 0 and 65535")
    memory = None
    memory_error = None
    try:
        memory = ReadOnlyResearchMemory(args.memory_root)
    except BrowserDataError as exc:
        memory_error = str(exc)
    artifacts = ArtifactCatalog(run_dirs=args.run_dir, run_roots=args.run_root)
    application = ResearchBrowser(memory, artifacts, memory_error=memory_error)
    if args.check:
        print(json.dumps({
            "status": "READY" if memory else "PARTIAL",
            "listen_host": "127.0.0.1",
            "memory": memory.diagnostic() if memory else {"status": "UNAVAILABLE", "code": memory_error},
            "artifacts": artifacts.diagnostic(),
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if memory else 2
    server = build_server(application, port=args.port)
    actual_port = server.server_address[1]
    print(f"Research Browser: http://127.0.0.1:{actual_port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
