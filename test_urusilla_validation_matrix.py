#!/usr/bin/env python3
"""Table-driven negative coverage for the semantic and wire boundaries."""

from __future__ import annotations

import copy
import math
import unittest

from urusilla import (
    FLAGS,
    MAGIC,
    MAX_FRAME_BYTES,
    DecodeError,
    ValidationError,
    decode_message,
    demo_message,
    encode_message,
    normalize_message,
    validate_effect_eligibility,
)


def changed(mutator):
    message = copy.deepcopy(demo_message())
    mutator(message)
    return message


def with_body(act: str, body: dict, *, effectful: bool = False) -> dict:
    message = copy.deepcopy(demo_message())
    message["act"] = act
    message["body"] = body
    message["reply_to"] = (
        "20000000-0000-0000-0000-000000000001" if effectful else None
    )
    return message


class TopLevelValidationMatrixTests(unittest.TestCase):
    def test_top_level_type_identity_routing_and_numeric_failures(self) -> None:
        cases = (
            ("mapping", 7, "message must be a mapping"),
            (
                "missing",
                changed(lambda message: message.pop("body")),
                "missing top-level",
            ),
            (
                "id type",
                changed(lambda message: message.__setitem__("id", 7)),
                "canonical UUID",
            ),
            (
                "id spelling",
                changed(lambda message: message.__setitem__("id", message["id"].upper())),
                "lowercase canonical UUID",
            ),
            (
                "empty sender",
                changed(lambda message: message.__setitem__("sender", "")),
                "non-empty string",
            ),
            (
                "sender whitespace",
                changed(lambda message: message.__setitem__("sender", "bad sender")),
                "whitespace",
            ),
            (
                "recipient scalar",
                changed(lambda message: message.__setitem__("recipients", "peer")),
                "non-empty sequence",
            ),
            (
                "empty recipients",
                changed(lambda message: message.__setitem__("recipients", [])),
                "non-empty strings",
            ),
            (
                "recipient type",
                changed(lambda message: message.__setitem__("recipients", [7])),
                "non-empty strings",
            ),
            (
                "duplicate recipients",
                changed(
                    lambda message: message.__setitem__(
                        "recipients", ["peer.agent", "peer.agent"]
                    )
                ),
                "unique",
            ),
            (
                "act type",
                changed(lambda message: message.__setitem__("act", 7)),
                "act must be a string",
            ),
            (
                "unknown act",
                changed(lambda message: message.__setitem__("act", "WHISPER")),
                "unknown communicative act",
            ),
            (
                "clock",
                changed(lambda message: message.__setitem__("logical_clock", -1)),
                "logical_clock",
            ),
            (
                "expiry",
                changed(lambda message: message.__setitem__("expires_ms", True)),
                "expires_ms",
            ),
            (
                "confidence",
                changed(lambda message: message.__setitem__("confidence_ppm", 1_000_001)),
                "confidence_ppm",
            ),
            (
                "expected scalar",
                changed(lambda message: message.__setitem__("expected", "ASSERT")),
                "expected must be a sequence",
            ),
            (
                "expected type",
                changed(lambda message: message.__setitem__("expected", [7])),
                "expected acts must be strings",
            ),
            (
                "expected unknown",
                changed(lambda message: message.__setitem__("expected", ["WHISPER"])),
                "unknown expected act",
            ),
            (
                "meta",
                changed(lambda message: message.__setitem__("meta", [])),
                "meta must be a mapping",
            ),
            (
                "body scalar",
                changed(lambda message: message.__setitem__("body", [])),
                "body must be a semantic node map",
            ),
            (
                "body no kind",
                changed(lambda message: message.__setitem__("body", {"value": 1})),
                "body must declare a node kind",
            ),
        )
        for label, value, pattern in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValidationError, pattern):
                    normalize_message(value)  # type: ignore[arg-type]

    def test_query_and_extension_quarantine_failures(self) -> None:
        cases = (
            (
                changed(
                    lambda message: (
                        message.__setitem__("act", "QUERY"),
                        message.__setitem__("body", {"question": {"kind": "claim", "predicate": "p"}}),
                    )
                ),
                "question and answer_schema",
            ),
            (
                changed(
                    lambda message: (
                        message.__setitem__("act", "QUERY"),
                        message.__setitem__(
                            "body", {"question": "p", "answer_schema": "urn:test:answer"}
                        ),
                    )
                ),
                "question must be a semantic node",
            ),
            (
                changed(
                    lambda message: (
                        message.__setitem__("act", "QUERY"),
                        message.__setitem__(
                            "body",
                            {
                                "question": {"kind": "claim", "predicate": "p"},
                                "answer_schema": "relative",
                            },
                        ),
                    )
                ),
                "absolute URI",
            ),
            (
                changed(lambda message: message.__setitem__("body", {"kind": "x:local", "value": 1})),
                "quarantined to ASSERT",
            ),
        )
        for message, pattern in cases:
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(ValidationError, pattern):
                    normalize_message(message)


