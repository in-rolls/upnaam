# Baseline diagnostic findings

These are descriptive results from the unreleased baseline, not accuracy
estimates. The source of truth is `data/audit/evaluation.csv`.

## Four-state aggregate tables

| State | Weighted records | Final-token coverage | Single-token share | First candidate in relative | Last candidate in relative |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bihar | 69,943,602 | 97.42% | 2.58% | 2.57% | 35.13% |
| Rajasthan | 42,680,004 | 32.86% | 67.14% | 0.34% | 7.54% |
| Maharashtra | 83,029,252 | 98.27% | 1.73% | 89.20% | 65.08% |
| Punjab | 18,748,931 | 88.89% | 11.08% | 0.60% | 37.57% |

The Maharashtra comparison is strong evidence that a universal final-token
rule is wrong. Upnaam leaves the current result provisional and does not switch
to a first-token rule without an approved decision rule. Rajasthan's low
coverage is largely a tokenization fact in the Romanized aggregate table and
motivates the independent Devanagari linked-record check.

## Accepted external links

Upnaam materialized 4,387 Bihar land links, 536,536 Rajasthan T1 ration links,
and 467,882 Rajasthan T2 ration links. These counts exactly match the accepted
upstream artifacts.

| Accepted links | Written final token | Ration-supported exact suffix split | Abstained |
| --- | ---: | ---: | ---: |
| Bihar land exact links | 99.52% | 0.00% | 0.48% |
| Rajasthan T1 | 32.61% | 3.84% | 63.55% |
| Rajasthan T2 | 30.11% | 37.51% | 32.38% |

Rajasthan's T2 result demonstrates the value of a second transcription for
spacing: examples include `मोहनसिंह`/`मोहन सिंह` and
`सुनितादेवी`/`सुनिता देवी`. It does not demonstrate omitted family surnames,
because the upstream person link requires equality of the complete name
skeleton. Consequently the current family-surname candidate count is zero.

After excluding alignments with token gaps, the accepted links supply 104,215
eligible substitution operations and 8,259 variant mappings at the declared
support and similarity thresholds. Those counts describe evidence volume; they
are not a precision estimate.
