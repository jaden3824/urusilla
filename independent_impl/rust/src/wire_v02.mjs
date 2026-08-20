import { createHash, timingSafeEqual } from "node:crypto";
import {
  ACTS,
  ACT_TO_CODE,
  Float64,
  INTEGER_LIMITS,
  LIMITS,
  decodedInteger,
  integerToBigInt,
  isMap,
  normalizeMessage,
  utf8Length,
} from "./semantic.mjs";
import { DecodeError, ValidationError } from "./errors.mjs";

export const MAGIC = Buffer.from([0x55, 0x52, 0x53, 0x4c, 0x02]);
export const CAPSULE_MAGIC = Buffer.from([0x55, 0x52, 0x43, 0x50, 0x02]);
export const FLAGS = 0x01;
export const PROFILE_FORMAT = 0x01;
export const CHECKSUM_SIZE = 16;
export const DICTIONARY_ID_SIZE = 8;
export const FRAME_HASH_DOMAIN = Buffer.from("UrusillaWire-v0.2-frame\0", "utf8");
export const CAPSULE_HASH_DOMAIN = Buffer.from("UrusillaWire-v0.2-capsule\0", "utf8");

export const TAGS = Object.freeze({
  NULL: 0x00,
  FALSE: 0x01,
  TRUE: 0x02,
  UINT: 0x03,
  SINT: 0x04,
  FLOAT64: 0x05,
  BYTES: 0x06,
  LIST: 0x07,
  MAP: 0x08,
  STRING_RAW: 0x09,
  STRING_PREFIX: 0x0a,
  STRING_REF: 0x0b,
  DIRECT_STRING_BASE: 0x20,
  DIRECT_STRING_COUNT: 0x60,
  SHAPE_BASE: 0x80,
});

const UTF8_DECODER = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
const VALID_PROFILES = new WeakSet();

function sha256(...parts) {
  const hash = createHash("sha256");
  for (const part of parts) hash.update(part);
  return hash.digest();
}

export function sha256Hex(value) {
  return sha256(value).toString("hex");
}

function bytesEqual(left, right) {
  return left.length === right.length && timingSafeEqual(left, right);
}

function asBytes(value, field = "bytes") {
  if (Buffer.isBuffer(value)) return value;
  if (value instanceof Uint8Array) return Buffer.from(value);
  throw new ValidationError(`${field} must be bytes`, "bytes_type");
}

class Builder {
  constructor(limit = LIMITS.maxFrameBytes) {
    this.limit = limit;
    this.length = 0;
    this.parts = [];
  }

  append(value, error = "encoded data exceeds size limit") {
    const bytes = Buffer.isBuffer(value) ? value : Buffer.from(value);
    if (this.length + bytes.length > this.limit) {
      throw new ValidationError(error, "frame_limit");
    }
    this.parts.push(bytes);
    this.length += bytes.length;
    return this;
  }

  byte(value) {
    return this.append(Buffer.from([value]));
  }

  finish() {
    return Buffer.concat(this.parts, this.length);
  }
}

export function encodeUvarint(input) {
  let value = integerToBigInt(input, "uvarint");
  if (value < 0n || value > INTEGER_LIMITS.MAX_UINT64) {
    throw new ValidationError(`uvarint out of range: ${String(input)}`, "uvarint_range");
  }
  const output = [];
  while (value >= 0x80n) {
    output.push(Number((value & 0x7fn) | 0x80n));
    value >>= 7n;
  }
  output.push(Number(value));
  return Buffer.from(output);
}

export function encodeSvarint(input) {
  const value = integerToBigInt(input, "signed integer");
  if (value < INTEGER_LIMITS.MIN_INT64 || value > INTEGER_LIMITS.MAX_INT64) {
    throw new ValidationError("signed integer out of range", "svarint_range");
  }
  const zigzag = value >= 0n ? value * 2n : -value * 2n - 1n;
  return encodeUvarint(zigzag);
}

export class Reader {
  constructor(data) {
    if (!Buffer.isBuffer(data) && !(data instanceof Uint8Array)) {
      throw new DecodeError("reader input must be bytes", "bytes_type");
    }
    this.data = Buffer.isBuffer(data) ? data : Buffer.from(data);
    this.position = 0;
  }

  get remaining() {
    return this.data.length - this.position;
  }

  read(count) {
    if (!Number.isSafeInteger(count) || count < 0 || count > this.remaining) {
      throw new DecodeError("truncated v0.2 data", "truncated");
    }
    const start = this.position;
    this.position += count;
    return this.data.subarray(start, this.position);
  }

  byte() {
    return this.read(1)[0];
  }

