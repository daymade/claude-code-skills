# Course text and video in one reader

Use when a change affects a course reader with timed prose, inline images and the matching
original video. Reuse existing content/source checks; this recipe tests the reading journey.
Use the actual delivered URL, video and scroll owner. An export receipt, visible video tag,
loaded metadata or successful seek assignment alone does not establish usable playback.

At the affected wide and portrait sizes, perform these ordinary actions:

1. Open a deep chapter through the outline. Compare its visible heading and first paragraph
   with the active cue. In portrait, inspect the entire fixed player and outline together:
   the destination must appear below them, and enough prose must remain visible to read.
   Expanding the outline must leave a usable selection and closing path.
2. Click a visible paragraph timestamp. Observe actual matching video frames and the native
   playback time; confirm it is the same player, document and tab. Preserve original-video
   coordinates, including a course whose useful content starts after waiting or roll call.
3. Scroll at least two viewports. Check that the promised fixed player remains visible.
   Use “video corresponding text” to return, then enable following and cross a paragraph
   boundary during playback. The resulting paragraph and its time control must be visible
   below the fixed area. A large player leaving only a clipped text sliver is a failure.
4. Enlarge an inline image and close it. Check the same visible passage, scroll position and
   usable focus return; do not count a new image tab as an in-place inspection.
5. Rotate or resize to landscape and back without reloading. Verify the promised layout,
   original video time and playback/paused state. Changing viewport can itself alter scroll
   geometry: wait for layout to settle before judging a return-position defect. A paused
   rotation test proves paused retention only; it does not prove uninterrupted playing.

Report actual dimensions, target time, matching frame observation, visible destination and
the tested retention state. Distinguish browser viewport emulation from physical-device testing.
Do not prescribe these layouts for unrelated readers, universal player heights or a complete
viewport/state matrix. Stop after affected journeys pass; a CSS-only change does not justify
retranscribing or reviewing an unchanged whole course.

## Known-answer calibration

Resolve `assets/course-video-reader-fixture.html` from the loaded Skill root and open it with
`?video=<URL-encoded local video URL>`. Use a local playable video covering every timestamp
offered by the fixture. Its reading content is synthetic; no customer's recording is bundled or downloaded.

- No `failure` parameter: healthy fixed portrait player and target offsets.
- `&failure=static-video`: after scrolling, the player leaves the viewport.
- `&failure=covered-target`: the deep chapter/paragraph lands behind the fixed player.
- `&failure=reset-player`: changing portrait/landscape resets the current time.

First establish the healthy journey, then demonstrate that the corresponding failing state is
rejected by the same observation. Do not alter the criterion to accept the injected failure.
These controls calibrate geometry and media-state observations; content fidelity and matching
course identity still require the actual delivered course. Fixture input counts and passing
DOM assertions do not replace looking at the populated reader and using its controls.
