"""Read-only source inventory checks."""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


def _csv_profile(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, mode="rt", encoding="utf-8", newline="") as stream:
            columns = next(csv.reader(stream))
    else:
        with path.open(encoding="utf-8", newline="") as stream:
            columns = next(csv.reader(stream))
    return {
        "path": str(path),
        "format": "csv",
        "columns": columns,
        "bytes": path.stat().st_size,
    }


def _parquet_profile(path: Path) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    return {
        "path": str(path),
        "format": "parquet",
        "rows": parquet.metadata.num_rows,
        "row_groups": parquet.metadata.num_row_groups,
        "columns": parquet.schema_arrow.names,
        "bytes": path.stat().st_size,
    }


def profile_configured_sources(config: dict[str, Any]) -> dict[str, Any]:
    """Profile required local sources without querying cloud services.

    Args:
        config: Resolved source configuration.

    Returns:
        Nested schema, size, and coverage inventory.

    Raises:
        FileNotFoundError: If a configured source or partition set is missing.
    """
    profile: dict[str, Any] = {"electoral_name_tables": {}, "external_sources": {}}
    for state, value in config["electoral_name_tables"].items():
        path = Path(value)
        if not path.exists():
            raise FileNotFoundError(path)
        profile["electoral_name_tables"][state] = _csv_profile(path)

    bihar = config["bihar_land"]
    profile["external_sources"]["bihar_land"] = {
        "accepted_links": _parquet_profile(Path(bihar["accepted_links"])),
        "roll_records": _parquet_profile(Path(bihar["roll_records"])),
        "linkage_limit": (
            "The accepted links require exact normalized elector and relative names; "
            "they are excluded from edit and omission learning."
        ),
    }
    rajasthan = config["rajasthan_ration"]
    link_files = sorted(Path(rajasthan["person_links"]).glob("bucket_*.parquet"))
    roll_files = sorted(Path(rajasthan["roll_households"]).glob("bucket=*/*.parquet"))
    ration_files = sorted(
        Path(rajasthan["ration_households"]).glob("bucket=*/*.parquet")
    )
    if not link_files or not roll_files or not ration_files:
        raise FileNotFoundError("Rajasthan link or household partitions are missing")
    profile["external_sources"]["rajasthan_ration"] = {
        "person_link_partitions": len(link_files),
        "roll_partitions": len(roll_files),
        "ration_partitions": len(ration_files),
        "accepted_tiers": rajasthan["accepted_tiers"],
        "age_offset_audit": str(rajasthan["age_offset_audit"]),
        "person_links_example": _parquet_profile(link_files[0]),
        "roll_example": _parquet_profile(roll_files[0]),
        "ration_example": _parquet_profile(ration_files[0]),
    }
    return profile


def write_profile(profile: dict[str, Any], output: Path) -> None:
    """Write a source profile as stable JSON.

    Args:
        profile: Source inventory.
        output: Destination path.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        json.dump(profile, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
