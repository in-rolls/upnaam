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
5. reconciles a spelling to a named canonical anchor only when the evidence
   leaves exactly one eligible anchor.

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
| `surname_canonical` | Accepted anchor label; otherwise the unchanged normalized value, except that ambiguity is null |
| `canonicalization_status` | `identity_unmapped`, `canonical_identity`, `variant_mapped`, `ambiguous`, `normalization_unavailable`, or `not_applicable` |
| `canonicalization_reason` | Stable reason such as `single_supported_anchor`, `multiple_supported_anchors`, or `no_reconciliation_decision` |
| `canonicalization_provenance` | Named reconciliation evidence; null when no decision was applied |
| `canonicalization_revision` | Immutable reconciliation implementation revision |
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
  -> uniquely supported anchor label (`surname_canonical`)
```

Levenshtein similarity generates candidate pairs only. It never establishes a
merge on its own. Evidence is directed from an observed form to a stable anchor
ID and label and carries its context, source, tier, support, and similarity.
Candidates are ranked, but rank does not force a choice:

- exactly one candidate passing the declared gates is accepted;
- more than one passing candidate yields `ambiguous` and a null canonical
  surname; and
- no passing candidate leaves the normalized spelling unchanged as
  `identity_unmapped`.

Many observed spellings may therefore point to one anchor, while one observed
spelling may retain several candidate anchors. This avoids the false
transitivity and forced partition created by global string clustering. The
current support and similarity gates are stored in every candidate and decision
row; neither the rank nor `support_share` is a calibrated probability.

Thus `jadhab` and `jadhav` may be proposed because they are close strings, but
they remain separate until linked records or another accepted evidence source
supports a directed reconciliation. Complete-link clustering remains in the
research namespace solely as a comparator. It is not the public canonicalizer.
The complete contract is in `docs/canonicalization.md`.

## Package layout

Reusable technology lives in a small set of modules:

| Module | Responsibility |
| --- | --- |
| `normalization.py` | Lossless tokenization and deterministic comparison forms |
| `selection.py` | Positional candidate generation and abstention |
| `resolver.py` | State-policy selection and standard elector schema |
| `compressed_sqlite.py` | Read-only targeted queries over multipart gzip-compressed SQLite |
| `canonicalization/candidates.py` | Efficient edit-distance candidate generation |
| `canonicalization/reconciliation.py` | Directed evidence, ranking, and ambiguity-preserving decisions |
| `canonicalization/mapping.py` | Decision validation, application, status, reason, and provenance |
| `adapters/bihar.py` | Official-land reference labels on accepted Bihar links |
| `adapters/bihar_land_counts.py` | Grouped final-token vocabulary from distinct official Bihar land names |
| `adapters/bihar_land_inference.py` | Separate inferred vocabulary after exact land-record suffixes |
| `adapters/bihar_ration.py` | Grouped written-surname counts from Bihar ration rosters |
| `adapters/punjab.py` | Frozen Punjab roll plus validated Indicate alignment |
| `adapters/rajasthan.py` | Surname-only evidence from accepted ration links |
| `adapters/rajasthan_reference.py` | Ration-card reference labels on accepted Rajasthan links |
| `adapters/links.py` | Accepted Bihar land and Rajasthan ration links |
| `research/` | Developmental diagnostics and clustering comparator, not public API |

There is one installed CLI rather than numbered scripts. Each command is a
separate pipeline operation and reads or writes CSV/CSV.GZ or Parquet:

```console
upnaam normalize names.parquet normalized.parquet --name-column name
upnaam select normalized.parquet candidates.parquet --name-column name
upnaam resolve electors.parquet resolved.parquet
upnaam labels-bihar-land bihar_links.parquet bihar_reference_labels.parquet \
  --manifest bihar_reference_manifest.json
upnaam aggregate-bihar-land unique_hindi_names_uncleaned.parquet \
  bihar_land_surname_counts.parquet --audit bihar_land_counts.json
upnaam infer-bihar-land unique_hindi_names_uncleaned.parquet \
  bihar_land_inferred_surname_counts.parquet --audit bihar_land_inference.json
