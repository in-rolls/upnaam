# Data contracts

Upnaam's public inputs are parsed name records and accepted cross-source links.
Raw electoral, ration, and land records remain outside this repository.

## Electoral name table

The diagnostic state tables contain `english_name`,
`father_husband_name`, and `n_times`. They are aggregated name pairs, not
elector-level records. Consequently they support weighted position and
relative-name diagnostics but not household or sex-specific estimates.

## Rajasthan person links

Upnaam accepts only person links marked `T1` or `T2` by `milaan_raj`. Each link
must identify one ration-card member and one elector. Upnaam joins the accepted
identifier pairs to the frozen roll and ration household tables; it never
re-scores or broadens the linkage. `T3` links are rejected.

The frozen household tables repeat ration members and contain colliding
elector identifiers. Upnaam does not create a new match to repair these keys.
It recovers the exact roll row selected upstream using the fields emitted by
`milaan_raj`: household ID, name skeleton, exact-name flag, relative-skeleton
flag, sex, and age residual with the frozen median age offset. Recovery must be
one-to-one after identical repeated rows are collapsed.

Because upstream person assignment requires the complete ration and roll name
skeletons to match, these links cannot identify a surname present only in the
ration name. A token present only after ration-side whitespace splitting is
segmentation evidence. It may resolve a suffix already present in the raw roll
string, but it never populates `family_surname`.

## Bihar land links

The Shekhpura pilot links land accounts one-to-one to voter identifiers after
exact normalized elector-name and relative-name matching within block. They are
an exact-match validation source. Because the linkage itself requires the full
names to agree, Upnaam excludes these pairs from edit learning and omission
measurement. The source roll contains duplicated OCR-corrupted voter IDs.
Upnaam therefore recovers raw text by the upstream `(voter ID, normalized
elector name, normalized relative name)` key and requires that key to identify
one unique raw name pair per accepted land account.

## Output invariants

- Raw name strings are never overwritten.
- Normalization is deterministic and does not transliterate.
- Recorded surnames are substrings of the elector's own raw name.
- Family surnames require a named external evidence record.
- Every stage writes its input paths, hashes, row counts, and configuration to
  a manifest.
