"""The scripts/ layout: every ROOT is the repository root, the top level holds only numbered steps, and the live
docs and code name only script paths that exist."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
ROOT_LINE = re.compile(r"Path\(__file__\)\.resolve\(\)\.parents\[(\d+)\]")
# A path from the repository root or relative to it (../scripts/...), not _parked/scripts/... or other folders.
SCRIPT_PATH = re.compile(r"(?<![\w\-/.])(?:\.\./)*(scripts/[A-Za-z0-9_./]+?\.py)")
# Old names that live files quote on purpose, as what another recorded file still says.
HISTORICAL = {"scripts/download_vision_guided_yield_data.py"}  # docs/DATASET.md 2.5: named in data/audit notes

# Files whose bytes a manifest or receipt records, or that are dated history: they keep the paths of their time.
FROZEN_PREFIXES = ("data/", "_parked/", "docs/archive/", "results/merge_v2/", "results/weather_v2/full/",
                   "results/weather_v2/compact/", "results/aggregation_v2/", "results/multiyear_v2/")
FROZEN = {
    "docs/DECISIONS.md",                      # append-only log
    "docs/DATA_V2_PLAN.md",                   # pre-registered plan, kept word for word
    "notebooks/data_guide_2_zimbabwe.ipynb",  # bytes recorded by data_guide_2_zimbabwe.validation.json
    "tests/test_zimbabwe_reproduction.py",    # asserts a path inside the recorded-revision snapshot
    "tests/test_repo_layout.py",
}


def python_files(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*.py") if "__pycache__" not in path.parts)


def test_every_script_root_is_the_repository_root():
    checked = 0
    for script in python_files(SCRIPTS):
        for level in ROOT_LINE.findall(script.read_text(encoding="utf-8")):
            assert script.resolve().parents[int(level)] == REPO, f"{script.relative_to(REPO)} parents[{level}]"
            checked += 1
    assert checked >= 30  # 33 of the 34 scripts define ROOT this way; compare_data_v2 imports it


def test_scripts_top_level_holds_only_numbered_steps():
    top = sorted(path.name for path in SCRIPTS.glob("*.py"))
    extra = [name for name in top if name != "get_all_data.py" and not re.fullmatch(r"step\d+b?_\w+\.py", name)]
    assert not extra, f"not a pipeline step, move it into a subfolder: {extra}"
    numbers = [re.match(r"step(\d+b?)_", name).group(1) for name in top if name.startswith("step")]
    assert len(numbers) == len(set(numbers)), f"two scripts share a step number: {sorted(numbers)}"
    folders = {script.parent.relative_to(SCRIPTS).as_posix() for script in python_files(SCRIPTS)} - {"."}
    assert folders == {"baselines", "paper", "quality", "verification"}


@pytest.mark.skipif(shutil.which("git") is None or not (REPO / ".git").exists(), reason="needs the git checkout")
def test_live_files_name_only_existing_scripts():
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "*.md", "*.py", "*.ipynb"], check=True,
                             capture_output=True, text=True).stdout.split()
    live = [name for name in tracked if name not in FROZEN and not name.startswith(FROZEN_PREFIXES)
            and not re.fullmatch(r"experiments/[^/]+/PLAN\.md", name)]  # plans take only dated lines at the end
    assert len(live) > 100
    missing = sorted({f"{name}: {found}" for name in live if (REPO / name).exists()
                      for found in SCRIPT_PATH.findall((REPO / name).read_text(encoding="utf-8", errors="replace"))
                      if found not in HISTORICAL and not (REPO / found).exists()})
    assert not missing, "stale script paths:\n" + "\n".join(missing)
