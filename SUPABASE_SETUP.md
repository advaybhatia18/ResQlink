# Supabase Setup & Migration Guide (`SUPABASE_SETUP.md`)

## 1. Fresh Supabase Project Setup

1. Create a new project in [Supabase](https://supabase.com/).
2. Open **Project Settings > API** and copy:
   - **Project URL** -> `SUPABASE_URL`
   - **Publishable / anon key** -> `SUPABASE_KEY`
   - **Secret / service_role key** -> `SUPABASE_SERVICE_ROLE_KEY` (**never place in frontend files**)
3. Open **SQL Editor > New query**, paste the full contents of [`supabase/schema.sql`](./supabase/schema.sql), and run it.

## 2. Upgrading an Existing Supabase Database

If `public.profiles` and `public.emergencies` were already created using earlier ResQlink SQL:
1. Ensure [`supabase/migrations/20261110_emergency_user_ownership.sql`](./supabase/migrations/20261110_emergency_user_ownership.sql) and [`supabase/migrations/20261110163248_emergency_submission_safety.sql`](./supabase/migrations/20261110163248_emergency_submission_safety.sql) have already been applied.
2. Run [`supabase/migrations/20261113_complete_platform_schema.sql`](./supabase/migrations/20261113_complete_platform_schema.sql) in the SQL Editor.

This migration is additive and idempotent (`if not exists` / `create or replace`), adding:
- Extended `profiles` (`phone`, `updated_at`, `deletion_requested_at`)
- Extended `emergencies` (`category`, `recommended_services`, `requested_services`, `notes`, `admin_notes`, `updated_at`, `acknowledged_at`, `resolved_at`, expanded status check `ACTIVE | ACKNOWLEDGED | DISPATCHED | RESOLVED`)
- `emergency_contacts` (with RLS owner policy + indexes)
- `contact_notification_logs` (with RLS owner policy)
- `emergency_status_history` (with RLS owner/admin read policies)
- `admin_audit_logs` (with RLS admin read policy)
- `simulator_scenarios` and `simulator_runs` (with RLS admin read policy + `check (is_simulated = true)`)

## 3. Authentication & Redirect Allowlist

Under **Authentication > URL Configuration**:
- Add your local reset page (e.g. `http://127.0.0.1:5500/password-reset.html`) and deployed GitHub Pages reset page to **Redirect URLs**.
- Under **Authentication > Providers > Email**, configure confirmation rules and SMTP settings if moving beyond Supabase's built-in email limits.

## 4. Promoting an Administrator Account

All newly signed-up accounts receive `role = 'USER'` automatically via the `handle_new_user()` trigger. To grant `ADMIN` permissions to a trusted responder account:

```sql
update public.profiles
set role = 'ADMIN'
where id = '<user-uuid-from-auth-users>';
```

Never grant `ADMIN` via client metadata (`user_metadata`) — `public.profiles.role` is the single source of truth checked by both the FastAPI backend and RLS policies.
