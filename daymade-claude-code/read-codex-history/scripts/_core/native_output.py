"""Search native Codex command results without counting their output aliases.

Native item_completed records are not always mirrored by response_item output.
Deduplicate only matching result identities and text, never equal text from
different commands. User/assistant event mirrors remain owned by the readers.
"""

from .text import SearchSegment


def native_command_segments(record):
    if record.get("type") != "event_msg":
        return []
    payload = record.get("payload", {})
    if not isinstance(payload, dict) or payload.get("type") != "item_completed":
        return []
    item = payload.get("item", {})
    if not isinstance(item, dict) or item.get("type") != "CommandExecution":
        return []
    # stdout/stderr preserve separate streams. The aggregate and formatted
    # views normally repeat them, so consult these only when streams are absent.
    values = [item.get("stdout"), item.get("stderr")]
    if not any(isinstance(v, str) and v for v in values):
        values = [item.get("aggregated_output") or item.get("formatted_output")]
    return [SearchSegment(source="tool_result:CommandExecution", text=v)
            for v in values if isinstance(v, str) and v]


def result_identity(record):
    payload = record.get("payload", {})
    if not isinstance(payload, dict):
        return None
    if record.get("type") == "event_msg" and payload.get("type") == "item_completed":
        item = payload.get("item", {})
        if isinstance(item, dict) and item.get("type") == "CommandExecution":
            return item.get("id")
    if record.get("type") == "response_item" and payload.get("type") in {"function_call_output", "custom_tool_call_output"}:
        return payload.get("call_id")
    return None


def distinct_result_segments(record, segments, seen):
    identity = result_identity(record)
    if not isinstance(identity, str) or not identity:
        return segments
    result = []
    for segment in segments:
        key = (identity, segment.text)
        if key not in seen:
            seen.add(key)
            result.append(segment)
    return result