  uvarint() {
    let value = 0n;
    const raw = [];
    for (let shift = 0n; shift < 70n; shift += 7n) {
      const byte = this.byte();
      raw.push(byte);
      value |= BigInt(byte & 0x7f) << shift;
      if ((byte & 0x80) === 0) {
        if (value > INTEGER_LIMITS.MAX_UINT64) {
          throw new DecodeError("uvarint overflow", "uvarint_overflow");
        }
        if (!bytesEqual(Buffer.from(raw), encodeUvarint(value))) {
          throw new DecodeError("non-canonical uvarint", "uvarint_noncanonical");
        }
        return value;
      }
    }
    throw new DecodeError("uvarint exceeds 10 bytes", "uvarint_too_long");
  }

  expectEnd() {
    if (this.remaining !== 0) {
      throw new DecodeError(
        `unexpected trailing data: ${this.remaining} byte(s)`,
        "trailing_data",
      );
    }
  }
}

function boundedNumber(value, maximum, error, code) {
  if (value > BigInt(maximum)) throw new DecodeError(error, code);
  return Number(value);
}

function decodeUtf8(bytes) {
  try {
    return UTF8_DECODER.decode(bytes);
  } catch (error) {
    throw new DecodeError("text contains invalid UTF-8", "utf8");
  }
}

function readText(reader, limit = LIMITS.maxStringBytes) {
  const size = reader.uvarint();
  if (size > BigInt(limit)) {
    throw new DecodeError("text exceeds size limit", "string_limit");
  }
  return decodeUtf8(reader.read(Number(size)));
}

function appendText(builder, value, limit = LIMITS.maxStringBytes) {
  if (typeof value !== "string") {
    throw new ValidationError("profile text must be a string", "profile_text_type");
  }
  const length = utf8Length(value, "profile text");
  if (length > limit) {
    throw new ValidationError("profile text exceeds size limit", "string_limit");
  }
  const raw = Buffer.from(value, "utf8");
  builder.append(encodeUvarint(raw.length)).append(raw);
}

function compareUtf8(left, right) {
  const leftIterator = left[Symbol.iterator]();
  const rightIterator = right[Symbol.iterator]();
  while (true) {
    const leftItem = leftIterator.next();
    const rightItem = rightIterator.next();
    if (leftItem.done || rightItem.done) {
      if (leftItem.done && rightItem.done) return 0;
      return leftItem.done ? -1 : 1;
    }
    const difference = leftItem.value.codePointAt(0) - rightItem.value.codePointAt(0);
    if (difference !== 0) return difference;
  }
}

function sortUtf8Keys(keys) {
  return keys
    .map((key) => ({ key, bytes: Buffer.from(key, "utf8") }))
    .sort((left, right) => Buffer.compare(left.bytes, right.bytes))
    .map((entry) => entry.key);
}

export function validateProfile(input) {
  if (!isMap(input)) {
    throw new ValidationError("profile must be a mapping", "profile_type");
  }
  const profileId = input.profileId ?? input.profile_id;
  if (!Number.isSafeInteger(profileId) || profileId < 1 || profileId > 65_535) {
    throw new ValidationError(
      "profile_id must be an integer from 1 to 65,535",
      "profile_id",
    );
  }
  const name = input.name;
  if (typeof name !== "string" || name.length === 0) {
    throw new ValidationError("profile name must be a non-empty string", "profile_name");
  }
  if (utf8Length(name, "profile name") > LIMITS.maxProfileNameBytes) {
    throw new ValidationError("profile name exceeds size limit", "profile_name_limit");
  }
  if (!Array.isArray(input.strings) || input.strings.length > LIMITS.maxDictionaryItems) {
    throw new ValidationError("static dictionary exceeds size limit", "dictionary_limit");
  }
  const strings = [...input.strings];
  if (strings.some((item) => typeof item !== "string")) {
    throw new ValidationError("static dictionary items must be strings", "dictionary_type");
  }
  if (new Set(strings).size !== strings.length) {
    throw new ValidationError(
      "static dictionary contains duplicate strings",
      "dictionary_duplicate",
    );
  }
  for (const item of strings) {
    if (item.length === 0) {
      throw new ValidationError("static dictionary cannot contain an empty string", "dictionary_empty");
    }
    if (utf8Length(item, "static dictionary string") > LIMITS.maxStringBytes) {
      throw new ValidationError(
        "static dictionary string exceeds size limit",
        "string_limit",
      );
    }
  }
  if (!Array.isArray(input.shapes) || input.shapes.length > LIMITS.maxShapes) {
    throw new ValidationError("profile shape table exceeds size limit", "shape_limit");
  }
  const known = new Set(strings);
  let totalShapeKeys = 0;
  const shapes = input.shapes.map((shape) => {
    if (!Array.isArray(shape) || shape.length === 0) {
      throw new ValidationError("profile map shape cannot be empty", "shape_empty");
    }
    if (shape.length > LIMITS.maxCollectionItems) {
      throw new ValidationError("profile map shape exceeds size limit", "shape_limit");
    }
    totalShapeKeys += shape.length;
    if (totalShapeKeys > LIMITS.maxProfileShapeKeys) {
      throw new ValidationError(
        "profile shape references exceed aggregate limit",
        "shape_limit",
      );
    }
    if (shape.some((key) => typeof key !== "string" || !known.has(key))) {
      throw new ValidationError(
        "every shape key must exist in the string dictionary",
        "shape_key",
      );
    }
    if (
      new Set(shape).size !== shape.length ||
      shape.some((key, index) => index > 0 && compareUtf8(shape[index - 1], key) >= 0)
    ) {
      throw new ValidationError(
        "profile map-shape keys must be unique and UTF-8 sorted",
        "shape_order",
      );
    }
    return Object.freeze([...shape]);
  });
  const serializedShapes = shapes.map((shape) => JSON.stringify(shape));
  if (new Set(serializedShapes).size !== serializedShapes.length) {
    throw new ValidationError("profile contains duplicate map shapes", "shape_duplicate");
  }
  const profile = Object.freeze({
    profileId,
    name,
    strings: Object.freeze(strings),
    shapes: Object.freeze(shapes),
  });
  VALID_PROFILES.add(profile);
  return profile;
}

