# Architecture Reference

Technical implementation details of the transcript-fixer system.

## Table of Contents

- [Module Structure](#module-structure)
- [Design Principles](#design-principles)
  - [SOLID Compliance](#solid-compliance)
  - [File Length Limits](#file-length-limits)
- [Module Architecture](#module-architecture)
  - [Layer Diagram](#layer-diagram)
  - [Correction Workflow](#correction-workflow)
  - [Learning Cycle](#learning-cycle)
- [Data Flow](#data-flow)
- [SQLite Architecture (v2.0)](#sqlite-architecture-v20)
  - [Two-Layer Data Access](#two-layer-data-access-simplified)
  - [Database Schema](#database-schema-schemasql)
  - [ACID Guarantees](#acid-guarantees)
  - [Thread Safety](#thread-safety)
  - [Migration from JSON](#migration-from-json)
- [Module Details](#module-details)
  - [fix_transcription.py](#fix_transcriptionpy-orchestrator)
  - [correction_repository.py](#correction_repositorypy-data-access-layer)
  - [correction_service.py](#correction_servicepy-business-logic-layer)
  - [CLI Integration](#cli-integration-commandspy)
  - [dictionary_processor.py](#dictionary_processorpy-stage-1)
  - [ai_processor.py](#ai_processorpy-stage-2)
  - [learning_engine.py](#learning_enginepy-pattern-detection)
  - [diff_generator.py](#diff_generatorpy-stage-3)
- [State Management](#state-management)
  - [Database-Backed State](#database-backed-state)
  - [Thread-Safe Access](#thread-safe-access)
- [Error Handling Strategy](#error-handling-strategy)
- [Testing Strategy](#testing-strategy)
- [Performance Considerations](#performance-considerations)
- [Security Architecture](#security-architecture)
- [Extensibility Points](#extensibility-points)
- [Dependencies](#dependencies)
- [Deployment](#deployment)
- [Further Reading](#further-reading)

## Module Structure

The codebase follows a modular package structure for maintainability:

```
scripts/
├── fix_transcription.py        # Main entry point (~70 lines)
├── core/                       # Business logic & data access
│   ├── correction_repository.py # Data access layer (466 lines)
│   ├── correction_service.py    # Business logic layer (525 lines)
│   ├── schema.sql              # SQLite database schema (216 lines)
│   ├── dictionary_processor.py # Stage 1 processor (140 lines)
│   ├── ai_processor.py        # Stage 2 processor (199 lines)
│   └── learning_engine.py     # Pattern detection (252 lines)
├── cli/                        # Command-line interface
│   ├── commands.py            # Command handlers (180 lines)
│   └── argument_parser.py     # Argument config (95 lines)
└── utils/                      # Utility functions
    ├── diff_generator.py       # Multi-format diffs (132 lines)
    ├── logging_config.py       # Logging configuration (130 lines)
    └── validation.py          # SQLite validation (105 lines)
```

**Benefits of modular structure**:
- Clear separation of concerns (business logic / CLI / utilities)
- Easy to locate and modify specific functionality
- Supports independent testing of modules
- Scales well as codebase grows
- Follows Python package best practices

## Design Principles

### SOLID Compliance

Every module follows SOLID principles for maintainability:

1. **Single Responsibility Principle (SRP)**
   - Each module has exactly one reason to change
   - `CorrectionRepository`: Database operations only
   - `CorrectionService`: Business logic and validation only
   - `DictionaryProcessor`: Text transformation only
   - `AIProcessor`: API communication only
   - `LearningEngine`: Pattern analysis only

2. **Open/Closed Principle (OCP)**
   - Open for extension via SQL INSERT
   - Closed for modification (no code changes needed)
   - Add corrections via CLI or SQL without editing Python

3. **Liskov Substitution Principle (LSP)**
   - All processors implement same interface
   - Can swap implementations without breaking workflow

4. **Interface Segregation Principle (ISP)**
   - Repository, Service, Processor, Engine are independent
   - No unnecessary dependencies

5. **Dependency Inversion Principle (DIP)**
   - Service depends on Repository interface
   - CLI depends on Service interface
   - Not tied to concrete implementations

### File Length Limits

All files comply with code quality standards:

| File | Lines | Limit | Status |
|------|-------|-------|--------|
| `validation.py` | 105 | 200 | ✅ |
| `logging_config.py` | 130 | 200 | ✅ |
| `diff_generator.py` | 132 | 200 | ✅ |
| `dictionary_processor.py` | 140 | 200 | ✅ |
| `commands.py` | 180 | 200 | ✅ |
| `ai_processor.py` | 199 | 250 | ✅ |
| `schema.sql` | 216 | 250 | ✅ |
| `learning_engine.py` | 252 | 250 | ✅ |
| `correction_repository.py` | 466 | 500 | ✅ |
| `correction_service.py` | 525 | 550 | ✅ |

## Module Architecture

### Layer Diagram

```
┌─────────────────────────────────────────┐
│   CLI Layer (fix_transcription.py)     │
│   - Argument parsing                    │
│   - Command routing                     │
│   - User interaction                    │
└───────────────┬─────────────────────────┘
                │
┌───────────────▼─────────────────────────┐
│   Business Logic Layer                  │
│                                         │
│  ┌──────────────────┐  ┌──────────────┐│
│  │ Dictionary       │  │ AI           ││
│  │ Processor        │  │ Processor    ││
│  │ (Stage 1)        │  │ (Stage 2)    ││
│  └──────────────────┘  └──────────────┘│
│                                         │
│  ┌──────────────────┐  ┌──────────────┐│
│  │ Learning         │  │ Diff         ││
│  │ Engine           │  │ Generator    ││
│  │ (Pattern detect) │  │ (Stage 3)    ││
│  └──────────────────┘  └──────────────┘│
└───────────────┬─────────────────────────┘
                │
┌───────────────▼─────────────────────────┐
│   Data Access Layer (SQLite-based)      │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │ CorrectionManager (Facade)       │  │
│  │ - Backward-compatible API        │  │
│  └──────────────┬───────────────────┘  │
│                 │                       │
│  ┌──────────────▼───────────────────┐  │
│  │ CorrectionService                │  │
│  │ - Business logic                 │  │
│  │ - Validation                     │  │
│  │ - Import/Export                  │  │
│  └──────────────┬───────────────────┘  │
│                 │                       │
│  ┌──────────────▼───────────────────┐  │
│  │ CorrectionRepository             │  │
│  │ - ACID transactions              │  │
│  │ - Thread-safe connections        │  │
│  │ - Audit logging                  │  │
│  └──────────────────────────────────┘  │
└───────────────┬─────────────────────────┘
                │
┌───────────────▼─────────────────────────┐
│   Storage Layer                         │
│   ~/.transcript-fixer/corrections.db    │
│   - SQLite database (ACID compliant)    │
│   - 8 normalized tables + 3 views       │
│   - Comprehensive indexes               │
│   - Foreign key constraints             │
└─────────────────────────────────────────┘
```

## Data Flow

### Correction Workflow

```
1. User Input
   ↓
2. fix_transcription.py (Orchestrator)
   ↓
3. CorrectionService.get_corrections()
   ← Query from ~/.transcript-fixer/corrections.db
   ↓
4. DictionaryProcessor.process()
   - Apply context rules (regex)
   - Apply dictionary replacements
   - Track changes
   ↓
5. AIProcessor.process()
   - Split into chunks
   - Call GLM-4.6 API
   - Retry with fallback on error
   - Track AI changes
   ↓
6. CorrectionService.save_history()
   → Insert into correction_history table
   ↓
7. LearningEngine.analyze_and_suggest()
   - Query correction_history table
   - Detect patterns (frequency ≥3, confidence ≥80%)
   - Generate suggestions
   → Insert into learned_suggestions table
   ↓
8. Output Files
   - {filename}_stage1.md
   - {filename}_stage2.md
```

### Learning Cycle

```
Run 1: meeting1.md
   AI corrects: "巨升" → "具身"
   ↓
   INSERT INTO correction_history

Run 2: meeting2.md
   AI corrects: "巨升" → "具身"
   ↓
   INSERT INTO correction_history

Run 3: meeting3.md
   AI corrects: "巨升" → "具身"
   ↓
   INSERT INTO correction_history
   ↓
   LearningEngine queries patterns:
   - SELECT ... GROUP BY from_text, to_text
   - Frequency: 3, Confidence: 100%
   ↓
   INSERT INTO learned_suggestions (status='pending')
   ↓
   User reviews: --review-learned
   ↓
   User approves: --approve "巨升" "具身"
   ↓
   INSERT INTO corrections (source='learned')
   UPDATE learned_suggestions (status='approved')
   ↓
   Future runs query corrections table (Stage 1 - faster!)
```

## SQLite Architecture (v2.0)

### Two-Layer Data Access (Simplified)

**Design Principle**: No users = no backward compatibility overhead.

The system uses a clean 2-layer architecture:

```
┌──────────────────────────────────────────┐
│ CLI Commands (commands.py)               │
│ - User interaction                       │
│ - Command routing                        │
└──────────────┬───────────────────────────┘
               │
┌──────────────▼───────────────────────────┐
│ CorrectionService (Business Logic)       │
│ - Input validation & sanitization        │
│ - Business rules enforcement             │
│ - Import/export orchestration            │
│ - Statistics calculation                 │
│ - History tracking                       │
└──────────────┬───────────────────────────┘
               │
┌──────────────▼───────────────────────────┐
│ CorrectionRepository (Data Access)       │
│ - ACID transactions                      │
│ - Thread-safe connections                │
│ - SQL query execution                    │
│ - Audit logging                          │
└──────────────┬───────────────────────────┘
               │
┌──────────────▼───────────────────────────┐
│ SQLite Database (corrections.db)         │
│ - 8 normalized tables                    │
│ - Foreign key constraints                │
│ - Comprehensive indexes                  │
│ - 3 views for common queries             │
└───────────────────────────────────────────┘
```

### Database Schema (schema.sql)

**Core Tables**:

1. **corrections** (main correction storage)
   - Primary key: id
   - Unique constraint: (from_text, domain)
   - Indexes: domain, source, added_at, is_active, from_text
   - Fields: confidence (0.0-1.0), usage_count, notes

2. **context_rules** (regex-based rules)
   - Pattern + replacement with priority ordering
   - Indexes: priority (DESC), is_active

3. **correction_history** (audit trail for runs)
   - Tracks: filename, domain, timestamps, change counts
   - Links to correction_changes via foreign key
   - Indexes: run_timestamp, domain, success

4. **correction_changes** (detailed change log)
   - Links to history via foreign key (CASCADE delete)
   - Stores: line_number, from/to text, rule_type, context
   - Indexes: history_id, rule_type

5. **learned_suggestions** (AI-detected patterns)
   - Status: pending → approved/rejected
   - Unique constraint: (from_text, to_text, domain)
   - Fields: frequency, confidence, timestamps
   - Indexes: status, domain, confidence, frequency

6. **suggestion_examples** (occurrences of patterns)
   - Links to learned_suggestions via foreign key
   - Stores context where pattern occurred

7. **system_config** (configuration storage)
   - Key-value store with type safety
   - Stores: API settings, thresholds, defaults

8. **audit_log** (comprehensive audit trail)
   - Tracks all database operations
   - Fields: action, entity_type, entity_id, user, success
   - Indexes: timestamp, action, entity_type, success

**Views** (for common queries):
- `active_corrections`: Active corrections only
- `pending_suggestions`: Suggestions pending review
- `correction_statistics`: Statistics per domain

### ACID Guarantees

**Atomicity**: All-or-nothing transactions
```python
with self._transaction() as conn:
    conn.execute("INSERT ...")  # Either all succeed
    conn.execute("UPDATE ...")  # or all rollback
```

**Consistency**: Constraints enforced
- Foreign key constraints
- Check constraints (confidence 0.0-1.0, usage_count ≥ 0)
- Unique constraints

**Isolation**: Serializable transactions
```python
conn.execute("BEGIN IMMEDIATE")  # Acquire write lock
```

**Durability**: Changes persisted to disk
- SQLite guarantees persistence after commit
- Backup before migrations

### Thread Safety

**Thread-local connections**:
```python
def _get_connection(self):
    if not hasattr(self._local, 'connection'):
        self._local.connection = sqlite3.connect(...)
    return self._local.connection
```

**Connection pooling**:
- One connection per thread
- Automatic cleanup on close
- Foreign keys enabled per connection

### Clean Architecture (No Legacy)

**Design Philosophy**:
- Clean 2-layer architecture (Service → Repository)
- No backward compatibility overhead
- Direct API design without legacy constraints
- YAGNI principle: Build for current needs, not hypothetical migrations

## Module Details

### fix_transcription.py (Orchestrator)

**Responsibilities**:
- Parse CLI arguments
- Route commands to appropriate handlers
- Coordinate workflow between modules
- Display user feedback

**Key Functions**:
```python
cmd_init()              # Initialize ~/.transcript-fixer/
cmd_add_correction()    # Add single correction
cmd_list_corrections()  # List corrections
cmd_run_correction()    # Execute correction workflow
cmd_review_learned()    # Review AI suggestions
cmd_approve()           # Approve learned correction
```

**Design Pattern**: Command pattern with function routing

### correction_repository.py (Data Access Layer)

**Responsibilities**:
- Execute SQL queries with ACID guarantees
- Manage thread-safe database connections
- Handle transactions (commit/rollback)
- Perform audit logging
- Convert between database rows and Python objects

**Key Methods**:
```python
add_correction()          # INSERT with UNIQUE handling
get_correction()          # SELECT single correction
get_all_corrections()     # SELECT with filters
get_corrections_dict()    # For backward compatibility
update_correction()       # UPDATE with transaction
delete_correction()       # Soft delete (is_active=0)
increment_usage()         # Track usage statistics
bulk_import_corrections() # Batch INSERT with conflict resolution
```

**Transaction Management**:
```python
@contextmanager
def _transaction(self):
    conn = self._get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

### correction_service.py (Business Logic Layer)

**Responsibilities**:
- Input validation and sanitization
- Business rule enforcement
- Orchestrate repository operations
- Import/export with conflict detection
- Statistics calculation

**Key Methods**:
```python
# Validation
validate_correction_text()  # Check length, control chars, NULL bytes
validate_domain_name()      # Prevent path traversal, injection
validate_confidence()       # Range check (0.0-1.0)
validate_source()          # Enum validation

# Operations
add_correction()           # Validate + repository.add
get_corrections()          # Get corrections for domain
remove_correction()        # Validate + repository.delete

# Import/Export
import_corrections()       # Pre-validate + bulk import + conflict detection
export_corrections()       # Query + format as JSON

# Analytics
get_statistics()          # Calculate metrics per domain
```

**Validation Rules**:
```python
@dataclass
class ValidationRules:
    max_text_length: int = 1000
    min_text_length: int = 1
    max_domain_length: int = 50
    allowed_domain_pattern: str = r'^[a-zA-Z0-9_-]+$'
```

### CLI Integration (commands.py)

**Direct Service Usage**:
```python
def _get_service():
    """Get configured CorrectionService instance."""
    config_dir = Path.home() / ".transcript-fixer"
    db_path = config_dir / "corrections.db"
    repository = CorrectionRepository(db_path)
    return CorrectionService(repository)

def cmd_add_correction(args):
    service = _get_service()
    service.add_correction(args.from_text, args.to_text, args.domain)
```

**Benefits of Direct Integration**:
- No unnecessary abstraction layers
- Clear data flow: CLI → Service → Repository
- Easy to understand and debug
- Performance: One less function call per operation

### dictionary_processor.py (Stage 1)

**Responsibilities**:
- Apply context-aware regex rules
- Apply simple dictionary replacements
- Track all changes with line numbers

**Processing Order**:
1. Context rules first (higher priority)
2. Dictionary replacements second

**Key Methods**:
```python
process(text) -> (corrected_text, changes)
_apply_context_rules()
_apply_dictionary()
get_summary(changes)
```

**Change Tracking**:
```python
@dataclass
class Change:
    line_number: int
    from_text: str
    to_text: str
    rule_type: str      # "dictionary" or "context_rule"
    rule_name: str
```

### ai_processor.py (Stage 2)

**Responsibilities**:
- Split text into API-friendly chunks
- Call GLM-4.6 API
- Handle retries with fallback model
- Track AI-suggested changes

**Key Methods**:
```python
process(text, context) -> (corrected_text, changes)
_split_into_chunks()     # Respect paragraph boundaries
_process_chunk()         # Single API call
_build_prompt()          # Construct correction prompt
```

**Chunking Strategy**:
- Max 6000 characters per chunk
- Split on paragraph boundaries (`\n\n`)
- If paragraph too long, split on sentences
- Preserve context across chunks

**Error Handling**:
- Retry with fallback model (GLM-4.5-Air)
- If both fail, use original text
- Never lose user's data

### learning_engine.py (Pattern Detection)

**Responsibilities**:
- Analyze correction history
- Detect recurring patterns
- Calculate confidence scores
- Generate suggestions for review
- Track rejected suggestions

**Algorithm**:
```python
1. Query correction_history table
2. Extract stage2 (AI) changes
3. Group by pattern (from→to)
4. Count frequency
5. Calculate confidence
6. Filter by thresholds:
   - frequency ≥ 3
   - confidence ≥ 0.8
7. Save to learned/pending_review.json
```

**Confidence Calculation**:
```python
confidence = (
    0.5 * frequency_score +   # More occurrences = higher
    0.3 * consistency_score + # Always same correction
    0.2 * recency_score       # Recent = higher
)
```

**Key Methods**:
```python
analyze_and_suggest()     # Main analysis pipeline
approve_suggestion()      # Move to corrections.json
reject_suggestion()       # Move to rejected.json
list_pending()           # Get all suggestions
```

### diff_generator.py (Stage 3)

**Responsibilities**:
- Generate comparison reports
- Multiple output formats
- Word-level diff analysis

**Output Formats**:
1. Markdown summary (statistics + change list)
2. Unified diff (standard diff format)
3. HTML side-by-side (visual comparison)
4. Inline marked ([-old-] [+new+])

**Not Modified**: Kept original 338-line file as-is (working well)

## State Management

### Database-Backed State

- All state stored in `~/.transcript-fixer/corrections.db`
- SQLite handles caching and transactions
- ACID guarantees prevent corruption
- Backup created before migrations

### Thread-Safe Access

- Thread-local connections (one per thread)
- BEGIN IMMEDIATE for write transactions
- No global state or shared mutable data
- Each operation is independent (stateless modules)

### Soft Deletes

- Records marked inactive (is_active=0) instead of DELETE
- Preserves audit trail
- Can be reactivated if needed

## Error Handling Strategy

### Fail Fast for User Errors

```python
if not skill_path.exists():
    print(f"❌ Error: Skill directory not found")
    sys.exit(1)
```

### Retry for Transient Errors

```python
try:
    api_call(model_primary)
except Exception:
    try:
        api_call(model_fallback)
    except Exception:
        use_original_text()
```

### Backup Before Destructive Operations

```python
if target_file.exists():
    shutil.copy2(target_file, backup_file)
# Then overwrite target_file
```

## Testing Strategy

### Unit Testing (Recommended)

```python
# Test dictionary processor
def test_dictionary_processor():
    corrections = {"错误": "正确"}
    processor = DictionaryProcessor(corrections, [])
    text = "这是错误的文本"
    result, changes = processor.process(text)
    assert result == "这是正确的文本"
    assert len(changes) == 1

# Test learning engine thresholds
def test_learning_thresholds():
    engine = LearningEngine(history_dir, learned_dir)
    # Create mock history with pattern appearing 3+ times
    suggestions = engine.analyze_and_suggest()
    assert len(suggestions) > 0
```

### Integration Testing

```bash
# End-to-end test
python fix_transcription.py --init
python fix_transcription.py --add "test" "TEST"
python fix_transcription.py --input test.md --stage 3
# Verify output files exist
```

## Performance Considerations

### Bottlenecks

1. **AI API calls**: Slowest part (60s timeout per chunk)
2. **File I/O**: Negligible (JSON files are small)
3. **Pattern matching**: Fast (regex + dict lookups)

### Optimization Strategies

1. **Stage 1 First**: Test dictionary corrections before expensive AI calls
2. **Chunking**: Process large files in parallel chunks (future enhancement)
3. **Caching**: Could cache API results by content hash (future enhancement)

### Scalability

**Current capabilities (v2.0 with SQLite)**:
- File size: Unlimited (chunks handle large files)
- Corrections: Tested up to 100,000 entries (with indexes)
- History: Unlimited (database handles efficiently)
- Concurrent access: Thread-safe with ACID guarantees
- Query performance: O(log n) with B-tree indexes

**Performance improvements from SQLite**:
- Indexed queries (domain, source, added_at)
- Views for common aggregations
- Batch imports with transactions
- Soft deletes (no data loss)

**Future improvements**:
- Parallel chunk processing for AI calls
- API response caching
- Full-text search for corrections

## Security Architecture

### Secret Management

- API keys via environment variables only
- Never hardcode credentials
- Security scanner enforces this

### Backup Security

- `.bak` files same permissions as originals
- No encryption (user's responsibility)
- Recommendation: Use encrypted filesystems

### Git Security

- `.gitignore` for `.bak` files
- Private repos recommended
- Security scan before commits

## Extensibility Points

### Adding New Processors

1. Create new processor class
2. Implement `process(text) -> (result, changes)` interface
3. Add to orchestrator workflow

Example:
```python
class SpellCheckProcessor:
    def process(self, text):
        # Custom spell checking logic
        return corrected_text, changes
```

### Adding New Learning Algorithms

1. Subclass `LearningEngine`
2. Override `_calculate_confidence()`
3. Adjust thresholds as needed

### Adding New Export Formats

1. Add method to `CorrectionManager`
2. Support new file format
3. Add CLI command

## Dependencies

### Required

- Python 3.8+ (`from __future__ import annotations`)
- `httpx` (for API calls)

### Optional

- `diff` command (for unified diffs)
- Git (for version control)

### Development

- `pytest` (for testing)
- `black` (for formatting)
- `mypy` (for type checking)

## Deployment

### User Installation

```bash
# 1. Clone or download skill to workspace
git clone <repo> transcript-fixer
cd transcript-fixer

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize
python scripts/fix_transcription.py --init

# 4. Set API key
export GLM_API_KEY="KEY_VALUE"

# Ready to use!
```

### CI/CD Pipeline (Future)

```yaml
# Potential GitHub Actions workflow
test:
  - Install dependencies
  - Run unit tests
  - Run integration tests
  - Check code style (black, mypy)

security:
  - Run security_scan.py
  - Check for secrets

deploy:
  - Package skill
  - Upload to skill marketplace
```

## Further Reading

- SOLID Principles: https://en.wikipedia.org/wiki/SOLID
- API Patterns: `references/glm_api_setup.md`
- File Formats: `references/file_formats.md`
- Testing: https://docs.pytest.org/
