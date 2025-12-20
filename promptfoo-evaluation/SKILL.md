---
name: promptfoo-evaluation
description: Configures and runs LLM evaluation using Promptfoo framework. Use when setting up prompt testing, creating evaluation configs (promptfooconfig.yaml), writing Python custom assertions, implementing llm-rubric for LLM-as-judge, or managing few-shot examples in prompts. Triggers on keywords like "promptfoo", "eval", "LLM evaluation", "prompt testing", or "model comparison".
---

# Promptfoo Evaluation

## Overview

This skill provides guidance for configuring and running LLM evaluations using [Promptfoo](https://www.promptfoo.dev/), an open-source CLI tool for testing and comparing LLM outputs.

## Quick Start

```bash
# Initialize a new evaluation project
npx promptfoo@latest init

# Run evaluation
npx promptfoo@latest eval

# View results in browser
npx promptfoo@latest view
```

## Configuration Structure

A typical Promptfoo project structure:

```
project/
├── promptfooconfig.yaml    # Main configuration
├── prompts/
│   ├── system.md           # System prompt
│   └── chat.json           # Chat format prompt
├── tests/
│   └── cases.yaml          # Test cases
└── scripts/
    └── metrics.py          # Custom Python assertions
```

## Core Configuration (promptfooconfig.yaml)

```yaml
# yaml-language-server: $schema=https://promptfoo.dev/config-schema.json
description: "My LLM Evaluation"

# Prompts to test
prompts:
  - file://prompts/system.md
  - file://prompts/chat.json

# Models to compare
providers:
  - id: anthropic:messages:claude-sonnet-4-5-20250929
    label: Claude-4.5-Sonnet
  - id: openai:gpt-4.1
    label: GPT-4.1

# Test cases
tests: file://tests/cases.yaml

# Default assertions for all tests
defaultTest:
  assert:
    - type: python
      value: file://scripts/metrics.py:custom_assert
    - type: llm-rubric
      value: |
        Evaluate the response quality on a 0-1 scale.
      threshold: 0.7

# Output path
outputPath: results/eval-results.json
```

## Prompt Formats

### Text Prompt (system.md)

```markdown
You are a helpful assistant.

Task: {{task}}
Context: {{context}}
```

### Chat Format (chat.json)

```json
[
  {"role": "system", "content": "{{system_prompt}}"},
  {"role": "user", "content": "{{user_input}}"}
]
```

### Few-Shot Pattern

Embed examples directly in prompt or use chat format with assistant messages:

```json
[
  {"role": "system", "content": "{{system_prompt}}"},
  {"role": "user", "content": "Example input: {{example_input}}"},
  {"role": "assistant", "content": "{{example_output}}"},
  {"role": "user", "content": "Now process: {{actual_input}}"}
]
```

## Test Cases (tests/cases.yaml)

```yaml
- description: "Test case 1"
  vars:
    system_prompt: file://prompts/system.md
    user_input: "Hello world"
    # Load content from files
    context: file://data/context.txt
  assert:
    - type: contains
      value: "expected text"
    - type: python
      value: file://scripts/metrics.py:custom_check
      threshold: 0.8
```

## Python Custom Assertions

Create a Python file for custom assertions (e.g., `scripts/metrics.py`):

```python
def get_assert(output: str, context: dict) -> dict:
    """Default assertion function."""
    vars_dict = context.get('vars', {})

    # Access test variables
    expected = vars_dict.get('expected', '')

    # Return result
    return {
        "pass": expected in output,
        "score": 0.8,
        "reason": "Contains expected content",
        "named_scores": {"relevance": 0.9}
    }

def custom_check(output: str, context: dict) -> dict:
    """Custom named assertion."""
    word_count = len(output.split())
    passed = 100 <= word_count <= 500

    return {
        "pass": passed,
        "score": min(1.0, word_count / 300),
        "reason": f"Word count: {word_count}"
    }
```

**Key points:**
- Default function name is `get_assert`
- Specify function with `file://path.py:function_name`
- Return `bool`, `float` (score), or `dict` with pass/score/reason
- Access variables via `context['vars']`

## LLM-as-Judge (llm-rubric)

```yaml
assert:
  - type: llm-rubric
    value: |
      Evaluate the response based on:
      1. Accuracy of information
      2. Clarity of explanation
      3. Completeness

      Score 0.0-1.0 where 0.7+ is passing.
    threshold: 0.7
    provider: openai:gpt-4.1  # Optional: override grader model
```

**Best practices:**
- Provide clear scoring criteria
- Use `threshold` to set minimum passing score
- Default grader uses available API keys (OpenAI → Anthropic → Google)

## Common Assertion Types

| Type | Usage | Example |
|------|-------|---------|
| `contains` | Check substring | `value: "hello"` |
| `icontains` | Case-insensitive | `value: "HELLO"` |
| `equals` | Exact match | `value: "42"` |
| `regex` | Pattern match | `value: "\\d{4}"` |
| `python` | Custom logic | `value: file://script.py` |
| `llm-rubric` | LLM grading | `value: "Is professional"` |
| `latency` | Response time | `threshold: 1000` |

## File References

All paths are relative to config file location:

```yaml
# Load file content as variable
vars:
  content: file://data/input.txt

# Load prompt from file
prompts:
  - file://prompts/main.md

# Load test cases from file
tests: file://tests/cases.yaml

# Load Python assertion
assert:
  - type: python
    value: file://scripts/check.py:validate
```

## Running Evaluations

```bash
# Basic run
npx promptfoo@latest eval

# With specific config
npx promptfoo@latest eval --config path/to/config.yaml

# Output to file
npx promptfoo@latest eval --output results.json

# Filter tests
npx promptfoo@latest eval --filter-metadata category=math

# View results
npx promptfoo@latest view
```

## Troubleshooting

**Python not found:**
```bash
export PROMPTFOO_PYTHON=python3
```

**Large outputs truncated:**
Outputs over 30000 characters are truncated. Use `head_limit` in assertions.

**File not found errors:**
Ensure paths are relative to `promptfooconfig.yaml` location.

## Echo Provider (Preview Mode)

Use the **echo provider** to preview rendered prompts without making API calls:

```yaml
# promptfooconfig-preview.yaml
providers:
  - echo  # Returns prompt as output, no API calls

tests:
  - vars:
      input: "test content"
```

**Use cases:**
- Preview prompt rendering before expensive API calls
- Verify Few-shot examples are loaded correctly
- Debug variable substitution issues
- Validate prompt structure

```bash
# Run preview mode
npx promptfoo@latest eval --config promptfooconfig-preview.yaml
```

**Cost:** Free - no API tokens consumed.

## Advanced Few-Shot Implementation

### Multi-turn Conversation Pattern

For complex few-shot learning with full examples:

```json
[
  {"role": "system", "content": "{{system_prompt}}"},

  // Few-shot Example 1
  {"role": "user", "content": "Task: {{example_input_1}}"},
  {"role": "assistant", "content": "{{example_output_1}}"},

  // Few-shot Example 2 (optional)
  {"role": "user", "content": "Task: {{example_input_2}}"},
  {"role": "assistant", "content": "{{example_output_2}}"},

  // Actual test
  {"role": "user", "content": "Task: {{actual_input}}"}
]
```

**Test case configuration:**

```yaml
tests:
  - vars:
      system_prompt: file://prompts/system.md
      # Few-shot examples
      example_input_1: file://data/examples/input1.txt
      example_output_1: file://data/examples/output1.txt
      example_input_2: file://data/examples/input2.txt
      example_output_2: file://data/examples/output2.txt
      # Actual test
      actual_input: file://data/test1.txt
```

**Best practices:**
- Use 1-3 few-shot examples (more may dilute effectiveness)
- Ensure examples match the task format exactly
- Load examples from files for better maintainability
- Use echo provider first to verify structure

## Long Text Handling

For Chinese/long-form content evaluations (10k+ characters):

**Configuration:**

```yaml
providers:
  - id: anthropic:messages:claude-sonnet-4-5-20250929
    config:
      max_tokens: 8192  # Increase for long outputs

defaultTest:
  assert:
    - type: python
      value: file://scripts/metrics.py:check_length
```

**Python assertion for text metrics:**

```python
import re

def strip_tags(text: str) -> str:
    """Remove HTML tags for pure text."""
    return re.sub(r'<[^>]+>', '', text)

def check_length(output: str, context: dict) -> dict:
    """Check output length constraints."""
    raw_input = context['vars'].get('raw_input', '')

    input_len = len(strip_tags(raw_input))
    output_len = len(strip_tags(output))

    reduction_ratio = 1 - (output_len / input_len) if input_len > 0 else 0

    return {
        "pass": 0.7 <= reduction_ratio <= 0.9,
        "score": reduction_ratio,
        "reason": f"Reduction: {reduction_ratio:.1%} (target: 70-90%)",
        "named_scores": {
            "input_length": input_len,
            "output_length": output_len,
            "reduction_ratio": reduction_ratio
        }
    }
```

## Real-World Example

**Project:** Chinese short-video content curation from long transcripts

**Structure:**
```
tiaogaoren/
├── promptfooconfig.yaml          # Production config
├── promptfooconfig-preview.yaml  # Preview config (echo provider)
├── prompts/
│   ├── tiaogaoren-prompt.json   # Chat format with few-shot
│   └── v4/system-v4.md          # System prompt
├── tests/cases.yaml              # 3 test samples
├── scripts/metrics.py            # Custom metrics (reduction ratio, etc.)
├── data/                         # 5 samples (2 few-shot, 3 eval)
└── results/
```

**See:** `/Users/tiansheng/Workspace/prompts/tiaogaoren/` for full implementation.

## Resources

For detailed API reference and advanced patterns, see [references/promptfoo_api.md](references/promptfoo_api.md).
