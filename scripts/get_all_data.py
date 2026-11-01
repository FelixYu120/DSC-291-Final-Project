"""Get every file a teammate needs to work locally: labels and Sentinel-2 chips.

One command for the data steps. It calls the existing scripts and reuses what is already on
disk, so running it again is cheap.

    python scripts/get_all_data.py                                  # the 48-record pilot (default)
    python scripts/get_all_data.py --scope cohorts --cohorts kenya_oaf_2019_2020 malawi_2023
    python scripts/get_all_data.py --scope all                      # 5 cohorts: ~11,400 records, ~25 GB, ~10 days in one process
    python scripts/get_all_data.py --scope all --batch 3/32         # slice 3 of 32, for parallel jobs: ~4 hours for all 32
    python scripts/get_all_data.py --scope all --plan               # offline: counts and a size/time estimate
    python scripts/get_all_data.py --scope all --status             # offline: complete / failed / not on disk so far

Labels (data/audit) are committed to git, so they are only checked. The exit code is the
downloader's: non-zero when any record failed.

The download cells of notebooks/data_guide.ipynb call notebook_download. It asks for a typed yes,
runs the slices in the background with a loading bar, builds the database and reports.
"""
from __future__ import annotations

import argparse
from collections import Counter
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))  # the step scripts are plain files, not a package
import step5_download_imagery  # noqa: E402  scripts/step5_download_imagery.py
from cropyield.data.cohorts import AUDIT_DIR, COHORTS, date_overrides, load_cohort  # noqa: E402
from cropyield.data.database import SCENE_LIST, scene_differences  # noqa: E402
from cropyield.longpath import replace_file  # noqa: E402
from cropyield.satellite.chips import FAILED_DOWNLOAD  # noqa: E402
from cropyield.satellite.records import RecordScan  # noqa: E402

IMAGERY_DIR = ROOT / "data" / "imagery" / "sentinel2"  # the downloader's default output folder
STEPS = 4
# Measured on the 48-record pilot on a laptop (28 Oct 2026). Real values vary with cloud cover.
MB_PER_RECORD = 2
# Measured on the full download (30 Oct 2026, docs/DECISIONS.md). A read fetches whole image blocks, so the
# line moves far more than the disk keeps. 32 slices made 45 fields per minute and filled a 40 MB/s line.
MB_MOVED_PER_RECORD = 60
DEFAULT_SLICES = 32
FIELDS_PER_MINUTE_PER_SLICE = 45 / DEFAULT_SLICES
REFRESH_SECONDS = 5
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
    return RecordScan(output_dir).statuses()


def record_keys(rows: pd.DataFrame):
    """The record_status key of each window-file row."""
    return zip(rows["dataset"], rows["source_id"], rows["start_date"], rows["end_date"])


def print_summary(selected: pd.DataFrame, output_dir: Path) -> None:
    """Step 4: per cohort, how many of this job's records are complete, failed, or not on disk."""
    status = record_status(output_dir)
    for cohort, rows in selected.groupby("cohort", sort=False):
        counts = Counter(status.get(key, "not_on_disk") for key in record_keys(rows))
        text = ", ".join(f"{n} {name}" for name, n in sorted(counts.items()))
        print(f"  {cohort:<28} {len(rows):>6} records: {text}")


def format_time(seconds: float) -> str:
    """12 min, or 4 h 12 min."""
    minutes = max(1, round(seconds / 60))
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60} min"


def cost_text(records: int, slices: int = DEFAULT_SLICES) -> str:
    """What a download costs: GB moved over the line, GB kept on disk, and the time in parallel slices."""
    minutes = records / (slices * FIELDS_PER_MINUTE_PER_SLICE)
    return (f"{records:,} records: about {records * MB_MOVED_PER_RECORD / 1000:.1f} GB moved, "
            f"about {records * MB_PER_RECORD / 1000:.1f} GB kept, "
            f"about {format_time(minutes * 60)} with {slices} parallel slices")


def print_plan(selected: pd.DataFrame, total: int, slices: int) -> None:
    """Step 4 for --plan: records per cohort, then what the whole scope costs in parallel slices."""
    for cohort, rows in selected.groupby("cohort", sort=False):
        print(f"  {cohort:<28} {len(rows):>6} records")
    print(f"  {cost_text(total, slices)}. This is an estimate from the full download of 30 Oct 2026: "
          f"{MB_MOVED_PER_RECORD} MB moved and {MB_PER_RECORD} MB kept per record, and "
          f"{FIELDS_PER_MINUTE_PER_SLICE * DEFAULT_SLICES:.0f} fields per minute with {DEFAULT_SLICES} slices. "
          "More slices help only until the line is full, and the real values vary.")


