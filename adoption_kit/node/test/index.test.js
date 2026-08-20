'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const kit = require('../src/index.js');

const ROOT = path.resolve(__dirname, '..', '..');
const REPOSITORY_ROOT = path.resolve(ROOT, '..');
const SOURCE_A = '11111111111111111111111111111111';
const SOURCE_B = '22222222222222222222222222222222';
const WIRE_V01_BASE64 = 'VVJTTAEBxQEKBGtpbmQEZ29hbAVjbGFpbQlhcmd1bWVudHMJY29uZGl0aW9uCXByZWRpY2F0ZQ51cm46YWdlbnQ6YmV0YQ91cm46YWdlbnQ6YWxwaGEWdXJuOmV4YW1wbGU6c3VtLWVxdWFscxx1cm46dXJ1c2lsbGE6c2NoZW1hOmNvcmU6MC4xAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAQEHAQYCAAkBAAA4CQIECQMDCAMDAgMDAwUABgIFBggABgEJAFjdyWIjWtz3tsYJIbMIJ+A=';

function fixture(name = 'request.json') {
  return JSON.parse(fs.readFileSync(path.join(ROOT, 'fixtures', name), 'utf8'));
}

function capability(sourceId, cachedArtifacts = []) {
  return kit.createCapabilities({ sourceId, cachedArtifacts });
}

test('discovery separates bridge/native/fallback and compact is relay-only', () => {
  const offer = capability(SOURCE_A);
  const capsuleBytes = fs.readFileSync(path.join(REPOSITORY_ROOT, 'urusilla_capsule_v0_1.json'));
  const capsule = JSON.parse(capsuleBytes);
  assert.equal(capsuleBytes.length, kit.CAPSULE_BYTES);
  assert.equal(kit.sha256(capsuleBytes), kit.CAPSULE_SHA256);
  assert.equal(kit.RELEASE_STATUS, 'experimental-unsigned');
  assert.equal(capsule.release_status, kit.RELEASE_STATUS);
  assert.equal(capsule.publisher_authentication.status, 'unsigned');
  assert.match(capsule.security_contract.unsigned_restriction, /local read-only/);
  assert.match(capsule.security_contract.unsigned_restriction, /MUST NOT authorize external side effects/);
  assert.match(capsule.github_distribution.publication_modes.trusted_effect_authorizing, /accepted publisher signature/);
  assert.match(capsule.github_distribution.publication_modes.trusted_effect_authorizing, /authorization policy/);
  assert.equal(offer.lifecycle, kit.RELEASE_STATUS);
  assert.equal(offer.semantics.release_status, kit.RELEASE_STATUS);
  assert.equal(offer.safety.unsigned_operation_read_only, true);
  const retiredLifecycle = structuredClone(offer);
  retiredLifecycle.lifecycle = 'experimental-unsigned-invalid';
  assert.throws(() => kit.validateCapabilities(retiredLifecycle), /capability format/);
  const retiredSemanticStatus = structuredClone(offer);
  retiredSemanticStatus.semantics.release_status = 'experimental-unsigned-invalid';
  assert.throws(() => kit.validateCapabilities(retiredSemanticStatus), /capability semantics/);
  assert.equal(offer.modes.bridge.supported, true);
  assert.equal(offer.modes.native.supported, false);
  assert.equal(offer.modes.native.verified, false);
  assert.equal(offer.modes.fallback.supported, true);
  assert.equal(offer.provenance.support_claim_eligible, false);
  assert.equal(offer.provenance.reference_codec_matches_capsule, true);
  assert.equal(offer.safety.effect_authorization, false);
  for (const rep of offer.representations.filter((item) => item.id.startsWith('urusilla-wire-'))) {
    assert.equal(rep.relay_only, true);
    assert.equal(rep.can_encode, false);
    assert.equal(rep.can_decode, false);
  }
});

test('frozen JSON has code-point ordering and rejects unsafe numeric/surrogate values', () => {
  assert.equal(kit.canonicalJson({ '😀': 1, '\ue000': 2, a: 3 }), '{"a":3,"\ue000":2,"😀":1}');
  for (const value of [0.125, 2 ** 53, '\ud800']) {
    assert.throws(() => kit.canonicalJson({ value }), kit.IntegrationError);
  }
  const cyclic = []; cyclic.push(cyclic);
  assert.throws(() => kit.canonicalJson(cyclic), /acyclic/);
});

