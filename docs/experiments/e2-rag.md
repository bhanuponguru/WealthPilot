# E2 · Policy RAG

**Question.** Which retrieval design most reliably finds the policy rule that answers a question — and how much does each component
(chunking, BM25, dense vectors, fusion, reranking) contribute?

## Method

* **Gold set:** 104 queries = 13 rules × 4 phrasings × 2 policies. Each rule has two *direct* questions ("What is the minimum DSCR?") and two *paraphrased or scenario*
  questions ("cash flow is thin compared with the loan payments; what does the policy say"). The correct answer is the section for that rule id.
* **Hit:** the gold rule id is among the rules the retrieved chunk covers. (For *fixed* windows, which can span rules, this is generous.)
* **Metrics:** recall@1, recall@3, MRR, with a 95 % bootstrap interval on MRR.
* **Arms:** chunking {structure-aware, fixed windows} × retrieval {BM25, dense, hybrid RRF} × reranking {off, NIM reranker} — 10 combinations.
  See [Credit policy and RAG](../concepts/policy-rag.md#retrieval).

## Results

| Chunking | Retrieval | Rerank | recall@1 | recall@3 | MRR | MRR 95 % CI |
|---|---|---|---|---|---|---|
| structure | BM25 | – | 0.798 | 0.856 | 0.822 | 0.750–0.894 |
| structure | dense | – | 0.740 | 0.904 | 0.821 | 0.758–0.885 |
| structure | hybrid | – | 0.769 | 0.885 | 0.819 | 0.752–0.883 |
| structure | BM25 | NIM | 0.923 | 0.923 | 0.923 | 0.865–0.971 |
| structure | dense | NIM | 0.942 | 0.942 | 0.942 | 0.894–0.981 |
| structure | **hybrid** | **NIM** | **0.971** | **0.971** | **0.971** | 0.933–1.000 |
| fixed | BM25 | – | 0.625 | 0.856 | 0.732 | 0.657–0.803 |
| fixed | dense | – | 0.683 | 0.904 | 0.779 | 0.710–0.845 |
| fixed | hybrid | – | 0.673 | 0.923 | 0.790 | 0.728–0.853 |
| fixed | hybrid | NIM | 0.923 | 0.990 | 0.954 | 0.920–0.984 |

The reranker was available throughout (`rerank_degraded = 0` in every arm).

## Findings

1. **Reranking is the dominant lever.** Adding the NIM reranker to hybrid search lifts recall@1 from **0.77 to 0.97**. First-stage retrieval puts the right rule in the
   top three 86–90 % of the time but often not first; the cross-encoder sorts it.
2. **Structure-aware chunking beats fixed windows — until a reranker is added.** Without reranking, fixed windows have much lower recall@1 (0.63–0.68 vs 0.74–0.80): a window cuts rules in
   the middle and mixes neighbours. With a reranker the gap narrows (0.92 vs 0.97).
3. **Hybrid fusion did not beat BM25 here without a reranker** (0.769 vs 0.798 recall@1, intervals overlap). The corpus is small and keyword-rich, so exact terms ("DSCR", "collateral") carry most of the signal.
4. **Hybrid + rerank is the best and most consistent**, and is what the system uses.

## How this connects to E0

In the end-to-end system retrieval is **done by code for every rule**, with `get_rule` as a fallback when a rule's own section is missing from the top results, so a retrieval miss
degrades into an extra call rather than a wrong answer. The 97 % first-hit rate means that fallback is rarely needed.

## Caveats

* A small, clean, two-document corpus; larger or messier policy libraries will be harder, and the dense component may matter more.
* Gold labels are section-level; a query that legitimately spans two rules counts as a hit for either.
* Dense embeddings come from a small local model (`nomic-embed-text`) because no NIM embedding model worked for the account.

## Reproduce

```bash
cd experiments && CHAT_FALLBACK_MODEL="" uv run python e2_rag.py       # ~520 rerank calls; minutes with a warm cache
```