class SemanticNodeValidationMatrixTests(unittest.TestCase):
    def test_claim_goal_constraint_and_evidence_failures(self) -> None:
        valid_goal = {"kind": "goal", "condition": {"kind": "claim", "predicate": "p"}}
        cases = (
            (with_body("ASSERT", {"kind": "claim"}), "missing required"),
            (with_body("ASSERT", {"kind": "claim", "predicate": ""}), "non-empty"),
            (
                with_body("ASSERT", {"kind": "claim", "predicate": "p", "arguments": ()}),
                "tuples are not canonical",
            ),
            (
                with_body("ASSERT", {"kind": "claim", "predicate": "p", "context": []}),
                "context must be a map",
            ),
            (
                with_body("ASSERT", {"kind": "claim", "predicate": "p", "answer_limit": 0}),
                "positive integer",
            ),
            (
                with_body("ASSERT", {"kind": "claim", "predicate": "p", "shadow": 1}),
                "unknown field",
            ),
            (
                with_body("REQUEST", {"kind": "goal", "condition": []}),
                "condition must be a semantic node",
            ),
            (
                with_body("REQUEST", {**valid_goal, "priority": "high"}),
                "priority must be an integer",
            ),
            (
                with_body(
                    "REQUEST",
                    {**valid_goal, "constraints": [{"kind": "claim", "predicate": "p"}]},
                ),
                "must contain constraint nodes",
            ),
            (
                with_body(
                    "REQUEST",
                    {
                        **valid_goal,
                        "constraints": [
                            {"kind": "constraint", "scope": "s", "mode": "maybe", "condition": {}}
                        ],
                    },
                ),
                "hard or soft",
            ),
            (
                with_body(
                    "REQUEST",
                    {
                        **valid_goal,
                        "constraints": [
                            {
                                "kind": "constraint",
                                "scope": "s",
                                "mode": "hard",
                                "condition": {},
                                "weight_ppm": -1,
                            }
                        ],
                    },
                ),
                "weight_ppm",
            ),
            (
                with_body(
                    "ASSERT",
                    {
                        "kind": "evidence",
                        "target": {"kind": "claim", "predicate": "p"},
                        "stance": "maybe",
                        "digest": "sha256:aa",
                        "provenance": "run:1",
                    },
                ),
                "stance",
            ),
            (
                with_body(
                    "ASSERT",
                    {
                        "kind": "evidence",
                        "target": {"kind": "claim", "predicate": "p"},
                        "stance": "supports",
                        "digest": "relative",
                        "provenance": "run:1",
                    },
                ),
                "absolute URI",
            ),
            (
                with_body(
                    "ASSERT",
                    {
                        "kind": "evidence",
                        "target": {"kind": "claim", "predicate": "p"},
                        "stance": "supports",
                        "digest": "sha256:aa",
                        "provenance": 7,
                    },
                ),
                "provenance",
            ),
        )
        for message, pattern in cases:
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(ValidationError, pattern):
                    normalize_message(message)

    def test_uncertainty_action_commitment_resolution_and_tree_failures(self) -> None:
        valid_goal = {"kind": "goal", "condition": {"kind": "claim", "predicate": "p"}}
        target = {"kind": "claim", "predicate": "p"}
        cases = (
            (
                with_body(
                    "ASSERT",
                    {"kind": "uncertainty", "target": target, "model": "", "parameters": {}},
                ),
                "non-empty",
            ),
            (
                with_body(
                    "ASSERT",
                    {"kind": "uncertainty", "target": target, "model": "beta", "parameters": []},
                ),
                "parameters must be a map",
            ),
            (
                with_body("PROPOSE", {"kind": "action", "capability": "tool", "arguments": 7}),
                "arguments must be a map or list",
            ),
            (
                with_body(
                    "PROPOSE",
                    {
                        "kind": "action",
                        "capability": "tool",
                        "arguments": {},
                        "declared_effects": [""],
                    },
                ),
                "non-empty strings",
            ),
            (
                with_body(
                    "COMMIT",
                    {
                        "kind": "commitment",
                        "debtor": "planner.agent",
                        "creditors": [],
                        "goal": valid_goal,
                        "expiry_ms": 10,
                    },
                    effectful=True,
                ),
                "non-empty",
            ),
            (
                with_body(
                    "COMMIT",
                    {
                        "kind": "commitment",
                        "debtor": "planner.agent",
                        "creditors": ["peer", "peer"],
                        "goal": valid_goal,
                        "expiry_ms": 10,
                    },
                    effectful=True,
                ),
                "unique",
            ),
            (
                with_body(
                    "COMMIT",
                    {
                        "kind": "commitment",
                        "debtor": "planner.agent",
                        "creditors": ["peer"],
                        "goal": target,
                        "expiry_ms": 10,
                    },
                    effectful=True,
                ),
                "goal node",
            ),
            (
                with_body(
                    "COMMIT",
                    {
                        "kind": "commitment",
                        "debtor": "planner.agent",
                        "creditors": ["peer"],
                        "goal": valid_goal,
                        "expiry_ms": True,
                    },
                    effectful=True,
                ),
                "uint64",
            ),
            (
                with_body(
                    "RESOLVE",
                    {"kind": "resolution", "target": target, "status": "maybe", "result": {}},
                    effectful=True,
                ),
                "status",
            ),
            (
                with_body("ASSERT", {"kind": "ref", "uri": "relative"}),
                "absolute URI",
            ),
            (
                changed(lambda message: message["meta"].__setitem__("nan", math.nan)),
                "NaN and infinity",
            ),
            (
                changed(lambda message: message["meta"].__setitem__("large", 1 << 65)),
                "64-bit",
            ),
            (
                changed(lambda message: message["meta"].__setitem__(7, "bad")),
                "map keys must be strings",
            ),
            (
                changed(lambda message: message["meta"].__setitem__("set", {1, 2})),
                "unsupported semantic value type",
            ),
        )
        for message, pattern in cases:
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(ValidationError, pattern):
                    normalize_message(message)


