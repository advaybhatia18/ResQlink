# ResQlink Architecture (`ARCHITECTURE.md`)

## High-Level System Overview

```text
+-----------------------------------+        HTTPS (REST + Bearer JWT)        +------------------------------------+
|  Static Frontend (GitHub Pages)   | --------------------------------------> |   FastAPI Backend (Render)         |
|  12 HTML Pages + Vanilla CSS/JS   |                                         |   app.py + RequestControls         |
|  - theme.css / ui-shell.js        | <-------------------------------------- |   - auth.py (JWT + Role check)     |
|  - Leaflet Maps + MarkerCluster   |          JSON + Status Codes            |   - classification.py              |
|  - Tab-scoped sessionStorage      |                                         |   - contacts.py / simulator.py     |
+-----------------------------------+                                         +------------------------------------+
                                                                                      |                    |
                                                                      ctypes FFI      |                    | Service Role / Auth API
                                                                      (C + fallback)  v                    v
                                                                              +---------------+    +---------------------------+
                                                                              | core/         |    | Supabase                  |
                                                                              | emergency.c   |    | - Auth (users, recovery)  |
                                                                              | priority &    |    | - Postgres + RLS          |
                                                                              | severity_label|    |   (emergencies, contacts, |
                                                                              +---------------+    |    audit_logs, simulator)  |
                                                                                                   +---------------------------+
```

## Components & Boundaries

### 1. Native C Priority Engine (`core/emergency.c`, `backend/emergency_engine.py`)
- Exposes `calculate_priority(severity)` (`severity * 20` for 1–5) and `severity_label(severity)` (`LOW` .. `CRITICAL`).
- `backend/emergency_engine.py` loads `core/emergency64.dll` (Windows) or compiles `core/emergency.c` -> `core/libemergency.so` on Linux/Render when missing, with a deterministic Python fallback matching exact bounds (`1..5`) if a compiler/runtime library cannot be loaded.

### 2. Classification & Service Recommendation (`backend/classification.py`)
- Wraps `process_emergency` without modifying its C formula.
- Maps 7 emergency categories (`MEDICAL`, `ROAD_ACCIDENT`, `FIRE`, `THEFT`, `PERSONAL_SAFETY`, `NATURAL_DISASTER`, `OTHER`) and 5 severities to 3 selectable services (`POLICE`, `FIRE_RESCUE`, `AMBULANCE_MEDICAL`), safety guidance, and explicit non-medical triage disclaimers.

### 3. Authentication & RBAC (`backend/auth.py`, `auth-session.js`)
- Supabase Auth manages passwords, tokens, email recovery, and session revocation.
- Only the access token is stored in tab-scoped `sessionStorage`. Protected frontend pages call `GET /me` on load; the backend validates every Bearer JWT with Supabase Auth and reads `public.profiles.role` (`USER` vs `ADMIN`) for every authorization check.

### 4. Storage & Audit Trail (`backend/storage.py`, `supabase/`)
- All database mutations route through the FastAPI backend using `SUPABASE_SERVICE_ROLE_KEY`.
- Postgres enforces strict RLS for direct `authenticated` queries: users read only their own `profiles`, `emergencies`, `emergency_contacts`, `contact_notification_logs`, and `emergency_status_history`; only `ADMIN` reads global queues, `admin_audit_logs`, and `simulator_runs`.
- Updating alert status (`ACTIVE -> ACKNOWLEDGED -> DISPATCHED -> RESOLVED`) records a row in `emergency_status_history` and an audit entry in `admin_audit_logs`.

### 5. Isolated Simulator (`backend/simulator.py`, `simulator.html`)
- Requires `ADMIN` authorization on all `/simulator/*` endpoints.
- Uses synthetic coordinates, simulates fault modes (`OFFLINE_NETWORK`, `DATABASE_FAILURE`, `DUPLICATE_REQUEST`, `UNAUTHORIZED_*`), and persists strictly into `public.simulator_runs` (`is_simulated = true` CHECK constraint, `SIM-XXXXXXXX` IDs). It never touches `public.emergencies` or `contact_notification_logs`.

### 6. Honest Contacts & Notifications (`backend/contacts.py`, `contacts.html`)
- Up to 10 contacts per user, normalized E.164/digit phone validation, duplicate prevention, and single primary contact management.
- Because no SMS/WhatsApp provider is bundled, `POST /contacts/{id}/notify` records explicit consent in `contact_notification_logs` and honestly returns `sent: false` with `PROVIDER_NOT_CONFIGURED` or `MANUAL_FALLBACK` plus `tel:` and copy-text fallbacks.