function canonicalProfile(input) {
  return VALID_PROFILES.has(input) ? input : validateProfile(input);
}

const COMPILED_PROFILES = new WeakMap();

function profilePayloadUnchecked(profile) {
  const stringToIndex = new Map(profile.strings.map((value, index) => [value, index]));
  const builder = new Builder();
  builder.byte(PROFILE_FORMAT).append(encodeUvarint(profile.profileId));
  appendText(builder, profile.name, LIMITS.maxProfileNameBytes);
  builder.append(encodeUvarint(profile.strings.length));
  for (const item of profile.strings) appendText(builder, item);
  builder.append(encodeUvarint(profile.shapes.length));
  for (const shape of profile.shapes) {
    builder.append(encodeUvarint(shape.length));
    for (const key of shape) builder.append(encodeUvarint(stringToIndex.get(key)));
  }
  return builder.finish();
}

export function profilePayload(input) {
  const profile = canonicalProfile(input);
  return profilePayloadUnchecked(profile);
}

export function profileDictionaryId(input) {
  const profile = canonicalProfile(input);
  return sha256(profilePayloadUnchecked(profile)).subarray(0, DICTIONARY_ID_SIZE);
}

function firstCodePoint(value) {
  return value.length === 0 ? undefined : String.fromCodePoint(value.codePointAt(0));
}

function compileProfile(input) {
  const profile = canonicalProfile(input);
  const cached = COMPILED_PROFILES.get(profile);
  if (cached) return cached;
  const stringToIndex = new Map(profile.strings.map((value, index) => [value, index]));
  const shapeToIndex = new Map(
    profile.shapes.map((shape, index) => [JSON.stringify(shape), index]),
  );
  const prefixCandidates = new Map();
  profile.strings.forEach((value, index) => {
    const initial = firstCodePoint(value);
    const entries = prefixCandidates.get(initial) ?? [];
    entries.push({ index, value, bytes: utf8Length(value) });
    prefixCandidates.set(initial, entries);
  });
  for (const entries of prefixCandidates.values()) {
    entries.sort((left, right) => right.bytes - left.bytes || left.index - right.index);
  }
  const compiled = { profile, stringToIndex, shapeToIndex, prefixCandidates };
  COMPILED_PROFILES.set(profile, compiled);
  return compiled;
}

export function encodeCapsule(input) {
  const profile = canonicalProfile(input);
  const payload = profilePayloadUnchecked(profile);
  const header = Buffer.concat([CAPSULE_MAGIC, encodeUvarint(payload.length)]);
  const checksum = sha256(CAPSULE_HASH_DOMAIN, header, payload).subarray(0, CHECKSUM_SIZE);
  const capsule = Buffer.concat([header, payload, checksum]);
  if (capsule.length > LIMITS.maxFrameBytes) {
    throw new ValidationError("profile capsule exceeds size limit", "frame_limit");
  }
  return capsule;
}

