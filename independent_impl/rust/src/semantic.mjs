import { ValidationError } from "./errors.mjs";

export const LIMITS = Object.freeze({
  maxFrameBytes: 16 * 1024 * 1024,
  maxDictionaryItems: 65_535,
  maxStringBytes: 1024 * 1024,
  maxCollectionItems: 100_000,
  maxTotalSemanticNodes: 250_000,
  maxPortableNodes: 450_100,
  maxPortableJsonBytes: 192 * 1024 * 1024,
  maxDepth: 64,
  maxProfileNameBytes: 256,
  maxShapes: 128,
  maxProfileShapeKeys: 100_000,
});

export const ACTS = Object.freeze([
  "ASSERT",
  "QUERY",
  "REQUEST",
  "PROPOSE",
  "COMMIT",
  "RESOLVE",
  "RETRACT",
]);

export const ACT_TO_CODE = new Map(ACTS.map((name, code) => [name, code]));

const MAX_UINT64 = (1n << 64n) - 1n;
const MAX_INT64 = (1n << 63n) - 1n;
const MIN_INT64 = -(1n << 63n);

const CORE_KINDS = Object.freeze({
  claim: ["predicate"],
  goal: ["condition"],
  constraint: ["scope", "mode", "condition"],
  evidence: ["target", "stance", "digest", "provenance"],
  uncertainty: ["target", "model", "parameters"],
  action: ["capability", "arguments"],
  commitment: ["debtor", "creditors", "goal", "expiry_ms"],
  resolution: ["target", "status"],
  ref: ["uri"],
});

const TOP_LEVEL_FIELDS = new Set([
  "id",
  "session",
  "sender",
  "recipients",
  "act",
  "reply_to",
  "schema",
  "logical_clock",
  "expires_ms",
  "confidence_ppm",
  "expected",
  "body",
  "meta",
]);

const CORE_KIND_FIELDS = Object.freeze({
  claim: new Set([
    "kind",
    "predicate",
    "arguments",
    "context",
    "valid_time",
    "answer_limit",
    "annotations",
  ]),
  goal: new Set([
    "kind",
    "condition",
    "owner",
    "window",
    "priority",
    "constraints",
    "annotations",
  ]),
  constraint: new Set([
    "kind",
    "scope",
    "mode",
    "condition",
    "weight",
    "weight_ppm",
    "annotations",
  ]),
  evidence: new Set([
    "kind",
    "target",
    "stance",
    "digest",
    "provenance",
    "observed_at",
    "observed_at_ms",
    "method",
    "annotations",
  ]),
  uncertainty: new Set([
    "kind",
    "target",
    "model",
    "parameters",
    "basis",
    "annotations",
  ]),
  action: new Set([
    "kind",
    "capability",
    "arguments",
    "declared_effects",
    "annotations",
  ]),
  commitment: new Set([
    "kind",
    "debtor",
    "creditors",
    "goal",
    "expiry_ms",
    "verifier",
    "cancellation_rule",
    "annotations",
  ]),
  resolution: new Set([
    "kind",
    "target",
    "status",
    "result",
    "evidence",
    "annotations",
  ]),
  ref: new Set(["kind", "uri", "annotations"]),
});

const ACT_BODY_KINDS = Object.freeze({
  ASSERT: new Set(["claim", "evidence", "uncertainty", "ref"]),
  QUERY: new Set(["claim"]),
  REQUEST: new Set(["goal"]),
  PROPOSE: new Set(["action"]),
  COMMIT: new Set(["commitment"]),
  RESOLVE: new Set(["resolution"]),
  RETRACT: new Set(["ref"]),
});

const RESOLUTION_STATUSES = new Set([
  "succeeded",
  "completed",
  "failed",
  "expired",
  "rejected",
  "canceled",
  "error",
]);
const EVIDENCE_STANCES = new Set(["supports", "contradicts", "neutral"]);
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const IDENTIFIER_RE = /^[A-Za-z][A-Za-z0-9+.-]*:.+$/u;
const UNICODE_WHITESPACE_RE = /\p{White_Space}/u;
export class Float64 {
  constructor(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new ValidationError("Float64 requires a finite Number", "float_nonfinite");
    }
    this.value = Object.is(value, -0) ? 0 : value;
    Object.freeze(this);
  }
}

export function float64(value) {
  return new Float64(value);
}

