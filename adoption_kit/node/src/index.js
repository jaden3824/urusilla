'use strict';

const crypto = require('node:crypto');

const PRODUCT_LABEL = 'Urusilla Adoption Kit';
const INTERFACE_VERSION = '1.0.0';
const CAPABILITY_FORMAT = 'urusilla-capability-v1';
const DELIVERY_FORMAT = 'urusilla-delivery-v1';
const LANGUAGE_VERSION = '0.1.0';
const RELEASE_STATUS = 'experimental-unsigned';
const CAPSULE_SHA256 = '588034f997fb4f3d35dfdbb68afd9232a78192ac1fa497d565f67e0892358a27';
const CAPSULE_BYTES = 33_476;
const CAPSULE_BOUND_REFERENCE_SHA256 = '3cb84380149a522bdadd94e866e39a848fa23c8b666382c4f88ce341147fbdcf';
const OBSERVED_REFERENCE_SHA256 = '3cb84380149a522bdadd94e866e39a848fa23c8b666382c4f88ce341147fbdcf';
const PROFILE_CAPSULE_SHA256 = 'b8d2cee7827f57e9c1b523cb195fbb75f3a91f8ad20e7a2f5209ce3abf63cdf6';
const PROFILE_DICTIONARY_ID = '7d12fc414eae60b2';
const PROFILE_ID = 1;
const MAX_DELIVERY_BYTES = 16 * 1024 * 1024;
const MAX_STRING_BYTES = 1024 * 1024;
const MAX_COLLECTION_ITEMS = 100_000;
const A2A_LOCAL_EXTENSION = 'urn:urusilla:local:1';

const REPRESENTATIONS = Object.freeze({
  JSON: 'canonical-json-v1',
  TERSE: 'controlled-terse-english-v1',
  WIRE_V01: 'urusilla-wire-v0.1',
  WIRE_V02: 'urusilla-wire-v0.2-static-7d12fc414eae60b2',
});
const REP_IDS = Object.freeze(Object.values(REPRESENTATIONS));
const COMPACT_IDS = new Set([REPRESENTATIONS.WIRE_V01, REPRESENTATIONS.WIRE_V02]);
const MODES = new Set(['bridge', 'native', 'fallback']);
const ACTS = Object.freeze(['ASSERT', 'QUERY', 'REQUEST', 'PROPOSE', 'COMMIT', 'RESOLVE', 'RETRACT']);
const ACT_INDEX = new Map(ACTS.map((act, index) => [act, index]));
const EFFECTFUL_ACTS = new Set(['COMMIT', 'RESOLVE', 'RETRACT']);
const SOURCE_RE = /^[0-9a-f]{32}$/;
const SHA_RE = /^[0-9a-f]{64}$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const IDENTIFIER_RE = /^[A-Za-z][A-Za-z0-9+.-]*:\S+$/;

const REQUIRED_NODE = Object.freeze({
  claim: ['predicate'], goal: ['condition'], constraint: ['scope', 'mode', 'condition'],
  evidence: ['target', 'stance', 'digest', 'provenance'],
  uncertainty: ['target', 'model', 'parameters'], action: ['capability', 'arguments'],
  commitment: ['debtor', 'creditors', 'goal', 'expiry_ms'],
  resolution: ['target', 'status'], ref: ['uri'],
});
const ALLOWED_NODE = Object.freeze({
  claim: ['kind', 'predicate', 'arguments', 'context', 'valid_time', 'answer_limit', 'annotations'],
  goal: ['kind', 'condition', 'owner', 'window', 'priority', 'constraints', 'annotations'],
  constraint: ['kind', 'scope', 'mode', 'condition', 'weight', 'weight_ppm', 'annotations'],
  evidence: ['kind', 'target', 'stance', 'digest', 'provenance', 'observed_at', 'observed_at_ms', 'method', 'annotations'],
  uncertainty: ['kind', 'target', 'model', 'parameters', 'basis', 'annotations'],
  action: ['kind', 'capability', 'arguments', 'declared_effects', 'annotations'],
  commitment: ['kind', 'debtor', 'creditors', 'goal', 'expiry_ms', 'verifier', 'cancellation_rule', 'annotations'],
  resolution: ['kind', 'target', 'status', 'result', 'evidence', 'annotations'],
  ref: ['kind', 'uri', 'annotations'],
});
const ACT_KINDS = Object.freeze({
  ASSERT: ['claim', 'evidence', 'uncertainty', 'ref'], QUERY: ['claim'], REQUEST: ['goal'],
  PROPOSE: ['action'], COMMIT: ['commitment'], RESOLVE: ['resolution'], RETRACT: ['ref'],
});
const TOP_FIELDS = new Set(['id', 'session', 'sender', 'recipients', 'act', 'reply_to', 'schema', 'logical_clock', 'expires_ms', 'confidence_ppm', 'expected', 'body', 'meta']);

class IntegrationError extends Error {
  constructor(message, code = 'INTEGRATION_ERROR') { super(message); this.name = 'IntegrationError'; this.code = code; }
}
function error(message, code) { throw new IntegrationError(message, code); }
function isObject(value) { return value !== null && typeof value === 'object' && !Array.isArray(value) && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null); }
function sha256(data) { return crypto.createHash('sha256').update(data).digest('hex'); }
function requireSha(value, field) { if (typeof value !== 'string' || !SHA_RE.test(value)) error(`${field} must be 64 lowercase hexadecimal characters`, 'DIGEST'); return value; }
function requireSource(value, field = 'source_id') { if (typeof value !== 'string' || !SOURCE_RE.test(value)) error(`${field} must be 32 lowercase hexadecimal characters`, 'SOURCE_PIN'); return value; }
function requireUint(value, field, max = Number.MAX_SAFE_INTEGER) { if (!Number.isSafeInteger(value) || value < 0 || value > max) error(`${field} must be a non-negative safe integer`, 'SEMANTIC_VALIDATION'); return value; }
function validUnicode(value) { for (let i = 0; i < value.length; i += 1) { const code = value.charCodeAt(i); if (code >= 0xd800 && code <= 0xdbff) { if (i + 1 >= value.length || value.charCodeAt(++i) < 0xdc00 || value.charCodeAt(i) > 0xdfff) return false; } else if (code >= 0xdc00 && code <= 0xdfff) return false; } return true; }
function requireUnicode(value, field) { if (typeof value !== 'string' || !validUnicode(value) || Buffer.byteLength(value) > MAX_STRING_BYTES) error(`${field} must be valid bounded Unicode text`, 'SEMANTIC_VALIDATION'); return value; }
function requireText(value, field) { requireUnicode(value, field); if (!value || /\s/u.test(value)) error(`${field} must be non-empty text without whitespace or controls`, 'SEMANTIC_VALIDATION'); return value; }
function requireId(value, field) { requireText(value, field); if (!IDENTIFIER_RE.test(value)) error(`${field} must be an absolute identifier`, 'SEMANTIC_VALIDATION'); return value; }
function compareText(a, b) { const left = [...a], right = [...b]; for (let i = 0; i < Math.min(left.length, right.length); i += 1) { const delta = left[i].codePointAt(0) - right[i].codePointAt(0); if (delta) return delta; } return left.length - right.length; }
function compareUtf8(a, b) { return Buffer.compare(Buffer.from(a), Buffer.from(b)); }

