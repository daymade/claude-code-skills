# Reference-Parity Decomposition

Load this before implementing or auditing anything whose pass condition names a
visual reference — "make it look like this screenshot", "match product X's
page", "why does theirs look premium and ours doesn't". It governs the
reference-parity profile from the main workflow.

Why this file exists: a real login-page rebuild against a public product's
sign-in screen took **five user-caught correction rounds** before parity held.
The deltas the user had to catch, one or two per round: a missing image, an
edge-to-edge split where the reference had page margins and a rounded inset
card, a logo that center-drifted 130px with the form instead of staying pinned,
a form block off its column's centerline, an image cropped — then letterboxed —
against an explicit no-crop instruction. Every structural delta was visible in
the reference from the first day (the letterbox was fix-induced, §4 tells that
part). One decomposition pass would have caught them together; the
complaint-driven loop caught them one at a time, at the price of the user's
patience. Every rule below was paid for in that engagement — the deltas
themselves, the loop that kept missing them, the green assertion suite that
certified each miss, and the ratio translation that finally closed it.

## Contents

- The first deliverable is a measured inventory, not a fix list
- A user-caught delta is evidence the inventory is incomplete
- Your own assertions are Level D for parity claims
- A vetoed effect indicts the premise, not the parameter
- User-supplied assets render faithfully by default
- Translate relationships, not values
- Pre-report confirmation

## 1. The first deliverable is a measured inventory, not a fix list

Before writing or judging any implementation, decompose the reference into
measured structural relationships. Screenshot pixels are measurable with any
tool that reports coordinates — open the reference image and read positions off
it (an image viewer's pointer, a quick script cropping/measuring with an image
library, or pasting it into a canvas at known scale); precision within a few
pixels is plenty, because everything converts to **ratios against the
reference's own viewport** before use. The inventory is a written block —
element, relationship, measured value/ratio — kept wherever the audit's working
notes live and reproduced in the report's parity enumeration (§2). It inherits
the main workflow's evidence rules: a user-supplied reference screenshot is the
same sensitive raw evidence as any capture, so persist the measurements and
ratios, not re-shared copies of the image. The inventory covers, for every
major element:

- **Anchoring** — pinned to the page/container (stays put while content
  centers) vs part of a centered stack. The classic miss: a logo that is pinned
  top-left in the reference but gets nested inside the implementation's
  vertically-centered pane, so it drifts with content height. The two read
  almost identically in a casual glance and completely differently in use.
- **Container discipline** — content living in a centered max-width container
  (margins grow on wide screens) vs full-bleed edge-to-edge. Measure the
  reference's content-start x-position as a fraction of viewport width; ~0 means
  full-bleed, ~10% means a container. A generic template defaults to full-bleed
  50/50 splits; references that read "premium" usually don't.
- **Aspect-ratio ownership** — for each box containing media: does the box
  impose its size on the media (forcing a fit strategy), or does the media's
  intrinsic ratio size the box? Diagnose from the reference: if the image is
  never cropped and never letterboxed, its box hugs the image — the box has no
  independent size at all.
- **Scale ladder** — headline height as a fraction of viewport height, and its
  ratio to body text. "Premium" references often run the hero headline at
  5–6% of viewport height — roughly double a typical component-scale heading
  token. If the implementation reuses its largest existing token and still looks
  like a form label, measure before concluding the font is wrong.
- **Material chrome** — which surfaces are elevated cards (background + border +
  radius + shadow) vs naked content on the page ground.
- **Column/region ratios** — measured, not assumed 50/50.
- **Intra-region alignment** — which elements share a centerline or edge
  *within* their region. A form block hugging its column's left edge while the
  reference centers headline, card, and footer on one vertical axis is a
  structural miss, not a spacing nit — and it only becomes visible once the
  column is wider than the content, which is exactly when nobody re-checks it.
- **Spacing rhythm** — the two or three load-bearing gaps (headline→subtitle,
  subtitle→card), measured, mapped to the project's nearest spacing tokens.

The inventory is cheap — minutes against a screenshot — and it is the artifact
every later round reuses. Without it, each audit round re-derives a partial
reading from memory, and memory supplies a generic template of the pattern
instead of the reference's actual choices.

## 2. A user-caught delta is evidence the inventory is incomplete

When the user catches a parity delta you missed, the tempting response is to
fix that item and re-declare parity. Don't stop there. The process that missed
this delta had no reason to have caught the others — so treat the catch as
falsifying the inventory, not just the pixel: redo or extend the decomposition,
re-diff **every** relationship in it, and only then report. In the five-round
case above, every round's fix was correct and every round's "done" was wrong,
because "done" was only ever measured against the deltas already complained
about.

Corollary for the report: a parity claim must enumerate the inventory's
relationships with a per-item verdict (matched / deliberately diverged + why /
not yet). "I fixed what you pointed out" is a change log, not a parity claim.