export function decodeCapsule(input) {
  if (!Buffer.isBuffer(input) && !(input instanceof Uint8Array)) {
    throw new DecodeError("profile capsule must be bytes", "bytes_type");
  }
  if (input.byteLength > LIMITS.maxFrameBytes) {
    throw new DecodeError("profile capsule exceeds size limit", "frame_limit");
  }
  const capsule = Buffer.from(input);
  const reader = new Reader(capsule);
  if (!bytesEqual(reader.read(CAPSULE_MAGIC.length), CAPSULE_MAGIC)) {
    throw new DecodeError(
      "unsupported profile capsule magic or version",
      "capsule_magic",
    );
  }
  const payloadLength = reader.uvarint();
  if (payloadLength > BigInt(LIMITS.maxFrameBytes)) {
    throw new DecodeError("declared capsule payload exceeds size limit", "frame_limit");
  }
  const headerLength = reader.position;
  if (reader.remaining !== Number(payloadLength) + CHECKSUM_SIZE) {
    throw new DecodeError(
      "capsule payload length does not match frame length",
      "length_mismatch",
    );
  }
  const payload = reader.read(Number(payloadLength));
  const checksum = reader.read(CHECKSUM_SIZE);
  reader.expectEnd();
  const expected = sha256(
    CAPSULE_HASH_DOMAIN,
    capsule.subarray(0, headerLength),
    payload,
  ).subarray(0, CHECKSUM_SIZE);
  if (!bytesEqual(checksum, expected)) {
    throw new DecodeError("profile capsule checksum mismatch", "checksum");
  }

  const payloadReader = new Reader(payload);
  if (payloadReader.byte() !== PROFILE_FORMAT) {
    throw new DecodeError("unsupported profile capsule format", "profile_format");
  }
  const profileIdValue = payloadReader.uvarint();
  if (profileIdValue < 1n || profileIdValue > 65_535n) {
    throw new DecodeError("profile ID is out of range", "profile_id");
  }
  const profileId = Number(profileIdValue);
  const name = readText(payloadReader, LIMITS.maxProfileNameBytes);
  const dictionaryCount = payloadReader.uvarint();
  if (dictionaryCount > BigInt(LIMITS.maxDictionaryItems)) {
    throw new DecodeError("static dictionary exceeds size limit", "dictionary_limit");
  }
  const strings = [];
  for (let index = 0; index < Number(dictionaryCount); index += 1) {
    strings.push(readText(payloadReader));
  }
  if (new Set(strings).size !== strings.length) {
    throw new DecodeError(
      "static dictionary contains duplicate strings",
      "dictionary_duplicate",
    );
  }
  const shapeCount = payloadReader.uvarint();
  if (shapeCount > BigInt(LIMITS.maxShapes)) {
    throw new DecodeError("profile shape table exceeds size limit", "shape_limit");
  }
  const shapes = [];
  let totalShapeKeys = 0;
  for (let shapeIndex = 0; shapeIndex < Number(shapeCount); shapeIndex += 1) {
    const keyCount = payloadReader.uvarint();
    if (keyCount < 1n || keyCount > BigInt(LIMITS.maxCollectionItems)) {
      throw new DecodeError(
        "profile map shape has an invalid key count",
        "shape_key_count",
      );
    }
    totalShapeKeys += Number(keyCount);
    if (totalShapeKeys > LIMITS.maxProfileShapeKeys) {
      throw new DecodeError(
        "profile shape references exceed aggregate limit",
        "shape_limit",
      );
    }
    const keys = [];
    for (let keyIndex = 0; keyIndex < Number(keyCount); keyIndex += 1) {
      const dictionaryIndex = payloadReader.uvarint();
      if (dictionaryIndex >= BigInt(strings.length)) {
        throw new DecodeError(
          "profile shape key reference is out of range",
          "shape_key_reference",
        );
      }
      keys.push(strings[Number(dictionaryIndex)]);
    }
    shapes.push(keys);
  }
  payloadReader.expectEnd();
  let profile;
  try {
    profile = validateProfile({ profileId, name, strings, shapes });
  } catch (error) {
    if (error instanceof ValidationError) {
      throw new DecodeError(`invalid static profile: ${error.message}`, error.code);
    }
    throw error;
  }
  if (!bytesEqual(encodeCapsule(profile), capsule)) {
    throw new DecodeError(
      "profile capsule is valid but not canonical",
      "capsule_noncanonical",
    );
  }
  return profile;
}

export class ProfileRegistry {
  constructor(profiles = []) {
    this.profiles = new Map();
    for (const profile of profiles) this.register(profile);
  }

  register(input) {
    const profile = canonicalProfile(input);
    const dictionaryId = profileDictionaryId(profile);
    const key = `${profile.profileId}:${dictionaryId.toString("hex")}`;
    const existing = this.profiles.get(key);
    if (existing && !bytesEqual(profilePayload(existing), profilePayload(profile))) {
      throw new ValidationError("profile fingerprint collision", "profile_collision");
    }
    this.profiles.set(key, profile);
    return profile;
  }

  registerCapsule(capsule) {
    return this.register(decodeCapsule(capsule));
  }

