# Financial Research Agent

An agentic financial research system that retrieves multi-source company data, extracts
factual claims, **independently verifies every claim against the original source text**,
flags disagreements between sources, and only then produces a structured research report.

Built as a 3rd-semester OJT project (GenAI track) by Suhrid Marwah and Ashnaa Seth.

## 1. Problem Statement

Financial analysts spend hours manually gathering data from SEC filings, earnings reports,
news, and financial data providers, then cross-checking whether cited numbers actually match
their sources. Errors and mis-citations routinely go undetected because verification doesn't
scale. This project builds an agentic system that automatically retrieves multi-source
financial data, generates a structured report, and **verifies every claim against its cited
source text** - flagging disagreements and assigning transparent confidence scores - so the
report is evidence-based rather than trust-based.

The core design principle: **the report is never trusted just because an LLM generated it.**
Every factual statement in the final report traces back to a `claim_id`, which traces to a
stored `Evidence` span (character offsets into a real, retrieved source document), which was
independently checked by a verification engine that never sees the report itself.

## 2. Architecture

```
User Query
    v
Query Planner (LLM decomposition + CompanyResolver)
    v
Research Orchestrator  <---------------------------+
    v                                               |
Multi-Source Retriever                              |
    +-- Web Search Adapter (Tavily / SerpAPI)        |
    +-- SEC EDGAR Adapter (primary filings)          |
    +-- Financial Data Adapter (Alpha Vantage/yfinance) |
    v                                               |
Source Store (raw text + char offsets preserved)     |
    v                                               |
Claim Extractor (LLM, numeric + qualitative)         |
    v                                               |
Claim Normalizer (deterministic: scale/currency/period/basis) |
    v                                               |
Verification Engine                                  |
    +-- Numeric Matcher (deterministic)              |
    +-- Entailment Checker (LLM, evidence-only)       |
    v                                               |
Conflict Detector (basis/period/unit-aware)          |
    v                                               |
Confidence Scorer (transparent weighted formula)     |
    v                                               |
Evidence Sufficiency Check (Follow-Up Research Loop) -+  (bounded iterations)
    v
Report Generator (templated + one constrained LLM section)
    v
Final Verified Report
```

This mirrors the PRD's high-level and low-level design diagrams: `query_planner`,
`research_orchestrator`, `source_retriever` (+ `web_search_adapter` / `financial_api_adapter`
/ `sec_edgar`), `claim_extractor`, `verification_engine` (+ `numeric_matcher` /
`entailment_checker`), `conflict_detector`, `confidence_scorer`, `report_generator`, and a
storage layer with distinct `source` / `claim` / `evidence` / `verification_results` /
`conflicts` / `research_runs` / `reports` tables.

### Why not LangChain?

The stack list mentions LangChain, but this project deliberately implements a small custom
`LLMProvider` abstraction (`app/llm/`) and direct orchestration instead. Reasoning: the
pipeline's core requirement is exact control over structured Pydantic outputs, verbatim
evidence-span provenance, and strict context isolation between synthesis and verification
(see "verifier grading its own homework" below) - a thin, auditable direct-API layer makes
those guarantees easier to verify by reading the code than routing through a general-purpose
agent framework's abstractions would. This is a documented simplification, not an oversight.

## 3. Technology Stack

- **Python 3.11+**, FastAPI, Pydantic v2
- **LLM**: Claude API (`anthropic` SDK) or OpenAI API, behind a swappable `LLMProvider`
- **Web search**: Tavily or SerpAPI, behind a swappable `SearchProvider`
- **Financial data**: SEC EDGAR (XBRL company facts, no key required) as the primary-filing
  source; Alpha Vantage or yfinance as the structured financial-API source
- **Storage**: SQLite (via SQLAlchemy), with a repository layer separating sources / claims /
  evidence / verification results / conflicts / research runs / reports
- **Frontend**: React 18 + TypeScript + Vite, served from the FastAPI app's built `frontend/dist` bundle
- **Testing**: pytest, with a fully mocked end-to-end path (no live API dependency)
- **Deployment**: Docker / docker-compose

Every external integration sits behind an adapter interface so a provider can be swapped
(or entirely absent) without touching the core agent logic:

```
LLMProvider          SearchProvider         FinancialDataProvider
  |- ClaudeProvider     |- TavilyProvider      |- AlphaVantageProvider
  |- OpenAIProvider     |- SerpAPIProvider     |- YFinanceProvider
  (mock: see below)     |- MockSearchProvider  |- MockFinancialDataProvider
                                                (SEC EDGAR handled separately, primary-filing tier)
```