def field_counts(table: pd.DataFrame, status: dict) -> tuple[int, int]:
    """(done, failed) among the records of a window table. A failed record gets a new try on the next run."""
    counts = Counter(status.get(key, "not_on_disk") for key in record_keys(table))
    failed = sum(counts[name] for name in FAILED_DOWNLOAD)
    return len(table) - counts["not_on_disk"] - failed, failed


def seconds_left(total: int, done: int, done_at_start: int, elapsed: float) -> float | None:
    """Time left at the speed of this run; None until it has finished a record of its own.

    Records already on disk at the start do not count, so a restart does not look fast.
    """
    if done <= done_at_start:
        return None
    return (total - done) * elapsed / (done - done_at_start)


def bar_text(done: int, total: int, failed: int, gigabytes: float, left: float | None) -> str:
    """The line under the loading bar."""
    if done == total:
        time_text = "finished"
    else:
        time_text = "time left not known yet" if left is None else f"about {format_time(left)} left"
    failed_text = f" | {failed:,} failed" if failed else ""
    return f"{done / total:.1%} done | {done:,} of {total:,} fields{failed_text} | {gigabytes:.2f} GB on disk | {time_text}"


def bar_html(done: int, total: int, failed: int, gigabytes: float, left: float | None) -> str:
    return (f'<progress value="{done}" max="{total}" style="width:100%"></progress>'
            f"<pre>{bar_text(done, total, failed, gigabytes, left)}</pre>")


def loading_bar():
    """Show a bar in the cell output, and return the function that replaces it. Only the notebook needs IPython."""
    from IPython.display import HTML, display

    handle = display(HTML("<pre>Reading what is already on disk ...</pre>"), display_id=True)
    return lambda html: handle.update(HTML(html))


def typed_yes(question: str) -> bool:
    """True only for a typed yes. A run with no keyboard, such as nbconvert, counts as no."""
    try:
        return input(question).strip().lower() == "yes"
    except (EOFError, NotImplementedError):
        return False


def presto_rows(database: Path) -> int:
    """Rows in presto_embeddings of an existing database. The build leaves that table empty."""
    if not database.exists():
        return 0
    with duckdb.connect(str(database), read_only=True) as con:
        return con.execute("SELECT count(*) FROM presto_embeddings").fetchone()[0]


def stop_with_parent() -> None:
    """End this process when the kernel that started it ends: the pipe on stdin then closes."""
    def watch() -> None:
        try:
            os.read(sys.stdin.fileno(), 1)
        finally:
            os._exit(1)
    threading.Thread(target=watch, daemon=True).start()


def background_options() -> dict:
    """Popen options for a step of the notebook: no console window for each process on Windows.

    One matrix thread per process: these steps do no matrix math, and numpy otherwise reserves memory
    per CPU core. On 20 cores that is 686 MB per slice, so 32 slices filled the page file at the start
    and two died (1 Nov 2026). One thread needs 76 MB.
    """
    return {"cwd": ROOT, "env": {**os.environ, "PYTHONIOENCODING": "utf-8", "OPENBLAS_NUM_THREADS": "1"},
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def start_slices(scope: str, slices: int, output_dir: Path) -> list[subprocess.Popen]:
    """Start slices 1 to n of the scope in the background. Each one writes a log beside the chips."""
    logs = output_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    processes = []
    for index in range(1, slices + 1):
        command = [sys.executable, str(Path(__file__).resolve()), "--scope", scope, "--batch", f"{index}/{slices}",
                   "--output-dir", str(output_dir), "--stop-with-parent"]
        with open(logs / f"slice_{index}_of_{slices}.log", "ab") as log:
            processes.append(subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                              **background_options()))
    return processes