function normalizeJson(value, depth = 0, seen = new WeakSet()) {
  if (depth > 64) error('JSON exceeds maximum depth 64', 'JSON');
  if (value === null || typeof value === 'boolean') return value;
  if (typeof value === 'string') { requireUnicode(value, 'JSON string'); return value; }
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) error('Node endpoint JSON supports safe integers only; float64 and unsafe integers require another endpoint', 'JSON');
    return Object.is(value, -0) ? 0 : value;
  }
  if (typeof value !== 'object' || seen.has(value)) error('value is not acyclic JSON', 'JSON');
  seen.add(value);
  try {
    if (Array.isArray(value)) { if (value.length > MAX_COLLECTION_ITEMS) error('JSON array exceeds item limit', 'JSON'); return value.map((item) => normalizeJson(item, depth + 1, seen)); }
    if (!isObject(value)) error('JSON mappings must be plain objects', 'JSON');
    if (Object.keys(value).length > MAX_COLLECTION_ITEMS) error('JSON object exceeds item limit', 'JSON');
    const out = {};
    for (const key of Object.keys(value).sort(compareText)) { requireUnicode(key, 'JSON member name'); out[key] = normalizeJson(value[key], depth + 1, seen); }
    return out;
  } finally { seen.delete(value); }
}
function renderJson(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(renderJson).join(',')}]`;
  return `{${Object.keys(value).sort(compareText).map((key) => `${JSON.stringify(key)}:${renderJson(value[key])}`).join(',')}}`;
}
function canonicalJson(value) { return renderJson(normalizeJson(value)); }
function parseCanonicalJson(text) {
  if (typeof text !== 'string' || Buffer.byteLength(text) > MAX_DELIVERY_BYTES) error('JSON text type or size is invalid', 'JSON');
  let value; try { value = JSON.parse(text); } catch { error('payload is not strict JSON', 'JSON'); }
  if (canonicalJson(value) !== text) error('JSON payload is valid but not kit-canonical', 'JSON');
  return value;
}

function validateNode(value, depth = 0) {
  if (depth > 64) error('semantic tree exceeds maximum depth 64', 'SEMANTIC_VALIDATION');
  if (Array.isArray(value)) { value.forEach((item) => validateNode(item, depth + 1)); return; }
  if (!isObject(value)) return;
  if (value.kind !== undefined) {
    if (typeof value.kind !== 'string') error('node kind must be a string', 'SEMANTIC_VALIDATION');
    if (REQUIRED_NODE[value.kind]) {
      for (const field of REQUIRED_NODE[value.kind]) if (!(field in value)) error(`${value.kind} node is missing ${field}`, 'SEMANTIC_VALIDATION');
      for (const field of Object.keys(value)) if (!ALLOWED_NODE[value.kind].includes(field)) error(`${value.kind} node has unknown field ${field}`, 'SEMANTIC_VALIDATION');
    } else if (!value.kind.startsWith('x:') || value.kind.length === 2 || /\s/.test(value.kind)) error('unknown node kind; local extensions require x:<name>', 'SEMANTIC_VALIDATION');
  }
  Object.values(value).forEach((item) => validateNode(item, depth + 1));
  if (value.kind && value.annotations !== undefined && !isObject(value.annotations)) error(`${value.kind}.annotations must be a map`, 'SEMANTIC_VALIDATION');
  if (value.kind === 'constraint' && !['hard', 'soft'].includes(value.mode)) error('constraint.mode must be hard or soft', 'SEMANTIC_VALIDATION');
  if (value.kind === 'claim') { requireText(value.predicate, 'claim.predicate'); if (value.arguments !== undefined && !Array.isArray(value.arguments)) error('claim.arguments must be a list', 'SEMANTIC_VALIDATION'); if (value.context !== undefined && !isObject(value.context)) error('claim.context must be a map', 'SEMANTIC_VALIDATION'); if (value.answer_limit !== undefined && (!Number.isSafeInteger(value.answer_limit) || value.answer_limit <= 0)) error('claim.answer_limit must be a positive safe integer', 'SEMANTIC_VALIDATION'); }
  if (value.kind === 'goal') { if (!isObject(value.condition)) error('goal.condition must be a semantic node', 'SEMANTIC_VALIDATION'); if (value.owner !== undefined) requireText(value.owner, 'goal.owner'); if (value.priority !== undefined && !Number.isSafeInteger(value.priority)) error('goal.priority must be a safe integer', 'SEMANTIC_VALIDATION'); if (value.constraints !== undefined && (!Array.isArray(value.constraints) || value.constraints.some((item) => !isObject(item) || item.kind !== 'constraint'))) error('goal.constraints must contain constraint nodes', 'SEMANTIC_VALIDATION'); }
  if (value.kind === 'constraint') { requireText(value.scope, 'constraint.scope'); if (value.weight_ppm !== undefined) requireUint(value.weight_ppm, 'constraint.weight_ppm', 1_000_000); }
  if (value.kind === 'evidence') { if (!['supports', 'contradicts', 'neutral'].includes(value.stance)) error('unknown evidence stance', 'SEMANTIC_VALIDATION'); requireId(value.digest, 'evidence.digest'); if (typeof value.provenance !== 'string' && !isObject(value.provenance) && !Array.isArray(value.provenance)) error('evidence.provenance has an invalid type', 'SEMANTIC_VALIDATION'); }
  if (value.kind === 'uncertainty') { requireText(value.model, 'uncertainty.model'); if (!isObject(value.parameters)) error('uncertainty.parameters must be a map', 'SEMANTIC_VALIDATION'); if (value.basis !== undefined && !Array.isArray(value.basis)) error('uncertainty.basis must be a list', 'SEMANTIC_VALIDATION'); }
  if (value.kind === 'action') { requireText(value.capability, 'action.capability'); if (!isObject(value.arguments) && !Array.isArray(value.arguments)) error('action.arguments must be a map or list', 'SEMANTIC_VALIDATION'); if (value.declared_effects !== undefined && (!Array.isArray(value.declared_effects) || value.declared_effects.some((item) => typeof item !== 'string' || !item))) error('action.declared_effects must contain non-empty strings', 'SEMANTIC_VALIDATION'); }
  if (value.kind === 'commitment') {
    requireText(value.debtor, 'commitment.debtor'); if (!Array.isArray(value.creditors) || !value.creditors.length || value.creditors.some((item) => typeof item !== 'string' || !item) || new Set(value.creditors).size !== value.creditors.length) error('commitment.creditors must be unique non-empty strings', 'SEMANTIC_VALIDATION');
    if (!isObject(value.goal) || value.goal.kind !== 'goal') error('commitment.goal must be a goal node', 'SEMANTIC_VALIDATION');
    requireUint(value.expiry_ms, 'commitment.expiry_ms'); if (value.verifier !== undefined) requireText(value.verifier, 'commitment.verifier');
  }
  if (value.kind === 'resolution') { if (!['succeeded', 'completed', 'failed', 'expired', 'rejected', 'canceled', 'error'].includes(value.status)) error('unknown resolution status', 'SEMANTIC_VALIDATION'); if (value.evidence !== undefined && !isObject(value.evidence) && !Array.isArray(value.evidence)) error('resolution.evidence must be a semantic node or list', 'SEMANTIC_VALIDATION'); }
  if (value.kind === 'ref') requireId(value.uri, 'ref.uri');
}

function normalizeMessage(message) {
  if (!isObject(message)) error('message must be an object', 'SEMANTIC_VALIDATION');
  for (const field of ['id', 'session', 'sender', 'recipients', 'act', 'schema', 'body']) if (!(field in message)) error(`message is missing ${field}`, 'SEMANTIC_VALIDATION');
  for (const field of Object.keys(message)) if (!TOP_FIELDS.has(field)) error(`unknown top-level field ${field}`, 'SEMANTIC_VALIDATION');
  if (!UUID_RE.test(message.id) || !UUID_RE.test(message.session)) error('id and session must be canonical lowercase UUIDs', 'SEMANTIC_VALIDATION');
  const sender = requireText(message.sender, 'sender');
  if (!Array.isArray(message.recipients) || !message.recipients.length || message.recipients.length > MAX_COLLECTION_ITEMS || message.recipients.some((item) => typeof item !== 'string' || !item) || new Set(message.recipients).size !== message.recipients.length) error('recipients must be a unique non-empty bounded string list', 'SEMANTIC_VALIDATION');
  const recipients = message.recipients.map((item) => requireText(item, 'recipient'));
  const act = typeof message.act === 'string' ? message.act.toUpperCase() : '';
  if (!ACT_INDEX.has(act)) error('unknown communicative act', 'SEMANTIC_VALIDATION');
  const reply = message.reply_to == null ? null : message.reply_to;
  if (reply !== null && !UUID_RE.test(reply)) error('reply_to must be a canonical UUID', 'SEMANTIC_VALIDATION');
  if (EFFECTFUL_ACTS.has(act) && reply === null) error(`${act} requires reply_to`, 'SEMANTIC_VALIDATION');
  const schema = requireId(message.schema, 'schema');
  const expectedInput = message.expected === undefined ? [] : message.expected;
  if (!Array.isArray(expectedInput)) error('expected must be a list', 'SEMANTIC_VALIDATION');
  const expected = [...new Set(expectedInput.map((item) => typeof item === 'string' ? item.toUpperCase() : ''))];
  if (expected.some((item) => !ACT_INDEX.has(item))) error('expected contains an unknown act', 'SEMANTIC_VALIDATION');
  expected.sort((a, b) => ACT_INDEX.get(a) - ACT_INDEX.get(b));
  const body = normalizeJson(message.body); validateNode(body);
  const meta = normalizeJson(message.meta === undefined ? {} : message.meta); if (!isObject(meta)) error('meta must be a map', 'SEMANTIC_VALIDATION');
  if (!isObject(body)) error('body must be a semantic map', 'SEMANTIC_VALIDATION');
  if (body.kind === undefined && act === 'QUERY') {
    const allowed = new Set(['question', 'answer_schema', 'constraints', 'annotations']); if (Object.keys(body).some((field) => !allowed.has(field)) || !isObject(body.question) || typeof body.answer_schema !== 'string') error('untyped QUERY requires question and answer_schema only', 'SEMANTIC_VALIDATION'); requireId(body.answer_schema, 'QUERY answer_schema');
  } else if (typeof body.kind !== 'string') error('body must declare kind', 'SEMANTIC_VALIDATION');
  else if (body.kind.startsWith('x:')) { if (act !== 'ASSERT') error('local extensions are quarantined to ASSERT', 'SEMANTIC_VALIDATION'); }
  else if (!ACT_KINDS[act].includes(body.kind)) error(`${act} cannot carry ${body.kind}`, 'SEMANTIC_VALIDATION');
  if (act === 'COMMIT' && body.debtor !== sender) error('COMMIT debtor must equal sender', 'SEMANTIC_VALIDATION');
  return { id: message.id, session: message.session, sender, recipients, act, reply_to: reply, schema,
    logical_clock: requireUint(message.logical_clock === undefined ? 0 : message.logical_clock, 'logical_clock'),
    expires_ms: requireUint(message.expires_ms === undefined ? 0 : message.expires_ms, 'expires_ms'),
    confidence_ppm: message.confidence_ppm == null ? null : requireUint(message.confidence_ppm, 'confidence_ppm', 1_000_000),
    expected, body, meta };
}

const SAFE_TOKEN = /^[A-Za-z0-9_][A-Za-z0-9._:/-]*$/;
const SAFE_KEY = /^[A-Za-z_][A-Za-z0-9_-]*$/;
const NUMBER = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/;
const RESERVED = new Set(['true', 'false', 'null', 'none', 'unknown']);
function renderValue(value) {
  if (value === null) return 'null'; if (value === true) return 'true'; if (value === false) return 'false';
  if (typeof value === 'number') return JSON.stringify(value);
  if (typeof value === 'string') return SAFE_TOKEN.test(value) && !RESERVED.has(value) && !NUMBER.test(value) && !value.startsWith('bytes') ? value : JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(renderValue).join(',')}]`;
  return `{${Object.keys(value).sort(compareUtf8).map((key) => `${SAFE_KEY.test(key) ? key : JSON.stringify(key)}=${renderValue(value[key])}`).join(',')}}`;
}
class ValueParser {
  constructor(text, position = 0) { this.text = text; this.position = position; }
  literal(value) { if (!this.text.startsWith(value, this.position)) error(`expected ${value} at ${this.position}`, 'TERSE'); this.position += value.length; }
  quoted() { let end = this.position + 1, escaped = false; for (; end < this.text.length; end += 1) { const c = this.text[end]; if (c === '"' && !escaped) { end += 1; break; } escaped = c === '\\' && !escaped; if (c !== '\\') escaped = false; } let value; try { value = JSON.parse(this.text.slice(this.position, end)); } catch { error('invalid quoted string', 'TERSE'); } if (typeof value !== 'string') error('expected quoted string', 'TERSE'); this.position = end; return value; }
  bare() { const start = this.position; while (this.position < this.text.length && !',]} ;'.includes(this.text[this.position])) this.position += 1; if (start === this.position) error('expected terse value', 'TERSE'); return this.text.slice(start, this.position); }
  value() { const c = this.text[this.position]; if (c === '"') return this.quoted(); if (c === '[') return this.array(); if (c === '{') return this.map(); const token = this.bare(); if (token === 'null') return null; if (token === 'true') return true; if (token === 'false') return false; if (NUMBER.test(token)) { const n = Number(token); if (!Number.isFinite(n) || (Number.isInteger(n) && !Number.isSafeInteger(n))) error('unsafe terse number', 'TERSE'); return n; } if (!SAFE_TOKEN.test(token) || RESERVED.has(token) || token.startsWith('bytes')) error('invalid bare token', 'TERSE'); return token; }
  array() { const out = []; this.literal('['); if (this.text[this.position] === ']') { this.position += 1; return out; } while (true) { out.push(this.value()); if (this.text[this.position] === ']') { this.position += 1; return out; } this.literal(','); } }
  map() { const out = {}; this.literal('{'); if (this.text[this.position] === '}') { this.position += 1; return out; } while (true) { const key = this.text[this.position] === '"' ? this.quoted() : (() => { const start = this.position; while (this.text[this.position] !== '=') { if (this.position >= this.text.length || ',{}[]; '.includes(this.text[this.position])) error('invalid terse map key', 'TERSE'); this.position += 1; } const k = this.text.slice(start, this.position); if (!SAFE_KEY.test(k)) error('invalid terse map key', 'TERSE'); return k; })(); this.literal('='); if (key in out) error('duplicate terse map key', 'TERSE'); out[key] = this.value(); if (this.text[this.position] === '}') { this.position += 1; return out; } this.literal(','); } }
}
function canUseControlledEnglish(message) { try { normalizeMessage(message); return true; } catch { return false; } }
function encodeControlledEnglish(message) {
  const m = normalizeMessage(message);
  return `${m.act} from ${renderValue(m.sender)} to ${renderValue(m.recipients)}: ${renderValue(m.body)}; id ${renderValue(m.id)}, session ${renderValue(m.session)}, reply ${m.reply_to === null ? 'none' : renderValue(m.reply_to)}, schema ${renderValue(m.schema)}, clock ${m.logical_clock}, expires ${m.expires_ms}ms, confidence ${m.confidence_ppm === null ? 'unknown' : `${m.confidence_ppm}ppm`}, expect ${renderValue(m.expected)}, meta ${renderValue(m.meta)}.`;
}
function parseUint(parser, suffix) { const match = /^(?:0|[1-9][0-9]*)/.exec(parser.text.slice(parser.position)); if (!match) error('expected unsigned integer', 'TERSE'); parser.position += match[0].length; parser.literal(suffix); return requireUint(Number(match[0]), 'terse integer'); }
function decodeControlledEnglish(text) {
  if (typeof text !== 'string' || Buffer.byteLength(text) > MAX_DELIVERY_BYTES) error('controlled text type or size is invalid', 'TERSE');
  const actMatch = /^[A-Z]+/.exec(text); if (!actMatch || !ACT_INDEX.has(actMatch[0])) error('unknown terse act', 'TERSE'); const p = new ValueParser(text, actMatch[0].length);
  p.literal(' from '); const sender = p.value(); p.literal(' to '); const recipients = p.value(); p.literal(': '); const body = p.value(); p.literal('; id '); const id = p.value(); p.literal(', session '); const session = p.value(); p.literal(', reply '); let reply = null; if (p.text.startsWith('none', p.position)) p.position += 4; else reply = p.value(); p.literal(', schema '); const schema = p.value(); p.literal(', clock '); const clock = parseUint(p, ''); p.literal(', expires '); const expires = parseUint(p, 'ms'); p.literal(', confidence '); let confidence = null; if (p.text.startsWith('unknown', p.position)) p.position += 7; else confidence = parseUint(p, 'ppm'); p.literal(', expect '); const expected = p.value(); p.literal(', meta '); const meta = p.value(); p.literal('.'); if (p.position !== text.length) error('trailing terse text', 'TERSE');
  const message = normalizeMessage({ id, session, sender, recipients, act: actMatch[0], reply_to: reply, schema, logical_clock: clock, expires_ms: expires, confidence_ppm: confidence, expected, body, meta });
  if (encodeControlledEnglish(message) !== text) error('terse text is valid but not canonical', 'TERSE'); return message;
}

