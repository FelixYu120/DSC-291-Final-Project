"""Create the seasonal-GCVI and crop-cut agreement figures in the Zimbabwe visual atlas."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

COHORT = "zimbabwe_lacuna_2022_2023"
HANDOFF = Path("data/processed/zimbabwe_midterm_v2")
EXPERIMENT = Path("experiments/presto_finetune/runs") / COHORT
MONTHS = pd.period_range("2022-10", "2023-06", freq="M")
YIELD_GROUPS = ["Lower quarter", "Middle half", "Upper quarter"]
COLORS = ["#b15b26", "#297a84", "#344c86"]


def seasonal_gcvi_data(root):
    """Summarize observed field-month measurements in the pinned Lacuna handoff."""
    labels = pd.read_csv(root / HANDOFF / "cleaned_labels.csv")
    labels = labels.loc[labels["include_primary"] & labels["season_year"].eq(2023)].copy()
    labels["yield_t_ha"] = labels["yield_kg_ha"] / 1000
    cuts = labels["yield_t_ha"].quantile([0.25, 0.75]).to_list()
    labels["yield_group"] = pd.cut(labels["yield_t_ha"], [-np.inf, *cuts, np.inf], labels=YIELD_GROUPS)
    monthly = pd.read_csv(root / HANDOFF / "monthly_features.csv",
                          usecols=["obs_id", "month", "coverage_state", "gcvi"])
    monthly["month"] = pd.PeriodIndex(monthly["month"], freq="M")
    if monthly.duplicated(["obs_id", "month"]).any() or set(monthly["obs_id"]) != set(labels["obs_id"]):
        raise ValueError("Unexpected field-month keys in the handoff.")
    joined = monthly.merge(labels[["obs_id", "yield_group"]], on="obs_id", validate="many_to_one")
    if set(joined.month) != set(MONTHS) or len(joined) != len(labels) * len(MONTHS):
        raise ValueError("Expected one monthly coverage record per field and season month.")
    observed = joined["coverage_state"].eq("clear") & np.isfinite(joined["gcvi"])
    joined["gcvi"] = joined["gcvi"].where(observed)
    groups = joined.groupby(["yield_group", "month"], observed=True)["gcvi"]
    by_month = pd.concat([groups.count().rename("count"), groups.size().rename("total"),
                          groups.quantile(.25).rename("q25"), groups.median().rename("median"),
                          groups.quantile(.75).rename("q75")], axis=1)
    return by_month, cuts


def agreement_data(root):
    """Match the data-v2 Presto experiment's saved development predictions to v2 field labels."""
    labels = pd.read_parquet(root / "data/v2/processed/labels_v2.parquet",
                             columns=["obs_id", "cohort", "season_year", "include_primary", "admin_unit", "yield_kg_ha"])
    labels = labels.loc[labels["cohort"].eq(COHORT) & labels["season_year"].eq(2023) & labels["include_primary"]]
    split = pd.read_csv(root / f"data/v2/splits/{COHORT}__s1_cc2km.csv", usecols=["obs_id", "fold"])
    split = split[split["fold"].isin([1, 2, 3, 4])]
    fields = pd.read_csv(root / EXPERIMENT / "predictions.csv", usecols=["obs_id", "fold", "y_t_ha", "A1", "P0"])
    expected = set(zip(split.obs_id, split.fold))
    if set(zip(fields.obs_id, fields.fold)) != expected or fields.obs_id.duplicated().any():
        raise ValueError("Saved predictions disagree with the data-v2 spatial development split.")
    fields = fields.merge(labels, on="obs_id", how="left", validate="one_to_one")
    if not np.allclose(fields.y_t_ha, fields.yield_kg_ha / 1000, rtol=0, atol=1e-10):
        raise ValueError("Measured yields disagree with primary field labels.")
    if fields.admin_unit.isna().any() or not np.isfinite(fields[["A1", "P0"]]).all().all():
        raise ValueError("A field is missing an area or a prediction.")
    run = json.loads((root / EXPERIMENT / "run.json").read_text())
    db_pin = json.loads((root / "configs/team_database_v2.json").read_text())
    if run["database_pin"] != db_pin["sha256"] or run["fields_scored"] != len(fields):
        raise ValueError("Archived experiment metadata disagrees with data v2.")
    areas = fields.groupby("admin_unit").agg(y_t_ha=("y_t_ha", "mean"), A1=("A1", "mean"),
                                             P0=("P0", "mean"), n_fields=("obs_id", "size"))
    saved = pd.read_csv(root / EXPERIMENT / "scores.csv")
    saved = saved.loc[saved["kind"].eq("arm")].set_index("arm")
    scores = {}
    for arm in ["A1", "P0"]:
        scores[arm] = {}
        for unit, frame in [("field", fields), ("area", areas)]:
            actual, estimated = frame["y_t_ha"], frame[arm]
            sse = ((actual - estimated) ** 2).sum()
            rmse = np.sqrt(sse / len(frame))
            r2 = 1 - sse / ((actual - actual.mean()) ** 2).sum()
            scores[arm][unit] = {"rmse_t_ha": float(rmse), "r2": float(r2), "n": len(frame)}
            if unit == "field" and not np.allclose([rmse, r2], saved.loc[arm, ["rmse", "r2"]].astype(float),
                                                   rtol=0, atol=1e-9):
                raise ValueError(f"{arm} does not reproduce the archived development scores.")
    return fields, areas, scores