def stop_slices(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        process.terminate()
        process.stdin.close()
    for process in processes:
        process.wait()


def watch_slices(processes: list[subprocess.Popen], table: pd.DataFrame, scan: RecordScan,
                 show, refresh: float = REFRESH_SECONDS) -> None:
    """Update the loading bar until every slice has stopped."""
    started, done_at_start = time.monotonic(), None
    while True:
        running = any(process.poll() is None for process in processes)  # asked first: the last scan sees every record
        done, failed = field_counts(table, scan.statuses())
        done_at_start = done if done_at_start is None else done_at_start
        left = seconds_left(len(table), done, done_at_start, time.monotonic() - started)
        show(bar_html(done, len(table), failed, scan.gigabytes(), left))
        if not running:
            return
        time.sleep(refresh)


def run_database_build(data_dir: Path, output_dir: Path) -> None:
    """scripts/step6_build_database.py on these folders. It prints its table counts, or its error."""
    command = [sys.executable, str(ROOT / "scripts" / "step6_build_database.py"),
               "--db", str(data_dir / "cropyield.duckdb"), "--imagery-dir", str(output_dir),
               "--mosaiks-dir", str(data_dir / "features" / "mosaiks"), "--workers", str(min(16, os.cpu_count() or 1))]
    result = subprocess.run(command, capture_output=True, encoding="utf-8", check=False, **background_options())
    print(result.stdout + result.stderr)


def report(table: pd.DataFrame, status: dict, database: Path) -> None:
    """The last two lines of a download cell."""
    complete = sum(status.get(key) == "complete" for key in record_keys(table))
    total = len(table)
    print(f"Complete: yes, all {total:,} records are complete." if complete == total else
          f"Complete: no, {complete:,} of {total:,} records are complete. Run this cell again: "
          "it downloads only the missing fields.")
    if database.exists():
        on_disk, differ = scene_differences(database, SCENE_LIST)
        print(f"Same scenes: {on_disk - len(differ):,} of {on_disk:,} records hold the same scenes as the frozen list.")
    else:
        print("Same scenes: not checked, because there is no database.")


def notebook_download(scope: str, slices: int, data_dir: Path) -> None:
    """A download cell of the guide: ask, run the slices with a loading bar, build the database, report."""
    output_dir, database = data_dir / "imagery" / "sentinel2", data_dir / "cropyield.duckdb"
    cohort_names = scope_cohorts(scope, None)
    rows = window_rows(scope, cohort_names)
    table = window_table(rows)
    print("Checking what is already on disk ...")
    scan = RecordScan(output_dir)
    done, _ = field_counts(table, scan.statuses())
    missing = len(table) - done
    print(f"Cost:    {cost_text(len(table), slices)}.")
    print(f"On disk: {done:,} of {len(table):,} fields are done ({done / len(table):.1%}). "
          + (f"This run gets only the other {missing:,}." if missing else "This run fetches nothing new."))
    print("Stop:    you can stop at any time. Every finished field stays on disk.")
    print("Restart: run this cell again. It checks the disk and downloads only the missing fields.")
    if not typed_yes("Type yes to start the download: "):
        print("No download started.")
        return
    build = True
    embeddings = presto_rows(database)
    if embeddings:  # asked now, because nobody waits at the keyboard until the chips are done
        print(f"The database holds {embeddings:,} rows in presto_embeddings. The database build removes them.")
        build = typed_yes("Type yes to build the database after the chips: ")
    warn_if_onedrive()
    check_labels(cohort_names)
    # Written here, once, so that the slices find the window file ready and do not race to write it.
    write_windows(rows, window_path(scope, cohort_names, output_dir))
    show = loading_bar()
    processes = start_slices(scope, slices, output_dir)
    print(f"{slices} parallel slices started. Their logs are in {output_dir / 'logs'}.")
    stopped = False
    try:
        watch_slices(processes, table, scan, show)
    except KeyboardInterrupt:
        stopped = True
    finally:
        stop_slices(processes)
    status = scan.statuses()
    if stopped:
        done, _ = field_counts(table, status)
        print(f"Stopped at {done / len(table):.1%}: {done:,} of {len(table):,} fields are on disk. "
              "Run this cell again: it downloads only the missing fields.")
        return
    errors = sum(process.returncode != 0 for process in processes)
    if errors:
        print(f"{errors} of {slices} slices ended with an error. Their logs are in {output_dir / 'logs'}.")
    if not build:
        print("Database not built: the existing database stays as it is.")
    elif field_counts(table, status)[0] == 0:
        print("Database not built: no record is done. Read the logs, then press Run again.")
    else:
        print("Building the database ...")
        run_database_build(data_dir, output_dir)
    report(table, status, database)


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
    parser.add_argument("--stop-with-parent", action="store_true",
                        help="end when the pipe on stdin closes; the notebook starts its slices this way")
    args = parser.parse_args(argv)
    if args.scope == "cohorts" and not args.cohorts:
        parser.error("--scope cohorts needs --cohorts <name> ...")
    if args.scope != "cohorts" and args.cohorts:
        parser.error("--cohorts only goes with --scope cohorts")
    return args


def main(argv=None) -> int:
    args = arguments(argv)
    if args.stop_with_parent:
        stop_with_parent()
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
        print_plan(selected, len(table), args.batch[1] if args.batch[1] > 1 else DEFAULT_SLICES)
    else:
        print_summary(selected, args.output_dir)
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
