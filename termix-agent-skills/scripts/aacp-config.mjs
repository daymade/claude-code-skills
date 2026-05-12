#!/usr/bin/env node
import { getJson, main, printJson } from "./aacp-http.mjs";

await main(async () => {
  printJson(await getJson("/config"));
});