def style_axis(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["bottom", "left"]].set_color("#b3bfc2")
    ax.tick_params(color="#b3bfc2", labelcolor="#32494d", length=3)


def save_seasonal_gcvi(counts, cuts, output):
    fig, axes = plt.subplots(1, 3, figsize=(13.3, 5.6), sharey=True)
    fig.subplots_adjust(left=.065, right=.977, top=.74, bottom=.29, wspace=.16)
    fig.text(.065, .94, "Seasonal greenness by measured maize yield", weight="bold", fontsize=19)
    n_fields = sum(int(counts.loc[group, "total"].iloc[0]) for group in YIELD_GROUPS)
    fig.text(.065, .875, f"Lacuna 2023  •  {n_fields:,} fields  •  Lines show the median. Shading covers the middle 50% of observed GCVI.",
             color="#405a60", fontsize=10)
    positions = np.arange(len(MONTHS))
    for ax, group, color in zip(axes, YIELD_GROUPS, COLORS):
        sub = counts.loc[group].reindex(MONTHS)
        ax.fill_between(positions, sub.q25, sub.q75, color=color, alpha=.19, linewidth=0)
        ax.plot(positions, sub["median"], "o-", color=color, lw=2.2, ms=4.5)
        for index in positions[sub["count"].eq(0)]:
            ax.axvspan(index - .5, index + .5, color="#f0f2f2", zorder=-1, linewidth=0)
        ax.set(xlim=(-.5, 8.5), xticks=positions, xticklabels=[p.strftime("%b") for p in MONTHS])
        ax.set_title(f"{group}  ·  {sub.total.iloc[0]:,} fields", fontsize=11, loc="left", color=color, weight="bold")
        ax.grid(axis="y", alpha=.14)
        ax.tick_params(axis="x", labelsize=8)
        for x, n in zip(positions, sub["count"]):
            ax.text(x, -.23, str(n), ha="center", va="center", fontsize=8, color="#344a4e",
                    transform=ax.get_xaxis_transform())
        style_axis(ax)
    axes[0].set_ylabel("Green chlorophyll vegetation index", fontsize=10)
    axes[0].set_ylim(bottom=0)
    fig.text(.065, .222, "FIELDS WITH OBSERVATIONS", fontsize=7, weight="bold", color="#405a60")
    fig.text(.065, .083, f"Yield groups use the 25th and 75th percentiles ({cuts[0]:.2f} and {cuts[1]:.2f} t/ha). "
                         "Monthly counts can vary within each group.", fontsize=9, color="#405a60")
    fig.text(.065, .044, "Source  ·  Lacuna yield labels and Sentinel-2 monthly handoff, October 2022 to June 2023. "
                         "Only finite observations marked clear enter the curves.", fontsize=8, color="#53696c")
    fig.savefig(output, dpi=170, facecolor="white")
    plt.close(fig)


