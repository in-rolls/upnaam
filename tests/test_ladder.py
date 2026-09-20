"""The evidence ladder preserves source text, provenance and unresolved uncertainty."""

import hashlib
import json
from dataclasses import replace

import pyarrow.parquet as pq
import pytest

from upnaam import LadderPolicy, LinkedSurname, NameRecord, resolve_name_records
from upnaam.matching import MatchPolicy, compare_strings

POLICY = LadderPolicy("fixture-v1")


def person(record_id="1", name="Asha", **kwargs):
    return NameRecord(record_id, "roll-v1", "karnataka", "2017", name, **kwargs)


def rows(bundle):
    return bundle.resolutions.to_pylist()


def chosen(bundle, row=0):
    key = rows(bundle)[row]["selected_candidate_id"]
    return next(
        (c for c in bundle.candidates.to_pylist() if c["candidate_id"] == key), None
    )


def reference(record_id="1", raw="Asha Shastri", kind="explicit_field", **kwargs):
    return LinkedSurname(
        record_id,
        "ration:1",
        "ration-v1",
        raw,
        raw.index("Shastri"),
        len(raw),
        "independent-person-link",
        kind,
        **kwargs,
    )


def test_relative_candidate_preserves_own_abstention_and_source_span():
    bundle = resolve_name_records(
        [person(relative_name="Ravi Shastri", relationship="husband")],
        policy=replace(POLICY, relative_position="last"),
    )
    row = rows(bundle)[0]
    candidate = chosen(bundle)
    assert row["recorded_candidate_id"] is None
    assert row["resolution_status"] == "relative_candidate"
    assert row["rule_id"] == "relative_position_policy"
    assert row["p_correct"] is None
    assert row["reason_codes"] == ["surname_transfer_unvalidated"]
    assert candidate["origin"] == "relative"
    assert candidate["surname_raw"] == "Shastri"
    assert (
        candidate["source_value"][candidate["token_start"] : candidate["token_end"]]
        == "Shastri"
    )
    assert candidate["source_field"] == "relative_name"


def test_unknown_households_never_supply_corroboration():
    bundle = resolve_name_records(
        [person("1", "Ravi Shastri"), person("2", "Mohan Shastri")], policy=POLICY
    )
    assert all(row["resolution_status"] == "abstained" for row in rows(bundle))


def test_household_identity_is_scoped_to_source_state_and_year():
    first = person("1", "Ravi Shastri", household_id="1")
    second = replace(first, record_id="2", name="Mohan Shastri", year="2018")
    bundle = resolve_name_records([first, second], policy=POLICY)
    assert all(row["resolution_status"] == "abstained" for row in rows(bundle))


def test_corroboration_beats_position_and_preserves_rejected_tokens():
    bundle = resolve_name_records(
        [person(name="Shastri Ravi", relative_name="Shastri Mohan")],
        policy=replace(POLICY, position="last"),
    )
    assert rows(bundle)[0]["rule_id"] == "relation"
    assert chosen(bundle)["surname_raw"] == "Shastri"
    alternatives = bundle.candidates.to_pylist()
    assert any(
        c["surname_raw"] == "Ravi" and c["candidate_status"] == "retained_alternative"
        for c in alternatives
    )
    decisions = [
        e for e in bundle.evidence.to_pylist() if e["stage"] == "surname_selection"
    ]
    assert json.loads(decisions[0]["details"])["selected_index"] == 0


def test_conflict_is_a_gate_not_a_fallback():
    people = [
        person(
            "1",
            "Ravi Gowda",
            relative_name="Ravi Sharma",
            relationship="father",
            household_id="1",
        ),
        person("2", "Mohan Gowda", household_id="1"),
    ]
    bundle = resolve_name_records(
        people, policy=replace(POLICY, position="last", relative_position="last")
    )
    assert rows(bundle)[0]["resolution_status"] == "conflict"
    assert chosen(bundle) is None


def test_explicit_field_precedes_fallback_and_helps_resolve_relative():
    people = [
        person(
            "1",
            "Asha",
            relative_name="Ravi Shastri",
            relationship="husband",
            household_id="1",
        ),
        person("2", "Ravi Shastri", explicit_surname="Shastri", household_id="1"),
    ]
    bundle = resolve_name_records(people, policy=POLICY)
    assert rows(bundle)[1]["rule_id"] == "explicit_surname_field"
    assert rows(bundle)[0]["rule_id"] == "relative_recorded_surname"
    assert chosen(bundle)["surname_raw"] == "Shastri"


def test_conflicting_explicit_field_stays_a_conflict():
    bundle = resolve_name_records(
        [
            person(
                name="Asha Shastri",
                relative_name="Ravi Shastri",
                explicit_surname="Patil",
            )
        ],
        policy=POLICY,
    )
    assert rows(bundle)[0]["resolution_status"] == "conflict"
    assert {c["surname_raw"] for c in bundle.candidates.to_pylist()} >= {
        "Patil",
        "Shastri",
    }