function representation(id, canEncode, canDecode, relayOnly, requires, profile) {
  const item = { id, can_encode: canEncode, can_decode: canDecode, relay_only: relayOnly, requires_cached_artifacts: [...requires] };
  if (profile) item.profile = { ...profile }; return item;
}
function createCapabilities({ sourceId, cachedArtifacts = [], sourceStatus = 'unverified-local-pin', sourceManifestPayloadSha256 = null, sourceManifestSignatureStatus = 'not-supplied' }) {
  requireSource(sourceId); requireText(sourceStatus, 'sourceStatus'); requireText(sourceManifestSignatureStatus, 'sourceManifestSignatureStatus'); if (sourceManifestPayloadSha256 !== null) requireSha(sourceManifestPayloadSha256, 'sourceManifestPayloadSha256'); if (!Array.isArray(cachedArtifacts)) error('cachedArtifacts must be an array', 'CAPABILITY'); const cached = cachedArtifacts.map((v) => requireSha(v, 'cached artifact')); if (new Set(cached).size !== cached.length) error('cachedArtifacts contains a duplicate', 'CAPABILITY'); cached.sort(compareText);
  return { format: CAPABILITY_FORMAT, interface_version: INTERFACE_VERSION, product_label: PRODUCT_LABEL, lifecycle: RELEASE_STATUS,
    semantics: { language_version: LANGUAGE_VERSION, capsule_sha256: CAPSULE_SHA256, release_status: RELEASE_STATUS, normative_representation: 'typed-ir' },
    pins: { source_id: sourceId, source_status: sourceStatus, source_manifest_payload_sha256: sourceManifestPayloadSha256, source_manifest_signature_status: sourceManifestSignatureStatus },
    provenance: { capsule_reference_codec_sha256: CAPSULE_BOUND_REFERENCE_SHA256, observed_reference_codec_sha256: OBSERVED_REFERENCE_SHA256, reference_codec_matches_capsule: true, support_claim_eligible: false },
    modes: { bridge: { supported: true, claim: 'adapter input normalized by a local root-compatible validator' }, native: { supported: false, verified: false, claim: 'Node bridge never infers native model support' }, fallback: { supported: true, order: [REPRESENTATIONS.JSON, REPRESENTATIONS.TERSE] } },
    representations: [representation(REPRESENTATIONS.JSON, true, true, false, [CAPSULE_SHA256]), representation(REPRESENTATIONS.TERSE, true, true, false, [CAPSULE_SHA256]), representation(REPRESENTATIONS.WIRE_V01, false, false, true, [CAPSULE_SHA256]), representation(REPRESENTATIONS.WIRE_V02, false, false, true, [CAPSULE_SHA256, PROFILE_CAPSULE_SHA256], { profile_id: PROFILE_ID, profile_capsule_sha256: PROFILE_CAPSULE_SHA256, dictionary_id: PROFILE_DICTIONARY_ID, status: 'benchmark-specialized-experimental' })],
    cached_artifacts: cached, bindings: { json_envelope: true, a2a_message_shape: 'private-local-identifier-not-official-extension', mcp_structured_content: 'friendly-shape-not-conformance-claim' },
    limits: { max_delivery_bytes: MAX_DELIVERY_BYTES, json_max_safe_integer: Number.MAX_SAFE_INTEGER, json_float64: false, json_bytes: false, controlled_terse_float64: false, controlled_terse_bytes: false },
    safety: { effect_authorization: false, network_io: false, unsigned_operation_read_only: true, provenance_bound: false } };
}
function validateCapabilities(capability) {
  const top = ['bindings', 'cached_artifacts', 'format', 'interface_version', 'lifecycle', 'limits', 'modes', 'pins', 'product_label', 'provenance', 'representations', 'safety', 'semantics'];
  if (!isObject(capability) || canonicalJson(Object.keys(capability).sort(compareText)) !== canonicalJson(top) || capability.format !== CAPABILITY_FORMAT || capability.interface_version !== INTERFACE_VERSION || capability.product_label !== PRODUCT_LABEL || capability.lifecycle !== RELEASE_STATUS) error('unsupported or open capability format', 'CAPABILITY');
  if (!isObject(capability.semantics) || canonicalJson(Object.keys(capability.semantics).sort(compareText)) !== canonicalJson(['capsule_sha256', 'language_version', 'normative_representation', 'release_status']) || typeof capability.semantics.language_version !== 'string' || capability.semantics.normative_representation !== 'typed-ir' || capability.semantics.release_status !== RELEASE_STATUS) error('invalid capability semantics', 'CAPABILITY'); requireSha(capability.semantics.capsule_sha256, 'semantics.capsule_sha256');
  if (!isObject(capability.pins) || canonicalJson(Object.keys(capability.pins).sort(compareText)) !== canonicalJson(['source_id', 'source_manifest_payload_sha256', 'source_manifest_signature_status', 'source_status'])) error('invalid capability pins', 'CAPABILITY'); requireSource(capability.pins.source_id, 'capability source_id'); if (capability.pins.source_manifest_payload_sha256 !== null) requireSha(capability.pins.source_manifest_payload_sha256, 'source manifest payload'); if (typeof capability.pins.source_manifest_signature_status !== 'string') error('invalid source manifest status', 'CAPABILITY');
  if (!isObject(capability.provenance) || capability.provenance.support_claim_eligible !== false || typeof capability.provenance.reference_codec_matches_capsule !== 'boolean') error('invalid capability provenance', 'CAPABILITY'); requireSha(capability.provenance.capsule_reference_codec_sha256, 'Capsule codec pin'); requireSha(capability.provenance.observed_reference_codec_sha256, 'observed codec pin');
  if (!isObject(capability.modes) || canonicalJson(Object.keys(capability.modes).sort(compareText)) !== canonicalJson(['bridge', 'fallback', 'native']) || ['bridge', 'native', 'fallback'].some((m) => !isObject(capability.modes[m]) || typeof capability.modes[m].supported !== 'boolean')) error('capability must declare all modes', 'CAPABILITY');
  if (capability.modes.native.supported && capability.modes.native.verified !== true) error('native support lacks verified evidence', 'CAPABILITY'); if (!Array.isArray(capability.modes.fallback.order) || capability.modes.fallback.order.some((id) => ![REPRESENTATIONS.JSON, REPRESENTATIONS.TERSE].includes(id))) error('invalid fallback order', 'CAPABILITY');
  if (!Array.isArray(capability.cached_artifacts) || capability.cached_artifacts.some((v) => typeof v !== 'string' || !SHA_RE.test(v)) || new Set(capability.cached_artifacts).size !== capability.cached_artifacts.length) error('invalid cached_artifacts', 'CAPABILITY');
  if (!Array.isArray(capability.representations)) error('invalid representations', 'CAPABILITY'); const seen = new Set();
  for (const rep of capability.representations) { if (!isObject(rep) || !REP_IDS.includes(rep.id) || seen.has(rep.id)) error('unknown or duplicate representation', 'CAPABILITY'); seen.add(rep.id); for (const f of ['can_encode', 'can_decode', 'relay_only']) if (typeof rep[f] !== 'boolean') error(`invalid ${f}`, 'CAPABILITY'); if (!Array.isArray(rep.requires_cached_artifacts) || rep.requires_cached_artifacts.some((v) => typeof v !== 'string' || !SHA_RE.test(v)) || new Set(rep.requires_cached_artifacts).size !== rep.requires_cached_artifacts.length) error('invalid representation cache requirements', 'CAPABILITY'); }
  if (!isObject(capability.limits) || capability.limits.max_delivery_bytes !== MAX_DELIVERY_BYTES || capability.limits.json_max_safe_integer !== Number.MAX_SAFE_INTEGER || capability.limits.json_float64 !== false || capability.limits.json_bytes !== false || typeof capability.limits.controlled_terse_float64 !== 'boolean' || typeof capability.limits.controlled_terse_bytes !== 'boolean') error('unsafe cross-runtime limits', 'CAPABILITY');
  if (!isObject(capability.safety) || canonicalJson(Object.keys(capability.safety).sort(compareText)) !== canonicalJson(['effect_authorization', 'network_io', 'provenance_bound', 'unsigned_operation_read_only']) || capability.safety.effect_authorization !== false || capability.safety.network_io !== false || capability.safety.unsigned_operation_read_only !== true || capability.safety.provenance_bound !== false) error('unsafe capability flags', 'CAPABILITY'); return capability;
}
function repMap(cap) { return new Map(cap.representations.map((item) => [item.id, item])); }
function negotiate(localInput, peerInput, message, { requestedMode = 'bridge', preferredRepresentation } = {}) {
  const local = validateCapabilities(localInput), peer = validateCapabilities(peerInput), canonical = normalizeMessage(message); if (!MODES.has(requestedMode)) error('unknown requested mode', 'NEGOTIATION');
  const compatible = local.semantics.language_version === peer.semantics.language_version && local.semantics.capsule_sha256 === peer.semantics.capsule_sha256;
  let mode = requestedMode; let reason = null; if (requestedMode === 'native' && (!local.modes.native.supported || !peer.modes.native.supported)) { mode = 'fallback'; reason = 'native_evidence_unavailable'; } else if (requestedMode === 'bridge' && !peer.modes.bridge.supported) { mode = 'fallback'; reason = 'requested_mode_unsupported'; } if (!compatible) { mode = 'fallback'; reason = 'semantic_pin_mismatch'; } if (mode === 'fallback' && (!local.modes.fallback.supported || !peer.modes.fallback.supported)) error('required fallback is disabled', 'NEGOTIATION');
  const ours = repMap(local), theirs = repMap(peer); let candidates = mode === 'fallback' ? local.modes.fallback.order.filter((id) => peer.modes.fallback.order.includes(id)) : [REPRESENTATIONS.JSON, REPRESENTATIONS.TERSE]; if (!compatible) candidates = candidates.filter((id) => id === REPRESENTATIONS.JSON); if (!canUseControlledEnglish(canonical)) candidates = candidates.filter((id) => id !== REPRESENTATIONS.TERSE);
  const eligible = candidates.filter((id) => { const a = ours.get(id), b = theirs.get(id); return a && b && !a.relay_only && !b.relay_only && a.can_encode && a.can_decode && b.can_encode && b.can_decode; });
  if (!eligible.length) error('no mutually endpoint-decodable safe representation', 'NEGOTIATION'); const selected = preferredRepresentation === undefined ? eligible[0] : preferredRepresentation; if (!eligible.includes(selected)) error('preferred representation is not eligible', 'NEGOTIATION');
  return { mode, representation: selected, local_source_id: local.pins.source_id, peer_source_id: peer.pins.source_id, peer_language_version: peer.semantics.language_version, peer_capsule_sha256: peer.semantics.capsule_sha256, pins_compatible: compatible, fallback_reason: reason };
}
function pinsFor(cap, representationId) { const pins = { language_version: LANGUAGE_VERSION, capsule_sha256: CAPSULE_SHA256, source_id: cap.pins.source_id }; if (representationId === REPRESENTATIONS.WIRE_V02) Object.assign(pins, { profile_id: PROFILE_ID, profile_capsule_sha256: PROFILE_CAPSULE_SHA256, dictionary_id: PROFILE_DICTIONARY_ID }); return pins; }
function makeDelivery(cap, mode, rep, raw, data, encoding, status, reason) { return { format: DELIVERY_FORMAT, interface_version: INTERFACE_VERSION, product_label: PRODUCT_LABEL, mode, representation: rep, pins: pinsFor(cap, rep), payload: { encoding, data, sha256: sha256(raw) }, safety: { effect_authorized: false, semantic_status: status, fallback_reason: reason } }; }
function encodeDelivery(message, { capability, peerCapability, requestedMode = 'bridge', preferredRepresentation } = {}) {
  const local = validateCapabilities(capability), canonical = normalizeMessage(message); let session;
  if (peerCapability) session = negotiate(local, peerCapability, canonical, { requestedMode, preferredRepresentation }); else session = { mode: 'fallback', representation: REPRESENTATIONS.JSON, pins_compatible: false, fallback_reason: 'peer_capability_unavailable' };
  const status = session.pins_compatible ? 'canonical-locally-validated' : 'opaque-fallback-only';
  if (session.representation === REPRESENTATIONS.TERSE) { const text = encodeControlledEnglish(canonical); return makeDelivery(local, session.mode, session.representation, Buffer.from(text), text, 'utf-8-controlled-english', status, session.fallback_reason); }
  const text = canonicalJson(canonical); return makeDelivery(local, session.mode, REPRESENTATIONS.JSON, Buffer.from(text), text, 'utf-8-json', status, session.fallback_reason);
}

