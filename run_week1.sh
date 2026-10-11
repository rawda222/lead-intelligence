#!/usr/bin/env bash
set -euo pipefail
python -m src.data.generate
python -m src.data.build_master
python -m src.analysis.eda
pytest -q
