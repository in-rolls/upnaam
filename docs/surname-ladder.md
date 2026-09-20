# Surname resolution ladder

`upnaam.resolve_name_records` produces three typed tables: `resolutions`,
`candidates`, and `evidence`. Surname selection belongs in Upnaam. Instate consumes
eligible evidence and keeps any coverage adjustment in a separate module.

```python
from pathlib import Path
from upnaam import LadderPolicy, NameRecord, resolve_name_records

records = [
    NameRecord(
        record_id="roll:1",
        source_revision="roll-2017-sha256",
        state="karnataka",
        year="2017",
        name="Asha",
        relative_name="Ravi Shastri",
        relationship="husband",
    )
]
result = resolve_name_records(
    records,
    policy=LadderPolicy("example-relative-policy-v1", relative_position="last"),
)
print(result.resolutions.to_pylist())
result.write(Path("surname-example"))
```

This explicitly enabled relative-position policy returns a `relative_candidate`,
keeps the recorded-surname decision null, and leaves `p_correct` null. No state
has that policy enabled automatically. Matching scores are not accuracy estimates.

## Ladder

| Priority | Rule | Meaning |
| --- | --- | --- |
| 1 | `explicit_surname_field` | Surname explicitly written for the person. |
| 2 | `household_and_relation`, `household`, `relation`, `house` | Own-name token selected with the existing corroboration precedence. House evidence requires a source policy. |
| 3 | `initials_single_token` | Existing narrowly scoped Kannada initials exception. |
| 4 | `position_policy` | Own-name token under an explicit source position policy. |
| 5 | `same_person_external` | Surname on a uniquely linked record of the same person. |
| 6 | `relative_recorded_surname` | Candidate from the independently resolved named relative. |
| 7 | `relative_position_policy` | Candidate from the relative's full name under an explicit position policy. |
| 8 | `abstain` | Insufficient or unsupported evidence. |

Priority is not a claim about accuracy. Conflicting evidence blocks fallback.
An external disagreement preserves the written candidate while accepting neither
value. Differences may represent variants or changes over time; they are exposed
rather than silently resolved.

Relative candidates never feed the recorded-name pass or propagate recursively.
Unknown relationships, one-word relative names and ambiguous relative matches
abstain. Father, mother, husband, wife and spouse relationships stay explicit.
Confirming Ravi Shastri's surname does not establish that Asha uses it.

`LinkedSurname` requires source identity and revision, original text, surname span,
linkage basis and reference kind. `explicit_field` and `adjudicated` references
can produce `external_recovered`; a `position_policy` reference remains an
`external_candidate`. This interface checks link uniqueness; the caller must
establish person links independently. These statuses do not certify link accuracy.

## Three-table contract

| Table | Preserved information |
| --- | --- |
| `resolutions` | One row per source record in input order. Provenance, state/year/household, raw own and relative fields, relationship, recorded and selected candidate IDs, status, rule, reasons, policy revisions and nullable accuracy/calibration fields. |
| `candidates` | Eligible own/relative tokens and supplied explicit/external surnames. Source text and exact spans, origin, native normalization, original and normalized transliteration, comparison representation, canonical spelling, cluster identity/revision, selection status and rule. |
| `evidence` | Attempted household spelling comparisons, including rejections, and selection decisions. Exact compared representations, uncensored scores, thresholds, parameters, edit operations, metric/policy revisions and decision details. |

Offsets are zero-based Python Unicode code-point indices, with exclusive end.
Every source substring must equal the candidate's raw token. IDs are deterministic
hashes; source revisions must identify immutable inputs. Household grouping is
scoped by source revision, state and year. Unknown household IDs must be null.
Process complete households together when batching a larger source.

`comparison_value` records what was matched. Kannada uses the aligned token lookup
while `surname_source_normalized` retains native script. A lookup requires a
revision. The original Latin transcription is retained separately from its
normalization. Clustering never overwrites raw or normalized source variants.

Household spelling anchors are contextual and separately versioned. The existing
national variant clusterer retains its complete-link evidence requirement: A-B
and B-C similarity alone cannot merge A and C. These are different cluster scopes.

`upnaam.matching.compare_strings` supports exact matching, Levenshtein distance and
Jaro-Winkler similarity through `MatchPolicy`. Each has explicit score direction
and threshold. Jaro-Winkler records prefix weight; Levenshtein records edit
operations. Rejected scores are not cutoff-clipped. Household resolution continues
to use its constrained Levenshtein policy; it does not silently switch metrics.

`ResolutionBundle.write` atomically creates a new directory with three Parquet
files and a manifest containing hashes, row counts, policy and span convention.
It refuses to overwrite an existing artifact. Use `resolve_name_records` for
this complete audit; the positional `resolve_electors` and parsed-roll artifact
builder remain narrower interfaces. The parsed-roll builder also exposes separate
relative-candidate fields. Corroboration v2 removes unconditional inheritance from
recorded surnames.

## Validation

Bihar land and Rajasthan ration adapters currently label final tokens from full
names. These are provisional references, not independent surname boundaries.
Bihar's exact-name-and-relative links cannot evaluate naturally omitted surnames
using those links alone.

Evaluate linkage, token selection, transliteration and clustering separately.
Retain disagreements and independently adjudicate a stratified sample. Measure
incremental coverage, precision, abstention and conflict by rung, source, state,
relationship, recorded sex and naming pattern. Separate households and linked
people across development, calibration and test partitions. Hold out surname
variants when measuring generalization to new names. Freeze clustering first.

Recovery evaluation needs links that do not require the proposed surname to
agree. Include naturally missing cases; artificially masked names have a different
missingness mechanism. Landholders and ration members also differ from the
population of electors. Results from Bihar or Rajasthan do not establish Karnataka
accuracy. Some people may have no evidenced family surname.

These are restricted person-level artifacts. Public releases should contain
reviewed aggregates and reproducibility manifests, not the row-level tables.
