# Frozen compatibility reader/writer

`forecast_log_v119.py` is the unmodified public production script from
`daymade/claude-code-skills` commit
`50580de34d4cacbd1de59171783054367c298347`, path
`tibo-reset-codex/scripts/forecast_log.py`.
SHA-256: `22ce0b996892b13f3d0c5d04349409994dad22f80deb7cd59cafe3d14bd04718`.

Use only in isolated compatibility tests. Do not update this fixture to match the
current implementation. It represents the v1.19.0 consumer of the shared journal;
the old reader does not implement the new announcement sidecar or account views.
