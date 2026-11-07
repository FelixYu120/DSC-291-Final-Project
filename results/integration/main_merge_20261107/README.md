# Main merge verification — 7 November 2026

The merge includes all eight archived Felix commits alongside the existing Zimbabwe work.
The earlier quality-review variant remains separate from the frozen Zimbabwe experiment inputs.

Validation completed on the combined working tree:

- Full test suite: **318 passed, 2 skipped** (Windows-specific tests).
- Ruff: the new replay runner and its protection tests passed.
- Zimbabwe guide: all **26 code cells** passed in a fresh kernel with database access blocked;
  its optional one-model replay reproduced **376 predictions** within `1e-9` t/ha.
- Quality-review notebook: all **15 code cells** passed with database access blocked and optional local
  variant checks disabled. Its committed notebook is unchanged from the archived branch.
- Full-weather and compact-weather independent verifiers passed using the recorded source revision.
  Each replay verified **329 recorded inputs and outputs before and after execution**.
- Offline weather rebuild: all **13 output files** matched the original release byte for byte.
- The post-hoc candidate comparison was recomputed from the saved predictions.

The JSON receipts record notebook hashes, source revision and runner hash. The weather rebuild was written
to a temporary directory; its file comparisons are preserved in `weather_rebuild_verification.json`.
This verifies existing experiments and adds no new performance estimate or reserved-fold evaluation.
See [reproduction instructions](../../../docs/ZIMBABWE_REPRODUCTION.md).
