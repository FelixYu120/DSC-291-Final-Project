"""Replay frozen Zimbabwe experiments with their recorded code and current verified data.

The main branch can evolve its shared validation modules without rewriting historical
manifests. This runner extracts code from the recorded commit into a temporary directory,
checks the full experiment hash chain, and requires a new destination for every replay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
REVISION = "e1235944f092359e4ed29d3ef20cef1f17085d10"
CODE_PATHS = ["src", "scripts", "configs", "docs", "sql", "requirements.txt", "pyproject.toml"]
RELEASES = ["data/runs/zimbabwe_merge_v1", "data/runs/zimbabwe_transfer_diagnosis_v1",
            "data/processed/zimbabwe_weather_v1", "data/runs/zimbabwe_weather_v1",
            "data/runs/zimbabwe_weather_compact_v1"]
STAGES = {
    "merge": ("step9_compare_zimbabwe_merge.py", "--output", ""),
    "diagnosis": ("step10_diagnose_zimbabwe_transfer.py", "--output", ""),
    "weather": ("step11_add_zimbabwe_weather.py", "--output", ""),
    "weather-models": ("step12_compare_zimbabwe_weather.py", "--output", ""),
    "compact": ("step13_compare_compact_weather.py", "--output", ""),
    "verify-weather": ("verify_zimbabwe_weather.py", "--report", ".json"),
    "verify-compact": ("verify_compact_weather.py", "--output", ".json"),
    "candidate": ("compare_compact_candidate.py", None, ".csv"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def relative_path(name: str) -> Path:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"Manifest path must remain inside the snapshot: {name}")
    return Path(*path.parts)


def verify_paths(snapshot: Path, expected: dict[str, str]) -> int:
    for name, digest in expected.items():
        path = snapshot / relative_path(name)
        if not path.is_file():
            raise FileNotFoundError(f"Missing recorded input/output: {name}")
        if sha256(path) != digest:
            raise ValueError(f"Recorded hash differs: {name}")
    return len(expected)


def recorded_paths(root: Path, revision: str = REVISION) -> dict[str, str]:
    """Trust manifests from Git history, not a potentially edited working-tree copy."""
    expected = {}
    for directory in RELEASES:
        name = f"{directory}/manifest.json"
        raw = subprocess.check_output(["git", "-C", str(root), "show", f"{revision}:{name}"])
        manifest = json.loads(raw)
        entries = {name: hashlib.sha256(raw).hexdigest(), **manifest["inputs"]}
        entries.update({f"{directory}/{key}": value["sha256"] for key, value in manifest["outputs"].items()})
        for key, value in entries.items():
            relative_path(key)
            if key in expected and expected[key] != value:
                raise ValueError(f"Historical releases disagree about {key}")
            expected[key] = value
    return expected


def create_snapshot(root: Path, destination: Path, revision: str = REVISION) -> None:
    try:
        subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{revision}^{{commit}}"],
                       check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Historical commit {revision} is unavailable. Fetch full repository history before replaying.") from exc
    archive = destination / "code.tar"
    subprocess.run(["git", "-C", str(root), "archive", "--format=tar", "-o", str(archive),
                    revision, *CODE_PATHS], check=True)
    with tarfile.open(archive) as source:
        source.extractall(destination, filter="data")
    archive.unlink()
    # The historical scripts read these inputs; all output destinations are separate.
    (destination / "data").symlink_to(root / "data", target_is_directory=True)


def command_for(stage: str, snapshot: Path, output: Path) -> list[str]:
    script, flag, _ = STAGES[stage]
    path = snapshot / "scripts" / script
    if stage == "candidate":
        expression = "import runpy,sys; runpy.run_path(sys.argv[1])['compare']().to_csv(sys.argv[2],index=False)"
        return [sys.executable, "-c", expression, str(path), str(output)]
    return [sys.executable, str(path), flag, str(output)]


def destination_for(stage: str, output: Path | None, root: Path = ROOT) -> Path:
    if output is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        output = root / "data/runs/reproductions" / f"{stage}-{stamp}{STAGES[stage][2]}"
    output = output.resolve()
    if output.exists() or Path(str(output) + ".reproduction.json").exists():
        raise FileExistsError(f"Choose a new destination; refusing to overwrite {output}")
    # A verifier also writes a support CSV beside its receipt. Keep that side effect
    # in a private output directory and copy only the requested receipt out.
    return output


def replay(stage: str, output: Path | None = None, root: Path = ROOT) -> Path:
    output = destination_for(stage, output, root)
    expected = recorded_paths(root)
    with tempfile.TemporaryDirectory(prefix="zimbabwe-recorded-code-") as temp:
        snapshot = Path(temp)
        create_snapshot(root, snapshot)
        count = verify_paths(snapshot, expected)
        print(f"Verified {count} recorded inputs/outputs using code at {REVISION}.", flush=True)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(snapshot / "src")
        env["CROPYIELD_DATA_DIR"] = str(snapshot / "data")
        env.setdefault("MPLCONFIGDIR", str(snapshot / ".matplotlib"))
        env.setdefault("LOKY_MAX_CPU_COUNT", "1")
        output.parent.mkdir(parents=True, exist_ok=True)
        file_result = bool(STAGES[stage][2])
        generated = snapshot / ("receipt" + STAGES[stage][2]) if file_result else output
        subprocess.run(command_for(stage, snapshot, generated), cwd=snapshot, env=env, check=True)
        verify_paths(snapshot, expected)
        if file_result:
            # Exclusive creation protects a destination that appeared while the replay ran.
            with output.open("xb") as stream:
                stream.write(generated.read_bytes())
        receipt = {"stage": stage, "recorded_code_commit": REVISION,
                   "inputs_and_original_outputs_verified_before_and_after": count,
                   "original_releases_modified": False, "output": str(output),
                   "runner_sha256": sha256(Path(__file__)), "python": sys.version.split()[0]}
        with Path(str(output) + ".reproduction.json").open("x") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
    print(f"Saved replay output: {output}", flush=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=STAGES, nargs="?", default="verify-compact")
    parser.add_argument("--output", type=Path, help="New output file or directory; existing paths are never overwritten")
    args = parser.parse_args()
    replay(args.stage, args.output)
