# Data contracts

Upnaam's public inputs are parsed name records and accepted cross-source links.
Raw electoral, ration, and land records remain outside this repository.

## Punjab elector rows

The Punjab person-level stage uses the frozen Dataverse version 25.0 roll and
the same-length Indicate transcription artifact. It validates exact equality
of the 11 native fields duplicated across the two sources before joining by
zero-based source-row order. It rejects a missing row, extra row, reordered
row, or changed native field. The complete assumptions and output schema are
documented in [Punjab elector artifact](punjab-electors.md).

The roll's own `id` is neither complete nor unique. The stage never drops or
coalesces rows by that field; it creates a source-revision-qualified key from
the validated source-row position and retains the original ID separately.

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
- Every recorded-surname row carries the immutable `resolver_revision` that
  selected its state-position rule.
- A native surname can remain resolved when its independent Latin token cannot
  be aligned; the Latin and ASCII fields stay null and carry an explicit
  transliteration status.
- `surname_provenance` is `written_first_token` or `written_final_token` for a
  positional selection and names an external source only for a documented
  linked-record operation.

## Elector-row interface

`resolve_electors` requires exactly one row per source-qualified `elector_id`.
The identifier must be a unique nonempty string. `state` must be lowercase and
stripped; `name` may be missing, in which case the resolver abstains. Extra
input columns are accepted but ignored by `resolver-v1`.

The output preserves row count, order, identifier, state, and raw name. It adds
the nullable normalized recorded-surname token, its exact raw substring,
selected position, provenance, abstention fields, `normalization_revision`,
and `resolver_revision`. The interface does not infer family surnames,
households, token types, caste, or a calibrated confidence score.

## Resolver policy

`src/upnaam/resolver.json` is the packaged source of truth for the resolver
revision, supported states, and first-versus-final token position. The resolver
never guesses a state policy from the name string. Unsupported states emit
`abstained = true`, `abstention_reason = unsupported-state`, and null surname
fields.

The aggregate state output preserves one input row as one output row. Its
`weight` remains `n_times`; it is not expanded into synthetic elector rows.

The linked-record output standardizes source sex labels to `female`, `male`,
or `unknown` solely for stratified diagnostics. The accepted-link artifact
retains the source-specific value.
