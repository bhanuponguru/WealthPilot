# Agents

WealthPilot has six agent roles. An agent here is a workflow step with a defined responsibility. The roles differ in how much of the
work a language model does, and the table states that plainly.

| Role | Calls a language model | Calls tools | Authoritative output comes from |
|---|---|---|---|
| [Parser](#parser) | Yes (chat or vision) | No | Model extraction, verified by code through reconciliation |
| [Financial analyst](#financial-analyst) | Yes, for the narrative only | Yes, the `fincalc` server | Deterministic tool calls |
| [Credit research](#credit-research) | Only to summarize findings | Yes, the `research` server | Deterministic tool calls and code |
| [Risk scorer](#risk-scorer) | No | Yes, the `fincalc` server | The trained model |
| [Policy and compliance](#policy-and-compliance) | Yes, to judge rules | Yes, the `policydocs` and `fincalc` servers | Model judgment, verified by code |
| [Memo writer](#memo-writer) | Yes | Yes, the `policydocs` server | Model prose, validated by code |

!!! info "No supervisor agent"
    Routing between agents is deterministic. A language-model supervisor would make control flow harder to test and would add
    nondeterminism to every run. See [Design decisions](decisions.md#d1-deterministic-routing-instead-of-a-model-supervisor).

## Parser

The parser turns two PDFs into numbers: the financial statements (income statement and balance sheet, one to three fiscal years) and
a 12-month bank statement summary.

* **Text PDFs.** Words are reassembled into tables by their page coordinates so that each row states its values by fiscal year. A
  language model then maps row labels to 19 canonical fields.
* **Scanned PDFs.** Each page is sent to the vision model.
* **Verification.** The result is reconciled (the balance sheet balances, net income ties, bank balances roll forward). If it is
  inconsistent, the extraction is repeated once with the failures described to the model.

Details are in [Document parsing](document-parsing.md).

## Financial analyst

The analyst calls three tools directly and deterministically: ratios for the latest fiscal year, the revenue trend, and a stress test
that applies a 10 percent revenue drop. It then lets a language model, equipped with the `fincalc` tools, write a short narrative of
at most five sentences from those figures. The ratios stored on the case are the deterministic results. If the model calls extra
what-if tools, those results do not overwrite them.

When the policy check later reports missing data, the analysis retry recomputes the ratios using the prior year's value for any
field missing in the latest year, and records which fields were estimated.

## Credit research

Credit research makes five tool calls concurrently through the `research` server:

| Call | Purpose |
|---|---|
| Sanctions screening of the owner and of the business | Fuzzy match against the OFAC sanctions list and an optional additional watchlist |
| Adverse-media search | Returns articles about the business or its owner with a severity |
| Business registry lookup | Returns registration status and incorporation year if found |
| Sector default statistics | Five-year default rate for the applicant's industry sector, from the SBA data |

Code, not the language model, classifies sanctions matches. The best match score decides the status:

| Best score | Status |
|---|---|
| 97 or higher | Confirmed match |
| 92 up to 97 | Possible match |
| No match above 92 | No match |

The language model never sees the names that were screened. If there are articles or matches, one model call writes a two-sentence
summary from the redacted findings.

!!! note "Provider integration"
    The adverse-media and registry tools are integration points for external providers. The bundled implementations are mocks that
    read the optional demonstration data and report no results without it. The sanctions list is downloaded by the `bootstrap`
    service. Without it, screening finds no matches. See [Tool servers](tool-servers.md#data-sources).

## Risk scorer

The risk scorer makes one tool call that returns a calibrated five-year default probability, a probability band and the top
risk-increasing factors. No language model is involved. See [Risk model](risk-model.md).

## Policy and compliance

The policy agent is the most consequential role and the one whose accuracy the [evaluation](../research/e0-policy-adherence.md)
measures. It runs in two phases:

1. **Phase 1, rules CP-1 to CP-11.** For each rule, code retrieves passages through the `policydocs` server (hybrid search with
   reranking). One model call then judges four rules at a time and answers plain yes/no/unknown questions. Code maps the answers to a
   status and re-checks every numeric comparison the model claims to have made.
2. **Phase 2, CP-12 and CP-13.** The model judges CP-12 (is the risk grade acceptable). It then extracts the delegation-of-authority
   limits from the text of CP-13, and code compares the loan amount with those limits to choose the approver tier. Code applies the
   [decision rule](decision-rule.md) to produce the recommendation.

Details are in [Policy retrieval](policy-retrieval.md).

## Memo writer

The memo writer produces a structured credit memo with a recommendation, a summary, strengths, concerns, conditions, adverse-action
reasons and limitations. It receives the already derived recommendation and must explain it. The facts supplied to it include the
policy-check table, ratios, risk factors, the research summary, the applicant's prior decisions and up to two similar past cases. The
[memo validation](workflow.md#memo-validation) step checks its output.

## Tools

Every tool is served by one of three tool servers. See [Tool servers](tool-servers.md) for how the workflow calls them and the
[tool reference](../reference/tool-reference.md) for signatures.

| Server | Purpose |
|---|---|
| `fincalc` | Credit ratios, trend, stress test, comparisons, scorecard, grade and default-probability scoring |
| `policydocs` | Rule listing, policy search, rule lookup and similar precedents |
| `research` | Sanctions screening, adverse media, registry lookup and sector default statistics |
