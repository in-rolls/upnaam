# Upnaam

Upnaam resolves surnames in parsed Indian electoral rolls.

For each elector, it identifies the name component that functions as the
surname **in the roll record**, preserves the exact source text, and maps
supported spelling, OCR, and transliteration variants to a canonical form. When
an independently linked land or ration record supplies a fuller name, Upnaam
may also report a separately named family surname that is absent from the roll.

Upnaam does not infer caste, religion, ethnicity, gender, or any other identity
or social category. It supplies name fields and evidence for downstream
aggregate research, including `last-name-basis` and `outkast`.

## The two targets

The surname recorded for an elector and a surname recovered from family
evidence are different quantities. Upnaam never silently substitutes one for
the other.

### Recorded surname

`surname` answers:

> Which component of this elector's name is used as the surname in this roll
> record?

It is selected from the elector's own recorded name. It may be the last token,
the first token, or another token when the evidence supports a different name
order. It remains a recorded surname even when it is not transmitted within a
family.

For `Poorna Devi`, the ordinary last-token rule yields:

```text
surname_raw = "Devi"
surname = "devi"
surname_provenance = "written"
```

### Family surname

`family_surname` answers:

> Does an independently observed relative, household, land record, or ration
> record support a family surname for this elector that differs from, or is
> absent from, the roll name?

For `Poorna Devi` linked to an independent fuller record `Poorna Devi Sharma`,
the result may be:

```text
surname = "devi"
family_surname = "sharma"
family_surname_provenance = "land_record"
```

`family_surname` is nullable. Failure to recover one means only that the
available evidence is insufficient. It does not establish that the person has
no family surname.

## Unit of input and output

One input row is one elector record from a parsed electoral roll. At minimum,
the input must contain a source-qualified record identifier and the elector's
name. Relationship name, relationship type, house number, part, year, state,
and geography are optional evidence fields whose availability and use are
recorded.

One output row corresponds to the same elector record. Row count, order, and
identifier are preserved.

The intended result fields are:

| Field | Meaning |
| --- | --- |
| `surname` | Canonical recorded surname, if resolved |
| `surname_raw` | Exact substring selected from the roll name |
| `surname_position` | `first`, `middle`, `last`, or `single` |
| `surname_provenance` | Evidence used to select the recorded surname |
| `surname_score` | Uncalibrated resolution score during development |
| `family_surname` | Canonical family surname supported by other evidence |
| `family_surname_raw` | Exact supporting substring from the source record |
| `family_surname_provenance` | `relative`, `household`, `land_record`, or `ration_card` |
| `family_surname_score` | Uncalibrated family-surname score during development |
| `abstained` | Whether Upnaam declined to resolve the recorded surname |
| `abstention_reason` | Stable reason for abstention |
| `normalization_revision` | Immutable revision of the normalization artifacts |
| `resolver_revision` | Immutable revision of the resolution artifacts |

Scores will not be called confidence or probability until calibration against
independent evidence supports that interpretation.

## Evidence and assumptions

Upnaam begins with weak, inspectable assumptions:

1. The source name is preserved exactly. Normalization never overwrites it.
2. The first and last tokens are candidates, not universal surname positions.
3. Token length may be a feature or candidate-generation rule; short tokens are
   not silently deleted from the record.
4. Honorific and other token lists are versioned evidence, not automatic truth.
5. No token is predeclared a family surname because of its spelling alone.
6. Similar spelling alone does not establish that two tokens are variants.
7. A surname absent from one record is not evidence that the person has no
   surname.
8. Upnaam abstains when the available evidence does not distinguish candidates.

The first baseline is the final whitespace-separated token. Other rules must
show that they improve surname resolution on independent evidence before they
replace it for any state or source.

## Variant resolution

Variant learning uses independently linked observations of the same name. A
roll-to-land or roll-to-ration link must be established without relying on the
name component whose variation is being learned.

Given a trusted link, Upnaam aligns the two token sequences. The alignment can
produce:

- exact token matches;
- candidate spelling, OCR, or transliteration variants;
- tokens present only in the roll;
- tokens present only in the linked record, including possible omitted
  surnames.

Levenshtein distance is the baseline character-distance measure. Learned edit
weights may lower the cost of recurrent source-specific errors, but a low edit
distance does not by itself merge two tokens.

Canonicalization is represented as a token graph:

- nodes are observed normalized spellings;
- edges are supported equivalence claims with scores and provenance;
- clusters require conservative, non-chaining compatibility;
- ambiguous tokens remain separate;
- the canonical spelling is a supported cluster medoid, not necessarily the
  most frequent spelling.

The versioned variant artifact records every variant-to-canonical mapping, its
edit score, its linked-record support, its sources, and the artifact revision.

## External records

Land and ration records serve two purposes:

1. alternate transcriptions for learning spelling and OCR variants;
2. independent fuller names that may reveal a family surname omitted from the
   roll.

