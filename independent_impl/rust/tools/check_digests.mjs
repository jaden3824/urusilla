#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const lane = resolve(fileURLToPath(new URL("..", import.meta.url)));
const manifestPath = resolve(lane, "DIGESTS.sha256");

function unixPath(path) {
  return path.split(sep).join("/");
}

function walk(directory) {
  const files = [];
  for (const name of readdirSync(directory).sort()) {
    if (name === "node_modules" || name === ".DS_Store") continue;
    const path = resolve(directory, name);
    if (statSync(path).isDirectory()) files.push(...walk(path));
    else files.push(path);
  }
  return files;
}

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

const expected = new Map();
for (const line of readFileSync(manifestPath, "utf8").trimEnd().split("\n")) {
  const match = line.match(/^([0-9a-f]{64})  (.+)$/);
  if (match === null || expected.has(match[2])) {
    throw new Error(`invalid or duplicate digest-manifest line: ${line}`);
  }
  expected.set(match[2], match[1]);
}

const actualPaths = walk(lane)
  .filter((path) => path !== manifestPath)
  .map((path) => unixPath(relative(lane, path)));
const failures = [];
for (const path of actualPaths) {
  if (!expected.has(path)) failures.push(`${path}: missing from manifest`);
}
for (const [path, digest] of expected) {
  const absolute = resolve(lane, path);
  if (!existsSync(absolute)) failures.push(`${path}: file is missing`);
  else if (sha256(absolute) !== digest) failures.push(`${path}: digest mismatch`);
}
if (failures.length > 0) {
  process.stderr.write(`${failures.join("\n")}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(
    `${JSON.stringify(
      {
        checked_entries: expected.size,
        digest_manifest_sha256: sha256(manifestPath),
        authenticated_provenance: false,
      },
      null,
      2,
    )}\n`,
  );
}
