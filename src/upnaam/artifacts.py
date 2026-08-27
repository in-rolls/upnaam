"""Artifact manifests and source configuration."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path


def load_source_config(path: Path) -> dict[str, Any]:
    """Load a source configuration and resolve its data paths.

    Args:
        path: JSON configuration path. Relative data paths are interpreted from
            the repository containing the configuration directory.

    Returns:
        Parsed configuration with absolute paths represented as strings.
    """
    with path.open(encoding="utf-8") as stream:
        config: dict[str, Any] = json.load(stream)
    repository = path.resolve().parent.parent
    for section in config.values():
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            if isinstance(value, str):
                section[key] = str((repository / value).resolve())
    return config


def sha256_file(path: Path, *, block_size: int = 1024 * 1024) -> str:
    """Hash a file without loading it into memory.

    Args:
        path: File to hash.
        block_size: Bytes read per iteration.

    Returns:
        Lowercase hexadecimal SHA-256 digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def source_fingerprint(path: Path) -> dict[str, Any]:
    """Describe and hash one file or directory artifact.

    Args:
        path: Existing source artifact.

    Returns:
        Stable metadata including content digests.

    Raises:
        FileNotFoundError: If the artifact does not exist.
    """
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(resolved)
    if resolved.is_file():
        stat = resolved.stat()
        return {
            "path": str(resolved),
            "kind": "file",
            "bytes": stat.st_size,
            "sha256": sha256_file(resolved),
        }
    files = sorted(item for item in resolved.rglob("*") if item.is_file())
    digest = hashlib.sha256()
    total_bytes = 0
    for item in files:
        relative = item.relative_to(resolved).as_posix()
        file_digest = sha256_file(item)
        size = item.stat().st_size
        total_bytes += size
        digest.update(f"{relative}\0{size}\0{file_digest}\n".encode())
    return {
        "path": str(resolved),
        "kind": "directory",
        "files": len(files),
        "bytes": total_bytes,
        "sha256": digest.hexdigest(),
    }


def write_manifest(
    path: Path,
    *,
    stage: str,
    inputs: Iterable[Path],
    outputs: Iterable[Path],
    row_counts: Mapping[str, int],
    parameters: Mapping[str, Any],
) -> None:
    """Write a reproducibility manifest for a completed stage.

    Args:
        path: Destination JSON path.
        stage: Stable stage identifier.
        inputs: Input artifacts to fingerprint.
        outputs: Produced artifacts to fingerprint.
        row_counts: Named input and output row counts.
        parameters: Effective stage configuration.
    """
    payload = {
        "stage": stage,
        "created_at": datetime.now(UTC).isoformat(),
        "inputs": [source_fingerprint(item) for item in inputs],
        "outputs": [source_fingerprint(item) for item in outputs],
        "row_counts": dict(row_counts),
        "parameters": dict(parameters),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(path)
