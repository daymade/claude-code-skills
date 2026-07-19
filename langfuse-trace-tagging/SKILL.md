---
name: langfuse-trace-tagging
description: Tag Langfuse traces/sessions via the ingestion API. Use when the user asks to tag a Langfuse session, review/apply topic tags for a coding session, or manage trace tags. Handles credential discovery/setup generically, and works around Langfuse's tags-are-append-only-union API limitation by always getting a proposed tag table confirmed before applying anything (since applied tags cannot be removed or replaced).
---

# Langfuse Trace Tagging

Tags a Langfuse session's traces via the ingestion API. Read this whole skill before doing anything — the tag-mutation limitation in step 2 changes how you should approach every step after it.

This skill is written to be agent-agnostic: each step states the underlying requirement first, with a **concrete illustrative implementation for Claude Code** underneath. If you're a different agent (or maintaining this skill for one), keep the requirement and swap in your own agent's equivalent mechanism — e.g. whatever persistent-notes/memory feature, secret-storage convention, or confirmation-gating pattern it has. Contributions adding callouts for other agents are welcome.

## 1. Credential discovery

**Requirement**: before asking the user to set anything up from scratch, check whether Langfuse API credentials for this instance are already known/persisted somewhere accessible to you. If not, guide the user through first-time setup without ever having them paste the secret key directly into chat, and without silently persisting the secret anywhere without their explicit confirmation of *how* (not just *that*) it'll be stored.

> **Claude Code**: do these in order, stopping at the first that succeeds.
> 1. Check memory for a `reference`-type entry documenting Langfuse API credentials (search for something like "langfuse api credentials"). If found, follow its retrieval instructions as written.
> 2. Otherwise, ask the user for their Langfuse **public key** (safe to share in chat — it is not secret) and the Langfuse **host URL**, then attempt to retrieve a matching secret from macOS Keychain using this skill's own naming convention:
>    ```bash
>    security find-generic-password -a "<public-key>" -s "langfuse-trace-tagging" -w
>    ```
>    (service name `langfuse-trace-tagging`, account = the public key value — a convention this skill defines, not something tied to any particular user or instance.)
> 3. If no Keychain entry exists, run first-time setup:
>    - Ask the user to save `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` into a local scratch file using their own editor, then tell you the file path.
>    - `source` that file into environment variables — never echo the secret value in any visible command or output.
>    - **Explicitly ask the user for confirmation before writing anything to Keychain.** Do not treat this as implied by earlier instructions to "set up credentials" — a Keychain write is a new, distinct action worth its own confirmation.
>    - Once confirmed and stored, offer to save a `reference` memory entry (e.g. named `langfuse-api-credentials`) documenting the public key and the Keychain service/account convention used, so a future session can rediscover it without repeating this setup. Then delete the temp credentials file.

Throughout, regardless of agent: never print the secret key value in a visible command. Always source it from a file or secret store straight into an environment variable.

## 2. The tag limitation you must design around

**Langfuse trace tags can be added via the API, but never removed or replaced.** Confirmed via Langfuse's own issue tracker — a request to support tag updates/removal was closed "not planned" (`langfuse/langfuse#8937`), and multiple earlier feature requests for the same thing went unaddressed. The underlying mechanism: repeated tag-bearing events for the same trace ID are merged as a **unique union**, not a replace — there is structurally no way to represent "this tag was removed."

Practical consequence: **once you apply a tag to a trace, it is there permanently**, short of destructively deleting and recreating the trace (real data loss — you'd lose its spans, timing, and I/O too). A "tag broadly now, narrow it down later" approach does not work — the narrower second pass just unions with the first and nothing shrinks.

**Hard rule that follows from this**: always build and show the user a full proposed tag table and get explicit confirmation *before* calling the ingestion API. Never apply anything "provisionally." If the user later asks to reduce or correct an already-applied tag set, tell them plainly that it isn't possible via API/SDK/UI, and the only paths are living with the current tags or destructively rebuilding the traces.

## 3. Propose tags for confirmation

- Use a `topic:issue` naming convention, e.g. `service-name:short-issue-slug`.
- Derive proposed tags from the conversation content you already have in context — do not re-fetch raw trace input/output to do this (see the safety note in step 4).
- Present the proposal as a markdown table: trace/turn range (or "whole session" if uniform) → proposed tag(s) → one-line rationale.
- Get explicit confirmation or adjustment from the user before proceeding to step 5. Treat silence or a vague "sounds good" as insufficient if the table is large or the tags are consequential — ask directly if anything is ambiguous.

## 4. Fetching trace metadata safely

If you need the list of traces for a session (IDs, timestamps, turn numbers) to build the proposal table:

```bash
langfuse-cli api traces list --session-id "<session-id>" --fields core --json
```

**Never fetch or persist the `io` field group (trace input/output) to disk.** Trace content can contain secrets pasted during the session — API keys, passwords, tokens, connection strings. If you genuinely need per-trace content to classify topics accurately, view it via a tool call in-session rather than writing it to any file, and never copy it into a scratch file for later reference.

## 5. Applying tags

Once the table is confirmed:

1. For each trace, compute its **full desired tag set** client-side (existing tags ∪ new tags — remember the API only unions, so there's no reason to send a partial list expecting it to replace anything).
2. Build a batch of ingestion events:
   ```json
   {
     "batch": [
       {
         "id": "<fresh-uuid-per-event>",
         "type": "trace-create",
         "timestamp": "<iso-8601-now>",
         "body": { "id": "<existing-trace-id>", "tags": ["tag-a", "tag-b"] }
       }
     ]
   }
   ```
3. POST to `<host>/api/public/ingestion` with header `Authorization: Basic <base64(public_key:secret_key)>`.
4. Chunk at roughly 50 events per batch (the endpoint has a 3.5MB total batch-size limit).
5. Verify by re-fetching one sample trace afterward and confirming its tags match what was intended.