def test_validated_same_person_recovery_and_provisional_reference_differ():
    for kind, status in [
        ("explicit_field", "external_recovered"),
        ("adjudicated", "external_recovered"),
        ("position_policy", "external_candidate"),
    ]:
        bundle = resolve_name_records(
            [person()], policy=POLICY, linked_surnames=[reference(kind=kind)]
        )
        assert rows(bundle)[0]["resolution_status"] == status
        assert chosen(bundle)["origin"] == "same_person_external"
        assert chosen(bundle)["source_record_id"] == "ration:1"
        assert rows(bundle)[0]["p_correct"] is None


def test_external_conflict_preserves_written_candidate_without_accepting_either():
    bundle = resolve_name_records(
        [person(name="Asha Patil", relative_name="Ravi Patil")],
        policy=POLICY,
        linked_surnames=[reference()],
    )
    assert rows(bundle)[0]["resolution_status"] == "conflict"
    assert rows(bundle)[0]["recorded_candidate_id"]
    assert rows(bundle)[0]["selected_candidate_id"] is None


def test_external_reference_can_supply_relative_evidence_without_recursive_inference():
    people = [
        person(
            "1", relative_name="Ravi Shastri", relationship="husband", household_id="1"
        ),
        person("2", "Ravi Shastri", household_id="1"),
    ]
    bundle = resolve_name_records(
        people, policy=POLICY, linked_surnames=[reference("2", "Ravi Shastri")]
    )
    assert rows(bundle)[0]["rule_id"] == "relative_recorded_surname"
    assert rows(bundle)[1]["resolution_status"] == "external_recovered"
    provisional = resolve_name_records(
        people,
        policy=POLICY,
        linked_surnames=[reference("2", "Ravi Shastri", "position_policy")],
    )
    assert rows(provisional)[0]["resolution_status"] == "abstained"


def test_initials_exception_preserves_native_span_and_transliteration():
    lookup = {"ಸುಬ್ಬರಾವ್": "Subbarao"}
    bundle = resolve_name_records(
        [person(name="ಟಿ. ಸುಬ್ಬರಾವ್")],
        policy=replace(POLICY, tokenization="kannada"),
        romanize_token=lookup.get,
        romanization_revision="lookup-sha256",
    )
    candidate = chosen(bundle)
    assert rows(bundle)[0]["rule_id"] == "initials_single_token"
    assert candidate["surname_raw"] == "ಸುಬ್ಬರಾವ್"
    assert candidate["surname_source_normalized"] == "ಸುಬ್ಬರಾವ್"
    assert candidate["surname_latin_raw"] == "Subbarao"
    assert candidate["surname_latin_normalized"] == "subbarao"
    assert candidate["transliteration_revision"] == "lookup-sha256"
    assert (
        candidate["source_value"][candidate["token_start"] : candidate["token_end"]]
        == "ಸುಬ್ಬರಾವ್"
    )


def test_spelling_decisions_keep_variants_scores_and_rejected_edges():
    people = [
        person("1", "Asha Komatiareddy", household_id="1"),
        person(
            "2", "Ravi Komatireddy", household_id="1", relative_name="Mohan Komatireddy"
        ),
    ]
    bundle = resolve_name_records(people, policy=POLICY)
    candidate = chosen(bundle)
    assert candidate["surname_raw"] == "Komatiareddy"
    assert candidate["surname_latin_normalized"] == "komatiareddy"
    assert candidate["surname_canonical"] == "komatireddy"
    assert candidate["canonicalization_status"] == "variant_mapped"
    events = [e for e in bundle.evidence.to_pylist() if e["stage"] == "token_match"]
    assert any(e["accepted"] for e in events)
    assert any(not e["accepted"] for e in events)
    assert all(e["metric"] == "levenshtein_distance" for e in events)
    assert all(e["edit_operations"] is not None for e in events)
    assert all(e["metric_revision"].startswith("rapidfuzz:") for e in events)


def test_tied_duplicate_tokens_keep_the_selected_occurrence():
    bundle = resolve_name_records(
        [person(name="Shastri Ravi Shastri", relative_name="Mohan Shastri")],
        policy=POLICY,
    )
    assert chosen(bundle)["token_start"] == len("Shastri Ravi ")


def test_empty_bundle_has_stable_typed_schemas_and_writer_round_trips(tmp_path):
    bundle = resolve_name_records([], policy=POLICY)
    output = tmp_path / "artifact"
    bundle.write(output)
    manifest = json.loads((output / "manifest.json").read_text())
    for filename, metadata in manifest["artifacts"].items():
        assert pq.read_table(output / filename).num_rows == 0
        assert (
            hashlib.sha256((output / filename).read_bytes()).hexdigest()
            == metadata["sha256"]
        )
    with pytest.raises(FileExistsError):
        bundle.write(output)


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": ""},
        {"position": "middle"},
        {"relative_position": "guess"},
        {"tokenization": "guess"},
        {"tokenization": "kannada", "position": "last"},
    ],
)
def test_invalid_policy(changes):
    with pytest.raises(ValueError, match=r"policy|policies|Kannada"):
        replace(POLICY, **changes)