export function isMap(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  if (ArrayBuffer.isView(value) || value instanceof ArrayBuffer || value instanceof Float64) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

export function assertUnicodeScalarText(value, field = "string") {
  if (typeof value !== "string") {
    throw new ValidationError(`${field} must be a string`, "string_type");
  }
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        throw new ValidationError(
          `${field} contains an unpaired UTF-16 surrogate`,
          "invalid_unicode",
        );
      }
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      throw new ValidationError(
        `${field} contains an unpaired UTF-16 surrogate`,
        "invalid_unicode",
      );
    }
  }
  return value;
}

export function utf8Length(value, field = "string") {
  assertUnicodeScalarText(value, field);
  return Buffer.byteLength(value, "utf8");
}

function ensureStringLimit(value, field = "string") {
  if (utf8Length(value, field) > LIMITS.maxStringBytes) {
    throw new ValidationError(`${field} exceeds size limit`, "string_limit");
  }
}

function nonemptyText(value, field) {
  if (typeof value !== "string" || value.length === 0) {
    throw new ValidationError(`${field} must be a non-empty string`, "text_type");
  }
  ensureStringLimit(value, field);
  for (const character of value) {
    const code = character.codePointAt(0);
    if (code < 0x20 || UNICODE_WHITESPACE_RE.test(character)) {
      throw new ValidationError(
        `${field} cannot contain whitespace or control characters`,
        "text_whitespace",
      );
    }
  }
  return value;
}

function identifier(value, field) {
  const text = nonemptyText(value, field);
  if (!IDENTIFIER_RE.test(text)) {
    throw new ValidationError(
      `${field} must be an absolute URI or content identifier`,
      "identifier",
    );
  }
  return text;
}

function canonicalUuid(value, field) {
  if (typeof value !== "string" || !UUID_RE.test(value)) {
    throw new ValidationError(
      `${field} must use lowercase canonical UUID text`,
      "uuid",
    );
  }
  return value;
}

function canonicalInteger(value, field, minimum, maximum) {
  let integer;
  if (typeof value === "bigint") {
    integer = value;
  } else if (typeof value === "number" && Number.isSafeInteger(value)) {
    integer = BigInt(value);
  } else {
    throw new ValidationError(`${field} must be an exact integer`, "integer_type");
  }
  if (integer < minimum || integer > maximum) {
    throw new ValidationError(`${field} is out of range`, "integer_range");
  }
  return decodedInteger(integer);
}

function uint64(value, field) {
  return canonicalInteger(value, field, 0n, MAX_UINT64);
}

function ppm(value, field) {
  const result = canonicalInteger(value, field, 0n, 1_000_000n);
  return Number(result);
}

function requireArray(value, field, nonempty = false) {
  if (!Array.isArray(value)) {
    throw new ValidationError(`${field} must be a canonical list`, "list_type");
  }
  if (nonempty && value.length === 0) {
    throw new ValidationError(`${field} must be non-empty`, "list_empty");
  }
  return value;
}

