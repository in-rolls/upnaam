# Version 1 rules and assumptions

This page freezes `resolver-v1`. A rule change must change the resolver
revision and rerun the evaluation. The machine-readable state policy is
`src/upnaam/resolver.json`.

## Recorded surname baseline

1. Preserve the source name exactly.
2. Normalize with Unicode NFC, remove zero-width formatting characters,
   replace danda marks with spaces, collapse whitespace, and case-fold. Do not
   transliterate.
3. Split on whitespace. Preserve internal hyphens, apostrophes, and other
   punctuation.
4. Ignore only these exact tokens when they occur consecutively at the start
   of a name: `श्री`, `श्रीमती`, `सुश्री`, `डॉ`, `shri`, `sri`, `srimati`,
   `smt`, `mr`, `mrs`, `ms`, and `dr` (Roman tokens are case-insensitive).
5. A candidate token must contain at least two alphabetic characters.
   One-character initials and tokens with no letters remain in the raw record
   but are ineligible.
6. If at least two eligible tokens remain, select the eligible token at the
   state-configured position. If one remains, abstain with `single-token-name`.
   If none remains, abstain with `missing-name` or `no-eligible-token`.
7. `Devi`, `Rani`, `Kumari`, `Kaur`, `Begum`, `Khatun`, `Singh`, and `Kumar`
   are not pretyped or excluded. If one occupies the configured position, the
   resolver selects it as the written surname. A separate evidence stage may
   later report a fuller family name without overwriting this result.
8. The first and final eligible tokens remain competing positional candidates.
   A token appearing in a relative name is diagnostic support only; it does not
   override the configured position for an individual record.

The four `instate` tables contain Roman-script aggregate name pairs, not
elector-level records. Their `n_times` field weights every reported diagnostic.
They cannot support sex, household, or relation-type estimates.

The Punjab person-level stage applies the same final-token rule to the native
Gurmukhi roll name. Its Indicate transcription supplies an alternate script,
not evidence for choosing a different surname. The Latin token is copied only
at the selected native position and only when complete token counts agree.
Token-count disagreement leaves the Latin and ASCII fields null. Full source,
join, key, and schema rules are frozen in
[Punjab elector artifact](punjab-electors.md).

## State position

`resolver-v1` uses only these approved positional rules:

| State | Selected position |
| --- | --- |
| Bihar | Final eligible token |
| Rajasthan | Final eligible token |
| Maharashtra | First eligible token |
| Punjab | Final eligible token |

An unsupported state abstains with `unsupported-state`. Upnaam does not infer
name order automatically from an individual record.

The Maharashtra rule was approved after a full pass over 65,876,912 aggregate
name-pair rows representing 83,029,252 weighted records. The first candidate
appears exactly in the relative name for 89.20% of weighted records, compared
with 65.08% for the final candidate. Among records where first and final differ,
27.19% of all weighted records match only on the first candidate and 3.07%
match only on the final candidate.

Those are exact normalized-token overlaps, not surname labels. For example,
`jadhab asha ashok`/`jadhav ashok` registers as a final-only overlap because
`jadhab` and `jadhav` are not equal. Positional selection never uses fuzzy
matching; supported spelling canonicalization remains a separate stage.

## Linked records

- Rajasthan reuses exactly the existing `milaan_raj` T1 and T2 person links.
  It rejects T3 and never searches for new matches.
- For the Rajasthan person-level reference artifact, the accepted ration-card
  transcription is `provisional_gold`. Its final eligible token is the
  reference even when the roll token differs or the roll rule abstains.
- Ration members linked to multiple elector rows are not adjudicated: every
  associated row is retained but excluded from reference labels.
- Bihar reuses the 4,387 accepted Shekhpura land links. Those links required
  exact normalized elector and relative names, so they are excluded from edit
  and omission learning.
- On those accepted links, the official land-side name is the preferred Bihar
  reference transcription. The reference surname is its final eligible token.
  A land/roll positional conflict is excluded; the land record may supply a
  reference when the roll positional rule abstains.
- Bihar ration data is read locally from the restricted Harvard Dataverse
  SQLite corpus through the compressed-SQLite adapter. The complete pass emits
  grouped written-final-token counts only; it makes no portal or GCP query and
  retains no person or household identifiers.
- A linked record can split a one-token roll name only when the linked final
  eligible token is an exact suffix of the untouched roll name and at least two
  alphabetic characters remain before it. This produces recorded-surname
  provenance `ration_card_segmentation` or `land_record_segmentation`.
- Rajasthan person assignment required equality of the complete name skeleton.
  It therefore cannot reveal a genuinely additional ration-side surname.
  Under the accepted links, `family_surname` always abstains.

## Normalization and canonicalization

The surname representations are separate fields. `surname_raw` is the exact
selected substring; `surname_source_normalized` is its same-script comparison
form; `surname_latin_raw` is an exact source or validated aligned Latin token;
`surname_latin_normalized` is a deterministic ASCII comparison form; and
`surname_canonical` is the result of an ambiguity-preserving anchored
reconciliation. No earlier representation is overwritten.

Edit similarity and evidence play different roles:

- The Rajasthan pilot selects the final eligible Devanagari token independently
  on both sides of an existing accepted T1/T2 link. The ration spelling is a
  provisional anchor, not a gold label.
- Levenshtein similarity is an eligibility feature. String similarity alone
  does not supply the linked-record evidence or decide the canonical anchor.
- A candidate currently requires aggregate support of at least two and
  normalized Levenshtein similarity of at least 0.75. Both gates are stored in
  the artifact and are pilot assumptions, not universal linguistic thresholds.
- Exactly one eligible anchor is accepted. Two or more eligible anchors produce
  `ambiguous` and a null canonical surname, regardless of candidate rank.
- With no eligible anchor or no decision row, the normalized token remains
  unchanged with `canonicalization_status = identity_unmapped`. The reason
  distinguishes `no_supported_anchor` from `no_reconciliation_decision`.
- A missing comparison form is `normalization_unavailable`; it is not treated
  as an abstention from written-surname selection.
- Thresholds and resolution scores are not probabilities or calibrated
  confidence values.

Complete-link clustering remains a research comparator for earlier variant
diagnostics. It is not the canonicalization method or public package API.

The Bihar land written-token vocabulary applies the same literal final-token
rule to one row per distinct official ryot full-name string. It is descriptive,
not a canonical mapping. A separate inferred vocabulary applies the approved
`bihar-land-record-suffix-inference-v1` rule: after an exact match to one of 10
declared terminal administrative notations, it selects exactly the preceding
eligible token. It does not fuzzy-match, recurse, or add another blacklist.
Direct-written and suffix-adjusted support remain separate count columns.

## Not implemented in the baseline

No household surname propagation, father-versus-husband transmission model,
automatic state-order detection, English name parser, caste inference, or
manual surname annotation is used. The Punjab person-level artifact likewise
does not use the relative-name or household fields to alter its final-token
selection.
