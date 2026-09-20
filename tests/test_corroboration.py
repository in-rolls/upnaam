"""Corroboration-based surname selection."""

from __future__ import annotations

from collections import Counter

from upnaam.corroboration import (
    household_spellings,
    resolve_household,
    same_spelling,
)


def test_household_shared_token_wins_at_either_end() -> None:
    household = [
        ("Etham Jayamma", "Balakishtaiah"),  # surname first
        ("Etham Ramulu", "Balakishtaiah"),  # surname first
        ("Kavita Etham", "Ramulu Etham"),  # surname last, relation shares it too
    ]
    got = resolve_household(household)
    assert [r.surname for r in got] == ["etham", "etham", "etham"]
    assert [r.evidence for r in got] == [
        "household",
        "household",
        "household_and_relation",
    ]
    assert [r.position for r in got] == ["first", "first", "last"]


def test_relation_evidence_without_household() -> None:
    (got,) = resolve_household([("Kishore Masu", "Ravi Masu")])
    assert got.surname == "masu"
    assert got.evidence == "relation"
    assert got.position == "last"


def test_honorific_surnames_are_not_demoted() -> None:
    # reddy is shared by both members and by the relation; komatireddy only by one
    household = [
        ("Kiran Kumar Reddy Komatireddy", "Chandra Reddy Komatireddy"),
        ("Anil Reddy", "Chandra Reddy"),
    ]
    got = resolve_household(household)
    assert got[1].surname == "reddy"
    assert got[0].surname in {"reddy", "komatireddy"}
    assert got[0].evidence == "household_and_relation"


def test_position_rule_breaks_ties_only() -> None:
    # Maharashtra patronymics: patil and shankar are both shared by all three
    household = [
        ("Patil Shankar Ram", "Patil Ram"),
        ("Patil Sunita Shankar", "Patil Shankar Ram"),
        ("Patil Amit Shankar", "Patil Shankar Ram"),
    ]
    first = resolve_household(household, position="first")
    assert {r.surname for r in first} == {"patil"}
    last = resolve_household(household, position="last")
    assert last[0].surname == "patil"  # ram is not shared; patil is
    assert last[1].surname in {"patil", "shankar"}


def test_uncorroborated_rungs_and_abstention() -> None:
    (alone,) = resolve_household([("Kavita Namala", "Anjaneyulu")], position="last")
    assert alone.evidence == "position"
    assert alone.surname == "namala"
    (single,) = resolve_household([("Purusha", "Ramesh Gupta")], position="last")
    assert single.abstained
    assert single.surname is None
    (none,) = resolve_household([("Kavita Namala", "Anjaneyulu")])
    assert none.abstained
    assert none.abstention_reason == "no-evidence"
    (empty,) = resolve_household([("", "")])
    assert empty.abstention_reason == "no-eligible-token"


def test_particles_are_never_surnames() -> None:
    household = [
        ("Mohammed Abdul Haques", "Ahmad Hussain"),
        ("Mohammed Abdul Zuber", ""),
    ]
    got = resolve_household(household)
    assert all(r.surname not in {"mohammed", "abdul"} for r in got if r.surname)


def test_spelling_slack_by_length() -> None:
    assert same_spelling("gaud", "goud")  # vowel edit at 4 letters
    assert same_spelling("sing", "singh")  # aspiration h
    assert not same_spelling("rani", "ravi")  # consonant edit at 4 letters
    assert not same_spelling("rajesh", "ramesh")
    assert not same_spelling("ram", "rao")  # under 4 letters: exact only
    assert same_spelling("bayikadi", "baikadi")  # 8 letters: any single edit
    assert not same_spelling("thumkunta", "tumukunta")  # 9 letters, two edits
    assert same_spelling("komatiareddy", "komatireddy")  # 12 letters: two edits allowed


def test_household_majority_spelling_is_recorded() -> None:
    canon = household_spellings(
        Counter({"komatireddy": 2, "komatiareddy": 1, "kumar": 3})
    )
    assert canon["komatiareddy"] == "komatireddy"
    assert canon["kumar"] == "kumar"
    household = [
        ("Kiran Komatiareddy", "Chandra Komatireddy"),
        ("Shravan Komatireddy", "Chandra Komatireddy"),
    ]
    got = resolve_household(household)
    assert [r.surname for r in got] == ["komatireddy", "komatireddy"]
    assert got[0].surname_raw == "Komatiareddy"  # the elector's own spelling is kept


def test_house_name_is_evidence_only_when_passed() -> None:
    # Lakshadweep: the house field carries a house name people go by
    members = [("Farhan Kunninamel", "Sailani")]
    (without,) = resolve_household(members)
    assert without.abstained
    (with_house,) = resolve_household(members, houses=["1/5 Kunninamel"])
    assert with_house.surname == "kunninamel"
    assert with_house.evidence == "house"
    assert with_house.position == "last"
    # a co-resident sharing the token outranks the house field
    got = resolve_household(
        [("Farhan Kunninamel", "Sailani"), ("Farsina Kunninamel", "Pookoya")],
        houses=["1/5 Kunninamel", "1/5 Kunninamel"],
    )
    assert [r.evidence for r in got] == ["household", "household"]


def test_strict_spelling_cannot_turn_sabannavara_into_ramannavara():
    from upnaam.corroboration import conservative_same_spelling, resolve_household

    members = [("Shahida Sabannavara", "Unknown"), ("Rama Ramannavara", "Unknown")]
    got = resolve_household(members, spelling_matcher=conservative_same_spelling)
    assert all(r.abstained for r in got)
    assert conservative_same_spelling("gauda", "gouda")


def test_conflicting_household_and_relation_candidates_abstain():
    from upnaam.corroboration import resolve_household

    got = resolve_household(
        [("Lalita Hoogara", "Shivabasappa Hoogara"), ("Lalita Patil", "Rama Patil")],
        reject_evidence_conflicts=True,
    )
    assert all(r.abstention_reason == "conflicting-evidence" for r in got)
