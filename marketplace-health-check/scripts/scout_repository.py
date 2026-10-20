#!/usr/bin/env python3
"""Read marketplace metadata and complete open PR/issue inventories.

Emit one JSON object. Exit 0 only when metadata and both inventories are checked;
exit 1 retains successful observations and marks each failed part not_checked.
Use authenticated gh access already selected by the operator; never mutate it.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


class ScoutError(Exception):
    """Represent incomplete or untrustworthy audit input."""


def object_value(value, label):
    if not isinstance(value, dict):
        raise ScoutError(f"{label} must be an object")
    return value


def integer(value, label):
    if type(value) is not int or value < 0:
        raise ScoutError(f"{label} must be a nonnegative integer")
    return value


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ScoutError(f"{label} must be a nonempty string")
    return value


def gh_json(arguments):
    try:
        result = subprocess.run(["gh", *arguments], capture_output=True, text=True,
                                timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ScoutError(f"gh unavailable: {type(error).__name__}") from error
    if result.returncode:
        # Do not copy arbitrary server/body/credential text into a reusable report.
        raise ScoutError(f"gh command failed with exit {result.returncode}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ScoutError("gh returned invalid JSON") from error


def graphql(owner, name, query, cursor=None):
    command = ["api", "graphql", "-f", f"query={query}", "-f", f"owner={owner}",
               "-f", f"name={name}"]
    if cursor is not None:
        command.extend(["-f", f"endCursor={cursor}"])
    response = object_value(gh_json(command), "GraphQL response")
    if response.get("errors"):
        raise ScoutError("GraphQL reported errors")
    data = object_value(response.get("data"), "GraphQL data")
    return object_value(data.get("repository"), "GraphQL repository")


def validate_node(node, kind):
    node = object_value(node, "inventory node")
    expected_type = "PullRequest" if kind == "pullRequests" else "Issue"
    if node.get("__typename") != expected_type:
        raise ScoutError(f"inventory contains a non-{expected_type} object")
    nonempty(node.get("id"), "node id")
    if integer(node.get("number"), "node number") == 0:
        raise ScoutError("node number must be positive")
    nonempty(node.get("title"), "node title")
    nonempty(node.get("createdAt"), "node createdAt")
    author = node.get("author")
    if "author" not in node or (author is not None and
                                not isinstance(author, dict)):
        raise ScoutError("node author must be an object or null")
    if author is not None:
        nonempty(author.get("login"), "author login")
    if kind == "pullRequests":
        for field in ("additions", "deletions", "changedFiles"):
            integer(node.get(field), field)
        for field in ("headRefName", "mergeable", "mergeStateStatus"):
            nonempty(node.get(field), field)
    else:
        labels = object_value(node.get("labels"), "issue labels")
        page = object_value(labels.get("pageInfo"), "label pageInfo")
        if page.get("hasNextPage") is not False:
            raise ScoutError("issue labels require another page")
        if not isinstance(labels.get("nodes"), list):
            raise ScoutError("issue label nodes must be an array")
        for label in labels["nodes"]:
            nonempty(object_value(label, "label").get("name"), "label name")
        if integer(labels.get("totalCount"), "label totalCount") != len(labels["nodes"]):
            raise ScoutError("issue labels do not match their total")
    return node


def inventory(owner, name, kind):
    """Follow github-ops' GraphQL cursor recipe and reconcile totalCount."""
    fields = "__typename id number title author { login } createdAt"
    if kind == "pullRequests":
        fields += " headRefName additions deletions changedFiles mergeable mergeStateStatus"
    else:
        fields += " labels(first:100) { totalCount pageInfo { hasNextPage } nodes { name } }"
    query = ("query($owner:String!,$name:String!,$endCursor:String) { "
             "repository(owner:$owner,name:$name) { " + kind +
             "(first:100,states:OPEN,after:$endCursor) { totalCount "
             "pageInfo { hasNextPage endCursor } nodes { " + fields + " } } } }")
    items, ids, numbers, cursors = [], set(), set(), set()
    expected_total, cursor = None, None
    try:
        while True:
            repository = graphql(owner, name, query, cursor)
            connection = object_value(repository.get(kind), kind)
            total = integer(connection.get("totalCount"), "totalCount")
            if expected_total is None:
                expected_total = total
            if total != expected_total:
                raise ScoutError("server total changed during pagination")
            nodes = connection.get("nodes")
            if not isinstance(nodes, list) or len(nodes) > 100:
                raise ScoutError("inventory nodes must be an array of at most 100")
            page = object_value(connection.get("pageInfo"), "pageInfo")
            if type(page.get("hasNextPage")) is not bool or "endCursor" not in page:
                raise ScoutError("pageInfo is incomplete")
            for value in nodes:
                node = validate_node(value, kind)
                if node["id"] in ids or node["number"] in numbers:
                    raise ScoutError("duplicate inventory id or number")
                ids.add(node["id"])
                numbers.add(node["number"])
                items.append(node)
            if len(items) > expected_total:
                raise ScoutError("inventory exceeds server total")
            if not page["hasNextPage"]:
                break
            next_cursor = nonempty(page["endCursor"], "next cursor")
            if not nodes or next_cursor in cursors:
                raise ScoutError("pagination cursor did not advance")
            cursors.add(next_cursor)
            cursor = next_cursor
        if len(items) != expected_total:
            raise ScoutError("inventory count does not match server total")
        # Recheck the connection after enumeration; a moving queue is not a snapshot.
        total_query = ("query($owner:String!,$name:String!) { "
                       "repository(owner:$owner,name:$name) { " + kind +
                       "(first:1,states:OPEN) { totalCount } } }")
        final = object_value(graphql(owner, name, total_query).get(kind), kind)
        if integer(final.get("totalCount"), "final totalCount") != expected_total:
            raise ScoutError("server total changed after pagination")
        return {"status": "checked", "total": expected_total, "items": items}
    except ScoutError as error:
        return {"status": "not_checked", "total": expected_total,
                "items": items, "error": str(error)}


