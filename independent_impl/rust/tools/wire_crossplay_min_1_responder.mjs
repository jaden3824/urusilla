#!/usr/bin/env node

// Raw-stdio responder for the bounded WIRE-CROSSPLAY-MIN-1 experiment.
// It opens no network connection and performs no external effect.

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { TextDecoder } from "node:util";

import { UrusillaError, ValidationError } from "../src/errors.mjs";
import { normalizeMessage } from "../src/semantic.mjs";
import {
  ProfileRegistry,
  decodeCapsule,
  decodeMessage,
  encodeMessage,
} from "../src/wire_v02.mjs";

const MODES = new Set(["wire", "json"]);
const MAX_RECORDS = 16;
const MAX_RECORD_BYTES = 16 * 1024 * 1024;
const SCHEMA = "urn:urusilla:wire-crossplay-min:1";
const REQUEST_PREDICATE = "urn:urusilla:wire-crossplay:min:select";
const RESULT_PREDICATE = "urn:urusilla:wire-crossplay:min:selection";
const FALLBACK_PREDICATE = "urn:urusilla:wire-crossplay:min:fallback";
const RESPONDER = "urn:agent:node-responder";
const EXPERIMENT = "WIRE-CROSSPLAY-MIN-1";
const UTF8 = new TextDecoder("utf-8", { fatal: true });

class ApplicationError extends UrusillaError {
  constructor(message, code = "application_contract") {
    super(message, code);
  }
}

class Reader {
  constructor(bytes) {
    this.bytes = bytes;
    this.offset = 0;
  }

  read(length) {
    if (!Number.isSafeInteger(length) || length < 0 || this.offset + length > this.bytes.length) {
      throw new ValidationError("truncated stdio record stream", "stdio_truncated");
    }
    const value = this.bytes.subarray(this.offset, this.offset + length);
    this.offset += length;
    return value;
  }

  u32() {
    return this.read(4).readUInt32BE(0);
  }

  end() {
    if (this.offset !== this.bytes.length) {
      throw new ValidationError("trailing stdio record bytes", "stdio_trailing");
    }
  }
}

function u32(value) {
  if (!Number.isSafeInteger(value) || value < 0 || value > 0xffffffff) {
    throw new ValidationError("stdio record length is out of range", "stdio_length");
  }
  const bytes = Buffer.alloc(4);
  bytes.writeUInt32BE(value);
  return bytes;
}

function exactKeys(value, expected) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
}

function canonicalJson(value) {
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) {
      throw new ApplicationError("JSON control accepts only safe integers", "json_number");
    }
    return String(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value === "object") {
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  throw new ApplicationError("JSON control contains an unsupported value", "json_type");
}

function parseCanonicalJson(bytes) {
  let text;
  try {
    text = UTF8.decode(bytes);
  } catch (error) {
    throw new ApplicationError("JSON control is not valid UTF-8", "json_utf8");
  }
  let value;
  try {
    value = JSON.parse(text);
  } catch (error) {
    throw new ApplicationError("JSON control cannot be parsed", "json_parse");
  }
  if (canonicalJson(value) !== text) {
    throw new ApplicationError("JSON control is not canonical", "json_noncanonical");
  }
  return normalizeMessage(value);
}

