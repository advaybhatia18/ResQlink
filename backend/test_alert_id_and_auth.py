import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as resqlink_app
import storage

ROOT = Path(__file__).resolve().parent.parent
USER_A = "b2f3ac97-d7c2-48f4-a714-9e0f7abc1234"
USER_B = "99a1b2c3-d4e5-4f67-89ab-cdef01234567"
ADMIN_ID = "83c9e76b-27de-4d67-82a4-2ce5aabb5678"


class AlertIdAndIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(resqlink_app.app)

    def test_generate_alert_id_format_and_uniqueness(self):
        generated = {storage.generate_alert_id() for _ in range(250)}
        self.assertEqual(len(generated), 250)
        for alert_id in generated:
            self.assertRegex(
                alert_id,
                r"^RQ-\d{8}-[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{6}$",
            )
            suffix = alert_id.rsplit("-", 1)[1]
            for ambiguous in ("0", "O", "1", "I"):
                self.assertNotIn(ambiguous, suffix)

    def test_idempotent_retry_returns_same_alert_id_with_200(self):
        rows_by_key: dict[tuple[str, str], dict] = {}

        def fake_save_alert(result, user_id, key):
            lookup = (user_id, key)
            if lookup in rows_by_key:
                existing = rows_by_key[lookup]
                result["alert_id"] = existing["alert_id"]
                result["created_at"] = existing["created_at"]
                return existing["id"], True, existing["status"]
            created = {
                "id": 101,
                "alert_id": "RQ-20261115-K7M9P2",
                "status": "ACTIVE",
                "created_at": "2026-11-15T12:00:00+00:00",
            }
            rows_by_key[lookup] = created
            result["alert_id"] = created["alert_id"]
            result["created_at"] = created["created_at"]
            return created["id"], False, created["status"]

        auth_client = MagicMock()
        auth_client.auth.get_user.return_value = SimpleNamespace(
            user=SimpleNamespace(id=USER_A, email="a@example.com")
        )
        headers = {
            "Authorization": "Bearer user-a-token",
            "Idempotency-Key": "session-key-1111",
        }
        payload = {"severity": 5, "category": "MEDICAL"}

        with (
            patch("app.get_auth_client", return_value=auth_client),
            patch("app.get_user_profile", return_value={"id": USER_A, "name": "User A", "role": "USER"}),
            patch("app.save_alert", side_effect=fake_save_alert),
        ):
            first = self.client.post("/emergency", headers=headers, json=payload)
            second = self.client.post("/emergency", headers=headers, json=payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        first_body = first.json()
        second_body = second.json()
        self.assertEqual(first_body["alert_id"], "RQ-20261115-K7M9P2")
        self.assertEqual(second_body["alert_id"], first_body["alert_id"])
        self.assertEqual(first_body["id"], 101)
        self.assertEqual(first_body["priority"], 100)
        self.assertEqual(first_body["severity"], 5)
        self.assertEqual(first_body["label"], "CRITICAL")
        self.assertIn("AMBULANCE_MEDICAL", first_body["recommended_services"])
        self.assertEqual(first_body["created_at"], "2026-11-15T12:00:00+00:00")

    def test_ownership_lookup_by_alert_id_scopes_user_and_allows_admin(self):
        with patch("app.get_alert_detail_by_alert_id") as detail_mock:
            detail_mock.return_value = {
                "id": 101,
                "alert_id": "RQ-20261115-K7M9P2",
                "severity": 4,
                "label": "VERY HIGH",
                "priority": 80,
                "status": "ACTIVE",
                "created_at": "2026-11-15T12:00:00+00:00",
                "status_history": [],
            }
            user_auth = MagicMock()
            user_auth.auth.get_user.return_value = SimpleNamespace(
                user=SimpleNamespace(id=USER_B, email="b@example.com")
            )
            with (
                patch("app.get_auth_client", return_value=user_auth),
                patch("app.get_user_profile", return_value={"id": USER_B, "name": "User B", "role": "USER"}),
            ):
                res_user = self.client.get(
                    "/emergencies/by-alert-id/RQ-20261115-K7M9P2",
                    headers={"Authorization": "Bearer user-b-token"},
                )
            self.assertEqual(res_user.status_code, 200)
            detail_mock.assert_called_with("RQ-20261115-K7M9P2", user_id=USER_B)

            admin_auth = MagicMock()
            admin_auth.auth.get_user.return_value = SimpleNamespace(
                user=SimpleNamespace(id=ADMIN_ID, email="admin@example.com")
            )
            with (
                patch("app.get_auth_client", return_value=admin_auth),
                patch("app.get_user_profile", return_value={"id": ADMIN_ID, "name": "Admin", "role": "ADMIN"}),
            ):
                res_admin = self.client.get(
                    "/emergencies/by-alert-id/RQ-20261115-K7M9P2",
                    headers={"Authorization": "Bearer admin-token"},
                )
            self.assertEqual(res_admin.status_code, 200)
            detail_mock.assert_called_with("RQ-20261115-K7M9P2", user_id=None)

    def test_admin_search_matches_alert_id(self):
        auth_client = MagicMock()
        auth_client.auth.get_user.return_value = SimpleNamespace(
            user=SimpleNamespace(id=ADMIN_ID, email="admin@example.com")
        )
        sample = [
            {
                "id": 1,
                "alert_id": "RQ-20261115-A1B2C3",
                "severity": 3,
                "label": "HIGH",
                "priority": 60,
                "status": "ACTIVE",
                "created_at": "2026-11-15T10:00:00+00:00",
            },
            {
                "id": 2,
                "alert_id": "RQ-20261115-X9Y8Z7",
                "severity": 5,
                "label": "CRITICAL",
                "priority": 100,
                "status": "ACTIVE",
                "created_at": "2026-11-15T11:00:00+00:00",
            },
        ]
        with (
            patch("app.get_auth_client", return_value=auth_client),
            patch("app.get_user_profile", return_value={"id": ADMIN_ID, "name": "Admin", "role": "ADMIN"}),
            patch("app.get_alerts", return_value=sample),
        ):
            res = self.client.get(
                "/emergencies?search=X9Y8Z7",
                headers={"Authorization": "Bearer admin-token"},
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["count"], 1)
        self.assertEqual(res.json()["emergencies"][0]["alert_id"], "RQ-20261115-X9Y8Z7")

    def test_schema_and_migration_consistency_for_alert_id(self):
        schema_sql = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8").lower()
        self.assertIn("alert_id", schema_sql, "schema.sql missing alert_id")
        self.assertIn("emergencies_alert_id_key", schema_sql, "schema.sql missing emergencies_alert_id_key")
        self.assertIn("idempotency_key text", schema_sql, "schema.sql missing idempotency_key text")
        self.assertIn("emergencies_user_id_idempotency_key_idx", schema_sql, "schema.sql missing idempotency index")

    def test_cors_parser_warns_on_malformed_origins(self):
        with self.assertLogs("resqlink.app", level="WARNING") as captured:
            parsed = resqlink_app._parse_frontend_origins(
                "https://akshhq.github.io/ResQlink/, *, http://127.0.0.1:5500/"
            )
        self.assertEqual(parsed, ["http://127.0.0.1:5500"])
        self.assertTrue(any("malformed" in msg.lower() for msg in captured.output))

    def test_login_surfaces_unconfirmed_email_and_rate_limit(self):
        auth_client = MagicMock()
        auth_client.auth.sign_in_with_password.side_effect = AuthApiError(
            "Email not confirmed", 400, "email_not_confirmed"
        )
        with patch("app.get_auth_client", return_value=auth_client):
            unconfirmed = self.client.post(
                "/login",
                json={"email": "user@example.com", "password": "secure-password"},
            )
        self.assertEqual(unconfirmed.status_code, 401)
        self.assertIn("confirm your email", unconfirmed.json()["detail"].lower())

        auth_client.auth.sign_in_with_password.side_effect = AuthApiError(
            "Rate limit", 429, "over_request_rate_limit"
        )
        with patch("app.get_auth_client", return_value=auth_client):
            limited = self.client.post(
                "/login",
                json={"email": "user@example.com", "password": "secure-password"},
            )
        self.assertEqual(limited.status_code, 429)

    def test_schema_includes_sos_session_columns_and_indexes(self):
        schema_sql = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8").lower()
        for token in (
            "session_started_at",
            "session_ended_at",
            "session_duration_seconds",
            "emergencies_status_created_at_idx",
            "emergencies_user_created_at_idx",
            "set_updated_at",
        ):
            self.assertIn(token, schema_sql, f"schema.sql missing {token}")

    def test_active_sos_session_and_end_session_endpoints(self):
        user_id = "11111111-1111-4111-8111-111111111111"
        active_session = {
            "id": 42,
            "alert_id": "RQ-20261116-ABCD23",
            "severity": 4,
            "label": "VERY HIGH",
            "priority": 80,
            "status": "ACTIVE",
            "requested_services": ["POLICE", "AMBULANCE_MEDICAL"],
            "session_started_at": "2026-11-16T00:00:00+00:00",
            "session_ended_at": None,
            "session_duration_seconds": None,
            "created_at": "2026-11-16T00:00:00+00:00",
        }
        ended_session = {
            "id": 42,
            "alert_id": "RQ-20261116-ABCD23",
            "status": "ACTIVE",
            "requested_services": ["POLICE", "AMBULANCE_MEDICAL"],
            "session_started_at": "2026-11-16T00:00:00+00:00",
            "session_ended_at": "2026-11-16T00:02:05+00:00",
            "session_duration_seconds": 125,
            "already_ended": False,
        }
        resqlink_app.app.dependency_overrides[resqlink_app.get_authenticated_user] = (
            lambda: {"id": user_id, "email": "u@example.com", "role": "USER"}
        )
        try:
            with (
                patch("app.get_active_sos_session", return_value=active_session),
                patch("app.end_sos_session", return_value=ended_session) as end_mock,
            ):
                active_res = self.client.get(
                    "/emergencies/me/active-session",
                    headers={"Authorization": "Bearer user-token"},
                )
                self.assertEqual(active_res.status_code, 200)
                self.assertEqual(active_res.json()["session"]["alert_id"], "RQ-20261116-ABCD23")

                end_res = self.client.post(
                    "/emergencies/42/end-session",
                    headers={"Authorization": "Bearer user-token"},
                    json={"note": "Reached safe location"},
                )
                self.assertEqual(end_res.status_code, 200)
                self.assertEqual(end_res.json()["session_duration_seconds"], 125)
                self.assertEqual(end_res.json()["requested_services"], ["POLICE", "AMBULANCE_MEDICAL"])
                end_mock.assert_called_once_with(
                    42,
                    user_id,
                    owner_filter=user_id,
                    note="Reached safe location",
                )
        finally:
            resqlink_app.app.dependency_overrides.pop(resqlink_app.get_authenticated_user, None)


if __name__ == "__main__":
    unittest.main()
