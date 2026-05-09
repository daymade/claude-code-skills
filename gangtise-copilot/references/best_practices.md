# Gangtise Copilot — Best Practices

Non-obvious patterns for getting the most value out of the Gangtise skill catalog after installation. Read this when you've installed the skills and are wondering "okay, now what do I actually do with them?"

## The two-level mental model

Gangtise's 19 skills are organized into two layers that you should think of differently:

1. **Data-layer skills (gangtise-data-client, gangtise-kb-client, gangtise-file-client, gangtise-web-client, gangtise-stockpool-client)** — primitive operations. Each script returns a specific data structure (CSV, file list, text chunks). Don't call them directly in a workshop demo unless you're teaching the primitive; they're building blocks, not finished products.

2. **Workflow-layer skills (the 10 `gangtise-*` in the research bundle)** — finished research deliverables. Each one encodes a full professional workflow — data retrieval, analysis, writing, formatting — and outputs an MD + HTML report. Call these in workshop demos because they produce something the audience can *see*.

**The mistake a new user makes**: invoking `gangtise-data-client/quote.py` directly, getting back a CSV of 252 rows of OHLC data, and thinking "now what?" The workflow-layer skill `gangtise-stock-research` L2 answers "now what" — it wraps the same quote data into a research narrative.

## Skill composition patterns

### Pattern 1: Single flagship skill for quick wins

For a 10-minute demo, invoke a single workflow-layer skill end-to-end:

- **Stock research report**: `gangtise-stock-research` L2 on any named stock → complete investment view in one invocation.
- **Daily monitoring digest**: `gangtise-announcement-digest` with a stock pool → daily push to Feishu.
- **Devil's advocate review**: `gangtise-opinion-pk` on a named stock with user's thesis → risk scan MD + HTML.

The workflow-layer skills are designed for single-shot use and produce publication-ready output. Don't try to chain them together in a first demo — the output of one is not the input of another by default.

### Pattern 2: Data → workflow → revision

For deeper research, pair a data-layer skill with a workflow-layer skill:

1. Use `gangtise-data-client/financial.py` to pull specific metrics you care about (e.g., operating margin over 8 quarters).
2. Feed those numbers as context into `gangtise-stock-research` — the workflow skill will incorporate them into its narrative.
3. Run `gangtise-opinion-pk` on the resulting thesis for a risk scan.

This three-step composition produces a "my view + adversarial critique" pair that reads far more like institutional research than a single skill call.

### Pattern 3: Enumerate → filter → deepen

For industry research, fan out with the enumeration skills:

1. `gangtise-data-client/block_component.py -k 新能源汽车` → get constituent stocks
2. `gangtise-data-client/valuation.py --securities-file block_component_1.csv` → valuation data for each
3. Sort, filter, pick the top 3 by your criterion
4. `gangtise-stock-research` L2 on each of the top 3
5. `gangtise-thematic-research` on the sector as a whole

This is the pattern that `gangtise-stock-selector` and `gangtise-thematic-research` encode internally — knowing the decomposition lets you intervene at any step.

## Credential scope gotchas

The `accessKey + secretAccessKey` you get from Gangtise has **scopes** attached to it. Common scopes (from observation):

- **auth** — can call `loginV2` to mint a token. Every account has this.
- **rag** — can call `knowledge_base` semantic search. Most accounts have this.
- **data** — can call structured data scripts (`quote`, `financial`, `valuation`, etc.). Paid accounts.
- **file** — can call file-center scripts (`report`, `opinion`, `summary`, etc.). Paid accounts.
- **openapi** — aggregate name for the above three. This is what `skills-backend/version?skill=openapi` reports.

