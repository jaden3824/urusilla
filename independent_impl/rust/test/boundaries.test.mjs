import assert from "node:assert/strict";
import test from "node:test";

import { DecodeError, ValidationError } from "../src/errors.mjs";
import { loadCrossplayVectors, loadFrozenProfile, loadFrozenRegistry } from "../src/frozen_inputs.mjs";
import {
  fromFixtureJson,
  fromPortableJson,
  parsePortableJson,
  stringifyPortableJson,
  toPortableJson,
} from "../src/portable_json.mjs";
import { Float64, INTEGER_LIMITS, LIMITS, normalizeMessage } from "../src/semantic.mjs";
import {
  FLAGS,
  MAGIC,
  ProfileRegistry,
  TAGS,
  decodeCapsule,
  decodeMessage,
  encodeCapsule,
  encodeMessage,
  encodeString,
  encodeSvarint,
  encodeUvarint,
  profileDictionaryId,
  recomputeFrameChecksum,
  validateProfile,
} from "../src/wire_v02.mjs";

test("uvarint and zigzag cover exact 64-bit boundaries", () => {
  assert.deepEqual(encodeUvarint(0), Buffer.from([0]));
  assert.deepEqual(encodeUvarint(127), Buffer.from([127]));
  assert.deepEqual(encodeUvarint(128), Buffer.from([128, 1]));
  assert.equal(encodeUvarint(INTEGER_LIMITS.MAX_UINT64).length, 10);
  assert.equal(encodeSvarint(INTEGER_LIMITS.MIN_INT64).length, 10);
  assert.throws(() => encodeUvarint(-1), ValidationError);
  assert.throws(() => encodeUvarint(INTEGER_LIMITS.MAX_UINT64 + 1n), ValidationError);
});

test("generic values preserve uint64, int64, bytes, and typed Float64", () => {
  const profile = loadFrozenProfile();
  const registry = loadFrozenRegistry();
  const source = fromFixtureJson(loadCrossplayVectors().golden[0].message);
  source.reply_to = null;
  source.body = {
    kind: "x:numeric-boundary",
    values: [
      INTEGER_LIMITS.MIN_INT64,
      INTEGER_LIMITS.MAX_UINT64,
      Buffer.from([0, 255]),
      new Float64(0),
      new Float64(1.25),
    ],
  };
  const decoded = decodeMessage(encodeMessage(source, profile), registry);
  assert.equal(decoded.body.values[0], INTEGER_LIMITS.MIN_INT64);
  assert.equal(decoded.body.values[1], INTEGER_LIMITS.MAX_UINT64);
  assert.deepEqual(decoded.body.values[2], Buffer.from([0, 255]));
  assert.equal(decoded.body.values[3].value, 0);
  assert.equal(decoded.body.values[4].value, 1.25);
});

test("safe BigInt inputs normalize to the canonical safe Number representation", () => {
  const source = fromFixtureJson(loadCrossplayVectors().golden[0].message);
  source.logical_clock = 1n;
  source.body.annotations = { small_integer: 7n };
  const canonical = normalizeMessage(source);
  assert.equal(canonical.logical_clock, 1);
  assert.equal(typeof canonical.logical_clock, "number");
  assert.equal(canonical.body.annotations.small_integer, 7);
  assert.equal(typeof canonical.body.annotations.small_integer, "number");
  assert.deepEqual(
    decodeMessage(encodeMessage(source, loadFrozenProfile()), loadFrozenRegistry()),
    canonical,
  );
});

test("fully tagged portable JSON is bijective for adversarial semantic map keys", () => {
  const source = Object.create(null);
  source.__proto__ = "literal proto key";
  source.$urusilla_bigint = "literal wrapper-looking key";
  source.$urusilla_float64_be = INTEGER_LIMITS.MAX_UINT64;
  source.$urusilla_bytes_base64 = Buffer.from([0, 255]);
  source.safe = new Float64(1.25);

  const projection = toPortableJson(source);
  const roundTrip = fromPortableJson(JSON.parse(stringifyPortableJson(source)));
  assert.deepEqual(roundTrip, source);
  assert.equal(projection.$urusilla_type, "map");
  assert.ok(Object.hasOwn(roundTrip, "__proto__"));
  assert.throws(
    () =>
      fromPortableJson({
        $urusilla_type: "map",
        entries: [
          ["duplicate", { $urusilla_type: "null" }],
          ["duplicate", { $urusilla_type: "null" }],
        ],
      }),
    ValidationError,
  );
});

