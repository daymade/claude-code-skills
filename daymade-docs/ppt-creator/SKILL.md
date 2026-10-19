---
name: ppt-creator
disable-model-invocation: true
description: >-
  Deprecated presentation entry retained as a compatibility notice. Use to check
  the retirement status of ppt-creator or identify a legacy installation.
  This package does not generate PPTX files.
---

# PPT Creator — Compatibility Notice

Treat this entry as a retirement notice. Presentation creation was retired on
2026-08-07; the distributed package contains this notice, not the former builder,
templates or creation workflow. Do not use it to generate a slide deck.

Keep the existing `daymade-docs:ppt-creator` identity for installed-plugin
compatibility. A manual invocation can explain this status; it cannot restore
the retired workflow. This entry is scheduled for removal in `daymade-docs` v2.0.0.

For a new presentation, use `deck-creator` only when it is already installed;
otherwise select a presentation workflow actually available in the current host.
No replacement builder is bundled with this notice; do not promise access to a
private edition.
