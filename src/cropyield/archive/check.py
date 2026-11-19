"""Check the released pass archive the way a teammate will use it: a copy in an empty folder, opened with
file and network access switched off.

Run: ``python -m cropyield.archive.check``. Exit code 1 when a check fails.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from cropyield.archive import paths, release


def main() -> int:
    source = paths.team_database()
    failures: list[str] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        print(("PASS  " if passed else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
        if not passed:
            failures.append(name)

    with tempfile.TemporaryDirectory(prefix="passarchive_check_") as folder:
        copy = Path(folder) / source.name
        shutil.copy2(source, copy)
        check("checksum of the copy equals SHA256SUMS",
              release.sha256(copy) == (source.parent / "SHA256SUMS").read_text(encoding="utf-8").split()[0])
        con = duckdb.connect(str(copy), read_only=True, config={"enable_external_access": "false"})
        one = lambda sql, *args: con.execute(sql, list(args)).fetchone()[0]

        # ---- keys and completeness of the survey side
        check("source_observation_id is unique", one("select count(*) = count(distinct source_observation_id) from source_records"))
        check("every source row has a field-season", one("select count(*) from source_records where field_season_id not in (select field_season_id from fields)") == 0)
        check("field_season_id is unique", one("select count(*) = count(distinct field_season_id) from fields"))
        check("one label row per field-season", one("select (select count(*) from labels) = (select count(*) from fields)"))
        legacy = one("select count(*) from fields where legacy_cohort is not null")
        check("all 11,364 old labels are present", legacy == 11364, f"{legacy}")
        check("zero, blank and crop failure are different states",
              one("select count(distinct label_status) from labels") >= 4
              and one("select count(*) from labels where label_status = 'recorded_zero' and yield_kg_ha <> 0") == 0
              and one("select count(*) from labels where label_status in ('not_answered','not_measured') and yield_kg_ha is not null") == 0)
        check("no unusable location has passes", one("select count(*) from passes p join fields f using (fs_key) where not f.usable_at_field_scale") == 0)
        frozen = one("select count(*) from split_specs where frozen")
        same = one("select count(*) from split_specs c where frozen and rows = (select count(*) from splits s where s.split_name = c.split_name)")
        check("every frozen split has all its rows", frozen == same and frozen > 0, f"{same} of {frozen}")

        # ---- time windows and pass counting
        check("24 month cells per dated field-season",
              one("select count(*) from (select fs_key from coverage_months group by 1 having count(*) <> 24)") == 0)
        check("every pass lies in its half-open UTC window",
              one("""select count(*) from passes p join fields f using (fs_key)
                     where not (p.sensing_time_utc >= make_timestamp(cast(case when p.window_kind = 'current' then f.harvest_year else f.harvest_year - 1 end as bigint), 1, 1, 0, 0, 0)
                            and p.sensing_time_utc < make_timestamp(cast(case when p.window_kind = 'current' then f.harvest_year + 1 else f.harvest_year end as bigint), 1, 1, 0, 0, 0))
                        or p.year <> year(p.sensing_time_utc) or p.month <> month(p.sensing_time_utc)""") == 0)
        check("a pass is listed once per field-season and granule",
              one("select count(*) from (select fs_key, granule_key from passes group by all having count(*) > 1)") == 0)
        check("an overflight counts once, whatever the tiles and levels",
              one("select count(*) from (select fs_key, acquisition_id from v_overflights group by all having count(*) > 1)") == 0)
        check("month counts equal the passes table",
              one("select (select sum(n_passes) from coverage_months) = (select count(*) from passes)"))
        check("master holds every pass and every field-season, once",
              one("select count(*) from master") == one("select count(*) from passes")
              + one("select count(*) from fields where fs_key not in (select fs_key from passes)")
              and one("select count(distinct field_season_id) from master") == one("select count(*) from fields"))
        rows, in_lists = con.execute("select count(*), sum(n_passes) from field_xy").fetchone()
        check("field_xy has one row per field-season and holds every pass in its lists",
              rows == one("select count(*) from fields") and in_lists == one("select count(*) from passes"),
              f"{rows:,} rows, {in_lists:,} passes")
        check("no catalogue request failed", one("select count(*) from catalog_queries where status <> 'ok'") == 0)

        # ---- values
        check("a measurement is stored once per location and scene",
              one("select count(*) from (select loc_key, scene_key from pass_samples group by all having count(*) > 1)") == 0)
        low, high = con.execute("""select quantile_cont(b04, 0.01), quantile_cont(b04, 0.99) from v_reflectance
                                   where b04 is not null""").fetchone()
        check("red reflectance is in a physical range (offset applied once)",
              low is not None and -0.05 < low < 0.3 and 0.02 < high < 1.2, f"1 % {low:.3f}, 99 % {high:.3f}")

        # ---- the four uses
        field = con.execute("""select fs_key, any_value(year), any_value(month) from pass_bands_wide
                               where read_route = 'direct_cog_all_bands' group by fs_key, year, month
                               order by count(*) desc, fs_key limit 1""").fetchone()
        if field is None:
            check("a field with all-band samples exists", False)
        else:
            fs_key, year, month = field
            listed = con.execute("select count(*), count(distinct acquisition_id) from passes where fs_key = ? and year = ? and month = ?",
                                 [fs_key, year, month]).fetchone()
            bands = con.execute("select * from pass_bands_wide where fs_key = ? and year = ? and month = ? order by sensing_time_utc",
                                [fs_key, year, month]).df()
            print(f"\n(a) field-season fs_key {fs_key}, {year}-{month:02d}: {listed[0]} passes of {listed[1]} overflights listed, "
                  f"{len(bands)} with band values")
            print(bands[["sensing_time_utc", "mgrs_tile", "scene_cloud_cover_percent", "sample_status", "b02", "b04", "b08", "b11", "scl"]]
                  .to_string(index=False))
            check("(a) every acquisition of one field in one month, with bands", listed[0] > 0 and len(bands) > 0)
            months = con.execute("select window_kind, year, month, n_passes, n_overflights, n_outside_swath_per_catalogue, n_sampled_all_bands, n_not_sampled, month_status "
                                 "from coverage_months where fs_key = ? order by year, month", [fs_key]).df()
            print("\n(b) all 24 months of that field-season\n" + months.to_string(index=False))
            check("(b) 24 months, empty months included", len(months) == 24)
            rules = con.execute("""
                select year, month, a.ndvi_median_scl_vegetation_or_bare, b.gcvi_max_cloud_probability_below_20
                from (select year, month, median(ndvi) ndvi_median_scl_vegetation_or_bare from v_ndvi_v1
                      where fs_key = ? and scl in (4, 5) group by all) a
                full join (select year, month, max(gcvi) gcvi_max_cloud_probability_below_20 from v_gcvi_v1
                           where fs_key = ? and (cld < 20 or (cld is null and scl in (4, 5, 6))) group by all) b
                using (year, month) order by 1, 2""", [fs_key, fs_key]).df()
            print("\n(c) two monthly rules from the same passes\n" + rules.to_string(index=False))
            check("(c) two different monthly rules from the same passes", len(rules) > 0)
        name = "frozen/v2/zimbabwe_lacuna_2022_2023/s1_cc2km"
        joined = con.execute("""select s.fold, count(*) fields, round(avg(l.yield_kg_ha)) mean_yield_kg_ha
                                from splits s join labels l using (fs_key) where s.split_name = ? group by 1 order by 1""",
                             [name]).df()
        print(f"\n(d) split {name} joined to labels\n" + joined.to_string(index=False))
        check("(d) a named split joined to labels", len(joined) == 5 and int(joined.fields.sum()) == 1880)
        con.close()

        # ---- a new split in a scratch copy leaves the frozen ones as they are
        scratch = Path(folder) / "scratch.duckdb"
        shutil.copy2(copy, scratch)
        con = duckdb.connect(str(scratch), read_only=True)
        before = con.execute("select md5(string_agg(split_name || field_season_id || fold, ',' order by split_name, field_season_id)) "
                             "from splits").fetchone()[0]
        mine = con.execute("select field_season_id, fs_key % 3 as fold from fields where legacy_cohort = 'malawi_2023'").df()
        con.close()
        csv = Path(folder) / "my_split.csv"
        mine.to_csv(csv, index=False)
        added = release.register_split(scratch, "team/example/v1", csv)
        con = duckdb.connect(str(scratch), read_only=True)
        after = con.execute("select md5(string_agg(split_name || field_season_id || fold, ',' order by split_name, field_season_id)) "
                            "from splits where split_name like 'frozen/%'").fetchone()[0]
        con.close()
        check("a new split is added and the frozen memberships do not change", added == len(mine) and before == after,
              f"{added} rows added")
        try:
            release.register_split(scratch, "team/example/v1", csv)
            check("a split name cannot be used twice", False)
        except SystemExit:
            check("a split name cannot be used twice", True)
    print(f"\n{len(failures)} failed" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 60)
    sys.exit(main())