test("portable JSON enforces depth before recursive conversion", () => {
  let projected = { $urusilla_type: "null" };
  let semantic = null;
  for (let index = 0; index < LIMITS.maxDepth + 2; index += 1) {
    projected = { $urusilla_type: "list", items: [projected] };
    semantic = [semantic];
  }
  assert.throws(
    () => fromPortableJson(projected),
    (error) => error instanceof ValidationError && error.code === "depth_limit",
  );
  assert.throws(
    () => stringifyPortableJson(semantic),
    (error) => error instanceof ValidationError && error.code === "depth_limit",
  );
});

test("portable projection preserves a wire-valid exact-depth message", () => {
  const profile = loadFrozenProfile();
  const source = fromFixtureJson(loadCrossplayVectors().golden[0].message);
  source.act = "ASSERT";
  source.reply_to = null;
  let nested = null;
  for (let index = 0; index < LIMITS.maxDepth - 1; index += 1) nested = [nested];
  source.body = { kind: "x:depth-boundary", value: nested };
  source.meta = {};
  const frame = encodeMessage(source, profile);
  const decoded = decodeMessage(frame, loadFrozenRegistry());
  const reparsed = parsePortableJson(stringifyPortableJson(decoded));
  assert.deepEqual(encodeMessage(reparsed, profile), frame);
});

test("portable document limit accommodates expansion beyond the wire-frame limit", () => {
  const profile = loadFrozenProfile();
  const source = fromFixtureJson(loadCrossplayVectors().golden[0].message);
  source.act = "ASSERT";
  source.reply_to = null;
  source.body = {
    kind: "x:portable-expansion",
    blob: Buffer.alloc(12 * 1024 * 1024, 0xab),
  };
  source.meta = {};
  const frame = encodeMessage(source, profile);
  assert.ok(frame.length < LIMITS.maxFrameBytes);
  const portable = stringifyPortableJson(decodeMessage(frame, loadFrozenRegistry()), 0);
  assert.ok(Buffer.byteLength(portable) > LIMITS.maxFrameBytes);
  assert.ok(Buffer.byteLength(portable) < LIMITS.maxPortableJsonBytes);
  assert.deepEqual(encodeMessage(parsePortableJson(portable), profile), frame);
});

test("portable JSON rejects noncanonical numeric aliases and invalid output text", () => {
  assert.throws(
    () => fromPortableJson({ $urusilla_type: "integer", value: "-0" }),
    ValidationError,
  );
  assert.throws(
    () => fromPortableJson({ $urusilla_type: "float64", bits: "8000000000000000" }),
    ValidationError,
  );
  assert.throws(() => stringifyPortableJson("\ud800"), ValidationError);
  assert.throws(() => toPortableJson(1n), /canonical Number/);
});

test("semantic depth, string size, and collection caps reject before encoding", () => {
  const profile = loadFrozenProfile();
  const base = fromFixtureJson(loadCrossplayVectors().golden[0].message);
  base.reply_to = null;
  base.body = { kind: "x:limit", value: "x".repeat(LIMITS.maxStringBytes + 1) };
  assert.throws(() => encodeMessage(base, profile), /size limit/);

  base.body = { kind: "x:limit", value: new Array(LIMITS.maxCollectionItems + 1).fill(null) };
  assert.throws(() => encodeMessage(base, profile), /list exceeds/);

  let nested = null;
  for (let index = 0; index < LIMITS.maxDepth + 2; index += 1) nested = [nested];
  base.body = { kind: "x:limit", value: nested };
  assert.throws(() => encodeMessage(base, profile), /depth/);
});

test("frame and capsule global input limits are checked before parsing", () => {
  const registry = loadFrozenRegistry();
  const oversized = Buffer.alloc(LIMITS.maxFrameBytes + 1);
  assert.throws(() => decodeMessage(oversized, registry), /exceeds size limit/);
  assert.throws(() => decodeCapsule(oversized), /exceeds size limit/);
});

