# ResQlink API Documentation (`API_DOCUMENTATION.md`)

Base URL (production Render deployment): `https://resqlink-ji0g.onrender.com`
Authentication header for protected routes: `Authorization: Bearer <supabase_access_token>`

## Health & Classification (Public)

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/` | Public | Service health & message check |
| `GET` | `/classification/config` | Public | Returns categories, severity levels, service catalog, and triage/dispatch disclaimers |
| `POST` | `/classification/recommend` | Public | Accepts `{category, severity, requested_services?}`; returns C-engine priority, label, safety guidance, and `service_cards` |

## Authentication & Profile

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/register` | Public | Create user account (`{name, email, password}`) |
| `POST` | `/login` | Public | Authenticate via Supabase Auth (`{email, password}`); returns `access_token` |
| `GET` | `/me` | User | Returns verified user profile (`id`, `email`, `name`, `phone`, `role`, `deletion_requested_at`) |
| `PATCH` | `/me` | User | Update signed-in user's `name` and/or `phone` |
| `POST` | `/me/deletion-request` | User | Returns `202 Accepted`; timestamps a manual account deletion request on `public.profiles` |
| `POST` | `/password-recovery` | Public | Request Supabase password recovery email (`{email}`) |
| `POST` | `/password-update` | User | Update password with active/recovery Bearer token (`{password}`) |
| `POST` | `/logout` | User | Revoke current Supabase session |

## Emergency Alerts

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/emergency` | User | Submit SOS alert. Header `Idempotency-Key` recommended. Body: `{severity (1..5), category?, requested_services?, latitude?, longitude?, location_accuracy_m?, location_accuracy_confirmed?, notes?}`. Returns `201` (new) or `200` (idempotent duplicate) |
| `GET` | `/emergencies/me` | User | List signed-in user's own alerts; supports `status`, `category`, `limit`, `offset` |
| `GET` | `/emergencies/{alert_id}` | Owner or Admin | Detailed emergency record including `status_history` timeline and `admin_notes` |
| `GET` | `/emergencies` | **Admin** | List/filter all alerts (`severity`, `status`, `category`, `service`, `date_from`, `date_to`, `search`, `limit`, `offset`) |
| `PATCH` | `/emergencies/{alert_id}/status` | **Admin** | Update alert lifecycle (`ACTIVE`, `ACKNOWLEDGED`, `DISPATCHED`, `RESOLVED`) and `admin_notes`; writes `emergency_status_history` & `admin_audit_logs` |
| `PATCH` | `/emergency/{alert_id}/resolve` | **Admin** | Backward-compatible shortcut to mark an alert `RESOLVED` |

## Admin Analytics & Audit

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/admin/overview` | **Admin** | Aggregate counts (`total_alerts`, `active_emergencies`, `acknowledged_emergencies`, `dispatched_emergencies`, `resolved_emergencies`, `critical_emergencies`, `by_severity`, `by_category`, `by_service`, `recent_activity`) |
| `GET` | `/admin/audit-logs` | **Admin** | Recent administrator audit trail rows (`limit` up to 250) |

## Emergency Contacts & Notification Logs

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/contacts` | User | List current user's trusted emergency contacts (max 10) |
| `POST` | `/contacts` | User | Add contact (`{name, phone, relationship, is_primary?}`); rejects duplicate phone (`409`) or >10 contacts (`400`) |
| `PATCH` | `/contacts/{contact_id}` | User | Update own contact; swaps `is_primary` cleanly |
| `DELETE` | `/contacts/{contact_id}` | User | Delete own contact (`404` if not found) |
| `POST` | `/contacts/{contact_id}/notify` | User | Requires `consent_confirmed: true` and `channel` (`MANUAL_TEL`, `MANUAL_COPY`, `SMS`, `WHATSAPP`, `EMAIL`). Records audit log and returns honest `sent: false` + `manual_fallback` (`tel_uri`, `copy_text`) when no external provider is configured |
| `GET` | `/contacts/notifications` | User | List current user's recent notification attempt logs |

## Isolated Simulator (`ADMIN` Only)

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/simulator/scenarios` | **Admin** | List the 14 prebuilt scenarios |
| `GET` | `/simulator/runs` | **Admin** | List recent isolated runs (`limit` up to 200) |
| `POST` | `/simulator/run` | **Admin** | Execute prebuilt (`scenario_id`) or `"custom"` simulation; persists solely to `simulator_runs` with `is_simulated: true` |
| `PATCH` | `/simulator/runs/{run_id}/status` | **Admin** | Query param `status` in `SIMULATED_ACKNOWLEDGED`, `SIMULATED_DISPATCHED`, `SIMULATED_RESOLVED` |
| `DELETE` | `/simulator/runs` | **Admin** | Clear all simulated telemetry without affecting production `emergencies` |
