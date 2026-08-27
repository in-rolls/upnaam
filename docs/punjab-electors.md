# Punjab elector artifact

Punjab is Upnaam's first complete person-level roll dataset. Stage 10 combines
the restricted 2018 Punjab electoral-roll file from Dataverse dataset version
25.0 with the locally available Indicate transcription artifact. It emits one
row for every one of the 19,119,006 source rows; it does not deduplicate the
roll's colliding or missing source identifiers.

Both person-level inputs and the result are restricted local artifacts. Upnaam
commits the code and aggregate audit evidence, not names or other elector data.

## Source and join contract

The roll input is `punjab_all_clean+t13n.csv.gz` from Dataverse dataset
`doi:10.7910/DVN/MUEGDT`, version 25.0. The historical `*_t13n` columns in that
file are not used: 12,003,070 of its `elector_name_t13n` values contain
Malayalam characters and are not credible Punjabi-to-Latin transcriptions.

The replacement is Indicate's local
`punjab_transliteration_subset.parquet`, which has 19,119,006 rows. Stage 10
joins the files by zero-based source-row order only after verifying exact
equality of all 11 repeated native fields in each batch:

- elector and father-or-husband names;
- assembly and parliamentary constituency names;
- main town, police station, mandal, revenue division, and district; and
- polling-station name and address.

Any row-count or native-field disagreement fails the stage. Row order is a
validated source contract here, not a general-purpose linkage method.

The source `id` is not an elector key: 99,261 non-unique ID values occur in
2,130,443 rows, and 654,308 rows have a missing or blank ID. Stage 10 therefore
defines `elector_id` as `muegdt-v25-punjab:<source_row>` and retains the source
value separately as `source_elector_id`.

## Resolution assumptions

The stage applies only the approved `resolver-v1` Punjab rule:

1. Preserve the native and Latin full names exactly.
2. Tokenize the native name under `normalization-v1`.
3. Ignore only the versioned leading honorifics already declared by Upnaam.
4. Require at least two alphabetic characters in an eligible token.
5. Abstain when fewer than two eligible native tokens remain.
6. Otherwise select the final eligible native token. Do not exclude `Kaur`,
   `Singh`, `Kumar`, `Devi`, or any other token by spelling.
7. Copy the Latin token at the same position only when the complete native and
   Latin token sequences have equal length.
8. If token counts differ, retain the resolved native surname, leave the Latin
   and ASCII surname fields null, and report `token-count-mismatch`. Do not use
   fuzzy matching or a nearby token.
9. Convert an aligned Latin token to a lowercase ASCII comparison form with
   Unicode compatibility decomposition and combining-mark removal. For
   example, `Rāj` becomes `raj`. This is not cross-spelling canonicalization:
   `Kanr` remains `kanr` unless a later variants stage supplies independent
   evidence for a mapping.

This stage does not use the relative name, house number, sex, English name
parsers, Levenshtein distance, household propagation, land records, ration
cards, or a learned name model to change the selection.

## Output contract

The main fields are:

| Field | Meaning |
| --- | --- |
| `source_row` | Zero-based row in the frozen Dataverse file |
| `elector_id` | Unique source-revision-qualified artifact key |
| `source_elector_id` | Original, non-unique and nullable roll ID |
| `name_native_raw` | Exact Gurmukhi elector name |
| `name_latin_raw` | Exact Indicate full-name transcription |
| `surname_native_raw` | Exact selected Gurmukhi token |
| `surname_native` | Conservatively normalized Gurmukhi token |
| `surname_latin_raw` | Exact aligned Indicate token, including diacritics |
| `surname` | Lowercase ASCII comparison form, when alignment succeeds |
| `surname_position` | `last` for a resolved native surname |
| `surname_provenance` | `written_final_token` for a resolved native surname |
| `abstained` | Whether native recorded-surname selection abstained |
| `abstention_reason` | `missing-name`, `no-eligible-token`, or `single-token-name` |
| `transliteration_status` | `aligned`, `token-count-mismatch`, `ineligible-latin-token`, or `no-surname-selected` |

Because native resolution and transliteration are separate decisions,
`abstained = false` can coexist with a null `surname`: in that case
`surname_native_raw` remains populated and `transliteration_status` explains
why no ASCII value was asserted.

`surname` makes exact grouping and downstream joins convenient but does not
claim that OCR or spelling variants have been merged. For example, the source
native token `ਕੰਰ` is transcribed as `Kanr` and remains `kanr`; Upnaam does not
silently rewrite it to `kaur` in this stage.

The artifact also retains the source row's number, year, filename, part, house
number, age, sex, relationship, relative name, and selected native/Latin
geography fields. Every row carries the normalization, resolver, and
transliteration revision. The stage manifest records SHA-256 fingerprints for
both inputs and all outputs.

Run the stage with:

```console
python scripts/10_resolve_punjab_electors.py
```

All paths can be overridden on the command line. The defaults expect the
restricted Dataverse file under `data/source/dataverse/` and the Indicate
artifact in the sibling repository.

## First complete run

The frozen v1 run produced:

| Result | Rows | Share of all rows |
| --- | ---: | ---: |
| Source and output | 19,119,006 | 100.00% |
| Native surname resolved | 16,899,471 | 88.39% |
| ASCII comparison form resolved | 16,898,030 | 88.38% |
| Abstained | 2,219,535 | 11.61% |
| Resolved native surname with token-count mismatch | 1,319 | 0.0069% |
| Resolved native surname with ineligible Latin token | 122 | 0.0006% |

Native-surname coverage is 85.75% for female rows and 90.66% for male rows.
The difference is descriptive of this final-token rule and source data; it is
not a validated sex-specific accuracy estimate. The checked-in
[`punjab_elector_resolution.csv`](../data/audit/punjab_elector_resolution.csv)
contains the complete aggregate coverage table by sex and relationship field.

The ten most frequent ASCII comparison forms illustrate both the scale and the
need to keep variant resolution separate:

| Form | Rows |
| --- | ---: |
| `singh` | 6,434,719 |
| `kaur` | 4,289,329 |
| `kanr` | 1,190,956 |
| `kumar` | 1,060,342 |
| `rani` | 595,446 |
| `devi` | 564,068 |
| `laal` | 219,871 |
| `ram` | 199,539 |
| `sharma` | 175,583 |
| `kumaari` | 137,682 |

Of the `kanr` rows, 1,190,954 come directly from native `ਕੰਰ` transcribed as
`Kanr`; only two come from `ਕੰੜ`. Stage 10 correctly preserves that observation
instead of declaring it equivalent to `kaur`. Establishing such equivalence is
the job of the later evidence-backed variant stage.
