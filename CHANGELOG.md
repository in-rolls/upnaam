# Changelog

All notable changes to Upnaam will be documented here.

## Unreleased

- Add the calibrated full J&K Urdu profile. Preserve 4,608,102 active assembly
  records, select 970,947 corroborated native occurrences, and apply the shared
  27,221-pair map to all 4,399 selected token types without changing native
  evidence or abstentions.

- Add optional local Urdu romanization after native corroboration, preserving
  abstentions, letter distinctions and null confidence. Hindi and Urdu share
  map validation and record the supplied map's hash.

- Add an audited J&K Hindi inventory handoff with exact native-script evidence,
  explicit abstentions and no inferred Latin spellings. Share inventory validation
  with the English adapter.

- Add a hash-verified J&K English inventory handoff with active assembly filtering,
  explicit relationship mapping, exact spelling corroboration and null confidence.

- Bind elector input and output paths as SQL parameters so filenames containing
  apostrophes work throughout surname artifact creation.

- Keep Latin normalization unavailable when a selected token contains U+FFFD,
  preserving the damaged source instead of manufacturing a shorter spelling
  (`normalization-v2`).

- Retain the sole usable token beside explicit initials in Karnataka resolver v4,
  with distinct fallback provenance, null confidence, and corroboration precedence.

- Add a Karnataka elector adapter with native/Latin name provenance and
  household isolation for missing zero house numbers.

- Add manifest-verified, read-only targeted SQLite queries over multipart gzip
  archives without materializing the decompressed database.
- Add streaming member and household counts by normalized written-final token
  over Bihar ration-card rosters.
- Add a generic edit-neighbor proposal command that records frequency and
  thresholds but cannot create canonical mappings.
- Add grouped written-final-token counts over distinct official Bihar land-name
  strings, including explicit terminal-notation diagnostics.
- Add a separate Bihar land inferred-surname aggregate that scans left across
  exact `एव`/`एवं` connectors and repeated approved administrative suffixes,
  with separate immediate and chain-adjustment counts.
- Define the recorded-surname and family-surname evidence contracts.
- Add deterministic normalization and explicit surname candidate rules.
- Reuse accepted Bihar land and Rajasthan ration-card links.
- Add token alignment, edit evidence, linked-name segmentation, and abstaining
  surname resolvers.
- Add full weighted diagnostics for Bihar, Rajasthan, Maharashtra, and Punjab.
- Add a row-preserving Punjab elector resolver using the validated Indicate
  native/Latin transcription artifact.
- Replace the numbered research scripts with a package-oriented CLI.
- Separate raw, source-normalized, Latin-normalized, and canonical surname
  representations with explicit mapping status and provenance.
- Replace global spelling clusters with directed anchor reconciliation that
  records all candidates and preserves supported forks as ambiguity.
- Add a surname-only Rajasthan evidence adapter over existing accepted T1/T2
  ration links, with no new person linkage or cloud query.
- Add stable canonicalization reasons and store the exact support and similarity
  gates in candidate and decision artifacts.
- Retain complete-link clustering only as a developmental research comparator.
- Add typed Bihar official-land reference labels over the frozen 4,387 exact
  one-to-one Shekhpura links, including positional abstention and conflict
  reasons.
- Reject and document a name-withheld relative/location linkage whose held-out
  full-name agreement was only 10.7%.
- Add typed provisional-gold Rajasthan ration reference labels over the frozen
  T1/T2 links, with final-token selection, explicit abstention, and exclusion
  of nonunique ration-member links.
