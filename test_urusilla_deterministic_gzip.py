import gzip
import hashlib
import unittest

from urusilla_deterministic_gzip import compress


class DeterministicGzipTests(unittest.TestCase):
    def test_frozen_member_and_round_trip(self) -> None:
        source = b"hello world" * 100
        member = compress(source, compresslevel=6)
        self.assertEqual(len(member), 41)
        self.assertEqual(member[:10].hex(), "1f8b08000000000000ff")
        self.assertEqual(
            hashlib.sha256(member).hexdigest(),
            "a4e5ab99003854c27c0eaa7db0f29a38147ec2e49e843ec533ddbd8d58d88852",
        )
        self.assertEqual(gzip.decompress(member), source)
        self.assertEqual(compress(source, compresslevel=6), member)

    def test_input_and_level_validation(self) -> None:
        with self.assertRaises(TypeError):
            compress(bytearray(b"data"))  # type: ignore[arg-type]
        for level in (-1, 10, 1.0, True):
            with self.subTest(level=level):
                with self.assertRaises(ValueError):
                    compress(b"data", compresslevel=level)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