class BoundaryAndEffectMatrixTests(unittest.TestCase):
    def test_effect_policy_negative_and_registered_extension_paths(self) -> None:
        base = demo_message()
        with self.assertRaisesRegex(ValidationError, "authenticated sender"):
            validate_effect_eligibility(
                base,
                authenticated_sender="other.agent",
                authorized_schemas=[base["schema"]],
            )
        with self.assertRaisesRegex(ValidationError, "schema is not authorized"):
            validate_effect_eligibility(
                base,
                authenticated_sender=base["sender"],
                authorized_schemas=[],
            )

        extension = with_body("ASSERT", {"kind": "x:private", "value": 1})
        with self.assertRaisesRegex(ValidationError, "unregistered extension"):
            validate_effect_eligibility(
                extension,
                authenticated_sender=extension["sender"],
                authorized_schemas=[extension["schema"]],
            )
        accepted = validate_effect_eligibility(
            extension,
            authenticated_sender=extension["sender"],
            authorized_schemas=[extension["schema"]],
            registered_extension_kinds=["x:private"],
        )
        self.assertEqual(accepted["body"]["kind"], "x:private")

    def test_wire_outer_boundary_failures(self) -> None:
        frame = encode_message(demo_message())
        cases = (
            (bytearray(frame), "frame must be bytes"),
            (b"x" * (MAX_FRAME_BYTES + 1), "frame exceeds size limit"),
            (b"", "truncated frame"),
            (b"BAD" + frame[3:], "unsupported magic"),
            (frame[: len(MAGIC)] + bytes([FLAGS ^ 1]) + frame[len(MAGIC) + 1 :], "flags"),
            (frame[:-1], "payload length does not match"),
        )
        for candidate, pattern in cases:
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(DecodeError, pattern):
                    decode_message(candidate)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
