import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  loadCrossplayVectors,
  loadFrozenProfile,
  loadFrozenRegistry,
} from "../src/frozen_inputs.mjs";
import { fromFixtureJson } from "../src/portable_json.mjs";
import { normalizeMessage } from "../src/semantic.mjs";
import {
  decodeCapsule,
  decodeMessage,
  encodeCapsule,
  encodeMessage,
  profileDictionaryId,
  sha256Hex,
} from "../src/wire_v02.mjs";

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

test("the frozen profile capsule has the published identity and round-trips", () => {
  const vectors = loadCrossplayVectors();
  const capsule = Buffer.from(vectors.profile.capsule_base64, "base64");
  const profile = decodeCapsule(capsule);

  assert.equal(capsule.length, vectors.profile.capsule_bytes);
  assert.equal(sha256Hex(capsule), vectors.profile.capsule_sha256);
  assert.deepEqual(capsule.subarray(0, 5), Buffer.from("URCP\x02", "latin1"));
  assert.equal(profile.profileId, 1);
  assert.equal(profile.name, "urusilla-core-benchmark-static-v1");
  assert.equal(profile.strings.length, 109);
  assert.equal(profile.shapes.length, 19);
  assert.equal(profileDictionaryId(profile).toString("hex"), vectors.profile.dictionary_id_hex);
  assert.deepEqual(encodeCapsule(profile), capsule);
});

test("all 280 project-frozen frames cross-play byte exactly in both directions", () => {
  const vectors = loadCrossplayVectors();
  const profile = loadFrozenProfile();
  const registry = loadFrozenRegistry();
  const sequence = [];
  let totalBytes = 0;

  for (const vector of vectors.golden) {
    const source = fromFixtureJson(vector.message);
    const expectedFrame = Buffer.from(vector.frame_base64, "base64");
    const encoded = encodeMessage(source, profile);
    assert.deepEqual(encoded, expectedFrame, `${vector.id}: encoder bytes`);
    assert.equal(encoded.length, vector.frame_bytes, `${vector.id}: frame length`);
    assert.equal(sha256(encoded), vector.frame_sha256, `${vector.id}: frame digest`);

    const decoded = decodeMessage(expectedFrame, registry);
    assert.deepEqual(decoded, normalizeMessage(source), `${vector.id}: semantic decode`);
    assert.deepEqual(encodeMessage(decoded, profile), expectedFrame, `${vector.id}: re-encode`);

    const length = Buffer.alloc(4);
    length.writeUInt32BE(encoded.length);
    sequence.push(length, encoded);
    totalBytes += encoded.length;
  }

  assert.equal(vectors.golden.length, 280);
  assert.equal(totalBytes, 54_752);
  const stream = Buffer.concat(sequence);
  assert.equal(stream.length, 55_872);
  assert.equal(
    sha256(stream),
    vectors.aggregates.four_byte_length_prefixed_frame_sequence_sha256,
  );
  assert.equal(
    sha256(stream),
    vectors.aggregates.four_byte_length_prefixed_frame_sequence_sha256,
  );
});

test("the public semantic input retains its exact Python-oracle v0.1 wire artifact", () => {
  const publicVectors = JSON.parse(
    readFileSync(new URL("../vectors/public_v01_semantic_vectors.json", import.meta.url), "utf8"),
  );
  const vector = publicVectors.positive_vectors[0];
  const v01Frame = Buffer.from(vector.wire_base64, "base64");
  assert.equal(v01Frame.length, vector.wire_bytes);
  assert.equal(sha256(v01Frame), vector.wire_sha256);
  assert.deepEqual(v01Frame.subarray(0, 5), Buffer.from("URSL\x01", "latin1"));

  // This lane does not implement v0.1 wire decoding. It independently checks
  // that the same semantic input cross-plays under the frozen v0.2 profile.
  const v02Frame = encodeMessage(vector.input, loadFrozenProfile());
  assert.equal(decodeMessage(v02Frame, loadFrozenRegistry()).act, "REQUEST");
});

test("map insertion order cannot alter canonical frame bytes", () => {
  const vectors = loadCrossplayVectors();
  const profile = loadFrozenProfile();
  const source = fromFixtureJson(vectors.golden[3].message);
  const reversed = Object.fromEntries(Object.entries(source).reverse());
  reversed.body = Object.fromEntries(Object.entries(source.body).reverse());
  reversed.meta = Object.fromEntries(Object.entries(source.meta).reverse());
  assert.deepEqual(encodeMessage(reversed, profile), encodeMessage(source, profile));
});
