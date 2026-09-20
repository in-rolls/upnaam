# Lakshadweep 2026 elector surnames

`resolve-electors --state lakshadweep` resolves surnames from the romanized Malayalam SIR Final Roll 2026. It retains one row per active elector, including abstentions, in the shared elector-artifact structure, including native Malayalam fields.

```sh
upnaam resolve-electors /path/to/lakshadweep_2026.parquet /path/to/lakshadweep_2026_surnames.parquet --state lakshadweep --audit /path/to/lakshadweep_2026_surnames_audit.json
```

The name fields are `elector_name_en` and `father_or_husband_name_en`. The original Malayalam fields remain beside them. Unlike Telangana, the printed house name (`house_no_en`) supplies surname evidence. Household identity uses the original house field within a PDF part, preserves vowel marks, and ignores punctuation and case. The sort uses this same identity so serial-order interleaving cannot split a household.

The September 2026 build contains 57,618 active rows and 43,229 nonempty household keys. It selects 5,026 source surnames and abstains on 52,592 rows; one selected token has no Latin romanization. No position-only fallback is applied. Full evidence counts are in `data/audit/lakshadweep/lakshadweep_2026_surnames_audit.json`.

The reported corroboration confidence is 117/136 (86.0%) agreement with relation evidence among checkable household picks. It is not an independently validated accuracy estimate, especially for house-only selections. Repeated given names and generic house words can survive the evidence rule.

The source parse has 58,528 boxes across 64 parts. All ending serials reconcile, but active counts match in only 35 parts: 57,618 parsed versus 57,607 printed. OCR and deletion-status errors remain. The parsed-roll deposit includes the 64 PDFs, checksums, per-part audit and a crop sample. Resolver revision: `lakshadweep-elector-resolver-v2`.

The September 11 instate handoff check reproduced all 1,777 saved Latin count
strings and their 5,025 occurrences exactly. The shared support filters retain
381 surname-state cells and 3,312 occurrences in the 3.3 lookup.
