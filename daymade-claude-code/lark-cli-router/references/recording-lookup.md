# Find an existing recording by date

Use this branch when Feishu is the known recording source and the user wants an
existing recording's playback link. Keep a supplied minute token or meeting ID
and use the embedded guide's direct lookup instead of searching again.

1. Follow the router's runtime check and load the current embedded
   `lark-meeting` minutes-search scene/reference. Its guide owns API parameters
   and date limits. This branch does not start ingest, gap audit, ASR or filing.
2. Fix the requested date window. For one day, use the same start and end.
   If a year is omitted, use a context-supported year and state that assumption;
   do not silently try unrelated years or widen the window. Select only profiles
   already verified as belonging to the requester and authorized for this read,
   under the router's identity contract. A local profile list alone is not that
   authorization. Report excluded or unverified accounts as not queried.
3. Run the bundled helper from this loaded Skill's directory:

   ```bash
   uv run --script "<loaded-skill-dir>/scripts/find_recording_candidates.py" \
     --profile "<authorized-profile-a>" --profile "<authorized-profile-b>" \
     --start 2026-03-10 --end 2026-03-10
   ```

   Repeat `--profile` only for the decided scope. Consult the helper's `--help`
   for runtime limits and exit meanings; the embedded guide owns pagination policy.
   By default the helper queries profiles in argument order with a shared item
   budget, shrinking each page to the remaining budget. Raw items count before
   deduplication. It adds no title or participant filters and retains archived and
   unarchived candidates. Use `--all-pages` only when the user explicitly requests
   all results under the embedded guide; that mode queries profiles concurrently.
   An unsuccessful lookup alone does not authorize this flag.
   For large results, retain the full JSON in a private task file and inspect
   coverage and bounded candidate groups; clipped terminal output is incomplete.
4. Read `coverage` for every requested profile and retain partial results.
   `complete` means pagination completed for this explicit date/profile scope;
   it does not confirm a recording's identity or imply all accounts were searched.
   Do not interpret an API/CLI failure or an unqueried account as an empty search.
   Follow the existing
   auth/permission recovery route; do not broaden access or loop on a denial.
   A `confirmation_required` stop retains the next page token; profiles not yet
   queried are `not_queried`. If existing candidates already identify the target,
   return it with the coverage limit rather than asking merely to make coverage
   complete. Otherwise obtain the guide's required confirmation before more pages.
   The known leading CLI token-refresh notice appears in `coverage.notices`;
   unknown stdout noise or malformed JSON remains an error.
5. Use names, homophones, titles, duration and scene only to rank candidates.
   A company name need not appear in the title, and a person's mention does not
   establish attendance. When necessary, use the current embedded guide to read
   the smallest relevant candidate transcripts, preserving each source profile.
   Verify the requested scene or discussion before calling a candidate the target.
   While an authorized, relevant read can resolve the ambiguity, perform it before
   asking the user to supply information the agent can obtain itself.
6. Return the actual URL from the selected candidate's `sources`, with the title,
   duration and a brief matching reason, plus any material coverage gap. Missing
   URLs remain `null`; obtain one through the official detail route rather than
   constructing a tenant hostname. Treat platform start/upload time as platform
   metadata unless independent evidence establishes the actual meeting time.

The helper lists candidates and observed coverage. The executing agent owns
authorization, source selection and scene confirmation; it has no automatic
semantic judge and does not maintain a separate recording index.
