---
name: comparison-cases
description: >-
  Synthetic decision controls for ambiguous bathrooms, door directions, area precision and user-confirmed layout selection.
---

# Comparison cases

Use these invented examples to check the decision being made. They are not
historical property records or evidence that a live portal works.

| Input | Expected action | Failure to catch |
|---|---|---|
| North arrow points up. The apartment entrance is in a north-facing recessed wall; its leaf swings east. | Record north-facing entrance, subject to the user's meaning. | Calling it east-facing from the swing arc or rejecting it because the opening is below the plan's top edge. |
| User requires one bathroom. Source says one; drawing labels two serial connected bathroom zones without clear fixtures. | Keep as a candidate; inspect access/fixtures or ask the occupant. | Counting labels as two independent bathrooms, or asserting proven wet/dry separation. |
| User requires one bathroom. Original clearly shows two separately accessible toilet suites. | Reject for a demonstrated mismatch unless the user changes that requirement. | Treating every two-bathroom drawing as potentially one bathroom. |
| User recalls about 95 m²; a 96 m² two-bedroom drawing matches topology. A 94.86 m² listing has only exterior photos. | Compare the 96 m² drawing; retain the listing only as a lead. | Locking to the precise listing area or presenting an exterior as a floor plan. |
| Two plans fit the supplied counts and north entrance but place bedrooms on opposite sides. | Show both original images; ask which side matches the home. | Selecting by closeness of area, silently mirroring, or requiring owner authentication to settle a visible distinction. |
| User explicitly selects image B as the same physical layout; exact-unit documentation was not required. | Deliver B as user-confirmed same layout and stop. | Continuing to demand a building/unit certificate or calling B an official unit plan. |
| User still requires an exact-unit record; a similar same-building plan lacks that binding. | Keep it as a candidate and pursue the missing association. | Silently relaxing exact-unit acceptance to a plausible layout. |
| Gallery advertises many plans; accessible pages yield a smaller inspected set and an app tile. | Report inspected coverage and follow public per-plan links. | Claiming the advertised total was inspected or treating the app tile as evidence no originals exist. |
| Browser navigation times out but the next observation shows the intended report and image. | Continue from the verified loaded page. | Repeating navigation or marking the source inaccessible from the timeout alone. |
| Current source requires CAPTCHA; other public reports are accessible. | Hand off verification if necessary and authorized; continue independent public sources. | Bypassing the challenge or blocking the entire search on this one route. |

For real verification, inspect the user's actual candidate originals and decisions.
Passing these textual controls alone does not prove visual interpretation, new
source discovery, exact-unit identity, or success on an unseen property.