function validateKnownNode(value, kind) {
  const unknown = Object.keys(value)
    .filter((key) => !CORE_KIND_FIELDS[kind].has(key))
    .sort();
  if (unknown.length) {
    throw new ValidationError(
      `${kind} node has unknown field(s): ${unknown.join(", ")}; use annotations`,
      "node_unknown_field",
    );
  }
  if (value.annotations !== undefined && !isMap(value.annotations)) {
    throw new ValidationError(`${kind}.annotations must be a map`, "annotations_type");
  }

  switch (kind) {
    case "claim":
      nonemptyText(value.predicate, "claim.predicate");
      if (value.arguments !== undefined) requireArray(value.arguments, "claim.arguments");
      if (value.context !== undefined && !isMap(value.context)) {
        throw new ValidationError("claim.context must be a map", "claim_context");
      }
      if (
        value.answer_limit !== undefined &&
        !(
          (typeof value.answer_limit === "number" &&
            Number.isSafeInteger(value.answer_limit) &&
            value.answer_limit > 0) ||
          (typeof value.answer_limit === "bigint" && value.answer_limit > 0n)
        )
      ) {
        throw new ValidationError(
          "claim.answer_limit must be a positive integer",
          "answer_limit",
        );
      }
      break;
    case "goal":
      if (!isMap(value.condition)) {
        throw new ValidationError("goal.condition must be a semantic node", "goal_condition");
      }
      if (value.owner !== undefined) nonemptyText(value.owner, "goal.owner");
      if (
        value.priority !== undefined &&
        !(
          (typeof value.priority === "number" && Number.isSafeInteger(value.priority)) ||
          typeof value.priority === "bigint"
        )
      ) {
        throw new ValidationError("goal.priority must be an integer", "goal_priority");
      }
      if (value.constraints !== undefined) {
        const constraints = requireArray(value.constraints, "goal.constraints");
        if (constraints.some((item) => !isMap(item) || item.kind !== "constraint")) {
          throw new ValidationError(
            "goal.constraints must contain constraint nodes",
            "goal_constraints",
          );
        }
      }
      break;
    case "constraint":
      nonemptyText(value.scope, "constraint.scope");
      if (value.mode !== "hard" && value.mode !== "soft") {
        throw new ValidationError("constraint.mode must be hard or soft", "constraint_mode");
      }
      if (value.weight_ppm !== undefined) ppm(value.weight_ppm, "constraint.weight_ppm");
      break;
    case "evidence":
      if (!EVIDENCE_STANCES.has(value.stance)) {
        throw new ValidationError("evidence.stance is not recognized", "evidence_stance");
      }
      identifier(value.digest, "evidence.digest");
      if (
        typeof value.provenance !== "string" &&
        !isMap(value.provenance) &&
        !Array.isArray(value.provenance)
      ) {
        throw new ValidationError(
          "evidence.provenance must be a string, map, or list",
          "evidence_provenance",
        );
      }
      break;
    case "uncertainty":
      nonemptyText(value.model, "uncertainty.model");
      if (!isMap(value.parameters)) {
        throw new ValidationError(
          "uncertainty.parameters must be a map",
          "uncertainty_parameters",
        );
      }
      if (value.basis !== undefined) requireArray(value.basis, "uncertainty.basis");
      break;
    case "action":
      nonemptyText(value.capability, "action.capability");
      if (!isMap(value.arguments) && !Array.isArray(value.arguments)) {
        throw new ValidationError(
          "action.arguments must be a map or list",
          "action_arguments",
        );
      }
      if (value.declared_effects !== undefined) {
        const effects = requireArray(value.declared_effects, "action.declared_effects");
        if (effects.some((item) => typeof item !== "string" || item.length === 0)) {
          throw new ValidationError(
            "action.declared_effects must contain non-empty strings",
            "declared_effects",
          );
        }
      }
      break;
    case "commitment": {
      nonemptyText(value.debtor, "commitment.debtor");
      const creditors = requireArray(value.creditors, "commitment.creditors", true);
      if (creditors.some((item) => typeof item !== "string" || item.length === 0)) {
        throw new ValidationError(
          "commitment.creditors must contain non-empty strings",
          "creditors_type",
        );
      }
      if (new Set(creditors).size !== creditors.length) {
        throw new ValidationError("commitment.creditors must be unique", "creditors_unique");
      }
      if (!isMap(value.goal) || value.goal.kind !== "goal") {
        throw new ValidationError("commitment.goal must be a goal node", "commitment_goal");
      }
      uint64(value.expiry_ms, "commitment.expiry_ms");
      if (value.verifier !== undefined) nonemptyText(value.verifier, "commitment.verifier");
      break;
    }
    case "resolution":
      if (typeof value.status !== "string" || !RESOLUTION_STATUSES.has(value.status)) {
        throw new ValidationError(
          "resolution.status is not recognized",
          "resolution_status",
        );
      }
      if (
        value.evidence !== undefined &&
        !isMap(value.evidence) &&
        !Array.isArray(value.evidence)
      ) {
        throw new ValidationError(
          "resolution.evidence must be a semantic node or list",
          "resolution_evidence",
        );
      }
      break;
    case "ref":
      identifier(value.uri, "ref.uri");
      break;
    default:
      throw new ValidationError(`unsupported core kind: ${kind}`, "internal_kind");
  }
}

