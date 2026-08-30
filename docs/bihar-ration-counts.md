# Bihar ration surname counts

## Estimand

The artifact counts the final eligible token written in each Bihar ration-card
member name. It is a grouped description of source transcriptions, not a claim
that the token is a legal or hereditary family surname.

One output row represents one conservatively normalized token. The artifact
contains no person names, member identifiers, household identifiers,
relationships, father names, ages, or phone numbers.

## Selection and grouping rules

- Names are read from `family_members_tables.sub_table`, a JSON household
  roster, using the `सदस्य का नाम` field.
- The existing Bihar rule selects the final token containing at least two
  alphabetic characters after leading honorific removal.
- One-token names and names without an eligible token abstain.
- `Devi`, `Rani`, `Kumari`, `Kumar`, `Singh`, and similar tokens are retained.
- Grouping uses `surname_source_normalized`. No transliteration, edit-distance
  merge, canonicalization, or household surname inference is applied.
- `surname_raw_mode` is the most common source spelling within a normalized
  group. Equal counts are resolved by lexical order so the result is stable.
- `member_count` counts selected member names. `household_count` counts a token
  at most once per JSON roster.

The source parser's `members_qty` can include blank roster rows that are absent
from the stored JSON. The audit therefore reports both declared and parsed
member totals and the number of households where they differ.

## Output dictionary

| Field | Meaning |
| --- | --- |
| `surname_source_normalized` | Conservative same-script grouping key |
| `surname_raw_mode` | Most frequent exact selected spelling |
| `surname_raw_mode_count` | Members carrying the modal raw spelling |
| `raw_variant_count` | Distinct exact spellings in the normalized group |
| `member_count` | Selected member names in the group |
| `household_count` | Distinct roster rows containing the group |
| `surname_provenance` | `bihar_ration_written_final_token` |
| `normalization_revision` | Normalization implementation revision |
| `aggregate_revision` | Immutable aggregation-contract revision |

## Command

```console
upnaam aggregate-bihar-ration bihar_ration_surname_counts.parquet \
  --part ration_cards.sqlite.gz.001 \
  --part ration_cards.sqlite.gz.002 \
  --index ration_cards.sqlite.gzidx \
  --audit bihar_ration_counts_audit.json \
  --manifest bihar_ration_counts_manifest.json
```

The command streams the source table once and writes only grouped counts. A
`--limit-households` run is explicitly marked incomplete in its audit and
manifest.

## Complete source run

The first complete run produced:

| Quantity | Count |
| --- | ---: |
| Household rosters | 17,696,683 |
| Parsed member rows | 85,798,262 |
| Members with a selected final token | 79,358,176 |
| Members abstained | 6,440,086 |
| Households with at least one selected token | 17,539,149 |
| Distinct normalized token groups | 310,949 |

Selection coverage is 92.49% of parsed member rows, and 99.11% of households
contain at least one selected token. The selected and abstained counts sum
exactly to the parsed-member count.

Every household has a declared-member count exactly one larger than its stored
JSON roster. In aggregate, 103,494,945 declared members minus 85,798,262 parsed
members equals the 17,696,683 household rows. The grouped artifact therefore
uses parsed member rows as its denominator.

The most frequent groups demonstrate why this is a written-token artifact:

| Normalized token | Members | Households |
| --- | ---: | ---: |
| `देवी` | 15,339,399 | 12,041,496 |
| `कुमार` | 14,327,800 | 8,087,238 |
| `कुमारी` | 13,734,026 | 7,993,738 |
| `यादव` | 1,925,044 | 1,234,088 |
| `खातुन` | 1,877,580 | 1,083,947 |
| `खातून` | 1,834,963 | 1,204,874 |
| `सिंह` | 1,547,852 | 1,019,133 |
| `राम` | 1,297,666 | 828,559 |
| `पासवान` | 1,177,938 | 760,953 |
| `साह` | 1,079,015 | 755,051 |

These groups have not been transliterated or reconciled. For example, `खातुन`
and `खातून` remain separate, as do Devanagari and Latin renderings of `Devi`.
That separation is the input to canonicalization, not an error in aggregation.
