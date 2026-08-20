from __future__ import annotations

import unittest

from competitive_eval.config import LOCAL_ONLY_ARTIFACTS
from competitive_eval.manifests import verify_public_digest_inventory


class PublicInventoryTests(unittest.TestCase):
    def test_clean_clone_inventory_requires_no_local_or_provider_state(self) -> None:
        result = verify_public_digest_inventory()
        self.assertGreater(result["public_package_files_verified"], 20)
        self.assertEqual(result["root_current_files_verified"], 4)
        self.assertEqual(result["local_only_files_required"], 0)
        self.assertEqual(result["provider_calls"], 0)
        self.assertFalse(result["network_used"])

    def test_all_dataset_derived_products_are_declared_local_only(self) -> None:
        self.assertEqual(len(LOCAL_ONLY_ARTIFACTS), 8)
        self.assertTrue(
            all(path.startswith("artifacts/") for path in LOCAL_ONLY_ARTIFACTS)
        )


if __name__ == "__main__":
    unittest.main()
