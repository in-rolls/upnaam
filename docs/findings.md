# Baseline diagnostic findings

These are descriptive results from `resolver-v1`, not accuracy estimates. The
source of truth is `data/audit/evaluation.csv`.

## Four-state aggregate tables

| State | Weighted records | Selected position | Coverage | Single-token share | Selected candidate in relative |
| --- | ---: | --- | ---: | ---: | ---: |
| Bihar | 69,943,602 | Final | 97.42% | 2.58% | 35.13% |
| Rajasthan | 42,680,004 | Final | 32.86% | 67.14% | 7.54% |
| Maharashtra | 83,029,252 | First | 98.27% | 1.73% | 89.20% |
| Punjab | 18,748,931 | Final | 88.89% | 11.08% | 37.57% |

Maharashtra's first and final candidates differ in 98.12% of weighted records.
Among those records, the exact relative-name overlap falls into these cells:

| Overlap | Weighted records | Share of all weighted records |
| --- | ---: | ---: |
| First only | 22,575,921 | 27.19% |
| Final only | 2,546,251 | 3.07% |
| Both | 50,936,959 | 61.35% |
| Neither | 5,405,719 | 6.51% |

The first-only cell is 8.9 times the final-only cell. Exact matching makes this
comparison conservative for first-position variants: `jadhab asha ashok` and
`jadhav ashok`, for example, count as final-only because `jadhab` does not equal
`jadhav`. Candidate selection does not repair that spelling; variant
canonicalization is a separate stage. Rajasthan's low coverage is largely a
tokenization fact in the Romanized aggregate table and motivates the
independent Devanagari linked-record check.

## Accepted external links

Upnaam materialized 4,387 Bihar land links, 536,536 Rajasthan T1 ration links,
and 467,882 Rajasthan T2 ration links. These counts exactly match the accepted
upstream artifacts.

| Accepted links | Written final token | Ration-supported exact suffix split | Abstained |
| --- | ---: | ---: | ---: |
| Bihar land exact links | 99.52% | 0.00% | 0.48% |
| Rajasthan T1 | 32.61% | 3.84% | 63.55% |
| Rajasthan T2 | 30.11% | 37.51% | 32.38% |

The Rajasthan results differ substantially by sex and linkage tier:

| Tier and sex | Written | Exact suffix split | Abstained |
| --- | ---: | ---: | ---: |
| T1 female | 31.54% | 8.92% | 59.54% |
| T1 male | 33.11% | 1.54% | 65.35% |
| T2 female | 34.16% | 16.90% | 48.94% |
| T2 male | 28.36% | 46.49% | 25.15% |

The committed evaluation also reports unknown-sex strata and Bihar land
results by sex. These are coverage and segmentation diagnostics, not accuracy
estimates.

Rajasthan's T2 result demonstrates the value of a second transcription for
spacing: examples include `मोहनसिंह`/`मोहन सिंह` and
`सुनितादेवी`/`सुनिता देवी`. It does not demonstrate omitted family surnames,
because the upstream person link requires equality of the complete name
skeleton. Consequently the current family-surname candidate count is zero.

The earlier complete-link research comparator contains 104,215 eligible
substitution operations and 8,259 node-to-representative assignments. Those
assignments are no longer the canonicalization output because a global
partition suppresses one-to-many ambiguity.

The surname-only anchored pilot starts from all 1,004,418 accepted Rajasthan
T1/T2 links. Both sides have a final eligible token for 257,509 links, including
230,716 exact token pairs. After aggregation, 2,021 observed roll forms have
2,771 anchor candidates. At the recorded support threshold of 2 and normalized
similarity threshold of 0.75, the decisions are:

| Decision | Observed forms |
| --- | ---: |
| Accepted identity | 608 |
| Accepted variant | 93 |
| Ambiguous | 114 |
| Unresolved | 1,206 |

These are operating outcomes, not precision estimates. In particular, the
accepted links are selected on complete-name skeleton equality, and the
ration-side token is a provisional anchor rather than a hand-adjudicated gold
spelling. The 114 ambiguous forms demonstrate why candidate rankings are kept
separate from decisions.

## Bihar official-land reference labels

The 4,387 accepted Shekhpura links produce 4,366 official-land reference
surnames under the Bihar final-token rule. Of these, 4,365 agree with the
roll-side normalized final token. One official land record adds a reference
where the roll rule abstains, 20 land names themselves yield a positional
abstention, and one token-order conflict is excluded. The accepted labels cover
78 distinct normalized reference surnames.

This near-perfect agreement is expected because the upstream person link used
the complete normalized name and relative name. It supports the quality of the
official land transcription and the positional extraction on the linked slice;
it is not an independent spelling-variant accuracy estimate. A name-withheld
relative-and-location linkage was tested and rejected after only 10.7% of 2,696
nominally unique pairs agreed on the held-out full name.