test("aggregate semantic node budgets bound encoder and decoder expansion", () => {
  const profile = loadFrozenProfile();
  const registry = loadFrozenRegistry();
  const source = fromFixtureJson(loadCrossplayVectors().golden[0].message);
  source.act = "ASSERT";
  source.reply_to = null;
  source.expected = [];
  source.body = {
    kind: "x:aggregate-limit",
    value: [
      new Array(100_000).fill(null),
      new Array(100_000).fill(null),
      new Array(49_994).fill(null),
    ],
  };
  source.meta = {};

  const exact = structuredClone(source);
  exact.body.value = [
    new Array(100_000).fill(null),
    new Array(100_000).fill(null),
    new Array(49_993).fill(null),
  ];
  const exactFrame = encodeMessage(exact, profile);
  const exactPortable = stringifyPortableJson(decodeMessage(exactFrame, registry), 0);
  assert.deepEqual(encodeMessage(parsePortableJson(exactPortable), profile), exactFrame);

  assert.throws(
    () => encodeMessage(source, profile),
    (error) => error instanceof ValidationError && error.code === "node_limit",
  );

  const canonical = normalizeMessage({
    ...source,
    body: { kind: "x:aggregate-limit", value: null },
  });
  const uuidBytes = (value) => Buffer.from(value.replaceAll("-", ""), "hex");
  const encodedNullList = (count) =>
    Buffer.concat([Buffer.from([TAGS.LIST]), encodeUvarint(count), Buffer.alloc(count)]);
  const aggregateList = Buffer.concat([
    Buffer.from([TAGS.LIST]),
    encodeUvarint(3),
    encodedNullList(100_000),
    encodedNullList(100_000),
    encodedNullList(49_994),
  ]);
  const body = Buffer.concat([
    Buffer.from([TAGS.MAP]),
    encodeUvarint(2),
    encodeString("kind", profile),
    encodeString("x:aggregate-limit", profile),
    encodeString("value", profile),
    aggregateList,
  ]);
  const payload = Buffer.concat([
    uuidBytes(canonical.id),
    uuidBytes(canonical.session),
    encodeString(canonical.sender, profile),
    encodeUvarint(canonical.recipients.length),
    ...canonical.recipients.map((item) => encodeString(item, profile)),
    Buffer.from([0]),
    encodeString(canonical.schema, profile),
    encodeUvarint(canonical.logical_clock),
    encodeUvarint(canonical.expires_ms),
    encodeUvarint(0),
    Buffer.from([0]),
    body,
    Buffer.from([TAGS.MAP, 0]),
  ]);
  const header = Buffer.concat([
    MAGIC,
    Buffer.from([FLAGS]),
    encodeUvarint(profile.profileId),
    profileDictionaryId(profile),
    encodeUvarint(payload.length),
  ]);
  const frame = recomputeFrameChecksum(Buffer.concat([header, payload]));
  assert.ok(frame.length < LIMITS.maxFrameBytes);
  assert.throws(
    () => decodeMessage(frame, registry),
    (error) => error instanceof DecodeError && error.code === "node_limit",
  );
});

test("profiles reject duplicates and noncanonical shapes", () => {
  assert.throws(
    () => validateProfile({ profileId: 7, name: "duplicate", strings: ["kind", "kind"], shapes: [] }),
    /duplicate/,
  );
  assert.throws(
    () => validateProfile({ profileId: 7, name: "shape", strings: ["a", "b"], shapes: [["b", "a"]] }),
    /UTF-8 sorted/,
  );
  assert.throws(
    () => validateProfile({ profileId: 7, name: "bad\ud800", strings: [], shapes: [] }),
    (error) => error instanceof ValidationError && error.code === "invalid_unicode",
  );
});

test("an explicitly registered nondefault profile cross-plays locally", () => {
  const base = loadFrozenProfile();
  const profile = validateProfile({
    profileId: 2,
    name: "cross-language-test-profile",
    strings: base.strings,
    shapes: base.shapes,
  });
  const registry = new ProfileRegistry();
  registry.registerCapsule(encodeCapsule(profile));
  const source = fromFixtureJson(loadCrossplayVectors().golden[1].message);
  const frame = encodeMessage(source, profile);
  assert.deepEqual(decodeMessage(frame, registry), normalizeMessage(source));
});

test("unknown profile and dictionary combinations fail closed", () => {
  const frame = Buffer.from(loadCrossplayVectors().golden[0].frame_base64, "base64");
  assert.throws(() => decodeMessage(frame, new ProfileRegistry()), DecodeError);
});
