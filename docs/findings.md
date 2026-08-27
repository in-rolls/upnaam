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

After excluding alignments with token gaps, the accepted links supply 104,215
eligible substitution operations and 8,259 variant mappings at the declared
support and similarity thresholds. Those counts describe evidence volume; they
are not a precision estimate.
