"""Focused conformance and adversarial tests for UrusillaTokenSurface v0.3."""

from __future__ import annotations

import hashlib
import unittest

from urusilla_benchmark import build_corpus
from urusilla import DecodeError, MAX_FRAME_BYTES, ValidationError
from urusilla_token_surface_v03 import (
    ALPHABET_SHA256,
    CODEBOOK_SYMBOLS,
    EXPECTED_CODEBOOK_SHA256,
    MAX_ENTRY_BYTES,
    SURFACE_CHECKSUM_SYMBOLS,
    TokenCodebook,
    decode_codebook_capsule,
    decode_codebook_capsule_text,
    decode_message,
    development_codebook,
    encode_codebook_capsule,
    encode_codebook_capsule_text,
    encode_message,
)


class TokenSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.codebook = development_codebook()
        cls.corpus = build_corpus(280)

    def test_frozen_content_addresses(self) -> None:
        self.assertEqual(len(self.codebook.entries), CODEBOOK_SYMBOLS)
        self.assertEqual(self.codebook.sha256, EXPECTED_CODEBOOK_SHA256)
        self.assertEqual(
            hashlib.sha256(self.codebook.alphabet.encode("utf-8")).hexdigest(),
            ALPHABET_SHA256,
        )

    def test_codebook_capsule_exact_roundtrip(self) -> None:
        capsule = encode_codebook_capsule(self.codebook)
        decoded = decode_codebook_capsule(capsule)
        self.assertEqual(decoded, self.codebook)
        self.assertEqual(encode_codebook_capsule(decoded), capsule)
        text = encode_codebook_capsule_text(self.codebook)
        self.assertEqual(decode_codebook_capsule_text(text), self.codebook)
        self.assertEqual(encode_codebook_capsule_text(decode_codebook_capsule_text(text)), text)

    def test_all_messages_exact_and_deterministic(self) -> None:
        for message in self.corpus:
            first = encode_message(message, self.codebook)
            self.assertEqual(encode_message(message, self.codebook), first)
            self.assertEqual(decode_message(first, self.codebook), message)

    def test_surface_payload_is_printable_data_only(self) -> None:
        surface = encode_message(self.corpus[0], self.codebook)
        self.assertEqual(surface[:2], "S3")
        self.assertEqual(surface[2], self.codebook.alphabet[0])
        payload = surface[3:-SURFACE_CHECKSUM_SYMBOLS]
        checksum = surface[-SURFACE_CHECKSUM_SYMBOLS:]
        self.assertTrue(payload)
        self.assertTrue(all(not character.isascii() for character in payload))
        self.assertTrue(all(character.isprintable() and not character.isspace() for character in payload))
        self.assertNotIn("<", surface)
        self.assertNotIn(">", surface)
        self.assertEqual(len(checksum), SURFACE_CHECKSUM_SYMBOLS)

    def test_single_symbol_corruption_is_rejected(self) -> None:
        surface = encode_message(self.corpus[9], self.codebook)
        start = 3
        end = len(surface) - SURFACE_CHECKSUM_SYMBOLS
        payload = list(surface[start:end])
        index = len(payload) // 2
        original_index = self.codebook.alphabet.index(payload[index])
        payload[index] = self.codebook.alphabet[(original_index + 1) % CODEBOOK_SYMBOLS]
        with self.assertRaises(DecodeError):
            decode_message(surface[:start] + "".join(payload) + surface[end:], self.codebook)

    def test_unknown_codebook_and_unknown_symbol_are_rejected(self) -> None:
        surface = encode_message(self.corpus[10], self.codebook)
        wrong_slot = surface[:2] + self.codebook.alphabet[1] + surface[3:]
        with self.assertRaises(DecodeError):
            decode_message(wrong_slot, self.codebook)
        end = len(surface) - SURFACE_CHECKSUM_SYMBOLS
        unknown_symbol = surface[:end] + "A" + surface[end:]
        with self.assertRaises(DecodeError):
            decode_message(unknown_symbol, self.codebook)

    def test_negotiated_nonzero_slot_roundtrip(self) -> None:
        surface = encode_message(self.corpus[12], self.codebook, slot=517)
        self.assertEqual(surface[2], self.codebook.alphabet[517])
        self.assertEqual(decode_message(surface, self.codebook, slot=517), self.corpus[12])
        with self.assertRaises(DecodeError):
            decode_message(surface, self.codebook, slot=0)

    def test_malformed_and_noncanonical_surfaces_are_rejected(self) -> None:
        surface = encode_message(self.corpus[11], self.codebook)
        cases = [
            surface + "A",
            "S4" + surface[2:],
            surface[:-1] + "=",
            "S3" + self.codebook.alphabet[0] + "\n" + surface[-SURFACE_CHECKSUM_SYMBOLS:],
            "S3" + self.codebook.alphabet[0] + surface[-SURFACE_CHECKSUM_SYMBOLS:],
        ]
        for case in cases:
            with self.subTest(case=case[:30]):
                with self.assertRaises(DecodeError):
                    decode_message(case, self.codebook)

    def test_codebook_capsule_checksum_is_enforced(self) -> None:
        capsule = bytearray(self.codebook.capsule)
        capsule[len(capsule) // 2] ^= 1
        with self.assertRaises(DecodeError):
            decode_codebook_capsule(bytes(capsule))

    def test_codebook_requires_complete_byte_fallback(self) -> None:
        entries = list(self.codebook.entries)
        entries[0] = b"duplicate"
        with self.assertRaises(ValidationError):
            TokenCodebook(
                self.codebook.corpus_sha256,
                self.codebook.profile_dictionary_id,
                self.codebook.alphabet,
                tuple(entries),
            )

    def test_codebook_entry_resource_limit(self) -> None:
        entries = list(self.codebook.entries)
        entries[-1] = b"x" * (MAX_ENTRY_BYTES + 1)
        with self.assertRaises(ValidationError):
            TokenCodebook(
                self.codebook.corpus_sha256,
                self.codebook.profile_dictionary_id,
                self.codebook.alphabet,
                tuple(entries),
            )

    def test_decoded_frame_expansion_limit(self) -> None:
        # Exercise the limit without allocating or parsing a dangerous wire frame.
        entries = tuple(bytes([value]) for value in range(256)) + (b"x" * MAX_ENTRY_BYTES,)
        alphabet = self.codebook.alphabet[:257]
        limited = TokenCodebook(
            self.codebook.corpus_sha256,
            self.codebook.profile_dictionary_id,
            alphabet,
            entries,
        )
        payload = alphabet[-1] * (MAX_FRAME_BYTES // MAX_ENTRY_BYTES + 1)
        fake = "S3" + alphabet[0] + payload + alphabet[0] * SURFACE_CHECKSUM_SYMBOLS
        with self.assertRaisesRegex(DecodeError, "decoded v0.2 frame exceeds"):
            decode_message(fake, limited)


if __name__ == "__main__":
    unittest.main()
