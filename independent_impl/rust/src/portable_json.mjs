import {
  Float64,
  INTEGER_LIMITS,
  LIMITS,
  decodedInteger,
  isMap,
  utf8Length,
} from "./semantic.mjs";
import { ValidationError } from "./errors.mjs";

const FIXTURE_FLOAT_KEY = "$urusilla_float64_be";
const FIXTURE_BYTES_KEY = "$urusilla_bytes_base64";
const FIXTURE_BIGINT_KEY = "$urusilla_bigint";
const TYPE_KEY = "$urusilla_type";

function exactKeys(value, keys) {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function decodeFloatBits(bits) {
  if (typeof bits !== "string" || !/^[0-9a-f]{16}$/.test(bits)) {
    throw new ValidationError("invalid portable Float64 bits", "portable_float");
  }
  const value = Buffer.from(bits, "hex").readDoubleBE(0);
  if (Object.is(value, -0)) {
    throw new ValidationError("negative zero is not canonical", "portable_float");
  }
  return new Float64(value);
}

function decodeCanonicalBase64(value) {
  if (typeof value !== "string") {
    throw new ValidationError("invalid portable byte string", "portable_bytes");
  }
  const maximumCharacters = 4 * Math.ceil(LIMITS.maxFrameBytes / 3);
  if (value.length > maximumCharacters) {
    throw new ValidationError("portable byte string exceeds size limit", "frame_limit");
  }
  const bytes = Buffer.from(value, "base64");
  if (bytes.byteLength > LIMITS.maxFrameBytes || bytes.toString("base64") !== value) {
    throw new ValidationError("portable byte string is not canonical Base64", "portable_bytes");
  }
  return bytes;
}

function decodeIntegerText(value, label) {
  if (
    typeof value !== "string" ||
    value === "-0" ||
    !/^-?(?:0|[1-9][0-9]*)$/.test(value)
  ) {
    throw new ValidationError(`invalid ${label}`, "portable_bigint");
  }
  if (value.length > 20) {
    throw new ValidationError(`${label} exceeds the Urusilla integer range`, "integer_range");
  }
  const integer = BigInt(value);
  if (integer < INTEGER_LIMITS.MIN_INT64 || integer > INTEGER_LIMITS.MAX_UINT64) {
    throw new ValidationError(`${label} exceeds the Urusilla integer range`, "integer_range");
  }
  return decodedInteger(integer);
}

function checkDepth(depth) {
  if (depth > LIMITS.maxDepth + 1) {
    throw new ValidationError("portable JSON exceeds semantic depth limit", "depth_limit");
  }
}

function consumeNode(budget) {
  budget.remaining -= 1;
  if (budget.remaining < 0) {
    throw new ValidationError(
      "portable JSON exceeds aggregate semantic node limit",
      "node_limit",
    );
  }
}

/** Decode the compact, constrained convention used only by frozen fixture files. */
export function fromFixtureJson(
  value,
  depth = 0,
  budget = { remaining: LIMITS.maxPortableNodes },
) {
  checkDepth(depth);
  consumeNode(budget);
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") {
    if (utf8Length(value) > LIMITS.maxStringBytes) {
      throw new ValidationError("fixture string exceeds size limit", "string_limit");
    }
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) {
      throw new ValidationError(
        "fixture JSON numbers must be safe integers; use an explicit typed wrapper",
        "portable_number",
      );
    }
    return value;
  }
  if (Array.isArray(value)) {
    if (value.length > LIMITS.maxCollectionItems) {
      throw new ValidationError("fixture list exceeds size limit", "collection_limit");
    }
    return value.map((item) => fromFixtureJson(item, depth + 1, budget));
  }
  if (!isMap(value)) {
    throw new ValidationError("fixture JSON contains an unsupported value", "portable_type");
  }
  if (exactKeys(value, [FIXTURE_FLOAT_KEY])) return decodeFloatBits(value[FIXTURE_FLOAT_KEY]);
  if (exactKeys(value, [FIXTURE_BYTES_KEY])) return decodeCanonicalBase64(value[FIXTURE_BYTES_KEY]);
  if (exactKeys(value, [FIXTURE_BIGINT_KEY])) {
    return decodeIntegerText(value[FIXTURE_BIGINT_KEY], "fixture BigInt");
  }
  const entries = Object.entries(value);
  if (entries.length > LIMITS.maxCollectionItems) {
    throw new ValidationError("fixture map exceeds size limit", "collection_limit");
  }
  const output = Object.create(null);
  for (const [key, item] of entries) {
    if (utf8Length(key, "fixture map key") > LIMITS.maxStringBytes) {
      throw new ValidationError("fixture map key exceeds size limit", "string_limit");
    }
    output[key] = fromFixtureJson(item, depth + 1, budget);
  }
  return output;
}

