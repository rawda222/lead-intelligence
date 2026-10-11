"""Step 1: generate the synthetic CRM bundle with leadforge (deterministic seed).

Usage:  python -m src.data.generate
"""
import shutil
import subprocess
import sys

from src import config


def main(force: bool = False) -> None:
    if config.RAW_DIR.exists():
        if not force:
            print(f"Raw bundle already exists at {config.RAW_DIR}. Use --force to regenerate.")
            return
        shutil.rmtree(config.RAW_DIR)
    config.RAW_DIR.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "leadforge", "generate",
        "--recipe", config.LEADFORGE_RECIPE,
        "--seed", str(config.LEADFORGE_SEED),
        "--mode", config.LEADFORGE_MODE,
        "--difficulty", config.LEADFORGE_DIFFICULTY,
        "--n-leads", str(config.LEADFORGE_N_LEADS),
        "--out", str(config.RAW_DIR),
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print("Done.")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
