# Import URLs and extract structured content

Use IMA as a page reader: import URLs into a knowledge base, have IMA's chat turn them into structured text, save that text as a note, and read the note back over the API. It is worth the effort when the pages are ones your own machine cannot fetch (anti-bot verification walls, logged-in-only rendering) but IMA's servers can read.

Evidence scope: everything below was observed in one batch run of 98 URLs (roughly 12 rounds of extraction). Numbers are from that run, not a service guarantee.

## What the API can and cannot do

| Need | Endpoint | Observed behaviour |
|---|---|---|
| Add pages to a KB | `POST wiki/v1/import_urls` `{knowledge_base_id, urls[]}` | At most 10 URLs per call. `data.results` is keyed by URL; each value has `media_id` and `ret_code`. |
| See what the KB holds | `POST wiki/v1/get_knowledge_list` `{knowledge_base_id, cursor, limit}` | Returns `knowledge_list[{media_id, title}]`, `is_end`, `next_cursor`. No status field and no source URL. |
| Find your own imports | — | Take `media_id`s from the `import_urls` response and match them against the list. Do not match on title. |
| List notes | `POST note/v1/list_note_by_folder_id` `{folder_id: "", cursor: "", limit: 20}` | Lists notes in the root folder. |
| Read a note | `POST note/v1/get_doc_content` `{doc_id, target_content_format: 0}` | Body text is in `data.content`. |

No endpoint was found for: creating or deleting a knowledge base, deleting a KB entry, or reading a KB entry's body. None was found for asking a KB a question either, so the extraction step below goes through the desktop app.

## Entries resolve asynchronously

Right after `import_urls` an entry's `title` is the URL itself. It becomes the real page title once IMA has parsed the page: about 25–60 seconds for a small batch, longer for a big one. Poll `get_knowledge_list` and treat "title no longer starts with `http`" as resolved. Some entries never resolve into readable content: IMA shows 解析失败 for them (9 of 98 pages in the run). Plan for a residue of unreadable pages rather than assuming every import succeeds.

## Structured extraction protocol

The API cannot query the chat, so extraction is: chat in the desktop app → save as note → read the note over the API.

1. Give IMA a numbered list of the entry titles for this round and ask for a JSON array with one object per title and fixed fields (for example `title`, `author`, `published`, `paragraphs`). Ask for verbatim text.
2. Use the app's "记笔记 → 新建笔记" on that answer. The note is the machine-readable hand-off; screen text is not.
3. Read the note with `get_doc_content` and parse it.

Behaviours to design for:

- **Unescaped inner quotes.** IMA often leaves ASCII `"` inside string values unescaped, so a strict `json.loads` fails. Asking for escaped quotes helped only some of the time. Write a lenient parser (repair inner quotes, accept several arrays in one note) and keep the strict path first.
- **Truncated rounds.** 12 titles in one round returned only 7 objects once in four rounds; cause not established. 8 per round was used afterwards. Compare the number of returned objects to the number of titles asked, and re-ask only the missing ones.
- **Empty placeholder objects.** For a page it cannot read, IMA may emit a null or empty object instead of skipping it. Count an item as matched only when its body has real content (a minimum body length works), not when the object merely exists.
- **Match by title, then verify.** The chat returns titles, not `media_id`s. Normalise both sides (whitespace, width, punctuation) before comparing, and treat two entries with the same title as ambiguous rather than picking one.

## Desktop-app automation pitfalls

These apply when a computer-use tool drives the IMA desktop app.

- A success flag from the tool (`ok: true`, or a reply saying the target is occluded) does not mean the text arrived. Take a screenshot and confirm the prompt is in the input box.
- Bring the app to the front before typing; input aimed at an occluded window was silently lost.
- "新建笔记" opens a new tab and shifts the tab bar. Click the knowledge-base tab again before typing the next prompt, or the prompt lands in the new note.
- The note menu loads its list lazily. Clicking too early can hit an existing note, and the answer is then appended to that note instead of a new one. After saving, list notes over the API and check which note received the text.
- Scrolling acts on the window under the cursor, and on the tool used here a positive delta scrolled up.

## Leftovers

Every run leaves entries in the knowledge base and notes in the account. The API cannot delete either, so tell the user what was created and let them clean up in the app once the extracted data is safely stored elsewhere.
