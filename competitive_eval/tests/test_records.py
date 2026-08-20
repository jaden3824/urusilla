from __future__ import annotations

import unittest

from competitive_eval.errors import ParseFailure
from competitive_eval.records import (
    Evidence,
    QARecord,
    parse_answer_tag,
    parse_canonical_record,
    parse_cte,
    render_cte,
)


class StrictRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = QARecord(
            answer="Paris",
            claims=("France has a capital",),
            evidence=(Evidence("The source names Paris", "A"),),
            needs=(),
            act="agree",
        )

    def test_json_and_cte_round_trip(self) -> None:
        self.assertEqual(parse_canonical_record(self.record.canonical_text), self.record)
        self.assertEqual(parse_cte(render_cte(self.record)), self.record)

    def test_json_rejects_duplicates_unknowns_whitespace_and_types(self) -> None:
        invalid = (
            '{"a":"Paris","a":"Lyon","c":[],"e":[],"n":[],"x":"agree"}',
            '{"a":"Paris","c":[],"e":[],"n":[],"x":"agree","z":0}',
            '{"a": "Paris","c":[],"e":[],"n":[],"x":"agree"}',
            '{"a":"Paris","c":"bad","e":[],"n":[],"x":"agree"}',
            '{"a":"Paris","c":[],"e":[],"n":[],"x":"execute"}',
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ParseFailure):
                    parse_canonical_record(value)

    def test_cte_rejects_extra_lines_and_ambiguous_evidence(self) -> None:
        with self.assertRaises(ParseFailure):
            parse_cte(render_cte(self.record) + "\nEXTRA")
        with self.assertRaises(ParseFailure):
            parse_cte(
                "ACT: agree\nCLAIM: x\nEVIDENCE: [C] fact\nNEED: NONE\nANSWER: Paris"
            )

    def test_opaque_parser_does_not_invent_unresolved_request_state(self) -> None:
        parsed = parse_answer_tag("arbitrary mock surface\nANSWER: Paris")
        self.assertEqual(parsed.answer, "Paris")
        self.assertFalse(parsed.unresolved_request_known)
        with self.assertRaises(ParseFailure):
            parse_answer_tag("ANSWER: Paris\ntrailing prose")


if __name__ == "__main__":
    unittest.main()

