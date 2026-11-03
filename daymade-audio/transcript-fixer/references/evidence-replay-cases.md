# Audio-evidence replay cases

Use these synthetic cases when continuing a difficult pending queue or checking
changes to evidence selection. Execute the existing pending-continuation and
audio-check workflow; these cases add no recognition engine or verdict shortcut.

## Wrong window, successful engine

The pending phrase is in a 50-second speaker turn. A short clip returns fluent
text, but neither checked neighbour appears; the wider clip contains only the
next topic. The process exited 0.

Expected action: report failed target coverage, correct the clock/anchor using
the source, and re-cut only within the existing bounded rule. The text cannot
support the suggestion, the original, deletion or a new person identity. Empty
text with `ok:true` is likewise no wording evidence.

## A familiar component is the wrong answer

An assembly discussion elsewhere mentions rails. At the disputed occurrence,
two verified windows say “把刀具交给他”，and a second recognizer agrees; a
third recognizer returns another reading. The pending suggestion is “导轨”.

Expected action: preserve the disagreement and judge the selected occurrence.
Do not turn the familiar component elsewhere into proof here, or claim unanimous
recognition. A supported correction belongs in this occurrence's verdict and
ledger, not a bare “刀具→导轨” rule. Recognizer votes also cannot turn a spoken
“小邢总” into the roster's differently spelled “晓星总”; identity authority is
still required. If an existing dictionary entry would undo the adjudicated
wording, inspect and correct that entry through its owner before another pass.

## Evidence exists but the interface refuses it

A replay explicitly repeats a city story, but the original selected slot ends
with a comma before “市长”. An adjacent-suffix citation is refused.

Expected action: distinguish this interface gap from unreadable audio. Use the
source-bound replay record in [the queue contract](review_queue_dashboard.md#a-place-name-heard-again-in-the-same-recording)
only when its complete construction and authority are present. Missing replay
identity, anchors, municipal context or source bytes stays pending; do not
relabel a person or hand-edit around a refused verdict. A supported record must
change the exact body and ledger through the real CLI and survive queue readback.
