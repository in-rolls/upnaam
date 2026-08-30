# Upnaam

Upnaam is generic, auditable surname-resolution technology for Indian name
records. Punjab is its first complete person-level adapter; it is not the
definition of the package.

Given a parsed electoral-roll row, Upnaam:

1. preserves the source name;
2. emits first and final eligible surname candidates;
3. applies an explicit state-position rule or abstains;
4. keeps raw, normalized, Latin, and canonical surname representations in
   separate columns; and
5. applies a spelling-variant map only when independent evidence supports it.

The estimand is the surname component **written in the source name under a
declared positional rule**. It is not necessarily a legal, hereditary, or
family surname. An external record may provide separate evidence of a fuller
name, but that evidence never silently overwrites the written surname.

Upnaam does not infer caste, religion, ethnicity, gender, or any other social
category. Downstream analysis belongs in repositories such as
`last-name-basis` and `outkast`.

## Output contract

The public elector interface requires one row per record with a unique
source-qualified `elector_id`, a lowercase `state`, and the raw `name`. It
preserves row order and emits:

| Field | Meaning |
| --- | --- |
| `surname_raw` | Exact token selected from the source name |
| `surname_source_normalized` | Conservative same-script Unicode comparison form |
| `surname_latin_raw` | Exact Latin token when the source or a validated aligned transcription supplies one |
| `surname_latin_normalized` | Lowercase ASCII comparison form; not a spelling merge |
| `surname_canonical` | Representative after an accepted variant map; otherwise the unchanged Latin-normalized value |
| `canonicalization_status` | `identity_unmapped`, `canonical_identity`, `variant_mapped`, `normalization_unavailable`, or `not_applicable` after surname abstention |
| `canonicalization_provenance` | Accepted map or evidence artifact; null when no mapping was consulted |
| `canonicalization_revision` | Immutable map revision |
| `surname_position` | `first` or `last`; null on abstention |
| `surname_provenance` | Positional rule that selected the written token |
| `abstained` | Whether no written surname was selected |
| `abstention_reason` | Stable reason for abstention |
| `normalization_revision` | Normalization implementation revision |
| `resolver_revision` | State-policy revision |

For `Poorna Devi` under Bihar's final-token rule:

```text
surname_raw = "Devi"
surname_source_normalized = "devi"
surname_latin_normalized = "devi"
surname_canonical = "devi"
canonicalization_status = "identity_unmapped"
surname_provenance = "written_final_token"
```

`Devi` is therefore the written surname result. Upnaam may separately test
whether a linked ration or land record supplies a fuller family name, but it
does not relabel `Devi` by intuition.

## Explicit version 1 assumptions

- Unicode normalization removes formatting marks, converts danda to a token
  boundary, collapses whitespace, and case-folds. It does not transliterate.
- Leading honorifics are ignored only when they match the small versioned list
  in `selection.py`.
- A candidate needs at least two alphabetic characters. Short tokens remain in
  the raw name.
- A single eligible token is not declared a surname; the resolver abstains.
- Bihar, Rajasthan, and Punjab select the final eligible token.
- Maharashtra selects the first eligible token.
- Unsupported states abstain. Upnaam does not guess name order from an
  individual string.
- `Devi`, `Rani`, `Kaur`, `Singh`, `Kumar`, and similar tokens are neither
  removed nor retyped. If the configured position selects one, that is the
  written-surname result.
- English `nameparser` and similar libraries are not evidence about Indian name
  order and are not used.

