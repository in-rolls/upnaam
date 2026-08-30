# Targeted queries over compressed SQLite

Upnaam can query a gzip-compressed SQLite database without writing the full
decompressed database to disk. This matters for the Bihar ration source: its
two archive parts occupy about 3.30 GB, while the logical SQLite database is
56,741,351,424 bytes.

The generic adapter treats ordered archive parts as one compressed byte stream,
builds an [`indexed-gzip`](https://github.com/pauldmccarthy/indexed_gzip)
seek index, and exposes decompressed byte ranges to SQLite through a read-only
[APSW virtual file system](https://rogerbinns.github.io/apsw/vfs.html). The
index is built once and reused. For the Bihar source it is 417,660,907 bytes,
or about 398 MiB.

Install the optional dependencies:

```console
pip install "upnaam[compressed-sqlite]"
```

Then issue ordinary targeted SQL:

```python
from pathlib import Path

from upnaam.compressed_sqlite import open_gzip_sqlite

parts = [
    Path("ration_cards.sqlite.gz.001"),
    Path("ration_cards.sqlite.gz.002"),
]
index = Path("ration_cards.sqlite.gzidx")

with open_gzip_sqlite(parts, index) as connection:
    rows = connection.execute(
        "SELECT id, members_qty, sub_table FROM family_members_tables WHERE id = ?",
        ("00000001",),
    ).fetchall()
```

The connection is always read-only. Each index has a JSON sidecar recording the
ordered source-part hashes, decompressed size, index hash, and implementation
revision. Upnaam refuses to use a stale, partial, or unverified index. Pass
`rebuild_index=True` only when deliberately replacing the index after a source
change.

This mechanism makes indexed point lookups practical. The Bihar database has
primary-key indexes on `family_members_tables.id` and
`ration_card_details.ration_card_number`; queries on those keys are targeted
lookups. It does not make an unindexed predicate cheap: a filter such as
`ration_card_details.village_id = ?` still scans that table. Nor does the
adapter alter the data or turn the ration transcription into a surname label.
Source-specific name selection remains a separate pipeline stage.
