"""compare_compact_candidate.py: a v2 config never writes over the committed v1 candidate file by default."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("compare_compact_candidate",
                                              ROOT / "scripts" / "verification" / "compare_compact_candidate.py")
candidate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(candidate)


def test_default_output_follows_the_config_version():
    runs = ROOT / "data" / "runs"
    assert candidate.candidate_output(ROOT / "configs" / "zimbabwe_weather_compact_v1.json") == \
        runs / "zimbabwe_weather_compact_candidate_v1.csv"
    assert candidate.candidate_output(ROOT / "configs" / "zimbabwe_weather_compact_v2.json") == \
        runs / "zimbabwe_weather_compact_candidate_v2.csv"
