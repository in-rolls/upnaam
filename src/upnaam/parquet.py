"""Small Parquet artifact utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


def combine_parquet_files(sources: Iterable[Path], output: Path) -> int:
    """Combine schema-identical Parquet artifacts without loading all rows.

    Args:
        sources: Input Parquet paths in desired output order.
        output: Destination Parquet path.

    Returns:
        Number of rows written.

    Raises:
        ValueError: If no rows are supplied or input schemas differ.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    rows = 0
    try:
        for source in sources:
            parquet = pq.ParquetFile(source)
            for batch in parquet.iter_batches():
                table = pa.Table.from_batches([batch])
                if writer is None:
                    writer = pq.ParquetWriter(output, table.schema, compression="zstd")
                if table.schema != writer.schema:
                    raise ValueError(f"Parquet schemas differ: {source}")
                writer.write_table(table)
                rows += table.num_rows
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        raise ValueError("no Parquet rows to combine")
    return rows
