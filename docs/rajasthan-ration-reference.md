# Rajasthan ration-card reference labels

This stage treats the official ration-card name on an accepted `milaan_raj`
person link as a `provisional_gold` transcription. The source pipeline reports
roughly 15.9 million cards and 62.8 million members with explicit household
relationships. Its wrong-geography placebo estimates false-discovery rates of
0.140% for T1 and 0.111% for T2 links.

That evidence supports treating the linked person transcription as nearly
gold for this pass. The roster still stores a full name rather than an explicit
surname. The target is therefore narrower: **the final eligible token in the
ration-side name under Upnaam's Rajasthan rule**. The output is a reference for
name-resolution research, not a legal or hereditary-surname adjudication.

## Source artifact

The input is the existing standardized artifact
`data/derived/links/rajasthan_ration.parquet`. One row is an accepted T1/T2
ration-member-to-elector link. It has 1,004,418 rows and 14 columns:

| Field group | Fields | Profile |
| --- | --- | --- |
| Source and tier | `source`, `link_tier` | All Rajasthan; 536,536 T1 and 467,882 T2 |
| Link keys | `link_id`, `roll_id`, `external_id` | 1,004,418 unique roll IDs; 1,003,829 unique ration members |
| Names | roll/ration person and relative raw strings | Person names complete; relation type missing on 209 rows |
| Diagnostics | sex, exact-name and learning flags | Sex missing on 14,043 rows |

Actual beginning and ending rows include:

| Tier | Roll name | Ration name | Roll relative | Ration relative |
| --- | --- | --- | --- | --- |
| T1 | `नानजी` | `नानजी` | `जगजी` | `जगजी` |
| T2 | `सीता राम` | `सीताराम` | `छोटू लाल` | `छोटूलाल` |
| T1 | `रामप्यारी देवी` | `रामप्यारी देवी` | `शंकर लाल` | `मोठाराम` |
| T2 | `श्रवणराम` | `श्रवण राम` | `रामरखाराम` | `रामरख राम` |
| T1 | `विनोद कंवर` | `विनोद कँवर` | `रणवीर सिंह` | `जसु सिंह` |

The source collection is the 2021 Rajasthan PDS roster linked to 2018 electoral
rolls. Upnaam reuses the accepted links and does not query GCP, search for new
people, or rescore T1/T2.

## Unit and key contract

The estimand is one reference outcome per linked elector row.

```text
LEFT    accepted Rajasthan person links   key: roll_id       unique: 1,004,418/1,004,418
RIGHT   linked ration member              key: external_id   unique: 1,003,829/1,004,418
CARD    many electors may point to one ration member in 570 duplicate groups
OUTPUT  exactly 1,004,418 rows; reference_row_id is unique
```

The 570 nonunique ration-member keys cover 1,159 elector rows, with at most
three rows per member. Examples include a single ration `भुरा` linked to roll
forms `भेरा`, `भूरा`, and `भेरू`. Upnaam cannot know which elector is correct,
so it retains and excludes every row in each group. It never chooses the
closest spelling.

## Label rule and recode ledger

The source-to-reference decisions are:

| Link and ration result | Reference status | Reason |
| --- | --- | --- |
| Ration member appears on one link; final token selected | `accepted` | `ration_final_token_selected` |
| Ration member appears on one link; one-token name | `abstained` | `ration_surname_unresolved` |
| Ration member appears on multiple links | `excluded` | `nonunique_ration_member_link` |

The mandatory source-to-derived crosstab is:

| Status and ration result | Roll abstains | Roll selects | Total |
| --- | ---: | ---: | ---: |
| Accepted; ration selects | 217,333 | 257,254 | 474,587 |
| Abstained; ration abstains | 470,392 | 58,280 | 528,672 |
| Excluded; ration selects | 244 | 255 | 499 |
| Excluded; ration abstains | 629 | 31 | 660 |

Among the 257,254 accepted rows where both sides select a token, 230,503
normalized tokens agree and 26,751 differ. Unlike the Bihar land stage, a
disagreement does not exclude the row: the ration token is the reference under
the `provisional_gold` assumption.

