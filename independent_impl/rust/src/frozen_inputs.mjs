import { readFileSync } from "node:fs";
import { decodeCapsule, ProfileRegistry } from "./wire_v02.mjs";

export const CROSSPLAY_VECTOR_URL = new URL("../vectors/v02_crossplay.json", import.meta.url);

let cached;

export function loadCrossplayVectors() {
  if (cached === undefined) {
    cached = JSON.parse(readFileSync(CROSSPLAY_VECTOR_URL, "utf8"));
  }
  return cached;
}

export function loadFrozenProfile() {
  const vectors = loadCrossplayVectors();
  return decodeCapsule(Buffer.from(vectors.profile.capsule_base64, "base64"));
}

export function loadFrozenRegistry() {
  return new ProfileRegistry([loadFrozenProfile()]);
}