  resolve(profileId, dictionaryId) {
    const key = `${profileId}:${Buffer.from(dictionaryId).toString("hex")}`;
    const profile = this.profiles.get(key);
    if (profile) return profile;
    const knownId = [...this.profiles.keys()].some((candidate) =>
      candidate.startsWith(`${profileId}:`),
    );
    if (!knownId) {
      throw new DecodeError(`unknown UrusillaWire v0.2 profile: ${profileId}`, "unknown_profile");
    }
    throw new DecodeError(
      `unknown dictionary for UrusillaWire v0.2 profile ${profileId}: ${Buffer.from(dictionaryId).toString("hex")}`,
      "unknown_dictionary",
    );
  }
}

export function encodeString(value, compiledOrProfile) {
  if (typeof value !== "string") {
    throw new ValidationError("string value must be text", "string_type");
  }
  const compiled = compiledOrProfile.stringToIndex
    ? compiledOrProfile
    : compileProfile(compiledOrProfile);
  const rawLength = utf8Length(value);
  if (rawLength > LIMITS.maxStringBytes) {
    throw new ValidationError("string exceeds size limit", "string_limit");
  }
  const raw = Buffer.from(value, "utf8");
  const exact = compiled.stringToIndex.get(value);
  if (exact !== undefined) {
    if (exact < TAGS.DIRECT_STRING_COUNT) {
      return Buffer.from([TAGS.DIRECT_STRING_BASE + exact]);
    }
    return Buffer.concat([Buffer.from([TAGS.STRING_REF]), encodeUvarint(exact)]);
  }

  const rawEncoding = Buffer.concat([
    Buffer.from([TAGS.STRING_RAW]),
    encodeUvarint(raw.length),
    raw,
  ]);
  let best = null;
  const candidates = compiled.prefixCandidates.get(firstCodePoint(value)) ?? [];
  for (const candidatePrefix of candidates) {
    if (!value.startsWith(candidatePrefix.value)) continue;
    const suffixText = value.slice(candidatePrefix.value.length);
    if (suffixText.length === 0) continue;
    const suffix = Buffer.from(suffixText, "utf8");
    const candidate = Buffer.concat([
      Buffer.from([TAGS.STRING_PREFIX]),
      encodeUvarint(candidatePrefix.index),
      encodeUvarint(suffix.length),
      suffix,
    ]);
    if (candidate.length >= rawEncoding.length) continue;
    const rank = [candidate.length, -candidatePrefix.bytes, candidatePrefix.index];
    if (
      best === null ||
      rank[0] < best.rank[0] ||
      (rank[0] === best.rank[0] && rank[1] < best.rank[1]) ||
      (rank[0] === best.rank[0] && rank[1] === best.rank[1] && rank[2] < best.rank[2])
    ) {
      best = { rank, candidate };
    }
  }
  return best?.candidate ?? rawEncoding;
}

function decodeStringWithTag(tag, reader, compiled) {
  const strings = compiled.profile.strings;
  if (
    tag >= TAGS.DIRECT_STRING_BASE &&
    tag < TAGS.DIRECT_STRING_BASE + TAGS.DIRECT_STRING_COUNT
  ) {
    const index = tag - TAGS.DIRECT_STRING_BASE;
    if (index >= strings.length) {
      throw new DecodeError(
        "direct static string reference is out of range",
        "string_reference",
      );
    }
    return strings[index];
  }
  if (tag === TAGS.STRING_REF) {
    const index = reader.uvarint();
    if (index >= BigInt(strings.length)) {
      throw new DecodeError("static string reference is out of range", "string_reference");
    }
    return strings[Number(index)];
  }
  if (tag === TAGS.STRING_RAW) return readText(reader);
  if (tag === TAGS.STRING_PREFIX) {
    const index = reader.uvarint();
    if (index >= BigInt(strings.length)) {
      throw new DecodeError("static prefix reference is out of range", "prefix_reference");
    }
    const suffix = readText(reader);
    const value = strings[Number(index)] + suffix;
    if (utf8Length(value) > LIMITS.maxStringBytes) {
      throw new DecodeError("prefixed string exceeds size limit", "string_limit");
    }
    return value;
  }
  throw new DecodeError(`value tag ${tag} is not a string representation`, "string_tag");
}

