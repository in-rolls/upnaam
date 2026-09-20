"""Surname selection from corroborating evidence: co-residents and the relation name.

``resolver-v1`` picks a surname by position (first or last eligible token) under a
per-state rule, which fails on rolls that mix name orders within one part: the
Telangana English rolls print "etham jayamma" (surname first) beside "kavita namala"
(surname last).
This module selects the token that other evidence corroborates instead, and keeps the
position rule only as a tie-breaker.

Evidence, strongest first:

1. ``household_and_relation``: a token shared with a co-resident (same part and house
   number) and also carried by the relation name (father, husband, mother).
2. ``household``: a token shared with a co-resident.
3. ``relation``: a token carried by the relation name.
4. ``house``: a token carried by the elector's own house field, where the roll prints a
   house name and people go by it (Lakshadweep: "Farhan Kunninamel" at house
   "Kunninamel"). Only where the adapter passes house fields.
5. ``position``: no corroboration; the state's position rule on a multi-token name.

Tokens absent from the elector's name are never selected here. Relative-name
candidates are produced separately by :mod:`upnaam.relative` after this pass.

Ties inside a rung go to the state's position rule when one exists, otherwise to the
rightmost token. Tokens such as reddy, rao, singh or kumar are surnames people go by and
are never demoted in favour of a rarer token.

Spellings inside one household may differ by a slip. A token counts as shared when it
is within the longer token's edit slack: exact only under four letters (ram / rao); one
edit at four to six letters, and only a vowel change or an aspiration ``h`` (begam /
begum, gaud / goud, sing / singh, never rani / ravi or rajesh / ramesh); one edit of any
kind at seven to nine; two at ten or more. The household's majority spelling is the
recorded surname.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rapidfuzz.distance import Levenshtein

from upnaam.normalization import NameToken, tokenize_name
from upnaam.selection import PREFIX_HONORIFICS

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

CORROBORATION_REVISION = "corroboration-v2"

Evidence = Literal[
    "explicit_surname_field",
    "same_person_external",
    "household_and_relation",
    "household",
    "relation",
    "house",
    "position",
]
RUNGS: dict[int, Evidence] = {
    4: "household_and_relation",
    3: "household",
    2: "relation",
    1: "house",
}
Position = Literal["first", "middle", "last"]

#: Name particles that precede a given name and are never a surname.
NAME_PARTICLES = frozenset(
    {
        "md",
        "mohd",
        "mohmd",
        "mohamad",
        "mohamed",
        "mohammad",
        "mohammed",
        "muhammad",
        "muhammed",
        "mo",
        "sk",
        "sekh",
        "shekh",
        "sheikh",
        "shaikh",
        "shek",
        "she",
        "syed",
        "sayed",
        "sayyed",
        "sayyad",
        "saiyad",
        "saiyed",
        "abdul",
        "bin",
        "binte",
        "bint",
        "ibn",
        "abu",
        "smt",
        "shrimati",
        "shri",
        "sri",
        "mr",
        "mrs",
        "miss",
        "ms",
        "mast",
        "master",
        "kum",
        "km",
        "late",
    }
)
NULL_TOKENS = frozenset(
    {
        "fnu",
        "lnu",
        "lnf",
        "fnf",
        "nfu",
        "nlu",
        "na",
        "nil",
        "null",
        "none",
        "nan",
        "unknown",
        "unknwn",
        "baby",
        "minor",
    }
)
VOWELS = frozenset("aeiouy")
MIN_LETTERS = 3


@dataclass(frozen=True, slots=True)
class CorroboratedSurname:
    """One elector's selection under the corroboration rules."""

    surname: str | None
    surname_raw: str | None
    evidence: Evidence | None
    position: Position | None
    abstention_reason: str | None

    @property
    def abstained(self) -> bool:
        """Return whether no surname was selected."""
        return self.surname is None


def spelling_slack(token: str) -> int:
    """Edits two household spellings of one name may differ by."""
    return 0 if len(token) < 4 else 1 if len(token) < 10 else 2


def _soft_edit(a: str, b: str) -> bool:
    ops = Levenshtein.editops(a, b).as_list()
    if len(ops) != 1:
        return False
    tag, src_pos, dest_pos = ops[0]
    src = a[int(src_pos)] if tag != "insert" else ""
    dst = b[int(dest_pos)] if tag != "delete" else ""
    changed = {c for c in (src, dst) if c}
    return changed <= VOWELS or changed == {"h"}


def same_spelling(a: str, b: str) -> bool:
    """Return whether two normalized tokens are one name under the slack rules."""
    if a == b:
        return True
    longer = max(a, b, key=len)
    slack = spelling_slack(longer)
    if slack == 0 or Levenshtein.distance(a, b, score_cutoff=slack) > slack:
        return False
    return len(longer) >= 7 or _soft_edit(a, b)


def conservative_same_spelling(a: str, b: str) -> bool:
    """Match exact spellings or one vowel/aspiration edit within the length slack."""
    return a == b or (same_spelling(a, b) and _soft_edit(a, b))


def household_spellings(
    spellings: Counter[str],
    *,
    spelling_matcher: Callable[[str, str], bool] = same_spelling,
    trace: list[dict[str, object]] | None = None,
) -> dict[str, str]:
    """Map each spelling seen in a household to the household's majority spelling.

    Greedy: the most frequent spelling anchors a cluster and absorbs every unclustered
    spelling within its slack; ties on frequency go to the shorter, then alphabetical,
    spelling so the mapping is deterministic.
    """
    canon: dict[str, str] = {}
    for tok in sorted(spellings, key=lambda t: (-spellings[t], len(t), t)):
        if tok in canon:
            continue
        canon[tok] = tok
        if spelling_slack(tok) == 0:
            continue
        for other in spellings:
            if other not in canon:
                accepted = spelling_matcher(tok, other)
                if trace is not None:
                    trace.append(
                        {
                            "stage": "surname_variant",
                            "left_value": tok,
                            "right_value": other,
                            "accepted": accepted,
                            "rule_id": spelling_matcher.__name__,
                            "anchor_support": spellings[tok],
                            "variant_support": spellings[other],
                        }
                    )
                if accepted:
                    canon[other] = tok
    return canon


