# The synthetic world

Real SME underwriting files are private, so WealthPilot generates a **synthetic population with full ground truth**. Everything is
seeded and reproducible.

```bash
uv run python -m wealthpilot.synth.applicants     # applicants.json + watchlist.csv      (seed 7, 80 applicants)
uv run python -m wealthpilot.synth.render_docs    # data/synthetic/docs/<case>/<variant>/*.pdf
uv run python -m wealthpilot.synth.news           # news.json
uv run python -m wealthpilot.synth.groundtruth    # ground_truth.json (needs the trained PD model)
```

## Applicants

`wealthpilot.synth.applicants.generate(n=80, seed=7)` creates, for each applicant:

| Group | Contents |
|---|---|
| Identity | business name (usually containing the owner's surname), owner name, owner gender and name-origin label, street/city/state/ZIP |
| Business | industry (10 ordinary sectors; ~12 % are *prohibited* ones — cannabis, firearms, gambling, adult entertainment, crypto exchange), years in business |
| Request | loan amount (3–38 % of revenue), term (60–120 months), purpose, collateral value, whether a personal guarantee is given |
| SBA-like profile | state, legal form, fixed/variable rate, jobs supported, franchise flag — the inputs of the [PD model](../concepts/risk-model.md) |
| **True financials** | 1–3 fiscal years of income statement and balance sheet, built from a latent "health" variable so ratios, margins and leverage are realistic and consistent |
| Bank statement | 12 months of opening/deposits/withdrawals/closing that roll forward; owner draws mention the owner's name |
| Planted flags | **sanctions hit** (~6 %, the owner appears on a synthetic watchlist as `LAST, First`), **adverse-media severity** (none 74 %, low 10 %, medium 9 %, high 7 %) |

Internal identities hold: assets = liabilities + equity, current assets = cash + receivables + inventory, net income ties, and the bank rolls forward.
Ordinary (non-planted) names are re-drawn if they fuzzy-match anyone on the real OFAC list, so false sanctions hits do not contaminate the ground truth.

!!! note "Name-origin labels"
    The generator draws names from four internal origin groups (`g1`–`g4`) and two genders. These labels exist **only** to drive the
    counterfactual fairness tests; they are held in the sealed part of the case and are never shown to a model.

## Document variants

`wealthpilot.synth.render_docs` renders every applicant's statements and bank summary as PDFs in three variants:

| Variant | What changes |
|---|---|
| `clean` | standard layout, canonical row labels, one font |
| `noisy` | label synonyms ("Net Sales", "Finance Costs", "Creditors"), `$`/parenthesis negatives, columns in either order, mixed header formats (`FY2024` next to `Year ended Dec 31, 2023`), random fonts, notes naming the owner, pages in either order, "Profit and Loss" titles |
| `scanned` | the noisy content **rasterised** at 110 dpi with small rotation (±1.2°), brightness noise and blur, saved as image-only PDFs — there is no text layer |

Documents total about 260 MB for 80 applicants × 3 variants and are git-ignored.

## Mock external sources

| Source | Implementation |
|---|---|
| Adverse media | `news.json`: an article with the planted severity for flagged applicants, plus benign "decoy" articles (an award, a sponsorship) so that *having* an article is not itself a signal |
| Business registry | looks the business up in `applicants.json` |
| Sanctions | **real** OFAC SDN list (`data/ofac/sdn.csv`) plus `data/synthetic/watchlist.csv` (planted hits) |

## Ground truth

`wealthpilot.synth.groundtruth.build()` scores each applicant with the trained PD model and runs the [reference engine](../concepts/policy-rag.md#ground-truth)
under every policy, saving rule statuses, grade, recommendation and approver tier to `ground_truth.json`.

The generator was tuned so the population exercises every outcome:

| Policy | Approve | Refer | Decline |
|---|---|---|---|
| strict | 12 | 6 | 62 |
| lenient | 52 | 3 | 25 |

and **42 of 80** applicants have a different correct decision under the two policies.

## Counterfactual applicants

The fairness experiment ([E3](../experiments/e3-fairness.md#c-identity-counterfactuals)) builds counterfactuals with `swap()`: identical financials and loan, but a different owner name
(gender and name-origin swapped), business surname, street and ZIP — in the structured fields **and** re-rendered into the document text. They are written to `data/synthetic/docs_cf/`.
