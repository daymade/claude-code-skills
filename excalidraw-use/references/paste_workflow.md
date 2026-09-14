# Getting a scene onto a board that already has work on it

This is the half of the job that has nothing to do with generating the file, and
it is where a correct scene file still ruins someone's afternoon.

## The trap

At excalidraw.com, **both** of the obvious routes replace the entire current
scene:

- the menu's **Open**
- **dragging a `.excalidraw` file onto the canvas**

There is a confirmation prompt on a non-empty canvas, but the operation is still
*replace*, not *merge*. So "here's the file, just open it" is the wrong hand-off
whenever the user has an existing board — which is the normal case, because the
reason they wanted images placed is that they already have a board.

## The additive route

The clipboard carries elements *and* their embedded image payloads, so
copy-paste merges instead of replacing:

1. Open the generated scene file in a **second browser tab**
   (a fresh excalidraw.com tab → Open → the file; this tab is disposable)
2. `Cmd/Ctrl + A`, then `Cmd/Ctrl + C`
3. Switch to the tab holding the real board
4. **Scroll to empty canvas first**, then `Cmd/Ctrl + V`

Step 4 is not optional. Paste lands relative to the current viewport, so pasting
where existing work sits drops the new grid on top of it. `inspect_scene.py`
prints the existing board's occupied extent, which is how you tell the user
where *not* to paste.

## Why the file on disk is not the board

Two independent failure modes, both of which look like the tool losing work:

**A board open in a browser tab does not watch the file.** Editing the `.excalidraw`
on disk changes nothing in the tab, and the next in-app save writes the tab's
state over your edit. The change is not merged, it is erased, and nothing reports
an error.

**The exported file is usually older than the browser state.** People export a
board once and keep working in the tab for days. So the file you can read is a
stale snapshot; merging into it and handing it back silently discards everything
since the export. Check the file's mtime against when the user says they last
worked on the board before you even consider a merge.

Together these mean: **generate a separate scene file, let the user paste.** If
they explicitly want a merged file, write it to a new path so the original
survives and they choose which to open.

## Size

A scene is JSON with base64 image payloads inline, so it is roughly 1.4× the
total size of the images. Large scenes are where the clipboard route gets slow
or fails without a clear error.

Rough guidance from practice, not a published limit: a few MB pastes without
noticeable delay; around 20 MB is where it is worth splitting pre-emptively
rather than finding out during a live session. `split_scene.py` re-lays each part
on its own grid and carries only the files that part references, so four parts of
a 20 MB scene are ~5 MB each rather than 20 MB each.

## Verification boundary

Everything above is about *delivering* the file. Note what you can and cannot
check yourself:

- You **can** verify the file is structurally sound — `build_scene.py` does it on
  every write, and `inspect_scene.py` re-checks any scene.
- You **cannot** verify it renders correctly without opening it in Excalidraw,
  and opening it replaces whatever scene that browser session currently holds.

So do not open excalidraw.com to check your own output when the user has a live
board — the verification would cost the thing it was protecting. Say plainly that
the structure is verified and the render is not, and ask the user to glance at
the first paste.
