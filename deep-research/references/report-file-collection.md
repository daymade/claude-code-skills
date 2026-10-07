# Collect provider reports through files

Apply when collecting an existing provider response or finished research task. Stop when the original files are saved and independently read back, or record the unavailable channel and coverage gap. Collection does not authorize another research submission.

## Choose the available channel

1. Inspect the existing study files and the task's actual attachments before downloading again.
2. Use the provider's download/export button, attachment download, or actual task directory when available. Do not use clipboard input or output as a substitute for an available file channel. For Kimi input and task files, load `kimi-use` and its driving reference.
3. For browser operations, load the installed browser Skill and its current API documentation. Confirm ownership of the tab before automation; stop and coordinate at the first concurrent overwrite. Do not copy tool signatures from an old transcript.
4. Only when no file/export channel exists and the task permits it may a copy channel be used. Label it as copied response text, not a downloaded original report. Text size alone does not establish completeness.

## Browser download recipes

These are observed UI routes, not fixed selectors. Discover controls from the current page state. Arm the documented download-event listener before clicking and save the resulting download in the same operation; a successful click is not evidence that a file was saved.

- Native ChatGPT Deep Research: open the completed report's export menu, then its Markdown export. A nested report frame may require reading that frame's current controls. Preserve the exported Markdown unchanged.
- Ordinary ChatGPT Pro with a report attachment: open the file card's preview, then use the preview's Download button. An overlay intercepting the card click does not establish that download is unavailable; inspect the current overlay and preview.
- Kimi Deep Research: download the original report ZIP through its file panel. Preserve the ZIP and extract a separate copy, retaining its real internal directories and relative figure references. The file inventory is discovered per task, not assumed from a previous export.

## Independent readback

Record actual provider/mode, conversation or task locator, capture time, original filename and archive path. Keep credentials and signed temporary download URLs out of public examples.

Read the saved file independently of the download tool's receipt. Check the expected report's opening and ending sections, source list and advertised attachments; distinguish the full report from the short response announcing it. For ZIPs, check archive integrity and the extracted Markdown/figure paths. Retain the unedited original separately from normalized text, corrections and synthesis.

If the received file is partial, corrupt or belongs to another task, mark collection unresolved. Inspect the existing task and file channels before retrying collection. Do not submit the research again to repair a collector failure.