export function normalizeTree(
  value,
  depth = 0,
  budget = { remaining: LIMITS.maxTotalSemanticNodes },
) {
  if (depth > LIMITS.maxDepth) {
    throw new ValidationError(
      `semantic tree exceeds maximum depth ${LIMITS.maxDepth}`,
      "depth_limit",
    );
  }
  budget.remaining -= 1;
  if (budget.remaining < 0) {
    throw new ValidationError(
      "semantic tree exceeds aggregate node limit",
      "node_limit",
    );
  }
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") {
    ensureStringLimit(value);
    return value;
  }
  if (Buffer.isBuffer(value) || value instanceof Uint8Array) {
    if (value.byteLength > LIMITS.maxFrameBytes) {
      throw new ValidationError("byte string exceeds size limit", "frame_limit");
    }
    return Buffer.from(value);
  }
  if (value instanceof Float64) return new Float64(value.value);
  if (typeof value === "bigint") {
    if (value < MIN_INT64 || value > MAX_UINT64) {
      throw new ValidationError("integer exceeds 64-bit Urusilla range", "integer_range");
    }
    return decodedInteger(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new ValidationError("NaN and infinity are not allowed", "float_nonfinite");
    }
    if (Object.is(value, -0)) return new Float64(0);
    if (Number.isInteger(value)) {
      if (!Number.isSafeInteger(value)) {
        throw new ValidationError(
          "integer must be exact; use BigInt outside the safe Number range",
          "integer_inexact",
        );
      }
      const integer = BigInt(value);
      if (integer < MIN_INT64 || integer > MAX_UINT64) {
        throw new ValidationError("integer exceeds 64-bit Urusilla range", "integer_range");
      }
      return value;
    }
    return new Float64(value);
  }
  if (Array.isArray(value)) {
    if (value.length > LIMITS.maxCollectionItems) {
      throw new ValidationError("list exceeds size limit", "collection_limit");
    }
    return value.map((item) => normalizeTree(item, depth + 1, budget));
  }
  if (isMap(value)) {
    const keys = Object.keys(value);
    if (keys.length > LIMITS.maxCollectionItems) {
      throw new ValidationError("map exceeds size limit", "collection_limit");
    }
    const kind = value.kind;
    if (kind !== undefined) {
      if (typeof kind !== "string") {
        throw new ValidationError("node kind must be a string", "node_kind_type");
      }
      if (Object.hasOwn(CORE_KINDS, kind)) {
        const missing = CORE_KINDS[kind].filter((key) => !Object.hasOwn(value, key));
        if (missing.length) {
          throw new ValidationError(
            `${kind} node is missing required field(s): ${missing.join(", ")}`,
            "node_missing_field",
          );
        }
      } else if (
        !kind.startsWith("x:") ||
        kind.length === 2 ||
        [...kind].some(
          (character) =>
            character.codePointAt(0) < 0x20 || UNICODE_WHITESPACE_RE.test(character),
        )
      ) {
        throw new ValidationError(
          `unknown node kind ${JSON.stringify(kind)}; local prototype extensions require x:<name>`,
          "node_kind",
        );
      }
    }
    const normalized = Object.create(null);
    for (const key of keys) {
      ensureStringLimit(key, "map key");
      normalized[key] = normalizeTree(value[key], depth + 1, budget);
    }
    if (Object.hasOwn(CORE_KINDS, kind)) validateKnownNode(normalized, kind);
    return normalized;
  }
  throw new ValidationError(
    `unsupported semantic value type: ${typeof value}`,
    "value_type",
  );
}

function containsExtensionNode(value) {
  if (Array.isArray(value)) return value.some(containsExtensionNode);
  if (!isMap(value)) return false;
  if (typeof value.kind === "string" && value.kind.startsWith("x:")) return true;
  return Object.values(value).some(containsExtensionNode);
}

