"""Read-only, label-free Sentinel-2 quality screening for passarchive_v1.

Writes one row per sampled field-scene and up to 15 ranked scenes per field-month.
The source DuckDB is opened read-only. This is an optical-quality proposal,
not a crop/field-purity classifier or a replacement for the frozen pipeline.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def quote(path: Path) -> str:
    return "'" + str(path.resolve()).replace("\\", "/").replace("'", "''") + "'"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="A new output directory")
    parser.add_argument("--limit-fields", type=int, default=None, help="For a small pilot")
    parser.add_argument("--min-clear-fraction", type=float, default=0.8)
    parser.add_argument("--review-cloud-probability", type=float, default=60.0)
    parser.add_argument("--top-k", type=int, default=15)
    parser.add_argument("--window-kind", choices=("current", "both"), default="current",
                        help="Include only harvest-year images or both archive years")
    parser.add_argument("--crop", default=None, help="Optional crop filter, e.g. maize")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("Database does not exist")
    if args.output.exists():
        parser.error("Output directory already exists; choose a new one")
    if args.limit_fields is not None and args.limit_fields < 1:
        parser.error("--limit-fields must be positive")
    if not 0 < args.min_clear_fraction <= 1:
        parser.error("--min-clear-fraction must be in (0, 1]")
    if not 0 <= args.review_cloud_probability <= 100:
        parser.error("--review-cloud-probability must be in [0, 100]")
    if args.top_k < 1:
        parser.error("--top-k must be positive")

    args.output.mkdir(parents=True)
    con = duckdb.connect(str(args.database), read_only=True)
    try:
        # The current window corresponds to the field's own growing season.
        # There can be more than one reading route for a scene: keep one
        # deterministically while retaining distinct scenes as candidates.
        scope = "" if args.limit_fields is None else f"LIMIT {args.limit_fields}"
        crop_filter = "" if args.crop is None else "WHERE crop = ?"
        con.execute(f"CREATE TEMP TABLE scope_fields AS SELECT fs_key FROM fields {crop_filter} ORDER BY fs_key {scope}",
                    [] if args.crop is None else [args.crop])
        window_filter = "p.window_kind='current'" if args.window_kind == "current" else "p.window_kind IN ('current','previous')"
        con.execute(f"""
            CREATE TEMP TABLE candidates AS
            WITH items AS (
                SELECT item_id, max(sun_elevation) AS sun_elevation,
                       any_value(collection) AS collection,
                       any_value(dn_add_offset) AS dn_add_offset
                FROM scene_items GROUP BY item_id
            ), sampled AS (
                SELECT f.field_season_id, f.country_iso3, f.dataset, f.crop,
                       f.geometry_type, f.location_quality,
                       f.usable_at_field_scale, f.planting_date, f.harvest_date,
                       p.fs_key, p.loc_key, p.granule_key, p.acquisition_id,
                       p.sensing_time_utc,
                       year(p.sensing_time_utc) AS year,
                       month(p.sensing_time_utc) AS month,
                       s.scene_key, s.scene_id, s.processing_baseline,
                       s.cloud_cover_percent AS scene_cloud_cover_percent,
                       x.item_id, x.read_route, x.n_pixels,
                       x.scl, x.cld, x.aot, x.wvp,
                       i.sun_elevation, i.collection, i.dn_add_offset,
                       x.b02, x.b03, x.b04, x.b05, x.b06,
                       x.b07, x.b08, x.b8a, x.b11, x.b12
                FROM passes p
                JOIN scope_fields sf USING (fs_key)
                JOIN fields f USING (fs_key)
                JOIN pass_samples x ON x.loc_key=p.loc_key AND x.granule_key=p.granule_key
                JOIN scenes s ON s.scene_key=x.scene_key
                LEFT JOIN items i ON i.item_id=x.item_id
                WHERE {window_filter}
                  AND p.sample_status='sampled_all_bands'
                  AND s.level='L2A'
                QUALIFY row_number() OVER (
                    PARTITION BY p.fs_key, s.scene_key
                    ORDER BY x.read_route, x.item_id
                )=1
            )
            SELECT * FROM sampled
        """)

        # Polygon SCL from pass_samples is one summary class. Obtain the
        # per-pixel SCL values inside the actual default footprint instead.
        con.execute("""
            CREATE TEMP TABLE polygon_clear AS
            SELECT x.loc_key, x.scene_key,
                   count(*) AS scl_pixels,
                   count(*) FILTER (WHERE x.dn IN (4,5)) AS clear_pixels,
                   count(*) FILTER (WHERE x.dn IN (3,8,9,10)) AS cloud_shadow_pixels,
                   count(*) FILTER (WHERE x.dn IN (0,1,2,7,11)) AS other_invalid_pixels,
                   count(*) FILTER (WHERE x.dn=6) AS water_pixels,
                   count(*) FILTER (WHERE x.dn IN (4,5))*1.0/count(*) AS clear_fraction
            FROM pixel_samples x
            JOIN (SELECT DISTINCT loc_key,scene_key FROM candidates
                  WHERE geometry_type='polygon') c
              ON c.loc_key=x.loc_key AND c.scene_key=x.scene_key
            JOIN scenes s ON s.scene_key=x.scene_key
            JOIN footprint_pixels fp
              ON fp.loc_key=x.loc_key AND fp.mgrs_tile=s.mgrs_tile
             AND fp.res_m=x.res_m AND fp.px_row=x.px_row AND fp.px_col=x.px_col
            WHERE x.band='SCL' AND fp.in_default_summary
            GROUP BY x.loc_key, x.scene_key
        """)

        con.execute(f"""
            CREATE TEMP TABLE decisions AS
            WITH measured AS (
                SELECT c.*,
                       pc.scl_pixels, pc.clear_pixels, pc.cloud_shadow_pixels,
                       pc.other_invalid_pixels, pc.water_pixels,
                       CASE WHEN c.geometry_type='polygon' THEN pc.clear_fraction
                            WHEN c.scl IN (4,5) THEN 1.0
                            ELSE 0.0 END AS local_clear_fraction,
                       (c.b02 IS NOT NULL AND c.b03 IS NOT NULL AND
                        c.b04 IS NOT NULL AND c.b05 IS NOT NULL AND
                        c.b06 IS NOT NULL AND c.b07 IS NOT NULL AND
                        c.b08 IS NOT NULL AND c.b8a IS NOT NULL AND
                        c.b11 IS NOT NULL AND c.b12 IS NOT NULL AND
                        c.b02>0 AND c.b03>0 AND c.b04>0 AND
                        c.b05>0 AND c.b06>0 AND c.b07>0 AND
                        c.b08>0 AND c.b8a>0 AND c.b11>0 AND c.b12>0)
                        AS ten_bands_valid
                FROM candidates c
                LEFT JOIN polygon_clear pc ON pc.loc_key=c.loc_key
                                          AND pc.scene_key=c.scene_key
            ), screened AS (
                SELECT *,
                    CASE
                      WHEN NOT ten_bands_valid OR n_pixels<1 THEN 'reject'
                      WHEN geometry_type='point' AND scl IN (0,1,2,3,8,9,10,11)
                           THEN 'reject'
                      WHEN geometry_type='polygon' AND local_clear_fraction IS NOT NULL
                           AND local_clear_fraction < {args.min_clear_fraction}
                           THEN 'reject'
                      WHEN geometry_type='polygon' AND local_clear_fraction IS NULL
                           THEN 'review'
                      WHEN geometry_type='point' AND (scl IS NULL OR scl IN (6,7))
                           THEN 'review'
                      WHEN cld >= {args.review_cloud_probability}
                           THEN 'review'
                      WHEN sun_elevation IS NOT NULL AND sun_elevation<30
                           THEN 'review'
                      ELSE 'keep'
                    END AS decision,
                    CASE
                      WHEN NOT ten_bands_valid OR n_pixels<1 THEN 'missing_or_invalid_band'
                      WHEN geometry_type='point' AND scl IN (0,1,2,3,8,9,10,11)
                           THEN 'local_scl_obstruction'
                      WHEN geometry_type='polygon' AND local_clear_fraction IS NOT NULL
                           AND local_clear_fraction < {args.min_clear_fraction}
                           THEN 'insufficient_clear_field_pixels'
                      WHEN geometry_type='polygon' AND local_clear_fraction IS NULL
                           THEN 'polygon_pixel_quality_unknown'
                      WHEN geometry_type='point' AND (scl IS NULL OR scl IN (6,7))
                           THEN 'local_scl_uncertain_or_water'
                      WHEN cld >= {args.review_cloud_probability}
                           THEN 'high_local_cloud_probability'
                      WHEN sun_elevation IS NOT NULL AND sun_elevation<30
                           THEN 'low_sun_elevation'
                      ELSE 'optically_clear'
                    END AS primary_reason,
                    CASE WHEN geometry_type='point' THEN 'field_boundary_unverified'
                         WHEN scl_pixels<3 THEN 'few_polygon_pixels'
                         ELSE 'polygon_pixels_audited' END AS spatial_support,
                    CASE WHEN planting_date IS NOT NULL AND
                              sensing_time_utc::DATE < planting_date THEN 'before_planting'
                         WHEN harvest_date IS NOT NULL AND
                              sensing_time_utc::DATE > harvest_date THEN 'after_harvest'
                         WHEN planting_date IS NULL OR harvest_date IS NULL THEN 'dates_incomplete'
                         ELSE 'within_recorded_dates' END AS timing_flag
                FROM measured
            )
            SELECT * FROM screened
        """)

        # Hard gates establish eligibility. Score only the eligible scenes;
        # a missing cloud/sun metric receives a neutral score, not a perfect one.
        con.execute(f"""
            CREATE TEMP TABLE monthly_top AS
            WITH eligible AS (
                SELECT *,
                    round(
                      50*greatest(0,least(1,local_clear_fraction))
                      + 25*(CASE WHEN cld IS NULL THEN 0.5
                                 ELSE 1-greatest(0,least(100,cld))/100 END)
                      + 10*(CASE WHEN scene_cloud_cover_percent IS NULL THEN 0.5
                                 ELSE 1-greatest(0,least(100,scene_cloud_cover_percent))/100 END)
                      + CASE timing_flag WHEN 'within_recorded_dates' THEN 10 ELSE 5 END
                      + 5*(CASE WHEN sun_elevation IS NULL THEN 0.5
                                ELSE greatest(0,least(1,(sun_elevation-30)/40)) END),
                      3) AS quality_score
                FROM decisions
                WHERE decision='keep'
                  AND timing_flag IN ('within_recorded_dates','dates_incomplete')
            ), overflight_order AS (
                SELECT *, row_number() OVER (
                    PARTITION BY field_season_id, year, month, acquisition_id
                    ORDER BY quality_score DESC, scene_cloud_cover_percent ASC NULLS LAST,
                             scene_id ASC
                ) AS same_overflight_rank
                FROM eligible
            ), ranked AS (
                SELECT *,
                    row_number() OVER (
                        PARTITION BY field_season_id,year,month
                        ORDER BY CASE WHEN same_overflight_rank=1 THEN 0 ELSE 1 END,
                                 quality_score DESC,
                                 local_clear_fraction DESC,
                                 cld ASC NULLS LAST,
                                 scene_cloud_cover_percent ASC NULLS LAST,
                                 sensing_time_utc ASC, scene_id ASC
                    ) AS quality_rank,
                    count(*) OVER (PARTITION BY field_season_id,year,month)
                        AS eligible_scenes_in_month,
                    count(DISTINCT acquisition_id) OVER
                        (PARTITION BY field_season_id,year,month)
                        AS unique_overflights_in_month
                FROM overflight_order
            )
            SELECT * FROM ranked WHERE quality_rank <= {args.top_k}
        """)

        # Include months with zero selected scenes, using the source coverage
        # table rather than inferring coverage from successful downloads.
        con.execute(f"""
            CREATE TEMP TABLE monthly_coverage AS
            WITH candidates_by_month AS (
                SELECT fs_key,year,month,count(*) AS sampled_scenes,
                       count(*) FILTER (WHERE decision='keep') AS optically_kept_scenes
                FROM decisions GROUP BY 1,2,3
            ), selected_by_month AS (
                SELECT fs_key,year,month,count(*) AS selected_scenes,
                       max(eligible_scenes_in_month) AS eligible_scenes,
                       max(unique_overflights_in_month) AS unique_overflights
                FROM monthly_top GROUP BY 1,2,3
            )
            SELECT f.field_season_id, f.country_iso3, f.dataset, f.crop,
                   cm.year, cm.month, cm.month_status,
                   coalesce(c.sampled_scenes,0) AS sampled_scenes,
                   coalesce(c.optically_kept_scenes,0) AS optically_kept_scenes,
                   coalesce(t.eligible_scenes,0) AS eligible_scenes,
                   coalesce(t.unique_overflights,0) AS unique_overflights,
                   coalesce(t.selected_scenes,0) AS selected_scenes,
                   greatest(0,{args.top_k}-coalesce(t.selected_scenes,0))
                       AS shortfall_to_target
            FROM coverage_months cm
            JOIN scope_fields sf USING (fs_key)
            JOIN fields f USING (fs_key)
            LEFT JOIN candidates_by_month c USING (fs_key,year,month)
            LEFT JOIN selected_by_month t USING (fs_key,year,month)
            WHERE cm.window_kind IN ({"'current'" if args.window_kind == "current" else "'current','previous'"})
        """)

        con.execute(f"COPY decisions TO {quote(args.output / 'scene_decisions.parquet')} (FORMAT PARQUET)")
        con.execute(f"COPY monthly_top TO {quote(args.output / 'monthly_top15.parquet')} (FORMAT PARQUET)")
        con.execute(f"COPY monthly_coverage TO {quote(args.output / 'monthly_coverage.parquet')} (FORMAT PARQUET)")
        summary = {
            "database": str(args.database.resolve()),
            "scope_fields": con.execute("SELECT count(*) FROM scope_fields").fetchone()[0],
            "candidate_rows": con.execute("SELECT count(*) FROM decisions").fetchone()[0],
            "decisions": dict(con.execute("SELECT decision,count(*) FROM decisions GROUP BY 1").fetchall()),
            "top_k": args.top_k,
            "window_kind": args.window_kind,
            "crop": args.crop,
            "selected_scenes": con.execute("SELECT count(*) FROM monthly_top").fetchone()[0],
            "field_months": con.execute("SELECT count(*) FROM monthly_coverage").fetchone()[0],
            "field_months_with_full_target": con.execute(f"SELECT count(*) FROM monthly_coverage WHERE selected_scenes={args.top_k}").fetchone()[0],
            "field_months_with_zero_selected": con.execute("SELECT count(*) FROM monthly_coverage WHERE selected_scenes=0").fetchone()[0],
            "selected_by_country": dict(con.execute("SELECT country_iso3,count(*) FROM monthly_top GROUP BY 1").fetchall()),
            "minimum_polygon_clear_fraction": args.min_clear_fraction,
            "review_cloud_probability": args.review_cloud_probability,
            "notes": [
                "No yield label or model score participates in selection.",
                "Only selected-window sampled L2A scenes are scored; missing overflights require a separate coverage audit.",
                "The clear fraction is computed from polygon footprint SCL pixels. Point field boundaries remain unverified.",
                "Top-k contains only keep scenes within recorded crop dates or with incomplete dates; no rejected/review scenes fill shortages.",
                "Unique overflights rank first; additional clear scenes from the same overflight can fill remaining top-k slots and are marked same_overflight_rank > 1.",
                "The quality score weights are provisional: local clear fraction 50, local cloud 25, scene cloud 10, recorded timing 10, sun elevation 5.",
                "Date metadata is not fully verified, so the crop-timing gate needs a source review before use in final training.",
            ],
        }
        (args.output / "summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
        print(json.dumps(summary,indent=2))
    finally:
        con.close()


if __name__ == "__main__":
    main()