The machine-readable state policy is
[`src/upnaam/resolver.json`](https://github.com/in-rolls/upnaam/blob/main/src/upnaam/resolver.json).
Full assumptions are in
[`docs/assumptions.md`](https://github.com/in-rolls/upnaam/blob/main/docs/assumptions.md).

## Canonicalization ladder

Canonicalization is deliberately separate from selection and normalization:

```text
source string
  -> exact selected token (`surname_raw`)
  -> same-script normalized token (`surname_source_normalized`)
  -> exact aligned/source Latin token (`surname_latin_raw`)
  -> deterministic Latin comparison form (`surname_latin_normalized`)
  -> accepted variant representative (`surname_canonical`)
```

Levenshtein similarity generates candidate pairs only. It never establishes a
merge on its own. Accepted edges carry a source, evidence tier, support count,
and optional preferred spelling. Complete-link clustering requires direct
accepted evidence between every pair of joined clusters, preventing similarity
chains from collapsing unrelated names. Representative choice uses explicit
preferred-spelling support, then medoid distance, corpus frequency, and a final
deterministic lexical tie-break.

Thus `jadhab` and `jadhav` may be proposed because they are close strings, but
they remain separate until linked records or another accepted evidence source
supports the equivalence. Unmapped tokens remain unchanged and are marked
`identity_unmapped`.

## Package layout

Reusable technology lives in a small set of modules:

| Module | Responsibility |
| --- | --- |
| `normalization.py` | Lossless tokenization and deterministic comparison forms |
| `selection.py` | Positional candidate generation and abstention |
| `resolver.py` | State-policy selection and standard elector schema |
| `canonicalization/candidates.py` | Efficient edit-distance candidate generation |
| `canonicalization/evidence.py` | Typed accepted/rejected evidence |
| `canonicalization/clustering.py` | Conservative complete-link clustering |
| `canonicalization/mapping.py` | Map validation, application, status, and provenance |
| `adapters/punjab.py` | Frozen Punjab roll plus validated Indicate alignment |
| `adapters/links.py` | Accepted Bihar land and Rajasthan ration links |
| `research/` | Developmental aggregate and linked-record diagnostics, not public API |

There is one installed CLI rather than numbered scripts. Each command is a
separate pipeline operation and reads or writes CSV/CSV.GZ or Parquet:

```console
upnaam normalize names.parquet normalized.parquet --name-column name
upnaam select normalized.parquet candidates.parquet --name-column name
upnaam resolve electors.parquet resolved.parquet
upnaam canonicalize candidates resolved.parquet candidate_pairs.parquet
upnaam canonicalize build accepted_evidence.parquet variants.parquet
upnaam canonicalize apply resolved.parquet canonical.parquet variants.parquet
```

The Python interface is equally small:

```python
import pandas as pd
from upnaam import resolve_electors

electors = pd.DataFrame(
    {
        "elector_id": ["roll:1", "roll:2"],
        "state": ["bihar", "maharashtra"],
        "name": ["Poorna Devi", "Patil Ashwini"],
    }
)
resolved = resolve_electors(electors)
```

## Data adapters

The Punjab adapter validates row count and exact equality of 11 repeated native
fields before joining the frozen Dataverse roll to Indicate by source-row
order. It then applies the final-token rule to the native Gurmukhi name and
copies a Latin token only when complete token counts agree. Details and
aggregate results are in
[`docs/punjab-electors.md`](https://github.com/in-rolls/upnaam/blob/main/docs/punjab-electors.md).

For Rajasthan, Upnaam reuses only the existing high-precision `milaan_raj` T1
and T2 person links; it neither re-scores nor broadens them. The source pipeline
reports about 15.9 million cards, 62.8 million members, explicit relationships,
and estimated T1/T2 false-discovery rates around 0.1%. Bihar's accepted land
links are also reused rather than rebuilt. These sources can provide alternate
transcriptions and fuller-name evidence, subject to the linkage limitations in
[`docs/data-contracts.md`](https://github.com/in-rolls/upnaam/blob/main/docs/data-contracts.md).

No hand-labeled surname corpus is required. Manual review, if performed, audits
linkage precision rather than supplying surname labels.

## Privacy and non-goals

Raw electoral, ration, land, relationship, and household records remain
restricted local artifacts. Public outputs should be limited to reviewed
variant maps, schemas, manifests, tests, and aggregate diagnostics.

Upnaam does not:

- infer caste or publish surname-to-caste mappings;
- claim calibrated confidence without a calibration target;
- force a household or family surname onto an elector;
- treat string similarity as identity evidence;
- use a general English-name parser to decide Indian name order; or
- support consequential decisions about individuals.

The repository is unreleased. Punjab is the first full adapter, while the
normalization, selection, evidence, clustering, and mapping primitives are
state-agnostic and intended for one-dataset-at-a-time expansion.
