# Media playback and output cases

Use for an existing media library, review viewer, or playback/download complaint.
The auditor uses the selected browser owner's actual input and observation APIs;
this recipe adds acceptance cases, not another browser driver. Use Level A for
native download UI. If required capabilities or media are unavailable, report the
exact gap and continue independent visual checks; a source URL or HTTP probe does
not fill that gap. Do not change media, review facts or snapshots during an audit.

## Select by media state before bulk work

Bind actor, actual route, object key, platform/source ID, media version/role and
viewport before selecting a sample. Use explicit identity when titles repeat.
Cover the types actually present: portrait, landscape, long video, original plus
compatible preview, tall image/note, and missing/error. One object may cover
several types. Use the project's desktop widths; do not add mobile scope by default.
Exercise representative boundary types through the whole journey early, then
expand the data import or release. A list of titles is not a media browsing result.

## READ-DO journey

1. **Poster:** open the exact object from the user's actual entry. Confirm identity,
   ownership and current review. Save a screenshot and media-container rectangle.
   A poster alone proves neither a playable file nor a download.
2. **Playback:** use the visible play control. Observe advancing frames and time,
   and check the expected audio. Record the active source role and actual duration;
   `readyState`, `loadedmetadata`, a changed button or HTTP 200 alone is insufficient.
   Compare the frame before and after playback: intrinsic video dimensions must not
   expand the page or push native controls outside the desktop viewport. Inspect
   ancestor clipping as well as whole-page overflow; hidden overflow can conceal
   the unreachable right edge or lower controls while scroll-width checks pass.
3. **Seek:** use the real timeline and seek well into the item, including a late
   segment for long video. Observe the new time and resumed frames/audio. A Range
   response is supporting transport evidence, not proof that seeking worked.
4. **Download:** click the native download action, observe completion and inspect
   the file actually saved by the browser. Match its expected object/media role,
   byte count and hash where authoritative identity is available; probe and fully
   decode it, then open it in the intended recipient player. A copied URL, request
   log, fetched replacement file or programmatic handler call does not pass this
   browser-output journey. Signed source URLs and credentials stay out of reports.
5. **Return/recovery:** return to the same object and filter scope. Exercise the
   relevant missing/error branch without manufacturing a bad review. The source
   may be unavailable while its historical business judgment remains valid.

## Known-answer controls

Run the measurement/recipe against one healthy and the affected failing state.
Record each examined object/state and the actual observations; zero examined media
cannot pass. Existing project fixtures or retained before/after evidence are useful
controls, but are not a fresh audit of a later application build.

| State | Observation that can fail the case | Healthy control |
|---|---|---|
| Portrait poster → playing video | After play, frame grows with intrinsic dimensions; controls extend below viewport or an ancestor clips them | Frame remains constrained with the full natural picture and reachable controls |
| Landscape video | Cropping hides source content, aspect ratio distorts, or player displaces the review | Natural landscape frame and relevant review can be inspected together |
| Tall image + notice + source action | Parent max-height confines image and following text together, so notice/action overlap or clip | Constrain media itself; notice and source action flow below with a visible gap and a discoverable page scroll |
| Original plus compatible preview | Preview is labeled original, or native download silently serves another role | Visible role and downloaded identity agree; original/proxy provenance stays distinct |
| Long item | Duration cap misclassifies a valid file, or late seek stalls while start plays | Real duration is retained and late seek resumes playback |
| Missing/error | Thumbnail/avatar or another object's video masks absence; source failure changes review verdict | Exact source gap is visible, original judgment and recovery/source action remain available |

For the tall-image case, measure the bottom of the image, top/bottom of the notice
and top of the source action after image decode and text wrapping. The action may
be below the fold if normal page scrolling reaches it; do not fail that as clipping.
For every case, inspect screenshot pixels as well as rectangles. Verify that the
media, review wording, reason and applicability scope refer to the same object;
whole-film rejection may coexist with permission to reuse a local technique.

Report playback, seeking, download completion, downloaded-file identity and visual
geometry as separate observations. If one remains unobserved, mark that axis
partial rather than calling the entire media journey verified.
