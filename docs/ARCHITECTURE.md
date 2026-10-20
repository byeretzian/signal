# Architecture

## Context

Signal must answer natural-language music questions without delegating numerical truth to an LLM.
Milestone 1 proves the central execution loop while keeping local setup and failure diagnosis simple.

```text
Next.js web
    │ JSON/HTTP
    ▼
FastAPI modular monolith
    ├── catalog repositories ─────────┐
    ├── deterministic analytics ──────┼── PostgreSQL
    ├── LangGraph orchestration ──────┘
    ├── MusicBrainz provider ─────────── MusicBrainz API
    └── ListenBrainz provider ────────── ListenBrainz API
```

## Decisions

### Modular monolith first

Directories named `services` are domain boundaries, not independent deployments. FastAPI assembles
them in one process. This preserves simple database transactions, a fast test loop, and one local
debugging surface. A boundary should become a service only when scaling or ownership evidence calls
for it.

### Provider-neutral domain

`ArtistMetadataProvider`, `ReleaseMetadataProvider`, and `ListeningMetricsProvider` protocols return
Pydantic normalized models. Provider wire models and response quirks stay inside their adapters.
Provider identifiers have their own relational tables instead of provider-named columns.

### Explicit imports

Artist search is a read-only GET. Persistence is an explicit POST using a selected MusicBrainz ID.
This avoids surprising GET side effects and makes retries and idempotency clear.

### Deterministic analytics

`calculate_growth` reads two persisted endpoint snapshots and returns a typed `GrowthResult`.
It owns range validation, nearest-date tolerance, missing values, and zero denominators. Neither the
prompt nor the response formatter performs the formula.

### Narrow LangGraph

The graph has four responsibilities: interpret, route, execute, and present. The interpreter returns
a strict `QuestionPlan`. The execution node calls the deterministic function and records tool name,
arguments, success, and duration. Unsupported requests take a branch that calls no tool and states
the limitation.

If `OPENAI_API_KEY` is present, the interpreter uses the configured OpenAI chat model with structured
output. Otherwise a narrow offline interpreter supports the documented growth question. This keeps
local development and CI useful without disguising the fallback as a general LLM.

The tool-calling design follows the official OpenAI model: tools have schema-constrained arguments,
the application executes them, and resulting data grounds the response. The relevant official guide
is https://developers.openai.com/api/docs/guides/function-calling.

### MCP as transport, not business logic

Milestone 1 keeps the tool in-process. A future MCP server will translate protocol requests to the
same typed catalog and analytics functions. No SQL or formulas should be reimplemented in an MCP
handler.

## Reliability

MusicBrainz requests use:

- A meaningful configured `User-Agent`.
- A shared one-request-per-second limiter.
- Explicit timeout.
- Bounded exponential retry for network errors, 429, and transient 5xx responses.
- Typed validation and structured provider exceptions.
- Structured timing logs.

ListenBrainz artist popularity uses its typed batch endpoint with one MusicBrainz artist ID per
refresh. The adapter sends an optional user token, honors `X-RateLimit-Reset-In` on retries, validates
the returned artist ID and nonnegative counts, and records the cumulative metric semantics in
snapshot metadata. Refreshing the same artist twice on one calendar day updates the existing row.

API requests receive correlation IDs. Agent runs receive run IDs. Tool and provider calls record
duration and outcome without logging credentials.

## Failure semantics

| Failure | Behavior |
| --- | --- |
| Database health failure | `/health` returns 503 |
| MusicBrainz transient exhaustion | API returns 502 with structured detail |
| Invalid MusicBrainz JSON shape | Provider response error; nothing persisted |
| ListenBrainz transient exhaustion | API returns 502; no snapshot is committed |
| Missing MusicBrainz artist ID | Metrics refresh returns 409 |
| Artist absent | API returns 404 |
| Missing snapshots | Tool returns `insufficient_data` |
| Zero starting metric | Absolute change returned; percentage explicitly undefined |
| Unsupported question | No tool execution; limitation returned |

## Future seams

- Schedule recurring ListenBrainz refreshes after the manual ingestion seam is proven.
- Add a cache implementation behind the provider rather than inside routes.
- Expose tools via MCP.
- Persist agent/tool run events to an observability store.
- Execute JSONL evaluation cases against graph traces.
- Split deployments only when operational evidence supports it.
