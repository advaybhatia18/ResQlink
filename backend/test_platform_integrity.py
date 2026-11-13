import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_PAGES = [
    "index.html",
    "register.html",
    "login.html",
    "password-reset.html",
    "user-dashboard.html",
    "sos.html",
    "history.html",
    "contacts.html",
    "admin-login.html",
    "dashboard.html",
    "simulator.html",
    "settings.html",
]

REQUIRED_DOCS = [
    "README.md",
    "TODO.md",
    "DEPLOYMENT.md",
    "TESTING.md",
    "ARCHITECTURE.md",
    "SUPABASE_SETUP.md",
    "API_DOCUMENTATION.md",
]


class PlatformIntegrityTests(unittest.TestCase):
    def test_all_12_html_pages_exist_with_viewport_and_valid_local_assets(self):
        for page in REQUIRED_PAGES:
            path = ROOT / page
            self.assertTrue(path.exists(), f"Missing HTML page: {page}")
            content = path.read_text(encoding="utf-8")
            self.assertIn('name="viewport"', content, f"Missing mobile viewport meta on {page}")
            self.assertNotIn("service_role", content.lower(), f"Forbidden service_role reference in {page}")

            for attr in ("href", "src"):
                for target in re.findall(rf'{attr}=["\']([^"\']+)["\']', content):
                    clean = target.split("#", 1)[0].split("?", 1)[0].strip()
                    if not clean or clean.startswith(("http://", "https://", "mailto:", "tel:", "data:", "#")):
                        continue
                    self.assertTrue(
                        (ROOT / clean).exists(),
                        f"{page} references missing local asset {attr}='{target}'",
                    )

    def test_supabase_migration_and_schema_rls_and_isolation(self):
        schema_sql = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
        migration_sql = (
            ROOT / "supabase" / "migrations" / "20261113_complete_platform_schema.sql"
        ).read_text(encoding="utf-8")

        for sql_text, label in ((schema_sql, "schema.sql"), (migration_sql, "20261113_complete_platform_schema.sql")):
            for table in (
                "emergency_contacts",
                "contact_notification_logs",
                "emergency_status_history",
                "admin_audit_logs",
                "simulator_scenarios",
                "simulator_runs",
            ):
                self.assertIn(f"public.{table}", sql_text, f"{label} missing table {table}")
                self.assertIn(
                    f"alter table public.{table} enable row level security",
                    sql_text.lower(),
                    f"{label} must enable RLS on {table}",
                )
            self.assertIn("is_simulated boolean not null default true check (is_simulated = true)", sql_text.lower())

    def test_ci_workflow_copies_all_js_and_runs_tests(self):
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("cp *.html *.css *.js _site/", workflow)
        self.assertIn("pytest", workflow)
        self.assertIn("frontend-tests", workflow)

    def test_documentation_files_present(self):
        for doc in REQUIRED_DOCS:
            self.assertTrue((ROOT / doc).exists(), f"Missing documentation file: {doc}")


if __name__ == "__main__":
    unittest.main()
