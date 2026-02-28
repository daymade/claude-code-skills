---
name: embed
description: Generate text embeddings for semantic search and similarity
argument-hint: <text>
---

# Text Embeddings via deAPI

Generate embeddings for: **$ARGUMENTS**

## Step 1: Validate input

Verify `$ARGUMENTS` contains text to embed:
- Text should not be empty
- Maximum recommended length: 8192 tokens
- For longer texts, consider chunking

## Step 2: Send request

```bash
curl -s -X POST "https://api.deapi.ai/api/v1/client/txt2embedding" \
  -H "Authorization: Bearer $DEAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "$ARGUMENTS",
    "model": "Bge_M3_FP16"
  }'
```

**Model info:**
| Model | Dimensions | Best for |
|-------|------------|----------|
| `Bge_M3_FP16` | 1024 | High accuracy, semantic search, multilingual |

## Step 3: Poll status (feedback loop)

Extract `request_id` from response, then poll every 10 seconds:

```bash
curl -s "https://api.deapi.ai/api/v1/client/request-status/{request_id}" \
  -H "Authorization: Bearer $DEAPI_API_KEY"
```

**Status handling:**
- `processing` → wait 10s, poll again
- `done` → proceed to Step 4
- `failed` → report error message to user, STOP

## Step 4: Fetch and present result

When `status = "done"`:
1. Get embedding vector from response
2. Show vector dimensions and sample values
3. Offer to save or use the embedding

**Output format:**
```json
{
  "embedding": [0.123, -0.456, 0.789, ...],
  "dimensions": 1024,
  "model": "Bge_M3_FP16"
}
```

## Step 5: Offer follow-up

Ask user:
- "Would you like to embed more text for comparison?"
- "Should I calculate similarity between embeddings?"
- "Would you like to save these embeddings to a file?"

## Use cases

- **Semantic search**: Find similar documents
- **Clustering**: Group related content
- **RAG**: Retrieval-augmented generation
- **Recommendations**: Content similarity

## Error handling

| Error | Action |
|-------|--------|
| 401 Unauthorized | Check if `$DEAPI_API_KEY` is set correctly |
| 429 Rate Limited | Wait 60s and retry |
| 500 Server Error | Wait 30s and retry once |
| Empty text | Ask user to provide text to embed |
| Text too long | Suggest chunking into smaller segments |
