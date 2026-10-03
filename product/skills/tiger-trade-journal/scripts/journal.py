"""Use coinstalled code; never infer private state from this script's location."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from trading_journal.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
