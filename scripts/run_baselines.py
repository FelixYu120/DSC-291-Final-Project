"""Run the three spatial baselines: python scripts/run_baselines.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cropyield.baselines.experiment import main

if __name__ == '__main__':
    raise SystemExit(main())
