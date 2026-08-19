# Signal

Signal is an evidence-backed music intelligence platform for investigating artists, releases,
labels, and listening trends with natural language. It combines normalized provider data,
deterministic analytics, and a LangGraph agent that shows which tools actually ran.

Milestone 1 is a production-minded vertical slice: search MusicBrainz, persist an artist and basic
releases, attach clearly labeled synthetic demonstration snapshots, and ask how the artist changed
over 30 days. The LLM plans the request; SQL/Python performs the calculation.

## Why it exists

Music questions often mix catalog knowledge with numerical claims. Signal separates those concerns:
provider adapters normalize external data, analytics functions calculate important statistics, and
the agent explains verified tool output. When data is absent, it says so.

## Current capabilities

- Search artists using the MusicBrainz JSON API.
- Import normalized artist and release metadata idempotently.
- Persist provider-neutral external identifiers in PostgreSQL.
- Calculate listener or listen-count growth from stored snapshots.
- Route growth questions through a LangGraph workflow and record tool arguments and duration.
- Use an OpenAI-backed structured planner when configured, with a deterministic offline fallback.
- Explore the complete slice in a responsive Next.js interface.

## Architecture

Signal is currently a modular monolith. Next.js calls FastAPI; FastAPI assembles catalog,
analytics, ingestion, and agent modules; PostgreSQL is the system of record. Module boundaries are
transport-independent so MCP adapters can later expose the same tools without copying logic.

See [Architecture](docs/ARCHITECTURE.md) and [Data model](docs/DATA_MODEL.md).

## Run with Docker

Prerequisites: Docker Desktop and Docker Compose.

```bash
cp .env.example .env
# Replace MUSICBRAINZ_CONTACT and MUSICBRAINZ_USER_AGENT with real contact information.
docker compose up --build
```

Then open:

- Web: http://localhost:3000
- API documentation: http://localhost:8000/docs
- Health: http://localhost:8000/health

The API service applies Alembic migrations at startup. Importing an artist attaches 31 synthetic
`demo` snapshots so the Milestone 1 analytics workflow can be exercised. Responses visibly identify
that these are demonstration values and not MusicBrainz listening data.

To seed a standalone demo artist manually:

```bash
docker compose exec api python -m signal_app.seed
```

## Run tests locally

Python 3.12 and Node.js 22 LTS are the project targets.

```bash
python -m venv .venv
source .venv/bin/activate
pip install '.[dev]'
pytest
ruff check .
mypy src

npm install
npm run lint:web
npm run typecheck:web
npm run build:web
```

Automated tests mock external HTTP. They do not consume MusicBrainz or OpenAI quota.

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Yes | SQLAlchemy PostgreSQL connection URL |
| `MUSICBRAINZ_USER_AGENT` | Yes | App/version plus valid maintainer contact |
| `MUSICBRAINZ_CONTACT` | Yes | Documented maintainer contact |
| `MUSICBRAINZ_BASE_URL` | No | Defaults to the public v2 API |
| `MUSICBRAINZ_TIMEOUT_SECONDS` | No | External request timeout |
| `OPENAI_API_KEY` | No | Enables LLM structured planning |
| `OPENAI_MODEL` | No | Model used only for question planning |
| `CORS_ORIGINS` | No | Comma-separated trusted web origins |
| `NEXT_PUBLIC_API_BASE_URL` | Yes for web | Browser-visible API origin |

MusicBrainz read access does not require an API key, but its public service requires a meaningful
User-Agent and at most one request per second. Never commit `.env` or credentials.

Without `OPENAI_API_KEY`, the complete growth workflow remains usable through a deliberately narrow
rule-based interpreter. Tests always use that deterministic path. With a key, the agent uses a
strict structured output schema to choose the supported action and arguments; the calculation is
still performed only by `calculate_growth`.

## API workflow

1. `GET /artists/search?q=...` returns MusicBrainz candidates without mutating state.
2. `POST /artists/import/{musicbrainz_id}` explicitly persists the chosen artist and releases.
3. `GET /artists/{id}` retrieves the normalized record.
4. `POST /query` accepts a question, artist ID, metric source, and optional end date.

Example query body:

```json
{
  "question": "How much has this artist grown over the last 30 days?",
  "artist_id": "018f79ad-cbb0-7df9-8bd3-610467f94634",
  "source": "demo"
}
```

The response includes the answer, endpoint snapshots, percentage and absolute change, sources,
caveats, run ID, and verified tool trace.

## Roadmap

- Replace demonstration snapshots with ListenBrainz ingestion.
- Add genre/style, label, track, and richer artist-credit models.
- Add MCP transport adapters over the typed catalog and analytics tools.
- Add 7/30/90-day acceleration, peer percentiles, anomaly detection, and ranking.
- Expand the evaluation runner and observability backend.
- Deploy the web app to Vercel and container workloads to Azure Container Apps with managed
  PostgreSQL and Terraform.

Deployment and the broader scoring system are intentionally outside Milestone 1.