function responseUuid(requestId) {
  const bytes = Buffer.from(
    createHash("sha256")
      .update(`urusilla-wire-crossplay-min-1-response\u0000${requestId}`, "utf8")
      .digest()
      .subarray(0, 16),
  );
  bytes[6] = (bytes[6] & 0x0f) | 0x50;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes.toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function safetyConstraintIsClosed(message) {
  const constraints = message.body.constraints;
  if (!Array.isArray(constraints) || constraints.length !== 1) return false;
  const constraint = constraints[0];
  return (
    exactKeys(constraint, ["kind", "scope", "mode", "condition"]) &&
    constraint.kind === "constraint" &&
    constraint.scope === "safety" &&
    constraint.mode === "hard" &&
    exactKeys(constraint.condition, [
      "external_effects",
      "permission_expansion",
      "persistence",
      "spending_authority",
    ]) &&
    Object.values(constraint.condition).every((value) => value === false)
  );
}

function fallbackBody(reasonCode) {
  return {
    kind: "claim",
    predicate: FALLBACK_PREDICATE,
    arguments: [{ reason_code: reasonCode }],
  };
}

function deriveBody(message) {
  const condition = message.body.condition;
  if (
    !exactKeys(condition, ["kind", "predicate", "arguments"]) ||
    condition.kind !== "claim" ||
    condition.predicate !== REQUEST_PREDICATE ||
    !Array.isArray(condition.arguments)
  ) {
    throw new ApplicationError("request condition differs", "application_condition");
  }
  if (condition.arguments.length === 0) return fallbackBody("missing-payload");
  if (condition.arguments.length !== 1) {
    throw new ApplicationError("request payload count differs", "application_payload_count");
  }

  const payload = condition.arguments[0];
  const complete = ["branch", "candidates", "values", "invariant_marker"];
  const branchMissing = ["candidates", "values", "invariant_marker"];
  if (exactKeys(payload, branchMissing)) return fallbackBody("missing-branch");
  if (!exactKeys(payload, complete)) {
    throw new ApplicationError("request payload fields differ", "application_payload_fields");
  }
  if (
    !exactKeys(payload.candidates, ["A", "B"]) ||
    typeof payload.candidates.A !== "string" ||
    typeof payload.candidates.B !== "string" ||
    !Array.isArray(payload.values) ||
    payload.values.length === 0 ||
    payload.values.some((value) => !Number.isSafeInteger(value)) ||
    typeof payload.invariant_marker !== "string"
  ) {
    throw new ApplicationError("request payload value types differ", "application_payload_values");
  }
  if (payload.branch !== "A" && payload.branch !== "B") {
    return fallbackBody("unsupported-branch");
  }
  return {
    kind: "claim",
    predicate: RESULT_PREDICATE,
    arguments: [
      {
        selected: payload.candidates[payload.branch],
        total: payload.values.reduce((sum, value) => sum + value, 0),
      },
    ],
  };
}

function deriveResponse(input) {
  const message = normalizeMessage(input);
  if (
    message.act !== "REQUEST" ||
    message.schema !== SCHEMA ||
    message.recipients.length !== 1 ||
    message.recipients[0] !== RESPONDER ||
    message.body.kind !== "goal" ||
    !safetyConstraintIsClosed(message)
  ) {
    throw new ApplicationError("request envelope differs", "application_envelope");
  }
  return normalizeMessage({
    id: responseUuid(message.id),
    session: message.session,
    sender: RESPONDER,
    recipients: [message.sender],
    act: "ASSERT",
    reply_to: message.id,
    schema: SCHEMA,
    logical_clock: message.logical_clock + 1,
    expires_ms: 0,
    confidence_ppm: 1_000_000,
    expected: [],
    body: deriveBody(message),
    meta: {
      experiment: EXPERIMENT,
      effect_authorized: false,
    },
  });
}

function errorCode(error) {
  if (error instanceof UrusillaError && typeof error.code === "string") return error.code;
  return "unexpected_error";
}

function readRecords(reader) {
  const count = reader.u32();
  if (count > MAX_RECORDS) {
    throw new ValidationError("too many stdio records", "stdio_record_count");
  }
  const records = [];
  for (let index = 0; index < count; index += 1) {
    const length = reader.u32();
    if (length > MAX_RECORD_BYTES) {
      throw new ValidationError("stdio record exceeds size limit", "stdio_record_limit");
    }
    records.push(reader.read(length));
  }
  reader.end();
  return records;
}

function processStream(mode, input) {
  const reader = new Reader(input);
  let profile = null;
  let registry = null;
  if (mode === "wire") {
    const capsuleLength = reader.u32();
    if (capsuleLength > MAX_RECORD_BYTES) {
      throw new ValidationError("profile capsule exceeds stdio limit", "stdio_record_limit");
    }
    profile = decodeCapsule(reader.read(capsuleLength));
    registry = new ProfileRegistry([profile]);
  }
  const records = readRecords(reader);
  const output = [u32(records.length)];
  for (const record of records) {
    try {
      const message = mode === "wire" ? decodeMessage(record, registry) : parseCanonicalJson(record);
      const response = deriveResponse(message);
      const payload = mode === "wire"
        ? encodeMessage(response, profile)
        : Buffer.from(canonicalJson(response), "utf8");
      output.push(Buffer.from([0]), u32(payload.length), payload);
    } catch (error) {
      const payload = Buffer.from(errorCode(error), "ascii");
      output.push(Buffer.from([1]), u32(payload.length), payload);
    }
  }
  return Buffer.concat(output);
}

function main(argv) {
  if (argv.length !== 2 || argv[0] !== "--mode" || !MODES.has(argv[1])) {
    throw new Error("Usage: wire_crossplay_min_1_responder.mjs --mode wire|json");
  }
  const input = readFileSync(0);
  process.stdout.write(processStream(argv[1], input));
}

try {
  main(process.argv.slice(2));
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 2;
}
