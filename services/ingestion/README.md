# Ingestion boundary

Provider protocols and the MusicBrainz and ListenBrainz adapters live under `signal_app.domain` and
`signal_app.providers`. `signal_app.ingestion.refresh_artist_metrics` is the transport-independent
write boundary for idempotent daily listening snapshots.
