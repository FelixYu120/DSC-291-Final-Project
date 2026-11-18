"""Run the approved spatial baseline comparison from the shared database.

Read and verify inputs -> align by obs_id -> train on four spatial folds ->
predict the fifth -> pool predictions -> save scores and provenance.

Only the already-evaluated R0/R1/A1 arms and s1_cc2km are supported here. New
representations need a separate decision about the team's fold-0 restriction.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from threadpoolctl import threadpool_limits

from cropyield import ROOT
from cropyield.baselines.models import coordinates_knn, ridge_cv, train_mean
from cropyield.baselines.scoring import score_predictions
from cropyield.data.xy import FEATURES, MIN_CLEAR_MONTHS, load_xy
from cropyield.eval.splits import check_split

ARMS = ['R0', 'R1', 'A1']
COHORTS = ['malawi_2023', 'kenya_oaf_2019_2020', 'zimbabwe_lacuna_2022_2023']


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_config(config):
    if config['arms'] != ARMS or config['split_family'] != 's1_cc2km':
        raise ValueError('This runner reproduces only R0, R1, A1 on s1_cc2km; new arms require a fold-policy decision')
    if not config['cohorts'] or len(set(config['cohorts'])) != len(config['cohorts']) or not set(config['cohorts']) <= set(COHORTS):
        raise ValueError('Choose distinct supported cohorts')
    if config['min_clear_months'] != MIN_CLEAR_MONTHS:
        raise ValueError('The frozen baseline cohort requires four clear months')
    if config['knn_neighbors'] != 10 or config['ridge']['inner_folds'] != 5:
        raise ValueError('The approved baselines use 10 neighbours and five inner folds')
    if config['bootstrap_draws'] < 1:
        raise ValueError('bootstrap_draws must be positive')


def verify_inputs(data_dir: Path, cohorts) -> dict:
    """Stop before training if the database, labels or selected splits changed."""
    spec = json.loads((ROOT / 'configs/team_database_v1.json').read_text())
    database = data_dir / 'cropyield.duckdb'
    if not database.is_file():
        raise FileNotFoundError(f'Download the shared team database to {database}; do not rebuild it')
    if database.stat().st_size != spec['bytes'] or sha256(database) != spec['sha256']:
        raise ValueError('Database does not match configs/team_database_v1.json')
    manifest = json.loads((data_dir / 'splits/manifest.json').read_text())
    labels = data_dir / 'processed/labels_v1.parquet'
    if sha256(labels) != manifest['labels_sha256']:
        raise ValueError('Frozen labels checksum mismatch')
    hashes = {'database': spec['sha256'], 'labels': manifest['labels_sha256'],
              'split_manifest': sha256(data_dir / 'splits/manifest.json'), 'splits': {}}
    for cohort in cohorts:
        name = f'{cohort}__s1_cc2km.csv'
        digest = sha256(data_dir / 'splits' / name)
        if digest != manifest['files'][name]['sha256']:
            raise ValueError(f'Frozen split checksum mismatch: {name}')
        hashes['splits'][cohort] = digest
    return hashes


def load_rows(data_dir: Path, cohort: str, expected_rows: int) -> pd.DataFrame:
    """Same fields for every arm, with source labels and split grouping by ID."""
    labels = pd.read_parquet(data_dir / 'processed/labels_v1.parquet').set_index('obs_id')
    if not labels.index.is_unique:
        raise ValueError('Duplicate obs_id in labels')
    primary = labels[(labels.cohort == cohort) & labels.include_primary]
    X, y = load_xy(cohort, data_dir)
    if not X.index.is_unique or not X.index.equals(y.index) or not X.index.isin(primary.index).all():
        raise ValueError(f'{cohort}: feature/label IDs do not align')
    if len(X) != expected_rows:
        raise ValueError(f'{cohort}: expected {expected_rows} model rows, found {len(X)}')
    # Preserve frozen label order, including deterministic KNN tie breaking in
    # the historical baseline. Every join still uses obs_id, never row position.
    ids = primary.index[primary.index.isin(X.index)]
    rows = X.loc[ids].copy()
    rows['yield_t_ha'] = primary.loc[ids, 'yield_kg_ha'] / 1000
    if not np.allclose(rows.yield_t_ha, y.loc[ids], rtol=0, atol=1e-10):
        raise ValueError(f'{cohort}: database yield differs from frozen labels')
    rows[['lat', 'lon']] = primary.loc[ids, ['lat', 'lon']]
    split = pd.read_csv(data_dir / 'splits' / f'{cohort}__s1_cc2km.csv',
                        dtype={'group_id': str, 'fold': str}, keep_default_na=False)
    problems = check_split(split, primary.reset_index())
    if problems:
        raise ValueError('; '.join(problems))
    aligned = split.set_index('obs_id').loc[ids]
    rows[['group_id', 'fold']] = aligned[['group_id', 'fold']]
    return rows


def out_of_fold(rows, config, verbose=False):
    """One prediction per observation per arm, always from other spatial folds."""
    if config['arms'] != ARMS:
        raise ValueError('Only R0, R1, A1 are enabled')
    if not rows.index.is_unique:
        raise ValueError('Duplicate observation IDs')
    if rows[['group_id', 'fold']].isna().any().any() or (rows.group_id.astype(str) == '').any():
        raise ValueError('Missing group or fold')
    if set(rows.fold) != {'0', '1', '2', '3', '4'}:
        raise ValueError('Expected all five frozen folds 0 through 4')
    if (rows.groupby('group_id').fold.nunique() > 1).any():
        raise ValueError('A spatial group occurs in multiple folds')
    if not np.isfinite(rows[[*FEATURES, 'yield_t_ha', 'lat', 'lon']].to_numpy(dtype=float)).all():
        raise ValueError('Nonfinite model input; no rows are silently dropped')
    X = rows[FEATURES].to_numpy(dtype=float)
    y = rows.yield_t_ha.to_numpy(dtype=float)
    coords = rows[['lat', 'lon']].to_numpy(dtype=float)
    groups = rows.group_id.to_numpy()
    alphas = np.logspace(*config['ridge']['alphas_logspace'])
    predictions, fits = [], []
    for fold in sorted(rows.fold.unique()):
        test = (rows.fold == fold).to_numpy()
        train = ~test
        if verbose:
            print(f'  fold {fold}: {train.sum()} training fields, {test.sum()} test fields', flush=True)
        for arm in ARMS:
            alpha = float('nan')
            if arm == 'R0':
                predicted = train_mean(y[train], int(test.sum()))
            elif arm == 'R1':
                predicted = coordinates_knn(coords[train], y[train], coords[test], config['knn_neighbors'])
            else:
                predicted, alpha = ridge_cv(X[train], y[train], groups[train], X[test], alphas,
                                            config['ridge']['inner_folds'])
            if not np.isfinite(predicted).all():
                raise ValueError(f'{arm}, fold {fold}: nonfinite predictions')
            part = rows.loc[test, ['group_id', 'fold', 'yield_t_ha']].copy()
            part.index.name = 'obs_id'
            predictions.append(part.reset_index().assign(arm=arm, predicted=predicted, n_train=int(train.sum())))
            fits.append({'fold': fold, 'arm': arm, 'n_train': int(train.sum()), 'n_test': int(test.sum()),
                         'n_train_groups': len(np.unique(groups[train])), 'n_test_groups': len(np.unique(groups[test])),
                         'selected_alpha': alpha})
    return pd.concat(predictions, ignore_index=True), pd.DataFrame(fits)


def pooled_summary(table):
    """Nine rows: three arms for each of three cohorts."""
    pooled = table[table.fold == 'pooled']
    summary = pooled.pivot(index=['cohort', 'arm'], columns='metric', values='value').reset_index()
    for metric in ['rmse_t_ha', 'rmse_minus_R1']:
        ci = pooled[pooled.metric == metric][['cohort', 'arm', 'ci_low', 'ci_high']]
        summary = summary.merge(ci.rename(columns={'ci_low': f'{metric}_ci_low', 'ci_high': f'{metric}_ci_high'}),
                                on=['cohort', 'arm'], how='left', validate='one_to_one')
    counts = pooled[['cohort', 'arm', 'n_test', 'n_groups']].drop_duplicates()
    return summary.merge(counts, on=['cohort', 'arm'], validate='one_to_one')


def provenance(config_path, config, hashes):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    sources = sorted((ROOT / 'src/cropyield').rglob('*.py')) + [ROOT / 'scripts/baselines/spatial_baselines.py']
    return {'git_commit': git('rev-parse', 'HEAD'), 'git_branch': git('branch', '--show-current'),
            'working_tree_dirty': bool(git('status', '--porcelain', '--untracked-files=all')),
            'source_sha256': {str(path.relative_to(ROOT)): sha256(path) for path in sources},
            'config_sha256': sha256(config_path), 'config': config, 'input_sha256': hashes,
            'python': platform.python_version(), 'platform': platform.platform(),
            'versions': {name: importlib.metadata.version(name) for name in
                         ['numpy', 'pandas', 'scipy', 'scikit-learn', 'duckdb', 'pyarrow', 'threadpoolctl']},
            'target_unit': 't/ha', 'row_order': 'frozen labels_v1 order',
            'evaluation_note': 'Reproduction on previously inspected research folds; not an untouched final test',
            'fold_policy': 'Only previously evaluated R0/R1/A1; no new model arm is enabled'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/spatial_baselines_v1.yaml')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--output-dir', type=Path, help='New directory for score tables and provenance')
    args = parser.parse_args(argv)
    config = yaml.safe_load(args.config.read_text())
    validate_config(config)
    print('Verifying shared database, frozen labels and split checksums...', flush=True)
    hashes = verify_inputs(args.data_dir, config['cohorts'])
    # Validate every cohort before starting any model fit.
    inputs = {cohort: load_rows(args.data_dir, cohort, config['expected_rows'][cohort]) for cohort in config['cohorts']}
    run_id = config['experiment'] + '-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    out = args.output_dir or ROOT / 'results/spatial_baselines' / run_id
    prediction_dir = ROOT / 'data/runs/spatial_baselines' / run_id
    if out.exists():
        raise FileExistsError(f'{out} already exists; use a new directory to preserve prior results')
    metadata = provenance(args.config, config, hashes)
    metadata.update(run_id=run_id, timestamp=datetime.now(UTC).isoformat())
    scores, predictions, fitted = [], [], []
    with threadpool_limits(limits=1):
        for cohort, rows in inputs.items():
            print(f'{cohort}: {len(rows)} fields, {rows.group_id.nunique()} spatial groups', flush=True)
            pred, fits = out_of_fold(rows, config, verbose=True)
            print(f'  scoring pooled predictions with {config["bootstrap_draws"]} group-bootstrap draws', flush=True)
            table = pd.DataFrame(score_predictions(pred, seed=config['seed'], draws=config['bootstrap_draws']))
            scores.append(table.assign(cohort=cohort, split_family=config['split_family'],
                                       split_sha256=hashes['splits'][cohort], seed=config['seed'],
                                       run_id=run_id, git_commit=metadata['git_commit'], config_sha256=metadata['config_sha256']))
            predictions.append(pred.assign(cohort=cohort))
            fitted.append(fits.assign(cohort=cohort))
    # No builder or write connection is used. Confirm all protected inputs again.
    if verify_inputs(args.data_dir, config['cohorts']) != hashes:
        raise ValueError('Protected inputs changed during the run')
    table = pd.concat(scores, ignore_index=True)
    summary = pooled_summary(table)
    out.mkdir(parents=True)
    prediction_dir.mkdir(parents=True)
    prediction_path = prediction_dir / 'predictions.parquet'
    pd.concat(predictions, ignore_index=True).to_parquet(prediction_path, index=False)
    table.to_csv(out / 'metrics.csv', index=False)
    summary.to_csv(out / 'summary.csv', index=False)
    pd.concat(fitted, ignore_index=True).to_csv(out / 'fold_fits.csv', index=False)
    shutil.copyfile(args.config, out / 'config.yaml')
    metadata['predictions'] = {'path': str(prediction_path), 'sha256': sha256(prediction_path),
                               'rows': sum(map(len, predictions))}
    metadata['protected_inputs_unchanged'] = True
    metadata['output_sha256'] = {p.name: sha256(p) for p in out.iterdir() if p.is_file()}
    (out / 'run.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print('\nPooled out-of-fold scores (yield and errors in t/ha):')
    print(summary[['cohort', 'arm', 'n_test', 'rmse_t_ha', 'mae_t_ha', 'bias_t_ha', 'r2', 'spearman']].round(4).to_string(index=False))
    print(f'\nScore tables and provenance: {out}\nPer-field predictions: {prediction_path}')
    return 0
