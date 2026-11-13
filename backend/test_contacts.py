import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as resqlink_app
import contacts

USER_ID = "b2f3ac97-d7c2-48f4-a714-9e0f7abc1234"
OTHER_USER_ID = "99999999-27de-4d67-82a4-2ce5aabb5678"


def _auth_client_for(uid: str):
    mock = MagicMock()
    mock.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id=uid, email="user@example.com", user_metadata={"name": "User"})
    )
    return mock


class ContactsUnitAndApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(resqlink_app.app)

    def test_phone_normalization_and_validation(self):
        self.assertEqual(contacts.normalize_phone(" +1 (415) 555-0199 "), "+14155550199")
        self.assertEqual(contacts.normalize_phone("0091 9876543210"), "+919876543210")
        with self.assertRaises(ValueError):
            contacts.normalize_phone("123")
        with self.assertRaises(ValueError):
            contacts.normalize_phone("not-a-phone")

    def test_crud_and_honest_notification_fallback_via_api(self):
        sample_contact = {
            "id": 7,
            "user_id": USER_ID,
            "name": "Asha Patel",
            "phone": "+919876543210",
            "relationship": "Parent",
            "is_primary": True,
            "created_at": "2026-11-13T10:00:00Z",
            "updated_at": "2026-11-13T10:00:00Z",
        }
        updated_contact = {**sample_contact, "relationship": "Mother"}

        with (
            patch("app.get_auth_client", return_value=_auth_client_for(USER_ID)),
            patch("app.get_user_profile", return_value={"id": USER_ID, "name": "User", "role": "USER"}),
            patch("app.list_contacts", return_value=[{k: v for k, v in sample_contact.items() if k != "user_id"}]),
            patch("app.create_contact", return_value={k: v for k, v in sample_contact.items() if k != "user_id"}),
            patch("app.update_contact", return_value={k: v for k, v in updated_contact.items() if k != "user_id"}),
            patch("app.delete_contact", return_value=True),
            patch(
                "app.list_notification_logs",
                return_value=[{"id": 1, "contact_id": 7, "channel": "SMS", "status": "PROVIDER_NOT_CONFIGURED"}],
            ),
        ):
            list_res = self.client.get("/contacts", headers={"Authorization": "Bearer tok"})
            self.assertEqual(list_res.status_code, 200)
            self.assertEqual(list_res.json()["count"], 1)

            create_res = self.client.post(
                "/contacts",
                headers={"Authorization": "Bearer tok"},
                json={
                    "name": "Asha Patel",
                    "phone": "+91 98765-43210",
                    "relationship": "Parent",
                    "is_primary": True,
                },
            )
            self.assertEqual(create_res.status_code, 201)
            self.assertEqual(create_res.json()["contact"]["phone"], "+919876543210")

            patch_res = self.client.patch(
                "/contacts/7",
                headers={"Authorization": "Bearer tok"},
                json={"relationship": "Mother"},
            )
            self.assertEqual(patch_res.status_code, 200)
            self.assertEqual(patch_res.json()["contact"]["relationship"], "Mother")

            logs_res = self.client.get("/contacts/notifications", headers={"Authorization": "Bearer tok"})
            self.assertEqual(logs_res.status_code, 200)
            self.assertEqual(logs_res.json()["count"], 1)

            del_res = self.client.delete("/contacts/7", headers={"Authorization": "Bearer tok"})
            self.assertEqual(del_res.status_code, 200)

    def test_duplicate_phone_and_max_limit_and_consent_enforcement(self):
        existing = [
            {"id": idx, "name": f"C{idx}", "phone": f"+155500000{idx:02d}", "relationship": "Friend", "is_primary": idx == 1}
            for idx in range(1, 11)
        ]
        with patch("contacts.list_contacts", return_value=existing):
            with self.assertRaises(contacts.HTTPException) as limit_exc:
                contacts.create_contact(USER_ID, "Extra", "+15559999999", "Sibling")
            self.assertEqual(limit_exc.exception.status_code, 400)

        with patch("contacts.list_contacts", return_value=existing[:1]):
            with self.assertRaises(contacts.HTTPException) as dup_exc:
                contacts.create_contact(USER_ID, "Dup", "+15550000001", "Sibling")
            self.assertEqual(dup_exc.exception.status_code, 409)

        with self.assertRaises(contacts.HTTPException) as consent_exc:
            contacts.record_notification_attempt(USER_ID, 1, "SMS", consent_confirmed=False)
        self.assertEqual(consent_exc.exception.status_code, 422)

    def test_notify_fallback_never_claims_external_delivery(self):
        fake_db = MagicMock()
        fake_db.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": 91}]
        )
        with (
            patch("contacts.get_contact", return_value={"id": 7, "name": "Asha", "phone": "+919876543210", "relationship": "Parent", "is_primary": True}),
            patch("contacts.get_database_client", return_value=fake_db),
        ):
            sms_attempt = contacts.record_notification_attempt(
                USER_ID,
                7,
                channel="SMS",
                consent_confirmed=True,
                message_preview="Need help near Main Rd",
            )
            manual_attempt = contacts.record_notification_attempt(
                USER_ID,
                7,
                channel="MANUAL_TEL",
                consent_confirmed=True,
            )

        self.assertFalse(sms_attempt["sent"])
        self.assertEqual(sms_attempt["status"], "PROVIDER_NOT_CONFIGURED")
        self.assertEqual(sms_attempt["manual_fallback"]["tel_uri"], "tel:+919876543210")

        self.assertFalse(manual_attempt["sent"])
        self.assertEqual(manual_attempt["status"], "MANUAL_FALLBACK")

    def test_ownership_enforcement_rejects_mismatched_user_row(self):
        fake_db = MagicMock()
        query = fake_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value
        query.execute.return_value = SimpleNamespace(
            data=[{"id": 7, "user_id": OTHER_USER_ID, "name": "Other", "phone": "+15551112222", "relationship": "Peer", "is_primary": False}]
        )
        with patch("contacts.get_database_client", return_value=fake_db):
            with self.assertRaises(contacts.HTTPException) as exc:
                contacts.get_contact(USER_ID, 7)
        self.assertEqual(exc.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
