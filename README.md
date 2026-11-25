# ResQlink

ResQlink is an emergency-assistance platform, triage classification aid, personal safety contact hub, and isolated responder simulator. Its FastAPI backend uses Supabase Auth for authentication and Supabase Postgres (with Row Level Security) for storage, while the native C engine in `core/` calculates deterministic emergency priorities and severity labels. The frontend consists of 12 mobile-first static HTML/CSS/JS pages deployed to GitHub Pages.

> **Important Safety Notice:** Submitting or storing an alert in ResQlink does **not** automatically notify or dispatch public police, fire, or medical services unless an authorized external integration is explicitly configured. For real emergencies, contact your local emergency number (e.g., 112 / 911 / 999) directly. Priority and service recommendations are operational routing aids only, not medically validated triage.

## Live Deployments

- **Main Website (Production):** `https://advaybhatia18.github.io/ResQlink/`
- **Development Mirror:** `https://aksh.is-a.dev/ResQlink/`
- **Backend API (Render):** `https://resqlink-ji0g.onrender.com` (health check: `/healthz`, API docs: `/docs`)

[`api-config.js`](./api-config.js) automatically points to `http://127.0.0.1:8000` when running on `localhost` / `127.0.0.1` and `https://resqlink-ji0g.onrender.com` on deployed origins (and `.github/workflows/pages.yml` also supports overriding via the `RESQLINK_API_URL` Actions variable).

## Key Features

- **Idempotent SOS Reporting & Location-Only Guest Mode:** 7 emergency categories, 5 severity levels, C-engine priority scoring (`20–100`), service recommendations (`POLICE`, `FIRE_RESCUE`, `AMBULANCE_MEDICAL`), browser GPS capture with `>100 m` accuracy guard, Leaflet map preview, `Idempotency-Key` retry protection, and unauthenticated **location-only SOS** (`POST /emergency/anonymous`) when not signed in.
- **Timed SOS Sessions & Unique Alert IDs:** Every authenticated SOS starts a live timed session (`session_started_at`, `session_ended_at`, `session_duration_seconds`) that can be ended directly on [`sos.html`](./sos.html), with a human-readable `RQ-YYYYMMDD-XXXXXX` ID and append-only `emergency_status_history` timeline.
- **Role-Prioritized Spaces & Admin User Info:** [`ui-shell.js`](./ui-shell.js) and page layouts prioritize tools by role (`ADMIN`, `USER`, `GUEST`). On [`dashboard.html`](./dashboard.html), admins get horizontal analytics bar charts, CSV export, and a **User Info** button (`GET /emergencies/{id}/reporter`) for signed-in alerts.
- **Live Admin & History Sync + Offline Shell:**
  - [`dashboard.html`](./dashboard.html) polls every 5s when active, retries automatically after transient cold-start timeouts, and syncs immediately on tab focus, `visibilitychange`, `BroadcastChannel`, and `storage` events.
  - [`history.html`](./history.html) polls every 10s when visible, syncs cross-tab on new SOS submissions or admin updates, and displays the full status transition timeline.
  - [`sw.js`](./sw.js) and [`manifest.webmanifest`](./manifest.webmanifest) cache the static shell for weak-signal resilience while preserving pending SOS retry keys.
- **Emergency Contacts & Audit Trails:** Up to 10 personal emergency contacts per account with primary designation, `tel:` / clipboard fallback, and consent-logged notification history.
- **Strictly Isolated Simulator:** [`simulator.html`](./simulator.html) runs 14 prebuilt and custom emergency scenarios persisted only to `public.simulator_runs`, never mixing with real alerts or notifications.
- **Security & Access Control:** Supabase JWT verification, server-enforced `ADMIN` RBAC, Row Level Security (`supabase/schema.sql`), rate limiting, CORS origin allowlisting, and XSS-safe DOM rendering (`textContent`, never `innerHTML`).

## Pages & Portals

