# Analysis Dimensions

Detailed definitions for each audit dimension. Agents should use these as exploration guides.

## Dimension 1: Frontend Navigation & Information Density

**Goal**: Quantify cognitive load for a new user.

**Key questions**:
1. How many top-level components does App.tsx mount simultaneously?
2. How many tabs/sections exist in each sidebar panel?
3. Which features have multiple entry points (duplicate navigation)?
4. What is the total count of interactive elements on first screen?
5. Are there panels/drawers that overlap in functionality?

**Exploration targets**:
- Main app entry (App.tsx or equivalent)
- Left sidebar / navigation components
- Right sidebar / inspector panels
- Floating panels, drawers, modals
- Settings / configuration panels
- Control center / dashboard panels

**Output format**:
```
| Component | Location | Interactive Elements | Overlaps With |
|-----------|----------|---------------------|----------------|
```

## Dimension 2: User Journey & Empty State

**Goal**: Evaluate time-to-first-value for a new user.

**Key questions**:
1. What does a user see when they have no data/sessions/projects?
2. How many steps from launch to first successful action?
3. Is there an onboarding flow? How many steps?
4. How many clickable elements compete for attention in the empty state?
5. Are high-frequency actions visually prioritized over low-frequency ones?

**Exploration targets**:
- Empty state components
- Onboarding dialogs/wizards
- Prompt input area and surrounding controls
- Quick start templates / suggested actions
- Mobile-specific navigation and input

**Output format**:
```
Step N: [Action] → [What user sees] → [Next possible actions: count]
```

## Dimension 3: Backend API Surface

**Goal**: Identify API bloat, inconsistency, and unused endpoints.

**Key questions**:
1. How many total API endpoints exist?
2. Which endpoints have no corresponding frontend call?
3. Are error responses consistent across all endpoints?
4. Is authentication applied consistently?
5. Are there duplicate endpoints serving similar purposes?

**Exploration targets**:
- Router files (API route definitions)
- Frontend API client / fetch calls
- Error handling middleware
- Authentication middleware
- API documentation / OpenAPI spec

**Output format**:
```
| Method | Path | Purpose | Has Frontend Consumer | Auth Required |
|--------|------|---------|----------------------|---------------|
```

## Dimension 4: Architecture & Module Structure

**Goal**: Identify coupling, duplication, and dead code.

**Key questions**:
1. Which modules have circular dependencies?
2. Where is the same pattern duplicated across 3+ files?
3. Which modules have unclear single responsibility?
4. Are there unused exports or dead code paths?
5. How deep is the import chain for core operations?

**Exploration targets**:
- Module `__init__.py` / `index.ts` files
- Import graphs (who imports whom)
- Utility files and shared helpers
- Configuration and factory patterns

## Dimension 5: Documentation & Config Consistency

**Goal**: Find gaps between claims and reality.

**Key questions**:
1. Does README list features that don't exist in code?
2. Are config file defaults consistent with code defaults?
3. Is there documentation for removed/renamed features?
4. Which modules have zero test coverage?
5. Are there TODO/FIXME/HACK comments in production code?

**Exploration targets**:
- README.md, CLAUDE.md, CONTRIBUTING.md
- Config files (YAML, JSON, .env)
- Test directories (coverage gaps)
- Source code comments (TODO/FIXME/HACK)
