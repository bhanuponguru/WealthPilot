# Managing credit policies

A credit policy is a Markdown document. The assistant reads it the way an analyst would: it finds each rule, reads the thresholds and exceptions stated in the
text, and checks the application against them. Changing the bank's rules therefore means editing text, not code.

## Where policies live

Each policy is a folder under `policies/` containing a single file, `policy.md`:

```text
policies/
  strict/policy.md
  lenient/policy.md
  <your-policy>/policy.md
```

The folder name is the policy identifier shown in the console. In the Docker deployment the folder is part of the image; to edit policies without rebuilding,
bind-mount your own folder over it by adding this to the `console` and `mcp` services of the compose file:

```yaml
volumes:
  - ./policies:/app/policies
```

The folder must contain only policy text. Nothing else belongs next to `policy.md`.

## What a policy document must contain

| Convention | Why it matters |
|---|---|
| Rules are second-level headings of the form `## CP-<n> <Title>` | The rule catalogue and the search index recognize rules by this heading. Each rule becomes one searchable section carrying its identifier. |
| **CP-3, CP-4 and CP-5** state a minimum debt service coverage ratio, a maximum debt-to-equity ratio and a minimum current ratio as numbers in prose | The policy step extracts these thresholds, and the scorecard (and so the risk grade) uses them. |
| **CP-12** states which risk grades (A best to E worst) are acceptable | It is evaluated after the grade is computed. |
| **CP-13** states approval limits in dollars for the Analyst and Senior Credit Officer tiers, and what requires the Credit Committee | The limits are read from the text; code then selects the required approval tier. |
| A **Definitions** section for the ratios used | Case facts are computed with fixed formulas. The text should agree with them. |
| A **Decision rule** section | The rule itself is fixed (any failed rule leads to decline; otherwise any exception or missing data leads to refer; otherwise approve). The section documents it for readers and for retrieval. |

Rules after CP-13 (for example `CP-14`) are picked up automatically: every rule other than CP-12 and CP-13 is evaluated in the policy step. The full catalogue of the
bundled rules is in [Policy rules](../reference/policy-rules.md).

## Writing rules that are read correctly

* **Put the number in the sentence:** "The debt service coverage ratio must be at least 1.30." Avoid tables of thresholds that retrieval could separate from their heading.
* **State conditions explicitly:** "For requests above USD 150,000, collateral coverage must be at least 1.00."
* **Define exceptions inside the rule**, including the extra condition they need.
* **Use plain pass/fail language.** The model answers three questions about each rule (does it apply, is it satisfied, does an exception apply); code turns the answers into a status.
* **Be careful with prohibitions and size conditions.** "Applicants in prohibited industries fail this rule" and "above or below a given size" were the most error-prone constructions. After adding one, run a few cases and read the evidence quoted in the policy checklist.

## Activating a new or changed policy

1. Add or edit `policies/<id>/policy.md`.
2. Rebuild the search index for the policies and restart the services that cache it:

    ```bash
    docker compose exec console wealthpilot ingest-policy
    docker compose restart mcp console
    ```

    A new policy folder is indexed automatically the first time the tool servers start; an edited one must be re-indexed as above.
3. Open **Credit policies** in the console to read the policy as the assistant sees it, compare it with another policy rule by rule, and run retrieval queries to confirm each rule can be found.
4. Run a case under the policy from **New case** and review the **Policy checklist**: each rule shows its status, the reason, a quoted evidence sentence and the citation `<policy>/CP-<n>`.

## What changes when a policy changes

| Changing... | Changes... |
|---|---|
| a threshold in CP-3, CP-4 or CP-5 | the extracted thresholds, the scorecard, the risk grade and rule statuses |
| the list of prohibited industries | rule verdicts for CP-2 |
| exception wording | which cases become exceptions and are therefore referred |
| the acceptable grades in CP-12 | grade-based failures |
| the approval limits in CP-13 | the approval tier shown at the decision gate |

## Evaluating a policy against ground truth

Measuring how faithfully the assistant applies a policy requires a machine-readable answer key, which is deliberately kept out of the product. The research package holds the answer keys
and the tooling to score a policy; see [Reproducing the experiments](../research/reproduce.md).
