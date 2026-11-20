# Decision rule

The recommendation is computed by code from rule statuses. It is never the language model's opinion. This page defines the statuses,
the rule that combines them, the cap for degraded runs, the risk grade that feeds rule CP-12 and the selection of the approver tier.

## Rule statuses

Each policy rule evaluated for a case receives exactly one status.

| Status | Meaning |
|---|---|
| Pass | The case complies with the rule. |
| Fail | The case violates the rule. |
| Exception | The rule text defines this situation as an exception to be referred to a committee, for example a media finding at or above a stated severity, or a metric inside an exception band when the stated extra condition is met. |
| Not applicable | The rule's condition does not apply, for example a collateral requirement for a loan below the size it covers. It is treated like a pass when the rules are combined. |
| Missing data | A fact needed to judge the rule is absent, a tool was unavailable, or the model's answer could not be trusted. |

The language model does not choose these labels. For each rule it answers three plain questions about the case: does the rule apply,
is the case in compliance, and does the rule text define the situation as an exception. Code maps the answers to a status in this
order:

| Answer | Status |
|---|---|
| The rule does not apply | Not applicable |
| The situation is an exception | Exception |
| In compliance | Pass |
| Not in compliance | Fail |
| Compliance unknown | Missing data |

!!! note "Why the model answers questions instead of choosing a label"
    Prohibition-style rules such as "an applicant in a prohibited industry fails this rule" invite double negatives, which can produce
    a correct explanation attached to the wrong label. Questions about the case remove that class of error.

## The rule

Every policy ends with the same decision rule, applied once in code:

1. If any rule has failed, the recommendation is **decline**.
2. Otherwise, if any rule carries an exception or has missing data, the recommendation is **refer**.
3. Otherwise the recommendation is **approve**.

Rules CP-1 to CP-12 take part. CP-13 (delegation of authority) is informational and only selects the approver tier.

## The degraded-run cap

A run is degraded when any tool, circuit breaker or check was unavailable. A degraded run never auto-decides in either direction:
whatever the rule produces, a recommendation of approve or decline is replaced by refer.

* Approving on incomplete checks would be unsafe for the bank.
* Declining because a check such as sanctions screening was not performed, and was misread as a failure, would be an adverse action
  with no real basis.

The memo validator additionally requires a limitations section whenever a run is degraded. The [reliability
evaluation](../research/e4-reliability.md) examines the behavior of degraded runs under injected faults.

## Risk grade

The grade, from A (best) to E (worst), is the bank's fixed rating methodology. It is not part of any one credit policy: the policy
only states which grades are acceptable, in rule CP-12.

**Step 1: probability band.** The calibrated five-year default probability maps to a band.

| Probability of default | Band |
|---|---|
| Below 2.0 percent | Low |
| 2.0 up to 3.5 percent | Moderate |
| 3.5 up to 4.5 percent | Elevated |
| 4.5 percent or higher | High |

The thresholds sit around the roughly 4 percent base rate of the training portfolio. See [Risk model](risk-model.md).

**Step 2: scorecard class.** Three ratio tests use thresholds that the policy agent extracted from the policy prose, so a stricter
policy produces a stricter scorecard.

| Test | Passes when |
|---|---|
| Debt service coverage | The ratio is at least the policy's minimum |
| Leverage | Debt-to-equity is between zero and the policy's maximum |
| Liquidity | The current ratio is at least the policy's minimum |

Three passes give **strong**, two give **adequate**, and zero or one give **weak**.

**Step 3: grade matrix.** Add the band position (low 0, moderate 1, elevated 2, high 3) to the class position (strong 0, adequate 1,
weak 2). The sum selects the grade from A to E, with sums above 4 capped at E.

| | Strong | Adequate | Weak |
|---|---|---|---|
| **Low** | A | B | C |
| **Moderate** | B | C | D |
| **Elevated** | C | D | E |
| **High** | D | E | E |

If the thresholds could not be extracted, or the ratios or the probability are missing, there is no grade. Rule CP-12 then cannot be
judged and the case is referred.

## Approver tier

The required approver level comes from the policy's own delegation-of-authority rule (CP-13). The model extracts the dollar limits
and whether exceptions require the committee from the text, and code compares the loan amount with the limits:

| Condition | Required tier |
|---|---|
| Any rule carries an exception and the policy says exceptions need the committee, or the loan exceeds the senior officer limit | Credit Committee |
| The loan exceeds the analyst limit | Senior Credit Officer |
| Otherwise | Analyst |

If the limits cannot be extracted, the tier defaults to the safest value, Credit Committee. [Human approval](compliance.md#human-approval)
describes how the approval gate enforces the tier. The accuracy of tier selection is reported in the
[policy adherence evaluation](../research/e0-policy-adherence.md).

## Overrides

The approver can decide differently from the recommendation. If the human decision is approve or decline and contradicts an
approve or decline recommendation, the final record is marked as an override and keeps the approver's reason. Overrides are written to
the audit log like any other decision. A human decision that differs from a refer recommendation is not an override.
