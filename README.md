# ResQlink

ResQlink is an emergency-assistance platform, triage classification aid, personal safety contact hub, and isolated responder simulator. Its FastAPI backend uses Supabase Auth for authentication and Supabase Postgres (with Row Level Security) for storage, while the native C engine in `core/` calculates deterministic emergency priorities and severity labels. The frontend consists of 12 mobile-first static HTML/CSS/JS pages deployed to GitHub Pages.

> **Important Safety Notice:** Submitting or storing an alert in ResQlink does **not** automatically notify or dispatch public police, fire, or medical services unless an authorized external integration is explicitly configured. For real emergencies, contact your local emergency number (e.g., 112 / 911 / 999) directly. Priority and service recommendations are operational routing aids only, not medically validated triage.

## Pages & Portals

1. [`index.html`](./index.html) — Landing page, safety disclaimer, platform overview, and dynamic member/admin entry links
2. [`register.html`](./register.html) — New member account registration
3. [`login.html`](./login.html) — Member sign-in portal
4. [`password-reset.html`](./password-reset.html) — Dual-mode password recovery email request and token-based reset
5. [`user-dashboard.html`](./user-dashboard.html) — Authenticated member hub (profile summary, emergency contacts snapshot, quick SOS, recent alerts)
6. [`sos.html`](./sos.html) — Primary SOS console (category + severity 1–5 selection, live service recommendations, GPS capture with >100m accuracy guard, Leaflet location preview, idempotency retry, and emergency contacts check-in fallback)
7. [`history.html`](./history.html) — Personal emergency history with status/category filtering and timeline detail modal
8. [`contacts.html`](./contacts.html) — Trusted emergency contacts CRUD (up to 10 contacts, primary toggle, `tel:` & copy fallback, consent-logged notification audit trail)
9. [`settings.html`](./settings.html) — Profile editor, password update, session revocation, and account deletion request
10. [`admin-login.html`](./admin-login.html) — Administrator portal sign-in with backend role verification
11. [`dashboard.html`](./dashboard.html) — Admin Command Center (overview analytics, multi-filter queue, Leaflet marker map, emergency status workflow `ACTIVE -> ACKNOWLEDGED -> DISPATCHED -> RESOLVED`, admin notes, and audit logs)
12. [`simulator.html`](./simulator.html) — Strictly isolated Admin Simulator (14 prebuilt scenarios + custom scenario runner + simulated lifecycle transitions stored separately in `simulator_runs`)

## Repository Layout

```text
.
├── *.html                     # 12 static frontend pages
├── theme.css, auth.css        # Accessible responsive stylesheets
├── emergency.css              # Legacy SOS utility stylesheet (retained)
├── api-config.js              # API base URL configuration (overwritten in CI for Pages)
├── auth-session.js            # Tab-scoped session storage and authenticated API client
├── auth-pages.js              # Auth forms & redirect allowlist
├── ui-shell.js                # Shared navigation shell & XSS-safe DOM helpers
├── emergency-api.js           # SOS submission API client
├── emergency-submit.js        # GPS validation, service selection, idempotent retries
├── backend/
│   ├── app.py                 # FastAPI routes, RBAC, middleware wiring
│   ├── auth.py                # Supabase Auth token validation & role lookups
│   ├── classification.py      # 7 categories, 5 severities, 3 services recommendation rules
│   ├── contacts.py            # Emergency contacts CRUD & honest notification audit logging
│   ├── emergency_engine.py    # ctypes wrapper around core C engine with pure-Python fallback
│   ├── location.py            # Coordinate & accuracy validation
│   ├── request_controls.py    # Rate limiting & request size caps
│   ├── simulator.py           # Isolated simulator engine (writes only to simulator_runs)
│   ├── storage.py             # Supabase Postgres persistence, status history, audit logs
│   ├── requirements.txt       # Backend runtime dependencies
│   └── test_*.py              # Automated backend unit, integration & integrity tests
├── core/
│   └── emergency.c            # Native C priority & severity engine
├── frontend-tests/            # Node.js built-in test runner suites (`*.test.cjs`)
├── supabase/
│   ├── schema.sql             # Consolidated database schema, RLS policies & triggers
│   └── migrations/            # Additive versioned SQL migrations
├── render.yaml                # Render FastAPI service blueprint
├── .github/workflows/pages.yml# CI test gate + GitHub Pages artifact build
├── TODO.md                    # Remaining manual setup steps for the project owner
└── [ARCHITECTURE|API_DOCUMENTATION|SUPABASE_SETUP|TESTING|DEPLOYMENT].md
```

## Quick Local Setup (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Fill in `.env` with your Supabase project credentials (`SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`), allowed CORS origins (`FRONTEND_ORIGINS`), and `PASSWORD_RESET_REDIRECT_URL`. Then run the backend locally:

```powershell
uvicorn app:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

## Running Automated Tests

```powershell
# Backend, C engine, schema, and static asset integrity tests
python -m pytest

# Frontend JS tests (requires Node.js 20+)
node --test frontend-tests\auth-session.test.cjs frontend-tests\platform-ui.test.cjs
```

See [TESTING.md](./TESTING.md) for details on what each suite covers, [SUPABASE_SETUP.md](./SUPABASE_SETUP.md) for applying SQL migrations and RLS policies, [DEPLOYMENT.md](./DEPLOYMENT.md) for Render + GitHub Pages deployment, [ARCHITECTURE.md](./ARCHITECTURE.md) for system design, [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) for all endpoints, and [TODO.md](./TODO.md) for remaining manual owner actions.
