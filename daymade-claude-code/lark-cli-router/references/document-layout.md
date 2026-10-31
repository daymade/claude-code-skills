# Preserve document layout during updates

Use this reference when a document update must retain manual table widths or a
reader asks for a wider page. The executing agent selects the current embedded
`lark-doc` guide and its update, fetch and format references through the router.
Those guides and the live schema own syntax; this reference owns preservation
and acceptance decisions.

## Separate the state being changed

| State | How to treat it |
|---|---|
| Body text and table cells | Read and update through the selected content workflow. |
| Shared table column widths | Capture the current native/XML properties when preserving them; a Markdown export or text hash does not establish geometry. |
| A reader's page-width preference | Treat it as that reader's view. A shared table edit does not establish another reader's full-width setting. |

Feishu's [page-width help](https://www.feishu.cn/hc/zh-CN/articles/909135942944-设置文档页面宽度)
describes page width as a personal setting. Do not promise a shared or global
full-width default from a document-content write. Check current UI/API support
and its scope before claiming such a setting can be automated.

## Plan the smallest preserving update

1. Capture the target document identity, revision, affected table identities and
   current column widths before writing. Define which manual properties this
   operation will preserve; preserving widths alone does not preserve every
   format, comment, resource or block ID.
2. Prefer the embedded guide's local content operations. If an already-authorized
   publisher must rebuild tables, save widths before replacement and match each
   old table to its replacement by an explicit structural identity. Table order
   alone is insufficient; duplicate identities or changed column structure need
   a resolved mapping before any destructive write.
3. Retain the matched existing widths. Allocate widths by visible content only
   for new tables or when the user explicitly requests resizing. Give short
   identifiers less space and long titles/descriptions more; long URLs hidden
   behind link labels should not determine the visible text width.
4. Use the target's documented conditional-write and idempotency mechanisms.
   An interrupted publisher needs its own durable recovery state. A lost receipt
   is an unknown outcome; do not repeat the write or restore a stale baseline
   until readback establishes what happened. A later human change, including a
   return to an old width value, is a conflict to preserve.

If the current interface cannot read or preserve a required property, report that
specific gap before the affected overwrite. This checklist is applied by the
executing agent; the router itself does not enforce layout preservation.

## Verify the result at both surfaces

- Independently read back the body and each affected table's native/XML widths.
  Equal Markdown alone cannot prove equal layout. Reacquire identities after
  replacement rather than using stale block IDs.
- For readability work, inspect the actual document in the intended reader's
  browser and viewport. Check representative short and long cells for excessive
  wrapping or clipping; computed widths are a starting point, not a universal
  optimum. Browser inspection supplements the API workflow and does not bypass
  a target/profile permission denial.
- When changing a publisher, use an authorized disposable copy for a body change
  plus a new table. Check preservation of existing widths, allocation for the new
  table, and a no-write repeat with unchanged inputs. Cover interrupted writes
  and subsequent human edits in the owning publisher's existing regressions.

Stop after the affected content, geometry and requested reading task are verified.
Keep unobserved viewers or viewports explicit; do not claim their settings or
readability from one reader's successful result.
