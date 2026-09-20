# J&K Hindi elector handoff

`upnaam resolve-jk-hindi` creates a restricted native-script token artifact from
instate's reconciled Hindi inventory for historical J&K AC057–AC080 in 2018.
The source is a historical electoral roll, not full-state or current coverage.

```sh
upnaam resolve-jk-hindi inventory.parquet source_audit.json output_directory
```

The output directory must be new. The command verifies the inventory SHA-256,
parser identity, PDF hashes, event-key provenance, source identities within each
assembly/NPR scope, Boolean flags, and every part's inventory and activity counts.
A repeated serial is allowed only when the source IDs are nonempty and distinct.
Entry-event keys remain unique and supply stable elector IDs, so these cards cannot
overwrite one another or create a household solely through their shared serial.
Inactive and NPR rows are excluded; every active assembly row remains, including
rows with missing or withheld names. Publication of the directory is atomic.

| File | Content |
| --- | --- |
| `electors.parquet` | Prepared active assembly rows, accepted evidence fields, raw candidates and source keys |
| `surnames.parquet` | One native selection or explicit abstention per prepared row |
| `SCHEMA.json` | Prepared-field types and source contract |
| `audit.json` | Counts, exclusions, evidence diagnostics, source/code hashes and dependency versions |

Only parser-accepted Devanagari names supply evidence. A parser issue or unsupported
script withholds the name; a damaged raw candidate never replaces it. Source
candidates remain in `name_source_raw` and `relative_name_source_raw`. The accepted
input fields are retained in `electors.parquet`. The labels `पिता` and `पति` map to
father and husband; other labels supply no relative evidence. Raw labels remain
in the output.

Native tokens retain vowel signs, nukta and other combining marks. Comparisons use
NFC and the package's formatting-mark normalization, with no nearby-spelling merges.
Tokens require two Devanagari letters because vowel signs are marks: the Latin
three-letter rule would exclude राम. Single-letter initials, punctuated or mixed
script tokens, and the explicit title list in `adapters/devanagari.py` supply no
evidence. The title list is a conservative rule, not a learned linguistic model.

Household keys use PDF filename and house number, preserve numeric separators, and
treat zero in either digit script as missing. There is no uncorroborated position
rule. Conflicting household and relationship evidence abstains. Relative-only
candidates remain separate and never feed the recorded selections.

A selected native token appears in `surname_raw` and `surname_source_normalized`.
By default, all Latin name and surname fields, `surname_canonical`, and
`surname_confidence` remain null. A native selection has
`canonicalization_reason=latin_form_unavailable`; an abstention has
`surname_not_selected`. Native relative candidates use the same script.

To attach Latin surname forms, supply a local JSON object whose keys are eligible
native tokens and whose values contain at least two ASCII letters:

```json
{"शर्मा": "Sharma", "कुमार": "Kumar"}
```

```sh
upnaam resolve-jk-hindi inventory.parquet source_audit.json output_directory \
  --romanization-map hindi_romanizations.json
```

The map is applied after native corroboration. It cannot select a new token, change
the supporting evidence, or resolve an abstention. Two native spellings mapped to
the same Latin form still require separate native evidence. Mapped selections fill
`surname_latin_raw`, `surname_latin_normalized` and `surname_canonical`; the canonical
status is `identity_unmapped`, since no spelling reconciliation was performed.
Unmapped selections retain their native token and null Latin fields. Full-name
Latin fields, relative-only candidates and confidence remain unchanged.

Duplicate JSON keys, duplicate normalized native keys, ineligible tokens and
non-ASCII, punctuated, numeric or multiword Latin values fail validation. The audit
records the map SHA-256 and mapped/unmapped selection counts. Format validation
does not establish transliteration accuracy; the caller must evaluate the supplied
spellings. Native strings must not be passed directly to a Latin surname lookup.

Keep source-spelling review separate from Latin spelling conventions. In the
September 12, 2026 J&K diagnostic, Muse Spark 1.3 Contributor flagged `सिहं` as
unusual; the historical map supplied `Singh`, while the independent response
returned literal `Sihan` and listed `Singh` as an alternative. This affects 216,109
selected occurrences and remains unresolved. Omit unresolved entries from a
production romanization map so their Latin fields stay null. A shared candidate
in two corpora is not unique agreement: one corpus can contain several alternatives.
The completed 5,857-token diagnostic is recorded in instate under
`data/jk_recovery/muse_review/hindi_full/`. A candidate map retains 3,503 native
forms where the historical candidate agrees with the independent response and
passes the source-warning and local format rules. Model/corpus agreement is not
verified transliteration accuracy. On six development pages, all 67 inspected
font sequences reproduce literal `सिहं`; none reproduces `सिंह`. This confirms
the inspected source sequence, not the intended conventional name. That token
remains withheld from the candidate map.

The candidate supplies Latin forms for 913,449 selected occurrences and leaves
247,808 selected occurrences unmapped. The complete handoff was checked against
the native artifact: prepared elector files are byte-identical, and every row
preserves its native selection, abstention and supporting evidence. These checks
establish that attaching the map preserves the native evidence; they do not
establish linguistic accuracy or authorize production promotion.

A subsequent check against Google Dakshina's 30,000-word Hindi lexicon found
human-attested exact alternatives for 1,103 retained native forms, covering
856,370 candidate occurrences. Fifty-nine forms covering 1,096 occurrences have other
attested spellings; 2,341 forms covering 55,983 occurrences have no reference
entry. These are lexical-support counts, not an accuracy estimate: the references
are not exhaustive, Wikipedia overlap is not representative of electoral names,
and the earlier models' training exposure is unknown. All three Dakshina splits
were consulted; this audit must not be presented as untouched test evaluation.
The reference files were verified against the publisher's archive. The audit and
provenance are retained in instate; no source corpus or map changed.

Shared given names can satisfy corroboration. These outputs measure written-token
evidence, not hereditary-surname accuracy or a person's identity. Source count
mismatches, page gaps and withheld names remain unresolved. Keep person-level files
local; use the aggregate audit for reproducibility. This command makes no lookup or
model update and uses no external LLM.

The September 12, 2026 identity repair retained four additional source cards with
repeated serials and distinct printed IDs. The corrected handoff contains
2,230,975 active assembly rows, selects 1,161,257 native tokens and abstains on
1,069,718. Two added cards receive selections; two abstain. One existing row gains
exact household evidence from an added card. Of 58,745 withheld own-name fields,
55,143 were missing or flagged by the parser and 3,602 failed the handoff input
policy, mostly because of colons or digits. The English regression rerun preserves
all 169,191 rows and reproduces the prepared and surname files byte for byte.

A convention review of the original 60 differing reference cases passed all 12
synthetic controls. It classified 59 as compatible conventions and one as
uncertain. The reviewed instate candidate changes only `बख्शी` from `bakshi` to
`bakhshi`, supported by both a human-attested alternative and the earlier blind
model answer. Exactly 25 Latin-name occurrences change; native selections,
abstentions and household/relative evidence remain unchanged. This is a reviewed
candidate map change, not a source-corpus or model update. The current handoff is
`data/jk_recovery/hindi_reviewed_candidate/` in instate.
