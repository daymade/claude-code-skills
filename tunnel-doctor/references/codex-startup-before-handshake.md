# Codex startup before the local protocol

Use this case when the installed native executable answers `--version` and help,
but a task-owned app-server never answers `initialize` or creates its selected
local listener. Empty stderr and no recent runtime errors do not establish that
the protocol is unsupported. The executing agent runs these bounded probes;
this reference installs no proxy, watcher or recovery service.

## Separate program, home state and egress

1. Bind the failing executable, version, arguments, Codex home, working directory
   and effective proxy. Preserve the existing request handle and terminal state.
   Use the installed help/schema to choose the transport; switching stdio to a
   local socket without a new discriminator is not a repair.
2. Start one task-owned process using a new private temporary Codex home and the
   same executable/environment. Test its local handshake without copying auth,
   sessions, databases or the full original home. If necessary, repeat with only
   the original configuration file in that temporary home. Keep those inputs
   private and remove these task-owned copies after the probe. A successful
   temporary home narrows the failure boundary; it does not validate the real
   account, hook source or task.
3. When the real-home process opens an outbound connection before answering,
   inspect only that process's endpoint metadata and the target's effective
   proxy. Test an ordinary HTTPS request through that same route using bounded
   `curl` timeouts and `time_appconnect`, `http_connect` and final HTTP status.
   CONNECT 200 with TLS time zero and a timeout is a failed HTTPS path, not an
   application response. Avoid trace logging that could expose authorization.
4. Compare a verified existing alternative route. Where already authorized,
   scope it to the task-owned process; a loopback-only temporary SSH forward
   can carry an existing approved proxy. Bind the forwarding identity and actual
   selected port, preserve host-key checks and wait for forwarding readiness.
   Do not alter shared proxy services, default routes or credentials to make
   this comparison. A host/permission refusal remains a stop condition.
5. Replay the original operation with its real home/config and exact target
   through that route. Read its actual result, then close the owned process,
   forward and temporary inputs. On an unknown result, inspect side effects
   before repeating a write.

## Interpret the result at its boundary

If the real-home operation succeeds through the alternative route while the
original HTTPS route fails, retain the egress dependency as the actionable
finding. Do not infer which internal startup request blocked unless separately
observed. Do not reset login, delete state databases, reinstall the CLI or disable
hooks from the handshake symptom alone.

Report separately: the requested operation completed through the tested route;
temporary resources were closed; the default route remains failed or unverified.
For a lasting recovery, return to the existing network-configuration owner and
verify the ordinary consumer there. A controller-held temporary forward does not
establish Worker operation after the controller disconnects.