## 4. Project Structure

```
financial-research-agent/
├── app/
│   ├── api/routes.py            # FastAPI endpoints
│   ├── agents/                  # query_planner, research_orchestrator, followup_research
│   ├── retrieval/                # base, company_resolver, web_search, sec_edgar, financial_data, source_retriever
│   ├── extraction/claim_extractor.py
│   ├── verification/             # verification_engine, numeric_matcher, entailment_checker
│   ├── analysis/                 # normalizer, conflict_detector, confidence_scorer
│   ├── generation/report_generator.py
│   ├── storage/                  # database, models, repositories
│   ├── llm/                      # LLMProvider + Claude/OpenAI implementations
│   ├── schemas/                  # canonical Pydantic models
│   └── config.py
├── frontend/                     # index.html, style.css, app.js,React 18 + TypeScript + Vite
├── tests/                        # pytest: unit + integration + adversarial + e2e
├── evaluation/                   # hand-labelled eval sets, calibration, run_evaluation.py
├── sample_data/                  # bundled company directory + mock fixtures
├── Dockerfile / docker-compose.yml
├── requirements.txt
└── .env.example
```

## 5. Setup

```bash
cd financial-research-agent
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
copy .env.example .env        # Windows: copy, macOS/Linux: cp
```

The app runs **without any API keys** in DEMO_MODE (the default) - see section 8.

### Environment Variables

See `.env.example` for the full list. Key ones:

| Variable | Purpose |
|---|---|
| `DEMO_MODE` | `true` forces deterministic mock providers everywhere (default) |
| `LLM_PROVIDER` | `claude` or `openai` |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | LLM credentials |
| `SEARCH_PROVIDER` | `tavily` or `serpapi` |
| `TAVILY_API_KEY` / `SERPAPI_API_KEY` | Web search credentials |
| `ALPHAVANTAGE_API_KEY` | Optional; falls back to yfinance (no key) if unset |
| `SEC_EDGAR_USER_AGENT` | Required by SEC's fair-access policy for EDGAR requests |
| `MAX_FOLLOWUP_ITERATIONS`, `MAX_RESEARCH_QUERIES` | Bounds on the follow-up research loop |

## 6. Running Locally

```bash
cd frontend
npm install
npm run build
cd ..
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000` for the web UI, or `http://localhost:8000/docs` for the
interactive API docs.

For frontend-only development with hot reload, run the backend on port 8000 and then:

```bash
cd frontend
npm run dev
```

The Vite dev server proxies `/api` requests to `http://localhost:8000`.

## 7. Running with Docker

```bash
copy .env.example .env   # edit in real API keys if you have them, otherwise leave as-is
docker compose up --build
```

The app is available at `http://localhost:8000`. The SQLite database persists in `./data`
via a bind mount.

## 8. Demo Mode

`DEMO_MODE=true` (the default, and the automatic fallback whenever no LLM key is configured)
makes every provider use a deterministic, clearly-labelled mock implementation instead of a
live API call:

- Mock sources always have `source_type=mock` and `source_tier=mock`, and their
  `document_text` is prefixed with `[MOCK ... - DEMO MODE, NOT A REAL ...]`.
- Mock claim extraction uses real regex parsing over that mock text (not fabricated numbers) -
  every evidence span still points at real, stored text.
- Mock verification (`NumericMatcher` is always deterministic regardless of mode;
  `EntailmentChecker`'s mock path reuses the same numeric-matching logic for numeric claims
  and a text-overlap heuristic for qualitative claims).