def test_invalid_identities_links_and_romanization():
    with pytest.raises(ValueError, match="unique"):
        resolve_name_records([person(), person()], policy=POLICY)
    with pytest.raises(ValueError, match="one-to-one"):
        resolve_name_records(
            [person()], policy=POLICY, linked_surnames=[reference("missing")]
        )
    with pytest.raises(ValueError, match="one-to-one"):
        resolve_name_records(
            [person()], policy=POLICY, linked_surnames=[reference(), reference()]
        )
    with pytest.raises(ValueError, match="lookup"):
        resolve_name_records([person()], policy=replace(POLICY, tokenization="kannada"))
    with pytest.raises(ValueError, match="together"):
        resolve_name_records([person()], policy=POLICY, romanization_revision="missing")
    with pytest.raises(ValueError, match="span"):
        replace(reference(), token_end=999)
    with pytest.raises(ValueError, match="reference_kind"):
        replace(reference(), reference_kind="gold-because-official")


@pytest.mark.parametrize(
    ("metric", "threshold"),
    [("exact", 1), ("levenshtein_distance", 1), ("jaro_winkler_similarity", 0.9)],
)
def test_matching_evidence_records_actual_metric(metric, threshold):
    comparison = compare_strings(
        "shastri", "shastry", MatchPolicy(metric, threshold, "test")
    )
    assert comparison["metric"] == metric
    assert comparison["threshold"] == threshold
    assert comparison["left_value"] == "shastri"
    assert "p_correct" not in comparison
    if metric == "jaro_winkler_similarity":
        assert json.loads(comparison["parameters"])["prefix_weight"] == 0.1
        assert comparison["edit_operations"] is None


def test_rejected_distances_are_not_clipped_at_threshold():
    comparison = compare_strings(
        "patil", "shastri", MatchPolicy("levenshtein_distance", 1, "test")
    )
    assert not comparison["accepted"]
    assert comparison["metric_value"] > 2


@pytest.mark.parametrize(
    ("metric", "threshold"),
    [
        ("exact", 0),
        ("levenshtein_distance", -1),
        ("levenshtein_distance", 1.5),
        ("jaro_winkler_similarity", 2),
        ("exact", float("nan")),
    ],
)
def test_invalid_metric_thresholds(metric, threshold):
    with pytest.raises(ValueError, match="threshold"):
        MatchPolicy(metric, threshold, "test")


def test_unhoused_record_id_cannot_collide_with_a_household_scope():
    people = [
        person("same", "Asha Shastri"),
        person("other", "Ravi Shastri", household_id="same"),
    ]
    bundle = resolve_name_records(people, policy=replace(POLICY, position="last"))
    assert chosen(bundle, 0)["scope_id"] != chosen(bundle, 1)["scope_id"]
    assert chosen(bundle, 0)["cluster_id"] != chosen(bundle, 1)["cluster_id"]


def test_invalid_explicit_surname_blocks_relative_fallback_and_preserves_source():
    bundle = resolve_name_records(
        [
            person(
                explicit_surname="123",
                relative_name="Ravi Shastri",
                relationship="husband",
            )
        ],
        policy=replace(POLICY, relative_position="last"),
    )
    assert rows(bundle)[0]["explicit_surname_raw"] == "123"
    assert rows(bundle)[0]["resolution_status"] == "abstained"
    assert rows(bundle)[0]["reason_codes"] == ["invalid-explicit-surname"]


@pytest.mark.parametrize("reference_source", ["explicit", "external"])
def test_kannada_relative_uses_independently_recorded_native_surname(reference_source):
    lookup = {"ಆಶಾ": "Asha", "ರವಿ": "Ravi", "ಶಾಸ್ತ್ರಿ": "Shastri"}
    people = [
        person(
            "1",
            "ಆಶಾ",
            relative_name="ರವಿ ಶಾಸ್ತ್ರಿ",
            relationship="husband",
            household_id="1",
        ),
        person(
            "2",
            "ರವಿ ಶಾಸ್ತ್ರಿ",
            household_id="1",
            explicit_surname="ಶಾಸ್ತ್ರಿ" if reference_source == "explicit" else None,
        ),
    ]
    external = (
        []
        if reference_source == "explicit"
        else [
            LinkedSurname(
                "2",
                "ration:2",
                "ration-v1",
                "ರವಿ ಶಾಸ್ತ್ರಿ",
                len("ರವಿ "),
                len("ರವಿ ಶಾಸ್ತ್ರಿ"),
                "independent-link",
                "adjudicated",
            )
        ]
    )
    bundle = resolve_name_records(
        people,
        policy=replace(POLICY, tokenization="kannada"),
        linked_surnames=external,
        romanize_token=lookup.get,
        romanization_revision="lookup-v1",
    )
    assert rows(bundle)[0]["rule_id"] == "relative_recorded_surname"
    assert chosen(bundle)["surname_raw"] == "ಶಾಸ್ತ್ರಿ"
    assert chosen(bundle)["surname_latin_raw"] == "Shastri"