If your account is missing a scope, the affected scripts will return an error at call time, not at auth time. `diagnose.sh` probes only the `rag` scope by default (because that's the one most skills need), so a partial-scope account will show "✅ RAG liveness passed" and then fail when you try to call a `data` skill.

**Best practice**: When onboarding a new user, ask their Gangtise admin explicitly: "Does this account have `data` and `file` scopes in addition to `rag`?" If they don't know, the fastest way to find out is to call one of each tier and observe:

```bash
# Tier: rag (should work)
cd ~/.local/share/gangtise-copilot/skills/gangtise-kb-client
python3 scripts/kb.py -q "test" -l 1

# Tier: data (fails if no data scope)
cd ../gangtise-data-client
python3 scripts/quote.py --securities 宁德时代 -sd 2026-04-01 -ed 2026-04-10

# Tier: file (fails if no file scope)
cd ../gangtise-file-client
python3 scripts/report.py -k 宁德时代 -l 3
```

## Working around the OBS LIST block

`gts-download.obs.myhuaweicloud.com/skills/` has its LIST permission disabled (403 on any listing request). This means:

- **You cannot programmatically discover new skills** by crawling the bucket.
- **The installer's bundle list is hand-maintained.**
- **A new Gangtise skill release will not be detected automatically** by the wrapper.

When you hear about a new Gangtise skill (via WeChat, Gangtise's own announcements, or a user report), update `scripts/install_gangtise.sh`:

1. Try to HEAD the new standalone ZIP: `curl -I https://gts-download.obs.myhuaweicloud.com/skills/gangtise-<new-name>.zip`
2. If it returns 200, add it to the bundle map under the appropriate bundle (or under its own standalone line if it's truly independent).
3. Re-test the install flow end-to-end with `--only <new-skill>` to confirm it unpacks cleanly.
4. Add it to the preset lists if it's workshop-relevant.
5. Bump the wrapper version in `marketplace.json` and commit.

## NO_PROXY for macOS / Linux users with local HTTP proxies

If you run a local HTTP proxy (Shadowrocket, Clash, Surge, v2ray, etc.) that intercepts `.com` traffic, every call to `open.gangtise.com` or `gts-download.obs.myhuaweicloud.com` goes through the proxy. Depending on your proxy's TLS handling, this can:

- **Corrupt download responses** (proxy truncates or re-encodes HTTPS bodies) — the installer's size sanity check catches this, but only after a failure.
- **Fail auth calls** (proxy terminates TLS and Gangtise rejects the resulting cert chain).
- **Add 500-2000 ms latency** to every API call, making workshop demos feel sluggish.

The fix:

```bash
export NO_PROXY="open.gangtise.com,gts-download.obs.myhuaweicloud.com,$NO_PROXY"
export no_proxy="open.gangtise.com,gts-download.obs.myhuaweicloud.com,$no_proxy"
```

Or add these to your shell init (`~/.zshrc`, `~/.bashrc`). `gangtise-copilot`'s scripts do NOT set this for you — setting NO_PROXY globally is a user-level decision.

## Workshop timing reference (from the 2026 Q2 Investor Workshop design)

Approximate timings for live workshop demos of each workflow skill (based on staging tests, your mileage will vary with query complexity and account quota):

| Skill | Typical wall time | What the audience sees |
|---|---|---|
| `gangtise-stock-research` L1 | 30-60 sec | 1-page MD + rendered HTML |
| `gangtise-stock-research` L2 | 2-4 min | Full investment view MD + HTML |
| `gangtise-stock-research` L3 | 5-10 min | Institutional first-coverage MD + HTML |
| `gangtise-opinion-pk` | 2-4 min | Adversarial analysis MD + HTML |
| `gangtise-thematic-research` | 3-5 min | Theme analysis MD + HTML |
| `gangtise-announcement-digest` | 1-2 min | Stock pool digest MD + HTML |
| `gangtise-event-review` | 1-2 min | Event post-mortem MD + HTML |
| Data-layer call (e.g., `quote.py`) | 3-10 sec | CSV file on disk |

**Demo tip**: Use `gangtise-stock-research` L1 for "hello world" because it's fast enough to not break audience attention, and use L2 for the "wow" moment because the output is institutional-grade but doesn't take so long that you lose the room.

## What NOT to do in a workshop demo

- **Don't call 18 data-layer scripts in a row.** The audience will see 18 CSV files and think "I could have done this in Excel." Always wrap data calls in a workflow-layer skill.
- **Don't claim the workflow skills are making investment recommendations.** They explicitly avoid this (the compliance guardrails in their templates forbid "买入 / 卖出 / 目标价"). Calling the output a "recommendation" in front of an audience defeats the purpose of the guardrails and puts you at compliance risk.
- **Don't use the legacy minimal skills (`gangtise-data`, `gangtise-file`, `gangtise-kb`) for workshop demos.** They're missing 5-9 capabilities compared to the client variants. Save them for batch pipelines where their strict input style is a feature.
- **Don't pair `gangtise-stock-research` with a stock that has sparse coverage.** The workflow needs at least 20 recent research reports + opinions to produce a good L2 output. Pick large-cap Chinese stocks (宁德时代, 比亚迪, 贵州茅台, 宁德 sector peers) for guaranteed data density.
- **Don't demonstrate the `opinion-pk` adversarial analysis on a stock the audience has strong personal opinions about.** It produces a devil's-advocate view by design, which can read as an attack on whoever recommended the stock. Stay with neutral or unfamiliar names.

## What TO do after install

1. **Run `diagnose.sh` once** to confirm everything is healthy (9 checks should pass).
2. **Try one workflow skill on one stock** — pick `gangtise-stock-research L1 宁德时代` as a smoke test. You should get a ~1 minute run and an MD + HTML pair on disk.
3. **Open the HTML in a browser** to see Gangtise's professional report template render. This is the output your workshop audience will see.
4. **Read the MD file's "data sources" section** at the bottom — it lists which underlying skills were called. Use this to build intuition about the workflow → data-layer mapping.
5. **Go back and re-read `skill_registry.md`** with fresh eyes — the capability matrix makes more sense after you've seen one workflow in action.
