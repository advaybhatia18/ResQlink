import logging
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from supabase_auth.errors import AuthApiError

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as resqlink_app
import storage


USER_ID = "b2f3ac97-d7c2-48f4-a714-9e0f7abc1234"
ADMIN_ID = "83c9e76b-27de-4d67-82a4-2ce5aabb5678"


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(resqlink_app.app)
        self.auth_client = MagicMock()
        self.auth_client.auth.get_user.side_effect = self.get_auth_user
        self.auth_client_patch = patch(
            "app.get_auth_client",
            return_value=self.auth_client
        )
        self.profile_patch = patch(
            "app.get_user_profile",
            side_effect=self.get_profile
        )
        self.alerts_patch = patch("app.get_alerts", return_value=[])
        self.save_alert_patch = patch(
            "app.save_alert",
            return_value=(27, False, "ACTIVE")
        )
        self.resolve_alert_patch = patch("app.resolve_alert", return_value=True)
        self.process_emergency_patch = patch(
            "app.process_emergency",
            return_value={"severity": 3, "label": "HIGH", "priority": 60}
        )
        self.password_update_patch = patch("app.update_supabase_password")
        self.session_revoke_patch = patch("app.revoke_supabase_session")

        for patcher in (
            self.auth_client_patch,
            self.profile_patch,
            self.alerts_patch,
            self.save_alert_patch,
            self.resolve_alert_patch,
            self.process_emergency_patch,
            self.password_update_patch,
            self.session_revoke_patch,
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def get_auth_user(token):
        if token == "invalid":
            raise AuthApiError("Invalid token", 401, None)
        if token == "user-token":
            return SimpleNamespace(
                user=SimpleNamespace(id=USER_ID, email="user@example.com")
            )
        if token == "admin-token":
            return SimpleNamespace(
                user=SimpleNamespace(id=ADMIN_ID, email="admin@example.com")
            )
        raise AuthApiError("Invalid token", 401, None)

    @staticmethod
    def get_profile(user_id):
        profiles = {
            USER_ID: {"id": USER_ID, "name": "User", "role": "USER"},
            ADMIN_ID: {"id": ADMIN_ID, "name": "Admin", "role": "ADMIN"},
        }
        return profiles.get(user_id)

    @staticmethod
    def auth(token):
        return {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "42542a3c-a73d-455f-9388-893fce868a47",
        }

    def test_missing_token_is_401_for_admin_operations(self):
        self.assertEqual(self.client.get("/emergencies").status_code, 401)
        self.assertEqual(
            self.client.post(
                "/emergency",
                json={"severity": 3, "latitude": 12.9, "longitude": 77.5}
            ).status_code,
            401
        )
        self.assertEqual(
            self.client.patch("/emergency/27/resolve").status_code,
            401
        )

    def test_health_endpoint_needs_no_external_service(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIn("x-request-id", response.headers)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_request_body_size_is_limited(self):
        response = self.client.post(
            "/register",
            content=b"x" * (1_048_577),
            headers={"Content-Type": "application/json"}
        )

        self.assertEqual(response.status_code, 413)

    def test_cors_preflight_allows_only_configured_dashboard_origin(self):
        response = self.client.options(
            "/emergencies",
            headers={
                "Origin": "https://advaybhatia18.github.io",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "https://advaybhatia18.github.io"
        )
        self.assertNotIn("access-control-allow-credentials", response.headers)

    def test_cors_rejects_unconfigured_origin(self):
        response = self.client.options(
            "/emergencies",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            }
        )

        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_invalid_token_is_401(self):
        headers = self.auth("invalid")
        self.assertEqual(
            self.client.get("/emergencies", headers=headers).status_code,
            401
        )
        self.assertEqual(
            self.client.patch(
                "/emergency/27/resolve",
                headers=headers
            ).status_code,
            401
        )

    def test_valid_user_can_send_sos_using_server_identity(self):
        response = self.client.post(
            "/emergency",
            headers=self.auth("user-token"),
            json={
                "severity": 3,
                "latitude": 12.9,
                "longitude": 77.5,
            }
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["alert_id"], 27)
        self.assertEqual(response.json()["status"], "ACTIVE")
        self.assertEqual(response.json()["submission_status"], "submitted")
        self.assertNotIn("latitude", response.json())
        self.assertNotIn("longitude", response.json())
        account = self.client.get("/me", headers=self.auth("user-token"))
        self.assertEqual(account.status_code, 200)
        self.assertEqual(account.json()["role"], "USER")
        resqlink_app.save_alert.assert_called_once()
        saved_alert, owner_id, request_key = resqlink_app.save_alert.call_args.args
        self.assertEqual(owner_id, USER_ID)
        self.assertEqual(saved_alert["severity"], 3)
        self.assertEqual(
            request_key,
            "42542a3c-a73d-455f-9388-893fce868a47"
        )

    def test_request_logs_exclude_tokens_and_precise_coordinates(self):
        with self.assertLogs("resqlink.requests", level="INFO") as captured:
            response = self.client.post(
                "/emergency",
                headers=self.auth("user-token"),
                json={
                    "severity": 3,
                    "latitude": 12.9,
                    "longitude": 77.5,
                }
            )

        self.assertEqual(response.status_code, 201)
        log_output = "\n".join(captured.output)
        self.assertIn('"event":"http_request"', log_output)
        self.assertNotIn("user-token", log_output)
        self.assertNotIn("12.9", log_output)
        self.assertNotIn("77.5", log_output)
        self.assertNotIn("Authorization", log_output)

    def test_valid_admin_can_read_alerts(self):
        response = self.client.get(
            "/emergencies",
            headers=self.auth("admin-token")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"count": 0, "emergencies": []})
        resqlink_app.get_alerts.assert_called_once_with()

    def test_admin_listing_reports_database_failure(self):
        resqlink_app.get_alerts.side_effect = HTTPException(
            status_code=503,
            detail="Could not load emergencies from Supabase"
        )

        response = self.client.get(
            "/emergencies",
            headers=self.auth("admin-token")
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Supabase", response.json()["detail"])

    def test_admin_alert_filters_combine_severity_status_and_search(self):
        resqlink_app.get_alerts.return_value = [
            {
                "id": 31,
                "severity": 5,
                "label": "CRITICAL",
                "priority": 100,
                "status": "ACTIVE",
                "created_at": "2026-11-10T10:00:00+00:00",
            },
            {
                "id": 32,
                "severity": 5,
                "label": "CRITICAL",
                "priority": 100,
                "status": "RESOLVED",
                "created_at": "2026-11-10T11:00:00+00:00",
            },
            {
                "id": 33,
                "severity": 3,
                "label": "HIGH",
                "priority": 60,
                "status": "ACTIVE",
                "created_at": "2026-11-10T12:00:00+00:00",
            },
        ]

        response = self.client.get(
            "/emergencies",
            params={
                "severity": 5,
                "status": "ACTIVE",
                "search": "critical",
            },
            headers=self.auth("admin-token")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(
            [alert["id"] for alert in response.json()["emergencies"]],
            [31]
        )

    def test_user_cannot_use_dashboard_filters_to_read_alerts(self):
        response = self.client.get(
            "/emergencies?severity=5&status=ACTIVE&search=critical",
            headers=self.auth("user-token")
        )

        self.assertEqual(response.status_code, 403)
        resqlink_app.get_alerts.assert_not_called()

    def test_dashboard_filter_values_are_validated(self):
        response = self.client.get(
            "/emergencies?severity=6",
            headers=self.auth("admin-token")
        )

        self.assertEqual(response.status_code, 422)
        resqlink_app.get_alerts.assert_not_called()

    def test_user_can_only_request_their_own_alerts(self):
        own_alert = {
            "id": 27,
            "severity": 3,
            "label": "HIGH",
            "priority": 60,
            "status": "ACTIVE",
            "created_at": "2026-11-10T10:00:00+00:00",
            "latitude": 12.9,
            "longitude": 77.5,
        }
        resqlink_app.get_alerts.return_value = [own_alert]

        response = self.client.get(
            "/emergencies/me",
            headers=self.auth("user-token")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["emergencies"][0]["id"], 27)
        self.assertIn("latitude", response.json()["emergencies"][0])
        resqlink_app.get_alerts.assert_called_once_with(USER_ID)

    def test_owner_scoped_alert_route_requires_authentication(self):
        response = self.client.get("/emergencies/me")
        self.assertEqual(response.status_code, 401)

    def test_valid_admin_can_resolve_alert(self):
        response = self.client.patch(
            "/emergency/27/resolve",
            headers=self.auth("admin-token")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "RESOLVED")

    def test_admin_resolution_reports_missing_alert(self):
        resqlink_app.resolve_alert.return_value = False

        response = self.client.patch(
            "/emergency/999/resolve",
            headers=self.auth("admin-token")
        )

        self.assertEqual(response.status_code, 404)

    def test_registration_still_uses_supabase_auth(self):
        self.auth_client.auth.sign_up.return_value = SimpleNamespace(
            user=SimpleNamespace(id=USER_ID, email="user@example.com")
        )

        response = self.client.post(
            "/register",
            json={
                "name": "New User",
                "email": "USER@example.com",
                "password": "secure-password"
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "USER")
        signup_options = self.auth_client.auth.sign_up.call_args.args[0]
        self.assertEqual(
            signup_options["options"]["data"],
            {"name": "New User"}
        )

    def test_registration_rejects_duplicate_email(self):
        self.auth_client.auth.sign_up.side_effect = AuthApiError(
            "Account exists", 422, "user_already_exists"
        )

        response = self.client.post(
            "/register",
            json={
                "name": "New User",
                "email": "user@example.com",
                "password": "secure-password"
            }
        )

        self.assertEqual(response.status_code, 409)

    def test_registration_reports_supabase_outage(self):
        self.auth_client.auth.sign_up.side_effect = AuthApiError(
            "Service unavailable", 503, None
        )

        response = self.client.post(
            "/register",
            json={
                "name": "New User",
                "email": "user@example.com",
                "password": "secure-password"
            }
        )

        self.assertEqual(response.status_code, 503)

    def test_login_still_returns_supabase_access_token(self):
        self.auth_client.auth.sign_in_with_password.return_value = SimpleNamespace(
            user=SimpleNamespace(id=USER_ID, email="user@example.com"),
            session=SimpleNamespace(access_token="user-token")
        )

        response = self.client.post(
            "/login",
            json={
                "email": "USER@example.com",
                "password": "secure-password"
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["access_token"], "user-token")
        self.assertEqual(response.json()["user"]["role"], "USER")

    def test_login_rejects_invalid_credentials(self):
        self.auth_client.auth.sign_in_with_password.side_effect = AuthApiError(
            "Invalid credentials", 401, None
        )

        response = self.client.post(
            "/login",
            json={
                "email": "user@example.com",
                "password": "incorrect-password"
            }
        )

        self.assertEqual(response.status_code, 401)

    @patch.dict(
        "os.environ",
        {"PASSWORD_RESET_REDIRECT_URL": "https://example.test/password-reset.html"}
    )
    def test_password_recovery_uses_supabase_and_fixed_redirect(self):
        response = self.client.post(
            "/password-recovery",
            json={"email": " USER@EXAMPLE.COM "}
        )

        self.assertEqual(response.status_code, 202)
        self.auth_client.auth.reset_password_email.assert_called_once_with(
            "user@example.com",
            options={
                "redirect_to": "https://example.test/password-reset.html"
            }
        )
        self.assertNotIn("user@example.com", response.json()["message"])

    @patch.dict("os.environ", {}, clear=False)
    def test_password_recovery_requires_redirect_configuration(self):
        with patch.dict("os.environ", {"PASSWORD_RESET_REDIRECT_URL": ""}):
            response = self.client.post(
                "/password-recovery",
                json={"email": "user@example.com"}
            )
        self.assertEqual(response.status_code, 503)
        self.auth_client.auth.reset_password_email.assert_not_called()

    def test_password_recovery_hides_unknown_email(self):
        self.auth_client.auth.reset_password_email.side_effect = AuthApiError(
            "User not found", 400, "user_not_found"
        )
        with patch.dict(
            "os.environ",
            {"PASSWORD_RESET_REDIRECT_URL": "https://example.test/password-reset.html"}
        ):
            response = self.client.post(
                "/password-recovery",
                json={"email": "missing@example.com"}
            )

        self.assertEqual(response.status_code, 202)
        self.assertNotIn("not found", response.json()["message"].lower())

    def test_password_recovery_surfaces_invalid_redirect_configuration(self):
        self.auth_client.auth.reset_password_email.side_effect = AuthApiError(
            "Invalid redirect URL", 400, "validation_failed"
        )
        with patch.dict(
            "os.environ",
            {"PASSWORD_RESET_REDIRECT_URL": "https://example.test/not-allowed"}
        ):
            response = self.client.post(
                "/password-recovery",
                json={"email": "user@example.com"}
            )

        self.assertEqual(response.status_code, 502)
        self.assertIn("redirect configuration", response.json()["detail"])

    def test_password_recovery_surfaces_supabase_rate_limit(self):
        self.auth_client.auth.reset_password_email.side_effect = AuthApiError(
            "Rate limit exceeded", 429, "over_email_send_rate_limit"
        )
        with patch.dict(
            "os.environ",
            {"PASSWORD_RESET_REDIRECT_URL": "https://example.test/password-reset.html"}
        ):
            response = self.client.post(
                "/password-recovery",
                json={"email": "user@example.com"}
            )

        self.assertEqual(response.status_code, 429)

    def test_password_update_requires_authenticated_user(self):
        response = self.client.post(
            "/password-update",
            json={"password": "new-password"}
        )
        self.assertEqual(response.status_code, 401)
        resqlink_app.update_supabase_password.assert_not_called()

    def test_password_update_uses_verified_access_token(self):
        response = self.client.post(
            "/password-update",
            headers=self.auth("user-token"),
            json={"password": "new-password"}
        )

        self.assertEqual(response.status_code, 200)
        resqlink_app.update_supabase_password.assert_called_once_with(
            "user-token",
            "new-password"
        )

    def test_password_update_rejects_short_password(self):
        response = self.client.post(
            "/password-update",
            headers=self.auth("user-token"),
            json={"password": "short"}
        )

        self.assertEqual(response.status_code, 422)
        resqlink_app.update_supabase_password.assert_not_called()

    def test_logout_requires_authenticated_user(self):
        response = self.client.post("/logout")
        self.assertEqual(response.status_code, 401)
        resqlink_app.revoke_supabase_session.assert_not_called()

    def test_logout_revokes_only_the_verified_users_session(self):
        response = self.client.post(
            "/logout",
            headers=self.auth("user-token")
        )
        self.assertEqual(response.status_code, 200)
        resqlink_app.revoke_supabase_session.assert_called_once_with("user-token")

    @patch.dict(
        "os.environ",
        {
            "SUPABASE_URL": "https://auth.example.test",
            "SUPABASE_KEY": "publishable-test-key",
            "SUPABASE_SERVICE_ROLE_KEY": "must-not-be-used",
        },
        clear=False
    )
    @patch("storage.httpx.put")
    def test_password_update_uses_anon_auth_api_and_verified_bearer(
        self,
        put
    ):
        put.return_value = SimpleNamespace(is_success=True, status_code=200)

        storage.update_supabase_password("recovery-access-token", "new-password")

        args, kwargs = put.call_args
        self.assertEqual(args[0], "https://auth.example.test/auth/v1/user")
        self.assertEqual(kwargs["headers"]["apikey"], "publishable-test-key")
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer recovery-access-token"
        )
        self.assertEqual(kwargs["json"], {"password": "new-password"})
        self.assertEqual(kwargs["timeout"], 10.0)
        self.assertNotEqual(
            kwargs["headers"]["apikey"],
            "must-not-be-used"
        )

    @patch.dict(
        "os.environ",
        {
            "SUPABASE_URL": "https://auth.example.test",
            "SUPABASE_KEY": "publishable-test-key",
        },
        clear=False
    )
    @patch("storage.httpx.post")
    def test_logout_requests_local_session_revocation(self, post):
        post.return_value = SimpleNamespace(is_success=True, status_code=204)

        storage.revoke_supabase_session("user-access-token")

        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://auth.example.test/auth/v1/logout")
        self.assertEqual(kwargs["params"], {"scope": "local"})
        self.assertEqual(kwargs["headers"]["apikey"], "publishable-test-key")
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer user-access-token"
        )

    def test_user_cannot_access_all_alert_locations(self):
        response = self.client.get(
            "/emergencies",
            headers=self.auth("user-token")
        )
        self.assertEqual(response.status_code, 403)
        resqlink_app.get_alerts.assert_not_called()

    def test_user_cannot_supply_another_owner_or_role(self):
        headers = self.auth("user-token")
        for field in ("user_id", "role"):
            payload = {
                "severity": 3,
                "latitude": 12.9,
                "longitude": 77.5,
                field: ADMIN_ID if field == "user_id" else "ADMIN",
            }
            response = self.client.post(
                "/emergency",
                headers=headers,
                json=payload
            )
            self.assertEqual(response.status_code, 422)
        resqlink_app.save_alert.assert_not_called()

    def test_invalid_emergency_values_are_rejected(self):
        headers = self.auth("user-token")
        for severity, latitude, longitude in (
            (True, 12.9, 77.5),
            (6, 12.9, 77.5),
            (3, 91, 77.5),
            (3, 12.9, 181),
            (3, None, 77.5),
        ):
            response = self.client.post(
                "/emergency",
                headers=headers,
                json={
                    "severity": severity,
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )
            self.assertEqual(response.status_code, 422)
        resqlink_app.save_alert.assert_not_called()

    def test_accuracy_must_be_finite_nonnegative_and_have_coordinates(self):
        headers = self.auth("user-token")
        for payload in (
            {
                "severity": 3,
                "latitude": 12.9,
                "longitude": 77.5,
                "location_accuracy_m": -1,
            },
            {
                "severity": 3,
                "latitude": None,
                "longitude": None,
                "location_accuracy_m": 5,
            },
            {
                "severity": 3,
                "latitude": True,
                "longitude": 77.5,
            },
        ):
            response = self.client.post(
                "/emergency",
                headers=headers,
                json=payload
            )
            self.assertEqual(response.status_code, 422)
        resqlink_app.save_alert.assert_not_called()

    def test_inaccurate_coordinates_require_explicit_confirmation(self):
        headers = self.auth("user-token")
        payload = {
            "severity": 3,
            "latitude": 12.9,
            "longitude": 77.5,
            "location_accuracy_m": 250,
        }

        rejected = self.client.post(
            "/emergency",
            headers=headers,
            json=payload
        )
        self.assertEqual(rejected.status_code, 422)
        resqlink_app.save_alert.assert_not_called()

        payload["location_accuracy_confirmed"] = True
        accepted = self.client.post(
            "/emergency",
            headers=headers,
            json=payload
        )
        self.assertEqual(accepted.status_code, 201)
        self.assertEqual(
            resqlink_app.save_alert.call_args.args[0]["location_accuracy_m"],
            250
        )

    def test_gps_unavailable_requires_explicit_null_location_fallback(self):
        response = self.client.post(
            "/emergency",
            headers=self.auth("user-token"),
            json={
                "severity": 5,
                "latitude": None,
                "longitude": None,
                "location_accuracy_m": None,
            }
        )

        self.assertEqual(response.status_code, 201)
        saved_alert = resqlink_app.save_alert.call_args.args[0]
        self.assertIsNone(saved_alert["latitude"])
        self.assertIsNone(saved_alert["longitude"])
        self.assertIsNone(saved_alert["location_accuracy_m"])

    def test_duplicate_submission_returns_original_alert(self):
        resqlink_app.save_alert.side_effect = [
            (27, False, "ACTIVE"),
            (27, True, "ACTIVE"),
        ]
        payload = {
            "severity": 3,
            "latitude": 12.9,
            "longitude": 77.5,
            "location_accuracy_m": 18.0,
        }

        first = self.client.post(
            "/emergency",
            headers=self.auth("user-token"),
            json=payload
        )
        second = self.client.post(
            "/emergency",
            headers=self.auth("user-token"),
            json=payload
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["alert_id"], first.json()["alert_id"])
        self.assertEqual(second.json()["submission_status"], "already_submitted")
        self.assertTrue(second.json()["duplicate"])

    def test_expired_session_is_rejected_without_saving(self):
        response = self.client.post(
            "/emergency",
            headers=self.auth("invalid"),
            json={"severity": 3, "latitude": 12.9, "longitude": 77.5}
        )

        self.assertEqual(response.status_code, 401)
        resqlink_app.save_alert.assert_not_called()

    def test_database_failure_returns_service_unavailable(self):
        resqlink_app.save_alert.side_effect = HTTPException(
            status_code=503,
            detail="Could not save the emergency to Supabase"
        )
        response = self.client.post(
            "/emergency",
            headers=self.auth("user-token"),
            json={"severity": 3, "latitude": 12.9, "longitude": 77.5}
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Could not save", response.json()["detail"])

    def test_missing_idempotency_key_is_rejected(self):
        response = self.client.post(
            "/emergency",
            headers={"Authorization": "Bearer user-token"},
            json={"severity": 3, "latitude": 12.9, "longitude": 77.5}
        )

        self.assertEqual(response.status_code, 422)
        resqlink_app.save_alert.assert_not_called()

    def test_non_finite_coordinates_are_rejected(self):
        with self.assertRaises(ValidationError):
            resqlink_app.EmergencyRequest(
                severity=3,
                latitude=12.9,
                longitude=float("inf")
            )

    def test_user_cannot_resolve_alert(self):
        response = self.client.patch(
            "/emergency/27/resolve",
            headers=self.auth("user-token")
        )
        self.assertEqual(response.status_code, 403)
        resqlink_app.resolve_alert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
