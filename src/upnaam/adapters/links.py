"""Adapters for already-accepted land and ration person links."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

LINK_COLUMNS = (
    "source",
    "link_tier",
    "link_id",
    "roll_id",
    "external_id",
    "roll_name_raw",
    "external_name_raw",
    "roll_relative_raw",
    "external_relative_raw",
    "relation_type",
    "sex",
    "name_exact_upstream",
    "edit_learning_eligible",
    "omission_eligible",
)

_BIHAR_ZERO_WIDTH = str.maketrans("", "", "\u200c\u200d")
_BIHAR_HONORIFIC = re.compile(r"(स्व०|स्व\.|स्व0|श्री|श्रीमती|मो०|मो\.|डा०|डॉ|कुमारी)")
_BRACKETS = re.compile(r"\[.*?\]")
_WHITESPACE = re.compile(r"\s+")


def _bihar_upstream_normalize(value: object) -> str:
    """Reproduce only the land pilot's linkage-time comparison form."""
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFC", value).translate(_BIHAR_ZERO_WIDTH)
    normalized = _BRACKETS.sub("", normalized)
    return _WHITESPACE.sub(" ", _BIHAR_HONORIFIC.sub("", normalized)).strip()


def _write_link_frames(frames: Iterable[pd.DataFrame], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    rows = 0
    try:
        for frame in frames:
            table = pa.Table.from_pandas(
                frame.loc[:, LINK_COLUMNS], preserve_index=False
            )
            if writer is None:
                writer = pq.ParquetWriter(output, table.schema, compression="zstd")
            writer.write_table(table)
            rows += len(frame)
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        raise ValueError("no accepted source links were found")
    return rows


def build_bihar_land_links(
    accepted_links: Path, roll_records: Path, output: Path
) -> int:
    """Materialize the exact-name Shekhpura land validation links.

    Args:
        accepted_links: Existing unique land-to-roll link artifact.
        roll_records: Roll records providing untouched elector names.
        output: Unified link artifact.

    Returns:
        Number of accepted links.

    Raises:
        ValueError: If accepted keys are not one-to-one after exact upstream
            comparison fields recover the raw roll row.
    """
    links = pd.read_parquet(
        accepted_links,
        columns=[
            "account_no",
            "name",
            "fatherraw",
            "nm",
            "rname",
            "vid",
            "relationship",
            "sex_obs",
        ],
    )
    roll = pd.read_parquet(
        roll_records,
        columns=["id", "elector_name", "father_or_husband_name"],
    )
    if links["account_no"].duplicated().any() or links["vid"].duplicated().any():
        raise ValueError(
            "Bihar accepted links violate the documented one-to-one contract"
        )
    roll["nm"] = roll["elector_name"].map(_bihar_upstream_normalize)
    roll["rname"] = roll["father_or_husband_name"].map(_bihar_upstream_normalize)
    merged = links.merge(
        roll,
        left_on=["vid", "nm", "rname"],
        right_on=["id", "nm", "rname"],
        validate="one_to_many",
    )
    merged = merged.drop_duplicates(
        ["account_no", "elector_name", "father_or_husband_name"]
    )
    if len(merged) != len(links) or merged["account_no"].duplicated().any():
        raise ValueError(
            "Bihar accepted links do not recover one unique raw roll name pair"
        )
    result = pd.DataFrame(
        {
            "source": "bihar_land",
            "link_tier": "exact_name_and_relative",
            "link_id": "bihar_land:" + merged["account_no"].astype(str),
            "roll_id": merged["vid"].astype(str),
            "external_id": merged["account_no"].astype(str),
            "roll_name_raw": merged["elector_name"],
            "external_name_raw": merged["name"],
            "roll_relative_raw": merged["father_or_husband_name"],
            "external_relative_raw": merged["fatherraw"],
            "relation_type": merged["relationship"],
            "sex": merged["sex_obs"],
            "name_exact_upstream": True,
            "edit_learning_eligible": False,
            "omission_eligible": False,
        }
    )
    return _write_link_frames([result], output)


def _rajasthan_bucket_frame(
    links_path: Path,
    roll_path: Path,
    ration_path: Path,
    accepted_tiers: frozenset[str],
    age_offset: float,
) -> pd.DataFrame:
    links = pd.read_parquet(links_path)
    links = links.loc[links["tier"].isin(sorted(accepted_tiers))].copy()
    if links.empty:
        return pd.DataFrame(columns=cast("Any", LINK_COLUMNS))
    if (
        links["elector_uid"].duplicated().any()
        or links.duplicated(["card_no", "member_no"]).any()
    ):
        raise ValueError(
            f"accepted Rajasthan person links are not one-to-one: {links_path}"
        )
    roll = pd.read_parquet(
        roll_path,
        columns=[
            "elector_uid",
            "hh_id",
            "name_dev",
            "rel_name_dev",
            "relation_type",
            "sex_std",
            "age_2018",
            "name_skel",
            "rel_skel",
        ],
    )
    ration = pd.read_parquet(
        ration_path,
        columns=[
            "card_no",
            "member_no",
            "name_dev",
            "member_father_dev",
            "age_2021",
            "name_skel",
            "father_skel",
        ],
    ).drop_duplicates()
    if ration.duplicated(["card_no", "member_no"]).any():
        raise ValueError(
            f"Rajasthan ration member keys have conflicting records: {ration_path}"
        )
    roll = roll.rename(
        columns={
            "name_dev": "roll_name_raw",
            "rel_name_dev": "roll_relative_raw",
            "sex_std": "roll_sex",
            "name_skel": "roll_name_skel",
        }
    )
    ration = ration.rename(
        columns={
            "name_dev": "external_name_raw",
            "member_father_dev": "external_relative_raw",
            "name_skel": "external_name_skel",
        }
    )
    merged = links.merge(
        ration, on=["card_no", "member_no"], validate="one_to_one"
    ).merge(
        roll,
        on=["elector_uid", "hh_id"],
        validate="one_to_many",
        suffixes=("", "_roll"),
    )
    sex_equal = (merged["sex_std"] == merged["roll_sex"]) | (
        merged["sex_std"].isna() & merged["roll_sex"].isna()
    )
    father_equal = (merged["father_skel"] == merged["rel_skel"]).astype(object)
    father_equal.loc[merged["father_skel"].isna() | merged["rel_skel"].isna()] = None
    father_flag_equal = (father_equal == merged["father_skel_eq"]) | (
        father_equal.isna() & merged["father_skel_eq"].isna()
    )
    calculated_age_residual = (
        merged["age_2021"] - merged["age_2018"] - age_offset
    ).abs()
    age_equal = ((calculated_age_residual - merged["age_resid"]).abs() < 1e-8) | (
        calculated_age_residual.isna() & merged["age_resid"].isna()
    )
    merged = merged.loc[
        (merged["external_name_skel"] == merged["roll_name_skel"])
        & (
            (merged["external_name_raw"] == merged["roll_name_raw"])
            == merged["name_exact"]
        )
        & father_flag_equal
        & sex_equal
        & age_equal
    ].copy()
    merged = merged.drop_duplicates(
        [
            "card_no",
            "member_no",
            "roll_name_raw",
            "roll_relative_raw",
            "relation_type",
            "roll_sex",
            "age_2018",
        ]
    )
    if len(merged) != len(links) or merged.duplicated(["card_no", "member_no"]).any():
        raise ValueError(
            f"upstream Rajasthan fields do not recover one roll row: {links_path}"
        )
    return pd.DataFrame(
        {
            "source": "rajasthan_ration",
            "link_tier": merged["tier"],
            "link_id": (
                "rajasthan_ration:"
                + merged["card_no"].astype(str)
                + ":"
                + merged["member_no"].astype(str)
            ),
            "roll_id": merged["elector_uid"],
            "external_id": merged["card_no"].astype(str)
            + ":"
            + merged["member_no"].astype(str),
            "roll_name_raw": merged["roll_name_raw"],
            "external_name_raw": merged["external_name_raw"],
            "roll_relative_raw": merged["roll_relative_raw"],
            "external_relative_raw": merged["external_relative_raw"],
            "relation_type": merged["relation_type"],
            "sex": merged["roll_sex"],
            "name_exact_upstream": merged["name_exact"],
            "edit_learning_eligible": (merged["tier"] == "T2") & ~merged["name_exact"],
            "omission_eligible": False,
        }
    )


def build_rajasthan_ration_links(
    person_links: Path,
    roll_households: Path,
    ration_households: Path,
    age_offset_audit: Path,
    output: Path,
    *,
    accepted_tiers: tuple[str, ...] = ("T1", "T2"),
) -> int:
    """Reuse only accepted `milaan_raj` T1/T2 person links.

    Args:
        person_links: Directory containing `bucket_XX.parquet` link files.
        roll_households: Partitioned roll household directory.
        ration_households: Partitioned ration household directory.
        age_offset_audit: Frozen upstream age-offset audit CSV.
        output: Unified link artifact.
        accepted_tiers: Exact upstream tiers to retain.

    Returns:
        Number of accepted links written.

    Raises:
        ValueError: If tiers, upstream audit data, or recovered link keys
            violate their declared contracts.
    """
    tiers = frozenset(accepted_tiers)
    if not tiers or not tiers.issubset({"T1", "T2"}):
        raise ValueError(
            "Rajasthan accepted tiers must be a nonempty subset of T1 and T2"
        )
    age_audit = pd.read_csv(age_offset_audit)
    if len(age_audit) != 1 or "offset_median" not in age_audit:
        raise ValueError("Rajasthan age-offset audit has an unexpected schema")
    age_offset = float(str(age_audit.loc[0, "offset_median"]))

    def bucket_frames() -> Iterable[pd.DataFrame]:
        for links_path in sorted(person_links.glob("bucket_*.parquet")):
            bucket = int(links_path.stem.removeprefix("bucket_"))
            roll_path = roll_households / f"bucket={bucket}" / "data_0.parquet"
            ration_path = ration_households / f"bucket={bucket}" / "data_0.parquet"
            if not roll_path.exists() or not ration_path.exists():
                raise FileNotFoundError(f"missing Rajasthan household bucket {bucket}")
            frame = _rajasthan_bucket_frame(
                links_path, roll_path, ration_path, tiers, age_offset
            )
            if not frame.empty:
                yield frame

    return _write_link_frames(bucket_frames(), output)
