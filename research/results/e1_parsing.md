# E1: Document parsing

## Financial statements (field-level)
| variant | arm | docs | field_acc | CI95 | doc_exact | wrong_docs_flagged_by_recon | errors | avg_secs |
|---|---|---|---|---|---|---|---|---|
| clean | baseline_oracle | 12 | 1.0 | 0.9937-1.0 | 12/12 | - | 0 | 0.0 |
| clean | baseline_canonical | 12 | 1.0 | 0.9937-1.0 | 12/12 | - | 0 | 0.0 |
| clean | llm_raw | 12 | 0.9786 | 0.9638-0.9875 | 8/12 | - | 0 | 71.4 |
| clean | llm_layout | 12 | 1.0 | 0.9937-1.0 | 12/12 | 0/0 | 0 | 76.7 |
| clean | llm_layout_repair | 12 | 1.0 | 0.9937-1.0 | 12/12 | 0/0 | 0 | 83.6 |
| noisy | baseline_oracle | 12 | 1.0 | 0.9937-1.0 | 12/12 | - | 0 | 0.0 |
| noisy | baseline_canonical | 12 | 0.3668 | 0.3294-0.4058 | 0/12 | - | 0 | 0.0 |
| noisy | llm_raw | 12 | 0.8026 | 0.7691-0.8323 | 7/12 | - | 0 | 86.1 |
| noisy | llm_layout | 12 | 0.9951 | 0.9856-0.9983 | 11/12 | 1/1 | 0 | 90.0 |
| noisy | llm_layout_repair | 12 | 1.0 | 0.9937-1.0 | 12/12 | 0/0 | 0 | 99.4 |
| scanned | baseline_oracle | 12 | 0.0 | 0.0-0.0063 | 0/12 | - | 0 | 0.8 |
| scanned | baseline_canonical | 12 | 0.0 | 0.0-0.0063 | 0/12 | - | 0 | 0.6 |
| scanned | llm_raw | 12 | 0.9688 | 0.9517-0.9799 | 10/12 | - | 0 | 20.1 |
| scanned | llm_layout | 12 | 0.9688 | 0.9517-0.9799 | 10/12 | 2/2 | 0 | 9.9 |
| scanned | llm_layout_repair | 12 | 0.9688 | 0.9517-0.9799 | 10/12 | 2/2 | 0 | 3.6 |

## Bank statements (monthly rows)
| variant | docs | month_rows_correct | acc | CI95 | errors |
|---|---|---|---|---|---|
| clean | 12 | 144/144 | 1.0 | 0.974-1.0 | 0 |
| noisy | 12 | 144/144 | 1.0 | 0.974-1.0 | 0 |
| scanned | 12 | 144/144 | 1.0 | 0.974-1.0 | 0 |