function encodeValue(value, compiled, depth = 0) {
  if (depth > LIMITS.maxDepth) {
    throw new ValidationError("semantic tree exceeds depth limit", "depth_limit");
  }
  if (value === null) return Buffer.from([TAGS.NULL]);
  if (value === false) return Buffer.from([TAGS.FALSE]);
  if (value === true) return Buffer.from([TAGS.TRUE]);
  if (value instanceof Float64) {
    if (!Number.isFinite(value.value)) {
      throw new ValidationError("NaN and infinity are not canonical", "float_nonfinite");
    }
    const result = Buffer.allocUnsafe(9);
    result[0] = TAGS.FLOAT64;
    result.writeDoubleBE(Object.is(value.value, -0) ? 0 : value.value, 1);
    return result;
  }
  if (typeof value === "number" || typeof value === "bigint") {
    const integer = integerToBigInt(value);
    return integer >= 0n
      ? Buffer.concat([Buffer.from([TAGS.UINT]), encodeUvarint(integer)])
      : Buffer.concat([Buffer.from([TAGS.SINT]), encodeSvarint(integer)]);
  }
  if (typeof value === "string") return encodeString(value, compiled);
  if (Buffer.isBuffer(value) || value instanceof Uint8Array) {
    if (value.byteLength > LIMITS.maxFrameBytes) {
      throw new ValidationError("byte string exceeds size limit", "frame_limit");
    }
    const bytes = Buffer.from(value);
    return Buffer.concat([Buffer.from([TAGS.BYTES]), encodeUvarint(bytes.length), bytes]);
  }
  if (Array.isArray(value)) {
    if (value.length > LIMITS.maxCollectionItems) {
      throw new ValidationError("list exceeds size limit", "collection_limit");
    }
    const builder = new Builder();
    builder.byte(TAGS.LIST).append(encodeUvarint(value.length));
    for (const item of value) builder.append(encodeValue(item, compiled, depth + 1));
    return builder.finish();
  }
  if (isMap(value)) {
    const keys = sortUtf8Keys(Object.keys(value));
    if (keys.length > LIMITS.maxCollectionItems) {
      throw new ValidationError("map exceeds size limit", "collection_limit");
    }
    const shapeIndex = compiled.shapeToIndex.get(JSON.stringify(keys));
    const builder = new Builder();
    if (shapeIndex !== undefined && shapeIndex < LIMITS.maxShapes) {
      builder.byte(TAGS.SHAPE_BASE + shapeIndex);
      for (const key of keys) builder.append(encodeValue(value[key], compiled, depth + 1));
      return builder.finish();
    }
    builder.byte(TAGS.MAP).append(encodeUvarint(keys.length));
    for (const key of keys) {
      builder.append(encodeString(key, compiled));
      builder.append(encodeValue(value[key], compiled, depth + 1));
    }
    return builder.finish();
  }
  throw new ValidationError(`cannot encode ${typeof value}`, "value_type");
}

function decodeValue(
  reader,
  compiled,
  depth = 0,
  budget = { remaining: LIMITS.maxTotalSemanticNodes },
) {
  if (depth > LIMITS.maxDepth) {
    throw new DecodeError("semantic tree exceeds depth limit", "depth_limit");
  }
  budget.remaining -= 1;
  if (budget.remaining < 0) {
    throw new DecodeError("semantic tree exceeds aggregate node limit", "node_limit");
  }
  const tag = reader.byte();
  if (tag >= TAGS.SHAPE_BASE) {
    const shapeIndex = tag - TAGS.SHAPE_BASE;
    if (shapeIndex >= compiled.profile.shapes.length) {
      throw new DecodeError(
        "static map-shape reference is out of range",
        "shape_reference",
      );
    }
    const result = Object.create(null);
    for (const key of compiled.profile.shapes[shapeIndex]) {
      result[key] = decodeValue(reader, compiled, depth + 1, budget);
    }
    return result;
  }
  switch (tag) {
    case TAGS.NULL:
      return null;
    case TAGS.FALSE:
      return false;
    case TAGS.TRUE:
      return true;
    case TAGS.UINT:
      return decodedInteger(reader.uvarint());
    case TAGS.SINT: {
      const zigzag = reader.uvarint();
      const value = zigzag % 2n === 0n ? zigzag / 2n : -((zigzag + 1n) / 2n);
      return decodedInteger(value);
    }
    case TAGS.FLOAT64: {
      const value = reader.read(8).readDoubleBE(0);
      if (!Number.isFinite(value) || Object.is(value, -0)) {
        throw new DecodeError("non-canonical float", "float_noncanonical");
      }
      return new Float64(value);
    }
    case TAGS.BYTES: {
      const size = reader.uvarint();
      if (size > BigInt(LIMITS.maxFrameBytes)) {
        throw new DecodeError("byte string exceeds size limit", "frame_limit");
      }
      return Buffer.from(reader.read(Number(size)));
    }
    case TAGS.LIST: {
      const count = reader.uvarint();
      if (count > BigInt(LIMITS.maxCollectionItems)) {
        throw new DecodeError("list exceeds size limit", "collection_limit");
      }
      const result = [];
      for (let index = 0; index < Number(count); index += 1) {
        result.push(decodeValue(reader, compiled, depth + 1, budget));
      }
      return result;
    }
    case TAGS.MAP: {
      const count = reader.uvarint();
      if (count > BigInt(LIMITS.maxCollectionItems)) {
        throw new DecodeError("map exceeds size limit", "collection_limit");
      }
      const result = Object.create(null);
      let previous = null;
      for (let index = 0; index < Number(count); index += 1) {
        const key = decodeStringWithTag(reader.byte(), reader, compiled);
        if (previous !== null && compareUtf8(key, previous) <= 0) {
          throw new DecodeError(
            "map keys are duplicate or non-canonical",
            "map_key_order",
          );
        }
        previous = key;
        result[key] = decodeValue(reader, compiled, depth + 1, budget);
      }
      return result;
    }
    default:
      if (
        tag === TAGS.STRING_RAW ||
        tag === TAGS.STRING_PREFIX ||
        tag === TAGS.STRING_REF ||
        (tag >= TAGS.DIRECT_STRING_BASE &&
          tag < TAGS.DIRECT_STRING_BASE + TAGS.DIRECT_STRING_COUNT)
      ) {
        return decodeStringWithTag(tag, reader, compiled);
      }
      throw new DecodeError(`unknown semantic value tag: ${tag}`, "value_tag");
  }
}

