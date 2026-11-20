# The synthetic world

Real SME underwriting files are private, so the evaluation uses a synthetic population of applicants with full ground truth. Every
element is generated from a seed and is reproducible. The generator is part of the research package and is not shipped with the product.

## Contents of the population

The population has 80 applicants (generator seed 7). Each applicant has the following attributes.

| Group | Contents |
|---|---|
| Identity | Business name (usually containing the owner's surname), owner name, owner gender, a name-origin label, street, city, state and ZIP code. |
| Business | Industry (10 ordinary sectors or 5 prohibited ones: cannabis, firearms, gambling, adult entertainment, cryptocurrency exchange) and years in business. |
| Request | Loan amount (3 % to 38 % of revenue), term (60, 84 or 120 months), purpose, collateral value and whether a personal guarantee is given. |
| Risk-model profile | State, legal form, fixed or variable rate, jobs supported and franchise flag: the inputs of the [risk model](../architecture/risk-model.md). |
| True financials | One to three fiscal years of income statement and balance sheet, built from a latent health variable so that ratios, margins and leverage are realistic and mutually consistent. |
| Bank statement | Twelve months of opening balance, deposits, withdrawals and closing balance that roll forward; owner draws mention the owner's name. |
| Planted flags | A sanctions hit (the owner appears on a synthetic watchlist as `LAST, First`) and an adverse-media severity (none, low, medium or high). |

Internal accounting identities hold by construction: assets equal liabilities plus equity, current assets equal cash plus receivables
plus inventory, net income ties to the income statement, and the bank balance rolls forward. Ordinary names, that is names that are
not planted sanctions hits, are redrawn if they fuzzy-match any entry on the real OFAC list, so accidental sanctions hits cannot contaminate the
ground truth.

Planted cases are drawn with fixed probabilities. The realized counts in the generated population are shown alongside.

| Attribute | Draw probability | Realized (of 80) |
|---|---|---|
| Prohibited industry | 12 % | 14 |
| Sanctions hit | 6 % | 3 |
| Adverse media: none / low / medium / high | 74 % / 10 % / 9 % / 7 % | 59 / 7 / 10 / 4 |

!!! note "Name-origin labels"
    Names are drawn from four internal origin groups and two genders. The labels exist only to drive the counterfactual fairness tests in
    [E3](e3-fairness.md). They are held in a sealed part of each case and are never shown to a model.

## Document variants

Each applicant's financial statements and bank statement are rendered as PDFs in three variants.

| Variant | What differs |
|---|---|
| Clean | Standard layout, canonical row labels, one font. |
| Noisy | Label synonyms (for example "Net Sales", "Finance Costs", "Creditors"), dollar signs and parenthesized negatives, columns in either order, mixed column-header formats (`FY2024` next to `Year ended Dec 31, 2023`), varied fonts, notes naming the owner, pages in either order and alternative statement titles ("Profit and Loss"). |
| Scanned | The noisy content rasterized at 110 dpi with a small random rotation (up to 1.2 degrees), brightness noise and blur, saved as image-only PDFs with no text layer. |

The full document set (80 applicants, three variants) occupies about 260 MB.

## Mock external sources

| Source | Content |
|---|---|
| Adverse media | A news corpus with one article of the planted severity for each flagged applicant, plus benign decoy articles (an award, a sponsorship, an expansion) so that having an article is not itself a signal. |
| Business registry | Looks the business up in the synthetic applicant list. |
| Sanctions screening | The real OFAC SDN list plus the synthetic watchlist that holds the planted hits. |

## Ground truth

The ground truth for each applicant is computed in two steps. The trained risk model scores the applicant's profile, and the reference
engine then applies each credit policy's hidden answer key to the true financials and planted flags. The engine records every rule status, the
risk grade, the recommendation and the required approver tier. The engine uses the same fixed decision rule as the product, so the
truth is computed by the rule that the system under test is also expected to follow.

The generator was tuned so that the population exercises every outcome under both policies.

| Policy | Approve | Refer | Decline |
|---|---|---|---|
| Strict | 12 | 6 | 62 |
| Lenient | 52 | 3 | 25 |

For 42 of the 80 applicants the correct decision differs between the two policies.

## Validation

* A unit test checks that the reference engine yields an exception status in the lenient policy's DSCR exception band and a failure under the strict policy.
* A unit test checks that the generated ground-truth decisions differ between the two policies for a substantial share of applicants.
* The accounting identities above are enforced when the statements are generated.

The population is not validated against real applicants. See [Limitations of the evaluation](limitations.md).

## Counterfactual applicants

The identity experiment ([E3](e3-fairness.md)) derives counterfactual applicants from selected cases. A counterfactual has identical financials
and loan terms but a different owner name (gender and name origin swapped), business surname, street and ZIP code. The changes are applied
both to the structured fields and to the text of the rendered documents. Two counterfactuals are built per case.

## Demonstration data

The generated applicants, documents and mock sources are plain files. The product can load them as optional demonstration data to try the
system without real documents; this is off by default. See [Reproducing the experiments](reproduce.md) for how to generate the files and
[Configuration](../get-started/configuration.md) for how the product is switched into demonstration mode.
