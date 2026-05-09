# Example Session

## Input transcript (`meeting.md`)
```
今天我们讨论了巨升智能的最新进展。
股价系统需要优化，目前性能不够好。
```

## After Stage 1 (`meeting_stage1.md`)
```
今天我们讨论了具身智能的最新进展。  ← "巨升"→"具身" corrected
股价系统需要优化，目前性能不够好。  ← Unchanged (not in dictionary)
```

## After Stage 2 (`meeting_stage2.md`)
```
今天我们讨论了具身智能的最新进展。
框架系统需要优化，目前性能不够好。  ← "股价"→"框架" corrected by AI
```

## Learned pattern detected
```
✓ Detected: "股价" → "框架" (confidence: 85%, count: 1)
  Run --review-learned after 2 more occurrences to approve
```
