# Bihar land surname counts

## Estimand

The artifact counts the final eligible token written in each distinct Bihar
land-record ryot name. One input row is one distinct official full-name string,
not a person, account, holding, parcel, or land-record transaction. Repeated
people with the same written full name are represented once, while spelling
differences remain separate source strings.

The output is a provisional official-record vocabulary. It does not assert
that every final token is a hereditary surname or that the most frequent
spelling is canonical.

## Source and rules

The source Parquet contains 3,197,304 rows in `name_of_ryot`: 3,197,303 unique
nonnull strings and one null. The command rejects duplicate nonnull names and
non-text name columns.

- Apply the Bihar final-eligible-token rule with a two-letter minimum.
- Drop only the versioned leading honorifics used throughout Upnaam.
- Abstain on null, empty, ineligible, and one-token names.
- Retain `देवी`, `रानी`, `कुमार`, `सिंह`, and similar tokens.
- Group with `normalization-v1`; do not transliterate or edit-merge.
- Do not read or use caste annotations.

Run locally with:

```console
upnaam aggregate-bihar-land unique_hindi_names_uncleaned.parquet \
  bihar_land_surname_counts.parquet \
  --audit bihar_land_counts.json --manifest bihar_land_counts.manifest.json
```

## Output dictionary

| Field | Meaning |
| --- | --- |
| `surname_source_normalized` | Conservative same-script grouping key |
| `surname_raw_mode` | Most frequent exact selected token among distinct full names |
| `surname_raw_mode_count` | Distinct full names carrying the modal raw token |
| `raw_variant_count` | Exact raw selected tokens in the normalized group |
| `distinct_full_name_count` | Distinct official full-name strings selecting the token |
| `surname_provenance` | `bihar_land_written_final_token` |
| `normalization_revision` | Normalization implementation revision |
| `aggregate_revision` | Immutable aggregation-contract revision |

## Complete source run

| Quantity | Count |
| --- | ---: |
| Source rows | 3,197,304 |
| Unique nonnull full-name strings | 3,197,303 |
| Names with a selected final token | 2,920,486 |
| Abstained names | 276,818 |
| Normalized final-token groups | 144,081 |

The abstentions comprise 276,318 one-token names, 497 names without an eligible
token, and 3 missing or normalization-empty names.

| Normalized token | Distinct full-name strings |
| --- | ---: |
| `देवी` | 177,693 |
| `सिंह` | 125,117 |
| `यादव` | 118,315 |
| `सिह` | 73,125 |
| `साह` | 69,029 |
| `राय` | 65,022 |
| `महतो` | 63,231 |
| `मंडल` | 58,903 |
| `वगैरह` | 41,011 |
| `चौधरी` | 34,824 |

The `वगैरह` result is a material source-specific failure of the literal final
token rule: the land name field commonly appends administrative notation
meaning “and others.” Other frequent renderings include `वगै0`, `वोगैरह`,
`वैगरह`, `वगेरह`, and `बगैरह`; `अन्य` is another observed suffix. These are
preserved in this baseline so the audit remains faithful to the approved rule.
A source-specific terminal-notation policy must be separately declared and
versioned before the preceding token can be inferred as the surname.

## Relation to the ration vocabulary

The land and ration aggregates share 46,417 exact normalized token forms. Of
the 28,854 ration forms observed at least 10 times, 15,858 occur exactly in the
land vocabulary and cover 77,969,914 ration-member token selections. That is
98.86% of selections represented by the frequency-filtered ration forms.

Exact cross-source presence is useful anchor-vocabulary coverage, not paired
evidence that a neighboring spelling should map to that anchor. The existing
edit-neighbor table contains 23,612 pairs where both spellings occur in land
records, 17,249 where exactly one does, and 13,320 where neither does. Upnaam
does not turn those counts into canonical decisions.
