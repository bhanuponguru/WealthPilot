# Concepts

These pages explain *how WealthPilot works and why it is built that way*. Read them in order for a complete picture, or jump to
the part you need.

| Page | What it explains |
|---|---|
| [Architecture](architecture.md) | The layers, processes and data stores, and the rules about what an LLM may and may not do |
| [The underwriting workflow](workflow.md) | Every node of the LangGraph graph, the routing predicates and the bounded loops |
| [Agents and tools](agents.md) | The six agent roles — which call an LLM, which call tools, which are plain code |
| [The decision rule](decision-rule.md) | How rule statuses become a recommendation, the risk grade, approver tiers and the degraded-run cap |
| [Credit policy and RAG](policy-rag.md) | How a policy written in prose is indexed, retrieved, read and verified |
| [Document parsing](document-parsing.md) | From PDF (text or scan) to verified numbers |
| [Risk model](risk-model.md) | The SBA-trained default model, calibration, SHAP reasons, scorecard and grade matrix |
| [Memory](memory.md) | Per-case checkpoints, long-term applicant memory and similar-case precedents |
| [Compliance and human approval](compliance.md) | Redaction, the memo validator, the approval gate and the audit log |
| [NIM gateway and reliability](nim-gateway.md) | Cache, adaptive rate limit, retries, breakers, fallback and fault injection |
| [MCP servers](mcp-servers.md) | The three tool servers and how the graph consumes them |
| [Observability](observability.md) | Traces, the call log, experiment runs and the audit trail |
| [The console (implementation)](user-interface.md) | How the Streamlit console is built: the case index, sessions, fail-fast health checks, forms and tests |
