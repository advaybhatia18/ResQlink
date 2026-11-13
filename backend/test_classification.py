import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as resqlink_app
from classification import (
    EMERGENCY_CATEGORIES,
    SERVICE_CATALOG,
    classify_emergency,
    get_classification_config,
    validate_category,
    validate_services,
)

USER_ID = "b2f3ac97-d7c2-48f4-a714-9e0f7abc1234"


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(resqlink_app.app)

    def test_all_categories_and_services_defined(self):
        self.assertEqual(
            set(EMERGENCY_CATEGORIES.keys()),
            {
                "MEDICAL",
                "ROAD_ACCIDENT",
                "FIRE",
                "THEFT",
                "PERSONAL_SAFETY",
                "NATURAL_DISASTER",
                "OTHER",
            },
        )
        self.assertEqual(
            set(SERVICE_CATALOG.keys()),
            {"POLICE", "FIRE_RESCUE", "AMBULANCE_MEDICAL"},
        )

    def test_severity_level_1_has_no_auto_recommended_services(self):
        for category in EMERGENCY_CATEGORIES:
            result = classify_emergency(category, 1)
            self.assertEqual(result["priority"], 20)
            self.assertEqual(result["label"], "LOW")
            self.assertEqual(result["recommended_services"], [])
            self.assertEqual(result["requested_services"], [])
            self.assertIn("not medically validated triage", result["triage_disclaimer"])

    def test_level_4_and_5_are_category_specific_not_blindly_all_services(self):
        medical_4 = classify_emergency("MEDICAL", 4)
        self.assertEqual(medical_4["recommended_services"], ["AMBULANCE_MEDICAL"])
        self.assertEqual(medical_4["priority"], 80)

        theft_5 = classify_emergency("THEFT", 5)
        self.assertEqual(theft_5["recommended_services"], ["POLICE", "AMBULANCE_MEDICAL"])
        self.assertEqual(theft_5["priority"], 100)

        fire_5 = classify_emergency("FIRE", 5)
        self.assertEqual(
            fire_5["recommended_services"],
            ["FIRE_RESCUE", "AMBULANCE_MEDICAL", "POLICE"],
        )

    def test_manual_service_override_is_validated_and_deduplicated(self):
        result = classify_emergency(
            "FIRE",
            2,
            requested_services=["police", "FIRE_RESCUE", "POLICE"],
        )
        self.assertEqual(result["recommended_services"], ["FIRE_RESCUE"])
        self.assertEqual(result["requested_services"], ["POLICE", "FIRE_RESCUE"])
        cards = {card["id"]: card for card in result["service_cards"]}
        self.assertTrue(cards["POLICE"]["requested"])
        self.assertEqual(cards["POLICE"]["selection_status"], "MANUALLY_SELECTED")
        self.assertTrue(cards["FIRE_RESCUE"]["recommended"])
        self.assertFalse(cards["AMBULANCE_MEDICAL"]["requested"])

    def test_invalid_category_service_or_severity_raises_value_error(self):
        with self.assertRaises(ValueError):
            validate_category("ALIEN_INVASION")
        with self.assertRaises(ValueError):
            validate_services(["COAST_GUARD"])
        with self.assertRaises(ValueError):
            classify_emergency("MEDICAL", 9)

    def test_public_classification_endpoints(self):
        config_res = self.client.get("/classification/config")
        self.assertEqual(config_res.status_code, 200)
        cfg = config_res.json()
        self.assertEqual(len(cfg["categories"]), 7)
        self.assertEqual(len(cfg["severity_levels"]), 5)
        self.assertEqual(len(cfg["services"]), 3)
        self.assertEqual(cfg, get_classification_config())

        rec_res = self.client.post(
            "/classification/recommend",
            json={"category": "ROAD_ACCIDENT", "severity": 4},
        )
        self.assertEqual(rec_res.status_code, 200)
        body = rec_res.json()
        self.assertEqual(body["priority"], 80)
        self.assertEqual(
            body["recommended_services"],
            ["AMBULANCE_MEDICAL", "POLICE", "FIRE_RESCUE"],
        )

    def test_emergency_submission_attaches_classification_payload(self):
        auth_client = MagicMock()
        auth_client.auth.get_user.return_value = SimpleNamespace(
            user=SimpleNamespace(
                id=USER_ID,
                email="user@example.com",
                user_metadata={"name": "Member"},
            )
        )
        with (
            patch("app.get_auth_client", return_value=auth_client),
            patch(
                "app.get_user_profile",
                return_value={"id": USER_ID, "name": "Member", "role": "USER"},
            ),
            patch("app.save_alert", return_value=(105, False, "ACTIVE")) as save_mock,
        ):
            res = self.client.post(
                "/emergency",
                headers={
                    "Authorization": "Bearer user-token",
                    "Idempotency-Key": "classify-key-123",
                },
                json={
                    "severity": 4,
                    "category": "FIRE",
                    "requested_services": ["FIRE_RESCUE", "AMBULANCE_MEDICAL"],
                    "notes": "Smoke seen near kitchen vent.",
                },
            )
        self.assertEqual(res.status_code, 201)
        payload = res.json()
        self.assertEqual(payload["classification"]["category"], "FIRE")
        self.assertEqual(
            payload["classification"]["requested_services"],
            ["FIRE_RESCUE", "AMBULANCE_MEDICAL"],
        )
        saved_dict = save_mock.call_args.args[0]
        self.assertEqual(saved_dict["category"], "FIRE")
        self.assertEqual(saved_dict["notes"], "Smoke seen near kitchen vent.")


if __name__ == "__main__":
    unittest.main()
