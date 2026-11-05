# External customer groups and Wiki pages

Use this recipe when a customer needs an external collaboration group and a
bounded set of Wiki pages. It composes the CLI's embedded guides; it does not
replace their current syntax, identity rules or confirmation gates.

## Bind the job and inspect first

Follow the router's runtime and source-account binding steps. Keep the selected
profile and identity explicit. If the CLI, account, scope or target access is
missing, use `lark-shared` and its identity/permissions reference. Resume from the
first unmet condition after the person completes a required step; preserve the
chosen customer, group, page and permission. Do not reinstall or reauthorize a
working account, borrow another person's profile, or request access automatically.

Distinguish an inspection from authorization to create, invite, move, grant or
send. Reuse authorization already established for the exact operation. Otherwise,
resolve the intended group members, target page, descendant scope and permission
before the write. An inspection of a manually created group stays read-only.
Writing this workflow does not authorize future external invitations or grants.

Load only the needed embedded guides with `lark-cli skills read`:

| Job | Required guide/reference |
|---|---|
| Find/reuse a group | `lark-im`, `lark-im/references/lark-im-chat-search.md`, `lark-im/references/lark-im-chat-members-list.md` |
| Create an external group | `lark-im/references/lark-im-chat-create.md`; current `im +chat-create --help` and `schema im.chats.create` |
| Resolve/create/move Wiki nodes | `lark-wiki` and its selected shortcut references; follow its organization workflow for a restructure |
| Inspect/grant page access | `lark-drive`, `lark-drive/references/lark-drive-permission-guide.md`, and the selected member/setting shortcut references |

Search the supplied group name using `im +chat-search`, preferably with
`--disable-search-by-user`. Results can be fuzzy: reconcile the exact name,
owner, membership and `chat_id`; inspect `im chats get` using its live schema.
Multiple plausible groups require disambiguation. Empty search results describe
the selected account's visibility, not global absence; do not substitute a whole
chat listing for search or create a duplicate from that empty result alone.

Read the selected group's complete member list. Honor pagination, bucket totals
and `truncations`; an incomplete list cannot establish the recipient scope.
Check `external` explicitly. `chat_type=private` describes discoverability and
does not mean that the group is internal. A matching title alone does not bind a
group to a customer page. Save confirmed IDs in the owning project's record,
outside this update-owned Skill bundle.

## Reuse or create the group

If the user already created the intended group, reuse it. Inspect its owner,
members and current authorization before making further changes. Do not create
a replacement, re-add members, resend invitations or repeat an existing grant.

For an authorized new external group:

1. Resolve the exact human owner and authorized invitees in the selected account.
   Do not infer their IDs from display names or another app's open IDs.
2. Inspect the live create shortcut and schema. Use the shortcut if it exposes
   the required external-group behavior. A private group without explicit
   external support is not a substitute.
3. If only the typed create endpoint exposes `external`, use the identity its
   current schema supports, `external=true`, a confirmed human `owner_id`, the
   chosen members and a stable request UUID where supported. Bot creation needs
   the bot's external-sharing capability; external invitees must satisfy the
   endpoint's friendship/visibility requirements. Do not silently switch a
   user-only request to bot identity. If that path is unavailable, report the
   exact prerequisite or use an authorized official UI creation path through the
   browser owner; never bypass a permission denial.
4. Preview the supported request with `--dry-run`. Execute only within the
   established creation/invitation authorization. On a lost response, search/read
   the expected group before retrying; retain the original UUID.
5. Independently read the resulting group and actual members. Require
   `external=true` and reconcile every invited ID with successful/invalid/missing
   results. A returned group ID or successful private-group creation is not
   proof of an external group with the intended people.

Do not send a welcome message, post the Wiki link, edit a group announcement or
place content in a real send box without authorization for its target/content.

## Organize the customer pages

When the user chooses one shared external Wiki, use one customer page per
customer, with that customer's work pages beneath it. The Wiki space is the
overall container; do not insert another generic "knowledge base" page between
the space and the customer page. Keep separate spaces when that is the chosen
structure. Do not consolidate other existing customer libraries automatically.

