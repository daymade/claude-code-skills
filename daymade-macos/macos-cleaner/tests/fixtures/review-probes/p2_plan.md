## Proposal (leads with the largest release, 41 GiB, as the gate's ranking rule requires)

| Command | Exact target | Expected release |
|---|---|---|
| `uv cache clean` | whole uv cache | 41.45 GiB |
| `osascript -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' -- "~/.npm/_npx"` | `_npx` | 4.84 GiB |