def content_tokens(value: object) -> tuple[NameToken, ...]:
    """Tokens that may be a surname.

    At least three letters, and not a prefix honorific, a name particle or a null token.
    """
    return tuple(
        token
        for token in tokenize_name(value)
        if token.letter_count >= MIN_LETTERS
        and token.normalized not in PREFIX_HONORIFICS
        and token.normalized not in NAME_PARTICLES
        and token.normalized not in NULL_TOKENS
    )


def _where(tokens: Sequence[NameToken], index: int) -> Position:
    if index == len(tokens) - 1:
        return "last"
    return "first" if index == 0 else "middle"


def _by_rule(tokens: Sequence[NameToken], position: str | None) -> int:
    return 0 if position == "first" else len(tokens) - 1


def resolve_household(
    members: Sequence[tuple[object, object]],
    *,
    position: str | None = None,
    houses: Sequence[object] | None = None,
    tokenizer: Callable[[object], tuple[NameToken, ...]] = content_tokens,
    spelling_matcher: Callable[[str, str], bool] = same_spelling,
    reject_evidence_conflicts: bool = False,
    trace: list[dict[str, object]] | None = None,
) -> list[CorroboratedSurname]:
    """Resolve every member of one household.

    Args:
        members: ``(name, relation_name)`` pairs for the electors at one part and house
            number. A household of one still gets relation and position evidence.
        position: The state's position rule (``first`` or ``last``) used to break ties
            and for the uncorroborated rungs; ``None`` for a state without a rule.
        houses: One house field per member, for rolls whose house field carries a house
            name that doubles as the surname; ``None`` disables the ``house`` rung.

        tokenizer: Eligible evidence tokens, optionally aligned to native source spans.
        spelling_matcher: Whether two household spellings may be pooled.
        reject_evidence_conflicts: Abstain when household and relation candidates
            disagree.
        trace: Optional sink for the actual spelling comparisons and token decisions.

    Returns:
        One result per member, in order.
    """
    names = [tokenizer(name) for name, _ in members]
    relations = [tokenizer(relation) for _, relation in members]
    house_tokens = (
        [content_tokens(h) for h in houses] if houses else [() for _ in members]
    )
    spellings: Counter[str] = Counter()
    for toks in names + relations + house_tokens:
        spellings.update({t.normalized for t in toks})
    canon = (
        household_spellings(spellings, spelling_matcher=spelling_matcher, trace=trace)
        if len(spellings) > 1
        else {}
    )

    def key(token: NameToken) -> str:
        return canon.get(token.normalized, token.normalized)

    tally: Counter[str] = Counter()
    for toks in names:
        tally.update({key(t) for t in toks})

    out: list[CorroboratedSurname] = []
    for member_index, (toks, rel, house) in enumerate(
        zip(names, relations, house_tokens, strict=True)
    ):
        rel_keys = {key(t) for t in rel}
        house_keys = {key(t) for t in house}
        household_ok = len(members) >= 2
        if reject_evidence_conflicts:
            own_keys = {key(t) for t in toks}
            shared_keys = {k for k in own_keys if household_ok and tally[k] >= 2}
            related_keys = own_keys & rel_keys
            if shared_keys and related_keys and not shared_keys & related_keys:
                out.append(
                    CorroboratedSurname(None, None, None, None, "conflicting-evidence")
                )
                if trace is not None:
                    trace.append(
                        {
                            "stage": "surname_selection",
                            "member_index": member_index,
                            "rule_id": "abstain",
                            "reason_code": "conflicting-evidence",
                            "selected_index": None,
                        }
                    )
                continue
        scored: list[tuple[tuple[int, int, int], int]] = []
        for i, t in enumerate(toks):
            k = key(t)
            shared = household_ok and tally[k] >= 2
            in_rel = k in rel_keys
            in_house = k in house_keys
            if not (shared or in_rel or in_house):
                continue
            rung = 4 if shared and in_rel else 3 if shared else 2 if in_rel else 1
            tie = -i if position == "first" else i
            scored.append(((rung, tally[k] if shared else 0, tie), i))
        selected_index = None
        if scored:
            (rung, _, _), i = max(scored)
            selected_index = i
            out.append(
                CorroboratedSurname(
                    key(toks[i]), toks[i].raw, RUNGS[rung], _where(toks, i), None
                )
            )
        elif len(toks) >= 2 and position in ("first", "last"):
            i = _by_rule(toks, position)
            selected_index = i
            out.append(
                CorroboratedSurname(
                    key(toks[i]), toks[i].raw, "position", _where(toks, i), None
                )
            )
        elif not toks:
            out.append(CorroboratedSurname(None, None, None, None, "no-eligible-token"))
        else:
            out.append(CorroboratedSurname(None, None, None, None, "no-evidence"))
        if trace is not None:
            trace.append(
                {
                    "stage": "surname_selection",
                    "member_index": member_index,
                    "rule_id": out[-1].evidence or "abstain",
                    "reason_code": out[-1].abstention_reason,
                    "selected_index": selected_index,
                    "candidate_scores": [
                        {
                            "index": i,
                            "rung": score[0],
                            "household_support": score[1],
                            "tie_break": score[2],
                        }
                        for score, i in scored
                    ],
                }
            )
    return out
