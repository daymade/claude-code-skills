# Independent Review Protocol

The operational detail behind standing discipline #5. SKILL.md carries the rules and the
pass/fail criteria; this file carries the reasoning, the worked cases, and the exact
procedure. Read it the first time you run an independent pass, and any time a pass returns
something you are tempted to argue with.

## Why self-review cannot substitute

Your "it's good now" judgment runs on the same model that produced the artifact, so it
shares the exact blind spots that produced the defect. This is measured, not folklore:
intrinsic self-correction without external feedback does not reliably improve output and
sometimes degrades it ([Huang et al., ICLR 2024](https://arxiv.org/abs/2310.01798)). The
same model corrects the *identical* error readily when it arrives in someone else's input.
And when generator and evaluator share error modes, iterating **raises confidence without
adding information** — the output is a polished, confidently wrong artifact. Adding *more*
self-checks does not escape that; only an outside view does.

## The two faces of independence

Most authors get the first one right and never notice the second.

| Face | What fails without it | Typical mistake |
|---|---|---|
| **The reviewer's context** | It inherits your blind spots and returns a "reviewed" stamp | Using a fork of your own context |
| **The evidence it measures against** | It inherits your *conclusion* — it reads an artifact and a spec that already agree, and reports agreement | Handing it a record you edited during this work |

### Worked case: a natural controlled experiment

Three independent agents read one diff. They caught a clause that reversed a dated,
attributed decision — and missed a **second, same-shaped reversal** a few clauses away.

The only difference between the two: the first decision's record was untouched, while the
second's had been edited by the author the previous day to declare the original decision
superseded. So the reviewers read an artifact and a record that already agreed.

**Same reviewers, same defect class, one visible and one invisible; the only variable was
whether the author had written to the evidence.**

Two things follow. First, "not edited in this session" is too weak a line — that record was
poisoned the *previous* day and would have passed such a test. The correct line is **outside
the change's blast radius**. Second, the failure is invisible from the inside by
construction: every reviewer downstream of a poisoned record reports agreement, and the
report is indistinguishable from a genuine one.

### Choosing an anchor

Rank candidates by how structurally hard they are for *you* to have touched:

1. **The user's own words in the transcript.** You cannot edit them. Looks like the weakest
   anchor because it is informal; it is in fact the strongest.
2. **A git ref predating the whole line of work** — verified, not assumed:
   ```bash
   git log --oneline <ref>..HEAD -- <path>    # any commit of yours ⇒ not an anchor
   ```
3. **An append-only decision log.** "Append-only" is a convention, not an enforcement.
   Check its history the same way before trusting it.

**Greenfield has no anchor, and pretending otherwise is the failure mode.** A brand-new
skill has no prior ref and no log, and the transcript *is* your input — an artifact agreeing
with it is the design goal, not evidence. Say so, name what could not be checked, and ask
the user for the missing anchor rather than reporting an independent pass you did not run.

## Writing the reviewer prompt

Give it **exactly two things**: the artifact, and the reader spec. Nothing else — no design
rationale, no project background, no "just confirm X is fine." A leading prompt converts an
independent reviewer into a rubber stamp.

### The reader spec

State who the target reader is and what they already know. This is a *specification*, not
rationale: it says nothing about what you built or why, so it cannot rubber-stamp anything.
Omitting it wastes half the pass — without it the reviewer measures against *itself*, a blank
slate, and returns a flood of "who is this person, what does this product name mean" that
buries the findings which hold for the real reader.

| Artifact | Reader spec | The reader's failure mode |
|---|---|---|
| A document / report | *"The reader owns this project and knows the product names and the people involved; they have not seen this particular work."* | "I don't know this word" |
| **A SKILL.md** (the main case here — its primary reader is another Claude instance executing it) | *"You are an agent about to perform &lt;task&gt;. You know the general tooling but nothing about this project's history."* | "I don't know which tool to call or what to produce" |

Ask an agent-reader which **instructions it could not act on**, not which words it did not
recognize.

**State the reader spec before the run and never use it afterwards to explain findings away.**
Post-hoc "my reader already knows that" is precisely how an author discards the findings that
hurt.

### What to ask

Only what the reviewer can directly observe:

- Which sentences could you not act on?
- What contradicts what?
- What does this claim exists that does not?
- Where would you get stuck?

Never *"confirm that X is fine."*

## Interpreting what comes back

| Finding type | Authority | What to do |
|---|---|---|
| **Comprehensibility** ("I could not follow this") | **Ground truth.** It literally is the naive reader; there is no arguing with it. | Apply directly |
| **Completeness against a corpus** ("the sources contain X, the skill does not") | **Ground truth** — objective anchor: is it in the sources? | Verify the citation, then apply |
| "This might be a bug / I'd suggest Y" | Hypothesis | Reproduce it yourself before acting |
| Taste, "AI slop", aesthetics | **None** — same-model blind spot | Do not delegate this at all |

The line between legitimate filtering and discarding what hurts is the written record: a
finding you reject leaves a reason in the review file (below). A rejection with no written
reason is how an author quietly drops the inconvenient ones.

## Choosing the axes, and how many reviewers

**The axis is the question you ask; the area is the material you read.** Three reviewers
covering scenarios, arithmetic, and the diff but all asking "is this internally consistent?"
is one reviewer billed three times.

**One reviewer is the default and frequently sufficient.** In one run a single fresh pass
caught a hard arithmetic contradiction — one card asserting 4 items while two other sections
independently computed 10 — that the author's own six-item self-check gate had just certified
green, plus two captions on the same image stating different counts. Both defects were
authored by the person who had just verified them.

Add a reviewer only to cover an **additional axis**, never to re-ask the same question.
Common axes, and the one that matters most:

| Axis | The question |
|---|---|
| Coherence | Does this hang together? |
| **Fidelity** | **Is this still faithful to commitments already made?** |
| Completeness | Is anything in the sources missing here? |
| Comprehensibility | Could a naive reader act on this? |

**Fidelity is the axis self-review is structurally worst at**, because the author is the one
who moved the commitment. Coherence and fidelity are orthogonal: an artifact can be flawlessly
self-consistent while being completely unfaithful to what was already decided. If you run a
second reviewer at all, make it the fidelity one — and hand it the out-of-blast-radius anchor,
or it will simply re-derive your conclusion from your own record.

## The corpus case

When a skill is built by distilling a large source corpus (docs, transcripts, prior research),
the compression model that dropped content is the same one now judging completeness — so
self-review, *including your own grep*, systematically misses the same-*type* gaps.

Run a fresh subagent over all the source material **plus** the finished skill; have it
adversarially list what is absent or materially thinner, with source citations, ranked by
load-bearingness. Evidence: in one build the author declared "complete" twice and both times
more surfaced; the independent audit then found 15 further genuine gaps, including a
load-bearing operational mechanism the skill kept referencing but never showed how to do.

## The review file

Write `<workspace>/independent-review.md`:

```markdown
# Independent review — <artifact>, <date>

## Reviewer prompt (verbatim)
<paste exactly what you sent, so a later reader can judge whether it was leading>

## Reader spec given
<the spec, stated before the run>

## Findings
| # | Finding | Type | Disposition | Reason |
|---|---------|------|-------------|--------|
| 1 | …       | comprehensibility | applied | — |
| 2 | …       | hypothesis | rejected | reproduced, does not occur because … |

## Not checked
<anything you could not anchor — greenfield gaps, missing sources>
```

Three properties earn their keep: the **verbatim prompt** exposes a leading question; the
**disposition column** makes filtering auditable; the **not-checked section** stops an
incomplete pass from being reported as a clean one.

Re-review with a **new** agent after a substantive edit — the one that just reviewed is no
longer independent of what it reviewed. *Substantive* = you changed a rule, a contract, or a
number; not a typo or a rewording that leaves every instruction identical.