function readVarint(buffer, start) { let value = 0, shift = 0, pos = start; while (pos < buffer.length && shift <= 63) { const byte = buffer[pos++]; value += (byte & 127) * (2 ** shift); if (!Number.isSafeInteger(value)) error('unsafe frame varint', 'WIRE'); if (!(byte & 128)) { const encoded = []; let n = value; while (n >= 128) { encoded.push((n & 127) | 128); n = Math.floor(n / 128); } encoded.push(n); if (!Buffer.from(encoded).equals(buffer.subarray(start, pos))) error('non-canonical frame varint', 'WIRE'); return [value, pos]; } shift += 7; } error('truncated frame varint', 'WIRE'); }
function decodeBase64(text) { if (typeof text !== 'string' || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(text)) error('invalid Base64', 'WIRE'); const raw = Buffer.from(text, 'base64'); if (raw.toString('base64') !== text || raw.length > MAX_DELIVERY_BYTES) error('non-canonical or oversized Base64', 'WIRE'); return raw; }
function inspectWire(raw, representationId) {
  if (raw.length < 23 || raw.subarray(0, 4).toString('ascii') !== 'URSL' || raw[5] !== 1) error('unsupported wire header', 'WIRE'); const version = raw[4]; if ((representationId === REPRESENTATIONS.WIRE_V01 && version !== 1) || (representationId === REPRESENTATIONS.WIRE_V02 && version !== 2)) error('wire version differs from representation', 'WIRE'); let pos = 6, profileId = null, dictionaryId = null;
  if (version === 2) { [profileId, pos] = readVarint(raw, pos); dictionaryId = raw.subarray(pos, pos + 8).toString('hex'); pos += 8; if (profileId !== PROFILE_ID || dictionaryId !== PROFILE_DICTIONARY_ID) error('v0.2 profile pins differ', 'WIRE'); }
  let length; [length, pos] = readVarint(raw, pos); const end = pos + length; if (end + 16 !== raw.length) error('wire payload length differs', 'WIRE'); const hash = crypto.createHash('sha256'); if (version === 2) hash.update(Buffer.from('UrusillaWire-v0.2-frame\0')); hash.update(raw.subarray(0, end)); if (!crypto.timingSafeEqual(hash.digest().subarray(0, 16), raw.subarray(end))) error('wire checksum mismatch', 'WIRE'); return { version: `0.${version}`, profile_id: profileId, dictionary_id: dictionaryId, sha256: sha256(raw), checksum_verified: true, semantic_decoded: false };
}
function relayOpaque({ capability, peerCapability, delivery }) {
  const local = validateCapabilities(capability), peer = validateCapabilities(peerCapability); if (!isObject(delivery) || !COMPACT_IDS.has(delivery.representation)) error('relay requires an exact compact delivery', 'RELAY'); const id = delivery.representation, a = repMap(local).get(id), b = repMap(peer).get(id); if (!a || !b || !a.relay_only || a.can_encode || a.can_decode || (!b.can_decode && !b.relay_only)) error('Node compact profile must remain relay-only and the peer must decode or relay it', 'RELAY'); const required = [...new Set([...a.requires_cached_artifacts, ...b.requires_cached_artifacts])]; if (required.some((d) => !local.cached_artifacts.includes(d) || !peer.cached_artifacts.includes(d))) error('compact relay requires artifacts cached by both peers', 'RELAY'); if (local.semantics.language_version !== peer.semantics.language_version || local.semantics.capsule_sha256 !== peer.semantics.capsule_sha256) error('compact relay semantic pins differ', 'RELAY'); decodeDelivery(delivery, { expectedSourceId: delivery.pins.source_id, capability: local }); return JSON.parse(canonicalJson(delivery));
}
function decodeDelivery(delivery, { expectedSourceId, capability, session } = {}) {
  const top = ['format', 'interface_version', 'mode', 'payload', 'pins', 'product_label', 'representation', 'safety'];
  if (!isObject(delivery) || canonicalJson(Object.keys(delivery).sort(compareText)) !== canonicalJson(top) || delivery.format !== DELIVERY_FORMAT || delivery.interface_version !== INTERFACE_VERSION || delivery.product_label !== PRODUCT_LABEL || Buffer.byteLength(canonicalJson(delivery)) > MAX_DELIVERY_BYTES) error('unsupported or open delivery format', 'DELIVERY'); if (!MODES.has(delivery.mode) || !REP_IDS.includes(delivery.representation)) error('unknown delivery mode or representation', 'DELIVERY');
  if (session && (delivery.mode !== session.mode || delivery.representation !== session.representation)) error('delivery differs from negotiated session', 'DELIVERY');
  const pins = delivery.pins; const pinFields = delivery.representation === REPRESENTATIONS.WIRE_V02 ? ['capsule_sha256', 'dictionary_id', 'language_version', 'profile_capsule_sha256', 'profile_id', 'source_id'] : ['capsule_sha256', 'language_version', 'source_id']; if (!isObject(pins) || canonicalJson(Object.keys(pins).sort(compareText)) !== canonicalJson(pinFields)) error('delivery pin fields differ', 'DELIVERY');
  const expectedSource = session ? session.peer_source_id : expectedSourceId; const expectedLanguage = session ? session.peer_language_version : LANGUAGE_VERSION; const expectedCapsule = session ? session.peer_capsule_sha256 : CAPSULE_SHA256; if (pins.language_version !== expectedLanguage || pins.capsule_sha256 !== expectedCapsule || pins.source_id !== requireSource(expectedSource, 'expectedSourceId')) error('delivery semantic or source pin mismatch', 'DELIVERY');
  const compatible = session ? session.pins_compatible : pins.language_version === LANGUAGE_VERSION && pins.capsule_sha256 === CAPSULE_SHA256; const expectedStatus = compatible ? 'canonical-locally-validated' : 'opaque-fallback-only'; const expectedReason = session ? session.fallback_reason : delivery.safety && delivery.safety.fallback_reason;
  if (!isObject(delivery.safety) || canonicalJson(Object.keys(delivery.safety).sort(compareText)) !== canonicalJson(['effect_authorized', 'fallback_reason', 'semantic_status']) || delivery.safety.effect_authorized !== false || delivery.safety.semantic_status !== expectedStatus || delivery.safety.fallback_reason !== expectedReason) error('delivery safety fields differ or authorize effects', 'DELIVERY'); const payload = delivery.payload; if (!isObject(payload) || canonicalJson(Object.keys(payload).sort(compareText)) !== canonicalJson(['data', 'encoding', 'sha256']) || typeof payload.data !== 'string' || !SHA_RE.test(payload.sha256)) error('invalid delivery payload', 'DELIVERY');
  let raw; if (COMPACT_IDS.has(delivery.representation)) { if (payload.encoding !== 'base64') error('wire delivery must use Base64', 'DELIVERY'); raw = decodeBase64(payload.data); if (!capability) error('compact relay verification requires local capability cache', 'DELIVERY'); const local = validateCapabilities(capability), rep = repMap(local).get(delivery.representation); if (!rep || !rep.relay_only || rep.requires_cached_artifacts.some((d) => !local.cached_artifacts.includes(d))) error('compact profile is not fully cached for relay', 'DELIVERY'); if (delivery.representation === REPRESENTATIONS.WIRE_V02 && (pins.profile_id !== PROFILE_ID || pins.profile_capsule_sha256 !== PROFILE_CAPSULE_SHA256 || pins.dictionary_id !== PROFILE_DICTIONARY_ID)) error('delivery v0.2 profile pins differ', 'DELIVERY'); inspectWire(raw, delivery.representation); } else { const expectedEncoding = delivery.representation === REPRESENTATIONS.JSON ? 'utf-8-json' : 'utf-8-controlled-english'; if (payload.encoding !== expectedEncoding) error('delivery text encoding differs', 'DELIVERY'); raw = Buffer.from(payload.data); }
  if (sha256(raw) !== payload.sha256) error('delivery payload digest mismatch', 'DELIVERY'); if (COMPACT_IDS.has(delivery.representation)) return { message: null, opaque_payload: payload.data, mode: delivery.mode, representation: delivery.representation, source_id: pins.source_id, semantic_valid: false, effect_authorized: false };
  if (!compatible) { if (delivery.representation !== REPRESENTATIONS.JSON) error('pin mismatch fallback must be JSON', 'DELIVERY'); return { message: null, opaque_payload: parseCanonicalJson(payload.data), mode: delivery.mode, representation: delivery.representation, source_id: pins.source_id, semantic_valid: false, effect_authorized: false }; }
  const message = delivery.representation === REPRESENTATIONS.JSON ? normalizeMessage(parseCanonicalJson(payload.data)) : decodeControlledEnglish(payload.data); return { message, opaque_payload: null, mode: delivery.mode, representation: delivery.representation, source_id: pins.source_id, semantic_valid: true, effect_authorized: false };
}
function estimateDeliveryAccounting(delivery, peerCapability) { const peer = validateCapabilities(peerCapability), rep = repMap(peer).get(delivery.representation); const missing = rep ? rep.requires_cached_artifacts.filter((d) => !peer.cached_artifacts.includes(d)) : []; const sizes = { [CAPSULE_SHA256]: CAPSULE_BYTES, [PROFILE_CAPSULE_SHA256]: 1402 }; const planned = missing.reduce((sum, d) => sum + (sizes[d] || 0), 0); const envelope = Buffer.byteLength(canonicalJson(delivery)); return { classification: 'plan_only_no_transfer_or_cache_mutation', envelope_bytes: envelope, planned_artifact_bytes: planned, estimated_first_delivery_bytes: envelope + planned, acknowledged_cache_hits: rep ? rep.requires_cached_artifacts.length - missing.length : 0, planned_cache_misses: missing.length }; }
function encodeJsonLine(value) { return `${canonicalJson(value)}\n`; }
function decodeJsonLine(line) { if (typeof line !== 'string') error('JSONL input must be text', 'JSONL'); const text = line.endsWith('\n') ? line.slice(0, -1) : line; if (!text || text.includes('\n') || text.endsWith('\r')) error('one LF-terminated canonical JSON line is required', 'JSONL'); return parseCanonicalJson(text); }
function toA2AMessage(delivery, messageId, role = 'ROLE_AGENT') { if (!['ROLE_USER', 'ROLE_AGENT'].includes(role) || typeof messageId !== 'string' || !messageId) error('invalid A2A role or messageId', 'A2A'); return { role, parts: [{ data: { urusilla_delivery: delivery } }], messageId, extensions: [A2A_LOCAL_EXTENSION], metadata: { [A2A_LOCAL_EXTENSION]: { source_id: delivery.pins.source_id, status: 'private-local-experimental' } } }; }
function fromA2AMessage(wrapper, options) { const top = ['extensions', 'messageId', 'metadata', 'parts', 'role']; if (!isObject(wrapper) || canonicalJson(Object.keys(wrapper).sort(compareText)) !== canonicalJson(top) || !['ROLE_USER', 'ROLE_AGENT'].includes(wrapper.role) || typeof wrapper.messageId !== 'string' || !wrapper.messageId || !Array.isArray(wrapper.parts) || wrapper.parts.length !== 1 || !isObject(wrapper.parts[0]) || !isObject(wrapper.parts[0].data) || !isObject(wrapper.parts[0].data.urusilla_delivery) || !Array.isArray(options.activatedExtensions) || !options.activatedExtensions.includes(A2A_LOCAL_EXTENSION) || options.a2aVersion !== '1.0') error('A2A local extension was not explicitly activated or shape is open', 'A2A'); const decoded = decodeDelivery(wrapper.parts[0].data.urusilla_delivery, options); const id = decoded.message ? decoded.message.id : decoded.opaque_payload && decoded.opaque_payload.id; if (typeof id === 'string' && wrapper.messageId !== id) error('A2A messageId differs from delivery message id', 'A2A'); return decoded; }
function toMcpResult(delivery) { const opaque = delivery.safety.semantic_status === 'opaque-fallback-only'; return { content: [{ type: 'text', text: opaque ? 'Opaque structured fallback; semantic pins differ and no authority is granted.' : 'Locally validated semantic delivery; no authority is granted.' }], structuredContent: { urusilla_delivery: delivery }, isError: false }; }
function fromMcpResult(result, options) { if (!isObject(result) || result.isError !== false || !Array.isArray(result.content) || result.content.length !== 1 || !isObject(result.structuredContent) || !isObject(result.structuredContent.urusilla_delivery)) error('invalid MCP-friendly result', 'MCP'); return decodeDelivery(result.structuredContent.urusilla_delivery, options); }

module.exports = Object.freeze({ PRODUCT_LABEL, INTERFACE_VERSION, CAPABILITY_FORMAT, DELIVERY_FORMAT, LANGUAGE_VERSION, RELEASE_STATUS, CAPSULE_SHA256, CAPSULE_BYTES, CAPSULE_BOUND_REFERENCE_SHA256, OBSERVED_REFERENCE_SHA256, PROFILE_CAPSULE_SHA256, PROFILE_DICTIONARY_ID, PROFILE_ID, A2A_LOCAL_EXTENSION, REPRESENTATIONS, IntegrationError, canonicalJson, parseCanonicalJson, sha256, normalizeMessage, canUseControlledEnglish, encodeControlledEnglish, decodeControlledEnglish, createCapabilities, validateCapabilities, negotiate, encodeDelivery, decodeDelivery, relayOpaque, inspectWire, estimateDeliveryAccounting, encodeJsonLine, decodeJsonLine, toA2AMessage, fromA2AMessage, toMcpResult, fromMcpResult });
