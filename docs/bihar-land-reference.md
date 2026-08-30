# Bihar land-record reference labels

This stage treats the official Bihar land record as the preferred transcription
for an already-linked elector. The source is unusually valuable because a
landholder has a strong incentive to have the registered name written
correctly. It is therefore Upnaam's highest-quality Bihar reference source.

The source still contains a full name, not an explicit surname field. The
target is consequently precise: **the final eligible token in the official
land-side name under Upnaam's declared Bihar rule**. It is a reference surname
for name-resolution research, not a claim about a legal or hereditary surname.

## Source tables

The local Shekhpura land-owner table contains 127,449 unique accounts and the
local electoral table contains 467,304 rows. The upstream pilot retained 4,387
unique one-to-one account/elector links after exact comparison of normalized
block, complete person name, and complete relative name, followed by an
electoral-age restriction of 18–110. That is 3.4% of land accounts.

Actual linked strings include:

| Land name | Land relative | Roll name | Roll relative |
| --- | --- | --- | --- |
| `मथुरा साव` | `रामेश्‍वर साव` | `मथुरा साव` | `रामेश्वर साव` |
| `शंकर  पासवान` | `अधिक पासवान` | `शंकर पासवान` | `अधिक पासवान` |
| `युगेश्‍वर यादव` | `रामखेलावन यादव` | `युगेश्वर यादव` | `रामखेलावन यादव` |

The frozen link artifact has one row per land account and unique `link_id`,
`roll_id`, and `external_id`. It reports 1,533 female, 2,845 male, and 9
unknown-sex roll rows. The source snapshots do not encode a collection date in
the linked artifact; this remains an open provenance question.

## Join contract

Upnaam does not rebuild or broaden the person linkage.

```text
LEFT    accepted Bihar land links       key: link_id       unique: 4,387/4,387
RIGHT   same row's land transcription   key: external_id   unique: 4,387/4,387
ROLL    recovered electoral row         key: roll_id       unique: 4,387/4,387
CARD    1:1
OUTPUT  exactly 4,387 rows
```

The upstream comparison normalizer removed zero-width marks, brackets, and a
list of honorific strings before exact matching. It removed those strings
wherever they occurred, not just as prefixes. Upnaam does not reuse that
normalizer for surname selection. It applies `normalization-v1` and the public
final-token rule to the untouched land and roll names.

A proposed independent linkage withholding the elector's own name was tested
and rejected. Exact block, full relative name, relation type, and land
mouza-to-roll-location agreement produced 2,696 nominally unique one-to-one
pairs, but only 289 (10.7%) agreed on the held-out full name. Relatives are
shared across siblings and do not identify the elector. Those pairs are not
labels and are not written by the pipeline.

## Label rule and recode ledger

The source-to-reference decisions are:

| Land result | Roll result | Reference status | Reason |
| --- | --- | --- | --- |
| Final token selected | Same normalized final token | `accepted` | `land_and_roll_surname_agree` |
| Final token selected | Roll abstains | `accepted` | `land_record_adds_reference_surname` |
| Final token selected | Different roll final token | `excluded` | `land_roll_position_conflict` |
| Land abstains | Any | `abstained` | `land_surname_unresolved` |

The mandatory source-to-derived crosstab is:

| Land positional result | Roll selected | Roll single-token abstention |
| --- | ---: | ---: |
| Selected | 4,366 | 1 |
| Single-token abstention | 0 | 20 |

No title or sex-marker list is used after token selection. `Devi`, `Kumari`,
`Rani`, `Singh`, `Kumar`, and similar strings remain eligible when they occupy
the final position. The one selected-token conflict is preserved rather than
resolved by intuition: roll `प्रेमलता कुमारी`, land `कुमारी प्रेमलता`.

## Output dictionary

One restricted output row represents one accepted upstream land-account to
elector link, whether or not it yields a reference label.

| Field | Type | Universe and missingness | Meaning and provenance |
| --- | --- | --- | --- |
| `link_id` | string | All 4,387; complete and unique | Standardized accepted-link ID |
| `roll_id` | string | All; complete and unique | Electoral identifier recovered upstream |
| `land_account_no` | string | All; complete and unique | Official land account number |
| `roll_name_raw` | string | All; complete | Untouched electoral name |
| `land_name_raw` | string | All; complete | Untouched official landholder name |
| `roll_surname_raw` | string | 4,366 selected; 21 null | Exact roll token under the Bihar final-token rule |
| `roll_surname_source_normalized` | string | Same universe as roll raw token | `normalization-v1` comparison form |
| `land_surname_raw` | string | 4,367 selected; 20 null | Exact land token under the Bihar final-token rule |
| `land_surname_source_normalized` | string | Same universe as land raw token | `normalization-v1` comparison form |
| `reference_surname_raw` | string | 4,366 accepted; 21 null | Preferred land-side token after conflict handling |
| `reference_surname_source_normalized` | string | Same universe as reference raw token | Normalized reference label |
| `reference_label_status` | string | All; complete | `accepted`, `abstained`, or `excluded` |
| `reference_label_reason` | string | All; complete | Stable rule outcome listed above |
| `reference_provenance` | string | Accepted labels only | `land_record` |
| `reference_position` | string | Accepted labels only | `last` |
| `relation_type` | string | 8 null in source | Roll relationship field; not used to select surname |
| `sex` | string | 9 null in source | Standardized roll sex; used only for coverage audit |
| `full_name_normalized_agreement` | boolean | All; complete | Exact comparison under `normalization-v1` |
| `linkage_basis` | string | All; complete | Frozen upstream one-to-one linkage design |
| `normalization_revision` | string | All; complete | `normalization-v1` |
| `reference_revision` | string | All; complete | `bihar-land-reference-v1` |

The restricted artifact is typed Parquet. Only aggregate diagnostics are
committed publicly.

## First run

| Outcome | Rows |
| --- | ---: |
| Accepted reference labels | 4,366 |
| Land and roll final token agree | 4,365 |
| Land record adds a label after roll abstention | 1 |
| Land-side positional abstention | 20 |
| Excluded positional conflict | 1 |
| Distinct normalized reference surnames | 78 |

The land-added case is roll `श्री देवी` and official land name `कुमारी देवी`,
which supplies reference token `देवी`. The 64 accepted raw-token differences
are mostly Unicode formatting distinctions such as `सिन्हा`/`सिन्‍हा`; their
`normalization-v1` forms agree.

Run locally with:

```console
upnaam labels-bihar-land data/derived/links/bihar_land.parquet \
  data/derived/reference/bihar_land_labels.parquet \
  --audit data/audit/bihar_land_reference.json \
  --summary data/audit/bihar_land_reference.csv \
  --manifest data/manifests/bihar_land_reference.json
```

The manifest fingerprints the source links and every requested output and records
the linkage, normalization, reference-label, and surname-rule revisions. No cloud
query, fuzzy linkage, LLM, or manual surname annotation is used.