No honorific, sex-marker, or family-name vocabulary is applied after positional
selection. `Singh`, `Kumar`, `Devi`, `Rani`, `Ram`, `Lal`, and other eligible
final tokens remain labels. This simple rule deliberately accepts the risk that
whitespace splitting turns a compound given name such as `गरीबाराम` into
`गरीबा राम`, yielding `राम` as the reference token.

## Output dictionary

One restricted output row represents one accepted upstream elector-link row,
including abstentions and exclusions.

| Field | Type | Universe and missingness | Meaning and provenance |
| --- | --- | --- | --- |
| `reference_row_id` | string | All; complete and unique | Source-qualified output row key |
| `source_link_id` | string | All; complete; 1,003,829 distinct | Upstream link ID; repeats when a ration member links to multiple electors |
| `roll_id` | string | All; complete and unique | Linked electoral identifier |
| `ration_member_id` | string | All; complete; 1,003,829 distinct | Card number plus member number |
| `roll_name_raw` | string | All; complete | Untouched electoral name |
| `ration_name_raw` | string | All; complete | Untouched official ration-card name |
| `roll_surname_raw` | string | 315,820 selected | Exact roll token under the final-token rule |
| `roll_surname_source_normalized` | string | Same universe as roll raw token | `normalization-v1` comparison form |
| `ration_surname_raw` | string | 475,086 selected | Exact ration token under the final-token rule |
| `ration_surname_source_normalized` | string | Same universe as ration raw token | `normalization-v1` comparison form |
| `reference_surname_raw` | string | 474,587 accepted | Preferred ration token after duplicate-link handling |
| `reference_surname_source_normalized` | string | Same universe as reference raw token | Normalized reference label |
| `reference_label_status` | string | All; complete | `accepted`, `abstained`, or `excluded` |
| `reference_label_reason` | string | All; complete | Stable rule outcome listed above |
| `reference_provenance` | string | Accepted labels only | `ration_card` |
| `reference_standard` | string | All; complete | `provisional_gold` |
| `reference_position` | string | Accepted labels only | `last` |
| `link_tier` | string | All; complete | Upstream T1 or T2 |
| `relation_type` | string | 209 null in source | Father/husband relation; not used for token selection |
| `sex` | string | 14,043 null in source | Original `m`/`f` source value |
| `sex_group` | string | All; complete | `female`, `male`, or `unknown` for aggregate auditing |
| `name_exact_upstream` | boolean | All; complete | Upstream complete-name diagnostic |
| `selected_surname_normalized_agreement` | nullable boolean | Both sides select | Whether normalized positional tokens agree |
| `ration_member_link_count` | int64 | All; complete | Number of input elector rows for the ration member |
| `linkage_basis` | string | All; complete | Frozen T1/T2 linkage design |
| `normalization_revision` | string | All; complete | `normalization-v1` |
| `reference_revision` | string | All; complete | `rajasthan-ration-reference-v1` |

The row-level Parquet, JSON audit, and manifest are restricted local artifacts.
Only the aggregate CSV is committed publicly.

## First run

| Outcome | Rows |
| --- | ---: |
| Accepted reference labels | 474,587 |
| Ration-side positional abstention | 528,672 |
| Excluded nonunique-member links | 1,159 |
| Ration token supplied after roll abstention | 217,333 |
| Accepted token agreements | 230,503 |
| Accepted token disagreements | 26,751 |
| Distinct normalized reference tokens | 2,443 |

Coverage is 35.4% in T1 and 60.8% in T2. This difference largely reflects
whitespace segmentation, so it is not evidence that T2 has better surname
recording. Among accepted rows, the most frequent labels are `सिंह` (104,186),
`राम` (73,189), `देवी` (57,873), `लाल` (45,969), and `कुमार` (41,303).

Run locally with:

```console
upnaam labels-rajasthan-ration data/derived/links/rajasthan_ration.parquet \
  data/derived/reference/rajasthan_ration_labels.parquet \
  --audit data/audit/rajasthan_ration_reference.json \
  --summary data/audit/rajasthan_ration_reference.csv \
  --manifest data/manifests/rajasthan_ration_reference.json
```

The manifest fingerprints the accepted links and every requested output and
records the linkage, normalization, label-standard, duplicate-link policy, and
reference revisions.
