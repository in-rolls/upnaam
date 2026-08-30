"""Build and apply typed surname canonicalization maps."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pandas as pd

from upnaam.schema import CANONICALIZATION_REVISION, CanonicalizationStatus

if TYPE_CHECKING:
    from collections.abc import Mapping


def canonical_map_from_frame(frame: pd.DataFrame) -> dict[str, str]:
    """Validate and load a variant-to-canonical mapping table."""
    required = {"variant", "canonical"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"canonical map is missing columns: {sorted(missing)}")
    variants = cast("pd.Series", frame["variant"])
    canonicals = cast("pd.Series", frame["canonical"])
    if variants.isna().any() or canonicals.isna().any():
        raise ValueError("canonical map tokens must be nonnull")
    valid = variants.map(lambda value: isinstance(value, str) and bool(value))
    valid &= canonicals.map(lambda value: isinstance(value, str) and bool(value))
    if not valid.all():
        raise ValueError("canonical map tokens must be nonempty strings")
    duplicates = cast("pd.Series", variants[variants.duplicated(keep=False)])
    if not duplicates.empty:
        raise ValueError("canonical map variants must be unique")
    mapping = dict(zip(variants.astype(str), canonicals.astype(str), strict=True))
    non_idempotent = {
        variant: canonical
        for variant, canonical in mapping.items()
        if canonical in mapping and mapping[canonical] != canonical
    }
    if non_idempotent:
        raise ValueError("canonical map must be idempotent")
    return mapping


def apply_canonical_map(
    records: pd.DataFrame,
    canonical_map: Mapping[str, str],
    *,
    normalized_column: str = "surname_latin_normalized",
    revision: str = CANONICALIZATION_REVISION,
    provenance: str = "accepted_variant_map",
) -> pd.DataFrame:
    """Attach canonical surnames while retaining normalized input spellings.

    Args:
        records: Surname records containing a normalized comparison column.
        canonical_map: Accepted variant-to-representative mapping.
        normalized_column: Column containing normalized Latin surnames.
        revision: Immutable canonicalization artifact revision.
        provenance: Evidence artifact or method used for mapped variants.

    Returns:
        A copy with canonical surname, status, provenance, and revision.

    Raises:
        ValueError: If the normalized input column is absent.
    """
    if normalized_column not in records.columns:
        raise ValueError(f"records are missing normalized column: {normalized_column}")
    output = records.copy()
    normalized = cast("pd.Series", output[normalized_column]).astype("string")
    canonical = normalized.map(
        lambda value: (
            canonical_map.get(value, value) if isinstance(value, str) else None
        )
    ).astype("string")
    in_map = normalized.isin(list(canonical_map))
    mapped = in_map & canonical.ne(normalized)
    status = pd.Series(
        CanonicalizationStatus.IDENTITY_UNMAPPED.value,
        index=output.index,
        dtype="string",
    )
    status.loc[in_map & ~mapped] = CanonicalizationStatus.CANONICAL_IDENTITY.value
    status.loc[mapped] = CanonicalizationStatus.VARIANT_MAPPED.value
    status.loc[normalized.isna()] = (
        CanonicalizationStatus.NORMALIZATION_UNAVAILABLE.value
    )
    if "abstained" in output.columns:
        abstained = cast("pd.Series", output["abstained"]).fillna(False).astype(bool)
        status.loc[abstained] = CanonicalizationStatus.NOT_APPLICABLE.value
    output["surname_canonical"] = canonical
    output["canonicalization_status"] = status
    output["canonicalization_provenance"] = pd.Series(
        provenance, index=output.index, dtype="string"
    ).where(in_map)
    output["canonicalization_revision"] = revision
    return output
