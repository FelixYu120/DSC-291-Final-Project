"""Produce source-backed Kenya date and coordinate review sidecars; retain every original."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cropyield.data.kenya_review import run_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/runs/kenya_review")
    args = parser.parse_args()
    path = run_review(args.output_root)
    print(path)
    print((path / "summary.json").read_text())


if __name__ == "__main__":
    main()
