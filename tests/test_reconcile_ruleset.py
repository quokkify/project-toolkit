from __future__ import annotations

import importlib.util
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any, Mapping
import unittest

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
        if isinstance(response, deque):
            if not response:
                raise AssertionError(f"no queued response for {method} {path}")
            response = response.popleft()
        if isinstance(response, Exception):
            raise response
        return response


class RulesetReconcilerTests(unittest.TestCase):
    @staticmethod
    def _validate_ruleset_request(payload: object, schema: Mapping[str, Any]) -> None:
        """Validate the complete POST/PUT body against the pinned API contract."""
        if not isinstance(payload, dict):
            raise AssertionError("request body must be an object")
        for field in schema["required"]:
            if field not in payload:
                raise AssertionError(f"missing request field: {field}")
        if payload.get("target") != "branch" or payload.get("enforcement") not in schema["enforcement"]:
            raise AssertionError("invalid target or enforcement")
        conditions = payload.get("conditions")
        if not isinstance(conditions, dict) or not isinstance(conditions.get("ref_name"), dict):
            raise AssertionError("invalid conditions")
        rules = payload.get("rules")
        if not isinstance(rules, list):
            raise AssertionError("rules must be a list")
        for rule in rules:
            if not isinstance(rule, dict) or rule.get("type") not in schema["allowed_rule_types"]:
                raise AssertionError("unsupported rule type")
            rule_type = rule["type"]
            params = rule.get("parameters", {})
            if rule_type == "pull_request":
                required = schema["pull_request_required_parameters"]
                if not isinstance(params, dict) or any(key not in params for key in required):
                    raise AssertionError("missing pull_request parameter")
            elif rule_type == "required_status_checks":
                statuses = params.get("required_status_checks") if isinstance(params, dict) else None
                if not isinstance(statuses, list):
                    raise AssertionError("invalid required status checks")
                for status in statuses:
                    if not isinstance(status, dict) or not isinstance(status.get("context"), str):
                        raise AssertionError("invalid status check")
                    if "integration_id" in status and (
                        not isinstance(status["integration_id"], int) or isinstance(status["integration_id"], bool)
                    ):
                        raise AssertionError("integration_id must be an integer")
            elif rule_type == "code_scanning":
                tools = params.get("code_scanning_tools") if isinstance(params, dict) else None
                if not isinstance(tools, list):
                    raise AssertionError("invalid code scanning tools")
                for tool in tools:
                    if (
                        not isinstance(tool, dict)
                        or tool.get("alerts_threshold") not in schema["code_scanning_alert_threshold"]
                        or tool.get("security_alerts_threshold") not in schema["code_scanning_security_alert_threshold"]
                    ):
                        raise AssertionError("invalid code scanning threshold")

    def test_complete_post_and_put_bodies_match_pinned_github_schema(self) -> None:
        schema_path = ROOT / "tests/fixtures/github_ruleset_request_schema_2022-11-28.json"
        schema = json.loads(schema_path.read_text())
        payload = module.build_desired(
            module.managed_name("acme", "widgets"), "main", ["gitleaks"], "evaluate", "errors"
        )
        for method in ("POST", "PUT"):
            with self.subTest(method=method):
                self._validate_ruleset_request(payload, schema)

    def test_pinned_github_schema_rejects_invalid_complete_bodies(self) -> None:
        schema = json.loads((ROOT / "tests/fixtures/github_ruleset_request_schema_2022-11-28.json").read_text())
        payload = module.build_desired(
            module.managed_name("acme", "widgets"), "main", ["gitleaks"], "evaluate", "errors"
        )
        invalid = []
        unsupported = json.loads(json.dumps(payload))
        unsupported["rules"][0]["type"] = "not_a_github_rule"
        invalid.append(("unsupported rule type", unsupported))
        for parameter in schema["pull_request_required_parameters"]:
            missing = json.loads(json.dumps(payload))
            del missing["rules"][2]["parameters"][parameter]
            invalid.append((f"missing {parameter}", missing))
        for threshold in ("critical", 1):
            bad_threshold = json.loads(json.dumps(payload))
            bad_threshold["rules"][-1]["parameters"]["code_scanning_tools"][0]["alerts_threshold"] = threshold
            invalid.append((f"invalid threshold {threshold!r}", bad_threshold))
        for integration_id in (None, "123"):
            bad_integration = json.loads(json.dumps(payload))
            bad_integration["rules"][3]["parameters"]["required_status_checks"][0]["integration_id"] = integration_id
            invalid.append((f"invalid integration_id {integration_id!r}", bad_integration))
        for label, candidate in invalid:
            with self.subTest(case=label):
                with self.assertRaises(AssertionError):
                    self._validate_ruleset_request(candidate, schema)

    def _client(self, existing: object = [], *, contexts: list[str] | None = None) -> FakeClient:
        return FakeClient({
            ("GET", "/repos/acme/widgets/commits/abc/check-runs?per_page=100&page=1"): {
                "check_runs": [{"name": name} for name in (contexts or ["gitleaks", "codeql"])],
            },
            ("GET", "/repos/acme/widgets/commits/abc/statuses?per_page=100&page=1"): [],
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

    def test_create_then_idempotent_repeat_uses_realistic_list_and_detail_shapes(self) -> None:
        name = module.managed_name("acme", "widgets")
        desired = module.build_desired(name, "main", ["gitleaks"], "active", None)
        summary = {"id": 7, "name": name, "target": "branch", "enforcement": "active"}
        detail = {
            "id": 7, "node_id": "R_7", "name": name, "target": "branch", "enforcement": "active",
            "conditions": desired["conditions"], "rules": desired["rules"],
            "source": "acme/widgets", "source_type": "Repository", "bypass_actors": [],
            "current_user_can_bypass": True, "_links": {"self": {"href": "https://example.test"}},
        }
        client = self._client()
        client.responses[("POST", "/repos/acme/widgets/rulesets")] = {"id": 7, **detail}
        client.responses[("GET", "/repos/acme/widgets/rulesets/7")] = deque([detail, detail])
        client.responses[("GET", "/repos/acme/widgets/rulesets?includes_parents=true&per_page=100&page=1")] = deque([[ ], [summary]])
        first = module.reconcile(client, "acme/widgets", "main", ["gitleaks"], "abc", "active", False)
        second = module.reconcile(client, "acme/widgets", "main", ["gitleaks"], "abc", "active", False)
        self.assertEqual(first["action"], "create")
        self.assertEqual(second["action"], "noop")
        self.assertTrue(second["matches"])
        self.assertEqual(len([call for call in client.calls if call[0] == "POST"]), 1)
        self.assertEqual(len([call for call in client.calls if call[0] == "PUT"]), 0)

    def test_update_preserves_unmanaged_rule_parameters(self) -> None:
        existing = [{"id": 7, "name": module.managed_name("acme", "widgets")}]
        client = self._client(existing)
        desired = module.build_desired(module.managed_name("acme", "widgets"), "main", ["gitleaks"], "active", None)
        detail = {"id": 7, **module.build_desired(module.managed_name("acme", "widgets"), "main", ["gitleaks"], "evaluate", None), "rules": [{"type": "deletion"}, {"type": "merge_queue", "parameters": {"method": "ALLGREEN", "timeout": 60}}]}
        client.responses[("GET", "/repos/acme/widgets/rulesets/7")] = deque([detail])
        updated = {"id": 7, **desired, "rules": desired["rules"] + [{"type": "merge_queue", "parameters": {"method": "ALLGREEN", "timeout": 60}}]}
        client.responses[("PUT", "/repos/acme/widgets/rulesets/7")] = updated
        client.responses[("GET", "/repos/acme/widgets/rulesets/7")] = deque([detail, updated])
        result = module.reconcile(client, "acme/widgets", "main", ["gitleaks"], "abc", "active", False)
        self.assertEqual(result["action"], "update")
        self.assertTrue(result["matches"])
        self.assertIn({"type": "merge_queue", "parameters": {"method": "ALLGREEN", "timeout": 60}}, result["desired"]["rules"])

    def test_unknown_rule_parameter_readback_mismatch_fails_closed(self) -> None:
        existing = [{"id": 7, "name": module.managed_name("acme", "widgets")}]
        client = self._client(existing)
        detail = {"id": 7, **module.build_desired(module.managed_name("acme", "widgets"), "main", ["gitleaks"], "active", None), "rules": [{"type": "deletion"}, {"type": "merge_queue", "parameters": {"method": "ALLGREEN", "timeout": 60}}]}
        mismatched = {"id": 7, **module.build_desired(module.managed_name("acme", "widgets"), "main", ["gitleaks"], "active", None), "rules": [{"type": "deletion"}, {"type": "merge_queue", "parameters": {"method": "HEADGREEN", "timeout": 5}}]}
        client.responses[("GET", "/repos/acme/widgets/rulesets/7")] = deque([detail, mismatched])
        client.responses[("PUT", "/repos/acme/widgets/rulesets/7")] = {"id": 7}
        with self.assertRaisesRegex(module.ReconcileError, "readback mismatch"):
            module.reconcile(client, "acme/widgets", "main", ["gitleaks"], "abc", "active", False)

    def test_check_runs_later_page_is_required_before_mutation(self) -> None:
        client = self._client()
        client.responses[("GET", "/repos/acme/widgets/commits/abc/check-runs?per_page=100&page=1")] = {"total_count": 101, "check_runs": [{"name": "gitleaks"}] * 100}
        client.responses[("GET", "/repos/acme/widgets/commits/abc/check-runs?per_page=100&page=2")] = {"total_count": 101, "check_runs": [{"name": "CodeQL"}]}
        client.responses[("GET", "/repos/acme/widgets/commits/abc/statuses?per_page=100&page=1")] = []
        result = module.reconcile(client, "acme/widgets", "main", ["CodeQL"], "abc", "active", True)
        self.assertTrue(result["dry_run"])
        self.assertNotIn("POST", {call[0] for call in client.calls})

    def test_incomplete_check_runs_fails_before_mutation(self) -> None:
        client = self._client()
        client.responses[("GET", "/repos/acme/widgets/commits/abc/check-runs?per_page=100&page=1")] = {"total_count": 101, "check_runs": [{"name": "gitleaks"}] * 100}
        client.responses[("GET", "/repos/acme/widgets/commits/abc/check-runs?per_page=100&page=2")] = {"total_count": 101, "check_runs": []}
        with self.assertRaisesRegex(module.ReconcileError, "incomplete"):
            module.reconcile(client, "acme/widgets", "main", ["gitleaks"], "abc", "active", False)
        self.assertNotIn("POST", {call[0] for call in client.calls})

    def test_help_describes_evaluate_mutation_and_dry_run_safety(self) -> None:
        help_text = module.parser().format_help()
        self.assertIn("Explicitly promote", help_text)
        self.assertNotIn("never changes GitHub", help_text)

    def test_readback_mismatch_fails_closed(self) -> None:
        client = self._client()
        client.responses[("POST", "/repos/acme/widgets/rulesets")] = {"id": 7}
        client.responses[("GET", "/repos/acme/widgets/rulesets/7")] = {"id": 7, "name": "wrong"}
        with self.assertRaisesRegex(module.ReconcileError, "readback mismatch"):
            module.reconcile(client, "acme/widgets", "main", ["gitleaks"], "abc", "active", False)

    def test_payload_uses_github_ruleset_schema_and_explicit_defaults(self) -> None:
        desired = module.build_desired(
            module.managed_name("acme", "widgets"), "main", ["gitleaks"], "evaluate", "errors"
        )
        by_type = {rule["type"]: rule for rule in desired["rules"]}
        self.assertNotIn("required_code_scanning", by_type)
        tool = by_type["code_scanning"]["parameters"]["code_scanning_tools"][0]
        self.assertEqual(tool["alerts_threshold"], "errors")
        self.assertEqual(tool["security_alerts_threshold"], "high_or_higher")
        self.assertFalse(by_type["pull_request"]["parameters"]["required_review_thread_resolution"])
        self.assertEqual(
            by_type["required_status_checks"]["parameters"]["required_status_checks"],
            [{"context": "gitleaks"}],
        )

        # The outbound 2022-11-28 payload must not emit nullable
        # integration_id; the field is optional and, when present, integer.
        self.assertNotIn(
            "integration_id",
            by_type["required_status_checks"]["parameters"]["required_status_checks"][0],
        )

    def test_status_check_integration_id_mismatch_fails_closed(self) -> None:
        existing = [{"id": 7, "name": module.managed_name("acme", "widgets")}]
        client = self._client(existing)
        desired = module.build_desired(module.managed_name("acme", "widgets"), "main", ["gitleaks"], "active", None)
        detail = {"id": 7, **module.build_desired(module.managed_name("acme", "widgets"), "main", ["gitleaks"], "evaluate", None)}
        mismatched = {"id": 7, **desired, "rules": [
            {**rule, "parameters": {
                **rule["parameters"],
                "required_status_checks": [{"context": "gitleaks", "integration_id": 12345}],
            }} if rule["type"] == "required_status_checks" else rule
            for rule in desired["rules"]
        ]}
        client.responses[("GET", "/repos/acme/widgets/rulesets/7")] = deque([detail, mismatched])
        client.responses[("PUT", "/repos/acme/widgets/rulesets/7")] = {"id": 7}
        self.assertNotEqual(module._policy_view(desired), module._policy_view(mismatched))
        with self.assertRaisesRegex(module.ReconcileError, "readback mismatch"):
            module.reconcile(client, "acme/widgets", "main", ["gitleaks"], "abc", "active", False)

    def test_malformed_ruleset_response_is_rejected(self) -> None:
        client = self._client(existing={"not": "a list"})
        with self.assertRaisesRegex(module.ReconcileError, "expected a list"):
            module.reconcile(client, "acme/widgets", "main", ["gitleaks"], "abc", "evaluate", False)


if __name__ == "__main__":
    unittest.main()