/** Decode the unambiguous CLI projection, in which every value is tagged. */
export function fromPortableJson(
  value,
  depth = 0,
  budget = { remaining: LIMITS.maxPortableNodes },
) {
  checkDepth(depth);
  consumeNode(budget);
  if (!isMap(value) || typeof value[TYPE_KEY] !== "string") {
    throw new ValidationError("portable JSON value must have a $urusilla_type tag", "portable_type");
  }
  switch (value[TYPE_KEY]) {
    case "null":
      if (!exactKeys(value, [TYPE_KEY])) throw new ValidationError("invalid null projection", "portable_shape");
      return null;
    case "boolean":
      if (!exactKeys(value, [TYPE_KEY, "value"]) || typeof value.value !== "boolean") {
        throw new ValidationError("invalid boolean projection", "portable_shape");
      }
      return value.value;
    case "string":
      if (!exactKeys(value, [TYPE_KEY, "value"]) || typeof value.value !== "string") {
        throw new ValidationError("invalid string projection", "portable_shape");
      }
      if (utf8Length(value.value, "portable string") > LIMITS.maxStringBytes) {
        throw new ValidationError("portable string exceeds size limit", "string_limit");
      }
      return value.value;
    case "integer":
      if (
        !exactKeys(value, [TYPE_KEY, "value"]) ||
        typeof value.value !== "string" ||
        !/^-?(?:0|[1-9][0-9]*)$/.test(value.value)
      ) {
        throw new ValidationError("invalid integer projection", "portable_shape");
      }
      return decodeIntegerText(value.value, "portable integer");
    case "float64":
      if (!exactKeys(value, [TYPE_KEY, "bits"])) {
        throw new ValidationError("invalid Float64 projection", "portable_shape");
      }
      return decodeFloatBits(value.bits);
    case "bytes":
      if (!exactKeys(value, [TYPE_KEY, "base64"])) {
        throw new ValidationError("invalid bytes projection", "portable_shape");
      }
      return decodeCanonicalBase64(value.base64);
    case "list":
      if (!exactKeys(value, [TYPE_KEY, "items"]) || !Array.isArray(value.items)) {
        throw new ValidationError("invalid list projection", "portable_shape");
      }
      if (value.items.length > LIMITS.maxCollectionItems) {
        throw new ValidationError("portable list exceeds size limit", "collection_limit");
      }
      return value.items.map((item) => fromPortableJson(item, depth + 1, budget));
    case "map": {
      if (!exactKeys(value, [TYPE_KEY, "entries"]) || !Array.isArray(value.entries)) {
        throw new ValidationError("invalid map projection", "portable_shape");
      }
      if (value.entries.length > LIMITS.maxCollectionItems) {
        throw new ValidationError("portable map exceeds size limit", "collection_limit");
      }
      const output = Object.create(null);
      for (const entry of value.entries) {
        if (!Array.isArray(entry) || entry.length !== 2 || typeof entry[0] !== "string") {
          throw new ValidationError("invalid map entry projection", "portable_shape");
        }
        if (Object.hasOwn(output, entry[0])) {
          throw new ValidationError("portable map contains a duplicate key", "portable_duplicate");
        }
        if (utf8Length(entry[0], "portable map key") > LIMITS.maxStringBytes) {
          throw new ValidationError("portable map key exceeds size limit", "string_limit");
        }
        output[entry[0]] = fromPortableJson(entry[1], depth + 1, budget);
      }
      return output;
    }
    default:
      throw new ValidationError(`unknown portable type: ${value[TYPE_KEY]}`, "portable_type");
  }
}