**The system never presents mock data as if it came from a real SEC filing, web search, or
financial API.** As soon as real API keys are configured and `DEMO_MODE=false`, each provider
switches to its live implementation automatically (with mock as a safety-net fallback if a
live call fails, so one flaky API doesn't take down the whole run - the resulting source is
still tagged with its provider's normal tier, since it succeeded).

## 9. API

| Endpoint | Description |
|---|---|
| `POST /api/research` | Runs the full pipeline for a query, returns the `ResearchRun` |
| `GET /api/research/{id}` | Fetch a research run's status/plan |
| `GET /api/research/{id}/claims` | All extracted + verified claims |
| `GET /api/research/{id}/sources` | All retrieved sources (with full text + provenance) |
| `GET /api/research/{id}/conflicts` | Detected conflicts between sources |
| `GET /api/research/{id}/report` | The generated structured report |
| `GET /api/health` | Health check + current provider/mode configuration |

### Example queries

```
Analyze Apple Q3 2024
Analyze Microsoft's revenue, profitability and major risks for FY2024
Analyze NVIDIA revenue and profitability
Compare Apple and Microsoft
```

The system is **company-agnostic**: company names are resolved dynamically via
`CompanyResolver` (backed by SEC EDGAR's public ticker directory when online, or a small
bundled sample directory in demo mode) - there is no `if company == "Apple"` branching
anywhere in the codebase.

## 10. Testing

```bash
pytest tests/ -v
```

59 tests covering the query planner, normalization, claim extraction (evidence-span
integrity), the numeric matcher, the entailment checker, conflict detection, confidence
scoring, report generation, the bounded follow-up loop, dedicated adversarial cases (wrong
number / wrong unit / wrong period / GAAP vs non-GAAP / quarterly vs annual), and one
fully-mocked end-to-end test through the real FastAPI app (no live API dependency).

## 11. Evaluation Harness

```bash
python -m evaluation.run_evaluation
```

Runs the hand-labelled evaluation sets (`evaluation/labeled_eval_set.py`,
`evaluation/conflict_eval_set.py`) through the real pipeline modules and writes
`evaluation/results/latest_report.json`. This is also wired into `pytest` as
`tests/test_evaluation_harness.py`, so the numbers below are re-measured on every test run,
never just claimed:

- **Citation verification coverage**: 100% (every claim in the eval set is run through the
  verification engine by construction)
- **Verification accuracy / Brier score / calibration curve**: computed from ~74 hand-labelled
  claim/evidence pairs across scenario types (exact match, scale-equivalent match, wrong
  number, wrong unit, wrong period, no-mention, qualitative support/no-support)
- **Conflict detection precision/recall**: computed from 15 hand-labelled claim-pair
  scenarios (genuine disagreement, basis mismatch, period mismatch, currency mismatch,
  within-tolerance agreement)

**Methodology note**: given the scope of an 8-week OJT project, this evaluation set is
constructed by the developers from parameterized scenario templates rather than independently
crowd-sourced - each scenario type deterministically implies its correct label by
construction (e.g. a "wrong_number" case is always CONTRADICTED), so the labels are
documented ground truth, not guesses. This makes the harness fully reproducible without any
external annotation effort, at the cost of not being a fully independent validation set - see
Known Limitations.

## 12. Confidence Scoring Methodology

Confidence is a transparent weighted sum of four independently-computable components
(`app/analysis/confidence_scorer.py`), never an LLM asked to "grade" its own claim:

| Component | Weight | What it measures |
|---|---|---|
| `source_quality` | 0.25 | Source tier (primary filing 1.0 → aggregator 0.45 → mock 0.5) |
| `evidence_match` | 0.30 | How exactly the claim's value matches the evidence (exact / normalized / mismatch) |
| `corroboration` | 0.20 | How many *other* sources independently report a compatible value |
| `entailment` | 0.25 | The entailment checker's own confidence in its verdict |

`confidence` means **the system's confidence in its verification verdict**, not "how likely
the underlying fact is true" - a confidently CONTRADICTED claim (a caught error) scores highly
too, since the system is sure it caught it.

## 13. Retrieval vs Extraction vs Verification vs Conflict Detection vs Confidence Scoring vs Synthesis

These are five genuinely distinct pipeline stages, each with a narrow responsibility -
important for the viva:

1. **Retrieval** (`app/retrieval/`): fetches raw documents from external sources and stores
   them verbatim with provenance metadata. Never interprets or summarizes content.
2. **Extraction** (`app/extraction/`): reads a *single* source's raw text and pulls out
   discrete factual claims, each anchored to an exact character span in that source. Never
   compares across sources.
3. **Verification** (`app/verification/`): re-examines *one claim against its own source
   evidence only* (never the report, never other claims) via two independent paths - a
   deterministic numeric matcher and an LLM entailment checker - and produces a verdict.
4. **Conflict Detection** (`app/analysis/conflict_detector.py`): compares *already-verified,
   normalized* claims about the same entity+metric *across different sources*, and
   distinguishes a genuine disagreement from a period/basis/currency mismatch that merely
   looks like one.
5. **Confidence Scoring** (`app/analysis/confidence_scorer.py`): combines source quality,
   evidence match quality, cross-source corroboration, and entailment confidence into one
   transparent number per claim - it does not re-verify anything.
6. **Synthesis** (`app/generation/report_generator.py`): assembles the already-verified,
   already-scored claims into report sections. Every fact in the report is a direct rendering
   of a `Claim` object; the one LLM-assisted section (the executive overview paragraph) is
   constrained to only cite already-verified claims and its cited `claim_id`s are validated
   against the real claim set afterwards.

The critical isolation: **the Verification stage never sees the Synthesis stage's output.**
This is what prevents the "verifier grading its own homework" failure mode explicitly called
out in the PRD (section 5.1.4) - the entailment checker is given only a claim and its raw
evidence text, with no report context at all.

## 14. Known Limitations

- **Mock-mode data is generic**: in `DEMO_MODE`, mock financial figures are the same
  illustrative numbers regardless of which company was requested (no real API is being
  called), so a demo comparison between two companies will show identical mock figures for
  both. This is intentional and clearly labelled - it goes away the moment real API keys are
  configured.
- **Mock qualitative entailment cannot detect CONTRADICTED**: the deterministic mock
  entailment path for qualitative (non-numeric) claims only distinguishes SUPPORTED vs
  INSUFFICIENT (a text-overlap heuristic can't reliably detect semantic negation/contradiction
  without an LLM). With a real LLM key configured, the entailment prompt does support
  qualitative CONTRADICTED verdicts.
- **The evaluation set is self-constructed** (see section 11) rather than independently
  annotated; a 100% score on it demonstrates internal consistency and guards against
  regressions, not generalization to arbitrary unseen real-world text.
- **No FX conversion**: claims in different currencies (e.g. USD vs INR) are correctly
  detected as non-comparable and reported as an explained (non-genuine) conflict, but the
  system does not perform currency conversion to compare them directly.
- **Web-source tiering is a domain allowlist heuristic** (`app/retrieval/web_search.py`):
  a small set of well-known publication domains is promoted to `PRESS` tier; everything else
  defaults to `AGGREGATOR`, since a generic web search API gives no stronger reputation
  signal than the source domain.
- **SEC EDGAR / Alpha Vantage / yfinance coverage** depends on the company being a
  US-listed/SEC-registered entity with a resolvable CIK/ticker; non-US companies (e.g.
  Reliance Industries) will have gaps in primary-filing and financial-API coverage and rely
  more heavily on web search results, which the system surfaces transparently as fewer
  sources rather than failing.

## 15. Observability

Every stage logs through Python's standard `logging` module under the `financial_research_agent.*`
logger hierarchy (configured in `app/main.py`, level via `LOG_LEVEL`): each research run's start
and completion (source/claim/conflict counts and the SUPPORTED/CONTRADICTED/INSUFFICIENT
breakdown), each retrieval batch's source count, each follow-up iteration, and any failure
(via `logger.exception`, with the full traceback but never a request payload or API key).
Structured `%s`-style fields (not string-concatenated messages) keep log lines easy to parse
or pipe into an aggregator. The codebase does not currently wire up actual OpenTelemetry
spans/exporters (the PRD lists this as "where practical," and for an 8-week single-process
project the log-based approach above already gives the same operational visibility) - the
logger boundaries above are exactly where OTel spans would be added first if this were
deployed as a real service.

## 16. Milestone Checklist (against the PRD)

| PRD Requirement | Status |
|---|---|
| Multi-source retrieval (web + financial APIs) | Implemented (`app/retrieval/`) |
| Source text + character-offset provenance | Implemented (`Evidence.start_char/end_char`, tested) |
| Canonical claim schema | Implemented (`app/schemas/claim.py`) |
| Dual-path verification (numeric + LLM entailment) | Implemented (`app/verification/`) |
| Conflict detection with basis/period/unit awareness | Implemented + tested |
| Transparent, component-based confidence scoring | Implemented + tested |
| Follow-up research loop with bounded iterations | Implemented + tested (`test_followup_loop.py`) |
| Multi-company comparison | Implemented (`ComparisonTable` in reports) |
| Hand-labelled evaluation harness | Implemented (`evaluation/`) |
| Adversarial testing | Implemented (`tests/test_adversarial.py`) |
| Calibration curve + Brier score | Implemented (`evaluation/calibration.py`) |
| Company-agnostic (no hardcoded company logic) | Implemented (`CompanyResolver`) |
| DEMO_MODE / mock providers, clearly labelled | Implemented across all adapters |
| Dockerized | Implemented (`Dockerfile`, `docker-compose.yml`) |
