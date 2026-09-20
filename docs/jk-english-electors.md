# J&K English elector handoff

`upnaam resolve-jk-english` builds a restricted surname artifact from the
reconciled inventory produced by instate's original English roll parser. The
source covers historical J&K assembly constituencies 047–050 in 2018, now in
Ladakh. It does not represent the full historical state or a current electorate.

```sh
upnaam resolve-jk-english inventory.parquet source_audit.json output_directory
```

The output directory must be new. The command verifies the inventory SHA-256
against `source_audit.json`, each PDF's source hash, Boolean activity flags,
unique elector serials within assembly/NPR scope, event-key provenance, and
per-part inventory and activity counts. It writes the complete directory only
after validation and resolution succeed.

| Output | Meaning |
| --- | --- |
| `electors.parquet` | One prepared row per active assembly elector, including missing-name rows |
| `surnames.parquet` | One selection or explicit abstention per prepared row |
| `SCHEMA.json` | Prepared-field types and the handoff contract |
| `audit.json` | Exclusions, source and code hashes, dependency versions, evidence counts and output hashes |

Source candidates, original relationship labels, house fields and event keys
remain in the prepared artifact. Accepted name fields supply the resolver's
evidence; damaged candidates never replace them. `Father's Name`, `Mother's
Name` and `Husband's Name` map to the corresponding relationships. Other labels,
including `Self`, `Name`, `Son in Law` and `Adopted Son`, provide no relative-name
evidence. Their literal labels remain visible in `relationship_raw`.

Household keys use the PDF filename and house number, preserve numeric
separators, and treat zero as missing. Missing or damaged house numbers cannot
group unrelated rows. Corroboration requires exact normalized spelling. It does
not pool similar spellings, use uncorroborated name positions, or choose between
conflicting household and relative evidence. Relative-only candidates are
reported separately and never enter recorded-name counts. Confidence is null.

In the September 11, 2026 local run, 171,653 inventory rows yielded 169,191 active
assembly rows after excluding 2,440 inactive records and 22 active NPR records.
The handoff retained 39 missing-name rows and withheld 379 relative-name fields.
It selected corroborated tokens for 66,636 rows and abstained on 102,555,
including 812 conflicting-evidence cases. All selected raw tokens occur in the
accepted source name. These checks establish provenance and row preservation;
they do not measure hereditary-surname accuracy. Shared given names remain a
particular concern when interpreting household corroboration.

The source parser's count discrepancies, truncated PDFs and missing closing
controls remain unresolved. The handoff cannot correct those defects. No Urdu
or Hindi names, romanization, national lookup updates or model weights enter this
command. Person-level files remain local; share aggregate checks and hashes.
