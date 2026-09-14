---
name: meme-creator
description: >-
  Creates video/GIF memes by overlaying images (logos, avatars, stickers) onto moving objects in a clip with frame-accurate tracking, then exports MP4 + GIF. Use whenever the user wants a meme, 梗图, 表情包, or reaction GIF from existing footage; to cover faces or heads in a video; to make a logo or avatar follow a moving person or object; to turn a video moment into a shareable GIF; or asks to 把 logo/头像贴到视频里跟着动. Handles source download (yt-dlp), segment picking via contact sheets, CSRT tracking with re-anchors and a manual-keyframe fallback, fades at frame edges and shot changes, and GIF size budgeting. Not for transcript-driven editing, programmatic scene generation, or subtitle work.
---

# Meme Creator

Turn a video clip into a meme: images (logos, avatars, stickers) glued onto
moving objects so they follow the motion frame by frame, delivered as MP4 + GIF.

The failure mode that ruins this is not tracking drift — it is gluing the
*wrong person's* avatar on screen because a name was bound to the first
plausible account found. So step 0 is identity, not tooling.

For a static image meme, skip tracking entirely: put one `manual_keys` entry
per target (`[[1, [x, y, w, h]]]`) in the overlays config and render just that
frame — `--tracks` is optional when every position comes from keys.

## Requirements

- `ffmpeg` on PATH
- `uv` — all bundled Python scripts carry inline dependencies; run them with
  `uv run <script>` and deps resolve themselves
- `yt-dlp` only when downloading (`uv run --with yt-dlp yt-dlp ...`)
- Chrome/Chromium only when rasterizing an SVG logo (asset-binding.md)
- Script paths below are written `scripts/…` **relative to this skill's bundle
  directory**. Resolve the bundle path once (`SKILL_DIR=<path to this skill>`)
  and run `"$SKILL_DIR"/scripts/make_sheets.py …` — your working directory is
  the scratch dir, not the bundle.

## Pipeline

Work inside a scratch directory (`/tmp/<meme-name>/` or similar), deliver only
the final MP4 + GIF.

### 0. Bind identities before fetching assets

When the user names who/what goes on screen ("Codex, Claude, and Tibo's
avatar"), every ambiguous name must survive the disambiguation gate in
[references/asset-binding.md](references/asset-binding.md) — enumerate
candidates with a handle-free search, discriminate from the request context
(the peer entities listed alongside are the strongest signal), and ask the
user when context cannot decide. That file also covers logo/avatar sourcing,
SVG→PNG with real transparency via headless Chrome, and badge styling. Fetch
and eyeball every image before compositing it.

### 1. Acquire the source

Local file: use it. URL: yt-dlp handles bilibili (incl. `b23.tv` short links),
YouTube, and most sites:

```bash
uv run --with yt-dlp yt-dlp -f "bv*+ba/b" --merge-output-format mp4 -o "source.%(ext)s" "<url>"
```

If a domestic-CN site fails with a proxy tunnel error, retry with `--proxy ""`
(a local HTTP proxy breaks some domestic CDNs); if an international site times
out, retry *with* the local proxy.

Check duration: `ffprobe -v error -show_entries format=duration -of csv=p=0 source.mp4`

### 2. Locate the segment

Never track "the whole video." Find the exact scene with a 1–2 fps contact
sheet, then expand around it:

```bash
ffmpeg -v error -ss <start_s> -t 40 -i source.mp4 -vf "fps=1,scale=240:-1,tile=5x8" -frames:v 1 contact.png
```

Read the sheet, pick the beat boundaries (entrance → action → exit), and cut
the final segment ±1 s of padding. Extract the frame sequence at native fps:

```bash
mkdir -p seq && ffmpeg -v error -ss <seg_start> -i source.mp4 -t <seg_dur> seq/f_%04d.png
ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 source.mp4
```

### 3. Prep overlay assets

One image per target, PNG with alpha. Unify mixed assets (app icon + logo mark
+ photo avatar) as `circle-white` badges — see asset-binding.md for why and for
the avatar circular-mask handling.

### 4. Track the targets

Full procedure and failure taxonomy:
[references/tracking-playbook.md](references/tracking-playbook.md). Short form:

1. Grid one frame where **all targets are fully visible**:
   `uv run scripts/make_sheets.py grid --frames 'seq/f_%04d.png' --index 30 --out grid.png`
   and read each target's `[x, y, w, h]` box off the grid.
2. Write the tracking config (targets + init frame), run:
   `uv run scripts/track_boxes.py --frames 'seq/f_%04d.png' --config track.json --out tracks.json --last <N>`
3. Verify: `uv run scripts/make_sheets.py tile --frames 'seq/f_%04d.png' --tracks tracks.json --start 1 --end <N> --step-frames 15 --out verify.png`
   and look at every tile.
4. Fix what the tiles show: re-anchor later segments (shot changes, scale
   blowups, drift), or take over a smooth long shot with `manual_keys`. Expect
   2–3 rounds. Then mark `visible`/`fade_in`/`fade_out` for every exit,
   entrance, and empty-stretch — a logo parked on an empty frame is the most
   visible possible bug.

### 5. Render

```bash
uv run scripts/render_overlay.py --frames 'seq/f_%04d.png' --tracks tracks.json \
  --overlays overlays.json --out 'out/o_%04d.png' --last <N>
```

Spot-check a rendered contact sheet (`make_sheets.py tile` over `out/`) before
encoding — much cheaper than re-encoding.

### 6. Encode + size budget

```bash
scripts/encode_outputs.sh --frames 'out/o_%04d.png' --fps <native_fps> \
  --source source.mp4 --ss <seg_start> --t <seg_dur> --mp4 meme.mp4 \
  --gif meme.gif --gif-width 400 --gif-fps 10 --gif-colors 96
```

GIF size is driven by frame count × dither noise, not palette size. To fit a
~10 MB chat-app budget, lower knobs in this order: `--gif-fps` (15→12→10),
then `--gif-width` (480→400), then `--gif-colors` (128→96).

### 7. Verify the encoded deliverables, then deliver

Extract frames from the **final MP4 and the final GIF** (`ffmpeg -ss <t>
-frames:v 1`) and look at them — the earlier checks verified intermediates;
this one verifies what the recipient will actually see. Deliver both files by
their exact paths.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| yt-dlp: `Tunnel connection failed 503` on a domestic site | local HTTP proxy intercepting | add `--proxy ""` |
| cairosvg/svglib crash: `no library called cairo` | missing system cairo | rasterize SVG via headless Chrome (asset-binding.md) |
| Tracker dies exactly at a shot change | CSRT cannot cross cuts | new `segments` entry at the new shot's first frame |
| Box drifts slowly off the target over ~1 min | template pollution | re-anchor with the tracker's own last-good box, or `manual_keys` |
| Logo parked mid-frame after subject exits | missing visibility window | `fade_out` before the exit, no `visible` range after |
| GIF massively over budget | dither noise × frames | lower `--gif-fps` first, then width, then colors |
| Logo looks fine in PNGs but wrong in the GIF | checked intermediates only | always verify frames from the encoded file (step 7) |
| Encode fails: `Failed to set value '1:a' for option 'map'` | source clip has no audio stream | the bundled script maps `1:a?` (optional); if running ffmpeg by hand, do the same or drop `--source` |

## References

- [references/asset-binding.md](references/asset-binding.md) — identity
  disambiguation gate, logo/avatar sourcing, transparency, badge styling
- [references/tracking-playbook.md](references/tracking-playbook.md) — CSRT
  failure taxonomy, re-anchor recovery, manual keyframes, fades, verify loop
