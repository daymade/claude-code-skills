import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "classify_response.py"
SPEC = importlib.util.spec_from_file_location("classify_response", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ResponseClassifierTests(unittest.TestCase):
    def test_auth_success_allows_observed_missing_optional_fields(self):
        result = MODULE.classify(
            "auth",
            {
                "code": "000000",
                "status": True,
                "data": {"accessToken": "Bearer secret", "expiresIn": 10800},
            },
            200,
        )
        self.assertEqual(result["state"], "success")
        self.assertEqual(result["missing_optional"], "uid,tenantId,productCode")
        self.assertNotIn("secret", str(result))

    def test_success_without_token_is_response_failure(self):
        result = MODULE.classify(
            "auth", {"code": "000000", "status": True, "data": {}}, 200
        )
        self.assertEqual(result["category"], "response")
        self.assertIn("accessToken", result["message"])

    def test_quota_preserves_support_metadata(self):
        result = MODULE.classify(
            "rag",
            {
                "code": 999005,
                "status": False,
                "errorType": "POINT_NOT_ENOUGH",
                "msg": "积分不足",
                "traceId": "trace-1",
                "data": "",
            },
            402,
        )
        self.assertEqual(result["category"], "quota")
        self.assertEqual(result["code"], "999005")
        self.assertEqual(result["error_type"], "POINT_NOT_ENOUGH")
        self.assertEqual(result["trace_id"], "trace-1")

    def test_permission_and_auth_are_distinct(self):
        permission = MODULE.classify(
            "rag", {"code": "0000001009", "status": False, "msg": "the uri can't be accessed"}, 403
        )
        auth = MODULE.classify(
            "rag", {"code": "0000001008", "status": False, "msg": "token is invalid"}, 401
        )
        self.assertEqual(permission["category"], "permission")
        self.assertEqual(auth["category"], "auth")

    def test_successful_empty_rag_response_is_not_failure(self):
        result = MODULE.classify(
            "rag", {"code": "000000", "status": True, "data": []}, 200
        )
        self.assertEqual(result["state"], "success")
        self.assertEqual(result["empty"], "true")

if __name__ == "__main__":
    unittest.main()
