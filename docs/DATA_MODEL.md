# Data model

Historical metrics and provider independence are first-class concerns. The Milestone 1 schema is
normalized around artists, releases, credits, external identities, and snapshots.

```text
artists 1 ── * artist_external_ids
   │
   ├── 1 ── * artist_metric_snapshots
   │
   └── * ── * releases (through release_artists)
                  │
                  └── 1 ── * release_external_ids
```

## Tables

### `artists`

Internal UUID, canonical display and sort names, optional ISO country code and disambiguation,
supplemental JSON metadata, and timestamps. Provider metadata is non-authoritative and must not
replace fields that need constraints or indexing.

### `artist_external_ids`

Maps an internal artist to `(provider, external_id)`. That pair is globally unique, making repeated
imports idempotent and allowing MusicBrainz, ListenBrainz, Discogs, and other identities to coexist.

### `releases`

Internal UUID, title, optional normalized date, type, status, supplemental metadata, and timestamps.
MusicBrainz partial dates are normalized to the first valid day while the exact source text remains
in metadata so precision is not silently lost.

### `release_artists`

Many-to-many artist credits with a position. This avoids the false assumption that every release has
one artist.

### `release_external_ids`

Provider identity mapping equivalent to the artist table.

### `artist_metric_snapshots`

One record per artist, calendar date, and source. Metrics are nullable because providers expose
different fields. Counts are constrained nonnegative. The initial fields are listener count, listen
count, provider popularity, and release activity.

`(artist_id, snapshot_date, source)` is unique and `(artist_id, snapshot_date)` is indexed for time
range access.

## Metric provenance

The `source` value is mandatory. Milestone 1 uses `demo` for synthetic values; UI and API responses
identify these values as demonstrations. Later ingestion must use a provider identifier such as
`listenbrainz` and preserve useful raw provenance in metadata.

## Growth definition

For nonzero starting values:

```text
percentage_change = ((end_value - start_value) / start_value) * 100
```

The function returns the actual snapshots used, which may differ by no more than three days from a
requested endpoint. Missing endpoints yield `insufficient_data`. A zero start yields an absolute
change and `undefined_percentage`; Signal never substitutes an arbitrary denominator.

