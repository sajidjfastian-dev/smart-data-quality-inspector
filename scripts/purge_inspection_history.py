"""Retention cleanup entrypoint for an approved scheduled deployment job.

No schema mutations. Configure and verify scheduling before activating history.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inspection_history import HistoryRepository, HistoryUnavailable


if __name__ == "__main__":
    try:
        count = HistoryRepository().purge_expired()
    except HistoryUnavailable:
        print("Inspection history cleanup failed.", file=sys.stderr)
        sys.exit(1)
    print(f"Removed {count} expired inspection summaries.")
