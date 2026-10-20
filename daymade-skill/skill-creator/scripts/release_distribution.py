"""Immutable distribution identity for opt-in review reuse.

Dependency completeness is a declaration in the original independent review,
not something inferred from imports or Markdown links. Inclusion stays with
packaging_policy; Git modes and blob identities bind the selected content.
"""
import json
from pathlib import Path
import posixpath

try:
    from .packaging_policy import inclusion_policy_metadata, should_exclude_skill_relative
except ImportError:
    from packaging_policy import inclusion_policy_metadata, should_exclude_skill_relative


POLICY_PATH = "daymade-skill/skill-creator/scripts/packaging_policy.py"


def dependencies(value, relative):
    if not isinstance(value, list) or not value:
        raise ValueError("rebind_dependencies must be a nonempty reviewed list")
    result = [relative(item) for item in value]
    if len(set(result)) != len(result):
        raise ValueError("duplicate rebind dependency")
    return sorted(result)


def distribution(repo, candidate, paths, dependency_paths, git, relative):
    """Bind whole owning plugin(s), policy implementation and declared dependencies."""
    policy = inclusion_policy_metadata()
    entries = {}
    for row in git(repo, "ls-tree", "-r", "-z", candidate).split("\0"):
        if not row:
            continue
        header, name = row.split("\t", 1)
        mode, kind, oid = header.split()
        entries[name] = [mode, kind, oid]
    manifest = json.loads(git(repo, "show", candidate + ":.claude-plugin/marketplace.json"))
    plugins = manifest.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        raise ValueError("marketplace plugins missing")
    owners = []
    plugin_sources = []
    covered = set()
    for plugin in plugins:
        if not isinstance(plugin, dict):
            raise ValueError("invalid plugin declaration")
        declaration = plugin.get("source")
        if not isinstance(declaration, str):
            raise ValueError("rebind requires a local plugin source")
        source = relative(declaration.removeprefix("./").rstrip("/"))
        plugin_sources.append(source)
        children = plugin.get("skills")
        if children is not None and (not isinstance(children, list) or not children
                                     or not all(isinstance(child, str) for child in children)):
            raise ValueError("invalid plugin skills")
        roots = [source + "/" + relative(child.removeprefix("./").rstrip("/"))
                 for child in children] if children else [source]
        owned = set(paths).intersection(roots)
        if not owned:
            continue
        if covered.intersection(owned):
            raise ValueError("ambiguous plugin ownership")
        covered.update(owned)
        if any(root + "/SKILL.md" not in entries for root in roots):
            raise ValueError("registered plugin has a missing Skill")
        owners.append((plugin, source, roots))
    if covered != set(paths):
        raise ValueError("every reviewed Skill must have an exact registered plugin owner")
    selected = {}
    # Repository-level helpers/configuration are dependencies even when a review
    # forgets to repeat them. Only the changelog and whole catalog are projected:
    # the selected plugin objects below bind their relevant catalog identity.
    for name, entry in entries.items():
        if name not in (".claude-plugin/marketplace.json", "CHANGELOG.md") and not any(
                name.startswith(source + "/") for source in plugin_sources):
            selected[name] = entry
    for plugin, source, roots in owners:
        for name, entry in entries.items():
            if not name.startswith(source + "/"):
                continue
            root = next((root for root in roots if name.startswith(root + "/")), None)
            if root and should_exclude_skill_relative(Path(name[len(root) + 1:]), policy=policy):
                continue
            selected[name] = entry
    # Dependencies deliberately include their entire tracked trees, without a
    # second exclusion policy. Unknown dynamic/external dependencies need review.
    for dependency in [POLICY_PATH, *dependency_paths]:
        matches = {name: entry for name, entry in entries.items()
                   if name == dependency or name.startswith(dependency + "/")}
        if not matches:
            raise ValueError("missing rebind dependency: " + dependency)
        selected.update(matches)
    def resolve_link(name, chain):
        if name in chain:
            raise ValueError("cyclic rebind symlink")
        mode, kind, oid = entries[name]
        if mode != "120000":
            return
        target = git(repo, "cat-file", "blob", oid)
        if len(target.encode()) != int(git(repo, "cat-file", "-s", oid)) or target.startswith("/"):
            raise ValueError("unsupported external or whitespace-bearing rebind symlink")
        target = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
        if target in (".", "..") or target.startswith("../"):
            raise ValueError("rebind symlink escapes repository")
        matches = {path: entry for path, entry in entries.items()
                   if path == target or path.startswith(target + "/")}
        if not matches:
            raise ValueError("rebind symlink target is missing")
        selected.update(matches)
        for path in matches:
            resolve_link(path, chain | {name})

    for name in list(selected):
        resolve_link(name, set())
    if any(entry[0] not in ("100644", "100755", "120000") or entry[1] != "blob"
           for entry in selected.values()):
        raise ValueError("rebind cannot establish submodule dependency identity")
    return dict(policy=policy, plugins=sorted((plugin for plugin, _, _ in owners),
                                            key=lambda plugin: json.dumps(plugin, sort_keys=True)),
                dependencies=dependency_paths, entries=selected, examined_files=len(selected))
