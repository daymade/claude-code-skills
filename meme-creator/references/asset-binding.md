---
name: asset-binding
description: Overlay asset acquisition and identity disambiguation for meme-creator — how to source logos/avatars with transparency, the mandatory disambiguation gate before binding a name to an account or logo, and badge styling. Read before fetching any logo or avatar for a meme.
---

# Asset binding: get the right image of the right entity

A meme that puts the *wrong person's* avatar on screen is worse than no meme.
Do these in order: disambiguate the identity first, then fetch the asset.

## Identity disambiguation gate (run before any asset fetch)

Trigger: the user names a person/product/org by a first name, nickname, or
abbreviation ("use Tibo's avatar", "put the Codex logo on it") and you must
bind it to a concrete account or file.

1. **Enumerate at least two candidates.** At least one must come from a search
   query that does *not* contain your guessed handle/ID. Searching
   `tibo_maker twitter` can only ever find `@tibo_maker`; searching
   `Tibo OpenAI Codex` can find the other one. A query containing the answer
   proves existence, never identity.
2. **Write the discriminating reason from the request context.** Point at
   specific words: the peer entities listed alongside, the domain, the user's
   scene. "Listed next to Codex and Claude" discriminates; "he's famous in the
   community" does not (both candidates usually pass that).
3. **If context cannot decide, present the candidates and let the user pick.**
   A ten-second question is cheaper than re-rendering 500 frames.
4. **In a correction round, re-verify the proposition actually questioned.**
   "The avatar belongs to this account" and "this account is the person the
   user meant" are different propositions; when the user challenges identity,
   evidence about account-avatar binding adds zero. And never embed your
   previous conclusion in the new verification query.
5. **Confidence goes down after a challenge, not up.** Unless you acquired a
   new discriminating fact, answer a second round with a candidate list, not
   a "confirmed, here's proof" verdict.

Real case (all public figures): asked to put "Tibo" next to Codex and Claude
in a meme, the first pass bound it to `@tibo_maker` (Thibault Louis-Lucas,
indie maker — real person, real account, real vibe-coding content). The user
meant `@thsottiaux` (Thibault Sottiaux, OpenAI's Codex lead). Every
verification of round one passed — the avatar really was that account's —
because existence had been checked instead of identity. The discriminating
signal sat unused in the original request: the peer set (Codex, Claude).

## Sourcing the images

- **Brand logos**: prefer the official brand/press page, then a reputable
  vector index (e.g. simple-icons CDN for OSS/tech brands). Check the logo is
  current — brands re-mark without asking you.
- **Avatars (X/Twitter, GitHub)**: `unavatar.io/x/<handle>?fallback=false`
  returns the current avatar and errors on a nonexistent handle when
  `fallback=false` — that error is itself evidence the handle exists. A
  profile-mirror page (bio text) is a good second source for identity.
- **SVG → PNG with real transparency**: headless Chrome does it without any
  native dependency:
  `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --screenshot=out.png --window-size=512,512 --default-background-color=00000000 file.svg`
  (macOS full path — `chrome` is usually not on PATH; on Linux use
  `google-chrome`/`chromium`. cairosvg and svglib/renderPM both need system
  cairo — often absent).
- Verify each fetched image is what you think before compositing: open it
  (view the file), confirm it has an alpha channel with real transparency,
  and confirm the depicted entity matches the identity you bound.

## Badge styling (visual consistency beats logo purity)

Mixed overlay assets (a dark app icon, an orange mark, a photo avatar) sit on
footage with wildly varying backgrounds. Normalize them instead of fighting
contrast case by case:

- **`circle-white` (default)**: white disc + subtle dark ring, mark/photo
  inside. Pops on dark and light footage alike; the consistent shape reads as
  "intentional sticker set" rather than three unrelated images.
- `circle`: transparent background circle crop (good for avatars that already
  have their own ring/border baked in).
- `none`: use the asset as-is (when the asset already has strong contrast on
  this specific footage — verify on a sample frame).

Photo avatars get a circular alpha mask (center, radius ≈ 98% of half-width);
don't ship the square JPEG corners.
