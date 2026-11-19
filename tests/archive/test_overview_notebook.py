"""The two pass-archive notebooks as they are shared: checks that need no data and no kernel."""
import json
import re
from pathlib import Path

import pytest

NOTEBOOKS = Path(__file__).resolve().parents[2] / "notebooks"
OVERVIEW, QUERY = NOTEBOOKS / "pass_archive_overview.ipynb", NOTEBOOKS / "pass_archive_query.ipynb"


def cells(notebook, kind):
    return [cell for cell in json.loads(notebook.read_text(encoding="utf-8"))["cells"] if cell["cell_type"] == kind]


@pytest.mark.parametrize(("notebook", "least_cells", "figures"), [(OVERVIEW, 10, 4), (QUERY, 2, 0)])
def test_saved_run_is_complete_and_has_no_error(notebook, least_cells, figures):
    code = cells(notebook, "code")
    assert len(code) >= least_cells
    assert [cell["execution_count"] for cell in code] == list(range(1, len(code) + 1))      # one run, top to bottom
    outputs = [output for cell in code for output in cell["outputs"]]
    assert not [output for output in outputs if output["output_type"] == "error"]
    assert sum("image/png" in output.get("data", {}) for output in outputs) == figures      # the query notebook: none


@pytest.mark.parametrize("notebook", [OVERVIEW, QUERY])
def test_notebook_only_reads_and_names_no_private_path(notebook):
    source = "\n".join("".join(cell["source"]) for cell in cells(notebook, "code"))
    assert source.count("duckdb.connect(") == 1 and "duckdb.connect(str(DB), read_only=True)" in source
    assert ".to_parquet(" not in source and ".to_csv(" not in source and "savefig(" not in source      # writes no file
    everything = notebook.read_text(encoding="utf-8")
    assert not re.search(r"[A-Za-z]:\\\\(Users|Dev)|/Users/|AppData", everything)             # no machine path in the outputs


def test_query_notebook_is_one_setup_cell_and_one_query_cell():
    code = ["".join(cell["source"]) for cell in cells(QUERY, "code")]
    assert len(code) == 2 and "def sql(query)" in code[0] and code[1].strip() == 'sql("select * from master limit 10")'
