# Promptfoo API Reference

## Provider Configuration

### Echo Provider (No API Calls)

```yaml
providers:
  - echo  # Returns prompt as-is, no API calls
```

**Use cases:**
- Preview rendered prompts without cost
- Debug variable substitution
- Verify few-shot structure
- Test configuration before production runs

**Cost:** Free - no tokens consumed.

### Anthropic

```yaml
providers:
  - id: anthropic:messages:claude-sonnet-4-5-20250929
    config:
      max_tokens: 4096
      temperature: 0.7
```

### OpenAI

```yaml
providers:
  - id: openai:gpt-4.1
    config:
      temperature: 0.5
      max_tokens: 2048
```

### Multiple Providers (A/B Testing)

```yaml
providers:
  - id: anthropic:messages:claude-sonnet-4-5-20250929
    label: Claude
  - id: openai:gpt-4.1
    label: GPT-4.1
```

## Assertion Reference

### Python Assertion Context

```python
class AssertionContext:
    prompt: str              # Raw prompt sent to LLM
    vars: dict               # Test case variables
    test: dict               # Complete test case
    config: dict             # Assertion config
    provider: Any            # Provider info
    providerResponse: Any    # Full response
```

### GradingResult Format

```python
{
    "pass": bool,           # Required: pass/fail
    "score": float,         # 0.0-1.0 score
    "reason": str,          # Explanation
    "named_scores": dict,   # Custom metrics
    "component_results": [] # Nested results
}
```

### Assertion Types

| Type | Description | Parameters |
|------|-------------|------------|
| `contains` | Substring check | `value` |
| `icontains` | Case-insensitive | `value` |
| `equals` | Exact match | `value` |
| `regex` | Pattern match | `value` |
| `not-contains` | Absence check | `value` |
| `starts-with` | Prefix check | `value` |
| `contains-any` | Any substring | `value` (array) |
| `contains-all` | All substrings | `value` (array) |
| `cost` | Token cost | `threshold` |
| `latency` | Response time | `threshold` (ms) |
| `perplexity` | Model confidence | `threshold` |
| `python` | Custom Python | `value` (file/code) |
| `javascript` | Custom JS | `value` (code) |
| `llm-rubric` | LLM grading | `value`, `threshold` |
| `factuality` | Fact checking | `value` (reference) |
| `model-graded-closedqa` | Q&A grading | `value` |
| `similar` | Semantic similarity | `value`, `threshold` |

## Test Case Configuration

### Full Test Case Structure

```yaml
- description: "Test name"
  vars:
    var1: "value"
    var2: file://path.txt
  assert:
    - type: contains
      value: "expected"
  metadata:
    category: "test-category"
    priority: high
  options:
    provider: specific-provider
    transform: "output.trim()"
```

### Loading Variables from Files

```yaml
vars:
  # Text file (loaded as string)
  content: file://data/input.txt

  # JSON/YAML (parsed to object)
  config: file://config.json

  # Python script (executed, returns value)
  dynamic: file://scripts/generate.py

  # PDF (text extracted)
  document: file://docs/report.pdf

  # Image (base64 encoded)
  image: file://images/photo.png
```

## Advanced Patterns

### Dynamic Test Generation (Python)

```python
# tests/generate.py
def get_tests():
    return [
        {
            "vars": {"input": f"test {i}"},
            "assert": [{"type": "contains", "value": str(i)}]
        }
        for i in range(10)
    ]
```

```yaml
tests: file://tests/generate.py:get_tests
```

### Scenario-based Testing

```yaml
scenarios:
  - config:
      - vars:
          language: "French"
      - vars:
          language: "Spanish"
    tests:
      - vars:
          text: "Hello"
        assert:
          - type: llm-rubric
            value: "Translation is accurate"
```

### Transform Output

```yaml
defaultTest:
  options:
    transform: |
      output.replace(/\n/g, ' ').trim()
```

### Custom Grading Provider

```yaml
defaultTest:
  options:
    provider: openai:gpt-4.1
  assert:
    - type: llm-rubric
      value: "Evaluate quality"
      provider: anthropic:claude-3-haiku  # Override for this assertion
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `PROMPTFOO_PYTHON` | Python binary path |
| `PROMPTFOO_CACHE_ENABLED` | Enable caching (default: true) |
| `PROMPTFOO_CACHE_PATH` | Cache directory |

## CLI Commands

```bash
# Initialize project
npx promptfoo@latest init

# Run evaluation
npx promptfoo@latest eval [options]

# Options:
#   --config <path>     Config file path
#   --output <path>     Output file path
#   --grader <provider> Override grader model
#   --no-cache          Disable caching
#   --filter-metadata   Filter tests by metadata
#   --repeat <n>        Repeat each test n times
#   --delay <ms>        Delay between requests
#   --max-concurrency   Parallel requests

# View results
npx promptfoo@latest view [options]

# Share results
npx promptfoo@latest share

# Generate report
npx promptfoo@latest generate dataset
```

## Output Formats

```bash
# JSON (default)
--output results.json

# CSV
--output results.csv

# HTML report
--output results.html

# YAML
--output results.yaml
```
