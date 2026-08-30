import gzip
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import apsw
import pytest

from upnaam.compressed_sqlite import (
    INDEX_REVISION,
    MultipartFile,
    build_gzip_sqlite_index,
    open_gzip_sqlite,
)


def _compressed_database(tmp_path: Path) -> tuple[list[Path], Path]:
    database = tmp_path / "source.sqlite"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT)")
        connection.executemany(
            "INSERT INTO people (name) VALUES (?)",
            [("Asha Devi",), ("Manoj Kumar Raut",), ("Rani Yadav",)],
        )
        connection.commit()

    compressed = gzip.compress(database.read_bytes())
    split_at = len(compressed) // 2
    parts = [tmp_path / "source.sqlite.gz.001", tmp_path / "source.sqlite.gz.002"]
    parts[0].write_bytes(compressed[:split_at])
    parts[1].write_bytes(compressed[split_at:])
    return parts, tmp_path / "source.sqlite.gzidx"


def test_multipart_file_reads_across_boundaries(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.write_bytes(b"abc")
    second.write_bytes(b"defg")

    with MultipartFile([first, second]) as stream:
        stream.seek(2)
        assert stream.read(4) == b"cdef"
        stream.seek(-2, 2)
        assert stream.read() == b"fg"


@pytest.mark.parametrize("parts", [[], ["empty"]])
def test_multipart_file_rejects_missing_content(
    tmp_path: Path, parts: list[str]
) -> None:
    paths = [tmp_path / part for part in parts]
    for path in paths:
        path.touch()

    with pytest.raises(ValueError, match=r"required|nonempty"):
        MultipartFile(paths)


def test_build_and_query_compressed_database(tmp_path: Path) -> None:
    parts, index_path = _compressed_database(tmp_path)

    manifest = build_gzip_sqlite_index(parts, index_path)

    assert manifest["revision"] == INDEX_REVISION
    assert manifest["uncompressed_bytes"] > 0
    assert [part["part"] for part in manifest["parts"]] == [1, 2]
    assert index_path.exists()
    manifest_path = index_path.with_suffix(".gzidx.json")
    assert json.loads(manifest_path.read_text())["index"]["bytes"] > 0

    with open_gzip_sqlite(parts, index_path) as connection:
        rows = list(connection.execute("SELECT id, name FROM people ORDER BY id"))
        assert rows == [
            (1, "Asha Devi"),
            (2, "Manoj Kumar Raut"),
            (3, "Rani Yadav"),
        ]
        assert connection.readonly("main")
        with pytest.raises(apsw.ReadOnlyError):
            connection.execute("INSERT INTO people (name) VALUES ('No')")

    with open_gzip_sqlite(parts, index_path) as connection:
        assert connection.execute("SELECT count(*) FROM people").fetchone() == (3,)


def test_open_builds_missing_index(tmp_path: Path) -> None:
    parts, index_path = _compressed_database(tmp_path)

    with open_gzip_sqlite(parts, index_path) as connection:
        assert connection.execute(
            "SELECT name FROM people WHERE id = 2"
        ).fetchone() == ("Manoj Kumar Raut",)

    assert index_path.exists()
    assert index_path.with_suffix(".gzidx.json").exists()


def test_open_rejects_source_that_no_longer_matches(tmp_path: Path) -> None:
    parts, index_path = _compressed_database(tmp_path)
    build_gzip_sqlite_index(parts, index_path)
    parts[1].write_bytes(parts[1].read_bytes() + b"changed")

    with (
        pytest.raises(RuntimeError, match="source does not match"),
        open_gzip_sqlite(parts, index_path),
    ):
        pass


def test_open_rejects_index_without_manifest(tmp_path: Path) -> None:
    parts, index_path = _compressed_database(tmp_path)
    index_path.write_bytes(b"untrusted")

    with (
        pytest.raises(FileNotFoundError, match="index and manifest"),
        open_gzip_sqlite(parts, index_path),
    ):
        pass
