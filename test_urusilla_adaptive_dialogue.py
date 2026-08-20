#!/usr/bin/env python3
"""Dependency-free tests for the adaptive semantic dialogue experiment."""

from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import re
import unittest

import urusilla_adaptive_dialogue as dialogue


EXPECTED_PROFILE_DIGEST = "sha256:074498c7a6054c2759e96b0aeaea3f5e527962ed79180af3d7ef20d652cf1744"
EXPECTED_CORPUS_DIGEST = "sha256:af65510aeb9a7bf26b0ccb265783cc3f0082fb37f183aea3f37527e68fb7ee13"
EXPECTED_LEDGER_DIGEST = "sha256:0ae2147fa81c3822284740e41118f1bbea292aa2a060232b94e8d9b74b92ecc2"
EXPECTED_DELTA_DIGEST = "sha256:5ee939068aa36e099732c2a428020305a35c0a6eeb5ed19eef65f614e5f4fa70"
EXPECTED_RATIFIED_DIGEST = "sha256:c126d6f790101acb65482717c86c6279170d7c88e698464fdb00ccf9c3a6533c"


class ProfileAndCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = dialogue.default_profile_document()
        cls.corpus = dialogue.build_positive_coverage_corpus(cls.profile)

    def test_profile_is_content_addressed_and_byte_stable(self) -> None:
        validated = dialogue.validate_profile_document(self.profile)
        self.assertEqual(validated["profile_digest"], EXPECTED_PROFILE_DIGEST)
        self.assertEqual(validated["sequence"], 0)
        self.assertIsNone(validated["parent_digest"])

    def test_generated_profile_artifact_matches_reference(self) -> None:
        path = Path(dialogue.__file__).with_name("urusilla_adaptive_dialogue_profile.json")
        self.assertTrue(path.is_file(), "run urusilla_adaptive_dialogue.py to generate the profile")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded, self.profile)
        dialogue.validate_profile_document(loaded)

    def test_profile_captures_boundary_and_five_stage_north_star(self) -> None:
        payload = self.profile["profile"]
        self.assertEqual(len(payload["north_star_stages"]), 5)
        self.assertEqual(payload["scope"]["internal_reasoning"], "model_specific_and_out_of_scope")
        self.assertEqual(payload["scope"]["chain_of_thought"], "not_requested_or_required")
        self.assertIn("existing_http_tcp", payload["scope"]["transport"])
        self.assertEqual(payload["scope"]["large_modalities"], "content_addressed_external_assets")
        self.assertEqual(payload["status"], "research_fixture_not_official_extension")
        self.assertEqual(payload["core_language_version"], "0.1.0")
        self.assertEqual(payload["core_relationship"], "experimental_external_dialogue_projection")
        self.assertEqual(payload["official_language_claim"], "none")
        self.assertEqual(
            payload["profile_id"],
            "urn:urusilla:experimental:profile:adaptive-dialogue:fixture-1",
        )
        self.assertEqual(payload["governance"]["phase"], "founder_led_experimental_stewardship")
        self.assertIn("Founding Maintainer".lower().replace(" ", "_"), payload["governance"]["core_or_official_ratification"].lower())
        for gate in (
            "semantic_exactness",
            "privacy",
            "hidden_state_compatibility",
            "provenance",
            "energy_task_utility",
            "fallback",
        ):
            self.assertIn(gate, payload["admission_gates"])

    def test_profile_tampering_fails(self) -> None:
        tampered = copy.deepcopy(self.profile)
        tampered["profile"]["version"] = "silently-changed"
        with self.assertRaisesRegex(dialogue.ValidationError, "profile_digest"):
            dialogue.validate_profile_document(tampered)

    def test_rehashed_projection_drift_still_fails(self) -> None:
        tampered = copy.deepcopy(self.profile)
        tampered["profile"]["interaction_projection"][0]["wire_act"] = "RESOLVE"
        unsigned = {key: value for key, value in tampered.items() if key != "profile_digest"}
        tampered["profile_digest"] = dialogue.content_digest(unsigned)
        with self.assertRaisesRegex(dialogue.ValidationError, "interaction_projection"):
            dialogue.validate_profile_document(tampered)

    def test_positive_corpus_covers_all_acts_and_nodes(self) -> None:
        acts = {message["act"] for message in self.corpus}
        functions = {
            dialogue.message_interaction_function(message, self.profile)
            for message in self.corpus
        }
        nodes = set().union(
            *(dialogue.collect_node_kinds(message["body"]) for message in self.corpus)
        )
        self.assertEqual(len(self.corpus), 26)
        self.assertEqual(acts, set(dialogue.CORE_WIRE_ACTS))
        self.assertEqual(len(acts), 7)
        self.assertEqual(functions, set(dialogue.INTERACTION_FUNCTION_BODY_KINDS))
        self.assertEqual(len(functions), 20)
        self.assertEqual(nodes, set(dialogue.NODE_SCHEMAS))
        self.assertEqual(dialogue.content_digest(list(self.corpus)), EXPECTED_CORPUS_DIGEST)

    def test_every_positive_message_is_deterministic(self) -> None:
        for message in self.corpus:
            with self.subTest(act=message["act"], message_id=message["id"]):
                first = dialogue.validate_message(message, self.profile)
                second = dialogue.validate_message(copy.deepcopy(message), self.profile)
                self.assertEqual(first, second)
                self.assertEqual(dialogue.message_digest(first), dialogue.message_digest(second))
                interaction_function, projected_act = dialogue.project_interaction_function(
                    message["body"], self.profile["profile"]
                )
                self.assertEqual(message["act"], projected_act)
                self.assertIn(interaction_function, dialogue.INTERACTION_FUNCTION_BODY_KINDS)

    def test_projection_table_is_closed_and_matches_required_examples(self) -> None:
        payload = self.profile["profile"]
        self.assertEqual(payload["core_wire_acts"], list(dialogue.CORE_WIRE_ACTS))
        self.assertEqual(set(payload["interaction_functions"]), set(dialogue.INTERACTION_FUNCTION_BODY_KINDS))
        rows = payload["interaction_projection"]
        lookup = {
            (row["interaction_function"], row["body_kind"], json.dumps(row["discriminator"], sort_keys=True)): row["wire_act"]
            for row in rows
        }
        self.assertEqual(lookup[("CLARIFY", "clarification", "null")], "QUERY")
        self.assertEqual(lookup[("DISCOVER", "capability_query", "null")], "QUERY")
        self.assertEqual(lookup[("DISCOVER", "capability_advertisement", "null")], "ASSERT")
        self.assertEqual(lookup[("CANCEL", "cancellation", "null")], "RETRACT")
        self.assertEqual(lookup[("PROGRESS", "progress", "null")], "RESOLVE")
        self.assertEqual(lookup[("NEGOTIATE_SCHEMA", "schema_negotiation", "null")], "PROPOSE")
        self.assertNotIn("interaction_intent", dialogue.MESSAGE_FIELDS)
        self.assertNotIn("intent", dialogue.MESSAGE_FIELDS)

    def test_raw_natural_language_literal_is_not_native_coverage(self) -> None:
        with self.assertRaisesRegex(dialogue.ValidationError, "raw_language_escape"):
            dialogue.validate_node(
                {
                    "kind": "literal",
                    "datatype": "urn:datatype:natural-language",
                    "value": "bridge only",
                },
                self.profile["profile"],
            )

    def test_untyped_mapping_escape_is_rejected(self) -> None:
        message = copy.deepcopy(
            next(
                item
                for item in self.corpus
                if dialogue.message_interaction_function(item, self.profile) == "ASSERT"
                and item["body"]["kind"] == "claim"
            )
        )
        message["body"]["arguments"].append({"text": "untyped"})
        with self.assertRaisesRegex(dialogue.ValidationError, "node_kind"):
            dialogue.validate_message(message, self.profile)

    def test_plan_dag_rejects_cycles(self) -> None:
        message = copy.deepcopy(
            next(
                item
                for item in self.corpus
                if dialogue.message_interaction_function(item, self.profile) == "COORDINATE"
            )
        )
        message["body"]["plan"]["steps"][0]["depends_on"] = ["route"]
        with self.assertRaisesRegex(dialogue.ValidationError, "plan_cycle"):
            dialogue.validate_message(message, self.profile)

    def test_asset_reference_rejects_negative_size(self) -> None:
        node = {
            "kind": "asset_ref",
            "uri": "urn:asset:test",
            "media_type": "image/avif",
            "digest": dialogue.content_digest({"asset": 1}),
            "size_bytes": -1,
        }
        with self.assertRaisesRegex(dialogue.ValidationError, "asset_size"):
            dialogue.validate_node(node, self.profile["profile"])


class ConversationLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = dialogue.default_profile_document()
        self.corpus = dialogue.build_positive_coverage_corpus(self.profile)

    def test_complete_positive_ledger_and_state_machines(self) -> None:
        ledger = dialogue.ConversationLedger(self.profile)
        for message in self.corpus:
            ledger.append(message)
        snapshot = ledger.snapshot()
        self.assertEqual(snapshot["message_count"], 26)
        self.assertEqual(snapshot["ledger_digest"], EXPECTED_LEDGER_DIGEST)
        self.assertEqual(
            set(snapshot["thread_states"].values()),
            {"SUCCEEDED", "FAILED", "CANCELLED", "REFUSED"},
        )
        self.assertEqual(len(snapshot["retracted"]), 1)
        self.assertEqual(len(snapshot["corrections"]), 1)

    def test_negative_corpus_fails_with_exact_codes(self) -> None:
        results = dialogue.run_negative_coverage()
        self.assertEqual(len(results), 20)
        self.assertTrue(all(result["rejected"] for result in results), results)
        self.assertEqual(
            [(result["case_id"], result["observed_code"]) for result in results],
            list(dialogue.NEGATIVE_CASES),
        )

    def test_replay_does_not_mutate_ledger(self) -> None:
        ledger = dialogue.ConversationLedger(self.profile)
        ledger.append(self.corpus[0])
        before = ledger.snapshot()
        with self.assertRaisesRegex(dialogue.LedgerError, "replay"):
            ledger.append(self.corpus[0])
        self.assertEqual(ledger.snapshot(), before)

    def test_missing_cause_does_not_mutate_ledger(self) -> None:
        ledger = dialogue.ConversationLedger(self.profile)
        invalid = copy.deepcopy(self.corpus[0])
        invalid["id"] = dialogue.stable_uuid("test:missing-cause")
        invalid["causes"] = [dialogue.stable_uuid("test:absent")]
        invalid["logical_clock"] = 100
        with self.assertRaisesRegex(dialogue.LedgerError, "missing_cause"):
            ledger.append(invalid)
        self.assertEqual(ledger.snapshot()["message_count"], 0)

    def test_effectful_message_needs_verified_scope(self) -> None:
        invalid = copy.deepcopy(self.corpus[0])
        invalid["authorization"]["verified"] = False
        invalid["authorization"]["scopes"] = []
        with self.assertRaisesRegex(dialogue.ValidationError, "authorization_gate"):
            dialogue.validate_message(invalid, self.profile)

    def test_message_profile_pin_is_hard_gate(self) -> None:
        invalid = copy.deepcopy(self.corpus[2])
        invalid["profile_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(dialogue.ValidationError, "profile_pin"):
            dialogue.validate_message(invalid, self.profile)

    def test_thread_state_is_scoped_by_conversation(self) -> None:
        ledger = dialogue.ConversationLedger(self.profile)
        first = copy.deepcopy(
            next(
                message
                for message in self.corpus
                if dialogue.message_interaction_function(message, self.profile) == "REQUEST"
            )
        )
        first["causes"] = []
        first["logical_clock"] = 1
        ledger.append(first)

        second = copy.deepcopy(first)
        second["id"] = dialogue.stable_uuid("test:second-conversation-request")
        second["conversation_id"] = dialogue.stable_uuid("test:second-conversation")
        second["logical_clock"] = 1
        second["causes"] = []
        ledger.append(second)

        states = ledger.snapshot()["thread_states"]
        self.assertEqual(len(states), 2)
        self.assertEqual(set(states.values()), {"REQUESTED"})

    def test_target_must_match_thread_and_be_causally_reachable(self) -> None:
        ledger = dialogue.ConversationLedger(self.profile)
        for message in self.corpus[:12]:
            ledger.append(message)

        target = self.corpus[10]
        progress = copy.deepcopy(self.corpus[11])
        progress["id"] = dialogue.stable_uuid("test:cross-thread-target")
        progress["thread_id"] = dialogue.stable_uuid("test:other-thread")
        with self.assertRaisesRegex(dialogue.LedgerError, "cross_thread_target"):
            ledger.append(progress)

        no_cause = copy.deepcopy(self.corpus[11])
        no_cause["id"] = dialogue.stable_uuid("test:uncausal-target")
        no_cause["causes"] = []
        no_cause["logical_clock"] = target["logical_clock"] + 1
        with self.assertRaisesRegex(dialogue.LedgerError, "target_causality"):
            ledger.append(no_cause)

        stale_clock = copy.deepcopy(self.corpus[11])
        stale_clock["id"] = dialogue.stable_uuid("test:stale-target-clock")
        stale_clock["causes"] = [self.corpus[0]["id"]]
        stale_clock["logical_clock"] = self.corpus[0]["logical_clock"] + 1
        with self.assertRaisesRegex(dialogue.LedgerError, "target_clock"):
            ledger.append(stale_clock)


class FragmentSplicingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = dialogue.default_profile_document()
        self.original = dialogue.build_positive_coverage_corpus(self.profile)[-1]
        self.receiver = dialogue.ReceiverContext(
            supported_codecs=frozenset(
                {
                    "urusilla-json-fixture@1",
                    "urusilla-wire-v02-fixture@1",
                }
            ),
            verified_schema_digests=frozenset({dialogue.DEFAULT_SCHEMA_DIGEST}),
            verified_profile_digests=frozenset({self.profile["profile_digest"]}),
            execution_authorized=False,
        )

    def replacement(self, *, executable: bool = False) -> dict[str, object]:
        return dialogue.make_splice(
            fragment_id="unsupported-detail",
            role="argument",
            codec="urusilla-json-fixture",
            codec_version="1",
            schema_digest=dialogue.DEFAULT_SCHEMA_DIGEST,
            profile_digest=self.profile["profile_digest"],
            payload=dialogue.canonical_json_bytes({"kind": "literal", "datatype": "urn:datatype:string", "value": "typed"}),
            loss_mode="exact",
            fallback_chain=("urusilla-wire-v02-fixture@1",),
            execution_eligibility=executable,
        )

    def test_unsupported_fragment_requests_only_local_replacement(self) -> None:
        assessment = dialogue.assess_message_fragments(self.original, self.receiver, self.profile)[0]
        self.assertEqual(assessment.status, "replace_fragment")
        request = dialogue.fragment_replacement_request(self.original, assessment)
        self.assertEqual(request["scope"], "fragment_only")
        self.assertEqual(request["fragment_id"], "unsupported-detail")
        self.assertNotIn("message", request)
        self.assertNotIn("body", request)

    def test_patch_changes_exactly_one_fragment(self) -> None:
        patch = dialogue.make_fragment_patch(
            self.original,
            "unsupported-detail",
            self.replacement(),
            self.profile,
        )
        self.assertEqual(
            set(patch),
            {"kind", "message_digest", "fragment_id", "replacement", "patch_digest"},
        )
        updated = dialogue.apply_fragment_patch(self.original, patch, self.profile)
        for field_name in dialogue.MESSAGE_FIELDS - {"body"}:
            self.assertEqual(updated[field_name], self.original[field_name])
        self.assertNotEqual(updated["body"], self.original["body"])
        assessments = dialogue.assess_message_fragments(updated, self.receiver, self.profile)
        self.assertEqual(assessments[0].status, "accepted")

    def test_patch_rejects_whole_message_embedding(self) -> None:
        patch = dialogue.make_fragment_patch(
            self.original,
            "unsupported-detail",
            self.replacement(),
            self.profile,
        )
        patch["message"] = self.original
        with self.assertRaisesRegex(dialogue.ValidationError, "fragment_patch_fields"):
            dialogue.apply_fragment_patch(self.original, patch, self.profile)

    def test_payload_digest_mismatch_fails(self) -> None:
        splice = self.replacement()
        splice["payload_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(dialogue.ValidationError, "splice_payload_digest"):
            dialogue.validate_node(splice, self.profile["profile"])

    def test_unknown_executable_splice_fails(self) -> None:
        splice = dialogue.make_splice(
            fragment_id="latent",
            role="working_state",
            codec="unknown",
            codec_version="1",
            schema_digest=dialogue.DEFAULT_SCHEMA_DIGEST,
            profile_digest=self.profile["profile_digest"],
            payload=b"state",
            loss_mode="exact",
            fallback_chain=("urusilla-json-fixture@1",),
            execution_eligibility=True,
        )
        with self.assertRaisesRegex(dialogue.ValidationError, "splice_unknown_executable"):
            dialogue.validate_node(splice, self.profile["profile"])

    def test_unknown_nonexecuting_splice_is_quarantined(self) -> None:
        splice = dialogue.make_splice(
            fragment_id="latent",
            role="working_state",
            codec="unknown",
            codec_version="1",
            schema_digest=dialogue.DEFAULT_SCHEMA_DIGEST,
            profile_digest=self.profile["profile_digest"],
            payload=b"state",
            loss_mode="opaque",
            fallback_chain=("urusilla-json-fixture@1",),
            execution_eligibility=False,
        )
        receiver = replace(self.receiver, supported_codecs=frozenset({"unknown@1"}))
        assessment = dialogue.assess_splice(splice, receiver, self.profile)
        self.assertEqual(assessment.status, "quarantined")
        self.assertFalse(assessment.executable)

    def test_structural_eligibility_does_not_grant_receiver_authority(self) -> None:
        assessment = dialogue.assess_splice(self.replacement(executable=True), self.receiver, self.profile)
        self.assertEqual(assessment.status, "accepted")
        self.assertFalse(assessment.executable)
        authorized = replace(self.receiver, execution_authorized=True)
        self.assertTrue(dialogue.assess_splice(self.replacement(executable=True), authorized, self.profile).executable)


class CodecSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = dialogue.SelectionPolicy(500, 10_000, 10_000, 950_000, True)
        self.base = dialogue.CodecCandidate(
            codec="eligible",
            version="1",
            receiver_tokens=100,
            encode_latency_us=10,
            decode_latency_us=10,
            risk_ppm=100,
            energy_uj=100,
            task_utility_ppm=999_000,
            semantics_exact=True,
            receiver_capable=True,
            verified=True,
            authorized=True,
            privacy_allowed=True,
            provenance_verified=True,
            fallback_available=True,
        )

    def test_lowest_token_choice_occurs_after_hard_gates(self) -> None:
        decision = dialogue.select_lowest_receiver_token_codec(
            (
                replace(self.base, codec="safe", receiver_tokens=100),
                replace(self.base, codec="unsafe", receiver_tokens=1, privacy_allowed=False),
                replace(
                    self.base,
                    codec="latent",
                    receiver_tokens=2,
                    is_latent=True,
                    hidden_state_compatible=False,
                ),
            ),
            self.policy,
        )
        self.assertEqual(decision.selected.key, "safe@1")
        self.assertIn("privacy", decision.rejected["unsafe@1"])
        self.assertIn("hidden_state_compatibility", decision.rejected["latent@1"])

    def test_every_admission_gate_is_fail_closed(self) -> None:
        variants = {
            "semantic_exactness": {"semantics_exact": False},
            "receiver_capability": {"receiver_capable": False},
            "codec_verification": {"verified": False},
            "authorization": {"authorized": False},
            "latency": {"encode_latency_us": 500},
            "risk": {"risk_ppm": 10_001},
            "energy": {"energy_uj": 10_001},
            "task_utility": {"task_utility_ppm": 949_999},
            "privacy": {"privacy_allowed": False},
            "provenance": {"provenance_verified": False},
            "fallback": {"fallback_available": False},
        }
        for expected_reason, changes in variants.items():
            candidate = replace(self.base, codec=f"bad-{expected_reason}", **changes)
            with self.subTest(gate=expected_reason):
                with self.assertRaisesRegex(dialogue.SelectionError, "no_eligible_codec"):
                    dialogue.select_lowest_receiver_token_codec((candidate,), self.policy)
                reasons = dialogue._candidate_rejections(candidate, self.policy)
                self.assertIn(expected_reason, reasons)

    def test_compatible_latent_path_is_optional_not_privileged(self) -> None:
        compatible = replace(
            self.base,
            codec="latent",
            receiver_tokens=20,
            is_latent=True,
            hidden_state_compatible=True,
        )
        decision = dialogue.select_lowest_receiver_token_codec((self.base, compatible), self.policy)
        self.assertEqual(decision.selected.key, "latent@1")
        incompatible = replace(compatible, codec="latent-bad", hidden_state_compatible=False)
        decision = dialogue.select_lowest_receiver_token_codec((self.base, incompatible), self.policy)
        self.assertEqual(decision.selected.key, "eligible@1")

    def test_tie_break_is_deterministic(self) -> None:
        first = replace(self.base, codec="z-codec")
        second = replace(self.base, codec="a-codec")
        decision = dialogue.select_lowest_receiver_token_codec((first, second), self.policy)
        self.assertEqual(decision.selected.key, "a-codec@1")


class CapsuleGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = dialogue.default_profile_document()
        self.delta = dialogue._proposal_delta(self.profile["profile_digest"])

    def test_delta_digest_uses_immutable_snapshot(self) -> None:
        self.assertEqual(self.delta.digest, EXPECTED_DELTA_DIGEST)
        original_payload = self.delta.payload
        self.delta.changes[0]["kind"] = "mutated-after-construction"
        self.assertEqual(self.delta.digest, EXPECTED_DELTA_DIGEST)
        self.assertEqual(self.delta.payload, original_payload)

    def test_delta_adds_new_version_migration_and_deprecation(self) -> None:
        original = copy.deepcopy(self.profile)
        evolved = dialogue.apply_capsule_delta(self.profile, self.delta)
        self.assertEqual(self.profile, original)
        self.assertEqual(evolved["profile_digest"], EXPECTED_RATIFIED_DIGEST)
        self.assertEqual(evolved["parent_digest"], EXPECTED_PROFILE_DIGEST)
        self.assertIn("literal_v2", evolved["profile"]["node_schemas"])
        self.assertEqual(
            evolved["profile"]["deprecated_symbols"]["literal"]["replacement"],
            "literal_v2",
        )

    def test_non_equivalent_migration_requires_review(self) -> None:
        migration = {
            "from_symbol": "literal",
            "to_symbol": "literal_v2",
            "relation": "narrowing",
        }
        with self.assertRaisesRegex(dialogue.GovernanceError, "migration_review"):
            dialogue.apply_symbol_migration(
                {"kind": "literal", "datatype": "urn:datatype:string", "value": "x"},
                migration,
            )
        migrated = dialogue.apply_symbol_migration(
            {"kind": "literal", "datatype": "urn:datatype:string", "value": "x"},
            migration,
            allow_reviewed_non_equivalent=True,
        )
        self.assertEqual(migrated["kind"], "literal_v2")

    def test_silent_redefinition_fails(self) -> None:
        delta = dialogue.CapsuleDelta(
            base_digest=self.profile["profile_digest"],
            sequence=1,
            proposal_id="redefine",
            changes=(
                {
                    "op": "add_node",
                    "kind": "claim",
                    "schema": {"required": ["changed"], "optional": []},
                    "semantics_digest": dialogue.content_digest({"changed": True}),
                },
            ),
        )
        with self.assertRaisesRegex(dialogue.GovernanceError, "silent_redefinition"):
            dialogue.apply_capsule_delta(self.profile, delta)

    def test_lifecycle_cannot_skip_evidence_stages(self) -> None:
        governance = dialogue.GrammarGovernance()
        governance.propose(self.delta, "governor.agent", authorized=True)
        with self.assertRaisesRegex(dialogue.GovernanceError, "lifecycle_transition"):
            governance.ratify(
                self.delta.proposal_id,
                ("ratifier-a", "ratifier-b"),
                quorum=2,
                authorized=True,
                signed_founding_maintainer_approval=None,
            )

    def test_complete_lifecycle_rollback_deprecation_and_gc(self) -> None:
        governance = dialogue.GrammarGovernance()
        base = governance.store.active_digest
        governance.propose(self.delta, "governor.agent", authorized=True)
        session = dialogue.stable_uuid("test:governance-session")
        governance.begin_session_trial(self.delta.proposal_id, session, authorized=True)
        ephemeral = governance.ephemeral_session_profile(
            self.delta.proposal_id,
            session_id=session,
            negotiated_non_core=True,
            safety_gates_passed=True,
        )
        self.assertEqual(governance.store.active_digest, base)
        self.assertNotEqual(ephemeral["profile_digest"], base)
        governance.record_session_trial(
            self.delta.proposal_id,
            session_id=session,
            implementation="runtime-a",
            exact_roundtrips=10,
            cases=10,
            semantic_mismatches=0,
        )
        governance.promote_cross_play(
            self.delta.proposal_id,
            ("runtime-a", "runtime-b"),
            authorized=True,
        )
        governance.record_cross_play(
            self.delta.proposal_id,
            implementation_a="runtime-a",
            implementation_b="runtime-b",
            exact_roundtrips=10,
            cases=10,
            semantic_mismatches=0,
        )
        signed_approval = dialogue.make_signed_founding_maintainer_approval_fixture(
            governance.proposals[self.delta.proposal_id]
        )
        evolved = governance.ratify(
            self.delta.proposal_id,
            ("ratifier-a", "ratifier-b"),
            quorum=2,
            authorized=True,
            signed_founding_maintainer_approval=signed_approval,
        )
        self.assertEqual(evolved, EXPECTED_RATIFIED_DIGEST)
        ratification_event = governance.proposals[self.delta.proposal_id].events[-1]
        self.assertEqual(
            ratification_event["signed_founding_maintainer_approval_digest"],
            dialogue.content_digest(signed_approval),
        )
        governance.store.rollback(base)
        self.assertEqual(governance.store.active_digest, base)
        self.assertEqual(len(governance.store.profiles), 2)
        orphan = governance.store.add_codebook(b"orphan")
        deleted = governance.store.garbage_collect_codebooks(
            live_session_profiles=(evolved,),
            migration_profiles=(base, evolved),
        )
        self.assertIn(orphan, deleted)
        self.assertEqual(len(governance.store.profiles), 2)
        governance.deprecate(self.delta.proposal_id, base, authorized=True)
        self.assertEqual(governance.proposals[self.delta.proposal_id].state, "deprecated")

    def test_cross_play_requires_independent_implementations(self) -> None:
        governance = dialogue.GrammarGovernance()
        governance.propose(self.delta, "governor.agent", authorized=True)
        session = dialogue.stable_uuid("test:one-runtime")
        governance.begin_session_trial(self.delta.proposal_id, session, authorized=True)
        governance.record_session_trial(
            self.delta.proposal_id,
            session_id=session,
            implementation="runtime-a",
            exact_roundtrips=1,
            cases=1,
            semantic_mismatches=0,
        )
        with self.assertRaisesRegex(dialogue.GovernanceError, "cross_play_independence"):
            governance.promote_cross_play(
                self.delta.proposal_id,
                ("runtime-a", "runtime-a"),
                authorized=True,
            )

    def test_ephemeral_delta_requires_non_core_negotiation_and_safety(self) -> None:
        governance = dialogue.GrammarGovernance()
        governance.propose(self.delta, "governor.agent", authorized=True)
        session = dialogue.stable_uuid("test:ephemeral-policy")
        governance.begin_session_trial(self.delta.proposal_id, session, authorized=True)
        with self.assertRaisesRegex(dialogue.GovernanceError, "ephemeral_scope"):
            governance.ephemeral_session_profile(
                self.delta.proposal_id,
                session_id=session,
                negotiated_non_core=False,
                safety_gates_passed=True,
            )
        with self.assertRaisesRegex(dialogue.GovernanceError, "ephemeral_safety"):
            governance.ephemeral_session_profile(
                self.delta.proposal_id,
                session_id=session,
                negotiated_non_core=True,
                safety_gates_passed=False,
            )

    def test_automated_evidence_cannot_ratify_meaning(self) -> None:
        governance = dialogue.GrammarGovernance()
        governance.propose(self.delta, "governor.agent", authorized=True)
        session = dialogue.stable_uuid("test:founder-approval")
        governance.begin_session_trial(self.delta.proposal_id, session, authorized=True)
        governance.record_session_trial(
            self.delta.proposal_id,
            session_id=session,
            implementation="runtime-a",
            exact_roundtrips=1,
            cases=1,
            semantic_mismatches=0,
        )
        governance.promote_cross_play(
            self.delta.proposal_id,
            ("runtime-a", "runtime-b"),
            authorized=True,
        )
        governance.record_cross_play(
            self.delta.proposal_id,
            implementation_a="runtime-a",
            implementation_b="runtime-b",
            exact_roundtrips=1,
            cases=1,
            semantic_mismatches=0,
        )
        with self.assertRaisesRegex(dialogue.GovernanceError, "founding_maintainer_approval"):
            governance.ratify(
                self.delta.proposal_id,
                ("automated-a", "automated-b"),
                quorum=2,
                authorized=True,
                signed_founding_maintainer_approval=None,
            )
        forged = dialogue.make_signed_founding_maintainer_approval_fixture(
            governance.proposals[self.delta.proposal_id]
        )
        forged["signature_verified"] = False
        with self.assertRaisesRegex(dialogue.GovernanceError, "founding_maintainer_approval"):
            governance.ratify(
                self.delta.proposal_id,
                ("automated-a", "automated-b"),
                quorum=2,
                authorized=True,
                signed_founding_maintainer_approval=forged,
            )


class IntegratedResultTests(unittest.TestCase):
    def test_conformance_summary_is_exact(self) -> None:
        result = dialogue.run_conformance()
        self.assertEqual(result["positive_accepted"], 26)
        self.assertEqual(result["negative_rejected"], 20)
        self.assertEqual(result["acts_covered"], result["acts_total"])
        self.assertEqual(result["nodes_covered"], result["nodes_total"])
        self.assertEqual(
            result["selection"]["selected"],
            "urusilla-wire-v02-fixture@1",
        )
        self.assertEqual(result["acts_covered"], 7)
        self.assertEqual(result["interaction_functions_covered"], 20)
        self.assertRegex(result["grammar"]["signed_approval_evidence_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(result["grammar"]["proposal_state"], "deprecated")
        self.assertTrue(result["grammar"]["orphan_codebook_collected"])
        self.assertTrue(result["grammar"]["ephemeral_global_active_unchanged"])

    def test_all_delivered_artifacts_are_english_only(self) -> None:
        directory = Path(dialogue.__file__).resolve().parent
        for filename in (
            "urusilla_adaptive_dialogue.py",
            "test_urusilla_adaptive_dialogue.py",
            "urusilla_adaptive_dialogue_profile.json",
            "urusilla_adaptive_dialogue_results.md",
        ):
            path = directory / filename
            self.assertTrue(path.is_file(), filename)
            self.assertIsNone(re.search(r"[\uac00-\ud7a3]", path.read_text(encoding="utf-8")), filename)


if __name__ == "__main__":
    unittest.main()
