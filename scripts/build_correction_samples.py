"""Rebuild public-data demonstration files from the pinned, verified snapshot."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from public_sample import write_workspace

if __name__ == "__main__":
    write_workspace()
