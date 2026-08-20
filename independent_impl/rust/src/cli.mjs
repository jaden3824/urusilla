#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readFileSync, statSync, writeFileSync } from "node:fs";

import { DecodeError, UrusillaError, ValidationError } from "./errors.mjs";
import {
  loadCrossplayVectors,
  loadFrozenProfile,
  loadFrozenRegistry,
} from "./frozen_inputs.mjs";
import { fromFixtureJson, parsePortableJson, stringifyPortableJson } from "./portable_json.mjs";
import { LIMITS } from "./semantic.mjs";
import {
  ProfileRegistry,
  decodeCapsule,
  decodeMessage,
  encodeMessage,
  profileDictionaryId,
  sha256Hex,
} from "./wire_v02.mjs";

function usage() {
  return `Usage:
  node src/cli.mjs verify-vectors
  node src/cli.mjs capsule-info [capsule.bin]
  node src/cli.mjs encode <portable-message.json> <frame.bin> [capsule.bin]
  node src/cli.mjs decode <frame.bin> <portable-message.json> [capsule.bin]

Portable JSON uses a tagged value at every level. For example:
  {"$urusilla_type":"integer","value":"18446744073709551615"}
  {"$urusilla_type":"float64","bits":"3ff0000000000000"}
  {"$urusilla_type":"bytes","base64":"AP8="}`;
}

function readBounded(path, label, limit = LIMITS.maxFrameBytes) {
  if (statSync(path).size > limit) {
    throw new ValidationError(`${label} exceeds size limit`, "frame_limit");
  }
  const bytes = readFileSync(path);
  if (bytes.byteLength > limit) {
    throw new ValidationError(`${label} exceeds size limit`, "frame_limit");
  }
  return bytes;
}

function loadProfile(path) {
  return path ? decodeCapsule(readBounded(path, "profile capsule")) : loadFrozenProfile();
}

function verifyVectors() {
  const vectors = loadCrossplayVectors();
  const profile = loadFrozenProfile();
  const registry = loadFrozenRegistry();
  let bytes = 0;
  let positive = 0;
  for (const vector of vectors.golden) {
    const source = fromFixtureJson(vector.message);
    const expected = Buffer.from(vector.frame_base64, "base64");
    const encoded = encodeMessage(source, profile);
    if (!encoded.equals(expected)) throw new Error(`${vector.id}: encoder mismatch`);
    const decoded = decodeMessage(expected, registry);
    if (!encodeMessage(decoded, profile).equals(expected)) {
      throw new Error(`${vector.id}: decoder/re-encode mismatch`);
    }
    if (sha256Hex(expected) !== vector.frame_sha256) {
      throw new Error(`${vector.id}: frozen digest mismatch`);
    }
    bytes += expected.length;
    positive += 1;
  }

  const negatives = JSON.parse(
    readFileSync(new URL("../vectors/v02_negative_vectors.json", import.meta.url), "utf8"),
  );
  let negative = 0;
  for (const vector of negatives.vectors) {
    const data = Buffer.from(vector.bytes_base64, "base64");
    const digest = createHash("sha256").update(data).digest("hex");
    if (digest !== vector.bytes_sha256) {
      throw new Error(`${vector.id}: frozen negative digest mismatch`);
    }
    try {
      if (vector.kind === "capsule") decodeCapsule(data);
      else decodeMessage(data, registry);
    } catch (error) {
      if (!(error instanceof UrusillaError)) throw error;
      if (!error.message.includes(vector.oracle_error_contains)) {
        throw new Error(`${vector.id}: rejection diagnostic diverged: ${error.message}`);
      }
      negative += 1;
      continue;
    }
    throw new Error(`${vector.id}: negative vector was accepted`);
  }

  return {
    implementation: "dependency-free-nodejs-fallback",
    runtime: process.version,
    positive_vectors_passed: positive,
    negative_vectors_rejected: negative,
    negative_vector_digests_matched: negative,
    negative_diagnostic_substrings_matched: negative,
    total_frame_bytes: bytes,
    profile_capsule_sha256: vectors.profile.capsule_sha256,
    dictionary_id_hex: profileDictionaryId(profile).toString("hex"),
    crossplay_vector_file_sha256: createHash("sha256")
      .update(readFileSync(new URL("../vectors/v02_crossplay.json", import.meta.url)))
      .digest("hex"),
    claim_boundary: "Project-internal cross-language compatibility evidence; not external reproduction.",
  };
}

function main(argv) {
  const [command, ...arguments_] = argv;
  if (command === "verify-vectors" && arguments_.length === 0) {
    process.stdout.write(`${JSON.stringify(verifyVectors(), null, 2)}\n`);
    return;
  }
  if (command === "capsule-info" && arguments_.length <= 1) {
    const profile = loadProfile(arguments_[0]);
    const capsule = arguments_[0]
      ? readBounded(arguments_[0], "profile capsule")
      : Buffer.from(loadCrossplayVectors().profile.capsule_base64, "base64");
    process.stdout.write(
      `${JSON.stringify(
        {
          profile_id: profile.profileId,
          name: profile.name,
          strings: profile.strings.length,
          shapes: profile.shapes.length,
          dictionary_id_hex: profileDictionaryId(profile).toString("hex"),
          capsule_bytes: capsule.length,
          capsule_sha256: sha256Hex(capsule),
        },
        null,
        2,
      )}\n`,
    );
    return;
  }
  if (command === "encode" && (arguments_.length === 2 || arguments_.length === 3)) {
    const [inputPath, outputPath, capsulePath] = arguments_;
    const profile = loadProfile(capsulePath);
    const message = parsePortableJson(
      readBounded(inputPath, "portable JSON document", LIMITS.maxPortableJsonBytes),
    );
    writeFileSync(outputPath, encodeMessage(message, profile));
    return;
  }
  if (command === "decode" && (arguments_.length === 2 || arguments_.length === 3)) {
    const [inputPath, outputPath, capsulePath] = arguments_;
    const profile = loadProfile(capsulePath);
    const registry = new ProfileRegistry([profile]);
    const message = decodeMessage(readBounded(inputPath, "frame"), registry);
    writeFileSync(outputPath, stringifyPortableJson(message), "utf8");
    return;
  }
  throw new Error(usage());
}

try {
  main(process.argv.slice(2));
} catch (error) {
  const code = error instanceof DecodeError ? error.code : error?.code;
  process.stderr.write(`${error.message}${code ? ` [${code}]` : ""}\n`);
  process.exitCode = 2;
}
