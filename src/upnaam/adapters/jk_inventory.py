"""Validated handoffs from reconciled historical J&K inventories."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq

from upnaam.adapters.electors import ElectorSource, build_elector_artifact
from upnaam.artifacts import sha256_file

if TYPE_CHECKING:
    from collections.abc import Callable

    from upnaam.normalization import NameToken


@dataclass(frozen=True)
class InventoryProfile:
    """The fixed parser and evidence contract for one source language."""

    source: ElectorSource
    language: str
    parser_filename: str
    filename_pattern: str
    relationships: dict[str, str]
    accept_name: Callable[[object, object], str | None]
    accept_house: Callable[[object, object], str | None]
    description: str
    limitations: tuple[str, ...]
    module_path: Path


STRING_FIELDS = [
    "filename",
    "number",
    "id",
    "relationship",
    "relationship_source",
    "father_or_husband_name",
    "elector_name",
    "house_no",
    "age",
    "sex",
    "ac_name",
    "district",
    "part_no",
    "year",
    "source_sha256",
    "entry_event_key",
    "event_key",
    "elector_name_source",
    "relative_name_source",
    "house_no_source",
]
SCHEMA = pa.schema(
    [(name, pa.string()) for name in STRING_FIELDS] + [("deleted", pa.bool_())]
)
REQUIRED = {
    "filename",
    "number",
    "id",
    "active",
    "assembly_eligible",
    "source_sha256",
    "entry_event_key",
    "event_key",
    "elector_name",
    "name_candidate",
    "name_issue",
    "relative_name",
    "relative_candidate",
    "relative_issue",
    "relative_type",
    "house_no",
    "age",
    "sex_candidate",
}


def _prepare(
    inventory: Path, audit: dict[str, Any], output: Path, profile: InventoryProfile
) -> dict[str, Any]:
    parts = {p["filename"]: p for p in audit["parts"]}
    if len(parts) != len(audit["parts"]):
        raise ValueError("Source audit repeats a PDF filename")
    source = pq.ParquetFile(inventory)
    if not REQUIRED.issubset(source.schema_arrow.names):
        raise ValueError("Input is not a reconciled J&K inventory")
    for name in ("active", "assembly_eligible"):
        if source.schema_arrow.field(name).type != pa.bool_():
            raise ValueError(f"{name} must be a Boolean column")
    counts: Counter[str] = Counter()
    per_part: dict[str, Counter[str]] = {name: Counter() for name in parts}
    relationships: Counter[str] = Counter()
    seen: dict[tuple[str, bool, str], set[str | None]] = {}
    entry_keys: set[str] = set()
    with pq.ParquetWriter(output, SCHEMA, compression="zstd") as writer:
        for batch in source.iter_batches(batch_size=10_000):
            prepared = []
            for row in batch.to_pylist():
                name, number = row["filename"], row["number"]
                match = re.fullmatch(profile.filename_pattern, name or "")
                if (
                    not match
                    or not isinstance(number, str)
                    or not number.isascii()
                    or not number.isdecimal()
                ):
                    raise ValueError("Invalid source filename or elector serial")
                part = parts.get(name)
                if part is None or row["source_sha256"] != part["source_sha256"]:
                    raise ValueError("Inventory row does not match its source PDF hash")
                if row["active"] is None or row["assembly_eligible"] is None:
                    raise ValueError(
                        "Inventory contains an unresolved activity or assembly flag"
                    )
                for key in ("event_key", "entry_event_key"):
                    if not isinstance(row[key], str) or not row[key].startswith(
                        name + ":"
                    ):
                        raise ValueError(
                            "Inventory event key does not identify its source PDF"
                        )
                key = (name, row["assembly_eligible"], number)
                identities = seen.setdefault(key, set())
                if identities and (
                    profile.source.record_key_column != "entry_event_key"
                    or not row["id"]
                    or None in identities
                    or "" in identities
                    or row["id"] in identities
                ):
                    raise ValueError(
                        "Inventory repeats an elector serial "
                        "without distinct source IDs"
                    )
                if row["entry_event_key"] in entry_keys:
                    raise ValueError("Inventory repeats an entry event key")
                entry_keys.add(row["entry_event_key"])
                counts["serial_collisions_retained"] += bool(identities)
                identities.add(row["id"])
                per_part[name]["inventory"] += 1
                counts["inventory"] += 1
                if not row["active"]:
                    counts["inactive_excluded"] += 1
                    continue
                per_part[name]["active_total"] += 1
                if not row["assembly_eligible"]:
                    per_part[name]["active_npr"] += 1
                    counts["active_npr_excluded"] += 1
                    continue
                per_part[name]["active_assembly"] += 1
                counts["active_assembly"] += 1
                own = profile.accept_name(row["elector_name"], row["name_issue"])
                relation = profile.relationships.get(row["relative_type"])
                relative = (
                    profile.accept_name(row["relative_name"], row["relative_issue"])
                    if relation
                    else None
                )
                house = profile.accept_house(row["house_no"], None)
                counts["names_withheld"] += own is None
                counts["relative_names_withheld"] += relative is None
                counts["house_numbers_withheld"] += house is None
                relationships[row["relative_type"] or "missing"] += 1
                prepared.append(
                    {
                        "filename": name,
                        "number": number,
                        "id": row["id"],
                        "relationship": relation,
                        "relationship_source": row["relative_type"],
                        "father_or_husband_name": relative,
                        "elector_name": own,
                        "house_no": house,
                        "age": row["age"],
                        "sex": row["sex_candidate"],
                        "ac_name": None,
                        "district": None,
                        "part_no": str(int(match[2])),
                        "year": "2018",
                        "deleted": False,
                        "source_sha256": row["source_sha256"],
                        "entry_event_key": row["entry_event_key"],
                        "event_key": row["event_key"],
                        "elector_name_source": row["name_candidate"],
                        "relative_name_source": row["relative_candidate"],
                        "house_no_source": row["house_no"],
                    }
                )
            writer.write_table(pa.Table.from_pylist(prepared, schema=SCHEMA))
    for name, observed in per_part.items():
        for field in ("inventory", "active_total", "active_npr", "active_assembly"):
            if observed[field] != parts[name][field]:
                raise ValueError(
                    f"Inventory disagrees with the source audit: {name} {field}"
                )
    return {"counts": dict(counts), "relationship_labels": dict(relationships)}


def resolve_inventory(
    inventory: Path,
    source_audit: Path,
    output_dir: Path,
    profile: InventoryProfile,
    *,
    romanize_token: Callable[[str], str | None] | None = None,
    romanization_revision: str | None = None,
) -> dict[str, Any]:
    """Validate a rebuilt J&K inventory and create its restricted surname artifact.

    Args:
        inventory: Reconciled inventory Parquet from instate's original roll parser.
        source_audit: Parser audit containing inventory and per-PDF hashes and counts.
        output_dir: New directory for prepared electors, surnames, schema and audit.
        profile: Source language, evidence and validation contract.
        romanize_token: Optional local mapping applied after native selection.
        romanization_revision: SHA-256 identifying the supplied mapping.

    Returns:
        Source validation, exclusions, corroboration diagnostics and artifact hashes.

    Raises:
        FileExistsError: The destination already exists.
        ValueError: Source hashes, schema, identity or per-part counts fail validation.
    """
    spec = profile.source
    if romanize_token is not None and spec.evidence_script not in {
        "devanagari",
        "arabic",
    }:
        raise ValueError("Postselection romanization requires native evidence")
    if bool(romanize_token) != bool(romanization_revision):
        raise ValueError("Native romanization requires a lookup and its revision")
    if output_dir.exists():
        raise FileExistsError(output_dir)
    audit = json.loads(source_audit.read_text())
    digest = sha256_file(inventory)
    if audit.get("artifacts", {}).get("inventory.parquet") != digest:
        raise ValueError("Inventory SHA-256 does not match the source audit")
    if profile.parser_filename not in audit.get("script_sha256", {}):
        raise ValueError(
            f"Audit does not identify the original {profile.language} parser"
        )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".jk-{profile.language.lower()}-", dir=output_dir.parent
    ) as temporary:
        root = Path(temporary)
        prepared = root / "electors.parquet"
        handoff = _prepare(inventory, audit, prepared, profile)
        result = build_elector_artifact(
            spec,
            prepared,
            root / "surnames.parquet",
            romanize_token=romanize_token,
            romanization_revision=romanization_revision,
        )
        if result.rows != handoff["counts"].get("active_assembly", 0):
            raise ValueError(
                "Surname artifact did not preserve every active assembly row"
            )
        schema = {
            "fields": [
                {"name": f.name, "type": str(f.type), "nullable": f.nullable}
                for f in SCHEMA
            ],
            "contract": f"jk-{profile.language.lower()}-inventory-handoff-v1",
            "description": profile.description,
        }
        (root / "SCHEMA.json").write_text(json.dumps(schema, indent=2) + "\n")
        report = {
            "revision": spec.resolver_revision,
            "source_revision": spec.source_revision,
            "inventory_sha256": digest,
            "versions": {
                name: version(name) for name in ("upnaam", "duckdb", "pyarrow")
            },
            "script_sha256": {
                str(path.relative_to(Path(__file__).parent.parent)): sha256_file(path)
                for path in [
                    Path(__file__),
                    profile.module_path,
                    Path(__file__).with_name("electors.py"),
                    Path(__file__).with_name(
                        "arabic.py"
                        if spec.evidence_script == "arabic"
                        else "devanagari.py"
                    ),
                ]
                + [
                    Path(__file__).parent.parent / name
                    for name in (
                        "corroboration.py",
                        "normalization.py",
                        "relative.py",
                        "selection.py",
                        "schema.py",
                    )
                ]
            },
            "source_audit_sha256": sha256_file(source_audit),
            **handoff,
            "resolver": result.to_json(),
            "artifacts": {
                name: sha256_file(root / name)
                for name in ("electors.parquet", "surnames.parquet", "SCHEMA.json")
            },
            "limitations": profile.limitations,
        }
        if romanize_token is not None:
            import duckdb

            with duckdb.connect() as connection:
                mapped, unmapped = connection.execute(
                    "SELECT count(*) FILTER (WHERE NOT abstained "
                    "AND surname_latin_normalized IS NOT NULL), "
                    "count(*) FILTER (WHERE NOT abstained "
                    "AND surname_latin_normalized IS NULL) FROM read_parquet(?)",
                    [str(root / "surnames.parquet")],
                ).fetchall()[0]
            report["romanization"] = {
                "stage": "after_native_selection",
                "mapping_sha256": romanization_revision,
                "mapped_selections": mapped,
                "unmapped_selections": unmapped,
                "accuracy": "not_measured_by_this_handoff",
            }
        (root / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
        root.rename(output_dir)
    return report


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Romanization map repeats a JSON key")
        result[key] = value
    return result


def load_romanization_map(
    path: Path, tokenize: Callable[[object], tuple[NameToken, ...]]
) -> tuple[dict[str, str], str]:
    """Validate a local native-token map and return its content hash.

    Args:
        path: JSON object mapping native tokens to single ASCII Latin tokens.
        tokenize: The source script's exact native evidence tokenizer.

    Returns:
        Mapping keyed by normalized native tokens and SHA-256 of the input bytes.

    Raises:
        ValueError: Keys repeat or either script fails the token contract.
    """
    data = path.read_bytes()
    source = json.loads(data, object_pairs_hook=_unique_keys)
    if not isinstance(source, dict) or not source:
        raise ValueError("Romanization map must be a nonempty JSON object")
    mapping = {}
    for native, latin in source.items():
        native = unicodedata.normalize("NFC", native)
        tokens = tokenize(native)
        if len(tokens) != 1 or tokens[0].raw != native:
            raise ValueError("Romanization map keys must be eligible native tokens")
        if not isinstance(latin, str) or not re.fullmatch(r"[A-Za-z]{2,}", latin):
            raise ValueError(
                "Romanization map values must be single ASCII letter tokens"
            )
        key = tokens[0].normalized
        if key in mapping:
            raise ValueError("Romanization map repeats a normalized native token")
        mapping[key] = latin
    return mapping, hashlib.sha256(data).hexdigest()
