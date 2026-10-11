"""Central configuration for the project. Change values here, not inside scripts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "leadforge_bundle"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "reports" / "week1"
CHART_DIR = REPORT_DIR / "charts"

# --- leadforge generation settings (fixed so everyone gets the same data) ---
LEADFORGE_RECIPE = "b2b_saas_procurement_v1"
LEADFORGE_SEED = 42
LEADFORGE_MODE = "research_instructor"   # needed for closed_at / close_outcome (not in student_public)
LEADFORGE_DIFFICULTY = "intermediate"
LEADFORGE_N_LEADS = 5000

# --- modeling design ---
# Features may only use events up to SNAPSHOT_DAYS after lead creation (leakage control).
# This matches the observation window used by leadforge itself.
SNAPSHOT_DAYS = 30

# Final pipeline stages in leadforge's `leads.current_stage`
WON_STAGE = "closed_won"
LOST_STAGE = "closed_lost"
