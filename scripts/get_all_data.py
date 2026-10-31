"""Get every file a teammate needs to work locally: labels and Sentinel-2 chips.

One command for the data steps. It calls the existing scripts and reuses what is already on
disk, so running it again is cheap.

    python scripts/get_all_data.py                                  # the 48-record pilot (default)
    python scripts/get_all_data.py --scope cohorts --cohorts kenya_oaf_2019_2020 malawi_2023
    python scripts/get_all_data.py --scope all                      # 5 cohorts: ~11,400 records, ~25 GB, ~10 days serial
    python scripts/get_all_data.py --scope all --batch 3/10         # slice 3 of 10, for parallel jobs
    python scripts/get_all_data.py --scope all --plan               # offline: counts and a size/time estimate
    python scripts/get_all_data.py --scope all --status             # offline: complete / failed / not on disk so far

Labels (data/audit) are committed to git, so they are only checked. The exit code is the
downloader's: non-zero when any record failed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import os
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))  # the step scripts are plain files, not a package
import step5_download_imagery  # noqa: E402  scripts/step5_download_imagery.py
from cropyield.data.cohorts import AUDIT_DIR, COHORTS, date_overrides, load_cohort  # noqa: E402
from cropyield.longpath import replace_file  # noqa: E402
from cropyield.satellite.records import record_folders  # noqa: E402

IMAGERY_DIR = ROOT / "data" / "imagery" / "sentinel2"  # the downloader's default output folder
STEPS = 4
# Measured on the 48-record pilot on a laptop (28 Oct 2026). Real values vary with cloud cover.
MB_PER_RECORD = 2
MINUTES_PER_RECORD = 1
# The week-0 pilot (docs/DECISIONS.md, 28 Oct 2026): per cohort, the first rows of its screened audit
# file in file order, split evenly over the harvest years. The sizes are in docs/ROADMAP.md.
PILOT_SIZES = {"malawi_2023": 12, "kenya_oaf_2019_2020": 12, "zimbabwe_2024": 16, "zimbabwe_lacuna_2022_2023": 8}
PILOT_PATH = ROOT / "configs" / "sentinel2_windows_pilot48.csv"


def parse_batch(text: str) -> tuple[int, int]:
    """'3/10' -> (3, 10): this job runs slice 3 of 10 equal, contiguous slices of the records."""
    try:
        index, count = map(int, text.split("/"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"--batch wants i/n, like 3/10, not {text!r}") from None
    if not 1 <= index <= count:
        raise argparse.ArgumentTypeError(f"--batch {text}: need 1 <= i <= n")
    return index, count


def batch_slice(total: int, index: int, count: int) -> tuple[int, int]:
    """(offset, size) of slice `index` of `count` over `total` records; the slices cover every record once."""
    start = (index - 1) * total // count
    stop = index * total // count
    return start, stop - start


def warn_if_onedrive() -> None:
    """OneDrive syncs and locks files under the repository while the downloader writes them."""
    if "OneDrive" in str(ROOT):
        print("WARNING: this clone is inside OneDrive. Long-path errors and file locks broke downloads "
              "on 28 Oct 2026; a clone outside OneDrive (for example C:\\Dev) avoids both.")


def scope_cohorts(scope: str, cohorts: list[str] | None) -> list[str]:
    """Cohort names of the scope, in COHORTS order (the order the downloader processes them)."""
    if scope == "pilot":
        chosen = list(PILOT_SIZES)
    elif scope == "all":
        chosen = list(COHORTS)
    else:
        chosen = cohorts
    return [name for name in COHORTS if name in chosen]


def label_files(dataset: str) -> list[Path]:
    """The committed audit files one dataset needs: the screened CSV, plus field polygons for Malawi."""
    files = [AUDIT_DIR / f"{dataset}_screened_candidates.csv"]
    if dataset.startswith("malawi_"):
        files.append(AUDIT_DIR / f"{dataset}_candidates_wgs84.geojson")
    return files


def check_labels(cohort_names: list[str]) -> None:
    """Step 1: stop with a clear message when an audit file is missing; print labelled records per cohort."""
    for name in cohort_names:
        for path in label_files(COHORTS[name].dataset):
            if not path.exists():
                raise FileNotFoundError(f"{path} is missing. Labels are committed to git, so check "
                                        f"`git status` and restore it with `git checkout -- {path}`")
        print(f"  {name:<28} {len(load_cohort(name)):>6} labelled records")


def pilot_rows(sizes: dict[str, int] = PILOT_SIZES) -> pd.DataFrame:
    """Cohort rows of the pilot: per cohort and harvest year, the first rows in audit-file order."""
    parts = []
    for name, size in sizes.items():
        cohort = load_cohort(name)
        years = sorted(cohort["year"].unique())
        if size % len(years):
            raise ValueError(f"{name}: {size} records do not split evenly over the years {years}")
        for year in years:
            rows = cohort[cohort["year"] == year].head(size // len(years))
            if len(rows) < size // len(years):
                raise ValueError(f"{name} {year}: only {len(rows)} rows")
            parts.append(rows)
    return pd.concat(parts, ignore_index=True)


def window_table(rows: pd.DataFrame) -> pd.DataFrame:
    """Window-file rows for the downloader: cohort, dataset, source_id and the fixed season window."""
    table = date_overrides(rows)
    table.insert(0, "cohort", rows["cohort"].to_numpy())
    return table


def window_rows(scope: str, cohort_names: list[str]) -> pd.DataFrame:
    """Cohort rows to download. For the pilot, exactly the rows pilot_rows picks."""
    if scope == "pilot":
        return pilot_rows()
    return pd.concat([load_cohort(name) for name in cohort_names], ignore_index=True)


def window_path(scope: str, cohort_names: list[str], output_dir: Path) -> Path:
    """Where the window file goes."""
    if scope == "pilot":
        return PILOT_PATH  # 48 rows, committed in configs/
    # Other window files have thousands of rows. They are inputs of one download, so they live
    # beside its output (git-ignored, and moved along with --output-dir) instead of in configs/.
    name = "all" if scope == "all" else "_".join(cohort_names)
    return output_dir / "windows" / f"sentinel2_windows_{name}.csv"


def write_windows(rows: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Step 2: write cohort,dataset,source_id,start_date,end_date for the downloader."""
    table = window_table(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Parallel --batch jobs write this same file at the same time. Their renames can collide (one of
    # 32 slices failed that way on 30 Oct), so skip the write when an earlier slice already made the file.
    if path.exists() and path.read_bytes() == table.to_csv(index=False, lineterminator="\n").encode("utf-8"):
        return table
    # Otherwise write beside it, then rename in one step.
    temporary = path.with_name(f"{path.name}.{os.getpid()}.part")
    table.to_csv(temporary, index=False, lineterminator="\n")
    replace_file(temporary, path)
    return table


def downloader_argv(command: str, cohort_names: list[str], window_file: Path, output_dir: Path,
                    offset: int, size: int) -> list[str]:
    """Command line for scripts/step5_download_imagery.py: exactly the listed records, one slice of them."""
    datasets = [COHORTS[name].dataset for name in cohort_names]
    return [command, "--datasets", *datasets, "--date-overrides", str(window_file), "--only-listed",
            "--output-dir", str(output_dir), "--offset", str(offset), "--limit", str(size)]


def record_status(output_dir: Path) -> dict[tuple[str, str, str, str], str]:
    """(dataset, source_id, start_date, end_date) -> status, from every record.json under output_dir.

    The window is part of the key: a folder downloaded for another window does not count.
    """
    status = {}
    for _, record in record_folders(output_dir):
        meta = record["record"]
        status[(meta["dataset"], meta["source_id"], meta["start_date"], meta["end_date"])] = record["status"]
    return status


def print_summary(selected: pd.DataFrame, output_dir: Path) -> None:
    """Step 4: per cohort, how many of this job's records are complete, failed, or not on disk."""
    status = record_status(output_dir)
    for cohort, rows in selected.groupby("cohort", sort=False):
        keys = zip(rows["dataset"], rows["source_id"], rows["start_date"], rows["end_date"])
        counts = Counter(status.get(key, "not_on_disk") for key in keys)
        text = ", ".join(f"{n} {name}" for name, n in sorted(counts.items()))
        print(f"  {cohort:<28} {len(rows):>6} records: {text}")


def print_plan(selected: pd.DataFrame) -> None:
    """Step 4 for --plan: records per cohort and a rough size and time estimate."""
    for cohort, rows in selected.groupby("cohort", sort=False):
        print(f"  {cohort:<28} {len(rows):>6} records")
    n = len(selected)
    hours = n * MINUTES_PER_RECORD / 60
    print(f"  {n} records: about {n * MB_PER_RECORD / 1000:.1f} GB and {hours:.0f} hours ({hours / 24:.1f} days) "
          f"on one laptop. This is an estimate from the pilot ({MB_PER_RECORD} MB and {MINUTES_PER_RECORD} min "
          "per record); the real values vary.")


def arguments(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scope", choices=("pilot", "cohorts", "all"), default="pilot",
                        help="pilot: the 48 week-0 records (default); cohorts: those in --cohorts; all: every cohort")
    parser.add_argument("--cohorts", nargs="+", choices=list(COHORTS), help="cohort names, with --scope cohorts")
    parser.add_argument("--batch", type=parse_batch, default="1/1",
                        help="i/n: run slice i of n equal slices of the records, for parallel jobs (default 1/1)")
    parser.add_argument("--plan", action="store_true", help="offline: count records, estimate size and time, download nothing")
    parser.add_argument("--status", action="store_true",
                        help="offline: how many records of the scope are complete, failed or not on disk; download nothing")
    parser.add_argument("--output-dir", type=Path, default=IMAGERY_DIR, help="where the chips and window file go")
    args = parser.parse_args(argv)
    if args.scope == "cohorts" and not args.cohorts:
        parser.error("--scope cohorts needs --cohorts <name> ...")
    if args.scope != "cohorts" and args.cohorts:
        parser.error("--cohorts only goes with --scope cohorts")
    return args


def main(argv=None) -> int:
    args = arguments(argv)
    warn_if_onedrive()
    cohort_names = scope_cohorts(args.scope, args.cohorts)
    if args.status:  # safe while download jobs run: it only reads record.json files
        print(f"Status of --scope {args.scope} under {args.output_dir}")
        print_summary(window_table(window_rows(args.scope, cohort_names)), args.output_dir)
        return 0

    print(f"[1/{STEPS}] Labels")
    check_labels(cohort_names)

    print(f"[2/{STEPS}] Window file")
    path = window_path(args.scope, cohort_names, args.output_dir)
    table = write_windows(window_rows(args.scope, cohort_names), path)
    offset, size = batch_slice(len(table), *args.batch)
    selected = table.iloc[offset:offset + size]
    print(f"  {len(table)} records -> {path}")
    print(f"  this job: rows {offset} to {offset + size} (--batch {args.batch[0]}/{args.batch[1]})")
    if selected.empty:
        print("  nothing to do: more batches than records")
        return 0

    print(f"[3/{STEPS}] Sentinel-2 chips" + (" (plan only, offline)" if args.plan else ""))
    command = "plan" if args.plan else "download"
    code = step5_download_imagery.main(downloader_argv(command, cohort_names, path, args.output_dir, offset, size))

    print(f"[4/{STEPS}] Summary")
    if args.plan:
        print_plan(selected)
    else:
        print_summary(selected, args.output_dir)
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