Resolve `space_id`, `node_token`, underlying object token/type and current
parents before changing structure. Prefer moving existing nodes to preserve
their identities; move a parent once when its descendants share the destination.
Retain the original node/object/parent mapping and sibling order. Afterward,
read the destination recursively and reconcile every original node, object and
parent, including descendants covered by a parent move. Numbered titles alone
do not establish sidebar order. Keep source spaces until deletion is authorized.

Moving nodes is not permission to overwrite their text, rebuild embedded tables,
copy another library's SOPs or replace a content publisher's source mapping.
Referenced files, shortcuts and embedded resources can have independent access;
do not assume a page grant grants those source resources too.

## Enable targeted external collaboration

Inspect these layers independently:

| Layer | Required observation for a targeted customer grant |
|---|---|
| Organization/Wiki policy | Pages may be shared externally; report policy blocks with the exact required administrator action |
| Customer page | External access is enabled; link sharing remains `closed` when access should be limited to collaborators |
| Recipient | The confirmed `chat_id` is granted through `member_type=openchat` |
| Wiki scope | `perm_type=container` grants the current page and descendants; `single_page` does not |
| Role | `view`, `edit` or `full_access` matches the user's chosen collaboration role |

`space.open_sharing=closed` means the whole Wiki is not published to the internet;
it is not evidence that page-level external collaboration is disabled. Read the
actual page setting and Wiki security policy. If the installed CLI lacks a Wiki
security-setting command, use the authorized official UI's Wiki settings →
Security → allow pages to be shared externally, then reload/read it back.
This permits invitation; it does not itself invite anyone or publish the Wiki.
Do not turn a resource-access denial into a browser/raw-API retry. An administrator
policy change needs its own applicable authorization; keep unrelated policy intact.

For a page-setting change, inspect `schema drive.permission.public.patch` first.
The Wiki node token used for a descendant grant and the underlying document token
used for supported document settings are different identities. Use only the
schema-supported type/fields. Missing external access does not justify selecting
`anyone_readable` or `anyone_editable`. A settings write can make the customer
parent stop inheriting the overall Wiki's settings; inspect that exact lock rather
than resetting it blindly and undoing the customer's access boundary.

Before a group grant, read the group's current members and explain that access is
granted to the group, including subsequent members. Verify who can add members
and whether joining requires approval; do not silently tighten those settings.
Grant the customer's page, not the overall space or another customer's page.

After reading the current member-add reference, preview the exact grant:

```bash
lark-cli --profile "$PROFILE" drive +member-add \
  --token "$CUSTOMER_NODE" --type wiki \
  --member-id "$CUSTOMER_CHAT" --member-type openchat \
  --perm "$CHOSEN_ROLE" --perm-type container \
  --need-notification=false --as user --dry-run
```

For real execution, retain those parameters, remove `--dry-run` and add the
command's confirmation flag only when the exact grant is authorized. Notification
is a separate choice; keep it off unless authorized. Never infer permission to
grant `edit` or `full_access` merely from a request to share.

## Verify and resume

Fresh-read the page's collaborator list with `--type wiki --perm-type container`.
Match the exact group ID, `member_type=openchat`, intended role and descendant
scope. Read child settings to find stopped inheritance or external-access blocks.
Preserve intentional restrictions; report the exact exceptions rather than mass
restoring permissions. A protected parent is not proof its descendants are blocked.

Keep these results distinct in the handoff:

- **Structure verified:** original nodes and their destination hierarchy reconcile.
- **Grant configured:** group ID, role, descendant scope and relevant settings
  were read back successfully.
- **External access tested:** an authorized external member actually opened the
  customer page and required child/resources. Admin access, a grant row, or
  `ok=true` alone cannot establish this result.

Test another customer's denial only with an authorized test identity and target.
Do not borrow another person's session or create outside recipients for a test.
Without such a test, state its limit while delivering the verified configuration.
On interruption, re-read current group IDs, members, grants, settings and node
parents before continuing. Preserve human changes and completed operations;
continue from the first unmet condition, not from creation again.

## Authority

- [Share Wiki pages with external users](https://www.feishu.cn/hc/en-US/articles/490001133435-share-wiki-pages-with-external-users)
- [Overview of Wiki permissions](https://www.feishu.cn/hc/en-US/articles/821998241087-overview-of-wiki-space-permissions)
- [Create a group](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat/create)

Revalidate current identity support and parameters before each real creation.
