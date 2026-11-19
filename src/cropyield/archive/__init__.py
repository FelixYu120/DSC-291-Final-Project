"""The shared crop-yield and Sentinel-2 pass archive (release ``passarchive_v1``).

It records what the surveys reported and what the satellite observed, with no cloud mask, no monthly rule
and no split applied. Four steps, run in this order (each is a module):

    python -m cropyield.archive.survey      every survey row, field-seasons, labels, frozen splits
    python -m cropyield.archive.catalog     every Sentinel-2 product over every usable location
    python -m cropyield.archive.sampling    native-pixel band values from the public files (resumable)
    python -m cropyield.archive.release build    the portable DuckDB file with README and dictionary
"""

RELEASE = "passarchive_v1"
