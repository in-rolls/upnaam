"""Validate and apply anchored surname-reconciliation decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pandas as pd

from upnaam.canonicalization.reconciliation import (
    RECONCILIATION_REVISION,
    ReconciliationStatus,
)
from upnaam.schema import CanonicalizationStatus

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class AppliedDecision:
    """Validated decision needed when applying reconciliation."""

    canonical_label: str | None
    status: ReconciliationStatus
    reason: str
    revision: str


def reconciliation_index_from_frame(
    frame: pd.DataFrame,
) -> dict[tuple[str, str], AppliedDecision]:
    """Validate and index a one-row-per-observation decision table.

    Args:
        frame: Reconciliation decision artifact.

    Returns:
        Decisions keyed by normalized observed form and context.

    Raises:
        ValueError: If the schema, keys, or status-dependent fields are invalid.
    """
    required = {
        "observed_form",
        "context",
        "canonical_label",
        "status",
        "reason",
        "reconciliation_revision",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"decision table is missing columns: {sorted(missing)}")
    keys = frame.loc[:, ["observed_form", "context"]]
    if keys.isna().any().any():
        raise ValueError("decision keys must be nonnull")
    valid_keys = keys.map(lambda value: isinstance(value, str) and bool(value))
    if not valid_keys.all().all():
        raise ValueError("decision keys must be nonempty strings")
    if keys.duplicated().any():
        raise ValueError("decision keys must be unique")

    output: dict[tuple[str, str], AppliedDecision] = {}
    for row in frame.to_dict(orient="records"):
        status = ReconciliationStatus(str(row["status"]))
        canonical = row["canonical_label"]
        canonical_missing = canonical is None or cast("bool", pd.isna(canonical))
        if status is ReconciliationStatus.ACCEPTED:
            if canonical_missing or not isinstance(canonical, str) or not canonical:
                raise ValueError("accepted decisions require a canonical label")
            canonical_label: str | None = canonical
        else:
            if not canonical_missing:
                raise ValueError("non-accepted decisions cannot name a canonical label")
            canonical_label = None
        reason = row["reason"]
        revision = row["reconciliation_revision"]
        if not isinstance(reason, str) or not reason:
            raise ValueError("decision reasons must be nonempty strings")
        if not isinstance(revision, str) or not revision:
            raise ValueError("decision revisions must be nonempty strings")
        output[(str(row["observed_form"]), str(row["context"]))] = AppliedDecision(
            canonical_label=canonical_label,
            status=status,
            reason=reason,
            revision=revision,
        )
    return output


def apply_reconciliation(
    records: pd.DataFrame,
    decisions: Mapping[tuple[str, str], AppliedDecision],
    *,
    normalized_column: str = "surname_latin_normalized",
    context: str = "global",
    context_column: str | None = None,
    provenance: str = "anchored_reconciliation",
) -> pd.DataFrame:
    """Apply anchored decisions while preserving unresolved input spellings.

    Args:
        records: Surname records containing a normalized comparison column.
        decisions: Validated decisions keyed by observed form and context.
        normalized_column: Column containing normalized surnames.
        context: Fixed context used when ``context_column`` is omitted.
        context_column: Optional per-row context column.
        provenance: Named evidence artifact or reconciliation method.

    Returns:
        A copy with canonical surname, status, reason, provenance, and revision.
        Ambiguous rows receive no canonical surname. Unresolved and absent
        decisions retain the normalized spelling as an explicitly unmapped
        identity value.

    Raises:
        ValueError: If required columns or contexts are absent or invalid.
    """
    if normalized_column not in records.columns:
        raise ValueError(f"records are missing normalized column: {normalized_column}")
    if context_column is not None and context_column not in records.columns:
        raise ValueError(f"records are missing context column: {context_column}")
    if context_column is None and not context:
        raise ValueError("fixed reconciliation context must be nonempty")

    output = records.copy()
    normalized = cast("pd.Series", output[normalized_column]).astype("string")
    contexts = (
        cast("pd.Series", output[context_column]).astype("string")
        if context_column is not None
        else pd.Series(context, index=output.index, dtype="string")
    )
    canonical = normalized.copy()
    status = pd.Series(
        CanonicalizationStatus.IDENTITY_UNMAPPED.value,
        index=output.index,
        dtype="string",
    )
    reason = pd.Series("no_reconciliation_decision", index=output.index, dtype="string")
    applied_provenance = pd.Series(pd.NA, index=output.index, dtype="string")
    revisions = pd.Series(RECONCILIATION_REVISION, index=output.index, dtype="string")

    for index, observed, row_context in zip(
        output.index, normalized, contexts, strict=True
    ):
        if not isinstance(observed, str):
            canonical.loc[index] = None
            status.loc[index] = CanonicalizationStatus.NORMALIZATION_UNAVAILABLE.value
            reason.loc[index] = "normalization_unavailable"
            continue
        if not isinstance(row_context, str) or not row_context:
            raise ValueError("reconciliation contexts must be nonempty strings")
        decision = decisions.get((observed, row_context))
        if decision is None:
            continue
        revisions.loc[index] = decision.revision
        if decision.status is ReconciliationStatus.ACCEPTED:
            canonical.loc[index] = decision.canonical_label
            status.loc[index] = (
                CanonicalizationStatus.CANONICAL_IDENTITY.value
                if decision.canonical_label == observed
                else CanonicalizationStatus.VARIANT_MAPPED.value
            )
            reason.loc[index] = decision.reason
            applied_provenance.loc[index] = provenance
        elif decision.status is ReconciliationStatus.AMBIGUOUS:
            canonical.loc[index] = None
            status.loc[index] = CanonicalizationStatus.AMBIGUOUS.value
            reason.loc[index] = decision.reason
            applied_provenance.loc[index] = provenance
        else:
            reason.loc[index] = decision.reason

    if "abstained" in output.columns:
        abstained = cast("pd.Series", output["abstained"]).fillna(False).astype(bool)
        canonical.loc[abstained] = None
        status.loc[abstained] = CanonicalizationStatus.NOT_APPLICABLE.value
        reason.loc[abstained] = "surname_not_selected"
        applied_provenance.loc[abstained] = pd.NA

    output["surname_canonical"] = canonical
    output["canonicalization_status"] = status
    output["canonicalization_reason"] = reason
    output["canonicalization_provenance"] = applied_provenance
    output["canonicalization_revision"] = revisions
    return output
