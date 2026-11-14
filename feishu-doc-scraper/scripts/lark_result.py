"""Validate Wiki locators and decode lark-cli JSON without losing error streams."""
import json
import re
from urllib.parse import unquote, urlsplit


class CLIError(RuntimeError):
    def __init__(self, message, envelope=None):
        super().__init__(message)
        self.envelope = envelope


def wiki_token(value):
    """Accept a bare node token or an HTTPS Feishu/Lark Wiki URL."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Wiki locator is required")
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9]+", value):
        return value
    url = urlsplit(value)
    host = (url.hostname or "").lower()
    allowed = any(host == h or host.endswith("." + h)
                  for h in ("feishu.cn", "larksuite.com"))
    if url.scheme != "https" or not allowed or url.username or url.password:
        raise ValueError("Expected an HTTPS Feishu/Lark Wiki URL or node token")
    if url.port not in (None, 443):
        raise ValueError("Unexpected Wiki URL port")
    match = re.fullmatch(r"/wiki/([A-Za-z0-9]+)/?", unquote(url.path))
    if not match:
        raise ValueError("Expected /wiki/<node-token>; docx and base tokens are different")
    return match[1]


def _objects(stream):
    """Only decode object starts at a line boundary; never execute log content."""
    if not isinstance(stream, str):
        return
    end = 0
    for match in re.finditer(r"(?m)^[ \t]*\{", stream):
        if match.start() < end:
            continue
        try:
            item, end = json.JSONDecoder().raw_decode(stream, match.end() - 1)
        except (ValueError, TypeError):
            return
        if isinstance(item, dict):
            yield item


def parse_cli_result(stdout, stderr, returncode, *, receipt_keys=()):
    """Return one success object or raise with the actual structured failure.

    lark-cli can place JSON on stderr after a token-refresh notice. Plain export
    receipts are admitted only when the caller names their required keys.
    Empty, malformed, conflicting or exit-inconsistent responses stay unknown.
    """
    if type(returncode) is not int:
        raise CLIError("Missing lark-cli exit status")
    candidates = []
    for stream in (stdout, stderr):
        for item in _objects(stream):
            envelope = type(item.get("ok")) is bool
            receipt = bool(receipt_keys) and all(k in item for k in receipt_keys)
            if (envelope or receipt) and item not in candidates:
                candidates.append(item)
    if len(candidates) != 1:
        raise CLIError("No unique structured lark-cli response (exit %s)" % returncode)
    item = candidates[0]
    if item.get("ok") is False:
        error = item.get("error")
        if not isinstance(error, dict):
            raise CLIError("Malformed lark-cli error envelope")
        raise CLIError("lark-cli failed: %s / %s: %s" % (
            error.get("type", "unknown"), error.get("code", "unknown"),
            error.get("message", "unknown")), item)
    if returncode != 0:
        raise CLIError("lark-cli exit status contradicts its success response", item)
    if item.get("ok") is True and not isinstance(item.get("data"), dict):
        raise CLIError("lark-cli response has no data object", item)
    return item
