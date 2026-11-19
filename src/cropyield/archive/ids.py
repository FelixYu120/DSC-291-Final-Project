"""Key functions of the pass archive. Every key is a pure function of provider facts, so a rebuild from the
same inputs gives the same keys.

Survey side
    source_observation_id   ``<dataset>:<provider id>`` or ``<dataset>:r<row>``; equals the legacy ``obs_id``.
    field_season_id         ``fs_`` + 16 hex of SHA-1 of the smallest confidently linked source_observation_id.
    location_id             ``loc_`` + 16 hex of SHA-1 of the canonical WGS84 geometry text.

Satellite side (all taken from the ESA product and granule names, never from one provider's item id)
    acquisition_id          one physical overflight (datatake): ``S2B_20190626T074619``.
    granule_id              overflight x datastrip x MGRS tile: ``S2B_20190626T074619_T36NXF_S20190626T080334``.
    scene_id                one processed product version: the ESA product name without ``.SAFE``.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# S2B_MSIL2A_20190626T074619_N0212_R135_T36NXF_20190626T110744
PRODUCT_NAME = re.compile(
    r"^(?P<platform>S2[A-D])_MSI(?P<level>L1C|L2A)_(?P<datatake_start>\d{8}T\d{6})_N(?P<baseline>\d{4})"
    r"_R(?P<relative_orbit>\d{3})_T(?P<tile>[0-9]{2}[A-Z]{3})_(?P<discriminator>\d{8}T\d{6})$"
)
# S2B_OPER_MSI_L2A_DS_MTI__20190626T110744_S20190626T080334_N02.12  (the S field is the datastrip sensing start)
DATASTRIP_ID = re.compile(r"^S2[A-D]_OPER_MSI_L(?:1C|2A)_DS_\w{4}_\d{8}T\d{6}_S(?P<datastrip_start>\d{8}T\d{6})_N\d{2}\.\d{2}$")
# S2B_OPER_MSI_L2A_TL_MTI__20190626T110744_A012030_T36NXF_N02.12
GRANULE_ID = re.compile(
    r"^S2[A-D]_OPER_MSI_L(?:1C|2A)_TL_\w{4}_\d{8}T\d{6}_A(?P<absolute_orbit>\d{6})_T(?P<tile>[0-9]{2}[A-Z]{3})_N\d{2}\.\d{2}$"
)


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def source_observation_id(dataset: str, provider_id: str | None, row_number: int | None = None) -> str:
    """``<dataset>:<provider id>``; without a provider id, ``<dataset>:r<row>`` (1-based data row, 6 digits)."""
    if provider_id is not None and str(provider_id).strip() != "":
        return f"{dataset}:{str(provider_id).strip()}"
    if row_number is None:
        raise ValueError("a record with no provider id needs its row number")
    return f"{dataset}:r{int(row_number):06d}"


def field_season_id(linked_source_observation_ids: list[str] | tuple[str, ...]) -> str:
    """Key of one crop on one field in one season, from its confidently linked source records."""
    if not linked_source_observation_ids:
        raise ValueError("a field-season needs at least one source record")
    return "fs_" + _digest(min(linked_source_observation_ids))


def location_id(geometry_wkt_wgs84: str) -> str:
    """Key of one sampling geometry. Pass the canonical WKT (see ``contract.canonical_wkt``)."""
    return "loc_" + _digest(geometry_wkt_wgs84)


@dataclass(frozen=True)
class ProductName:
    platform: str
    level: str
    datatake_start: str
    baseline: str          # "02.12"
    relative_orbit: int
    tile: str
    discriminator: str

    @property
    def scene_id(self) -> str:
        return (f"{self.platform}_MSI{self.level}_{self.datatake_start}_N{self.baseline.replace('.', '')}"
                f"_R{self.relative_orbit:03d}_T{self.tile}_{self.discriminator}")

    @property
    def acquisition_id(self) -> str:
        return f"{self.platform}_{self.datatake_start}"


def parse_product_name(name: str) -> ProductName:
    """Parse an ESA single-tile product name (with or without ``.SAFE``). Raises ValueError on any other text."""
    text = name.strip()
    if text.upper().endswith(".SAFE"):
        text = text[:-5]
    match = PRODUCT_NAME.match(text)
    if match is None:
        raise ValueError(f"not a single-tile Sentinel-2 product name: {name!r}")
    parts = match.groupdict()
    baseline = parts["baseline"]
    return ProductName(parts["platform"], parts["level"], parts["datatake_start"], f"{baseline[:2]}.{baseline[2:]}",
                       int(parts["relative_orbit"]), parts["tile"], parts["discriminator"])


def acquisition_id(platform: str, datatake_start: str) -> str:
    return f"{platform}_{datatake_start}"


def granule_id(platform: str, datatake_start: str, tile: str, datastrip_start: str) -> str:
    """One granule: the same for L1C, L2A and every reprocessing of that tile of that datastrip."""
    return f"{platform}_{datatake_start}_T{tile}_S{datastrip_start}"


def datastrip_start(datastrip_identifier: str) -> str:
    match = DATASTRIP_ID.match(datastrip_identifier.strip())
    if match is None:
        raise ValueError(f"not a datastrip identifier: {datastrip_identifier!r}")
    return match.group("datastrip_start")
