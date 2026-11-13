# Testing Guide (`TESTING.md`)

ResQlink's automated test suite validates backend APIs, C priority engine behavior, Supabase ownership/isolation logic, schema/RLS structure, static frontend asset integrity, and browser JS helpers without needing live Supabase credentials or GPS hardware.

## Prerequisites

- Python 3.12+ with dependencies installed (`pip install -r requirements-dev.txt`)
- A C compiler on `PATH` (e.g. `gcc` / MinGW-w64 on Windows or `build-essential` on Linux) for `conftest.py`'s temporary C-library build check
- Node.js 20+ on `PATH` for `frontend-tests/*.test.cjs`

## Running Backend & Platform Integrity Tests

```powershell
python -m pytest
```

### What `pytest` Covers
- `backend/test_engine.py`: C engine compilation, `calculate_priority`, and `severity_label` boundaries (`1..5` and invalid severities).
- `backend/test_auth.py`: Registration, sign-in, password recovery/update, session revocation, RBAC (`USER` vs `ADMIN`), validation, and idempotency key conflicts.
- `backend/test_ownership.py`: Ownership scoping (`user_id` isolation), coordinate validation, 100m accuracy gating, and historical migration assertions.
- `backend/test_request_controls.py`: Per-IP rate limiting and request body limits.
- `backend/test_classification.py`: All 7 emergency categories, 5 severity tiers, category-specific Level 4/5 service rules, Level 1 non-dispatch behavior, manual overrides, `/classification/*` endpoints, and `/emergency` classification payload attachment.
- `backend/test_contacts.py`: E.164 phone normalization, max 10 contacts limit, duplicate phone `409`, primary contact toggle, owner isolation, explicit consent requirement, honest `PROVIDER_NOT_CONFIGURED` / `MANUAL_FALLBACK` logging (never fabricating external delivery), and notification log retrieval.
- `backend/test_admin_simulator.py`: `/admin/overview`, category/service/date filtering, status lifecycle transitions (`ACKNOWLEDGED`, `DISPATCHED`, `RESOLVED`) with `admin_notes` & audit trail, `PATCH /me`, `POST /me/deletion-request`, all 14 simulator scenarios, isolation from `public.emergencies`, non-admin `403` enforcement, and a full mocked SOS-to-resolution end-to-end flow.
- `backend/test_platform_integrity.py`: Verifies all 12 HTML pages exist with mobile `viewport` tags, valid local `href`/`src` links, zero `service_role` leakage, RLS + `is_simulated = true` checks in SQL schemas, CI artifact copying in `.github/workflows/pages.yml`, and presence of all 7 documentation files.

## Running Frontend Unit & Module Tests

```powershell
node --test frontend-tests\auth-session.test.cjs frontend-tests\platform-ui.test.cjs
```

### What Frontend Tests Cover
- `frontend-tests/auth-session.test.cjs`: Tab-scoped `sessionStorage` isolation, token validation, and logout cleanup.
- `frontend-tests/platform-ui.test.cjs`: XSS-safe DOM helper (`ui-shell.js` using `textContent`, never `innerHTML`), `auth-pages.js` post-login redirect allowlist across all portals, and `emergency-api.js` `Idempotency-Key` + `RESQLINK_API_URL` integration.

## Continuous Integration Gate

[`.github/workflows/pages.yml`](./.github/workflows/pages.yml) runs both `pytest` and `node --test frontend-tests/*.test.cjs` on Ubuntu before building `_site/` and deploying to GitHub Pages. Any failing test aborts deployment.
