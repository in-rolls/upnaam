"""Read-only SQLite access inside indexed, multipart gzip archives."""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import uuid
from bisect import bisect_right
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import apsw
import indexed_gzip

from upnaam.artifacts import sha256_file

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from typing import BinaryIO

INDEX_REVISION = "indexed-gzip-sqlite-v1"


class MultipartFile(io.RawIOBase):
    """Expose ordered file parts as one seekable binary stream."""

    def __init__(self, paths: Sequence[Path]) -> None:
        """Open a sequence of nonempty file parts.

        Args:
            paths: Ordered paths forming one logical byte stream.

        Raises:
            ValueError: If no parts are supplied or a part is empty.
        """
        super().__init__()
        self._file_stack = ExitStack()
        self._files: list[BinaryIO] = []
        if not paths:
            raise ValueError("at least one compressed file part is required")
        resolved = [path.resolve(strict=True) for path in paths]
        sizes = [path.stat().st_size for path in resolved]
        if any(size == 0 for size in sizes):
            raise ValueError("compressed file parts must be nonempty")

        with ExitStack() as opening:
            for path in resolved:
                self._files.append(opening.enter_context(path.open("rb")))
            self._file_stack = opening.pop_all()
        self._sizes = sizes
        self._starts: list[int] = []
        total = 0
        for size in sizes:
            self._starts.append(total)
            total += size
        self._size = total
        self._position = 0

    def readable(self) -> bool:
        """Return whether the stream supports reads."""
        return True

    def seekable(self) -> bool:
        """Return whether the stream supports random access."""
        return True

    def tell(self) -> int:
        """Return the logical compressed-stream position."""
        self._checkClosed()
        return self._position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        """Move to a logical compressed-stream position.

        Args:
            offset: Byte offset relative to ``whence``.
            whence: One of ``SEEK_SET``, ``SEEK_CUR``, or ``SEEK_END``.

        Returns:
            New logical position.

        Raises:
            ValueError: If ``whence`` is unsupported or the result is negative.
        """
        self._checkClosed()
        if whence == io.SEEK_CUR:
            offset += self._position
        elif whence == io.SEEK_END:
            offset += self._size
        elif whence != io.SEEK_SET:
            raise ValueError(f"unsupported whence: {whence}")
        if offset < 0:
            raise ValueError("negative seek position")
        self._position = min(offset, self._size)
        return self._position

    def read(self, size: int = -1) -> bytes:
        """Read bytes across part boundaries.

        Args:
            size: Maximum bytes to read, or a negative value for the remainder.

        Returns:
            Bytes read from the logical stream.
        """
        self._checkClosed()
        if size is None or size < 0:
            size = self._size - self._position
        remaining = min(size, self._size - self._position)
        chunks: list[bytes] = []
        while remaining > 0:
            part_index = bisect_right(self._starts, self._position) - 1
            local_offset = self._position - self._starts[part_index]
            requested = min(remaining, self._sizes[part_index] - local_offset)
            handle = self._files[part_index]
            handle.seek(local_offset)
            chunk = handle.read(requested)
            if not chunk:
                break
            chunks.append(chunk)
            self._position += len(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def close(self) -> None:
        """Close every underlying file part."""
        if not self.closed:
            self._file_stack.close()
        super().close()


class _IndexedDatabaseFile(apsw.VFSFile):
    """APSW file backed by an indexed decompressed stream."""

    def __init__(
        self,
        stream: indexed_gzip.IndexedGzipFile,
        size: int,
        lock: threading.Lock,
        flags: list[int],
    ) -> None:
        readonly_flags = [apsw.SQLITE_OPEN_READONLY, apsw.SQLITE_OPEN_READONLY]
        super().__init__("", os.devnull, readonly_flags)
        flags[1] = apsw.SQLITE_OPEN_READONLY
        self._stream = stream
        self._size = size
        self._lock = lock

    def xRead(self, amount: int, offset: int) -> bytes:  # noqa: N802
        """Read exactly one SQLite page range."""
        with self._lock:
            self._stream.seek(offset)
            data = self._stream.read(amount)
        if len(data) != amount:
            raise apsw.IOError(f"short read at {offset}: {len(data)} of {amount}")
        return data

    def xFileSize(self) -> int:  # noqa: N802
        """Return the decompressed SQLite file size."""
        return self._size


class _IndexedDatabaseVFS(apsw.VFS):
    """Read-only APSW VFS for one indexed gzip stream."""

    def __init__(
        self,
        stream: indexed_gzip.IndexedGzipFile,
        size: int,
    ) -> None:
        name = f"upnaam-indexed-gzip-{uuid.uuid4().hex}"
        super().__init__(name, "")
        self.vfs_name = name
        self._stream = stream
        self._size = size
        self._lock = threading.Lock()

    def xOpen(  # noqa: N802
        self,
        name: str | apsw.URIFilename | None,
        flags: list[int],
    ) -> apsw.VFSFile:
        """Open only the synthetic main database file."""
        del name
        if not flags[0] & apsw.SQLITE_OPEN_MAIN_DB:
            raise apsw.ReadOnlyError("only the main read-only database is supported")
        return _IndexedDatabaseFile(self._stream, self._size, self._lock, flags)


def _part_fingerprints(parts: Sequence[Path]) -> list[dict[str, Any]]:
    """Fingerprint ordered archive parts without recording local directories."""
    fingerprints = []
    for number, path in enumerate(parts, start=1):
        resolved = path.resolve(strict=True)
        if resolved.stat().st_size == 0:
            raise ValueError("compressed file parts must be nonempty")
        fingerprints.append(
            {
                "part": number,
                "name": resolved.name,
                "bytes": resolved.stat().st_size,
                "sha256": sha256_file(resolved),
            }
        )
    if not fingerprints:
        raise ValueError("at least one compressed file part is required")
    return fingerprints


def _manifest_path(index_path: Path) -> Path:
    """Return the sidecar manifest path for an index."""
    return index_path.with_suffix(f"{index_path.suffix}.json")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(path)


def build_gzip_sqlite_index(
    parts: Sequence[Path],
    index_path: Path,
) -> dict[str, Any]:
    """Build a reusable seek index for a multipart gzip-compressed SQLite file.

    Args:
        parts: Ordered gzip archive parts.
        index_path: Destination for the indexed-gzip index.

    Returns:
        Index manifest payload.

    Raises:
        RuntimeError: If a source part changes while the index is built.
    """
    before = _part_fingerprints(parts)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=index_path.parent,
        prefix=f".{index_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_stream:
        temporary = Path(temporary_stream.name)
    try:
        with (
            MultipartFile(parts) as source,
            indexed_gzip.IndexedGzipFile(fileobj=source) as stream,
        ):
            stream.build_full_index()
            stream.seek(0, io.SEEK_END)
            uncompressed_bytes = stream.tell()
            stream.export_index(str(temporary))
        after = _part_fingerprints(parts)
        if before != after:
            raise RuntimeError("compressed source changed while building its index")
        temporary.replace(index_path)
    finally:
        temporary.unlink(missing_ok=True)

    payload = {
        "revision": INDEX_REVISION,
        "parts": after,
        "uncompressed_bytes": uncompressed_bytes,
        "index": {
            "bytes": index_path.stat().st_size,
            "sha256": sha256_file(index_path),
        },
    }
    _write_json(_manifest_path(index_path), payload)
    return payload


def _load_valid_manifest(parts: Sequence[Path], index_path: Path) -> dict[str, Any]:
    """Load an index manifest and verify every content fingerprint."""
    manifest_path = _manifest_path(index_path)
    if not index_path.exists() or not manifest_path.exists():
        raise FileNotFoundError(
            f"index and manifest are both required: {index_path}, {manifest_path}"
        )
    with manifest_path.open(encoding="utf-8") as stream:
        payload: dict[str, Any] = json.load(stream)
    if payload.get("revision") != INDEX_REVISION:
        raise RuntimeError("unsupported compressed SQLite index revision")
    if payload.get("parts") != _part_fingerprints(parts):
        raise RuntimeError("compressed source does not match the index manifest")
    index = payload.get("index")
    expected_index = {
        "bytes": index_path.stat().st_size,
        "sha256": sha256_file(index_path),
    }
    if index != expected_index:
        raise RuntimeError("seek index does not match its manifest")
    size = payload.get("uncompressed_bytes")
    if not isinstance(size, int) or size <= 0:
        raise RuntimeError("index manifest has an invalid uncompressed size")
    return payload


@contextmanager
def open_gzip_sqlite(
    parts: Sequence[Path],
    index_path: Path,
    *,
    rebuild_index: bool = False,
) -> Iterator[apsw.Connection]:
    """Open a gzip-compressed SQLite database for targeted read-only queries.

    Args:
        parts: Ordered gzip archive parts.
        index_path: Existing or new indexed-gzip index path.
        rebuild_index: Rebuild the index and its manifest before opening.

    Yields:
        Read-only APSW connection to the decompressed logical database.
    """
    manifest_path = _manifest_path(index_path)
    if rebuild_index or (not index_path.exists() and not manifest_path.exists()):
        manifest = build_gzip_sqlite_index(parts, index_path)
    else:
        manifest = _load_valid_manifest(parts, index_path)

    source = MultipartFile(parts)
    stream = indexed_gzip.IndexedGzipFile(fileobj=source)
    vfs: _IndexedDatabaseVFS | None = None
    connection: apsw.Connection | None = None
    try:
        stream.import_index(str(index_path))
        vfs = _IndexedDatabaseVFS(stream, manifest["uncompressed_bytes"])
        connection = apsw.Connection(
            "compressed.sqlite",
            flags=apsw.SQLITE_OPEN_READONLY,
            vfs=vfs.vfs_name,
        )
        yield connection
    finally:
        if connection is not None:
            connection.close()
        if vfs is not None:
            vfs.unregister()
        stream.close()
        source.close()