upnaam labels-rajasthan-ration rajasthan_links.parquet \
  rajasthan_reference_labels.parquet --manifest rajasthan_reference_manifest.json
upnaam aggregate-bihar-ration bihar_ration_surname_counts.parquet \
  --part ration_cards.sqlite.gz.001 --part ration_cards.sqlite.gz.002 \
  --index ration_cards.sqlite.gzidx --audit bihar_ration_counts_audit.json
upnaam evidence-rajasthan accepted_links.parquet rajasthan_evidence.parquet
upnaam reconcile propose bihar_ration_surname_counts.parquet \
  bihar_ration_variant_candidates.parquet --audit bihar_variant_candidates.json
upnaam reconcile rank rajasthan_evidence.parquet candidates.parquet
upnaam reconcile decide candidates.parquet decisions.parquet --audit audit.json
upnaam reconcile apply resolved.parquet canonical.parquet decisions.parquet
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

The first Rajasthan surname-only pilot produces 2,021 observed-form decisions:
608 accepted identities, 93 accepted variants, 114 explicit ambiguities, and
1,206 unresolved forms. These are operating counts, not accuracy estimates;
the ration-side token is a provisional anchor. Details and sample decisions are
in `docs/canonicalization.md`.

For the person-level Rajasthan reference artifact, the accepted ration-card
transcription is explicitly treated as `provisional_gold`. Upnaam accepts its
final eligible token even when the roll differs, abstains on one-token ration
names, and excludes every link involving one of 570 ration members linked to
multiple electors. The first run accepts 474,587 labels from 1,004,418 T1/T2
links. The complete contract is in `docs/rajasthan-ration-reference.md`.

For Bihar, Upnaam treats the official land-side name as the preferred reference
transcription on the existing 4,387 exact unique one-to-one Shekhpura links.
The first run accepts 4,366 final-token reference labels, abstains on 20
land-side single-token names, and excludes one land/roll positional conflict.
The complete join contract, dictionary, and recode ledger are in
`docs/bihar-land-reference.md`.

The separate full-state Bihar land pass uses 3,197,303 distinct nonnull official
ryot-name strings and selects 2,920,486 written final tokens. Its 144,081 token
groups form a provisional official-record vocabulary, not person counts or
canonical labels. The frequent terminal notation `वगैरह` demonstrates why
official transcription quality does not by itself make every final token a
surname. The complete contract is in `docs/bihar-land-counts.md`.

The separate land inference pass adjusts 79,891 names whose written final token
exactly matches one of 10 approved administrative suffixes. Version 2 scans
left across exact `एव` and `एवं` connectors and repeated approved suffixes. It
reports direct-written, immediate-previous, and chain-adjusted support
separately and performs no fuzzy suffix matching.

No hand-labeled surname corpus is required. Manual review, if performed, audits
linkage precision rather than supplying surname labels.

The Bihar ration SQLite source does not need to be expanded to its 56.7 GB
logical size. Upnaam's generic compressed-SQLite adapter uses a reusable seek
index to run targeted read-only queries directly over its two 3.30 GB archive
parts. The access contract and example are in `docs/compressed-sqlite.md`.

The first complete Bihar ration aggregation scans 17,696,683 household rosters
and 85,798,262 stored member rows. It selects 79,358,176 written final tokens
into 310,949 normalized groups while retaining `Devi`, `Kumar`, `Kumari`, and
similar tokens. Results and the denominator audit are in
`docs/bihar-ration-counts.md`.

## Privacy and non-goals

Raw electoral, ration, land, relationship, and household records remain
restricted local artifacts. Public outputs should be limited to reviewed
reconciliation artifacts, schemas, manifests, tests, and aggregate diagnostics.

Upnaam does not:

- infer caste or publish surname-to-caste mappings;
- claim calibrated confidence without a calibration target;
- force a household or family surname onto an elector;
- treat string similarity as identity evidence;
- use a general English-name parser to decide Indian name order; or
- support consequential decisions about individuals.

The repository is unreleased. Punjab is the first full elector adapter and
Rajasthan is the first anchored-reconciliation pilot. The normalization,
selection, reconciliation, and application primitives are state-agnostic and
intended for one-dataset-at-a-time expansion.
