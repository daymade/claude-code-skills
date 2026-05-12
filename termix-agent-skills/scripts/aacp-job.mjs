#!/usr/bin/env node
import { getJson, main, printJson, usage } from "./aacp-http.mjs";

if (process.argv.length !== 3) {
  usage("Usage: node scripts/aacp-job.mjs <jobId>");
}

await main(async () => {
  printJson(await getJson(`/jobs/${encodeURIComponent(process.argv[2])}`));
});
