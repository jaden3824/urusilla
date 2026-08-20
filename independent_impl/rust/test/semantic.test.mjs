import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

import { ValidationError } from "../src/errors.mjs";
import { LIMITS, normalizeMessage } from "../src/semantic.mjs";

const publicVectors = JSON.parse(
  readFileSync(new URL("../vectors/public_v01_semantic_vectors.json", import.meta.url), "utf8"),
);

function clone(value) {
  return structuredClone(value);
}

function setPath(target, dottedPath, value) {
  const parts = dottedPath.split(".");
  let cursor = target;
  for (const part of parts.slice(0, -1)) cursor = cursor[part];
  cursor[parts.at(-1)] = value;
}

test("the exact public v0.1 positive semantic vector normalizes canonically", () => {
  const vector = publicVectors.positive_vectors[0];
  const publishedWire = Buffer.from(vector.wire_base64, "base64");
  assert.equal(publishedWire.length, vector.wire_bytes);
  assert.equal(createHash("sha256").update(publishedWire).digest("hex"), vector.wire_sha256);
  assert.deepEqual(publishedWire.subarray(0, 5), Buffer.from("URSL\x01", "latin1"));
  const canonical = normalizeMessage(vector.input);
  assert.equal(canonical.reply_to, vector.normalized_additions.reply_to);
  assert.equal(canonical.confidence_ppm, vector.normalized_additions.confidence_ppm);
  assert.deepEqual(canonical.expected, ["PROPOSE", "COMMIT", "RESOLVE"]);
  assert.equal(canonical.body.kind, "goal");
});

test("the two precise public semantic negative mutations are rejected", () => {
  const source = publicVectors.positive_vectors[0].input;
  for (const vector of publicVectors.negative_vectors.filter((item) => item.mutations)) {
    const mutated = clone(source);
    for (const [path, value] of Object.entries(vector.mutations)) setPath(mutated, path, value);
    assert.throws(() => normalizeMessage(mutated), ValidationError, vector.id);
  }
});

test("core semantic invariants reject shadow authority and invalid commitments", () => {
  const source = clone(publicVectors.positive_vectors[0].input);
  source.authority = "admin";
  assert.throws(() => normalizeMessage(source), /unknown top-level/);

  const commit = clone(publicVectors.positive_vectors[0].input);
  commit.act = "COMMIT";
  commit.reply_to = "00000000-0000-0000-0000-000000000999";
  commit.body = {
    kind: "commitment",
    debtor: "urn:agent:someone-else",
    creditors: ["urn:agent:beta"],
    goal: clone(publicVectors.positive_vectors[0].input.body),
    expiry_ms: 10,
  };
  assert.throws(() => normalizeMessage(commit), /debtor/);
});

test("local x: extensions remain quarantined to ASSERT", () => {
  const source = clone(publicVectors.positive_vectors[0].input);
  source.body = { kind: "x:local-test", value: 7 };
  assert.throws(() => normalizeMessage(source), /quarantined/);
  source.act = "ASSERT";
  const canonical = normalizeMessage(source);
  assert.equal(canonical.body.kind, "x:local-test");

  const nested = clone(publicVectors.positive_vectors[0].input);
  nested.body.condition.arguments = [{ kind: "x:nested", value: 1 }];
  assert.throws(() => normalizeMessage(nested), /quarantined/);
});

test("explicit null or undefined cannot masquerade as an absent defaulted field", () => {
  const source = publicVectors.positive_vectors[0].input;
  for (const field of ["logical_clock", "expires_ms", "expected", "meta"]) {
    const mutated = clone(source);
    mutated[field] = null;
    assert.throws(() => normalizeMessage(mutated), ValidationError, field);
  }
  for (const field of ["reply_to", "logical_clock", "expires_ms", "confidence_ppm", "expected", "meta"]) {
    const mutated = clone(source);
    mutated[field] = undefined;
    assert.throws(() => normalizeMessage(mutated), ValidationError, field);
  }
});

test("act names are closed and case-sensitive", () => {
  const lowerAct = clone(publicVectors.positive_vectors[0].input);
  lowerAct.act = "request";
  assert.throws(() => normalizeMessage(lowerAct), /unknown communicative act/);

  const lowerExpected = clone(publicVectors.positive_vectors[0].input);
  lowerExpected.expected = ["propose"];
  assert.throws(() => normalizeMessage(lowerExpected), /unknown expected act/);
});

test("recipient and expected limits are checked before item traversal", () => {
  const recipients = clone(publicVectors.positive_vectors[0].input);
  recipients.recipients = new Array(LIMITS.maxCollectionItems + 1).fill(null);
  assert.throws(
    () => normalizeMessage(recipients),
    (error) => error instanceof ValidationError && error.code === "recipient_limit",
  );

  const expected = clone(publicVectors.positive_vectors[0].input);
  expected.expected = new Array(LIMITS.maxCollectionItems + 1).fill("NOT_AN_ACT");
  assert.throws(
    () => normalizeMessage(expected),
    (error) => error instanceof ValidationError && error.code === "collection_limit",
  );
});

test("ill-formed UTF-16 is rejected while valid astral Unicode is preserved", () => {
  for (const text of ["\ud800", "\udfff"]) {
    const mutated = clone(publicVectors.positive_vectors[0].input);
    mutated.act = "ASSERT";
    mutated.body = { kind: "x:unicode", value: text };
    assert.throws(
      () => normalizeMessage(mutated),
      (error) => error instanceof ValidationError && error.code === "invalid_unicode",
    );

    const keyed = clone(publicVectors.positive_vectors[0].input);
    keyed.act = "ASSERT";
    keyed.body = Object.assign(Object.create(null), { kind: "x:unicode", [text]: true });
    assert.throws(
      () => normalizeMessage(keyed),
      (error) => error instanceof ValidationError && error.code === "invalid_unicode",
    );
  }

  const valid = clone(publicVectors.positive_vectors[0].input);
  valid.act = "ASSERT";
  valid.body = { kind: "x:unicode", value: "astral \ud83d\ude42" };
  assert.equal(normalizeMessage(valid).body.value, "astral \ud83d\ude42");
});

test("identifier text uses Unicode White_Space semantics", () => {
  const rejected = clone(publicVectors.positive_vectors[0].input);
  rejected.sender = "agent\u0085alpha";
  assert.throws(() => normalizeMessage(rejected), /whitespace or control/);

  const accepted = clone(publicVectors.positive_vectors[0].input);
  accepted.sender = "agent\ufeffalpha";
  assert.equal(normalizeMessage(accepted).sender, "agent\ufeffalpha");
});

test("the frozen Capsule manifest digest is independently recomputed", () => {
  assert.equal(publicVectors.digest_match, true);
  assert.equal(
    publicVectors.declared_semantic_kernel_manifest_digest,
    `sha256:${publicVectors.computed_recursive_sorted_compact_manifest_sha256}`,
  );
  assert.equal(publicVectors.computed_manifest_bytes, 3681);
  assert.deepEqual(publicVectors.release_policy, {
    effect_authorizing_requires_signature_and_policy: true,
    lifecycle_status: "experimental-unsigned",
    publisher_status: "unsigned",
    unsigned_external_effects_forbidden: true,
    unsigned_operation_scope: "local-read-only",
    unsigned_public_source_distribution_allowed: true,
  });
});
