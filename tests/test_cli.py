from pathlib import Path

import pandas as pd

from upnaam.cli import main


def test_cli_normalize_select_and_resolve(tmp_path: Path) -> None:
    names = tmp_path / "names.csv"
    normalized = tmp_path / "normalized.parquet"
    selected = tmp_path / "selected.parquet"
    resolved = tmp_path / "resolved.parquet"
    pd.DataFrame(
        {
            "elector_id": ["roll:1", "roll:2"],
            "state": ["bihar", "maharashtra"],
            "name": [" Poorna  Devi ", "Patil Ashwini"],
        }
    ).to_csv(names, index=False)

    main(["normalize", str(names), str(normalized)])
    main(["select", str(normalized), str(selected)])
    main(["resolve", str(names), str(resolved)])

    normalized_frame = pd.read_parquet(normalized)
    selected_frame = pd.read_parquet(selected)
    resolved_frame = pd.read_parquet(resolved)
    assert normalized_frame["name_normalized"].tolist() == [
        "poorna devi",
        "patil ashwini",
    ]
    assert selected_frame["surname_first_normalized"].tolist() == [
        "poorna",
        "patil",
    ]
    assert selected_frame["surname_last_normalized"].tolist() == ["devi", "ashwini"]
    assert resolved_frame["surname_canonical"].tolist() == ["devi", "patil"]


def test_cli_canonicalization_requires_evidence_before_mapping(tmp_path: Path) -> None:
    frequencies = tmp_path / "frequencies.csv"
    candidates = tmp_path / "candidates.csv"
    evidence = tmp_path / "evidence.csv"
    mapping = tmp_path / "mapping.parquet"
    records = tmp_path / "records.parquet"
    canonical = tmp_path / "canonical.parquet"
    pd.DataFrame({"surname_latin_normalized": ["jadhab", "jadhav", "sharma"]}).to_csv(
        frequencies, index=False
    )

    main(
        [
            "canonicalize",
            "candidates",
            str(frequencies),
            str(candidates),
        ]
    )
    candidate_frame = pd.read_csv(candidates)
    assert candidate_frame[["left", "right"]].to_dict(orient="records") == [
        {"left": "jadhab", "right": "jadhav"}
    ]

    candidate_frame.assign(
        support=3,
        source="ration_links",
        evidence_tier="linked_record",
        accepted=True,
        preferred="jadhav",
    ).to_csv(evidence, index=False)
    main(["canonicalize", "build", str(evidence), str(mapping)])
    pd.DataFrame(
        {"surname_latin_normalized": ["jadhab", "jadhav", "sharma"]}
    ).to_parquet(records, index=False)
    main(
        [
            "canonicalize",
            "apply",
            str(records),
            str(canonical),
            str(mapping),
        ]
    )
    assert pd.read_parquet(canonical)["surname_canonical"].tolist() == [
        "jadhav",
        "jadhav",
        "sharma",
    ]


def test_cli_empty_candidate_artifact_keeps_its_schema(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "candidates.parquet"
    pd.DataFrame({"surname_latin_normalized": ["sharma"]}).to_csv(source, index=False)
    main(["canonicalize", "candidates", str(source), str(output)])
    assert list(pd.read_parquet(output).columns) == [
        "left",
        "right",
        "distance",
        "similarity",
        "left_frequency",
        "right_frequency",
    ]
