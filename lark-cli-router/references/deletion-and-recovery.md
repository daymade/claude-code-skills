# Deleted documents and Wiki spaces

Use this branch to locate deleted content or establish its recovery options.
Bind the source account through the router's existing identity procedure. Preserve
the notice, original URL, space/node/object IDs and deletion scope when available;
a matching title does not establish identity.

## Select the recovery surface

1. Distinguish a deleted document/page from deletion of an entire Wiki space.
   A space API returning not found does not establish permanent loss.
2. For an individual item, inspect its owning Docs/Drive or Wiki-space recycle
   bin through the current domain guide or authorized official interface. State
   which bin and identity were checked; an empty personal bin is only that result.
3. For an entire space, also inspect Wiki management in the enterprise admin
   console. Confirm the exact space ID, deleted state and available recovery
   action. Check the current [official Wiki deletion/recovery guidance](https://www.feishu.cn/hc/zh-CN/articles/557043079436-删除和恢复知识库)
   and actual interface for the applicable retention period and administrator role;
   do not turn a historical countdown into a permanent limit.
4. Prefer the installed CLI guide when it covers that operation. If it provides
   no matching admin recovery operation, use the official interface with the
   already authorized identity. Missing admin access leaves recovery unknown;
   preserve the exact missing access and continue authorized local-archive checks.

## Restore only within the authorized action

A request to inspect deleted content does not itself authorize restoration.
When restoration is already authorized, act on the exact identified object and
independently read back its restored state and accessible tree/content. Retain
permission failures and partial coverage rather than replaying an uncertain write.

After restoration, enumerate the requested tree with pagination and actual object
types through the current guides. Preserve a source-to-archive inventory for the
requested bodies, files and other resources. Resolve count differences by object
identity and scope; an empty bin or matching file hashes alone cannot explain a
space-wide discrepancy. Report the verified recovery/coverage and unresolved
items separately. Archive retention and source deletion follow their own owners
and authorization; recovery success does not establish either.
