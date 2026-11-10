# ResQlink deployment and security readiness review

**Review date:** 2026-11-10  
**Scope:** Repository configuration and code. External Render, GitHub, Supabase,
DNS, backup, and operational settings were not independently inspected.

## Summary

ResQlink is an emergency-reporting prototype with backend-authenticated
accounts, role-protected alert operations, Supabase persistence, and a native C
severity/priority engine. It is **not validated or approved for real emergency
dispatch or safety-critical operations**. The production API address, hosting
secrets, live CORS configuration, database policies, backups, and service
reliability still require deployment-owner verification.

The GitHub Pages workflow now fails closed unless the repository Actions
variable `RESQLINK_API_URL` contains an HTTPS public API URL. This repository
does not establish that the variable has been set or that the selected host
resolves to the intended Render service.

## Features that work (repository implementation)

- The frontend's checked-in `api-config.js` is for local development. Pages
  deployment generates its API configuration from `RESQLINK_API_URL` rather
  than publishing the local file.
- CORS uses an explicit origin allowlist, limited HTTP methods and headers,
  and does not enable credentialed cross-origin cookies. Render's checked-in
  origin is the default GitHub Pages origin; custom domains need a matching
  production setting.
- Supabase URL, publishable key, service-role key, and password recovery
  redirect are supplied to the backend as environment variables. `.env` is
  excluded from Git, and no production secret-shaped values were found in
  tracked static frontend files during this review.
- Render compiles the C source and smoke-tests the Python engine integration
  in its build command. `/healthz` provides a lightweight process health check.
- API responses include a request ID and defensive response headers. Request
  logs are structured JSON and omit headers, bodies, query strings, IP
  addresses, and response contents. A request-body cap and per-peer request
  limits are implemented.
- Supabase schema setup enables RLS, restricts profile/emergency reads to
  owners or admins, revokes direct anonymous/authenticated write access, and
  grants backend writes to `service_role`.

## Features tested

- `python -m pytest`: **98 passed** after the readiness changes. Coverage
  includes request limits, response headers, explicit CORS behavior, and
  privacy-safe request logs.
- Tests use mocked Supabase/auth operations and synthetic coordinates. They do
  not require production credentials, real accounts, or actual GPS readings.
- Frontend session/API error handling was exercised in a browser for expired
  sessions, forbidden responses, and network failures. YAML parsing and the
  Pages/Render configuration checks passed. The Node test runner was not
  installed in the local review environment; GitHub Actions runs those tests.
- No remote deployment, real Supabase project, Render health probe, backup
  restoration, penetration test, or dispatch integration was exercised.

## Features requiring external configuration or verification

1. **GitHub Pages:** Set the Actions repository variable `RESQLINK_API_URL`
   to the actual Render API base URL. Confirm the deployment uses the expected
   HTTPS hostname and that it responds to the browser. The Pages job fails if
   the variable is missing or points to a loopback/private address.
2. **Render:** Configure `SUPABASE_URL`, `SUPABASE_KEY`,
   `SUPABASE_SERVICE_ROLE_KEY`, and `PASSWORD_RESET_REDIRECT_URL` as private
   service environment variables. Set `FRONTEND_ORIGINS` to the exact Pages
   origin and exclude development origins. Verify the configured CORS origin
   matches the actual deployment domain.
3. **Supabase:** Apply and verify `supabase/schema.sql` and all required
   migrations. Confirm RLS policies and grants in the deployed project, keep
   the service-role key backend-only, and restrict administrator promotion to
   authorized operators.
4. **Authentication and email:** Configure allowed redirect URLs, email
   delivery, account-confirmation policy, password recovery, administrator
   provisioning, and credential-rotation procedures.
5. **Proxy and rate limiting:** Current limits are process-local and keyed by
   the ASGI peer address: 120 requests/minute generally, 10 requests/minute
   for each sensitive authentication route, plus a 1 MiB body limit. Verify
   that the host provides a trustworthy per-client address. Limits reset on
   restart and do not coordinate across instances; use a trusted proxy-aware
   distributed limiter and upstream WAF/DoS controls before exposing the API
   broadly.
6. **Health and availability:** `/healthz` indicates that the API process is
   responsive; it does not prove that Supabase, email, or the C library is
   operational. Configure and test dependency monitoring, alerts, capacity,
   incident response, and recovery objectives.
7. **Backups and data retention:** This repository configures no automatic
   location-retention period or backup schedule. Verify Supabase backup and
   point-in-time recovery coverage for the selected plan, set an approved
   retention/deletion policy for precise coordinates, protect backups, define
   restore authority, and test restoration in a separate environment.
   Deleting a profile cascades to its alert records; validate legal and
   operational retention requirements before deletion.

## Features that remain demo-only

- Alert submission records a report in ResQlink; it does not notify public
  emergency services, dispatch responders, or guarantee that anyone receives
  or acts on an alert.
- The dashboard is an administrative view of API records, not a staffed
  command centre or a monitored live dispatch console.
- No service-level objective, safety case, 24/7 monitoring, disaster-recovery
  exercise, location accuracy guarantee, or emergency-response workflow has
  been established by this repository.

## Readiness decision

**Not production-ready for real emergency dispatch.** Use only as a prototype
until the external configuration above is verified and the system has passed
appropriate operational, legal, privacy, security, reliability, and
emergency-response validation by responsible professionals.