test('JSON and controlled terse English round-trip the canonical fixture', () => {
  const message = fixture();
  assert.deepEqual(kit.decodeControlledEnglish(kit.encodeControlledEnglish(message)), kit.normalizeMessage(message));
  const a = capability(SOURCE_A), b = capability(SOURCE_B);
  const delivery = kit.encodeDelivery(message, { capability: a, peerCapability: b, preferredRepresentation: kit.REPRESENTATIONS.JSON });
  const decoded = kit.decodeDelivery(delivery, { expectedSourceId: SOURCE_A });
  assert.deepEqual(decoded.message, kit.normalizeMessage(message));
  assert.equal(decoded.source_id, SOURCE_A);
  assert.equal(decoded.effect_authorized, false);
});

test('native safely falls back and peer fallback disablement fails closed', () => {
  const a = capability(SOURCE_A), b = capability(SOURCE_B);
  const session = kit.negotiate(a, b, fixture(), { requestedMode: 'native' });
  assert.equal(session.mode, 'fallback');
  assert.equal(session.fallback_reason, 'native_evidence_unavailable');
  b.modes.fallback.supported = false;
  assert.throws(() => kit.negotiate(a, b, fixture(), { requestedMode: 'native' }), /fallback is disabled/);
});

test('delivery rejects authority-looking fields and damage', () => {
  const a = capability(SOURCE_A), b = capability(SOURCE_B);
  const delivery = kit.encodeDelivery(fixture(), { capability: a, peerCapability: b });
  const extra = structuredClone(delivery); extra.pins.authority = 'admin';
  assert.throws(() => kit.decodeDelivery(extra, { expectedSourceId: SOURCE_A }), /pin fields/);
  const damaged = structuredClone(delivery); damaged.payload.data += ' ';
  assert.throws(() => kit.decodeDelivery(damaged, { expectedSourceId: SOURCE_A }), /digest mismatch/);
});

test('A2A-shaped and MCP-friendly wrappers preserve the same delivery', () => {
  const a = capability(SOURCE_A), b = capability(SOURCE_B);
  const delivery = kit.encodeDelivery(fixture(), { capability: a, peerCapability: b });
  const wrapper = kit.toA2AMessage(delivery, fixture().id, 'ROLE_USER');
  const decoded = kit.fromA2AMessage(wrapper, { expectedSourceId: SOURCE_A, activatedExtensions: [kit.A2A_LOCAL_EXTENSION], a2aVersion: '1.0' });
  assert.equal(decoded.message.id, fixture().id);
  const result = kit.toMcpResult(delivery);
  assert.equal(kit.fromMcpResult(result, { expectedSourceId: SOURCE_A }).message.id, fixture().id);
});

test('compact relay preserves origin source and exact delivery bytes', () => {
  const cached = [kit.CAPSULE_SHA256, kit.PROFILE_CAPSULE_SHA256];
  const local = capability(SOURCE_B, cached), peer = capability('33333333333333333333333333333333', cached);
  const raw = Buffer.from(WIRE_V01_BASE64, 'base64');
  const delivery = {
    format: kit.DELIVERY_FORMAT,
    interface_version: kit.INTERFACE_VERSION,
    product_label: kit.PRODUCT_LABEL,
    mode: 'bridge',
    representation: kit.REPRESENTATIONS.WIRE_V01,
    pins: { language_version: kit.LANGUAGE_VERSION, capsule_sha256: kit.CAPSULE_SHA256, source_id: SOURCE_A },
    payload: { encoding: 'base64', data: WIRE_V01_BASE64, sha256: kit.sha256(raw) },
    safety: { effect_authorized: false, semantic_status: 'canonical-locally-validated', fallback_reason: null },
  };
  const relayed = kit.relayOpaque({ capability: local, peerCapability: peer, delivery });
  assert.equal(relayed.pins.source_id, SOURCE_A);
  assert.equal(kit.canonicalJson(relayed), kit.canonicalJson(delivery));
});

test('accounting helper is explicitly planning-only', () => {
  const a = capability(SOURCE_A), b = capability(SOURCE_B);
  const before = kit.canonicalJson(b);
  const delivery = kit.encodeDelivery(fixture(), { capability: a, peerCapability: b });
  const estimate = kit.estimateDeliveryAccounting(delivery, b);
  assert.equal(estimate.classification, 'plan_only_no_transfer_or_cache_mutation');
  assert.equal(estimate.planned_artifact_bytes, kit.CAPSULE_BYTES);
  assert.equal(kit.canonicalJson(b), before);
});

test('JSONL agent performs local discovery without sockets', () => {
  const request = kit.encodeJsonLine({ op: 'discover', source_id: SOURCE_A });
  const run = spawnSync(process.execPath, [path.join(ROOT, 'node', 'src', 'agent.js')], { input: request, encoding: 'utf8' });
  assert.equal(run.status, 0);
  const response = kit.decodeJsonLine(run.stdout);
  assert.equal(response.ok, true);
  assert.equal(response.result.pins.source_id, SOURCE_A);
  assert.equal(response.result.safety.network_io, false);
});