export function normalizeMessage(message) {
  if (!isMap(message)) {
    throw new ValidationError("message must be a mapping", "message_type");
  }
  const required = ["id", "session", "sender", "recipients", "act", "schema", "body"];
  const missing = required.filter((field) => !Object.hasOwn(message, field));
  if (missing.length) {
    throw new ValidationError(
      `missing top-level field(s): ${missing.join(", ")}`,
      "message_missing_field",
    );
  }
  const unknown = Object.keys(message)
    .filter((field) => !TOP_LEVEL_FIELDS.has(field))
    .sort();
  if (unknown.length) {
    throw new ValidationError(
      `unknown top-level field(s): ${unknown.join(", ")}; place extensions under meta`,
      "message_unknown_field",
    );
  }

  const id = canonicalUuid(message.id, "id");
  const session = canonicalUuid(message.session, "session");
  const sender = nonemptyText(message.sender, "sender");
  const recipientInput = requireArray(message.recipients, "recipients", true);
  if (recipientInput.length > LIMITS.maxCollectionItems) {
    throw new ValidationError("recipients exceed size limit", "recipient_limit");
  }
  const recipients = recipientInput.map((item) => nonemptyText(item, "recipient"));
  if (new Set(recipients).size !== recipients.length) {
    throw new ValidationError("recipients must be unique", "recipient_unique");
  }

  if (typeof message.act !== "string") {
    throw new ValidationError("act must be a string", "act_type");
  }
  const act = message.act;
  if (!ACT_TO_CODE.has(act)) {
    throw new ValidationError(`unknown communicative act: ${act}`, "act_unknown");
  }

  let replyTo = Object.hasOwn(message, "reply_to") ? message.reply_to : null;
  if (replyTo !== null) replyTo = canonicalUuid(replyTo, "reply_to");
  if (["COMMIT", "RESOLVE", "RETRACT"].includes(act) && replyTo === null) {
    throw new ValidationError(
      `${act} requires reply_to for an observable state transition`,
      "causal_reference",
    );
  }

  const schema = identifier(message.schema, "schema");
  const logicalClock = uint64(
    Object.hasOwn(message, "logical_clock") ? message.logical_clock : 0,
    "logical_clock",
  );
  const expiresMs = uint64(
    Object.hasOwn(message, "expires_ms") ? message.expires_ms : 0,
    "expires_ms",
  );
  const confidenceInput = Object.hasOwn(message, "confidence_ppm")
    ? message.confidence_ppm
    : null;
  const confidencePpm =
    confidenceInput === null ? null : ppm(confidenceInput, "confidence_ppm");

  const expectedInput = requireArray(
    Object.hasOwn(message, "expected") ? message.expected : [],
    "expected",
  );
  if (expectedInput.length > LIMITS.maxCollectionItems) {
    throw new ValidationError("expected acts exceed size limit", "collection_limit");
  }
  const expectedSet = new Set();
  for (const item of expectedInput) {
    if (typeof item !== "string") {
      throw new ValidationError("expected acts must be strings", "expected_type");
    }
    const name = item;
    if (!ACT_TO_CODE.has(name)) {
      throw new ValidationError(`unknown expected act: ${name}`, "expected_unknown");
    }
    expectedSet.add(name);
  }
  const expected = [...expectedSet].sort((left, right) => ACT_TO_CODE.get(left) - ACT_TO_CODE.get(right));

  const semanticBudget = { remaining: LIMITS.maxTotalSemanticNodes };
  const body = normalizeTree(message.body, 0, semanticBudget);
  if (!isMap(body)) {
    throw new ValidationError("body must be a semantic node map", "body_type");
  }
  const metaInput = Object.hasOwn(message, "meta") ? message.meta : {};
  if (!isMap(metaInput)) {
    throw new ValidationError("meta must be a mapping", "meta_type");
  }
  const meta = normalizeTree(metaInput, 0, semanticBudget);
  const bodyKind = body.kind;
  if (act === "QUERY" && bodyKind === undefined) {
    const allowed = new Set(["question", "answer_schema", "constraints", "annotations"]);
    const invalid = Object.keys(body).filter((key) => !allowed.has(key));
    if (invalid.length || !Object.hasOwn(body, "question") || !Object.hasOwn(body, "answer_schema")) {
      throw new ValidationError(
        "QUERY body without kind requires question and answer_schema only",
        "query_body",
      );
    }
    if (!isMap(body.question)) {
      throw new ValidationError("QUERY question must be a semantic node", "query_question");
    }
    identifier(body.answer_schema, "QUERY answer_schema");
  } else if (typeof bodyKind !== "string") {
    throw new ValidationError("body must declare a node kind", "body_kind");
  } else if (bodyKind.startsWith("x:")) {
    if (act !== "ASSERT") {
      throw new ValidationError(
        "prototype extension nodes are quarantined to ASSERT",
        "extension_quarantine",
      );
    }
  } else if (!ACT_BODY_KINDS[act].has(bodyKind)) {
    throw new ValidationError(`${act} cannot carry a ${bodyKind} body`, "act_body_kind");
  }

  if (act !== "ASSERT" && containsExtensionNode(body)) {
    throw new ValidationError(
      "prototype extension nodes are quarantined to ASSERT",
      "extension_quarantine",
    );
  }

  if (act === "COMMIT" && body.debtor !== sender) {
    throw new ValidationError(
      "COMMIT debtor must equal the declared sender",
      "commitment_debtor",
    );
  }

  return {
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
  };
}

export function integerToBigInt(value, field = "integer") {
  if (typeof value === "bigint") return value;
  if (typeof value === "number" && Number.isSafeInteger(value)) return BigInt(value);
  throw new ValidationError(`${field} must be an exact integer`, "integer_type");
}

export function decodedInteger(value) {
  if (value >= BigInt(Number.MIN_SAFE_INTEGER) && value <= BigInt(Number.MAX_SAFE_INTEGER)) {
    return Number(value);
  }
  return value;
}

export const INTEGER_LIMITS = Object.freeze({ MAX_UINT64, MAX_INT64, MIN_INT64 });
