"""只读检查当前组件，或显式渲染 profile/Skill 的批准版本镜像。"""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from product.runtime.versioning import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
