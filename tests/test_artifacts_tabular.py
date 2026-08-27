import gzip
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from upnaam.artifacts import (
    load_source_config,
    sha256_file,
    source_fingerprint,
    write_manifest,
)
from upnaam.parquet import combine_parquet_files
from upnaam.tabular import (
    extract_candidate_table,
    load_variant_map,
    normalize_electoral_name_table,
    resolve_recorded_surnames,
)


def _write_name_csv(path: Path) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write("english_name,father_husband_name,n_times\n")
        stream.write("Poorna Devi,Ram Sharma,2\n")
        stream.write("Kamla,Raj Kumar,3\n")


def test_config_hash_and_manifest(tmp_path: Path) -> None:
    config_dir = tmp_path / "project" / "config"
    config_dir.mkdir(parents=True)
    source = tmp_path / "project" / "source.txt"
    source.write_text("names\n", encoding="utf-8")
    config_path = config_dir / "sources.json"
    config_path.write_text('{"section": {"input": "source.txt"}}', encoding="utf-8")
    config = load_source_config(config_path)
    assert config["section"]["input"] == str(source)
    assert sha256_file(source) == source_fingerprint(source)["sha256"]
    directory_fingerprint = source_fingerprint(source.parent)
    assert directory_fingerprint["files"] == 2
    output = tmp_path / "result.txt"
    output.write_text("done\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    write_manifest(
        manifest,
        stage="test",
        inputs=[source],
        outputs=[output],
        row_counts={"output": 1},
        parameters={"rule": "simple"},
    )
    assert json.loads(manifest.read_text())["stage"] == "test"
    with pytest.raises(FileNotFoundError):
        source_fingerprint(tmp_path / "missing")


def test_tabular_baseline_pipeline(tmp_path: Path) -> None:
    source = tmp_path / "names.csv.gz"
    normalized = tmp_path / "normalized.parquet"
    candidates = tmp_path / "candidates.parquet"
    resolved = tmp_path / "resolved.parquet"
    _write_name_csv(source)
    assert normalize_electoral_name_table(source, normalized, state="bihar") == 2
    assert extract_candidate_table(normalized, candidates) == 2
    assert (
        resolve_recorded_surnames(candidates, resolved, variants={"devi": "devī"}) == 2
    )
    frame = pd.read_parquet(resolved)
    assert frame.loc[0, "surname_raw"] == "Devi"
    assert frame.loc[0, "surname"] == "devī"
    assert frame.loc[0, "surname_provenance"] == "written_final_token"
    assert frame.loc[1, "abstention_reason"] == "single-token-name"
    assert pd.isna(frame.loc[1, "surname"])


def test_variant_loaders_and_parquet_combination(tmp_path: Path) -> None:
    first = tmp_path / "first.parquet"
    second = tmp_path / "second.parquet"
    combined = tmp_path / "combined.parquet"
    pd.DataFrame({"variant": ["purna"], "canonical": ["poorna"]}).to_parquet(
        first, index=False
    )
    pd.DataFrame({"variant": ["sarma"], "canonical": ["sharma"]}).to_parquet(
        second, index=False
    )
    assert combine_parquet_files([first, second], combined) == 2
    assert pq.ParquetFile(combined).metadata.num_rows == 2
    assert load_variant_map(first) == {"purna": "poorna"}
    json_path = tmp_path / "variants.json"
    json_path.write_text(
        '[{"variant": "sarma", "canonical": "sharma"}]', encoding="utf-8"
    )
    assert load_variant_map(json_path) == {"sarma": "sharma"}


def test_normalizer_rejects_wrong_schema_and_empty_file(tmp_path: Path) -> None:
    wrong = tmp_path / "wrong.csv.gz"
    with gzip.open(wrong, "wt", encoding="utf-8") as stream:
        stream.write("name\nPoorna Devi\n")
    with pytest.raises(ValueError, match="missing columns"):
        normalize_electoral_name_table(wrong, tmp_path / "wrong.parquet", state="x")
