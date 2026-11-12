"""notebooks/midterm_figures.ipynb and its map-file script: checks that need no data, no network and no kernel."""
import ast
import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NOTEBOOK = REPO / "notebooks" / "midterm_figures.ipynb"
SCRIPT = REPO / "notebooks" / "midterm_get_basemap.py"
SAVE = re.compile(r'save\([^,]+,\s*"([^"]+)"')   # save(fig, "D01_powers_of_ten") writes the PNG and the PDF of a figure
pytestmark = pytest.mark.skipif(not NOTEBOOK.exists(), reason="the midterm notebook is not in this checkout")


@pytest.fixture(scope="module")
def cells():
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]


def text(cell) -> str:
    return "".join(cell["source"])


def saved_names(cell) -> list[str]:
    return SAVE.findall(text(cell)) if cell["cell_type"] == "code" else []


def test_every_code_cell_parses(cells):
    for number, cell in enumerate(cells):
        if cell["cell_type"] == "code":
            ast.parse(text(cell), filename=f"cell {number}")


def test_figure_names_are_unique_and_in_part_order(cells):
    names = [name for cell in cells for name in saved_names(cell)]
    assert len(names) >= 30
    assert len(names) == len(set(names)), "two cells write the same figure file"
    assert all(re.fullmatch(r"[DAR]\d\d[a-z]?_[a-z0-9_]+", name) for name in names), names
    parts = [name[0] for name in names]                    # D = data, A = architecture, R = results
    assert parts == sorted(parts, key="DAR".index), "a figure is in the wrong part of the notebook"


def test_each_figure_cell_follows_its_text_cell(cells):
    for number, cell in enumerate(cells):
        names = saved_names(cell)
        if names:
            figure_id = names[0].split("_")[0]
            before = cells[number - 1]
            assert before["cell_type"] == "markdown" and text(before).startswith(f"### {figure_id}."), names[0]


def test_no_cell_holds_a_saved_error(cells):
    failed = [number for number, cell in enumerate(cells) if cell["cell_type"] == "code"
              for output in cell.get("outputs", []) if output.get("output_type") == "error"]
    assert not failed, f"cells with a saved error output: {failed}"


def test_map_file_script_paths_and_tile_names():
    spec = importlib.util.spec_from_file_location("midterm_get_basemap", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    assert script.OUT == REPO / "data" / "imagery" / "basemap"      # git-ignored, relative to the clone
    south_east = "Copernicus_DSM_COG_30_S18_00_E030_00_DEM"
    assert script.tile_url(-18, 30) == f"https://copernicus-dem-90m.s3.amazonaws.com/{south_east}/{south_east}.tif"
    assert "_N00_00_E034_00_" in script.tile_url(0, 34)
    assert "_N05_00_W003_00_" in script.tile_url(5, -3)
