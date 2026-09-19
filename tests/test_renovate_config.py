from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENOVATE_PATH = ROOT / "renovate/default.json"


class RenovateConfigTests(unittest.TestCase):
    def test_allure_action_updates_share_one_cross_manager_group(self) -> None:
        config = json.loads(RENOVATE_PATH.read_text(encoding="utf-8"))
        rules = [
            rule
            for rule in config["packageRules"]
            if rule.get("matchPackageNames") == ["quokkify/allure-report-action"]
        ]

        self.assertEqual(len(rules), 1)
        self.assertEqual(
            rules[0],
            {
                "description": "Deduplicate Allure action updates across built-in and custom managers.",
                "matchManagers": ["github-actions", "custom.regex"],
                "matchPackageNames": ["quokkify/allure-report-action"],
                "matchUpdateTypes": ["minor", "patch", "digest"],
                "groupName": "quokkify/allure-report-action non-major updates",
            },
        )

    def test_allure_action_update_is_not_hidden_by_a_broad_ignore(self) -> None:
        config = json.loads(RENOVATE_PATH.read_text(encoding="utf-8"))
        self.assertIn("github-actions", config["enabledManagers"])
        self.assertIn("custom.regex", config["enabledManagers"])
        self.assertFalse(any("allure-report-action" in rule.get("matchPackageNames", []) and rule.get("enabled") is False for rule in config["packageRules"]))


if __name__ == "__main__":
    unittest.main()
