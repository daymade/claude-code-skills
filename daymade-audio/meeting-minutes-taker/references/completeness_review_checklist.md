# Meeting Minutes Review Checklist

Before this same-context review, load the [source and status contract](../SKILL.md#step-1-read-and-analyze-transcript) and [source-backed UNION merge](../SKILL.md#core-principle-multiple-complete-passes--union-merge). Run the separate [Retrieval Self-Test](../SKILL.md#step-35-retrieval-self-test-consumption-side-verification) as well.

## Completeness Review Process

### Phase 1: Structural Check

- [ ] All major discussion topics from transcript are covered
- [ ] Every decision has locatable evidence under the source contract
- [ ] All speakers who made decisions are attributed
- [ ] Task-owner attribution and priorities match the original supplied evidence
- [ ] Compare every supplied source with the draft for coverage

### Phase 2: Content Depth Check

For each transcript section, verify:

- [ ] **Entities/Data Models**: All mentioned entities captured (tables, fields, relationships)
- [ ] **Numerical Values**: Ranges, priorities, counts preserved (e.g., "0-99", "4 states", "3-4 categories")
- [ ] **State Machines**: All states and transitions documented
- [ ] **Architecture Decisions**: Data flow, dependencies, integration points
- [ ] **Trade-offs**: Rejected alternatives and reasoning
- [ ] **Constraints**: Technical limitations, MVP scope boundaries

### Phase 3: Quote Verification

Check evidence selected under the source contract; for transcript quotations:

- [ ] Quote accurately reflects speaker's point
- [ ] Speaker attribution is correct
- [ ] Context around quote is preserved

### Phase 4: Action Items Audit

Cross-reference with all supplied sources for:

- [ ] Explicit task assignments ("Alice will handle...", "Bob, please...")
- [ ] Implicit commitments ("I will design...", "Backend team will...")
- [ ] Deferred items ("Defer to later...", "Not in MVP scope...")
- [ ] Follow-up discussions needed ("Discuss offline...", "Follow up separately...")
- [ ] Compare each status with the exact action its source supports
- [ ] Check unknown fields and later corrections against the source/status and merge contracts

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

Audit the merge against the canonical contract loaded above.

### Merge Checklist

- [ ] Compare both versions' source-supported sections, details and final states with the merged draft
- [ ] No duplicate content (consolidate if same info appears twice)
- [ ] Verify retained quotations from both versions against their original sources
- [ ] Check the final action rows against both versions and original sources
- [ ] Inspect the separate Retrieval Self-Test's inputs and recorded results
- [ ] Numbering remains sequential

## Red Flags (Signs of Missing Content)

- Transcript mentions a topic not in minutes
- Decision evidence cannot be located in the supplied sources
- Task-owner attribution unsupported by its source
- Long transcript section summarized in one sentence
- Technical discussion with no entity/field names
- "TBD" items without clear description
- State machine with fewer states than mentioned
- Priority/order system without number ranges
