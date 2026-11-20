# Developer guide

This guide is for people who change WealthPilot: it covers the repository layout, local setup, tests, linting, building the
documentation and the common extension points. Operators who only deploy the product need [Deploy with Docker](../get-started/deploy.md)
instead.

## Repository layout

The repository holds two Python packages in one uv workspace. The product is the root package. The research package is a workspace
member in `research/` that depends on the product, never the other way round. See
[Design decisions](decisions.md#d24-product-and-research-are-separate-packages).

```text
src/wealthpilot/       the product: workflow, console, gateway, parsing, retrieval, risk model, compliance, command-line interface
mcp_servers/           the three tool servers: fincalc, policydocs, research
policies/<id>/         one folder per credit policy; each holds policy.md and nothing else
artifacts/             the trained risk model, its metrics and the sector default statistics
config/                the compliance profile
data/                  runtime data: uploads, sanctions list, optional demonstration data (not committed)
.streamlit/            console settings: upload limit, theme
tests/                 product tests: unit, boundary, contract and live
scripts/               documentation tooling: screenshots, a navigation check, a Mermaid validator
docs/                  this documentation (MkDocs Material)
Dockerfile             one image for every service, plus a lab target for the research package
docker-compose.yml     the deployment
research/              the evaluation, a separate package
  src/wealthpilot_lab/   synthetic-data generator and the reference engine that holds the ground truth
  reference/             the hidden answer key for each policy
  experiments/           experiments E0 to E4
  results/               experiment results, including superseded runs
  scripts/               model probe and comparison tooling
  tests/                 research tests
```

| Part | Contains | Never contains |
|---|---|---|
| Product | Everything an organization deploys | Experiment code, answer keys, synthetic-data generators |
| Research | Generator, reference engine, experiments, results | Code that the product imports |

A boundary test enforces the separation. See [Tests](#tests).

## Set up

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), Docker for Postgres, and a model API key. Install the workspace with
the development tools:

```bash
uv sync --all-packages --group dev        # the product, the research package and the test tools
uv sync --all-packages --group dev --group docs   # add the documentation tools
```

Set the key as `NVIDIA_API_KEY` or `NVIDIA_NIM_API_KEY` in the shell, or in a `.env` file based on `.env.example`. The precedence is
the `.env` file, then the environment, then an error. See [Configuration](../get-started/configuration.md).

Start the services the product needs. The Makefile wraps the common commands:

| Command | What it does |
|---|---|
| `make up` | Starts Postgres with Docker Compose (published on `127.0.0.1:5432`) |
| `ollama serve` and `ollama pull nomic-embed-text` | Starts the local embeddings service outside Docker and fetches the model |
| `uv run wealthpilot mcp-up` | Starts the three tool servers as local processes |
| `make mlflow` | Optional: starts MLflow on `127.0.0.1:5000` with a SQLite backend |
| `make doctor` | Checks every service and artifact and prints the command that fixes anything missing |
| `make ui` | Starts the console on `127.0.0.1:8501` |
| `make down` | Stops the Compose services |

To try the product with sample applicants, generate the demonstration data with the research package (see
[Reproduce the experiments](../research/reproduce.md)) and start the console with `WEALTHPILOT_DEMO=1`. The full Docker deployment is
described in [Deploy with Docker](../get-started/deploy.md).

!!! note "Restart after code changes"
    A running Streamlit server keeps the modules it has loaded, and tool servers keep their own. Restart the console and the tool
    servers after editing code that they import.

## Tests

The suite splits into offline tests, which need no services, and live tests, which need the real stack. Live tests carry the `live`
marker declared in `pyproject.toml`.

```bash
uv run pytest -m "not live"      # offline tests, no services needed
uv run pytest -m live            # live tests: Postgres, the embeddings service, a model key and, for some, the tool servers
uv run pytest                    # everything
make test                        # quiet run of everything
```

The test paths cover the product tests in `tests/` and the research tests in `research/tests/`. A shared fixture turns on
demonstration mode for the whole suite, because the product ships with it off. Tests that use sample applicants need the
demonstration data in `data/demo/`.

| Area | Offline | Live | What is verified |
|---|---|---|---|
| Credit math | Yes | | Amortization, the DSCR definition, ratios, comparisons with missing data, the scorecard and the grade matrix |
| Decision rule | Yes | | Fail leads to decline, exception and missing data lead to refer, not applicable is ignored, and degraded runs never auto-decide |
| Reconciliation | Yes | | A consistent set passes, a broken balance sheet is flagged, bank balances roll forward |
| Redaction and compliance | Yes | | Name, ZIP and business-name redaction, whole-word matching, the prohibited-language scan |
| Memo validation helpers | Yes | | Unsupported numbers are detected while rule ids, years and small integers are exempt |
| Routing | Yes | | Every routing condition, including loop limits |
| Status mapping | Yes | | The model's answers map to the five statuses |
| Numeric verification | Yes | | Wrong comparisons are caught and malformed entries are ignored |
| Batch judge | Yes | | With the model and tool calls mocked: one call for a correct batch, a targeted re-ask after a wrong comparison, missing data if the re-ask is still wrong |
| Configuration | Yes | | Precedence of the `.env` file over the environment, blank values ignored, either key name |
| Boundary | Yes | | Product code never imports the research package, policy folders hold only the policy text, the console exposes exactly its six pages |
| Console | Yes | | Form validation, applicant building, uploads, exports, policy parsing, the case index, health checks, and that every page renders with or without services |
| Reference engine | Yes | | Research tests of the reference engine under both example policies |
| Gateway | | Yes | Chat with tools, cache hits, embeddings, rerank ordering, recovery from an injected `429`, fallback, the adaptive limiter |
| Tool contract | | Yes | The tool inventory, agreement between `fincalc` and the shared math, policy search, research tools. Needs the servers running |
| Console against the live stack | | Yes | Run a sample case, block an under-authorized approver, record a decision, check the case index, run a new application with uploaded PDFs |
| Audit chain | | Yes | Tampering is detected at exactly that record. The test appends a few records to the audit log |

### Writing tests

* Test routing and mapping offline. They are pure functions over state.
* To test code that calls the model, mock the JSON helper and the tool-call helper, as the batch-judge tests do.
* Mark anything that needs a model as live and keep it tolerant of API latency.

## Lint

```bash
uv run ruff check src mcp_servers tests research --select F,E9     # pyflakes and syntax errors
```

## Documentation

```bash
make docs          # live preview at http://127.0.0.1:8000
make docs-build    # strict build into ./site; fails on broken links and anchors
```

The strict build does not check Mermaid syntax. `scripts/check_mermaid.mjs` validates every diagram with the real Mermaid parser. It
needs two Node packages that are not project dependencies, and its header explains how to install them. The screenshots under
`docs/assets/screenshots/` come from `scripts/capture_screenshots.py`, which drives a real browser with Playwright against a running
console. Its header documents the recipe, including the scratch database it should use.

## Extending the product

### Add a credit policy

1. Create `policies/<id>/policy.md` with sections whose headings start with the rule ids, CP-1 to CP-13, following the
   [conventions](policy-retrieval.md#conventions-a-policy-must-follow).
2. Start the tool servers, or run `uv run wealthpilot ingest-policy`, so that the policy is indexed.
3. Select the policy on New case.

The `policies/` folder must hold policy text only, and a boundary test fails if it holds anything else. See
[Managing credit policies](../administration/policies.md) for the operator's view.

### Add a console page

Follow [Extending the console](console.md#extending-the-console). The page list is pinned by the boundary test, so update its
expected list in the same change.

### Add a tool

1. Add a function with a clear docstring to the right server under `mcp_servers/` and register it as a tool. The docstring is the
   description the model sees. Return an object, not a bare list.
2. Put any logic worth testing in a shared pure function so that the tool and the tests use the same code.
3. Register the tool name with its server in the workflow's tool table, so that calls are routed and protected by that server's
   circuit breaker.
4. Add the tool to the contract tests and document it in the [Tool reference](../reference/tool-reference.md).

### Change the compliance profile

Edit the profile file in `config/compliance_profiles/`. The language scan loads the list of prohibited terms from that file, so
replacing its contents applies another jurisdiction's terms. Rebuild the image to ship the change in a Docker deployment. See
[Compliance](compliance.md#language-scan).

### Add research

New experiments, generators and answer keys belong in the research package. They may import the product. The product must not import
them. See [Reproduce the experiments](../research/reproduce.md).
