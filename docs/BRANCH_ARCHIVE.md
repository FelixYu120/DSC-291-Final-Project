# Main branch consolidation

The Zimbabwe data handoff and experiments from `e1235944f092359e4ed29d3ef20cef1f17085d10`
are integrated into `main`, together with `notebooks/data_guide_2_zimbabwe.ipynb`.
The notebook is the second guide because this work concerns Zimbabwe; the original guide remains the multi-country foundation.

The user subsequently confirmed that the eight commits on `felix-branch` should also be merged into main. They include
spatial baselines, data-quality reviews, stronger label validation and foundation-model notes. Main now contains both
histories. The archive tags remain as recovery references, and no development branches need to be restored.
The spatial-baseline tip is an ancestor of the Felix tip and is included in that merge.

Historical Zimbabwe manifests remain unchanged. Use the [recorded-code replay runner](ZIMBABWE_REPRODUCTION.md)
when verifying or retraining those experiments: main now includes stronger shared validation modules with different hashes.

| Previous branch | Previous tip | Preservation |
|---|---|---|
| `codex/zimbabwe-data-handoff` | `e1235944f092359e4ed29d3ef20cef1f17085d10` | Included in main history |
| `felix-branch` | `ad89b2d6358df2a163b813afea35452317510249` | Included in main; `archive/felix-branch-2026-11-07` retained |
| `codex/spatial-baselines` | `f511bad4c371f46261a9fdfcf6095693804984c8` | Included in main; `archive/spatial-baselines-2026-11-07` retained |
| `plan/scope-reset` | `12027894146f7dd5006cedcc458a3016303e3778` | Already included in main history |
| `presto/first-run` | `0028e1dab51c76885f18de360aa5ee58f32a3845` | Already included in main history |
| `scaffold/cropyield-skeleton` | `6256f160c1c39107376110b93d0c5d23d1a4c0fc` | Already included in main history |

Archive tags keep the commits accessible without keeping development branches. For example:

```bash
git show archive/felix-branch-2026-11-07:docs/DATA_QUALITY.md
git log --oneline main..archive/felix-branch-2026-11-07
```

A verified full local backup was also created before cleanup at
`data/runs/branch_archive_before_main_20261107.bundle` (79,678,827 bytes; intentionally Git-ignored).
Its SHA-256 is `0e0db0f2a6b29e0fa040cdd46be23dac6e63001dcc149368654717177f9b0a2f`.
The bundle contains the complete pre-cleanup Git history and can be checked with `git bundle verify`.
The archive tags are the shared recovery points on GitHub; the bundle is a local additional backup.