export function toPortableJson(
  value,
  depth = 0,
  budget = { remaining: LIMITS.maxPortableNodes },
) {
  checkDepth(depth);
  consumeNode(budget);
  if (value === null) return { [TYPE_KEY]: "null" };
  if (typeof value === "boolean") return { [TYPE_KEY]: "boolean", value };
  if (typeof value === "string") {
    if (utf8Length(value, "portable string") > LIMITS.maxStringBytes) {
      throw new ValidationError("portable string exceeds size limit", "string_limit");
    }
    return { [TYPE_KEY]: "string", value };
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || Object.is(value, -0)) {
      throw new ValidationError("untyped non-integer Number cannot be projected", "portable_number");
    }
    return { [TYPE_KEY]: "integer", value: String(value) };
  }
  if (typeof value === "bigint") {
    const canonical = decodeIntegerText(value.toString(), "portable integer");
    if (typeof canonical !== "bigint") {
      throw new ValidationError(
        "safe integer must use the canonical Number representation",
        "portable_number",
      );
    }
    return { [TYPE_KEY]: "integer", value: value.toString() };
  }
  if (value instanceof Float64) {
    const bytes = Buffer.allocUnsafe(8);
    bytes.writeDoubleBE(value.value, 0);
    return { [TYPE_KEY]: "float64", bits: bytes.toString("hex") };
  }
  if (Buffer.isBuffer(value) || value instanceof Uint8Array) {
    if (value.byteLength > LIMITS.maxFrameBytes) {
      throw new ValidationError("portable byte string exceeds size limit", "frame_limit");
    }
    return { [TYPE_KEY]: "bytes", base64: Buffer.from(value).toString("base64") };
  }
  if (Array.isArray(value)) {
    if (value.length > LIMITS.maxCollectionItems) {
      throw new ValidationError("portable list exceeds size limit", "collection_limit");
    }
    return {
      [TYPE_KEY]: "list",
      items: value.map((item) => toPortableJson(item, depth + 1, budget)),
    };
  }
  if (isMap(value)) {
    const entries = Object.entries(value);
    if (entries.length > LIMITS.maxCollectionItems) {
      throw new ValidationError("portable map exceeds size limit", "collection_limit");
    }
    return {
      [TYPE_KEY]: "map",
      entries: entries.map(([key, item]) => {
        if (utf8Length(key, "portable map key") > LIMITS.maxStringBytes) {
          throw new ValidationError("portable map key exceeds size limit", "string_limit");
        }
        return [key, toPortableJson(item, depth + 1, budget)];
      }),
    };
  }
  throw new ValidationError("cannot convert value to portable JSON", "portable_type");
}

export function parsePortableJson(input) {
  let text;
  if (typeof input === "string") {
    if (utf8Length(input, "portable JSON document") > LIMITS.maxPortableJsonBytes) {
      throw new ValidationError("portable JSON document exceeds size limit", "frame_limit");
    }
    text = input;
  } else if (Buffer.isBuffer(input) || input instanceof Uint8Array) {
    if (input.byteLength > LIMITS.maxPortableJsonBytes) {
      throw new ValidationError("portable JSON document exceeds size limit", "frame_limit");
    }
    try {
      text = new TextDecoder("utf-8", { fatal: true }).decode(input);
    } catch {
      throw new ValidationError("portable JSON document is not valid UTF-8", "invalid_utf8");
    }
  } else {
    throw new ValidationError("portable JSON input must be text or bytes", "portable_type");
  }
  return fromPortableJson(JSON.parse(text));
}

export function stringifyPortableJson(value, space = 2) {
  const text = `${JSON.stringify(toPortableJson(value), null, space)}\n`;
  if (utf8Length(text, "portable JSON document") > LIMITS.maxPortableJsonBytes) {
    throw new ValidationError("portable JSON document exceeds size limit", "frame_limit");
  }
  return text;
}
