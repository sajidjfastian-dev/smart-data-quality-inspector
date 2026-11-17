#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Replit's managed Python directory, not a separate virtual environment.
python -m pip install --disable-pip-version-check --no-input \
  --target .pythonlibs/lib/python3.12/site-packages --upgrade \
  -r requirements.txt

# Development database only; production schema remains managed by Publish.
python scripts/seed_demo.py --development-schema
