import csv
import importlib.util
from pathlib import Path

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

spec = importlib.util.spec_from_file_location("tb_export", Path(__file__).with_name("export.py"))
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def test_fold_values_are_actual_fold_steps_and_nan_is_excluded(tmp_path):
    src = tmp_path / "fold_metrics.csv"
    src.write_text("method,fold,rmse_t_ha,r2\nmodelA,1,2.5,0.3\nmodelA,4,1.5,\n", encoding="utf-8")
    assert export.export_table(src, tmp_path / "out", "protocol", "by_fold", fold=True) == 3
    a = EventAccumulator(str(tmp_path / "out" / "protocol" / "lacuna_2023" / "modelA"))
    a.Reload()
    assert [(x.step, x.value) for x in a.Scalars("by_fold/rmse_t_ha")] == [(1, 2.5), (4, 1.5)]
    assert len(a.Scalars("by_fold/r2")) == 1


def test_pair_comparisons_are_not_arms_and_names_remain_unique(tmp_path):
    src = tmp_path / "scores.csv"
    src.write_text("kind,arm,rmse,r2\narm,P0,1.0,0.2\npair,,,\n", encoding="utf-8")
    assert export.export_table(src, tmp_path / "out", "protocol", "overall") == 2
    assert export.safe("verylongsameprefix_a") != export.safe("verylongsameprefix_b")
    assert len(export.safe("x" * 200)) <= 21
