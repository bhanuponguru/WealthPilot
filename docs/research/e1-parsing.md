# E1: Document parsing

**Question.** How accurately can financial statements be extracted from clean, noisy-layout and scanned PDFs, and what does each
component of the [parsing pipeline](../architecture/document-parsing.md) contribute?

## Method

### Data

* **Applicants:** 12 synthetic applicants (every fifth of the 80), each in three document variants (clean, noisy, scanned): 36
  financial-statement documents and 36 bank statements. See [The synthetic world](synthetic-data.md).
* **Fields:** 19 per fiscal year (7 income-statement and 12 balance-sheet fields), with one to three years per applicant. Each cell in
  the results covers 608 field values.
* **Model:** `nvidia/nemotron-3.5-lightning-30b-a3b` for text, and a vision model for scanned pages.

### Metrics

A field is correct if the absolute difference from the true value is at most the larger of USD 1 and 0.1 % of the true value. A document
is exact if every field is correct. Intervals are Wilson 95 % intervals over field values. The reconciliation flag rate is the share of
documents with at least one wrong field that the accounting-identity checks flagged.

### Arms

| Arm | Description |
|---|---|
| Dictionary parser, full label set | A rule-based parser that knows every label variant the generator can emit. An unrealistically strong baseline and an upper bound for rule-based parsing. |
| Dictionary parser, canonical labels | The same parser knowing only the canonical labels. The realistic rule-based baseline. |
| Model on raw text | Model extraction on the text layer as extracted (the vision model for scans). |
| Model on reconstructed layout | Model extraction on layout-reconstructed text, in which every row states its values by year. |
| Full pipeline | Layout reconstruction, reconciliation against accounting identities, and one repair attempt. |

## Results: financial statements

Field-level accuracy.

| Variant | Dictionary, full labels | Dictionary, canonical labels | Model, raw text | Model, reconstructed layout | Full pipeline |
|---|---|---|---|---|---|
| Clean | 100 % | 100 % | 97.9 % | 100 % | 100 % |
| Noisy layout | 100 % | 36.7 % | 80.3 % | 99.5 % | 100 % |
| Scanned | 0 % | 0 % | 96.9 % | 96.9 % | 96.9 % |

95 % confidence intervals for the full pipeline: 99.4-100 % (clean), 99.4-100 % (noisy) and 95.2-98.0 % (scanned). Intervals for all arms
are in `research/results/e1_parsing.md`.

Document-level exact counts (all fields correct), out of 12:

| Variant | Dictionary, canonical | Model, raw | Model, reconstructed layout | Full pipeline |
|---|---|---|---|---|
| Clean | 12 | 8 | 12 | 12 |
| Noisy | 0 | 7 | 11 | 12 |
| Scanned | 0 | 10 | 10 | 10 |

Reconciliation flagged the wrong document in the noisy variant with reconstructed layout (1 of 1) and both wrong documents in the scanned
variant (2 of 2).

## Results: bank statements

| Variant | Monthly rows correct |
|---|---|
| Clean | 144 / 144 |
| Noisy | 144 / 144 |
| Scanned | 144 / 144 |

## Findings

1. **The model's advantage is robustness.** A dictionary parser is perfect when it knows the vocabulary and unusable when it does not: with
   canonical labels only, accuracy fell to 36.7 % on noisy layouts. No rule-based approach reads an image, which gives 0 % on scans. The model handles unseen
   label variants such as "Net Sales", "Finance Costs" and "Creditors", and handles scanned pages.
2. **Column order is a silent failure mode, and a deterministic fix removes it.** On noisy documents the model on raw text scored 80.3 %. The
   observed failure was a column swap: when column headers were formatted differently on one page (`Year ended Dec 31, 2023` next to
   `FY2024`), values were assigned to the wrong years. Because each year's totals still balance, reconciliation cannot detect a swap. Rebuilding tables from word
   coordinates so that each row states its values by year raised accuracy from 80.3 % to 99.5 %.
3. **Reconciliation detects errors, but repair does not always fix them.** On scans the reconciliation checks flagged both erroneous documents
   (2 of 2), but the repair attempt did not correct them (96.9 % is unchanged): detection works, automatic correction of OCR digit errors does not. The human
   document-review gate in the product exists for this case. On noisy layouts the repair step fixed the one remaining document (99.5 % to 100 %).

## Interpretation

Layout reconstruction is the decisive component for text PDFs with inconsistent layouts, and reconciliation with repair closes the remaining gap.
For scanned pages the pipeline reaches 96.9 % field accuracy and detects its own errors, but it cannot correct them without a person.

## Limitations

* The label dictionary of the full-label baseline comes from the same generator that produced the documents. The baseline is an upper bound, not a fair competitor.
* Synthetic documents have clean digital origins. Real scans, handwriting, multi-column notes and stamped pages are harder.
* The documents have a single layout family (right-aligned numeric columns). The coordinate-based reconstruction assumes that columns align.
* There are 12 applicants per variant. The scanned variant's two wrong documents are too few to characterize the error types.

See also [Limitations of the evaluation](limitations.md) and [Reproducing the experiments](reproduce.md).
