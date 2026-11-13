import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as resqlink_app
import simulator

USER_ID = "b2f3ac97-d7c2-48f4-a714-9e0f7abc1234"
ADMIN_ID = "83c9e76b-27de-4d67-82a4-2ce5aabb5678"


def _auth_for(uid: str, name: str = "Tester"):
    mock = MagicMock()
    mock.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id=uid, email=f"{name.lower()}@example.com", user_metadata={"name": name})
    )
    return mock


class AdminAndSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(resqlink_app.app)

    def test_admin_overview_and_status_lifecycle_and_audit_logs(self):
        sample_alerts = [
            {
                "id": 11,
                "severity": 5,
                "label": "CRITICAL",
                "priority": 100,
                "status": "ACTIVE",
                "category": "FIRE",
                "requested_services": ["FIRE_RESCUE", "AMBULANCE_MEDICAL"],
                "created_at": "2026-11-13T10:00:00Z",
            },
            {
                "id": 12,
                "severity": 2,
                "label": "MODERATE",
                "priority": 40,
                "status": "RESOLVED",
                "category": "THEFT",
                "requested_services": ["POLICE"],
                "created_at": "2026-11-12T10:00:00Z",
            },
        ]
        updated_record = {
            "id": 11,
            "severity": 5,
            "label": "CRITICAL",
            "priority": 100,
            "status": "ACKNOWLEDGED",
            "admin_notes": "Unit 4 assigned",
            "category": "FIRE",
        }

        with (
            patch("app.get_auth_client", return_value=_auth_for(ADMIN_ID, "Admin")),
            patch("app.get_user_profile", return_value={"id": ADMIN_ID, "name": "Admin", "role": "ADMIN"}),
            patch("app.get_alerts", return_value=sample_alerts),
            patch("app.update_alert_status", return_value=updated_record),
            patch("app.get_admin_audit_logs", return_value=[{"id": 1, "action": "STATUS_ACKNOWLEDGED", "emergency_id": 11}]),
        ):
            overview = self.client.get("/admin/overview", headers={"Authorization": "Bearer admin-tok"})
            self.assertEqual(overview.status_code, 200)
            ov = overview.json()
            self.assertEqual(ov["total_alerts"], 2)
            self.assertEqual(ov["active_emergencies"], 1)
            self.assertEqual(ov["critical_emergencies"], 1)
            self.assertEqual(ov["by_category"]["FIRE"], 1)

            filtered = self.client.get(
                "/emergencies?category=FIRE&service=FIRE_RESCUE",
                headers={"Authorization": "Bearer admin-tok"},
            )
            self.assertEqual(filtered.status_code, 200)
            self.assertEqual(filtered.json()["count"], 1)

            status_res = self.client.patch(
                "/emergencies/11/status",
                headers={"Authorization": "Bearer admin-tok"},
                json={"status": "ACKNOWLEDGED", "admin_notes": "Unit 4 assigned"},
            )
            self.assertEqual(status_res.status_code, 200)
            self.assertEqual(status_res.json()["status"], "ACKNOWLEDGED")

            logs = self.client.get("/admin/audit-logs", headers={"Authorization": "Bearer admin-tok"})
            self.assertEqual(logs.status_code, 200)
            self.assertEqual(logs.json()["count"], 1)

    def test_standard_user_rejected_from_admin_and_simulator_routes(self):
        with (
            patch("app.get_auth_client", return_value=_auth_for(USER_ID, "Member")),
            patch("app.get_user_profile", return_value={"id": USER_ID, "name": "Member", "role": "USER"}),
        ):
            for path in ("/admin/overview", "/admin/audit-logs", "/simulator/scenarios", "/simulator/runs"):
                res = self.client.get(path, headers={"Authorization": "Bearer user-tok"})
                self.assertEqual(res.status_code, 403, f"Expected 403 on {path}")

            post_res = self.client.post(
                "/simulator/run",
                headers={"Authorization": "Bearer user-tok"},
                json={"scenario_id": "sim-medical-urgent"},
            )
            self.assertEqual(post_res.status_code, 403)

    def test_profile_update_and_deletion_request(self):
        with (
            patch("app.get_auth_client", return_value=_auth_for(USER_ID, "Member")),
            patch("app.get_user_profile", return_value={"id": USER_ID, "name": "Member", "role": "USER"}),
            patch("app.update_user_profile", return_value={"id": USER_ID, "name": "Updated Name", "phone": "+15551234567", "role": "USER"}),
            patch("app.request_account_deletion", return_value={"id": USER_ID, "deletion_requested_at": "2026-11-13T11:00:00Z"}),
        ):
            patch_res = self.client.patch(
                "/me",
                headers={"Authorization": "Bearer user-tok"},
                json={"name": "Updated Name", "phone": "+15551234567"},
            )
            self.assertEqual(patch_res.status_code, 200)
            self.assertEqual(patch_res.json()["name"], "Updated Name")

            del_res = self.client.post(
                "/me/deletion-request",
                headers={"Authorization": "Bearer user-tok"},
            )
            self.assertEqual(del_res.status_code, 202)
            self.assertIn("deletion_requested_at", del_res.json())

    def test_simulator_runs_all_14_scenarios_strictly_isolated(self):
        fake_db = MagicMock()
        counter = {"id": 0}

        def insert_side_effect(payload):
            counter["id"] += 1
            exec_mock = MagicMock()
            exec_mock.execute.return_value = SimpleNamespace(
                data=[{"id": counter["id"], "created_at": "2026-11-13T12:00:00Z", **payload}]
            )
            return exec_mock

        fake_db.table.return_value.insert.side_effect = insert_side_effect

        scenarios = simulator.list_scenarios()
        self.assertEqual(len(scenarios), 14)

        with patch("simulator.get_database_client", return_value=fake_db):
            for scenario in scenarios:
                run = simulator.run_simulation(
                    admin_id=ADMIN_ID,
                    scenario_id=scenario["id"],
                    delay_ms=0,
                )
                self.assertTrue(run["is_simulated"])
                self.assertTrue(str(run["generated_emergency_id"]).startswith("SIM-"))

        touched_tables = {call.args[0] for call in fake_db.table.call_args_list}
        self.assertEqual(touched_tables, {"simulator_runs"})
        self.assertNotIn("emergencies", touched_tables)

    def test_simulator_api_lifecycle_and_reset(self):
        fake_db = MagicMock()
        fake_db.table.return_value.update.return_value.eq.return_value.select.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": 5, "simulated_status": "SIMULATED_DISPATCHED", "is_simulated": True}]
        )
        fake_db.table.return_value.delete.return_value.eq.return_value.select.return_value.execute.return_value = SimpleNamespace(
            data=[{"id": 5}, {"id": 6}]
        )
        with (
            patch("app.get_auth_client", return_value=_auth_for(ADMIN_ID, "Admin")),
            patch("app.get_user_profile", return_value={"id": ADMIN_ID, "name": "Admin", "role": "ADMIN"}),
            patch("simulator.get_database_client", return_value=fake_db),
        ):
            sc_res = self.client.get("/simulator/scenarios", headers={"Authorization": "Bearer admin-tok"})
            self.assertEqual(sc_res.status_code, 200)
            self.assertEqual(sc_res.json()["count"], 14)

            tr_res = self.client.patch(
                "/simulator/runs/5/status?status=SIMULATED_DISPATCHED",
                headers={"Authorization": "Bearer admin-tok"},
            )
            self.assertEqual(tr_res.status_code, 200)
            self.assertEqual(tr_res.json()["run"]["simulated_status"], "SIMULATED_DISPATCHED")

            clr_res = self.client.delete("/simulator/runs", headers={"Authorization": "Bearer admin-tok"})
            self.assertEqual(clr_res.status_code, 200)
            self.assertEqual(clr_res.json()["deleted_count"], 2)

    def test_end_to_end_mocked_workflow_user_to_admin(self):
        saved_alerts: dict[int, dict] = {}
        history_rows: dict[int, list] = {}

        def fake_save_alert(result, user_id, _key):
            new_id = len(saved_alerts) + 1
            saved_alerts[new_id] = {
                "id": new_id,
                "user_id": user_id,
                "severity": result["severity"],
                "label": result["label"],
                "priority": result["priority"],
                "status": "ACTIVE",
                "category": result.get("category", "MEDICAL"),
                "recommended_services": result.get("recommended_services", []),
                "requested_services": result.get("requested_services", []),
                "latitude": result.get("latitude"),
                "longitude": result.get("longitude"),
                "location_accuracy_m": result.get("location_accuracy_m"),
                "notes": result.get("notes"),
                "admin_notes": None,
                "created_at": "2026-11-13T12:05:00Z",
            }
            history_rows[new_id] = [{"status": "ACTIVE", "note": "Alert submitted", "created_at": "2026-11-13T12:05:00Z"}]
            return new_id, False, "ACTIVE"

        def fake_update_status(alert_id, target_status, _admin_id, admin_notes=None):
            row = saved_alerts[alert_id]
            row["status"] = target_status
            if admin_notes:
                row["admin_notes"] = admin_notes
            history_rows[alert_id].append({"status": target_status, "note": admin_notes, "created_at": "2026-11-13T12:06:00Z"})
            return row

        def fake_detail(alert_id, user_id=None):
            row = saved_alerts[alert_id]
            return {**row, "status_history": history_rows[alert_id]}

        with (
            patch("app.get_auth_client", side_effect=lambda: _auth_for(ADMIN_ID, "Admin")),
            patch("app.get_user_profile", side_effect=lambda uid: {"id": uid, "name": "Person", "role": "ADMIN" if uid == ADMIN_ID else "USER"}),
            patch("app.save_alert", side_effect=fake_save_alert),
            patch("app.update_alert_status", side_effect=fake_update_status),
            patch("app.get_alert_detail", side_effect=fake_detail),
        ):
            sos = self.client.post(
                "/emergency",
                headers={"Authorization": "Bearer admin-tok", "Idempotency-Key": "e2e-flow-1"},
                json={"severity": 5, "category": "MEDICAL", "latitude": 28.6, "longitude": 77.2, "location_accuracy_m": 15},
            )
            self.assertEqual(sos.status_code, 201)
            alert_id = sos.json()["alert_id"]

            for next_status in ("ACKNOWLEDGED", "DISPATCHED", "RESOLVED"):
                upd = self.client.patch(
                    f"/emergencies/{alert_id}/status",
                    headers={"Authorization": "Bearer admin-tok"},
                    json={"status": next_status, "admin_notes": f"Moved to {next_status}"},
                )
                self.assertEqual(upd.status_code, 200)

            detail = self.client.get(f"/emergencies/{alert_id}", headers={"Authorization": "Bearer admin-tok"})
            self.assertEqual(detail.status_code, 200)
            body = detail.json()
            self.assertEqual(body["status"], "RESOLVED")
            self.assertEqual([h["status"] for h in body["status_history"]], ["ACTIVE", "ACKNOWLEDGED", "DISPATCHED", "RESOLVED"])


if __name__ == "__main__":
    unittest.main()
