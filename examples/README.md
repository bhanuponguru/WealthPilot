# Example cases

Two synthetic applicants with their documents, for trying the console without real data. Everything here is generated, and no real
person or business is described. Each folder holds `application.json` (the values to type into **New case**), `financials.pdf` and
`bank_statement.pdf` (the clean document variant).

## Try one

1. Start the stack (`docker compose up -d --build`) and open <http://127.0.0.1:8501>.
2. Sign in as a reviewer in the sidebar and choose the tier **Senior Credit Officer**.
3. Open **New case**, enter the values from `C004/application.json` (the owner name is split into first and last name), upload the two PDFs
   and choose the credit policy **strict**.
4. Select **Run underwriting**. A run takes about five to ten minutes on the free model tier.

## Expected outcome

The reference outcome is computed by the research package from the policy thresholds, which the product never sees. A model-driven run is
not bit-for-bit repeatable, so judge the recommendation, the grade and the required tier, and read the quoted evidence for any rule you
doubt.

| Case | Business | Loan | Strict policy | Lenient policy |
|---|---|---|---|---|
| `C004` | Ibarra Restaurant Co. | 100,000 | decline, grade B, tier Senior Credit Officer | approve, grade B, tier Analyst |
| `C007` | Prescott Auto Co. | 175,000 | decline, grade C, tier Senior Credit Officer | approve, grade B, tier Senior Credit Officer |

`C004` is one of the cases used in the policy-adherence experiment. `C007` is used in no experiment, so it serves as an unseen case. Both flip
between the policies, which shows the policy being read.
