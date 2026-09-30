# Import URLs and extract structured content

Use IMA as a page reader: import URLs into a knowledge base, have IMA's chat turn them into structured text, save that text as a note, and read the note back over the API. It is worth the effort when the pages are ones your own machine cannot fetch (anti-bot verification walls, logged-in-only rendering) but IMA's servers can read.

Two prerequisites. Endpoint base URL and auth headers are in `api_key_setup.md` (`https://ima.qq.com/openapi/<path>`, headers `ima-openapi-clientid` / `ima-openapi-apikey`). The extraction step drives the IMA desktop app, so it needs a computer-use tool that can control it; without one, stop after import and hand the extraction to the user.

Evidence scope: the "Observed" statements below come from one batch run of 98 URLs (roughly 12 extraction rounds), not from a service guarantee. Statements marked "upstream" are from the upstream ima-skill docs (`knowledge-base/SKILL.md`) as installed at the time of writing.

## Before importing: confirm with the user

Imports write to the user's account and the API offers no delete (see below). Before the first `import_urls` call, show the user the target knowledge base and the URL list and get a yes. Find the base with `search_knowledge_base` (`query: ""` lists them) or `get_addable_knowledge_base_list`, and let the user pick if more than one fits.

## Endpoints used

| Need | Endpoint | Notes |
|---|---|---|
| Add pages to a KB | `wiki/v1/import_urls` `{knowledge_base_id, urls[], folder_id?}` | Upstream: 1–10 URLs per call; `folder_id` optional, omit for the root. Non-zero `ret_code` per URL means failure; read its `errmsg`. Observed: `data.results` is keyed by URL, each value has `media_id` and `ret_code`. |
| See what the KB holds | `wiki/v1/get_knowledge_list` `{knowledge_base_id, cursor, limit}` | Upstream: `limit` 1–50. Returns `knowledge_list[{media_id, title}]` (upstream `KnowledgeInfo` also has `parent_folder_id`), `is_end`, `next_cursor`. No status field and no source URL. |
| Find your own imports | — | Take `media_id`s from the `import_urls` response and match them against the list. Do not match on title. |
| List notes | `note/v1/list_note_by_folder_id` `{folder_id: "", cursor: "", limit: 20}` | Lists notes in the root folder. |
| Read a note | `note/v1/get_doc_content` `{doc_id, target_content_format: 0}` | Body text is in `data.content`. |

`import_urls` is for web pages. A URL that serves a file (PDF, Office document; upstream says to check the `Content-Type` with a HEAD request) goes through the upload flow instead; screen the list before importing.

Not found in the upstream ima-skill docs (16 `wiki/v1` and `note/v1` endpoints, checked at the time of writing): creating or deleting a knowledge base, deleting a KB entry, reading a full KB entry body (`search_knowledge` returns only highlight snippets), or asking a KB a question. That is why extraction goes through the desktop app and why cleanup is manual. Recheck against the current upstream release before relying on it.

## Entries resolve asynchronously

Observed: right after `import_urls` an entry's `title` is the URL itself, and it becomes the page title once IMA has parsed the page. That took roughly 25–60 seconds for a small batch and longer for a big one. Poll `get_knowledge_list` for your `media_id`s and treat "title no longer starts with `http`" as resolved.

The list has no status field, so a failed entry cannot be told from a slow one over the API. Put a timeout on the poll (for example ten minutes) and carry the stragglers into extraction anyway: an entry IMA could not read shows up there as an empty object (below). In the run, 9 of 98 pages ended as 解析失败 in IMA. Plan for a residue of unreadable pages.

## Structured extraction protocol

Extraction is: chat in the desktop app → save as note → read the note over the API. The chat must be the one scoped to the knowledge base you imported into.

1. Give IMA a numbered list of the entry titles for this round and ask for a JSON array with one object per title. Fields used in the run: `title`, `author`, `published`, `paragraphs` (array of strings), plus whatever page-specific text you need. Ask for verbatim text.
2. Use the app's "记笔记 → 新建笔记" on that answer. The note is the machine-readable hand-off; screen text is not.
3. List notes, identify the one that received the answer (see the pitfalls below), and read it with `get_doc_content`.

Behaviours to design for (all observed in the run):

- **Unescaped inner quotes.** IMA often leaves ASCII `"` inside string values unescaped, so a strict `json.loads` fails. Asking for escaped quotes helped only some of the time. Try strict first. The fallback that worked: ask for compact JSON with a fixed field order, then split on the known field delimiters (`","author":"`, `","published":"`, …) instead of parsing quotes, and keep any unescaped `"` inside a value as content. A note can also hold several arrays (one per round); parse each separately.
- **Truncated rounds.** 12 titles in one round returned only 7 objects once in four rounds; cause not established. 8 per round was used afterwards. Compare the number of returned objects to the titles asked and re-ask only the missing ones.
- **Empty placeholder objects.** For a page it cannot read, IMA may emit a null or empty object instead of skipping it. Count an item as matched only when its body has real content (the run used at least 30 characters), not when the object merely exists.
- **Match by title, then verify.** The chat returns titles, not `media_id`s. Normalise both sides (whitespace, width, punctuation) before comparing, and treat two entries with the same title as ambiguous rather than picking one.

## Desktop-app automation pitfalls

These apply when a computer-use tool drives the IMA desktop app.

- A success flag from the tool (`ok: true`, or a reply saying the target is occluded) does not mean the text arrived. Take a screenshot and confirm the prompt is in the input box.
- Bring the app to the front before typing; input aimed at an occluded window was silently lost.
- "新建笔记" opens a new tab and shifts the tab bar. Click the knowledge-base tab again before typing the next prompt, or the prompt lands in the new note.
- The note menu loads its list lazily. Clicking too early can hit an existing note, and the answer is then appended to that note instead of a new one. After saving, list notes over the API and check which note received the text.

## Leftovers

Every run leaves entries in the knowledge base and notes in the account, and the API has no delete. Tell the user what was created and let them clean it up in the app once the extracted data is safely stored elsewhere.
