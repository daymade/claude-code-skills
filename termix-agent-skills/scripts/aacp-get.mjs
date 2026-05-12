#!/usr/bin/env node
import { getJson, main, printJson, usage } from "./aacp-http.mjs";

if (process.argv.length !== 3) {
  usage("Usage: node scripts/aacp-get.mjs <path-or-url>", [
    "Example: node scripts/aacp-get.mjs /api/v1/stats",
    "Example: node scripts/aacp-get.mjs jobs?status=FUNDED",
  ]);
}

await main(async () => {
  printJson(await getJson(process.argv[2]));
});
