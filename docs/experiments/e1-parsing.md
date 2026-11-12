# E1 · Document parsing

**Question.** How accurately can financial statements be extracted from clean, noisy-layout and scanned PDFs — and what does each part of the
[parsing pipeline](../concepts/document-parsing.md) contribute?

## Method

* **Cases:** 12 applicants (every fifth of the 80), each in three document variants — 36 financial-statement documents and 36 bank statements.
* **Fields:** 19 per fiscal year (7 income-statement, 12 balance-sheet); one to three years per applicant.
* **Correct** means `|predicted − true| ≤ max($1, 0.1 %)`. A document is *exact* if every field is correct.

### Arms

| Arm | Description |
|---|---|
| `baseline_oracle` | rule-based label-dictionary parser that knows **every** label variant the generator can emit (unrealistically strong) |
| `baseline_canonical` | the same parser knowing only canonical labels (realistic) |
| `llm_raw` | LLM extraction on the raw extracted text (or the vision model for scans) |
| `llm_layout` | LLM extraction on **layout-reconstructed** text (rows stated by year) |
| `llm_layout_repair` | the full pipeline: layout + reconciliation + one repair attempt |

## Results — financial statements (field-level accuracy)

| Variant | Baseline (oracle labels) | Baseline (canonical) | LLM raw | LLM + layout | **+ repair** |
|---|---|---|---|---|---|
| **Clean** | 100 % | 100 % | 97.9 % | 100 % | **100 %** |
| **Noisy layout** | 100 % | 36.7 % | 80.3 % | 99.5 % | **100 %** |
| **Scanned** | 0 % | 0 % | 96.9 % | 96.9 % | 96.9 % |

95 % Wilson intervals are in `report/results/e1_parsing.md`; each cell covers roughly 600 field values.

Document-level "exact" counts (all fields correct): clean 12/12 for the layout arms; noisy 11/12 → **12/12** with repair; scanned **10/12** for all LLM arms.

## Results — bank statements

| Variant | Monthly rows correct |
|---|---|
| Clean | 144 / 144 |
| Noisy | 144 / 144 |
| Scanned | 144 / 144 |

## Findings

### 1. The LLM's advantage is robustness
A dictionary parser is perfect when it knows the vocabulary and useless when it does not: with canonical labels only it dropped to **36.7 %** on
noisy layouts, and **no** rule-based approach can read an image. The LLM handles unseen label variants (*Net Sales*, *Finance Costs*, *Creditors*) and scans.

### 2. Column order is a silent failure mode — and a deterministic fix works
On noisy documents the raw LLM scored **80.3 %**. The cause was **column swaps**: with headers formatted differently on one page
(`Year ended Dec 31, 2023` beside `FY2024`) it assigned values to the wrong years. Because each year's totals still balance, **reconciliation cannot detect this**.

Rebuilding tables from word coordinates so every row states its values *by year* removed the failure: **80.3 % → 99.5 %**. Telling the model in the prompt to
"read the year above each column" did **not** help; fixing the input did.

### 3. Reconciliation detects errors; repair does not always fix them
On scans the reconciliation checks flagged **both** documents that contained errors (2 of 2), but the repair attempt did not correct them (96.9 % is unchanged):
detection works, automatic correction of OCR digit errors does not. That is what the human *document-review* gate is for. On noisy layouts, repair fixed the
one remaining document (99.5 % → 100 %).

### 4. Thinking mode is not worth it
Extended reasoning was tried for extraction and abandoned: the test on a single noisy document was still running when it hit its **280-second** limit, so it was impractical (and we could not measure whether it would have fixed the column swaps).

## Caveats

* The label dictionary of the oracle baseline comes from the same generator that produced the documents — it is an upper bound, not a fair competitor.
* Synthetic documents have clean digital origins; real scans, handwriting, multi-column notes and stamped pages are harder.
* One layout family (right-aligned numeric columns) — the coordinate-based reconstruction assumes columns align.

## Reproduce

```bash
cd experiments && CHAT_FALLBACK_MODEL="" uv run python e1_parsing.py 12
```

Outputs `report/results/e1_parsing.json` (every document × arm, with the wrong fields listed) and `e1_parsing.md`.
