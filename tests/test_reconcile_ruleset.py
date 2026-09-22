from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
import unittest
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reconcile_ruleset", ROOT / "scripts/reconcile_ruleset.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class FakeClient:
    def __init__(self, responses: dict[tuple[str, str], object]):
        self.responses = responses
        self.calls: list[tuple[str, str, object | None]] = []

    def request(self, method: str, path: str, payload: object | None = None) -> object:
        self.calls.append((method, path, payload))
        response = self.responses.get((method, path))
        if isinstance(response, Exception):
            raise response
        return response


class RulesetReconcilerTests(TestCase):
    def _client(self, existing: object = [], *, contexts: list[str] | None = None) -> FakeClient:
        return FakeClient({
            ("GET", "/repos/acme/widgets/commits/abc/check-runs?per_page=100"): {
                "check_runs": [{"name": name} for name in (contexts or ["gitleaks", "codeql"])],
            },
            ("GET", "/repos/acme/widgets/commits/abc/statuses?per_page=100"): [],
            ("GET", "/repos/acme/widgets/rulesets?includes_parents=true&per_page=100&page=1"): existing,
        })

    def test_dry_run_preflights_context_and_makes_no_mutation(self) -> None:
        client = self._client()
        result = module.reconcile(client, "acme/widgets", "main", ["gitleaks", "codeql"], "abc", "evaluate", True)
        self.assertTrue(result["dry_run"])
        self.assertNotIn("POST", {call[0] for call in client.calls})
        self.assertNotIn("PUT", {call[0] for call in client.calls})

    def test_missing_context_fails_before_ruleset_lookup_or_mutation(self) -> None:
        client = self._client(contexts=["gitleaks"])
        with self.assertRaisesRegex(module.ReconcileError, "codeql"):
            module.reconcile(client, "acme/widgets", "main", ["gitleaks", "codeql"], "abc", "active", False)
        self.assertEqual([call[0] for call in client.calls], ["GET", "GET"])

    def test_create_then_readback(self) -> None:
        client = self._client()
        desired = module.build_desired(module.managed_name("acme", "widgets"), "main", ["gitleaks"], "active", None)
        client.responses[("POST", "/repos/acme/widgets/rulesets")] = {"id": 7, **desired}
        client.responses[("GET", "/repos/acme/widgets/rulesets/7")] = {"id": 7, **desired}
        result = module.reconcile(client, "acme/widgets", "main", ["gitleaks"], "abc", "active", False)
        self.assertEqual(result["action"], "create")
        self.assertTrue(result["matches"])
        self.assertEqual(len([call for call in client.calls if call[0] == "POST"]), 1)

    def test_update_preserves_unmanaged_rule_and_second_run_is_update(self) -> None:
        existing = [{"id": 7, "name": module.managed_name("acme", "widgets")}]
        client = self._client(existing)
        desired = module.build_desired(module.managed_name("acme", "widgets"), "main", ["gitleaks"], "active", None)
        desired["rules"].append({"type": "merge_queue"})
        detail = {"id": 7, **module.build_desired(module.managed_name("acme", "widgets"), "main", ["gitleaks"], "evaluate", None), "rules": [{"type": "deletion"}, {"type": "merge_queue"}]}
        client.responses[("GET", "/repos/acme/widgets/rulesets/7")] = detail
        client.responses[("PUT", "/repos/acme/widgets/rulesets/7")] = {"id": 7, **desired}
        client.responses[("GET", "/repos/acme/widgets/rulesets/7")] = {"id": 7, **desired}
        result = module.reconcile(client, "acme/widgets", "main", ["gitleaks"], "abc", "active", False)
        self.assertEqual(result["action"], "update")
        self.assertTrue(result["matches"])
        self.assertIn({"type": "merge_queue"}, result["desired"]["rules"])

    def test_readback_mismatch_fails_closed(self) -> None:
        client = self._client()
        client.responses[("POST", "/repos/acme/widgets/rulesets")] = {"id": 7}
        client.responses[("GET", "/repos/acme/widgets/rulesets/7")] = {"id": 7, "name": "wrong"}
        with self.assertRaisesRegex(module.ReconcileError, "readback mismatch"):
            module.reconcile(client, "acme/widgets", "main", ["gitleaks"], "abc", "active", False)

    def test_malformed_ruleset_response_is_rejected(self) -> None:
        client = self._client(existing={"not": "a list"})
        with self.assertRaisesRegex(module.ReconcileError, "expected a list"):
            module.reconcile(client, "acme/widgets", "main", ["gitleaks"], "abc", "evaluate", False)


if __name__ == "__main__":
    unittest.main()
