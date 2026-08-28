# Design Board Contract

## Workspace Layout

Keep exploration artifacts outside production source directories:

```text
<session-dir>/
├── board.json
├── design-board.html
├── variant-a.html
├── variant-b.html
├── variant-c.html
├── feedback.json
├── feedback-pending.json
└── approved.json
```

Only files produced by the current session belong here. Reuse an earlier workspace
only when the user explicitly asks to revisit that decision.

## Candidate Runtime Isolation

Candidate HTML runs in a sandboxed `srcdoc` frame. The Board injects a Content
Security Policy that permits inline prototype CSS and JavaScript plus embedded
`data:` / `blob:` media, while denying network connections, nested frames, object
embeds, navigation form submissions, and popup creation. Keep every candidate
self-contained even when a browser would otherwise allow JavaScript to create a
dynamic request.

## `board.json`

Use this schema. Variant files are relative to `board.json`, must remain within the
same directory tree, and must be self-contained HTML.

```json
{
  "schemaVersion": "interaction-design-board/v1",
  "title": "Bounded product surface",
  "objective": "The user-visible decision this comparison must improve",
  "task": "The representative task the user will perform in every candidate",
  "invariants": [
    "Business fact or first-view requirement held constant"
  ],
  "variants": [
    {
      "id": "command-first",
      "label": "A · Command first",
      "hypothesis": "Why this architecture may improve the task",
      "tradeoff": "What it may make worse",
      "file": "variant-a.html",
      "states": [
        {
          "name": "default",
          "expected": "What the user can observe or do in this state"
        },
        {
          "name": "evidence-open",
          "expected": "What changes and what must remain visible"
        }
      ]
    }
  ]
}
```

Do not persist a variant count; the builder derives it from `variants`.

## `feedback.json`

The Board creates this payload when the user selects a direction:

```json
{
  "schemaVersion": "interaction-design-board/feedback-v1",
  "prototypeRevision": "content-derived sha256 identifier",
  "boardId": "runtime Board identifier when a feedback server adds one",
  "preferred": "command-first",
  "comments": {
    "command-first": {
      "noticedFirst": "User's words",
      "worked": "User's words",
      "failed": "User's words"
    }
  },
  "overall": "Cross-candidate feedback",
  "remix": "Parts to combine, if any",
  "regenerated": false
}
```

`feedback-pending.json` uses the same shape with `regenerated: true` and an
additional `regenerateAction` of `iterate` or `remix`.

## `approved.json`

Write this only after the user confirms the agent's interpretation of the feedback:

```json
{
  "schemaVersion": "interaction-design-board/approval-v1",
  "prototypeRevision": "same content identity as feedback",
  "boardId": "runtime Board identifier when present",
  "approvedVariant": "command-first",
  "approvedSummary": "The confirmed interaction decision",
  "interactionRules": [
    "Observable rule that production implementation must preserve"
  ],
  "firstViewInvariant": [
    "Information or action that cannot be hidden"
  ],
  "rejectedTradeoffs": [
    "Rejected behavior and why"
  ],
  "exercisedStates": [
    "command-first:default",
    "command-first:evidence-open"
  ],
  "remainingUnknowns": [],
  "prototypeFiles": [
    {
      "id": "command-first",
      "path": "variant-a.html",
      "sha256": "sha256:<exact file digest>"
    }
  ],
  "approvedAt": "ISO-8601 timestamp with timezone"
}
```

Compute file hashes when writing approval; do not copy a digest from an earlier
iteration. A changed prototype requires a new Board and new approval.

## Feedback Transport

On gstack's current multi-Board daemon, the Board POSTs to the relative
`./api/feedback` endpoint so the Board ID in `/boards/<id>/` remains in the route.
The daemon adds that runtime `boardId`; it does not replace the Board's
content-derived `prototypeRevision`.
On the legacy single-Board server, it uses the injected
`window.__GSTACK_SERVER_URL` and POSTs to `/api/feedback`. When opened as a local
file, it downloads the same JSON payload. All modes preserve one contract. A
successful response or downloaded file is transport evidence, not approval; the
user still confirms the interpretation before `approved.json` is written.
