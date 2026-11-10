import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage


USER_ID = "b2f3ac97-d7c2-48f4-a714-9e0f7abc1234"
OTHER_USER_ID = "83c9e76b-27de-4d67-82a4-2ce5aabb5678"
IDEMPOTENCY_KEY = "42542a3c-a73d-455f-9388-893fce868a47"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = (
    PROJECT_ROOT
    / "supabase"
    / "migrations"
    / "20261110_emergency_user_ownership.sql"
)
SUBMISSION_MIGRATION_PATH = (
    PROJECT_ROOT
    / "supabase"
    / "migrations"
    / "20261110163248_emergency_submission_safety.sql"
)


def alert_record(user_id=USER_ID):
    return {
        "id": 42,
        "user_id": user_id,
        "severity": 3,
        "label": "HIGH",
        "priority": 60,
        "status": "ACTIVE",
        "created_at": "2026-11-10T10:00:00+00:00",
        "latitude": 12.9,
        "longitude": 77.5,
    }


class StorageOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.query = self.client.table.return_value.select.return_value
        self.query.eq.return_value = self.query
        self.query.limit.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        self.query.order.return_value.execute.return_value = SimpleNamespace(
            data=[alert_record()]
        )
        self.database_patch = patch(
            "storage.get_database_client",
            return_value=self.client
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)

    def test_user_query_is_filtered_by_authenticated_owner(self):
        records = storage.get_alerts(USER_ID)

        self.query.eq.assert_called_once_with("user_id", USER_ID)
        self.assertEqual(len(records), 1)
        self.assertNotIn("user_id", records[0])

    def test_owner_query_rejects_foreign_rows(self):
        self.query.order.return_value.execute.return_value = SimpleNamespace(
            data=[alert_record(OTHER_USER_ID)]
        )

        with self.assertRaises(HTTPException) as error:
            storage.get_alerts(USER_ID)

        self.assertEqual(error.exception.status_code, 503)

    def test_admin_query_is_unfiltered(self):
        storage.get_alerts()
        self.query.eq.assert_not_called()

    def test_invalid_emergency_is_rejected_before_database_write(self):
        invalid = {
            "severity": 5,
            "label": "CRITICAL",
            "priority": 100,
            "latitude": float("nan"),
            "longitude": 77.5,
        }

        with self.assertRaises(HTTPException) as error:
            storage.save_alert(invalid, USER_ID, IDEMPOTENCY_KEY)

        self.assertEqual(error.exception.status_code, 422)
        self.client.table.assert_not_called()

    def test_unknown_authenticated_owner_is_rejected(self):
        emergency = {
            "severity": 3,
            "label": "HIGH",
            "priority": 60,
            "latitude": 12.9,
            "longitude": 77.5,
        }

        with self.assertRaises(HTTPException) as error:
            storage.save_alert(
                emergency,
                "not-a-user-uuid",
                IDEMPOTENCY_KEY
            )

        self.assertEqual(error.exception.status_code, 401)
        self.client.table.assert_not_called()

    def test_alert_insert_sets_owner_from_authenticated_argument(self):
        insert_query = self.client.table.return_value.insert.return_value
        insert_query.execute.return_value = SimpleNamespace(
            data=[{
                "id": 42,
                "user_id": USER_ID,
                "idempotency_key": IDEMPOTENCY_KEY,
                "status": "ACTIVE",
            }]
        )
        emergency = {
            "severity": 3,
            "label": "HIGH",
            "priority": 60,
            "latitude": 12.9,
            "longitude": 77.5,
            "location_accuracy_m": 18.0,
        }

        alert_id, duplicate, status = storage.save_alert(
            emergency,
            USER_ID,
            IDEMPOTENCY_KEY
        )

        self.assertEqual(alert_id, 42)
        self.assertFalse(duplicate)
        self.assertEqual(status, "ACTIVE")
        inserted = self.client.table.return_value.insert.call_args.args[0]
        self.assertEqual(inserted["user_id"], USER_ID)
        self.assertEqual(inserted["idempotency_key"], IDEMPOTENCY_KEY)
        self.assertEqual(inserted["location_accuracy_m"], 18.0)
        self.assertNotIn("created_by", inserted)

    def test_retry_with_same_key_returns_existing_alert(self):
        self.query.limit.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "id": 42,
                "user_id": USER_ID,
                "idempotency_key": IDEMPOTENCY_KEY,
                "severity": 3,
                "latitude": 12.9,
                "longitude": 77.5,
                "location_accuracy_m": 18.0,
                "status": "ACTIVE",
            }]
        )
        emergency = {
            "severity": 3,
            "label": "HIGH",
            "priority": 60,
            "latitude": 12.9,
            "longitude": 77.5,
            "location_accuracy_m": 18.0,
        }

        result = storage.save_alert(emergency, USER_ID, IDEMPOTENCY_KEY)

        self.assertEqual(result, (42, True, "ACTIVE"))
        self.client.table.return_value.insert.assert_not_called()

    def test_same_key_with_different_payload_is_conflict(self):
        self.query.limit.return_value.execute.return_value = SimpleNamespace(
            data=[{
                "id": 42,
                "user_id": USER_ID,
                "idempotency_key": IDEMPOTENCY_KEY,
                "severity": 3,
                "latitude": 12.9,
                "longitude": 77.5,
                "location_accuracy_m": None,
                "status": "ACTIVE",
            }]
        )
        emergency = {
            "severity": 4,
            "label": "VERY HIGH",
            "priority": 80,
            "latitude": 12.9,
            "longitude": 77.5,
            "location_accuracy_m": None,
        }

        with self.assertRaises(HTTPException) as error:
            storage.save_alert(emergency, USER_ID, IDEMPOTENCY_KEY)

        self.assertEqual(error.exception.status_code, 409)
        self.client.table.return_value.insert.assert_not_called()

    def test_no_location_alert_stores_null_coordinates(self):
        insert_query = self.client.table.return_value.insert.return_value
        insert_query.execute.return_value = SimpleNamespace(
            data=[{
                "id": 43,
                "user_id": USER_ID,
                "idempotency_key": IDEMPOTENCY_KEY,
                "status": "ACTIVE",
            }]
        )
        emergency = {
            "severity": 5,
            "label": "CRITICAL",
            "priority": 100,
            "latitude": None,
            "longitude": None,
            "location_accuracy_m": None,
        }

        result = storage.save_alert(emergency, USER_ID, IDEMPOTENCY_KEY)

        inserted = self.client.table.return_value.insert.call_args.args[0]
        self.assertIsNone(inserted["latitude"])
        self.assertIsNone(inserted["longitude"])
        self.assertEqual(result, (43, False, "ACTIVE"))

