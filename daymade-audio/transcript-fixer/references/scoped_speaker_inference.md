# Task-scoped speaker inference

Load this branch only when the user explicitly authorizes inferring speaker
identities for a named transcript or task. The executing agent checks the grant
and produces the artifacts below; no script turns a confidence judgment into
identity authority. A request to fix names, clean a transcript, or make it readable
does not supply that grant. If the target is ambiguous, keep speaker labels while
continuing ordinary correction; resolve only the missing authorization scope.

## Keep correction and assignment separate

- **ASR name-word correction:** repairing a name inside spoken text follows the
  existing roster, evidence, queue and person-name verdict gates. This grant does
  not relax those gates or close their pending rows.
- **Speaker assignment:** associating an anonymous label with a person is allowed
  only in a separately labeled derived reader under this branch. Keep the raw
  source bytes and original speaker-label lines intact. Do not overwrite the
  canonical transcript, participants field or an authoritative speaker mapping.
- Explicit human mappings and authoritative source labels outrank inference.
  Preserve their exact source; do not replace a confirmed identity with a guess.
  Permission to infer a name is not a human-confirmed mapping.

## Read-do workflow

1. Record the user's exact grant and its message/source locator beside the task's
   artifacts, outside the Skill bundle. Bind the named task, source artifact and
   digest, intended derived output, and the grant's expiry (this task only).
   Do not add a global preference or reuse it for another recording/webinar.
2. Preserve the original artifact byte-for-byte and identify the canonical
   transcript used for the reader. If correction is also requested, complete its
   ordinary native workflow separately; retain unresolved correction status.
3. Read the complete dialogue and supplied context. For each anonymous speaker,
   collect the exact passages and locators supporting a candidate, conflicting
   cues, and what remains unknown. Inspect an available authoritative event page,
   agenda or explicit identity record when it could discriminate candidates;
   cite what it actually establishes. A participant list, topical similarity,
   frequency or another model's agreement alone does not bind a person to a turn.
   Audio absence does not block this authorized branch: record it and retain the
   uncertainty; voice resemblance alone does not confirm identity.
4. Keep one evidence row per original speaker label, including those left
   anonymous: original label, candidate or `unknown`, quoted dialogue/context
   locators, external authority and its limit (or unavailable), counterevidence,
   confidence with reason, and status `inferred`, `unknown`, or `human-mapped`
   only when an explicit human mapping is cited. Conflicting or insufficient
   evidence stays anonymous; do not force a complete mapping.
5. Create a separate reader artifact labeled `speaker identities inferred —
   not confirmed`, linked to the preserved source and evidence table. Retain each
   original label alongside a candidate, for example `Speaker A [inferred:
   Guest Alpha]`; unknown labels remain unchanged. Preserve turn order,
   timestamps and spoken bodies from the bound canonical transcript. Any ASR
   correction belongs in the ordinary correction diff, not an inference edit.
6. Read back both artifacts independently. Compare the raw digest to its frozen
   value; compare every original label, timestamp and turn body between the
   canonical transcript and the derived reader, allowing only the declared
   annotations. Count all turns, including continuation lines. Inspect every
   difference and fail the reader delivery if a body, timestamp or attribution
   changed beyond that allowance. Report unresolved identities and correction
   status separately from completion of the inferred reader.

Do not write inferred names into a global/project dictionary, people roster,
confirmed-correct record, participants metadata or `human-confirmed` tag. Do not
use this permission as `--authority`/`--authority-record` for a person-name
verdict. A later explicit user mapping may become authority for that occurrence;
its wording and scope must be read, not inferred from approval of the reader.
Ordinary final/high-quality transcript claims still require their existing
review, pending-row and finalization checks. An inferred reader does not satisfy
them or establish confirmed identities.

## Synthetic acceptance cases

Use these as output-level replay inputs; names and dialogue are synthetic.

**Authorized one-off.** The user says: “For webinar A only, infer the speaker
names in a separate reader copy.” Raw turns:

```text
Speaker A 00:00:01
Welcome. Guest Alpha, could you describe your parser?
Speaker B 00:00:06
Thanks. I wrote the parser and will show the export path.
Speaker C 00:00:12
I have a question about retries.
```

The supplied event agenda lists Host Delta and Guest Alpha, without a speaker
mapping. No audio is available. Produce the scope record, unchanged source,
per-speaker evidence and labeled reader. Speaker B may read `Speaker B [inferred:
Guest Alpha]` with the A→B address/response cited; the agenda only corroborates
attendance. A host candidate needs its own supporting evidence; Speaker C stays
anonymous. All bodies and timestamps stay identical. Do not label the agenda or
the grant a human confirmation; no identity inference applies to webinar B.

**No inference grant.** With the same source, the user says: “Fix transcription
errors and make the speaker names easier to read.” Preserve A/B/C and continue
ordinary correction; do not assign names from the agenda. If the user separately
says “Speaker B is Guest Alpha,” cite that exact mapping as human authority,
preserve it, and keep A/C anonymous. An explicit mapping authorizes that mapping,
not inference for the other speakers.
