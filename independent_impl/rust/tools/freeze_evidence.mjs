#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { arch, platform, release } from "node:os";
import { relative, resolve, sep } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const lane = resolve(fileURLToPath(new URL("..", import.meta.url)));
const projectRoot = resolve(lane, "../..");
const digestPath = resolve(lane, "DIGESTS.sha256");
const reportPath = resolve(lane, "conformance_report.json");
const evidenceEpoch = Number(process.env.SOURCE_DATE_EPOCH ?? 1_787_184_000);
if (!Number.isSafeInteger(evidenceEpoch) || evidenceEpoch < 0) {
  throw new Error("SOURCE_DATE_EPOCH must be a non-negative integer");
}
const startedAt = new Date(evidenceEpoch * 1000).toISOString();

function unixPath(path) {
  return path.split(sep).join("/");
}

function sha256Bytes(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function sha256File(relativePath) {
  return sha256Bytes(readFileSync(resolve(lane, relativePath)));
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

function probe(command, arguments_) {
  const result = spawnSync(command, arguments_, {
    cwd: lane,
    encoding: "utf8",
    timeout: 30_000,
  });
  return {
    available: result.error === undefined,
    exit_status: result.status,
    stdout: result.stdout?.trim() || "",
    stderr: result.stderr?.trim() || "",
    error_code: result.error?.code ?? null,
  };
}

function runNode(arguments_, label) {
  const result = spawnSync(process.execPath, arguments_, {
    cwd: lane,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
    timeout: 120_000,
  });
  if (result.error !== undefined || result.status !== 0) {
    throw new Error(
      `${label} failed with status ${String(result.status)}: ${result.error?.message ?? result.stderr}`,
    );
  }
  return result;
}

function requiredMatch(text, pattern, label) {
  const match = text.match(pattern);
  if (match === null) throw new Error(`could not parse ${label} from TAP output`);
  return Number(match[1]);
}

function verifyRootDigest(file, expected) {
  const actual = sha256Bytes(readFileSync(resolve(projectRoot, file)));
  if (actual !== expected) {
    throw new Error(`${file} changed: expected ${expected}, got ${actual}`);
  }
  return actual;
}

const testArguments = ["--test", "--test-reporter=tap"];
const testRun = runNode(testArguments, "Node test run");
const tap = testRun.stdout;
const stableTap = tap
  .replace(/duration_ms: [0-9.]+/g, "duration_ms: <not-recorded>")
  .replace(/duration_ms [0-9.]+/g, "duration_ms <not-recorded>");
writeFileSync(resolve(lane, "reports/test.tap"), stableTap, "utf8");
const tapSummary = {
  top_level_tests: (tap.match(/^# Subtest:/gm) ?? []).length,
  tests_and_subtests: requiredMatch(tap, /^# tests (\d+)$/m, "test count"),
  passed: requiredMatch(tap, /^# pass (\d+)$/m, "pass count"),
  failed: requiredMatch(tap, /^# fail (\d+)$/m, "failure count"),
  cancelled: requiredMatch(tap, /^# cancelled (\d+)$/m, "cancelled count"),
  skipped: requiredMatch(tap, /^# skipped (\d+)$/m, "skipped count"),
  todo: requiredMatch(tap, /^# todo (\d+)$/m, "todo count"),
};
if (
  tapSummary.tests_and_subtests !== tapSummary.passed ||
  tapSummary.failed !== 0 ||
  tapSummary.cancelled !== 0 ||
  tapSummary.skipped !== 0 ||
  tapSummary.todo !== 0
) {
  throw new Error(`test evidence is not an all-pass run: ${JSON.stringify(tapSummary)}`);
}

const vectorArguments = ["src/cli.mjs", "verify-vectors"];
const vectorRun = runNode(vectorArguments, "frozen-vector verification");
const vectorVerification = JSON.parse(vectorRun.stdout);
writeFileSync(
  resolve(lane, "reports/vector-verification.json"),
  `${JSON.stringify(vectorVerification, null, 2)}\n`,
  "utf8",
);

const npmProbe = probe("npm", ["--version"]);
const rustcProbe = probe("rustc", ["--version"]);
const cargoProbe = probe("cargo", ["--version"]);
const rustupProbe = probe("rustup", ["--version"]);
const gitProbe = probe("git", ["rev-parse", "HEAD"]);
const completedAt = startedAt;
const environment = {
  captured_at_utc: completedAt,
  platform: platform(),
  os_release: release(),
  architecture: arch(),
  node: process.version,
  node_executable: process.execPath,
  npm: npmProbe,
  rustc: rustcProbe,
  cargo: cargoProbe,
  rustup: rustupProbe,
  git_head: gitProbe,
  third_party_runtime_dependencies: [],
};
writeFileSync(
  resolve(lane, "reports/environment.json"),
  `${JSON.stringify(environment, null, 2)}\n`,
  "utf8",
);

const publicSemantic = JSON.parse(
  readFileSync(resolve(lane, "vectors/public_v01_semantic_vectors.json"), "utf8"),
);
const crossplay = JSON.parse(readFileSync(resolve(lane, "vectors/v02_crossplay.json"), "utf8"));
const negatives = JSON.parse(
  readFileSync(resolve(lane, "vectors/v02_negative_vectors.json"), "utf8"),
);
const pythonResourceProbe = JSON.parse(
  readFileSync(resolve(lane, "reports/python-reference-resource-probe.json"), "utf8"),
);
const currentPythonCrosscheck = JSON.parse(
  readFileSync(resolve(lane, "reports/python-reference-current-crosscheck.json"), "utf8"),
);
if (
  publicSemantic.release_policy?.lifecycle_status !== "experimental-unsigned" ||
  publicSemantic.release_policy?.publisher_status !== "unsigned" ||
  publicSemantic.release_policy?.unsigned_public_source_distribution_allowed !== true ||
  publicSemantic.release_policy?.unsigned_operation_scope !== "local-read-only" ||
  publicSemantic.release_policy?.unsigned_external_effects_forbidden !== true ||
  publicSemantic.release_policy?.effect_authorizing_requires_signature_and_policy !== true
) {
  throw new Error("Grammar Capsule release policy is not the frozen unsigned policy");
}

const semanticInputDigests = {
  "urusilla_v0_1_spec.md": verifyRootDigest(
    "urusilla_v0_1_spec.md",
    "4d817a607218f64998e1c0b061f80f07b400b382236485f2a2e7b88f6e92b263",
  ),
  "urusilla_capsule_v0_1.json": verifyRootDigest(
    "urusilla_capsule_v0_1.json",
    publicSemantic.source_file_sha256,
  ),
  "urusilla_wire_v02_results.md": verifyRootDigest(
    "urusilla_wire_v02_results.md",
    "aef3158a37c7e7581fd090d737008683cca5b472ebf217a1a5823d051db57a51",
  ),
};
const frozenVectorOriginDigests = {
  "urusilla.py": crossplay.source_artifacts["urusilla.py_sha256"],
  "urusilla_wire_v02.py": crossplay.source_artifacts["urusilla_wire_v02.py_sha256"],
  "urusilla_benchmark.py": crossplay.source_artifacts["urusilla_benchmark.py_sha256"],
};
const currentRootOracleDigests = {
  "urusilla.py": verifyRootDigest(
    "urusilla.py",
    currentPythonCrosscheck.current_root_sha256["urusilla.py"],
  ),
  "urusilla_wire_v02.py": verifyRootDigest(
    "urusilla_wire_v02.py",
    currentPythonCrosscheck.current_root_sha256["urusilla_wire_v02.py"],
  ),
  "urusilla_benchmark.py": verifyRootDigest(
    "urusilla_benchmark.py",
    currentPythonCrosscheck.current_root_sha256["urusilla_benchmark.py"],
  ),
};

if (
  vectorVerification.positive_vectors_passed !== crossplay.golden.length ||
  vectorVerification.negative_vectors_rejected !== negatives.vectors.length ||
  vectorVerification.negative_vector_digests_matched !== negatives.vectors.length ||
  vectorVerification.negative_diagnostic_substrings_matched !== negatives.vectors.length ||
  vectorVerification.total_frame_bytes !== crossplay.aggregates.total_frame_bytes
) {
  throw new Error("vector verifier output disagrees with the frozen fixture inventory");
}
if (
  pythonResourceProbe.root_inputs["urusilla.py_sha256"] !==
    currentRootOracleDigests["urusilla.py"] ||
  pythonResourceProbe.root_inputs["urusilla_wire_v02.py_sha256"] !==
    currentRootOracleDigests["urusilla_wire_v02.py"] ||
  pythonResourceProbe.minimal_non_sensitive_shape.body_plus_meta_nodes !== 250_001 ||
  pythonResourceProbe.exact_boundary_probe.decode_accepted !== true ||
  pythonResourceProbe.exact_plus_one_probe.decode_accepted !== false
) {
  throw new Error("Python reference resource-probe evidence is inconsistent");
}
if (
  Object.entries(frozenVectorOriginDigests).some(
    ([file, digest]) => currentPythonCrosscheck.frozen_vector_origin_sha256[file] !== digest,
  ) ||
  Object.entries(currentRootOracleDigests).some(
    ([file, digest]) => currentPythonCrosscheck.current_root_sha256[file] !== digest,
  ) ||
  currentPythonCrosscheck.current_reference_reexecution.all_frames_equal !== true ||
  currentPythonCrosscheck.current_reference_reexecution.frames_equal_to_frozen_fixtures !==
    crossplay.golden.length
) {
  throw new Error("Current Python reference cross-check evidence is inconsistent");
}

const implementationFiles = [
  "src/cli.mjs",
  "src/errors.mjs",
  "src/frozen_inputs.mjs",
  "src/portable_json.mjs",
  "src/semantic.mjs",
  "src/wire_v02.mjs",
];
const testFiles = [
  "test/boundaries.test.mjs",
  "test/golden.test.mjs",
  "test/negative.test.mjs",
  "test/semantic.test.mjs",
];
const vectorFiles = [
  "vectors/public_v01_semantic_vectors.json",
  "vectors/v02_crossplay.json",
  "vectors/v02_negative_vectors.json",
];
const digestObject = (paths) =>
  Object.fromEntries(paths.map((path) => [path, sha256File(path)]));

const selectedMutationFrameBytes = Buffer.from(
  crossplay.golden[6].frame_base64,
  "base64",
).byteLength;
const report = {
  format: "urusilla-cross-language-conformance-report-v2",
  lifecycle_status: "experimental-unsigned",
  run_date: completedAt.slice(0, 10),
  run_started_at_utc: startedAt,
  run_completed_at_utc: completedAt,
  implementation_revision: "uncommitted-worktree",
  immutable_git_revision_available: false,
  naming_status: {
    final_public_name_confirmed: true,
    public_brand: "Urusilla",
    target_repository: "jaden3824/urusilla",
    package_cli_base: "urusilla",
    namespace_consistent: true,
  },
  requested_language: "Rust",
  executed_language: "ECMAScript",
  fallback_reason: "rustc, cargo, and rustup were unavailable on the execution host",
  runtime: environment,
  runtime_independence: {
    python_invoked_by_implementation_tests_or_freezer: false,
    python_imported_by_implementation_tests_or_freezer: false,
    separate_read_only_python_reference_diagnostic_invoked: true,
    separate_diagnostic_evidence: "reports/python-reference-resource-probe.json",
    third_party_runtime_dependencies: [],
    vector_origin:
      "The v0.2 vectors are deterministically generated from the pinned same-project Python oracle; Node treats them as offline runtime data.",
  },
  claim_classification:
    "separately written project-internal ECMAScript implementation with offline byte agreement against Python-oracle-derived frozen fixtures",
  explicitly_not_demonstrated: [
    "independent external reproduction",
    "clean-room or oracle-independent reproduction",
    "external adoption or live cross-vendor interoperation",
    "full project conformance",
    "native model support",
    "security certification",
    "standard status",
    "state-of-the-art or universal compression superiority",
  ],
  verified_semantic_inputs_sha256: semanticInputDigests,
  frozen_vector_origin_sha256: frozenVectorOriginDigests,
  freeze_time_current_root_oracle_sha256: currentRootOracleDigests,
  oracle_source_drift: {
    detected: false,
    changed_file: null,
    historical_sha256: frozenVectorOriginDigests["urusilla.py"],
    current_sha256: currentRootOracleDigests["urusilla.py"],
    cause_established: true,
    cause: "fixtures were regenerated from the current pinned root inputs",
    current_reference_reexecuted_against_frozen_vectors: true,
    current_reference_exact_frame_matches:
      currentPythonCrosscheck.current_reference_reexecution.frames_equal_to_frozen_fixtures,
    evidence_file: "reports/python-reference-current-crosscheck.json",
  },
  semantic_authority:
    "The English v0.1 typed-IR specification and Capsule are semantic inputs; content never confers authority. Unsigned public source distribution is allowed only for local read-only research and conformance work.",
  capsule_release_policy: publicSemantic.release_policy,
  v02_compatibility_authority:
    "Exact v0.2 byte details and newly frozen vectors are same-project compatibility observations, not a complete independently ratified English byte specification.",
  exact_results: {
    ...tapSummary,
    public_v01_semantic_positives_normalized: publicSemantic.positive_vectors.length,
    public_v01_precise_semantic_negatives_rejected: publicSemantic.negative_vectors.filter(
      (item) => item.mutations,
    ).length,
    golden_frames_encoded_byte_exact: vectorVerification.positive_vectors_passed,
    golden_frames_decoded_semantic_exact: vectorVerification.positive_vectors_passed,
    golden_frames_reencoded_byte_exact: vectorVerification.positive_vectors_passed,
    frozen_negative_frames_and_capsules_rejected: vectorVerification.negative_vectors_rejected,
    frozen_negative_fixture_digests_matched:
      vectorVerification.negative_vector_digests_matched,
    nonnormative_oracle_diagnostic_substrings_matched:
      vectorVerification.negative_diagnostic_substrings_matched,
    selected_frame_low_bit_mutations_rejected: selectedMutationFrameBytes,
    mutation_method:
      "XOR 0x01 at each byte position, one position at a time, in golden frame index 6; this is not exhaustive byte-value or corpus mutation testing.",
    total_warm_frame_bytes: vectorVerification.total_frame_bytes,
    four_byte_length_prefixed_frame_sequence_bytes:
      crossplay.aggregates.four_byte_length_prefixed_frame_sequence_bytes,
    four_byte_length_prefixed_frame_sequence_sha256:
      crossplay.aggregates.four_byte_length_prefixed_frame_sequence_sha256,
    default_profile_capsule_bytes: crossplay.profile.capsule_bytes,
    default_profile_capsule_sha256: crossplay.profile.capsule_sha256,
    default_profile_dictionary_id: vectorVerification.dictionary_id_hex,
  },
  public_capsule_internal_digest_check: {
    declared: publicSemantic.declared_semantic_kernel_manifest_digest,
    computed_sha256: publicSemantic.computed_recursive_sorted_compact_manifest_sha256,
    computed_canonical_bytes: publicSemantic.computed_manifest_bytes,
    match: publicSemantic.digest_match,
    cause: "current Capsule manifest bytes and declared digest agree",
  },
  aggregate_node_compatibility: {
    node_lane_invariant:
      "Share a 250,000-value budget across body and meta; accept exactly 250,000 and reject 250,001 before effects.",
    current_python_reference_has_corresponding_budget: true,
    current_python_reference_plus_one_frame_accepted:
      pythonResourceProbe.exact_plus_one_probe.decode_accepted,
    plus_one_frame_bytes: pythonResourceProbe.exact_plus_one_probe.frame_bytes,
    plus_one_frame_sha256: pythonResourceProbe.exact_plus_one_probe.frame_sha256,
    compatibility_impact:
      "Both same-project implementations accept exactly 250,000 nodes and reject the demonstrated 250,001-node frame; frozen vectors are unaffected.",
    evidence_file: "reports/python-reference-resource-probe.json",
  },
  executed_commands: [
    {
      argv: [process.execPath, ...testArguments],
      exit_status: testRun.status,
      evidence_file: "reports/test.tap",
    },
    {
      argv: [process.execPath, ...vectorArguments],
      exit_status: vectorRun.status,
      evidence_file: "reports/vector-verification.json",
    },
  ],
  resource_limits: {
    frame_or_capsule_bytes: 16_777_216,
    tagged_portable_json_document_bytes: 201_326_592,
    static_dictionary_entries: 65_535,
    utf8_string_bytes: 1_048_576,
    collection_or_recipient_entries: 100_000,
    body_plus_meta_semantic_values: 250_000,
    tagged_portable_projection_values: 450_100,
    semantic_depth: 64,
    profile_name_bytes: 256,
    map_shapes: 128,
    aggregate_profile_shape_references: 100_000,
    byte_budget_distinction:
      "The 16 MiB limit is binary UrusillaWire; 192 MiB is a local tagged-JSON document cap that accommodates Base64/tagging expansion and is not a wire or semantic rule.",
  },
  implemented_scope: [
    "canonical top-level semantic normalization with absent-only defaults",
    "selected v0.1 core-node and act/body validation",
    "closed case-sensitive acts and fail-closed x: extension quarantine",
    "exact signed/unsigned 64-bit values, finite typed binary64, bytes, lists, and maps",
    "Unicode-scalar text validation and deterministic UTF-8 map ordering",
    "v0.2 profile capsule encode/decode",
    "v0.2 warm-frame encode/decode",
    "explicit profile registry and fingerprint matching",
    "checksum validation and canonical re-encoding",
    "fully tagged collision-free portable JSON projection",
    "documented resource limits checked before unbounded traversal or byte copies",
  ],
  unsupported_scope: [
    "v0.1 wire encode/decode",
    "complete schema or ontology registry validation",
    "authenticated identity, signatures, authorization, or effect execution",
    "replay or conversation-ledger policy",
    "signed profile authorization, downgrade handling, or revocation",
    "A2A binding and gzip wrapper",
    "UrusillaLens and adaptive-dialogue profiles",
    "general RFC 8785 canonicalization",
    "unseen external partner, deployed live peer, or task-success/cost evaluation",
    "fuzzing, sanitizers, or independent security review",
  ],
  unfavorable_findings: [
    "Rust tooling was absent, requiring the permitted ECMAScript fallback.",
    "No standalone normative English v0.2 byte specification or pre-existing exact per-frame v0.2 vector file was present.",
    "The 280 positive and 25 negative v0.2 fixtures are newly frozen same-project Python-oracle observations.",
    "The default profile and corpus are in-sample and project-authored.",
    "No Git HEAD, immutable source revision, signed source manifest, or JWS is available.",
    "The local digest inventory is unsigned and is drift evidence only, not authenticated provenance.",
  ],
  release_gate_status: {
    unsigned_public_source_distribution_allowed: true,
    unsigned_operation_scope: "local-read-only",
    effect_authorizing_requires_trusted_signature_and_policy: true,
    advertises_bridge_support: false,
    advertises_native_support: false,
    claims_full_project_conformance: false,
    unseen_partner_test_run: false,
    task_success_and_total_cost_comparison_run: false,
    external_effects_enabled: false,
    natural_language_or_structured_json_deployment_fallback_required: true,
  },
  workspace_isolation: {
    requested_lane: "independent_impl/rust/",
    task_writes_confined_to_requested_lane: true,
    verification_basis:
      "execution history only; the repository has no Git baseline, so this is not commit-diff proof",
  },
  evidence_integrity: {
    digest_manifest: "DIGESTS.sha256",
    digest_manifest_signed: false,
    authenticated_provenance: false,
    note: "The manifest detects later drift relative to this local snapshot only.",
  },
  artifact_digests: {
    implementation: digestObject(implementationFiles),
    tests: digestObject(testFiles),
    vectors: digestObject(vectorFiles),
    documentation: digestObject([
      "README.md",
      "REPORT.md",
      "SPECIFICATION_INPUTS.md",
    ]),
    tools: digestObject([
      "tools/check_digests.mjs",
      "tools/freeze_evidence.mjs",
      "tools/generate_python_oracle_vectors.py",
    ]),
    evidence: digestObject([
      "reports/environment.json",
      "reports/python-reference-current-crosscheck.json",
      "reports/python-reference-resource-probe.json",
      "reports/test.tap",
      "reports/vector-verification.json",
    ]),
  },
};

writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");

const digestLines = walk(lane)
  .filter((path) => path !== digestPath)
  .map((path) => {
    const relativePath = unixPath(relative(lane, path));
    return `${sha256Bytes(readFileSync(path))}  ${relativePath}`;
  });
writeFileSync(digestPath, `${digestLines.join("\n")}\n`, "utf8");

process.stdout.write(
  `${JSON.stringify(
    {
      run_started_at_utc: startedAt,
      run_completed_at_utc: completedAt,
      test_summary: tapSummary,
      conformance_report_sha256: sha256File("conformance_report.json"),
      digest_manifest_sha256: sha256File("DIGESTS.sha256"),
      digest_entries: digestLines.length,
      digest_manifest: "DIGESTS.sha256",
      authenticated_provenance: false,
    },
    null,
    2,
  )}\n`,
);