function uuidBytes(value, field) {
  if (typeof value !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)) {
    throw new ValidationError(`${field} must be a canonical UUID string`, "uuid");
  }
  return Buffer.from(value.replaceAll("-", ""), "hex");
}

function uuidText(bytes) {
  const hex = Buffer.from(bytes).toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function encodeMessage(message, profileInput) {
  if (!profileInput) {
    throw new ValidationError("an explicit v0.2 static profile is required", "profile_required");
  }
  const profile = canonicalProfile(profileInput);
  const canonical = normalizeMessage(message);
  const compiled = compileProfile(profile);
  const payloadBuilder = new Builder();
  payloadBuilder.append(uuidBytes(canonical.id, "id"));
  payloadBuilder.append(uuidBytes(canonical.session, "session"));
  payloadBuilder.append(encodeString(canonical.sender, compiled));
  payloadBuilder.append(encodeUvarint(canonical.recipients.length));
  for (const recipient of canonical.recipients) {
    payloadBuilder.append(encodeString(recipient, compiled));
  }
  const replyTo = canonical.reply_to;
  const actAndReply = ACT_TO_CODE.get(canonical.act) | (replyTo === null ? 0 : 0x08);
  payloadBuilder.byte(actAndReply);
  if (replyTo !== null) payloadBuilder.append(uuidBytes(replyTo, "reply_to"));
  payloadBuilder.append(encodeString(canonical.schema, compiled));
  payloadBuilder.append(encodeUvarint(canonical.logical_clock));
  payloadBuilder.append(encodeUvarint(canonical.expires_ms));
  payloadBuilder.append(
    encodeUvarint(canonical.confidence_ppm === null ? 0 : canonical.confidence_ppm + 1),
  );
  let expectedMask = 0;
  for (const act of canonical.expected) expectedMask |= 1 << ACT_TO_CODE.get(act);
  payloadBuilder.byte(expectedMask);
  payloadBuilder.append(encodeValue(canonical.body, compiled));
  payloadBuilder.append(encodeValue(canonical.meta, compiled));
  const payload = payloadBuilder.finish();

  const header = Buffer.concat([
    MAGIC,
    Buffer.from([FLAGS]),
    encodeUvarint(profile.profileId),
    profileDictionaryId(profile),
    encodeUvarint(payload.length),
  ]);
  const checksum = sha256(FRAME_HASH_DOMAIN, header, payload).subarray(0, CHECKSUM_SIZE);
  const frame = Buffer.concat([header, payload, checksum]);
  if (frame.length > LIMITS.maxFrameBytes) {
    throw new ValidationError("encoded v0.2 frame exceeds size limit", "frame_limit");
  }
  return frame;
}

export function decodeMessage(input, registry) {
  if (!(registry instanceof ProfileRegistry)) {
    throw new DecodeError("an explicit profile registry is required", "profile_registry");
  }
  if (!Buffer.isBuffer(input) && !(input instanceof Uint8Array)) {
    throw new DecodeError("frame must be bytes", "bytes_type");
  }
  if (input.byteLength > LIMITS.maxFrameBytes) {
    throw new DecodeError("frame exceeds size limit", "frame_limit");
  }
  const frame = Buffer.from(input);
  const reader = new Reader(frame);
  if (!bytesEqual(reader.read(MAGIC.length), MAGIC)) {
    throw new DecodeError("unsupported magic or UrusillaWire version", "frame_magic");
  }
  if (reader.byte() !== FLAGS) {
    throw new DecodeError(
      "unsupported or non-canonical v0.2 flags",
      "frame_flags",
    );
  }
  const profileIdValue = reader.uvarint();
  if (profileIdValue < 1n || profileIdValue > 65_535n) {
    throw new DecodeError("profile ID is out of range", "profile_id");
  }
  const profileId = Number(profileIdValue);
  const dictionaryId = reader.read(DICTIONARY_ID_SIZE);
  const payloadLength = reader.uvarint();
  if (payloadLength > BigInt(LIMITS.maxFrameBytes)) {
    throw new DecodeError("declared payload exceeds size limit", "frame_limit");
  }
  const headerLength = reader.position;
  if (reader.remaining !== Number(payloadLength) + CHECKSUM_SIZE) {
    throw new DecodeError("payload length does not match frame length", "length_mismatch");
  }
  const payload = reader.read(Number(payloadLength));
  const checksum = reader.read(CHECKSUM_SIZE);
  reader.expectEnd();
  const expectedChecksum = sha256(
    FRAME_HASH_DOMAIN,
    frame.subarray(0, headerLength),
    payload,
  ).subarray(0, CHECKSUM_SIZE);
  if (!bytesEqual(checksum, expectedChecksum)) {
    throw new DecodeError("v0.2 frame checksum mismatch", "checksum");
  }
  const profile = registry.resolve(profileId, dictionaryId);
  const compiled = compileProfile(profile);

  const payloadReader = new Reader(payload);
  const id = uuidText(payloadReader.read(16));
  const session = uuidText(payloadReader.read(16));
  const sender = decodeStringWithTag(payloadReader.byte(), payloadReader, compiled);
  const recipientCount = payloadReader.uvarint();
  if (recipientCount < 1n || recipientCount > BigInt(LIMITS.maxCollectionItems)) {
    throw new DecodeError("recipient count is invalid", "recipient_count");
  }
  const recipients = [];
  for (let index = 0; index < Number(recipientCount); index += 1) {
    recipients.push(decodeStringWithTag(payloadReader.byte(), payloadReader, compiled));
  }
  const actAndReply = payloadReader.byte();
  if ((actAndReply & 0xf0) !== 0) {
    throw new DecodeError("act/reply byte uses reserved bits", "act_reserved_bits");
  }
  const actCode = actAndReply & 0x07;
  if (actCode >= ACTS.length) {
    throw new DecodeError("unknown communicative act code", "act_unknown");
  }
  const act = ACTS[actCode];
  const replyTo = (actAndReply & 0x08) !== 0 ? uuidText(payloadReader.read(16)) : null;
  const schema = decodeStringWithTag(payloadReader.byte(), payloadReader, compiled);
  const logicalClock = decodedInteger(payloadReader.uvarint());
  const expiresMs = decodedInteger(payloadReader.uvarint());
  const encodedConfidence = payloadReader.uvarint();
  if (encodedConfidence > 1_000_001n) {
    throw new DecodeError("confidence is out of range", "confidence_range");
  }
  const confidencePpm = encodedConfidence === 0n ? null : Number(encodedConfidence - 1n);
  const expectedMask = payloadReader.byte();
  if (expectedMask >> ACTS.length) {
    throw new DecodeError(
      "expected-act bitset uses reserved bits",
      "expected_reserved_bits",
    );
  }
  const expected = ACTS.filter((_, code) => (expectedMask & (1 << code)) !== 0);
  const semanticBudget = { remaining: LIMITS.maxTotalSemanticNodes };
  const body = decodeValue(payloadReader, compiled, 0, semanticBudget);
  const meta = decodeValue(payloadReader, compiled, 0, semanticBudget);
  payloadReader.expectEnd();
  if (!isMap(meta)) {
    throw new DecodeError("decoded meta is not a map", "meta_type");
  }
  let canonical;
  try {
    canonical = normalizeMessage({
      id,
      session,
      sender,
      recipients,
      act,
      reply_to: replyTo,
      schema,
      logical_clock: logicalClock,
      expires_ms: expiresMs,
      confidence_ppm: confidencePpm,
      expected,
      body,
      meta,
    });
  } catch (error) {
    if (error instanceof ValidationError) {
      throw new DecodeError(
        `decoded frame violates Urusilla semantics: ${error.message}`,
        `semantic_${error.code}`,
      );
    }
    throw error;
  }
  if (!bytesEqual(encodeMessage(canonical, profile), frame)) {
    throw new DecodeError(
      "v0.2 frame is valid but not canonical",
      "frame_noncanonical",
    );
  }
  return canonical;
}

export function recomputeFrameChecksum(frameWithoutChecksum) {
  const data = Buffer.from(frameWithoutChecksum);
  return Buffer.concat([
    data,
    sha256(FRAME_HASH_DOMAIN, data).subarray(0, CHECKSUM_SIZE),
  ]);
}