1. [`index.html`](./index.html) — Landing page, safety disclaimer, platform overview, and dynamic member/admin entry links
2. [`register.html`](./register.html) — New member account registration
3. [`login.html`](./login.html) — Member sign-in portal
4. [`password-reset.html`](./password-reset.html) — Dual-mode password recovery email request and token-based reset
5. [`user-dashboard.html`](./user-dashboard.html) — Authenticated member hub (profile summary, emergency contacts snapshot, quick SOS, recent alerts)
6. [`sos.html`](./sos.html) — Primary SOS console (category + severity 1–5 selection, live service recommendations, GPS capture with >100m accuracy guard, Leaflet location preview, idempotency retry, and emergency contacts check-in fallback)
7. [`history.html`](./history.html) — Personal emergency history with status/category filtering, live sync, and status transition timeline modal
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
├── emergency.css              # SOS console stylesheet & multi-state trigger styles
├── manifest.webmanifest, sw.js# PWA manifest and offline shell Service Worker
├── DESIGN.md                  # Design tokens and accessibility conventions
├── api-config.js              # Environment-aware API base URL configuration
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
│   ├── emergency.c            # Native C priority & severity engine
│   ├── emergency.h            # C engine header
│   └── emergency64.dll        # Prebuilt Windows x64 shared library
├── frontend-tests/            # Node.js built-in test runner suites (`*.test.cjs`)
├── supabase/
│   └── schema.sql             # Unified Postgres schema, RLS policies, indexes & Auth trigger
├── render.yaml                # Render FastAPI service blueprint
├── requirements-dev.txt       # Local development & test dependencies
├── .github/workflows/pages.yml# CI test gate + GitHub Pages artifact build
├── MANUAL_STEPS.md            # Step-by-step Supabase, Render, and GitHub Pages setup
└── [ARCHITECTURE|API_DOCUMENTATION|SUPABASE_SETUP|TESTING|DEPLOYMENT|TODO].md
```

## Quick Local Setup (Windows PowerShell)

1. **Create a virtual environment & install dependencies**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

2. **Configure `.env`**

Fill in `.env` with your Supabase credentials (`SUPABASE_URL`, `SUPABASE_KEY` or `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY`), allowed CORS origins (`FRONTEND_ORIGINS`), and `PASSWORD_RESET_REDIRECT_URL`.

3. **Initialize Supabase**

Run [`supabase/schema.sql`](./supabase/schema.sql) in the Supabase SQL Editor (safe on fresh databases and idempotent on existing ones; includes a commented-out full reset block at the top). See [`SUPABASE_SETUP.md`](./SUPABASE_SETUP.md) and [`MANUAL_STEPS.md`](./MANUAL_STEPS.md) for details.

4. **Start the backend & local frontend**

```powershell
# Terminal 1: FastAPI backend (http://127.0.0.1:8000)
uvicorn app:app --app-dir backend --reload --host 127.0.0.1 --port 8000

# Terminal 2: Static frontend server (http://127.0.0.1:5500)
python -m http.server 5500
```

## Running Automated Tests

```powershell
# Backend, C engine, schema, and static asset integrity tests (130 tests)
python -m pytest

# Frontend JS tests (7 tests, requires Node.js 20+)
node --test frontend-tests\auth-session.test.cjs frontend-tests\platform-ui.test.cjs
```

## Documentation

- [`DESIGN.md`](./DESIGN.md) — Design tokens, role workspace accents, and accessibility conventions
- [`MANUAL_STEPS.md`](./MANUAL_STEPS.md) — Step-by-step setup checklist for Supabase, Render, and GitHub Pages
- [`SUPABASE_SETUP.md`](./SUPABASE_SETUP.md) — Database schema, RLS policies, Auth URL allowlist, and admin promotion
- [`DEPLOYMENT.md`](./DEPLOYMENT.md) — Render backend and GitHub Pages deployment guide
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — System architecture and security model
- [`API_DOCUMENTATION.md`](./API_DOCUMENTATION.md) — REST endpoints, request/response schemas, and auth headers
- [`TESTING.md`](./TESTING.md) — Backend and frontend test suite coverage
- [`TODO.md`](./TODO.md) — Owner setup checklist
