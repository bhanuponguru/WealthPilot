# Writing a new policy

Because the policy is *data*, changing the bank's rules means editing a Markdown file — no code. This guide covers what the system expects, how to
index a policy, how to run cases under it, and how to compute ground truth if you want to evaluate it.

## 1. Create the policy document

Create `data/policies/<policy_id>/policy.md`. Start from `data/policies/strict/policy.md`.

### What the system relies on

| Convention | Why it matters |
|---|---|
| Rules are second-level headings of the exact form **`## CP-<n> <Title>`** | `list_rules` and the chunker recognise rules with the pattern `^## (CP-\d+)\s+(.*)$`. Each rule becomes one chunk carrying its id. |
| **CP-3, CP-4, CP-5** state a minimum DSCR, a maximum debt-to-equity and a minimum current ratio as numbers in prose | the policy agent extracts these thresholds and the **scorecard** (and therefore the risk grade) uses them. |
| **CP-12** states which risk grades (A best … E worst) are acceptable | judged after the grade is computed. |
| **CP-13** states approval limits in dollars for *Analyst* and *Senior Credit Officer*, and what requires the *Credit Committee* | the LLM extracts the limits; code chooses the approver tier. |
| A **Definitions** section defining DSCR, debt-to-equity, current ratio, loan-to-revenue, collateral coverage and years in business | the case facts are computed with fixed formulas in `wealthpilot.finance`; the text should agree with them. |
| A **Decision Rule** section | the fixed rule (any `fail` → decline; else any `exception` or missing data → refer; else approve) is implemented in code. The section documents it for readers and for retrieval. |

Rules beyond CP-13 (for example `CP-14`) are picked up automatically: `list_rules` returns whatever headings exist, and every rule except CP-12/CP-13 is judged in the `policy` step.

### Writing style that works

* Put the **number in the sentence**: "The DSCR must be at least 1.30." Avoid tables of thresholds the retriever may split from their heading.
* State **conditions explicitly**: "For requests above USD 150,000 collateral coverage must be at least 1.00."
* Define **exceptions in the rule** itself, including what extra condition they need.
* Use **plain pass/fail language**; the model answers `applies / rule_satisfied / exception` questions about the case, not about your wording.

!!! tip "Test your wording"
    Prohibition rules ("applicants in prohibited industries fail this rule") and *"above/below a size"* conditions were the most error-prone
    constructions in the experiments. Run a few cases and read the evidence quotes in the policy checklist.

## 2. (Optional) Add a compliance profile

The prohibited-basis term list is in `data/compliance_profiles/us_example.yaml`. To use different terms, edit that file or point
`wealthpilot.compliance.language_scan.PROFILE` at another one.

## 3. Index it

The `policydocs` server indexes **every** directory under `data/policies/` that contains a `policy.md` on start-up (if its chunks are missing).
To index explicitly:

```bash
uv run python -c "from wealthpilot.rag import index; [print(s, index.ingest('mypolicy', s)) for s in index.STRATEGIES]"
```

`wealthpilot ingest-policy` rebuilds only the two bundled policies; for others use the command above or restart `policydocs`.

## 4. Check it in the console, then run cases under it

In the [web console](console.md), the **Policies** page lets you read your new policy, **compare it side by side** with another (showing only the rules that differ), and **try retrieval** with real questions
to confirm each rule is findable. Then run cases under it from **Underwrite**, or from the command line:

```bash
uv run wealthpilot run C004 --policy mypolicy --thread try-1
```

Read the **Policy checklist** — each rule shows the status, the reason, a quoted evidence sentence and the citation `mypolicy/CP-n`.

## 5. (Optional) Evaluate it against ground truth

The experiments score agents against a **reference engine** that reads a hidden `reference.yaml`. To evaluate a new policy:

1. Create `data/policies/<id>/reference.yaml` with the same keys as the bundled ones:

    ```yaml
    policy_id: mypolicy
    min_years_in_business: 2
    prohibited_industries: [cannabis]          # tags: cannabis, firearms, gambling, adult_entertainment, crypto_exchange
    min_dscr: 1.25
    dscr_exception_floor: null                 # or e.g. 1.10 for an exception band
    dscr_exception_min_collateral: null
    max_debt_to_equity: 3.5
    min_current_ratio: 1.1
    max_loan_to_revenue: 0.4
    min_statement_years: 2
    collateral_threshold_amount: 200000
    min_collateral_coverage: 0.9
    guarantee_always: false
    guarantee_amount_trigger: 250000
    guarantee_years_trigger: 5
    adverse_media_exception_levels: [high]
    worst_acceptable_grade: C
    authority: {analyst_max: 100000, officer_max: 400000}
    ```

2. Add the id to `POLICIES` in `wealthpilot/synth/groundtruth.py` and regenerate: `uv run python -m wealthpilot.synth.groundtruth`.
3. Run `experiments/e0_policy.py` (it iterates over `POLICIES` in that script — add your id there too).

!!! warning "Keep the answer key hidden"
    `reference.yaml` must never be indexed or exposed through a tool. If an agent can read it, a policy change becomes a trivially correct
    file swap and the experiment stops measuring reading comprehension.

## What changes when you change a policy

| You change… | …and the system changes… |
|---|---|
| a threshold in CP-3/4/5 | the extracted thresholds, the scorecard, the risk grade and rule statuses |
| the prohibited-industry list | CP-2 verdicts |
| the exception wording | which cases are `exception` → *refer* |
| the acceptable grades in CP-12 | grade-based failures |
| the authority limits in CP-13 | the approver tier shown at the approval gate |

The bundled *strict* and *lenient* policies differ in exactly these ways, and in the [policy-adherence experiment](../experiments/e0-policy-adherence.md)
the decision changed in the right direction for 5 of 6 cases whose correct outcome differs.
