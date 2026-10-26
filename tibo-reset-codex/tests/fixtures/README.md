# Frozen compatibility reader/writer

`forecast_log_v119.py` is the unmodified public production script from
`daymade/claude-code-skills` commit
`50580de34d4cacbd1de59171783054367c298347`, path
`tibo-reset-codex/scripts/forecast_log.py`.
SHA-256: `22ce0b996892b13f3d0c5d04349409994dad22f80deb7cd59cafe3d14bd04718`.

Use only in isolated compatibility tests. Do not update this fixture to match the
current implementation. It represents the v1.19.0 consumer of the shared journal;
the old reader does not implement the new announcement sidecar or account views.

`forecast_log_v240.py` is the unmodified public production script from
`daymade/claude-code-skills` commit
`962ec6d27517b856a6e260c16c0be296ed92bf2d`, path
`tibo-reset-codex/scripts/forecast_log.py`.
SHA-256: `c71b8206b0a13b30b9ed806a8cc075b3a597869c6635fa949ea71cbb0f128c15`.

Use only in isolated compatibility tests as the pre-compact v2.4.0 reader, including
its announcement sidecar and account views. Do not update this fixture to match the
current implementation; its purpose is to catch full-summary and followup drift.

`account-switch-replay.json` is a synthetic, de-identified replay of the 2026-10-17
failure shape: matching endpoint `account_ref` values, a usage drop, a changed
anchor and anonymous rollout evidence without a direct reset event. Its account
handles and timestamps are test values; it contains no email, token or credential.
The expected classification is `unknown`, with current-state reporting preserved.
