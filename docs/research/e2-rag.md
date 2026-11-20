# E2: Policy retrieval

**Question.** Which retrieval design most reliably finds the policy rule that answers a question, and how much does each component
(chunking, keyword search, dense vectors, fusion, reranking) contribute?

## Method

### Data

The gold set has 104 queries: 13 rules (CP-1 to CP-13) times 4 phrasings times 2 policies. Each rule has two direct questions ("What is the
minimum DSCR?") and two paraphrased or scenario questions ("cash flow is thin compared with the loan payments; what does the policy
say"). The correct answer for a query is the section for that rule id. Both example policies are indexed; see
[Credit policy and retrieval](../architecture/policy-retrieval.md).

### Metrics

* **Hit:** the gold rule id is among the rules covered by a retrieved chunk. For fixed-window chunks, which can span rules, this
  definition is generous.
* **recall@1, recall@3 and mean reciprocal rank (MRR).** The MRR carries a 95 % bootstrap interval (2,000 resamples).

### Arms

Chunking (structure-aware sections or fixed windows) times retrieval (keyword BM25, dense vectors, or hybrid fusion of both by reciprocal rank
fusion) times reranking (off, or the hosted cross-encoder reranker), for 10 combinations. Dense embeddings come from the local
`nomic-embed-text` model; the reranker is `nvidia/llama-nemotron-rerank-vl-1b-v2`.

## Results

| Chunking | Retrieval | Rerank | recall@1 | recall@3 | MRR | MRR 95 % CI |
|---|---|---|---|---|---|---|
| Structure | BM25 | no | 0.798 | 0.856 | 0.822 | 0.750-0.894 |
| Structure | Dense | no | 0.740 | 0.904 | 0.821 | 0.758-0.885 |
| Structure | Hybrid | no | 0.769 | 0.885 | 0.819 | 0.752-0.883 |
| Structure | BM25 | yes | 0.923 | 0.923 | 0.923 | 0.865-0.971 |
| Structure | Dense | yes | 0.942 | 0.942 | 0.942 | 0.894-0.981 |
| Structure | Hybrid | yes | 0.971 | 0.971 | 0.971 | 0.933-1.000 |
| Fixed | BM25 | no | 0.625 | 0.856 | 0.732 | 0.657-0.803 |
| Fixed | Dense | no | 0.683 | 0.904 | 0.779 | 0.710-0.845 |
| Fixed | Hybrid | no | 0.673 | 0.923 | 0.790 | 0.728-0.853 |
| Fixed | Hybrid | yes | 0.923 | 0.990 | 0.954 | 0.920-0.984 |

The reranker was available for every query in every arm (zero degraded reranking calls).

## Findings

1. **Reranking is the dominant lever.** Adding the reranker to hybrid search with structure-aware chunking lifts recall@1 from 0.769 to 0.971.
   First-stage retrieval places the correct rule in the top three for 85.6 % to 90.4 % of queries (structure-aware chunking) but often not first,
   and the cross-encoder reorders it.
2. **Structure-aware chunking beats fixed windows until a reranker is added.** Without reranking, fixed windows have lower recall@1
   (0.625 to 0.683, against 0.740 to 0.798): a window cuts rules in the middle and mixes neighboring rules. With a reranker the gap narrows to
   0.923 against 0.971.
3. **Hybrid fusion did not beat keyword search without a reranker.** Hybrid recall@1 is 0.769 against 0.798 for BM25, and the intervals
   overlap. The corpus is small and keyword-rich, so exact terms ("DSCR", "collateral") carry most of the signal.
4. **Hybrid retrieval with a reranker is the best arm** on recall@1 and MRR, and it is the configuration the system uses.

## Relation to E0

In the end-to-end system, retrieval is performed by the workflow itself for every rule, with a direct rule lookup as a fallback when a rule's
own section is missing from the top results. A retrieval miss therefore costs an extra call rather than producing a wrong answer. The 97.1 %
first-hit rate means the fallback is rarely needed. See [E0](e0-policy-adherence.md).

## Limitations

* The corpus is small, clean and consists of two policy documents. Larger or messier policy libraries will be harder, and the dense component may matter more.
* Gold labels are at section level. A query that legitimately spans two rules counts as a hit for either.
* Dense embeddings come from a small local model because no hosted embedding model was available for the account.
* The 104 queries are not independent: they are four phrasings of each of 13 rules in two policies of similar structure, which the intervals do not reflect.

See also [Limitations of the evaluation](limitations.md) and [Reproducing the experiments](reproduce.md).
