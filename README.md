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

No hand-labeled token corpus is required by the design. Any manual review of
record links is an audit of linkage precision, not a source of surname labels.

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

The repository currently defines the product and evidence contract. No resolver
has been implemented or released.
