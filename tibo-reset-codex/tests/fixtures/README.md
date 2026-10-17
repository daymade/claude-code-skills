# Frozen compatibility reader/writer

`forecast_log_v119.py` is the unmodified public production script from
`daymade/claude-code-skills` commit
`50580de34d4cacbd1de59171783054367c298347`, path
`tibo-reset-codex/scripts/forecast_log.py`.
SHA-256: `22ce0b996892b13f3d0c5d04349409994dad22f80deb7cd59cafe3d14bd04718`.

Use only in isolated compatibility tests. Do not update this fixture to match the
current implementation. It represents the v1.19.0 consumer of the shared journal;
the old reader does not implement the new announcement sidecar or account views.

`account-switch-replay.json` is a synthetic, de-identified replay of the 2026-10-17
failure shape: matching endpoint `account_ref` values, a usage drop, a changed
anchor and anonymous rollout evidence without a direct reset event. Its account
handles and timestamps are test values; it contains no email, token or credential.
The expected classification is `unknown`, with current-state reporting preserved.
