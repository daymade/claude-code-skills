---
name: tracking-playbook
description: Semi-supervised object tracking playbook for meme-creator — CSRT failure modes, re-anchor recovery, when to switch to manual keyframes, visibility windows and fades, and the verify-before-render loop. Read when the tracking step of meme-creator misbehaves, drifts, or when planning how to track targets across shot changes.
---

# Tracking playbook

The render is only as good as the boxes. This file is the decision layer for
`scripts/track_boxes.py`: when CSRT works, how it fails, and what to do instead.

## The loop (never skip the verify step)

1. Track with `track_boxes.py`.
2. Draw the result with `make_sheets.py tile --tracks tracks.json` over ~10
   sample frames per shot.
3. Look at every tile. A box that is 10–20 px off at 960x720 will read as
   "logo floating beside the head" in the final GIF.
4. Fix (re-anchor or keyframes), re-run, re-verify. Two or three rounds is
   normal for a 15-second clip.

Boxes that pass on sampled frames can still jitter frame-to-frame. The
`smooth` block in the tracking config (median 5 + average 5) exists for this;
leave it on.

## How CSRT fails (so you recognize it on the verification sheet)

| Failure | Looks like | Cause | Fix |
|---|---|---|---|
| Shot change | tracker returns None / box frozen on empty scene | the shot it learned is gone | start a new `segments` entry at the first frame of the new shot |
| Fast scale-up (subject walks toward camera) | box stays small, sits on one corner of the now-huge subject | scale adaptation saturates over ~100 frames | re-anchor a bigger box at a later frame |
| Slow drift | box slides sideways ~1 px/frame, off-target after 60-100 frames | template pollution | re-anchor from the tracker's own last-good box (read it from the verification tile), or switch to keyframes |
| Occlusion cluster | box jumps to the overlapping neighbor | two similar textures cross | short range: fade out before the cluster, fade in after; or keyframe through it |
| Subject leaves frame | box clamps at the edge, logo parked mid-screen | nothing to track | not a bug: define `fade_out` before the exit and nothing after |

## Re-anchor cheaply: reuse the tracker's own good box

When a verification tile shows the box is still correct at frame N but wrong at
N+80, read the box at N straight out of `tracks.json` and use it as the
`init_frame: N` segment box. Zero coordinate-reading work, kills the drift.

## Manual keyframes: the underrated winner

For slow, smooth motion (walking away from camera, steady pans), 6–9
hand-read keys over a long shot look *better* than any tracker: motion glides,
no jitter, no drift. Fast or erratic motion is the opposite — keep the tracker
there and add more re-anchors.

Read keys efficiently with `make_sheets.py band`: it stacks the same
horizontal band of several frames into one image with global coordinates, so
one image yields 3 boxes per listed frame:

```bash
uv run scripts/make_sheets.py band --frames 'seq/f_%04d.png' \
  --list 380,400,420 --yrange 80:560 --out band_a.png
```

Keys belong in `manual_keys` of the overlays config,
not in the tracking config — they interpolate at render time and override the
tracker across their span.

## Visibility windows and fades

Overlays must not hang around when their subject is off-screen:

- Subject exits: track as far as reliable, then `fade_out` over 6-8 frames.
  The renderer extrapolates with the last 5-frame velocity, so the badge keeps
  moving with the subject as it leaves instead of freezing then vanishing.
- Empty frames between shots: nothing visible — no `visible` window there.
- New shot starts: `fade_in` over ~8 frames at the new positions.

Fades of 6-8 frames at 30 fps are invisible as fades; they just read as "it
walked out of frame."

## Scale and placement

- Badge diameter ≈ box width × 1.25–1.35 covers the head/face fully. Below 1.1
  the subject's ears/edges leak out; above 1.5 it swallows the scene.
- `dy: -0.03` nudges the badge up slightly because boxes that include ears or
  chin sit a touch low.
- Verify placement on the **encoded** output (extract frames from the final
  MP4/GIF), not only on the intermediate PNG sequence — encoders can shift
  your assumptions about how it reads at delivery size.
