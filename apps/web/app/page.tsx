"use client";

import { FormEvent, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type SearchArtist = {
  external_id: string;
  name: string;
  country: string | null;
  disambiguation: string | null;
  score: number | null;
};

type PersistedArtist = {
  id: string;
  name: string;
  country: string | null;
  external_ids: Record<string, string>;
};

type QueryResult = {
  run_id: string;
  answer: string;
  supporting_data: {
    metric: string;
    source: string;
    start: { actual_date: string | null; value: number | null };
    end: { actual_date: string | null; value: number | null };
    absolute_change: number | null;
    percentage_change: number | null;
    status: string;
  } | null;
  tools: Array<{ tool: string; duration_ms: number; success: boolean }>;
  caveats: string[];
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export default function Home() {
  const [search, setSearch] = useState("");
  const [candidates, setCandidates] = useState<SearchArtist[]>([]);
  const [artist, setArtist] = useState<PersistedArtist | null>(null);
  const [question, setQuestion] = useState("How much has this artist grown over the last 30 days?");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [busy, setBusy] = useState<"search" | "import" | "query" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submitSearch(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy("search");
    try {
      setCandidates(await api<SearchArtist[]>(`/artists/search?q=${encodeURIComponent(search)}`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Search failed");
    } finally {
      setBusy(null);
    }
  }

  async function selectArtist(candidate: SearchArtist) {
    setError(null);
    setBusy("import");
    try {
      const imported = await api<{ artist: PersistedArtist }>(
        `/artists/import/${candidate.external_id}?include_demo_metrics=true`,
        { method: "POST" },
      );
      setArtist(imported.artist);
      setCandidates([]);
      setResult(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Import failed");
    } finally {
      setBusy(null);
    }
  }

  async function askSignal(event: FormEvent) {
    event.preventDefault();
    if (!artist) {
      setError("Search for and select an artist first.");
      return;
    }
    setError(null);
    setBusy("query");
    try {
      setResult(
        await api<QueryResult>("/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question, artist_id: artist.id, source: "demo" }),
        }),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Signal could not answer the question");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main>
      <header>
        <a className="brand" href="#top" aria-label="Signal home">
          <span className="mark" aria-hidden="true"><i /><i /><i /><i /></span>
          SIGNAL
        </a>
        <span className="edition">MUSIC INTELLIGENCE / M1</span>
      </header>

      <section className="hero" id="top">
        <p className="eyebrow">Evidence over instinct</p>
        <h1>Find the signal<br />in the <em>noise.</em></h1>
        <p className="intro">
          Investigate artists and growth with normalized catalog data, deterministic analytics,
          and an agent that shows its work.
        </p>
      </section>

      <section className="workspace" aria-label="Signal investigation workspace">
        <div className="step">
          <span>01</span>
          <div>
            <h2>Choose an artist</h2>
            <p>Search MusicBrainz and persist a normalized catalog record.</p>
          </div>
        </div>
        <form className="search-form" onSubmit={submitSearch}>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search an electronic music artist"
            minLength={2}
            required
            aria-label="Artist search"
          />
          <button disabled={busy !== null}>{busy === "search" ? "Searching…" : "Search"}</button>
        </form>

        {candidates.length > 0 && (
          <div className="results-list">
            {candidates.map((candidate) => (
              <button key={candidate.external_id} onClick={() => selectArtist(candidate)}>
                <span><strong>{candidate.name}</strong><small>{candidate.disambiguation || "Artist"}</small></span>
                <span>{candidate.country ?? "—"} <b>↗</b></span>
              </button>
            ))}
          </div>
        )}

        {artist && (
          <div className="selected">
            <span className="status-dot" />
            <span><small>Selected artist</small><strong>{artist.name}</strong></span>
            <code>{artist.external_ids.musicbrainz?.slice(0, 8)}…</code>
          </div>
        )}

        <div className="rule" />

        <div className="step">
          <span>02</span>
          <div>
            <h2>Ask Signal</h2>
            <p>The agent selects a verified analytics tool; arithmetic stays deterministic.</p>
          </div>
        </div>
        <form className="query-form" onSubmit={askSignal}>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            aria-label="Question for Signal"
            rows={3}
            required
          />
          <button disabled={busy !== null || !artist}>
            {busy === "query" ? "Investigating…" : "Ask Signal"}<span>→</span>
          </button>
        </form>

        {error && <div className="error" role="alert"><strong>Request failed</strong>{error}</div>}

        {result && (
          <article className="answer">
            <div className="answer-head"><span>Answer</span><code>RUN {result.run_id.slice(0, 8)}</code></div>
            <h3>{result.answer}</h3>
            {result.supporting_data && (
              <div className="metrics">
                <div><small>Start</small><strong>{result.supporting_data.start.value?.toLocaleString() ?? "—"}</strong><span>{result.supporting_data.start.actual_date}</span></div>
                <div><small>End</small><strong>{result.supporting_data.end.value?.toLocaleString() ?? "—"}</strong><span>{result.supporting_data.end.actual_date}</span></div>
                <div className="accent"><small>Growth</small><strong>{result.supporting_data.percentage_change?.toFixed(2) ?? "—"}%</strong><span>{result.supporting_data.metric.replace("_", " ")}</span></div>
              </div>
            )}
            <div className="trace">
              <span>Analysis details</span>
              {result.tools.map((tool) => <code key={tool.tool}>✓ {tool.tool} · {tool.duration_ms}ms</code>)}
            </div>
            {result.caveats.map((caveat) => <p className="caveat" key={caveat}>Note: {caveat}</p>)}
          </article>
        )}
      </section>

      <footer><span>Signal / Milestone 2</span><span>MusicBrainz catalog · deterministic metrics</span></footer>
    </main>
  );
}
