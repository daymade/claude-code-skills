#!/usr/bin/env node
import { getJson, main, printJson, usage } from "./aacp-http.mjs";

if (process.argv.length !== 3) {
  usage("Usage: node scripts/aacp-agent.mjs <agentId>");
}

await main(async () => {
  printJson(await getJson(`/agents/${encodeURIComponent(process.argv[2])}`));
});