def scout(root, repo):
    result = {"repo": repo}
    try:
        manifest = object_value(json.loads((root / ".claude-plugin/marketplace.json").read_text()),
                                "marketplace manifest")
        version = nonempty(object_value(manifest.get("metadata"), "metadata").get("version"),
                           "metadata.version")
        plugins = manifest.get("plugins")
        if not isinstance(plugins, list):
            raise ScoutError("manifest plugins must be an array")
        expanded = 0
        for plugin in plugins:
            plugin = object_value(plugin, "plugin")
            members = plugin.get("skills", [])
            if not isinstance(members, list):
                raise ScoutError("plugin skills must be an array")
            expanded += len(members) if members else 1
        result["marketplace"] = {"status": "checked", "version": version,
                                 "plugin_count": len(plugins), "skill_count": expanded}
    except (OSError, ValueError, ScoutError) as error:
        result["marketplace"] = {"status": "not_checked", "error": str(error)}
    try:
        identity = object_value(gh_json(["repo", "view", repo, "--json",
                                        "nameWithOwner,isPrivate,stargazerCount"]), "repo identity")
        if nonempty(identity.get("nameWithOwner"), "nameWithOwner").lower() != repo.lower():
            raise ScoutError("gh resolved a different repository")
        if type(identity.get("isPrivate")) is not bool:
            raise ScoutError("repository visibility is unknown")
        integer(identity.get("stargazerCount"), "stargazerCount")
        result["identity"] = {"status": "checked", **identity}
    except ScoutError as error:
        result["identity"] = {"status": "not_checked", "error": str(error)}
    owner, name = repo.split("/")
    result["open_prs"] = inventory(owner, name, "pullRequests")
    result["open_issues"] = inventory(owner, name, "issues")
    result["complete"] = all(result[key]["status"] == "checked" for key in
                             ("marketplace", "identity", "open_prs", "open_issues"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Exact owner/name to inspect")
    parser.add_argument("--root", type=Path, default=Path.cwd(),
                        help="Repository root containing .claude-plugin/marketplace.json")
    arguments = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", arguments.repo):
        parser.error("--repo must be owner/name")
    result = scout(arguments.root, arguments.repo)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
