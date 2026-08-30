"""Standard CSV and Parquet input/output for Upnaam commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pandas as pd

if TYPE_CHECKING:
    from pathlib import Path


def read_table(path: Path) -> pd.DataFrame:
    """Read a CSV, compressed CSV, or Parquet table."""
    suffixes = path.suffixes
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv" or suffixes[-2:] == [".csv", ".gz"]:
        return cast("pd.DataFrame", pd.read_csv(path))
    raise ValueError(f"unsupported table format: {path}")


def write_table(frame: pd.DataFrame, path: Path) -> None:
    """Write a CSV, compressed CSV, or Parquet table atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    suffixes = path.suffixes
    try:
        if path.suffix == ".parquet":
            frame.to_parquet(temporary, index=False)
        elif path.suffix == ".csv":
            frame.to_csv(temporary, index=False)
        elif suffixes[-2:] == [".csv", ".gz"]:
            frame.to_csv(
                temporary,
                index=False,
                compression=cast("Any", {"method": "gzip", "mtime": 0}),
            )
        else:
            raise ValueError(f"unsupported table format: {path}")
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
