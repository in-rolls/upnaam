# Upnaam

Upnaam resolves surname tokens in parsed Indian administrative name records.
It preserves the source name, applies a declared selection rule or corroboration
policy, and abstains when the evidence is insufficient or conflicting.

The result is the surname component supported by the configured source policy.
It is not a claim about a person's legal name, hereditary family name, caste,
religion, ethnicity, gender, residence, or origin.

## Installation

```console
pip install upnaam
```

Karnataka token romanization uses the optional Indicate integration and Python
3.13 or later:

```console
pip install "upnaam[romanization]"
```

## Python interface

`resolve_electors` accepts one row per record with a unique source-qualified
`elector_id`, a lowercase `state`, and the raw `name`. It preserves row order.

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
resolved[["name_raw", "surname_raw", "abstained", "resolver_revision"]]
```

The default policy selects the final eligible token for Bihar, Punjab, and
Rajasthan and the first eligible token for Maharashtra. Unsupported states and
names without enough usable tokens abstain. A custom versioned policy can be
loaded with `load_resolver_policy`.

## Parsed-roll adapters

The `resolve-electors` command applies household and relation-name
corroboration to the common parsed-roll schema.

| State | Current rule |
| --- | --- |
| Andhra Pradesh | Household and relation evidence; no position fallback |
| Telangana | Household and relation evidence; no position fallback |
| Lakshadweep | Household, relation, and printed house-name evidence; no position fallback |
| Karnataka | Native-token corroboration with a supplied local romanization lookup; explicit initials-plus-one-word fallback |
| Gujarat | First written token in the surname-first 2017 source; supplied local token lookup |

```console
upnaam resolve-electors electors.parquet surnames.parquet \
  --state andhra --audit surnames_audit.json
upnaam resolve-gujarat gujarat_2017.parquet gujarat_2017_surnames.parquet \
  --romanization-lookup lookup.tsv.gz --audit gujarat_2017_surnames_audit.json
```

Dedicated commands validate and resolve the audited J&K English, Hindi, and
Urdu inventory schemas:

```console
upnaam resolve-jk-english inventory.parquet source_audit.json output_directory
upnaam resolve-jk-hindi inventory.parquet source_audit.json output_directory
upnaam resolve-jk-urdu inventory.parquet source_audit.json output_directory
```

Native selection and Latin mapping remain separate. Adding a romanization map
cannot create a selection or change an abstention.

Punjab has a separate adapter for its validated roll-to-transliteration join.
Bihar and Rajasthan adapters produce typed reference labels and aggregate
surname evidence from accepted source links. See the
[data contracts](docs/data-contracts.md) for their required keys and validation
rules.

## Output contract

Every resolved row retains its source identity and records the rule revision.
Across the generic and parsed-roll resolver artifacts, the main fields are:

| Field | Meaning |
| --- | --- |
| `surname_raw` | Exact token selected from the source name |
| `surname_source_normalized` | Conservative same-script comparison form |
| `surname_latin_raw` | Exact Latin token supplied by the source or a validated alignment |
| `surname_latin_normalized` | Lowercase ASCII comparison form |
| `surname_canonical` | Accepted reconciliation anchor, unchanged normalized value, or null on ambiguity |
| `surname_position` | Selected token position, when applicable |
| `surname_provenance` | Rule that selected the token |
| `surname_evidence` | Evidence rung used by corroboration adapters |
| `surname_confidence` | Source-specific diagnostic when defined; otherwise null |
| `abstained` | Whether the resolver declined to select a surname |
| `abstention_reason` | Stable machine-readable reason |
| `normalization_revision` | Normalization implementation revision |
| `resolver_revision` | Source-policy implementation revision |

Raw, same-script normalized, Latin, and canonical values are separate columns.
Missing Latin text stays null. Confidence is emitted only when the adapter
defines a measured diagnostic; it is not a probability that the selected token
is a hereditary surname.

## Selection and reconciliation rules

- Unicode normalization removes formatting marks, converts danda to a token
  boundary, collapses whitespace, and case-folds. It does not transliterate.
- Leading honorifics are ignored only when they match the versioned list.
- A candidate requires at least two alphabetic characters.
- Position-based resolution abstains on a single eligible token.
- Household and relation evidence can corroborate a source token but cannot
  overwrite the written name.
- Conflicting evidence abstains where the source policy requires it.
- String similarity proposes reconciliation candidates. It cannot establish a
  mapping by itself.
- Reconciliation accepts exactly one candidate that passes the declared evidence
  gates. Multiple passing candidates remain explicit ambiguity.

The machine-readable state policy is
[`src/upnaam/resolver.json`](https://github.com/in-rolls/upnaam/blob/main/src/upnaam/resolver.json). The full contracts are in
[assumptions](docs/assumptions.md),
[surname ladder](docs/surname-ladder.md), and
[canonicalization](docs/canonicalization.md).

## Command-line interface

The CLI reads and writes CSV, compressed CSV, and Parquet tables.

```console
upnaam normalize names.parquet normalized.parquet --name-column name
upnaam select normalized.parquet candidates.parquet --name-column name
upnaam resolve electors.parquet resolved.parquet
upnaam reconcile propose surname_counts.parquet candidates.parquet \
  --audit candidates_audit.json
upnaam reconcile rank evidence.parquet candidates.parquet
upnaam reconcile decide candidates.parquet decisions.parquet --audit audit.json
upnaam reconcile apply resolved.parquet canonical.parquet decisions.parquet
```

Run `upnaam --help` for the complete command set.

## Privacy and use

Person-level electoral, ration, land, relationship, and household records should
remain in controlled storage. Public outputs should be limited to reviewed
aggregates, schemas, manifests, tests, and evidence that has passed a separate
privacy review.

Upnaam is intended for auditable data preparation and aggregate research. It
must not be used to label individuals or make consequential decisions about
them. It does not publish surname-to-caste mappings, manufacture confidence
scores, force family surnames onto records, or treat edit distance as identity
evidence.

Detailed adapter documentation is available in the
[documentation index](docs/index.md).
