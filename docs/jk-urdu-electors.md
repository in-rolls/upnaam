# J&K Urdu elector handoff

`upnaam resolve-jk-urdu` converts instate's audited 2018 Urdu inventory into
the same restricted elector and surname artifacts as the Hindi and English
adapters.

```sh
upnaam resolve-jk-urdu inventory.parquet source_audit.json output_directory \
  --romanization-map urdu_map.json
```

The output directory must be new. The command verifies parser provenance,
inventory and PDF hashes, unique entry keys, source identities, activity flags
and per-part counts. It preserves every active assembly record, including
records with missing names, and excludes inactive and NPR records. Its four
outputs are `electors.parquet`, `surnames.parquet`, `SCHEMA.json` and
`audit.json`. They contain person-level records and remain restricted local
artifacts.

The adapter selects a profile from the parser hashes in the source audit. The
current complete handoff uses `promote_jk_urdu.py`, source revision
`jk-urdu-2018-calibrated`, native resolver v3 and mapped resolver v4. The older
Arial and Nastaleeq profiles remain readable for reproducibility.

The enriched full-roll export uses `build_jk_rolls.py` and an explicit
`demographic_enrichment` audit record. Its separate source revision is
`jk-urdu-2018-demographics`, with resolver v5 for native and mapped outputs.
Recovered house identifiers can supply household corroboration, so this profile
must be evaluated separately from the calibrated baseline below. Native names,
source identities, activity flags, and the row universe remain unchanged.
Instate documents the full electoral-roll schema and demographic validation in
`model_training/JK_2018_ROLLS.md`.

Accepted names must be NFKC-normalized Arabic-script text without an extraction
issue. Father, mother and husband labels provide relative evidence; unknown
labels do not. Numeric house zero supplies no household evidence. Tokens retain
diacritics and distinguish Urdu letter variants. Initials, mixed scripts,
numeric tokens, punctuation and the explicit title list cannot corroborate a
selection. No position rule is applied.

Household and relative evidence may select a written token. Conflicting or
missing evidence abstains. Shared given names can also corroborate, so selection
does not establish a hereditary surname. Relative-only suggestions remain
separate from recorded selections. Confidence remains null.

The final calibrated inventory contains 4,690,023 rows: 4,617,281 active,
4,608,102 active assembly and 9,179 NPR. Its source ledger covers 6,014
row-bearing PDFs after redundant copies are excluded. The recovery accepts
2,315,587 own-name fields and 3,401,536 relative-name fields while preserving
every source identity, event field and record key.

The calibrated handoff preserves all 4,608,102 active assembly records. It
selects 970,947 corroborated native occurrences from 4,399 distinct tokens and
abstains on 3,637,155 records. The calibrated word-vote gate matched 1,259 of
1,322 hidden word controls exactly (95.23%). That diagnostic measures source
transcription, not surname accuracy.

`--romanization-map` accepts a local JSON object from eligible Urdu tokens to
single ASCII Latin tokens, for example `{"ڈار": "dar"}`. Mapping runs only
after native selection and cannot rescue an abstention or change native
evidence. Unmapped selections keep their native token and null Latin fields.
Duplicate or invalid keys and values fail before output creation. The audit
records the map hash and mapped and unmapped counts.

The calibrated baseline map contains 27,221 native/Latin pairs and covers all 4,399 selected
token types. It maps all 970,947 selected occurrences. The map SHA-256 is
`8f1c8f8211f001675678354cc1736c14b4a05ff9a971ba390c039e43fbc892e7`.
Format checks and model agreement do not establish transliteration accuracy;
model-only entries remain silver annotations.

The Hindi and Urdu editions share 693,201 exact one-to-one card identities.
Upnaam preserves each source handoff independently. Instate performs the
cross-edition reconciliation when it builds national counts, so consumers must
not add the two handoff totals directly.

## Retained Instate inputs

The accepted input is now `instate/data/jk_2018/urdu/inventory.parquet`,
with `source_audit.json` beside it. The accepted output is the adjacent
`handoff/` directory. Instate's `make verify-jk` checks these files against its
committed checksum list. Historical recovery paths in the source audits refer
to `/Volumes/Staging/instate/jk_recovery_archive_20261010/`.

Run from the Upnaam repository, with a new output directory:

```sh
uv run upnaam resolve-jk-urdu \
  ../instate/data/jk_2018/urdu/inventory.parquet \
  ../instate/data/jk_2018/urdu/source_audit.json \
  /tmp/jk-urdu-verified \
  --romanization-map ../instate/data/jk_2018/urdu/romanization_map.json
```

To use the verified demographic export with resolver v5:

```sh
uv run upnaam resolve-jk-urdu \
  ../instate/data/jk_2018_rolls_final/urdu_enriched_inventory.parquet \
  ../instate/data/jk_2018_rolls_final/urdu_enriched_audit.json \
  ../instate/data/jk_2018/urdu/enriched_handoff \
  --romanization-map ../instate/data/jk_2018/urdu/romanization_map.json
```

Use a new output directory for each run. This is a separate candidate source
revision; it does not replace the calibrated release handoff above.

The completed enriched handoff preserves 4,608,102 active assembly records and
selects 1,371,913 native tokens, leaving 3,236,189 records abstained. The expanded
27,282-pair map renders 1,371,162 selections in Latin; 751 selected occurrences
remain unmapped. These are coverage counts, not surname or transliteration
accuracy estimates. Instate records the result in
`model_training/jk_2018_enriched_urdu_audit.json`.

The expanded map adds 61 conservative readings from a three-pass Muse Spark
Contributor review of 179 previously unmapped selected types. It changes no
existing mapping or native selection. Its SHA-256 is
`729e257139fc270bce66c72a32844f308051bf847dbfde2e4eda209f87df569c`.
Of the additions, 31 have lexical support and 30 are model-only silver annotations;
repeated model agreement is not a pronunciation-accuracy estimate. Instate's
`model_training/jk_2018_urdu_transliteration_extension.json` records the policy,
controls, provenance and remaining abstentions.

The enriched profile excludes ten exact designation tokens, supported by
dictionary definitions and source-card review, from own-name, relative-name,
and household corroboration: `مسماۃ`, `مسماتہ`, `مشماتہ`, `مسمات`,
`مسماہ`, `مسما`, `مسماتا`, `مسمی`, `شریمتی`, and `شری`. Raw names retain them.
The handoff audit records this list. The calibrated baseline and transliteration
map validation are unchanged. These exclusions address a specific demonstrated
error; they do not establish that every other shared token is a hereditary surname.

The designation meanings are documented by Rekhta for
[Musammat](https://www.rekhtadictionary.com/meaning-of-musammaat?lang=ur),
[Musamma](https://www.rekhtadictionary.com/meaning-of-musammaa), and
[Shrimati](https://www.rekhtadictionary.com/meaning-of-shiriimatii?lang=ur).
Variant spellings were checked against eight original roll cards. Those cards
are development evidence, separate from the demographic extraction holdout.
