# Investigate one feature with reusable evidence

Use this recipe inside the existing reverse-analysis handoff when the question is
where a feature lives, how a function works, or what mechanism could transfer.
The executing agent applies it with the selected specialist's actual tools.
These are evidence-selection instructions, not an enforcement layer or a new
analysis engine. Return findings to app-evolver's mechanism decision and original
acceptance path; stop when the question is resolved or the next required
observation is unavailable.

## Locate the work from observable anchors

Bind the source commit or artifact digest, edition, architecture and module before
interpreting an address. Keep original symbols/addresses alongside analyst aliases;
an address or alias from one build does not identify the same function in another.

For an unfamiliar target, inspect its entry, relevant strings and imports to choose
a small useful reading frontier. For a named feature, begin directly with its
button/menu text, errors, output filenames, schema keys, notable imports or
constants. Use only clues actually present in the bound target.

Follow references into candidate functions, then trace callers to the trigger and
callees to the substantive operation and its consumer. Read the deciding branch,
inputs, outputs, side effects and relevant failure/recovery paths. Distinguish
display/wrapper code from execution. A string hit locates a candidate; it does
not prove that path runs. A source-only task can use repository search and call
sites without installing a disassembler.

For one function, infer parameter and return semantics from its callers and
consumers as well as its body. When pseudocode conflicts with control flow or
types, consult assembly or another available representation. Label reconstructed
code and uncertain types explicitly; readable pseudocode is not recovered
original source or demonstrated behavioral equivalence.

Stop expanding the graph when it reaches unrelated helpers or the remaining
answers cannot change the current decision. Select the next function by the
unresolved question, rather than renaming every function or reading the whole app.

## Keep an evidence note the next reader can use

Update the existing authorized analysis entry as understanding changes. For a
material finding retain:

- Artifact/ref, module, original symbol/address or source location, and analyst alias.
- User trigger and the short caller → deciding operation → consumer chain.
- Observed input/output, relevant failure/recovery behavior and source locators.
- Interpretation, competing explanation, coverage limit and smallest next probe.

Distinguish absent evidence from an evidenced absence. With incomplete strings,
dynamic dispatch or unavailable modules, keep candidate paths unresolved. Bind
notes to the build; re-establish the mapping before carrying them to another one.
Keep project-specific findings in that project's entry, not in this Skill.

Use annotations or renames only within the task's write authorization. In a
read-only investigation, record aliases in the findings without mutating the
analysis database. If the existing tool owns a project history, use that owner
for authorized mutations so changes remain attributable and reversible; do not
write through a second backend that bypasses it. Do not build a new history store
to satisfy this recipe. Analysis permission does not authorize byte patches or
execution of the target. When such work is separately authorized, preserve the
original, bind before/after evidence and verify the resulting behavior through
the existing engineering owner.

## Preserve the observation boundary

For networking, combine relevant imports with endpoint strings and their call
sites. Separate static destinations, request construction, dispatch conditions
and captured traffic. A reachable send call does not prove a request was sent;
a URL does not prove data left the machine. State the inspected module/path scope
and runtime observation needed before making an exhaustive traffic claim.

For performance, connect the suspected workload to its actual caller and use an
authorized recording or equivalent measurement. Utilization, a slow first frame
or a repeated texture read alone does not identify the bottleneck or justify a
specific optimization. Keep an unavailable recording as an evidence gap; do not
launch the target or prescribe a fix merely to complete the analysis.

## Source of the adaptation

This recipe adapts task decomposition from
[Eleven at commit 3154935](https://github.com/Zfinix/eleven/tree/3154935cdab5a5982dd21d2de67b09870d2a292b),
inspected as source. It does not claim runtime validation of Eleven:

| Source locator at that commit | Mechanism retained |
|---|---|
| `app/skills/first-look/SKILL.md:10-14`; `find/SKILL.md:10-15`; `trace-feature/SKILL.md:10-13` under `app/skills/` | Select useful anchors and trace the feature into substantive work |
| `app/skills/explain-function/SKILL.md:8-11`; `decompile/SKILL.md:10-18` under `app/skills/` | Read callers/consumers; distinguish reconstruction and uncertainty |
| `app/src/engine/project.ts:28-36,108-123`; `app/src/bridge/handlers.ts:47-54,80-118`; `app/src/bridge/reaProxy.ts:10-19,41-47` | Bind findings to an artifact and retain one owner for authorized analysis changes |
| `app/skills/network-map/SKILL.md:10-15`; `shader-check/SKILL.md:10-17` under `app/skills/` | Use call-site and recording evidence, with the narrower observation boundaries above |

Eleven's window-driving calls and automatic annotation steps are not prerequisites
here. Keep existing REA/reverse-skill composition, tools and authorization intact.
