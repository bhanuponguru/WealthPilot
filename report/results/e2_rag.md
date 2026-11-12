# E2: Policy RAG ablation

| arm | n_queries | recall@1 | recall@3 | MRR | MRR_95CI | rerank_degraded |
|---|---|---|---|---|---|---|
| structure/bm25 | 104 | 0.798 | 0.856 | 0.822 | 0.75-0.8942 | 0 |
| structure/dense | 104 | 0.74 | 0.904 | 0.821 | 0.758-0.8846 | 0 |
| structure/hybrid | 104 | 0.769 | 0.885 | 0.819 | 0.7516-0.883 | 0 |
| structure/bm25+rerank | 104 | 0.923 | 0.923 | 0.923 | 0.8654-0.9712 | 0 |
| structure/dense+rerank | 104 | 0.942 | 0.942 | 0.942 | 0.8942-0.9808 | 0 |
| structure/hybrid+rerank | 104 | 0.971 | 0.971 | 0.971 | 0.9327-1.0 | 0 |
| fixed/bm25 | 104 | 0.625 | 0.856 | 0.732 | 0.6571-0.8029 | 0 |
| fixed/dense | 104 | 0.683 | 0.904 | 0.779 | 0.7099-0.8446 | 0 |
| fixed/hybrid | 104 | 0.673 | 0.923 | 0.79 | 0.7276-0.8526 | 0 |
| fixed/hybrid+rerank | 104 | 0.923 | 0.99 | 0.954 | 0.9199-0.984 | 0 |
