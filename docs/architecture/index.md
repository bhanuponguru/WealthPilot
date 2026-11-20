# Architecture

These pages describe how WealthPilot is built and why. They cover the structure of the deployed system, the underwriting workflow,
the components behind each step, and the design decisions that shape them. Start with [System design](system-design.md) for the
overall picture, then read the pages that match your interest.

| Page | What it covers |
|---|---|
| [System design](system-design.md) | Layers, the deployed topology, data stores and the rules about what the language model may and may not do |
| [Underwriting workflow](workflow.md) | Every step of the workflow, the routing conditions, the bounded loops and the two human gates |
| [Agents](agents.md) | The six agent roles: which call a language model, which call tools and which are plain code |
| [Decision rule](decision-rule.md) | How rule statuses become a recommendation, the degraded-run cap, the risk grade and the approver tier |
| [Policy retrieval](policy-retrieval.md) | How a policy written in prose is indexed, searched, read and verified |
| [Document parsing](document-parsing.md) | From a PDF, text or scanned, to verified numbers |
| [Risk model](risk-model.md) | The default-probability model, its training data, calibration and explanations |
| [Memory](memory.md) | Per-case checkpoints, applicant history and similar-case precedents |
| [Compliance and human approval](compliance.md) | Redaction, the language scan, the approval gate and the audit log |
| [Model gateway](model-gateway.md) | Caching, rate limiting, retries, circuit breakers, fallback and fault injection |
| [Tool servers](tool-servers.md) | The three tool servers and how the workflow calls them |
| [Observability](observability.md) | Traces, the call log and the audit log |
| [How the console is built](console.md) | Design goals, page structure, the background run worker and testing |
| [Design decisions](decisions.md) | The decision record: context, decision, rationale and consequences |
| [Developer guide](development.md) | Repository layout, local setup, tests, linting and extension points |

Deployment is covered in [Deploy with Docker](../get-started/deploy.md). The evaluation of the system, including measured
accuracy and reliability, is documented in the [Research](../research/index.md) section.
