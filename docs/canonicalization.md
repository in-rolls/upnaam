# Canonicalization

Upnaam canonicalizes a selected and normalized surname token. It does not
decide which token is the surname in this stage, and it does not infer whether
the selected token is a hereditary family name.

## Candidate proposals

`reconcile propose` turns a frequency table into a compact set of spelling
pairs worth examining. The default gates retain forms observed at least 10
times and pairs with Levenshtein distance at most 1 and normalized similarity
at least 0.80:

```console
upnaam reconcile propose surname_counts.parquet candidates.parquet \
  --audit candidates.json --manifest candidates.manifest.json
```

Every output row is marked `edit_distance_gate` and records both form
frequencies and the proposal-rule revision. The output contains no canonical
label, mapping, or cluster identifier. Frequency filters noise and describes
the pair; it does not make the more frequent form canonical. A later evidence
stage must either direct a form to a named anchor or leave it unresolved.

On the Bihar ration-card written-final-token table, the defaults retain 28,854
of 310,949 normalized forms and propose 54,181 pairs. These are deliberately
not automatic merges. For example, `कुमार` and `कुमारी` are one edit apart but
are substantively different tokens, while `देवी` and `देवी.` are a plausible
punctuation variant. String distance alone cannot distinguish those cases.
Only 21,590 retained forms have any proposed neighbor, and 17,107 of those have
more than one; `कुमारी` alone has 222. Upnaam therefore preserves the pairwise
proposal graph and does not turn its connected components into clusters.

## Why this is not clustering

A global cluster is a partition: every spelling belongs to exactly one group,
and membership becomes transitive. That is too strong for this task. If `A`
resembles `B` and `B` resembles `C`, neither string distance nor two pairwise
links establish that all three are the same surname. A common observed form may
also genuinely point to more than one external spelling.

Upnaam instead performs directed reconciliation:

```text
observed form + context
  -> zero or more named anchor candidates
  -> eligibility gates
  -> accepted, ambiguous, or unresolved
```

An anchor has a stable `canonical_id` and a display `canonical_label`. Many
observed forms may resolve to the same anchor. One observed form may have many
candidate anchors, but Upnaam accepts one only when it is the sole eligible
candidate.

## Evidence contract

Each input row to `reconcile rank` contains:

| Field | Meaning |
| --- | --- |
| `observed_form` | Deterministically normalized source spelling |
| `context` | Declared state, source, script, and positional rule |
| `canonical_id` | Stable identity of the proposed anchor |
| `canonical_label` | Display spelling associated with that anchor |
| `support` | Number of source observations represented by the row |
| `similarity` | Normalized string similarity in `[0, 1]` |
| `source` | Named evidence source |
| `evidence_tier` | Evidence design, such as `linked_record` |

The rank stage aggregates repeated observed-to-anchor evidence, computes a
support-weighted similarity, and records all candidates. `support_share` is a
descriptive share of observed evidence, not a probability. Candidate rank is
deterministic and is not itself an acceptance rule.

The current pilot gates are:

- aggregate support of at least 2; and
- support-weighted normalized Levenshtein similarity of at least 0.75.

Both thresholds are stored in every candidate and decision row. They are
explicit pilot assumptions, not fitted or validated linguistic constants.

## Decision contract

For each `(observed_form, context)`:

| Eligible anchors | Status | Canonical output | Reason |
| ---: | --- | --- | --- |
| 1 | `accepted` | Sole anchor label | `single_supported_anchor` |
| 2 or more | `ambiguous` | Null | `multiple_supported_anchors` |
| 0 | `unresolved` | Original normalized form when applied | `no_supported_anchor` |
| No decision row | `identity_unmapped` when applied | Original normalized form | `no_reconciliation_decision` |

Accepted identity spellings become `canonical_identity`; accepted changes
become `variant_mapped`. Ambiguity never falls through to rank 1. Missing
normalization remains distinct from surname-selection abstention.

## Rajasthan pilot

`evidence-rajasthan` reads only the existing accepted `milaan_raj` T1/T2 link
artifact. It selects the final eligible Devanagari token independently on the
roll and ration sides and treats the ration-side spelling as a provisional
anchor. It does not query GCP, search for new people, or use manual labels.

This evidence is useful but not gold. Upstream linkage required equality of the
complete name skeleton. It therefore favors already-similar transcriptions and
cannot measure recovery outside that linkage support. A high-precision person
link does not make every ration spelling the uniquely correct canonical form.

The current local run contains 1,004,418 accepted Rajasthan links. It yields
257,509 pairs where both sides have a selected final token, 3,486 tier-specific
directed evidence rows, and 2,021 observed forms. At the declared gates:

| Decision | Observed forms |
| --- | ---: |
| Accepted identity | 608 |
| Accepted variant | 93 |
| Ambiguous | 114 |
| Unresolved | 1,206 |

Examples of developmental accepted variants include `अखतर` → `अख्तर`, `आसीफ`
→ `आसिफ`, and `किशौर` → `किशोर`. These are outputs of the stated evidence
rule, not hand-adjudicated truths. `शर्मा` remains ambiguous because both
`शर्मा` (support 828) and `शार्मा` (support 2) pass the current gates. That is
intentionally conservative: Upnaam has not yet adopted a dominance-margin
assumption.

An LLM is not used in this revision. A future evaluated model could rerank or
veto only the retained ambiguous candidate set, with model/version provenance;
it should not invent anchors or erase ambiguity without a labeled evaluation.