class OwnershipMigrationTests(unittest.TestCase):
    def test_migration_preserves_unowned_alerts_for_review(self):
        migration = MIGRATION_PATH.read_text(encoding="utf-8").lower()

        self.assertIn("add column if not exists user_id uuid", migration)
        self.assertIn("where emergency.user_id is null", migration)
        self.assertIn("emergency.created_by is not null", migration)
        self.assertIn("profile.id = emergency.created_by", migration)
        self.assertIn("do not infer ownership", migration)
        self.assertNotIn("delete from public.emergencies", migration)
        self.assertNotIn("truncate public.emergencies", migration)

    def test_rls_and_column_grants_protect_owner_field(self):
        migration = MIGRATION_PATH.read_text(encoding="utf-8").lower()

        self.assertIn("enable row level security", migration)
        self.assertIn("user_id = (select auth.uid())", migration)
        self.assertIn("grant select on public.emergencies to authenticated", migration)
        self.assertNotRegex(
            migration,
            r"grant\s+[^;]*(?:insert|update|delete)[^;]*"
            r"\s+on public\.emergencies to authenticated"
        )

    def test_migration_adds_retry_key_and_accuracy_without_dropping_rows(self):
        migration = SUBMISSION_MIGRATION_PATH.read_text(encoding="utf-8").lower()

        self.assertIn("add column if not exists idempotency_key uuid", migration)
        self.assertIn("add column if not exists location_accuracy_m double precision", migration)
        self.assertIn("alter column latitude drop not null", migration)
        self.assertIn("alter column longitude drop not null", migration)
        self.assertIn(
            "emergencies_user_id_idempotency_key_idx",
            migration
        )
        self.assertIn("emergencies_coordinates_paired_check", migration)
        self.assertIn("emergencies_latitude_range_check", migration)
        self.assertIn("emergencies_longitude_range_check", migration)
        self.assertIn("not valid", migration)
        self.assertNotIn("delete from public.emergencies", migration)


if __name__ == "__main__":
    unittest.main()
