# Telangana elector artifact

Telangana is the first state resolved by corroboration rather than position. Its English
rolls print surname-first and surname-last names side by side within one part ("etham
jayamma" beside "kavita namala"), so no position rule fits, and `resolver-v1` lists no
Telangana position. The adapter (`upnaam resolve-electors --state telangana`) uses
`upnaam.corroboration` instead. The saved full-roll artifact records
`corroboration-v1` and `telangana-elector-resolver-v2`.

## Source

`electors.parquet` from `parse_searchable_rolls/scripts/telangana_english/parse.py`: the
English edition of every 2017 SSR and 2018 draft part in the PDF corpus
(doi:10.7910/DVN/OG47IV), one row per printed elector box with EPIC, name, relation type
and name, house number, age, sex, the DELETED stamp, section, page and roll component,
validated part by part against the cover page. Only active electors are resolved: the
mother roll plus the supplement's additions, minus the electors stamped deleted.

`elector_id` is `og47iv-telangana-english-2017:<filename>:<number>`; EPICs repeat, so they
are kept as `source_elector_id` only.

## Evidence

Electors at one house number in one part form a household (`household_id`,
`household_size`). For each elector the candidates are the content tokens of the written
name (three letters or more; not a prefix honorific, a name particle such as `md`,
`sheikh`, `syed` or `abdul`, or a null token) that are corroborated by:

| `surname_evidence` | meaning |
| --- | --- |
| `household_and_relation` | shared with a co-resident and carried by the relation name |
| `household` | shared with a co-resident |
| `relation` | carried by the relation name |

Ties inside a rung go to the rightmost token (a position rule, where a state has one,
would break them instead). Reddy, rao, singh and kumar are surnames people go by and are
never demoted in favour of a rarer token. Names with no corroborated token abstain with
`no-evidence`; consumers decide whether a positional guess is acceptable for their use.

Spellings within a household may differ by a slip. Two tokens count as one name when they
are within the longer token's edit slack: exact only under four letters (ram / rao); one
edit at four to six letters and only a vowel change or an aspiration `h` (begam / begum,
gaud / goud, sing / singh; never rani / ravi, rajesh / ramesh); one edit of any kind at
seven to nine; two at ten or more. The household's majority spelling is recorded as
`surname_source_normalized`; the elector's own spelling stays in `surname_raw`.

## Confidence

`surname_confidence` is a within-roll agreement diagnostic, not calibrated surname
accuracy. For a corroborated token it
is the agreement between the two evidence sources where both exist: household picks that
the relation name also carries, over household picks that had any relation-shared token.
For a position-rule pick it would be the share of corroborated surnames sitting in that
position, which is what the rule scores here. The audit JSON (`--audit`) records the
evidence counts, the position of corroborated surnames, and the confidence table.

On the full roll: 24,592,470 active electors in 8,505,737 households; 16,394,076 (66.7%)
resolved by corroboration (4,236,582 household and relation, 9,625,649 household only,
2,531,845 relation only); 8,198,394 abstained: 8,192,933 with `no-evidence` and 5,461 with
`no-eligible-token`. Where a household
pick could be checked against the relation name the two agreed in 95.9% of cases.
Corroborated surnames sit last 58.6%, first 39.9%, middle 1.5% of the time, which is the
mixed convention in numbers and why a position rule was never an option.

## Not done here

No family-name propagation beyond the shared token, no relation-type model (father versus
husband transmission), no canonicalization across households. Those belong to the
reconciliation stage.

## Instate handoff

Use `name_tables.py lastnames-upnaam --surnames <artifact> --lang telugu` to
count the selected Latin tokens. The final artifact recovers 398,675 strings and
16,394,076 selected occurrences. Instate 3.4 replaces the older fallback input,
which contained 747,473 strings and 24,586,452 occurrences, with this upnaam
handoff. Its common national cell filter retains 16,091,519 Telangana
occurrences, and the training and lookup artifacts reconstruct that total
exactly.
