import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {randomUUID} from 'node:crypto';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, '../runtime/package.json'));
let modules;
async function loadModules() {
  if (modules) return modules;
  let entry;
  try { entry = require.resolve('agentpair'); }
  catch { throw new Error('Network runtime is missing. Run: npm ci --prefix <skill>/runtime --ignore-scripts'); }
  const base = path.dirname(entry);
  const load = rel => import(pathToFileURL(path.join(base, rel)).href);
  const [main, pair, inbox, approve, bonds, flush, protocol] = await Promise.all([
    load('index.js'), load('tools/pair.js'), load('tools/inbox.js'), load('tools/human-approve.js'),
    load('tools/list-bonds.js'), load('store/flush-context.js'),
    import(pathToFileURL(require.resolve('@agentpair/protocol')).href),
  ]);
  modules = {main, pair, inbox, approve, bonds, flush, protocol};
  return modules;
}
function unpack(result) {
  const text = result.content?.find(x => x.type === 'text')?.text;
  if (!text) throw new Error('Unexpected AgentPair result');
  return JSON.parse(text);
}
export async function transport({relay, dataDir}) {
  const nativeFetch = globalThis.fetch;
  if (!globalThis[Symbol.for('peer-message.deadline-fetch')]) {
    globalThis.fetch = (input, options = {}) => nativeFetch(input, {...options,
      signal: options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000)});
    globalThis[Symbol.for('peer-message.deadline-fetch')] = true;
  }
  const m = await loadModules();
  const {context} = m.main.createMcpServer({relayUrl: relay, dataDir});
  await m.pair.ensureAllowlistReady(context);
  await m.pair.ensurePendingApprovalReady(context);
  const keys = await context.keyStore.loadOrCreate();
  const self = m.protocol.publicKeyToAgentId(keys.publicKey);
  const invoke = async (fn, input) => {
    const r = unpack(await fn(context, input));
    await m.flush.flushAgentContext(context);
    if (r.ok === false) throw Object.assign(new Error(r.error || 'AgentPair operation failed'), {details: r});
    return r;
  };
  return {
    isBonded: peer => context.allowlist.get(self).includes(peer),
    info: () => invoke(m.bonds.handleListBonds, {}),
    invite: () => invoke(m.pair.handlePairInit, {scope: ['peer-message.ask'], mode: 'bonded_contact', profiles:['core/1']}),
    join: code => invoke(m.pair.handlePairJoin, {code}),
    approve: input => invoke(m.approve.handleHumanApprove, input),
    async pull(since, getSequence) {
      const peers = context.allowlist.get(self);
      const pulled = await context.relay.pullInbox(keys, since, {bonded_only: true, senders: peers});
      if (!pulled.ok) throw new Error(pulled.error);
      const sequences = new Map();
      const envelopes = []; const rejected = [];
      for (const wire of pulled.wires) {
        const r = await m.protocol.receiveEnvelope(wire, self, {
          selfKeyPair: keys, isBonded: from => peers.includes(from),
          seqStore: {
            getLastAccepted: (thread, from) => sequences.get(`${thread}:${from}`) ?? getSequence(thread, from),
            commitAccepted: (thread, from, seq) => sequences.set(`${thread}:${from}`, seq),
          },
          dispatch: async (body, bytes) => {
            const bond = context.bonds.find(self, body.from);
            if (body.type !== 'core.msg') return {ok: false, error: 'unsupported_envelope_type'};
            if (!m.protocol.isProfileInBond(body.type, bond?.profiles ?? ['core/1'])) return {ok: false, error: 'profile_not_supported'};
            try { return m.protocol.parseEnvelopePayload(body.type, JSON.parse(new TextDecoder().decode(bytes))); }
            catch { return {ok: false, error: 'invalid_payload'}; }
          },
        });
        if (!r.ok) { rejected.push({id: r.body?.id, error: r.error}); continue; }
        envelopes.push({...r.body, payload: JSON.parse(new TextDecoder().decode(r.plaintext)), signature_valid: true});
      }
      return {envelopes, rejected, cursor: pulled.cursor, sequences: [...sequences]};
    },
    async prepare(to, message, thread) {
      if (!context.allowlist.get(self).includes(to)) throw new Error('Recipient is not an approved contact');
      if(!Number.isFinite(message.expires_at))throw new Error('Message has no immutable application deadline');
      const payload = new TextEncoder().encode(JSON.stringify({body: JSON.stringify(message), kind: message.type}));
      if (payload.length > 24000) throw new Error('Message exceeds the preview transport limit');
      return m.protocol.createOuterEnvelope({sender: keys, recipientAgentId: to, type: 'core.msg', thread,
        seq: 1, ttl: Math.floor(message.expires_at/1000), payload, id: message.id || randomUUID()});
    },
    sendWire: (to, wire) => context.relay.sendEnvelope(to, wire),
    expiresAt: wire => m.protocol.parseEnvelopeBody(wire).ttl * 1000,
    revoke: peer => invoke(m.pair.handleRevoke, {peer}),
    flush: () => m.flush.flushAgentContext(context),
  };
}
