# Version 1 rules and assumptions

This page freezes the rules used by the unreleased baseline. A rule change must
change the resolver revision and rerun the evaluation.

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
6. If at least two eligible tokens remain, the final eligible token is the
   baseline recorded surname. If one remains, abstain with
   `single-token-name`. If none remains, abstain with `missing-name` or
   `no-eligible-token`.
7. `Devi`, `Kumari`, `Kaur`, `Begum`, `Khatun`, `Singh`, and `Kumar` are not
   pretyped or excluded. If one is the final eligible token, the baseline
   selects it.
8. The first eligible token remains a competing positional candidate. A token
   appearing in a relative name is diagnostic support only; it does not replace
   the written final-token baseline.

The four `instate` tables contain Roman-script aggregate name pairs, not
elector-level records. Their `n_times` field weights every reported diagnostic.
They cannot support sex, household, or relation-type estimates.

## State position

Upnaam does not assume one order for every state, but the unreleased resolver
does not switch orders automatically. A state-specific rule requires a
declared diagnostic threshold and approval before implementation.

The first full pass finds that Maharashtra's first candidate appears in the
relative name much more often than its last candidate. This is evidence against
the current final-token baseline for Maharashtra, not authorization to change
the rule. Maharashtra results remain provisional pending a decision on a
surname-first rule.

## Linked records

- Rajasthan reuses exactly the existing `milaan_raj` T1 and T2 person links.
  It rejects T3 and never searches for new matches.
- Bihar reuses the 4,387 accepted Shekhpura land links. Those links required
  exact normalized elector and relative names, so they are excluded from edit
  and omission learning.
- Bihar ration data is not used because no local bulk roster was found. Upnaam
  makes no portal, GCP, or other cloud query.
- A linked record can split a one-token roll name only when the linked final
  eligible token is an exact suffix of the untouched roll name and at least two
  alphabetic characters remain before it. This produces recorded-surname
  provenance `ration_card_segmentation` or `land_record_segmentation`.
- Rajasthan person assignment required equality of the complete name skeleton.
  It therefore cannot reveal a genuinely additional ration-side surname.
  Under the accepted links, `family_surname` always abstains.

## Edit evidence and variants

- Token substitutions are learned only from non-exact Rajasthan T2 links whose
  token alignments contain no gaps. A spacing difference such as
  `मोहनसिंह`/`मोहन सिंह` is not spelling-variant evidence.
- A variant edge requires at least two accepted linked pairs and normalized
  Levenshtein similarity of at least 0.75.
- Clusters use complete-link direct evidence. `A-B` and `B-C` do not merge all
  three unless `A-C` also has an accepted edge.
- Canonical forms are cluster medoids with support and lexical tie-breaks.
- Thresholds and resolution scores are not probabilities or calibrated
  confidence values.

## Not implemented in the baseline

No household surname propagation, father-versus-husband transmission model,
automatic state-order switch, English name parser, caste inference, or manual
surname annotation is used.