def save_agreement(fields, areas, scores, output):
    fig, axes = plt.subplots(2, 2, figsize=(9.8, 8.8))
    fig.subplots_adjust(left=.10, right=.96, bottom=.14, top=.84, hspace=.49, wspace=.32)
    fig.text(.085, .95, "Crop-cut yield and held-out estimates", fontsize=19, weight="bold")
    fig.text(.085, .91, "Lacuna 2023  •  Spatial development folds 1–4  •  Dashed line shows exact agreement",
             fontsize=10, color="#405a60")
    colors = ["#a86037", "#1d7475"]
    arms = [("A1", "Seasonal indices + Ridge"), ("P0", "Frozen Presto + Ridge")]
    for row, (unit, frame) in enumerate([("field", fields), ("area", areas)]):
        values = frame[["y_t_ha", "A1", "P0"]]
        lower = np.floor(values.min().min())
        upper = np.ceil(values.max().max())
        pad = (upper - lower) * .03
        for col, (arm, title) in enumerate(arms):
            ax = axes[row, col]
            ax.plot([lower-pad, upper+pad], [lower-pad, upper+pad], "--", lw=1.15, color="#9da7a8", zorder=0)
            ax.scatter(frame.y_t_ha, frame[arm], c=colors[col], alpha=.22 if row == 0 else .82,
                       s=12 if row == 0 else 34, linewidths=0)
            ax.set(xlim=(lower-pad, upper+pad), ylim=(lower-pad, upper+pad), aspect="equal")
            result = scores[arm][unit]
            ax.text(.045, .95, f"RMSE {result['rmse_t_ha']:.2f} t/ha\nR² {result['r2']:.3f}",
                    transform=ax.transAxes, ha="left", va="top", fontsize=9)
            label = f"{len(fields):,} fields" if row == 0 else f"{len(areas)} area means"
            ax.set_title(f"{title}   ·   {label}", fontsize=10.5, weight="bold", color=colors[col])
            ax.set_xlabel("Measured yield (t/ha)", fontsize=9)
            if col == 0:
                ax.set_ylabel("Estimated yield (t/ha)", fontsize=9)
            style_axis(ax)
    fig.text(.085, .066, f"Each lower-panel dot averages the same fields within one provider area "
             f"({areas.n_fields.min()}–{areas.n_fields.max()} fields). Area scores give each area equal weight.",
             fontsize=8.4, color="#405a60")
    fig.text(.085, .037, "Source  ·  Data v2 Presto experiment, saved development predictions. "
             "Four outer folds scored. Fold 0 contributed training fields.", fontsize=8.3, color="#53696c")
    fig.savefig(output, dpi=170, facecolor="white")
    plt.close(fig)


def build_diagnostics(repo_root, output_dir=None):
    """Write two independent PNGs; return figure paths and the underlying descriptive statistics."""
    root = Path(repo_root).resolve()
    output = Path(output_dir) if output_dir is not None else root / "results/visual_atlas"
    output.mkdir(parents=True, exist_ok=True)
    seasonal_path = output / "seasonal_gcvi.png"
    agreement_path = output / "yield_agreement.png"
    counts, cuts = seasonal_gcvi_data(root)
    fields, areas, scores = agreement_data(root)
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "text.color": "#243e43",
                         "axes.labelcolor": "#243e43"}):
        save_seasonal_gcvi(counts, cuts, seasonal_path)
        save_agreement(fields, areas, scores, agreement_path)
    return {
        "seasonal_gcvi": seasonal_path, "yield_agreement": agreement_path,
        "metadata": {
            "yield_cutpoints_t_ha": cuts, "observed_gcvi_by_month": {
                str(month): int(n) for month, n in counts.groupby(level="month")["count"].sum().items()
            },
            "scores": scores, "fields_per_area_range": [int(areas.n_fields.min()), int(areas.n_fields.max())],
        },
    }
