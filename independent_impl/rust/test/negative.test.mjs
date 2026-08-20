import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";

import { DecodeError } from "../src/errors.mjs";
import { loadFrozenRegistry } from "../src/frozen_inputs.mjs";
import { decodeCapsule, decodeMessage } from "../src/wire_v02.mjs";

const negativeVectors = JSON.parse(
  readFileSync(new URL("../vectors/v02_negative_vectors.json", import.meta.url), "utf8"),
);

test("all 25 frozen negative frame and capsule vectors fail closed", async (context) => {
  const registry = loadFrozenRegistry();
  for (const vector of negativeVectors.vectors) {
    await context.test(vector.id, () => {
      const bytes = Buffer.from(vector.bytes_base64, "base64");
      assert.equal(createHash("sha256").update(bytes).digest("hex"), vector.bytes_sha256);
      let rejection;
      try {
        if (vector.kind === "capsule") decodeCapsule(bytes);
        else decodeMessage(bytes, registry);
      } catch (error) {
        rejection = error;
      }
      assert.ok(rejection instanceof DecodeError, `${vector.id}: expected DecodeError`);
      assert.ok(
        rejection.message.includes(vector.oracle_error_contains),
        `${vector.id}: ${JSON.stringify(rejection.message)}`,
      );
    });
  }
});

test("one low-bit flip at every byte position of one frozen frame is rejected", () => {
  const registry = loadFrozenRegistry();
  const crossplay = JSON.parse(
    readFileSync(new URL("../vectors/v02_crossplay.json", import.meta.url), "utf8"),
  );
  const frame = Buffer.from(crossplay.golden[6].frame_base64, "base64");
  for (let position = 0; position < frame.length; position += 1) {
    const damaged = Buffer.from(frame);
    damaged[position] ^= 1;
    assert.throws(() => decodeMessage(damaged, registry), DecodeError, `position ${position}`);
  }
});