What "matched" means depends on the relationship's type. Most inventory
relationships are **categorical** — pinned vs centered, container vs
full-bleed, box hugs media vs box imposes size, card vs naked surface — and
categorical relationships match exactly or not at all; there is no tolerance to
argue about, which is why the inventory leans on them. **Scalar** values
(ratios, scale fractions, gaps) match at the implementing project's own
granularity: the translated target lands on the nearest design token or scale
step, and sitting on that token is a match — a 0.47 measured column fraction
implemented as the project's 50% grid step matches; drifting a further step off
does not. When a scalar has no token to snap to, state the measured pair and
the accepted deviation in the verdict instead of silently rounding.

## 3. Your own assertions are Level D for parity claims

Geometry assertions you wrote encode your own reading of the reference. When
that reading is wrong, the assertions are wrong in the same way, and green
proves "implementation matches my misreading" — with full confidence. In the
real case, a 22-assertion layout suite stayed green through three consecutive
structural misreads; each round's fix also rewrote the assertions, which then
guarded the new reading, which was still incomplete.

The scoping is by **claim type**, and it cuts across the main workflow's
evidence table: a project E2E/Playwright run sits at Level B *for the claims
that table lists* — DOM geometry, routes, focus, overlays, interaction states,
repeatable responsive behavior — and your suite keeps that standing for
regression claims. But "matches the
reference" is not among Level B's supported claims, and for that claim the
same suite drops to Level D, because the reference never entered it: only your
reading of the reference did. The oracle for parity is the reference artifact
plus measured comparison, nothing else. The correct order is: inventory first,
then derive assertions **from the inventory**, so the suite guards the
decomposed understanding rather than the guess that preceded it. The suite then
earns its keep as a regression guard — it just never gets to certify parity on
its own.

## 4. A vetoed effect indicts the premise, not the parameter

When the user vetoes a visible effect — "the image must never be cropped",
"nothing may overlap the headline" — locate the structural premise that made
the effect possible before touching any parameter. The trap: a fixed-size
container forces a fit strategy on its media, and every fit value is some
violation — `cover` crops, `contain` letterboxes. Toggling between them swaps
one violation for its mirror image while feeling like a fix. Two rounds were
lost this way: "no cropping" was answered with `cover → contain` inside the
same full-height container, producing letterbox bands the user rejected next.

The test: **state the veto as a property, and ask whether any parameter value
under the current premise satisfies it.** "Image always fully visible AND no
dead bands" is unsatisfiable while the container owns the size; it becomes
trivially true the moment the media's intrinsic ratio sizes the container. If
no parameter value satisfies the property, stop tuning and change the premise.

## 5. User-supplied assets render faithfully by default

Choosing a crop focal point, an `object-position`, a recolor, or a zoom to hide
an awkward region of a user-supplied asset is silently editing the user's
material. It reads as a rendering decision to you and as a mutilated asset to
its owner. Default to faithful, uncropped, unrecolored rendering; when the
composition genuinely needs a transformation, surface it as an explicit
tradeoff ("cropping at 72% hides the awkward seam but cuts the left card —
want that, or shall I resize the layout instead?") before shipping it.

## 6. Translate relationships, not values

When your constraints differ from the reference's — a landscape asset where the
reference uses portrait, a CJK sans stack where the reference uses a serif, a
different brand radius — copying the reference's literal values betrays it.
(Both examples below are from the same engagement as the preamble's case; they
were the final round's actual derivations.) Port the **relationship** and
re-derive the value:

- The reference's image column is *narrower* than its text column, yet the
  image dominates — because a portrait image takes its height from its own
  ratio. With a landscape asset, the same "image is the dominant mass"
  relationship forces the column ratio to **invert** (image column wider),
  since width is the only lever a landscape ratio gives you for height. The
  faithful translation contradicts the literal measurement.
- A serif display face signaling "editorial" does not survive into a product
  whose font stack ships no serif; the relationship ("headline is a different
  voice, twice the body scale") ports into weight/size contrast within the
  existing stack.

Record each translated relationship with its derivation next to the inventory,
so a reviewer can check the reasoning — otherwise every deliberate divergence
looks identical to a miss.

## 7. Pre-report confirmation

Work from the method above, then stop at the same pause point as the main
workflow's completion gate and confirm each item before reporting parity:

- Measured inventory of the reference exists and is written down.
- Every inventory relationship has a verdict: matched / deliberately diverged
  (with recorded derivation) / not yet.
- Assertions were re-derived from the inventory after the last structural
  correction, not carried over from before it.
- Any user veto in force is restated as a property, with the premise-level
  answer named.
- Any transformation applied to a user-supplied asset was disclosed and
  approved, or removed.
- Side-by-side evidence: reference and implementation cropped to the same
  region at the same scale, per the main workflow's evidence rules.