They are not assumed error-free. Every linkage method declares its blocking
fields, compared fields, expected cardinality, uniqueness rule, rival-candidate
margin, and acceptance threshold. Linkage coverage and disagreement are
reported by source, geography, and sex where those fields are available.

For Rajasthan, Upnaam reuses the existing `milaan_raj` links between the 2021
rural ration-card census and the 2018 electoral rolls. The source pipeline
contains approximately 15.9 million cards and 62.8 million members with names,
ages, and explicit relationships. Only its high-precision T1 and T2 person
links are eligible; T3 links are excluded. The existing negative-control audit
estimates false-discovery rates of approximately 0.1% for T1 and T2. Upnaam
does not rebuild or broaden that linkage. It records the upstream artifact
revision, linkage tier, and precision evidence with every Rajasthan-derived
result.

No hand-labeled token corpus is required by the design. Any manual review of
record links is an audit of linkage precision, not a source of surname labels.

## Pipeline boundaries

Each transformation is an independent, rerunnable stage with a declared input
and output artifact. No stage silently repeats or alters an earlier stage's
work. Pipeline scripts orchestrate the transformations; reusable logic lives in
the `upnaam` package and is tested directly.

The planned stages are:

| Stage | Responsibility | Principal output |
| --- | --- | --- |
| `00_profile_sources` | Audit schemas, keys, missingness, scripts, and source coverage | source profile and data dictionary |
| `01_normalize_names` | Preserve raw strings and create deterministic comparison forms and tokens | normalized records Parquet |
| `02_extract_candidates` | Emit first-, last-, and other explicitly defined positional candidates without selecting a winner | surname candidates Parquet |
| `03_link_records` | Link roll, land, and ration observations under source-specific linkage contracts | source links Parquet |
| `04_align_names` | Align token sequences within accepted links and classify alignment operations | aligned name pairs Parquet |
| `05_learn_edit_model` | Estimate source- and script-specific edit weights from linked pairs and negative controls | versioned edit-model artifact |
| `06_cluster_variants` | Build conservative token-variant clusters using the edit model and linked evidence | variants Parquet |
| `07_resolve_surnames` | Select the recorded surname from canonicalized candidates or abstain | recorded-surname results Parquet |
| `07_resolve_linked_surnames` | Use alternate spacing to split a roll token only when the external final token is an exact suffix | linked recorded-surname results Parquet |
| `08_resolve_family_surnames` | Add separately reported family surnames supported by relative, household, land, or ration evidence | family-surname results Parquet |
| `09_evaluate` | Compare rules, measure coverage and error, and verify artifact and row-count contracts | evaluation report and manifest |

Normalization, record linkage, name alignment, edit-distance learning, variant
clustering, recorded-surname resolution, and family-surname resolution remain
separate even when one command eventually runs the complete pipeline. Every
stage records its configuration and upstream artifact hashes so an output can
be reproduced without rerunning unrelated stages.

These files will be created when their stages are implemented. The repository
does not contain empty placeholder scripts.

The aggregate candidate and recorded-surname stages are state-scoped
(`--state`) so each very large state table runs in a fresh process and can be
retried without invalidating completed state artifacts.

## Version 1 scope

Version 1 covers parsed electoral rolls from selected northern Indian states.
The supported states and scripts will be declared from the available source
inventory rather than inferred from the phrase "North India." Unsupported
states, scripts, and required contexts abstain explicitly.

Row-level electoral, land, ration, relationship, and household data are not
public runtime artifacts. Public artifacts are limited to privacy-reviewed
models, variant mappings, schemas, manifests, and evaluation evidence.

## Non-goals

Upnaam does not:

- infer caste or publish surname-to-caste mappings;
- score how informative a surname is;
- infer a person's identity or group membership;
- treat a household surname as the elector's recorded surname;
- force a family surname when none is supported;
- use a general English-name parser as evidence about Indian naming order;
- support consequential decisions about individuals.

Downstream analysis and interpretation belong in their respective research
repositories. Upnaam's job ends with a documented name resolution, its source
text, provenance, uncertainty, and abstention state.

## Status

The repository contains an unreleased baseline resolver and source-specific
adapters for the locally available electoral-roll, Rajasthan ration-card, and
Bihar land-record evidence. The baseline implements only the explicit rules in
this document. Its scores are diagnostic quantities, not calibrated
probabilities.

The exact baseline rules and the assumptions they do and do not make are
frozen in [the Version 1 assumptions](https://github.com/in-rolls/upnaam/blob/main/docs/assumptions.md).
The first full four-state diagnostic is in
[`data/audit/evaluation.csv`](https://github.com/in-rolls/upnaam/blob/main/data/audit/evaluation.csv).
It shows that the
final-token baseline is especially questionable for Maharashtra; no
state-specific switch has been made without approval.
