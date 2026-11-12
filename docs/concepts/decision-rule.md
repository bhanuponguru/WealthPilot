# The decision rule

The recommendation is **computed by code** from the rule statuses — it is never the LLM's opinion. This page defines the statuses, the
rule, the safety cap for degraded runs, and the risk grade that feeds rule CP-12.

## Rule statuses

Each policy rule evaluated for a case gets exactly one status:

| Status | Meaning |
|---|---|
| `pass` | The case complies with the rule. |
| `fail` | The case violates the rule. |
| `exception` | The rule text defines this situation as an exception to be **referred** to a committee (for example a media finding at or above a stated severity, or a metric inside an exception band with the stated extra condition met). |
| `not_applicable` | The rule's condition does not apply (for example a collateral requirement for a loan below the size it covers). Treated like `pass` when scoring. |
| `missing_data` | A fact needed to judge the rule is absent, a tool was unavailable, or the model's answer could not be trusted. |

The LLM does **not** choose these labels. It answers three plain questions per rule — `applies`, `rule_satisfied`, `exception` — and code maps them
(`wealthpilot.graph.nodes.to_status`):

```text
applies == false                          -> not_applicable
exception == true                         -> exception
rule_satisfied == true                    -> pass
rule_satisfied == false                   -> fail
rule_satisfied == null                    -> missing_data
```

!!! note "Why not ask for pass/fail directly?"
    Prohibition-style rules ("an applicant in a prohibited industry *fails* this rule") invite double negatives. In testing the model once
    wrote "not in the prohibited list" and then `status: fail`. Boolean questions about the *case* removed that class of error.

## The fixed decision rule

Every policy ends with the same "Decision Rule" section, implemented once in `wealthpilot.policy_ref.derive_recommendation`:

```python
if any(status == "fail"):                              return "decline"
if any(status in ("exception", "missing_data")):       return "refer"
return "approve"
```

Rules CP-1 … CP-12 take part; CP-13 (delegation of authority) is informational and only selects the approver tier.

## The degraded-run cap

```python
def final_recommendation(checks, degraded):
    rec = derive_recommendation(checks)
    return "refer" if degraded and rec != "refer" else rec
```

A run is **degraded** when any tool, circuit breaker or check was unavailable (`state.degraded`). A degraded run **never auto-decides in
either direction**:

* approving on incomplete checks would be unsafe for the bank;
* declining because "sanctions screening was not performed" was read as a failure would be an adverse action with no real basis. The
  [reliability experiment](../experiments/e4-reliability.md#a-bug-e4-found) found four such wrongful declines before this cap existed.

The memo validator additionally requires a `limitations` section whenever a run is degraded.

## Risk grade

The grade (A best … E worst) is the bank's **fixed rating methodology**, not part of any one credit policy — the policy only states which
grades are acceptable (rule CP-12).

**Step 1 — PD band** from the calibrated 5-year default probability:

| PD | Band |
|---|---|
| < 2.0 % | low |
| 2.0 % – 3.5 % | moderate |
| 3.5 % – 4.5 % | elevated |
| ≥ 4.5 % | high |

The thresholds sit around the SBA portfolio's ~4 % base rate. See [Risk model](risk-model.md).

**Step 2 — scorecard class** from three ratio tests, using **thresholds the policy agent extracted from the policy prose** (so a stricter
policy produces a stricter scorecard):

| Test | Passes when |
|---|---|
| DSCR | `dscr >= min_dscr` |
| Leverage | `0 <= debt_to_equity <= max_debt_to_equity` |
| Liquidity | `current_ratio >= min_current_ratio` |

3 passes → **strong**, 2 → **adequate**, 0–1 → **weak**.

**Step 3 — grade matrix:** `index = band_index + class_index` (low = 0 … high = 3; strong = 0, adequate = 1, weak = 2), and
`grade = "ABCDE"[min(index, 4)]`.

| | strong | adequate | weak |
|---|---|---|---|
| **low** | A | B | C |
| **moderate** | B | C | D |
| **elevated** | C | D | E |
| **high** | D | E | E |

If the thresholds could not be extracted, or the ratios or PD are missing, the grade is `None`, rule CP-12 becomes `missing_data`, and the
case is referred.

## Approver tier

The required approver level comes from the policy's own delegation-of-authority rule (CP-13): the LLM **extracts** the dollar limits from the
text, and code compares the loan amount against them:

```python
if (has_exception and exception_requires_committee) or loan > officer_max:   "Credit Committee"
elif loan > analyst_max:                                                       "Senior Credit Officer"
else:                                                                          "Analyst"
```

If the limits cannot be extracted, the tier defaults to the **safest** value, *Credit Committee*. In the policy-adherence experiment,
tier accuracy was 91.7 % (strict) and 100 % (lenient). See [Compliance](compliance.md#human-approval) for how the gate enforces the tier.

## Overrides

The approver can decide differently from the recommendation. If the human decision is *approve* or *decline* and contradicts an
*approve*/*decline* recommendation, the final record has `"override": true` and keeps the approver's reason. Overrides are written to the
audit log like any other decision.
