# Limitations of the evaluation

This page lists the limits that apply when interpreting the results in this section. Limits of the deployed product are on
[Known limitations](../administration/limitations.md).

## Sample sizes

The free model tier throttles requests per model, which bounds the number of end-to-end runs. Sample sizes are small and confidence
intervals are wide.

| Experiment | Sample | Consequence |
|---|---|---|
| E0 | 12 cases under 2 policies (24 runs, 288 rule judgements) | The lenient-policy decision interval is 65-99 % and the flip-agreement interval is 44-97 %. One wrong decision moves the rate by 8.3 points. |
| E1 | 12 applicants in 3 variants; 608 field values per cell | Field intervals are narrow, but the scanned variant has only 2 wrong documents, too few to characterize error types. |
| E2 | 104 queries from 13 rules and 2 policies | Queries are phrasings of the same rules, so they are not independent samples. |
| E3(b) | 20 seeds per bias level | The false-positive rate at zero bias (15 %) is estimated from 3 of 20 seeds. |
| E3(c) | 3 cases, 6 counterfactuals | Small identity effects cannot be excluded. |
| E4 | 4 cases per fault profile | The results show mechanisms, not probabilities. |

Each experiment was run once. Run-to-run variation is not estimated, except for the single noise-floor comparison in E3(c).

## Synthetic data

* Formats, label noise, fraud patterns and financial structure are far simpler than real files. Real scans, handwriting, notes to the
  accounts and inconsistent templates are harder.
* The documents have one layout family (right-aligned numeric columns), and the reconstruction of table layout in the parsing pipeline
  assumes that columns align.
* The population has 80 applicants. The planted sanctions and adverse-media cases are few (3 sanctions hits; 4 high, 10 medium and 7 low
  adverse-media cases).
* Generated documents have clean digital origins. Scanned variants are rasterized from them with synthetic noise.
* The synthetic population is not validated against real applicants.

## Ground truth

* The reference engine encodes the authors' reading of the policy text, and the two policies and the engine were written together. The experiments
  measure consistent application of explicit rules. They do not measure the discovery or resolution of ambiguous, contradictory or incomplete policy text.
* The engine applies the same fixed decision rule as the product, so decision-level accuracy does not test that rule independently.
* The policies are two documents of similar structure. Generalization to other policy libraries is untested.

## Mock external sources

Adverse media and the business registry read the synthetic population, and only the OFAC sanctions list is real. The experiments therefore say
nothing about the quality of real news or registry providers, about name-matching against real-world noise in those sources, or about
latency and failure behavior of real services.

## Risk model and real data

* **No borrower financials.** The SBA data holds loan and business-profile fields only, so the default-risk model cannot use the parsed ratios. They
  enter the decision through the policy and the scorecard. The test AUC is modest (0.68).
* **Selective labels.** The SBA file contains only approved loans. The risk model and the fairness audit say nothing about applicants a lender would have
  rejected, and the audit probably understates disparities.
* **Proxy groups.** The file has no race, gender or ethnicity fields, so the real-data audit uses region, business age and legal form. These are not
  protected classes. The planted-bias test in E3(b) is synthetic and uses a simple proxy.
* **One jurisdiction's example profile.** The compliance profile is an ECOA and Regulation B style example. It is not legal advice and not a
  compliant implementation.

## Models and platform

* **One model family.** The accuracy experiments use a single chat model, `nvidia/nemotron-3.5-lightning-30b-a3b`, and one vision model and one
  reranker. Results with other models will differ. The model comparison in [Research overview](index.md) covers 2 cases and cannot rank models.
* **Free-tier endpoints.** Throttling per model, model availability and endpoint behavior change over time. Run times in the results reflect
  throttling and concurrency, not the intrinsic speed of the system.
* **Nondeterminism.** Models vary from run to run even at temperature 0. A plain uncached rerun changed 1 of 24 rule statuses in E3(c), and in one case
  changed document extraction enough to fail reconciliation and divert the case to document review. The response cache makes repeated runs with identical
  prompts reproduce earlier replies, which is useful for repeatability but hides this variation.
* **Mixed system versions.** The system was modified between some experiments. [Research overview](index.md#experimental-versions-and-re-runs)
  states which result was produced before or after which change.

## Experiment-specific limits

| Experiment | Limit |
|---|---|
| E0 | Remaining errors concentrate on rules whose applicability depends on a numeric condition in the text (CP-8, CP-9), and one run asserted a finding that was not in the case data. The decision rule and numeric verification contain these errors but do not eliminate them. |
| E1 | Reconciliation detects errors in scanned documents but the automatic repair did not correct them. Identity in scanned images cannot be text-redacted. |
| E2 | The corpus is small, so dense retrieval and fusion may matter more on larger corpora. Dense embeddings come from a small local model. |
| E3(c) | With redaction on, zero decision flips is guaranteed by construction because the prompts are identical after redaction. The evidence is the leak rate and the uncached noise floor. |
| E3(d) | The rate at which adverse-action reasons were complete on the first attempt was not measured. It is enforced by validation and unit-tested. |
| E4 | Faults are injected at the gateway and tool-call boundaries only. A crash is simulated by abandoning a stream, not by terminating a process. |

## Extensions of the evaluation

* A larger and more adversarial evaluation: more cases, more policy variants, ambiguous and contradictory policy text, and real-world document samples.
* A treatment of the CP-8 class of errors, for example by extracting conditions as structured predicates that code evaluates, extending numeric
  verification from checking comparisons to performing them, and an experiment to measure the effect.
* Automatic verification that facts cited by the model (such as an adverse-media severity) match the case data.
* A second model family, to measure how much of the observed behavior is model-specific.
* Real news and registry providers in place of the mock sources.
