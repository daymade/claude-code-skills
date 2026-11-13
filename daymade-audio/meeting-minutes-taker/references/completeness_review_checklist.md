# Meeting Minutes Review Checklist

> **Scope note**: this checklist is a same-context self-review — the reviewer holds the draft it just built while re-reading the transcript, so a blind spot shared by generation and review (e.g., a narrative-voiced directive none of the passes classified as a decision) survives every phase below. That structural gap is covered separately by SKILL.md **Step 3.5 Retrieval Self-Test** (fresh-context extractor that never sees the draft); run both — this checklist is not a substitute for it, nor vice versa.

## Contents
- Completeness Review Process (4 phases: structural, content depth, quotes, action items)
- Common Omission Patterns (technical, business logic, process items)
- Merge Strategy (multi-version union rules)
- Red Flags (signs of missing content)

## Completeness Review Process

### Phase 1: Structural Check

- [ ] All major discussion topics from transcript are covered
- [ ] Transcript-backed decisions have supporting quotes; note-only additions have labeled sources
- [ ] All speakers who made decisions are attributed
- [ ] Action items have specific owners (not generic "team")
- [ ] Stated priorities retained; unstated priorities remain unknown
- [ ] All supplied participant notes/corrections are integrated into one current minutes document, with original source identities retained

### Phase 2: Content Depth Check

For each transcript section, verify:

- [ ] **Entities/Data Models**: All mentioned entities captured (tables, fields, relationships)
- [ ] **Numerical Values**: Ranges, priorities, counts preserved (e.g., "0-99", "4 states", "3-4 categories")
- [ ] **State Machines**: All states and transitions documented
- [ ] **Architecture Decisions**: Data flow, dependencies, integration points
- [ ] **Trade-offs**: Rejected alternatives and reasoning
- [ ] **Constraints**: Technical limitations, MVP scope boundaries

### Phase 3: Quote Verification

For significant transcript-backed decisions, ensure (note-only additions use their labeled original source):

- [ ] Quote accurately reflects speaker's point
- [ ] Speaker attribution is correct
- [ ] Context around quote is preserved

### Phase 4: Action Items Audit

Cross-reference with transcript for:

- [ ] Explicit task assignments ("Alice will handle...", "Bob, please...")
- [ ] Implicit commitments ("I will design...", "Backend team will...")
- [ ] Deferred items ("Defer to later...", "Not in MVP scope...")
- [ ] Follow-up discussions needed ("Discuss offline...", "Follow up separately...")
- [ ] Supplied note-only additions and TODO/DONE updates are checked as well as transcript claims
- [ ] DONE names the exact completed action and its source; prerequisites, responsibility agreements and downstream results are distinct
- [ ] Missing owner, deadline or completion evidence stays unknown; the note author is not assumed to own every task
- [ ] Later reversals and conditions from every supplied source are reflected in the active task rows

## Common Omission Patterns

### Technical Details Often Missed

1. **Entity Hierarchies**: Category → Subcategory → Item → Detail
2. **Field Definitions**: What fields belong to which entity
3. **Calculation Rules**: Priority orders, workflow logic, matching rules
4. **Storage Decisions**: Where data is persisted, what's cached
5. **API Contracts**: Who calls whom, sync vs async

### Business Logic Often Missed

1. **State Transitions**: What triggers state changes
2. **Permission Rules**: Who can do what
3. **Validation Rules**: Required fields, constraints
4. **Display Logic**: What's shown where, sorting rules
5. **Integration Points**: Cross-system data sharing

### Process Items Often Missed

1. **Design Approach**: Joint vs separate design decisions
2. **Dependency Order**: What blocks what
3. **Offline Follow-ups**: Items requiring separate discussion
4. **Scope Deferrals**: What's explicitly pushed to Phase 2

## Merge Strategy (Multi-Version Union)

When merging versions:

1. **Keep source-supported content from the existing version** - Preserve useful superseded alternatives in Discussion
2. **Add source-supported content from the incoming version** - Union valid findings, consolidate duplicates
3. **Reconcile before combining** - Follow SKILL.md Step 1–2: use the final effective state for the same fact; keep distinct perspectives, and put irreconcilable conflicts in Open Questions
4. **Preserve more detailed version** - When same topic has different depth
5. **Maintain structure** - Keep section numbering logical

### Merge Checklist

- [ ] All sections from original preserved
- [ ] All sections from new version added (or merged into existing)
- [ ] No duplicate content (consolidate if same info appears twice)
- [ ] Quotes from both versions preserved
- [ ] Valid action items from both versions merged, with superseded commitments excluded from active rows
- [ ] Retrieval Self-Test reads every supplied source without seeing the draft; note-only claims retain their source labels
- [ ] Numbering remains sequential

## Red Flags (Signs of Missing Content)

- Transcript mentions a topic not in minutes
- Decision recorded without quote
- Action item without clear owner
- Long transcript section summarized in one sentence
- Technical discussion with no entity/field names
- "TBD" items without clear description
- State machine with fewer states than mentioned
- Priority/order system without number ranges
