#!/usr/bin/env python3
"""Probe a Claude endpoint for working server-side web tools.

Anthropic runs `web_search` and `web_fetch` on its own servers and splices the
results into the same response. A reseller that proxies the request to another
cloud cannot do that. The request still succeeds, so nothing errors — the model
simply gets no results and answers as if the topic did not exist.

This script asks the endpoint to use each tool and reads the shape of the reply,
which is where the truth is:

    server_tool_use + <tool>_tool_result   the tool really ran
    plain tool_use                         handed back for a client to run; no search happened
    HTTP 400 on the tool definition        the endpoint cannot even express the tool

The `id` on a tool block names the backend: `toolu_vrtx_` is Google Vertex AI,
`toolu_bdrk_` is AWS Bedrock. Two separate things are known about those backends,
and they have different weight. Anthropic's documentation states that **web fetch**
is not available on Amazon Bedrock or Google Cloud. That **web search** fails the
same way there is not a documented claim — it was measured, by this probe, against
a relay landing on both. Do not repeat the second one as though a vendor said it.

Standard library only: this runs before anything has been installed.

OpenAI's Responses API has the same property and the same failure: `web_search`
there is a hosted tool the API runs itself, returning a `web_search_call` item in
`output`. Codex reaches its backend this way, so `--api openai` is how a Codex user
gets a verdict at all.

Relays fail that probe in two different ways and only one of them is a refusal. A
relay that cannot express the tool rejects the request at validation. Far more
often it simply has no `/v1/responses` route, because many implement only the older
Chat Completions API — measured on one such relay, 200 on `/v1/chat/completions`
and 404 on `/v1/responses`. That pair is a verdict rather than a gap: the endpoint
speaks OpenAI and lacks the surface hosted tools live on, so this probe makes the
second request itself before deciding.

Usage:
    python3 diagnose.py                       # reads ANTHROPIC_BASE_URL / _AUTH_TOKEN / _MODEL
    python3 diagnose.py --url ... --key ... --model ...
    python3 diagnose.py --api openai          # probe an OpenAI-compatible endpoint instead
    python3 diagnose.py --api both            # probe whichever the relay answers
    python3 diagnose.py --json                # machine-readable

Exit codes:
    0  every probed tool works, or the endpoint is Anthropic direct — nothing to fix
    1  at least one tool is unavailable — the caller should act
    2  could not determine (missing credentials, unreachable, model refused to call)
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# Generous on purpose. The same gateway was measured answering in ~15s on two
# model ids and ~146s on a third, and a timeout shorter than the slow one reports
# a working endpoint as dead — the exact misdiagnosis this tool exists to prevent.
DEFAULT_TIMEOUT = 180

BACKEND_BY_PREFIX = {
    "toolu_vrtx_": "Google Vertex AI",
    "toolu_bdrk_": "AWS Bedrock",
    "srvtoolu_": "Anthropic (server tool)",
    "ws_": "OpenAI (hosted tool)",
}

# What the client calls the tool is not what the API calls it. A deny rule or a
# --disallowedTools list takes `WebSearch`; the API takes `web_search`. Writing the
# API spelling into a deny list matches nothing, so the config changes, the report
# says "removed", and the tool is still on the model's menu.
CLIENT_TOOL_NAME = {"web_search": "WebSearch", "web_fetch": "WebFetch"}

# A probe per tool. The web_fetch prompt names a URL inline on purpose: that tool
# only accepts URLs that already appeared in the conversation, so a probe without
# one is refused for a reason that has nothing to do with the endpoint.
PROBES = {
    "web_search": {
        "type": "web_search_20250305",
        "prompt": ("Use the web_search tool right now to find one news item from this week. "
                   "Reply with its headline and source URL. Do not answer from memory."),
    },
    "web_fetch": {
        "type": "web_fetch_20250910",
        "prompt": ("Use the web_fetch tool right now to fetch https://example.com and tell me "
                   "the first heading on that page. Do not answer from memory."),
    },
}

def implicates_tool(message, tool_name):
    """Decide whether an HTTP 400 is actually about the tool.

    A relay answers 400 for plenty of reasons that have nothing to do with web
    search: a model id it does not recognise, a malformed body, a policy rule.
    Reading those as "the tool is dead" would have the caller remove a tool that
    works — the exact misdiagnosis this script exists to prevent. So the verdict
    only hardens when the endpoint's own message mentions the tool, the word tool,
    or a schema complaint; anything else stays inconclusive with the text kept so
    a reader can see what really happened.
    """
    lowered = (message or "").lower()
    return tool_name.lower() in lowered or "tool" in lowered or "schema" in lowered


VERDICT_WORKS = "works"
VERDICT_BROKEN = "unavailable"
VERDICT_UNKNOWN = "inconclusive"


def post(url, payload, headers, timeout):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("content-type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"_raw": raw[:600]}
    except TimeoutError:
        return None, {"_timeout": timeout}
    except Exception as exc:  # noqa: BLE001 - any transport failure is one outcome here
        # A socket timeout can surface as URLError wrapping one, not only as TimeoutError.
        if "timed out" in str(exc).lower():
            return None, {"_timeout": timeout}
        return None, {"_transport_error": str(exc)}


def probe(base_url, key, model, name, timeout):
    spec = PROBES[name]
    status, data = post(
        f"{base_url}/v1/messages",
        {
            "model": model,
            # Some gateways reject a small max_tokens outright, which looks like
            # a different bug entirely. 1024 is above every limit seen so far.
            "max_tokens": 1024,
            "tools": [{"type": spec["type"], "name": name}],
            "messages": [{"role": "user", "content": spec["prompt"]}],
        },
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
        timeout,
    )

    result = {"tool": name, "client_tool": CLIENT_TOOL_NAME.get(name, name),
              "http": status, "backend": None, "blocks": []}

    if status is None:
        result["verdict"] = VERDICT_UNKNOWN
        if "_timeout" in data:
            result["detail"] = (
                f"no answer within {data['_timeout']}s. That is slowness, not a verdict — "
                "some gateways answer an order of magnitude slower on some model ids. "
                "Re-run with a longer --timeout before concluding anything."
            )
        else:
            result["detail"] = f"could not reach the endpoint: {data.get('_transport_error')}"
        return result

    if status == 400:
        message = ""
        if isinstance(data.get("error"), dict):
            message = str(data["error"].get("message", ""))
        if implicates_tool(message, name):
            result["verdict"] = VERDICT_BROKEN
            result["detail"] = (
                "the endpoint rejected the tool definition outright (HTTP 400). A translation "
                "layer that cannot express a server-side tool fails here. " + message[:300]
            ).strip()
        else:
            result["verdict"] = VERDICT_UNKNOWN
            result["detail"] = (
                "HTTP 400, but the endpoint's message does not mention the tool, so this "
                "probe says nothing about it. An unrecognised model id fails exactly this "
                "way. Read the message and re-run, most likely with --model set to an id "
                "this endpoint publishes: " + message[:300]
            ).strip()
        return result

    if status != 200:
        result["verdict"] = VERDICT_UNKNOWN
        result["detail"] = f"unexpected HTTP {status}: {json.dumps(data, ensure_ascii=False)[:300]}"
        return result

    blocks = data.get("content") or []
    result["blocks"] = [b.get("type") for b in blocks]

    for block in blocks:
        ident = str(block.get("id") or "")
        for prefix, label in BACKEND_BY_PREFIX.items():
            if ident.startswith(prefix):
                result["backend"] = f"{label} (tool id prefix {prefix})"

    if "server_tool_use" in result["blocks"] or f"{name}_tool_result" in result["blocks"]:
        result["verdict"] = VERDICT_WORKS
        result["detail"] = "the endpoint executed the tool and returned results inline."
        return result

    if "tool_use" in result["blocks"]:
        result["verdict"] = VERDICT_BROKEN
        result["detail"] = (
            "the endpoint returned a plain tool_use block, meaning it handed the request back "
            "for a client to run. The tool never executed and no results exist, yet nothing "
            "errored — which is why this reads as 'there is nothing about that topic'."
        )
        return result

    # The model answered without reaching for the tool. That is not proof of
    # anything about the endpoint, so do not claim it is.
    result["verdict"] = VERDICT_UNKNOWN
    result["detail"] = (
        "the model replied without attempting the tool, so this probe proves nothing either "
        "way. Re-run, or try a different model on the same endpoint."
    )
    return result


# The Responses API takes one hosted tool declaration and answers with a
# `web_search_call` item when it really ran. Shapes confirmed against OpenAI's
# current tool documentation; the HTTP 400 branch was observed on a live relay.
OPENAI_PROBE = {
    "type": "web_search",
    "prompt": ("Use the web_search tool right now to find one news item from this week. "
               "Reply with its headline and source URL. Do not answer from memory."),
}


def probe_openai(base_url, key, model, timeout):
    """Probe an OpenAI-compatible endpoint for the hosted web_search tool."""
    status, data = post(
        f"{base_url}/v1/responses",
        {
            "model": model,
            "tools": [{"type": OPENAI_PROBE["type"]}],
            "input": OPENAI_PROBE["prompt"],
        },
        {"authorization": f"Bearer {key}"},
        timeout,
    )

    result = {"tool": "web_search", "client_tool": CLIENT_TOOL_NAME["web_search"],
              "api": "openai", "http": status, "backend": None, "blocks": []}

    if status is None:
        result["verdict"] = VERDICT_UNKNOWN
        if "_timeout" in data:
            result["detail"] = (
                f"no answer within {data['_timeout']}s. That is slowness, not a verdict — "
                "re-run with a longer --timeout before concluding anything."
            )
        else:
            result["detail"] = f"could not reach the endpoint: {data.get('_transport_error')}"
        return result

    if status == 400:
        message = ""
        if isinstance(data.get("error"), dict):
            message = str(data["error"].get("message", ""))
        if implicates_tool(message, "web_search"):
            result["verdict"] = VERDICT_BROKEN
            result["detail"] = (
                "the endpoint rejected the hosted tool at validation (HTTP 400). A translation "
                "layer that cannot express a hosted tool fails here, before the model reads "
                "anything. " + message[:300]
            ).strip()
        else:
            result["verdict"] = VERDICT_UNKNOWN
            result["detail"] = (
                "HTTP 400, but the endpoint's message does not mention the tool, so this "
                "probe says nothing about it. An unrecognised model id fails exactly this "
                "way — pass --openai-model with an id this endpoint publishes: "
                + message[:300]
            ).strip()
        return result

    if status == 404:
        # A missing /v1/responses route is the commonest relay shape, and on its own it
        # is ambiguous: the endpoint might speak no OpenAI dialect at all, or the key
        # might be wrong. One more request settles it. If the older Chat Completions
        # route answers, the endpoint really is OpenAI-compatible and simply lacks the
        # surface hosted tools are served through — which is a verdict, not a shrug.
        chat_status, _chat = post(
            f"{base_url}/v1/chat/completions",
            {"model": model, "messages": [{"role": "user", "content": "hi"}],
             "max_tokens": 8},
            {"authorization": f"Bearer {key}"},
            timeout,
        )
        result["http"] = 404
        result["chat_completions_http"] = chat_status
        if chat_status == 200:
            result["verdict"] = VERDICT_BROKEN
            result["detail"] = (
                "this endpoint answers the older Chat Completions route (HTTP 200) but has "
                "no /v1/responses route (HTTP 404). Hosted web search is served through the "
                "Responses API, so it cannot run here at all. For Codex that is decisive: "
                "the route its hosted tools use does not exist on this endpoint."
            )
        else:
            result["verdict"] = VERDICT_UNKNOWN
            result["detail"] = (
                "no /v1/responses route (HTTP 404), and the older Chat Completions route did "
                f"not answer either (HTTP {chat_status}). So this says nothing about the tool "
                "— the endpoint may speak no OpenAI dialect, or the key may be wrong. Check "
                "the key and the base URL before drawing any conclusion."
            )
        return result

    if status != 200:
        result["verdict"] = VERDICT_UNKNOWN
        result["detail"] = f"unexpected HTTP {status}: {json.dumps(data, ensure_ascii=False)[:300]}"
        return result

    items = data.get("output") or []
    result["blocks"] = [i.get("type") for i in items]

    for item in items:
        ident = str(item.get("id") or "")
        for prefix, label in BACKEND_BY_PREFIX.items():
            if ident.startswith(prefix):
                result["backend"] = f"{label} (tool id prefix {prefix})"

    if "web_search_call" in result["blocks"]:
        result["verdict"] = VERDICT_WORKS
        result["detail"] = "the endpoint executed the hosted tool and returned results inline."
        return result

    # A compatibility layer that silently drops built-in tools lands here, and so
    # does a model that simply chose not to search. Those are not distinguishable
    # from one reply, so do not call either of them broken.
    result["verdict"] = VERDICT_UNKNOWN
    result["detail"] = (
        "the reply carries no web_search_call, so the tool did not run. This is either a "
        "compatibility layer that drops built-in tools silently or a model that chose not "
        "to search — one reply cannot tell them apart. Re-run, or try another model."
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", help="endpoint base URL (default: $ANTHROPIC_BASE_URL)")
    parser.add_argument("--key", help="API key (default: $ANTHROPIC_AUTH_TOKEN or $ANTHROPIC_API_KEY)")
    parser.add_argument("--model", help="model id to probe with (default: $ANTHROPIC_MODEL)")
    parser.add_argument("--tool", choices=sorted(PROBES), action="append",
                        help="probe only this Anthropic tool (repeatable; default: all)")
    parser.add_argument("--openai-model", help="model id for the OpenAI probe "
                        "(default: $OPENAI_MODEL). Required with --api both, because the "
                        "two APIs do not share a model namespace.")
    parser.add_argument("--api", choices=("anthropic", "openai", "both"), default="anthropic",
                        help="which API shape to probe (default: anthropic). Codex reaches its "
                             "backend through the OpenAI Responses API, so use openai for it.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help=f"seconds to wait per probe (default {DEFAULT_TIMEOUT})")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    want_anthropic = args.api in ("anthropic", "both")
    want_openai = args.api in ("openai", "both")

    if want_openai and not want_anthropic:
        base_url = (args.url or os.environ.get("OPENAI_BASE_URL")
                    or os.environ.get("ANTHROPIC_BASE_URL") or "").rstrip("/")
        key = (args.key or os.environ.get("OPENAI_API_KEY")
               or os.environ.get("ANTHROPIC_AUTH_TOKEN") or "")
        model = (args.openai_model or args.model
                 or os.environ.get("OPENAI_MODEL") or "gpt-5")
        vendor_host = "api.openai.com"
        vendor_name = "OpenAI"
    else:
        base_url = (args.url or os.environ.get("ANTHROPIC_BASE_URL") or "").rstrip("/")
        key = (args.key or os.environ.get("ANTHROPIC_AUTH_TOKEN")
               or os.environ.get("ANTHROPIC_API_KEY") or "")
        model = args.model or os.environ.get("ANTHROPIC_MODEL") or "claude-haiku-4-5"
        vendor_host = "api.anthropic.com"
        vendor_name = "Anthropic"
    # A context marker such as "[1m]" is a client-side hint the API will reject.
    model = re.sub(r"\[[^\]]*\]\s*$", "", model).strip()
    tools = args.tool or sorted(PROBES)

    # The two APIs do not share a model namespace, so --api both needs its own id.
    # Guessing one produces a 400 about the model that reads like a verdict about
    # the tool, which is the failure this whole script is built to avoid.
    openai_model = None
    if want_openai:
        openai_model = (args.openai_model or os.environ.get("OPENAI_MODEL")
                        or (model if not want_anthropic else None))
        if openai_model:
            openai_model = re.sub(r"\[[^\]]*\]\s*$", "", openai_model).strip()

    if not base_url or vendor_host in base_url:
        report = {
            "endpoint": base_url or f"(unset — {vendor_name} direct)",
            "conclusion": "not_affected",
            "results": [],
            "detail": (f"This session talks to {vendor_name} directly, where the hosted web tools "
                       "are available. If search still returns nothing, the cause is elsewhere."),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else report["detail"])
        return 0

    if not key:
        env_hint = ("OPENAI_API_KEY" if (want_openai and not want_anthropic)
                    else "ANTHROPIC_AUTH_TOKEN")
        message = (f"Endpoint {base_url} is configured but no key is visible.\n"
                   f"Pass one with --key, or export {env_hint}.\n"
                   "On a relay the value usually lives in the client's own settings rather "
                   "than the shell: the `env` block of ~/.claude/settings.json for Claude "
                   "Code, or ~/.codex/config.toml plus ~/.codex/auth.json for Codex.")
        print(json.dumps({"conclusion": "unknown", "detail": message}, ensure_ascii=False, indent=2)
              if args.json else message, file=sys.stderr)
        return 2

    results = []
    if want_anthropic:
        results.extend(probe(base_url, key, model, name, args.timeout) for name in tools)
    if want_openai:
        if openai_model:
            results.append(probe_openai(base_url, key, openai_model, args.timeout))
        else:
            results.append({
                "tool": "web_search", "client_tool": CLIENT_TOOL_NAME["web_search"],
                "api": "openai", "http": None, "backend": None,
                "blocks": [], "verdict": VERDICT_UNKNOWN,
                "detail": ("skipped: no OpenAI model id. The two APIs do not share a model "
                           "namespace, and sending the Anthropic id here produces a 400 about "
                           "the model that reads like a verdict about the tool. Pass "
                           "--openai-model, or export OPENAI_MODEL."),
            })
    broken = [r for r in results if r["verdict"] == VERDICT_BROKEN]
    unknown = [r for r in results if r["verdict"] == VERDICT_UNKNOWN]
    backend = next((r["backend"] for r in results if r["backend"]), None)

    conclusion = "affected" if broken else ("unknown" if unknown else "not_affected")
    report = {"endpoint": base_url, "model": model, "backend": backend,
              "conclusion": conclusion, "results": results}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"endpoint : {base_url}")
        print(f"model    : {model}")
        if backend:
            print(f"backend  : {backend}")
        print()
        for item in results:
            label = item["tool"]
            if args.api == "both":
                label = f"{item.get('api', 'anthropic')}/{label}"
            print(f"{label:<24} {item['verdict'].upper()}")
            print(f"             blocks: {', '.join(item['blocks']) or '(none)'}")
            print(f"             {item['detail']}")
            print()
        if broken:
            names = ", ".join(r["tool"] for r in broken)
            client_names = ", ".join(sorted({r["client_tool"] for r in broken}))
            print(f"CONCLUSION: {names} unavailable on this endpoint.")
            print("Switching models on the same endpoint does not change this — the capability")
            print("belongs to the backend, not the model. Remove the dead tool from the client")
            print("and give it a replacement it can actually call.")
            print()
            print(f"In the client, that tool is spelled: {client_names}")
            print("That is the spelling permissions.deny and --disallowedTools accept. The")
            print(f"API spelling above ({names}) matches nothing in a deny list, so writing it")
            print("there changes the file and leaves the tool on the model's menu.")
        elif unknown:
            print("CONCLUSION: undetermined. Re-run, or probe with a different model.")
        else:
            print("CONCLUSION: the server-side web tools work here. Nothing to fix.")

    return 1 if broken else (2 if unknown else 0)


if __name__ == "__main__":
    sys.exit(main())
