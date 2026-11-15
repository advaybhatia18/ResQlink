# ResQlink Manual Action Checklist (`TODO.md`)

All application source code, database migrations, automated tests, and CI workflows are complete in the repository. Only the tasks below genuinely require manual action in external dashboards or on real user devices because they depend on private credentials, live infrastructure, external third-party accounts, or human authorization decisions.

---

### [DONE] 1. Apply the Supabase Platform Schema Migration (`20261113_complete_platform_schema.sql`)
- **Status:** **Completed** by project owner (database tables, columns, indexes, and RLS policies applied in Supabase).

---

### 2. Configure Render Backend Environment Variables & Blueprint Sync
1. **Why it requires manual action:** Private Supabase keys (`SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_KEY`), CORS origins, and Render service configuration live in your private Render account and cannot be read or modified from local code.
2. **Exact dashboard or file location:** **Render Dashboard > Your ResQlink Service > Settings & Environment** (and [`render.yaml`](./render.yaml)).
3. **Exact steps:**
   - Open Render Dashboard for your service (`<MY_RENDER_URL>`).
   - Under **Settings**, match **Build Command** and **Start Command** to your **Root Directory**:
     - If **Root Directory** is `backend` (recommended for manual Render services):
       - **Build Command:** `pip install -r requirements.txt`
       - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
     - If **Root Directory** is blank / repository root (`.`, matching `render.yaml`):
       - **Build Command:** `pip install -r backend/requirements.txt`
       - **Start Command:** `uvicorn app:app --app-dir backend --host 0.0.0.0 --port $PORT`
   - Under **Environment**, ensure all required variables are set:
     - `SUPABASE_URL` (`<SUPABASE_URL>`)
     - `SUPABASE_KEY` (publishable/anon key)
     - `SUPABASE_SERVICE_ROLE_KEY` (secret/service-role key — backend only)
     - `FRONTEND_ORIGINS` (`https://advaybhatia18.github.io,https://aksh.is-a.dev,http://127.0.0.1:5500,http://localhost:5500`)
     - `PASSWORD_RESET_REDIRECT_URL` (`https://advaybhatia18.github.io/ResQlink/password-reset.html`)
   - Trigger a manual deploy after saving environment changes.
4. **Expected result:** Render builds cleanly, compiles or loads the emergency priority engine, boots Uvicorn on `$PORT`, and responds `200 OK` on `GET /`.
5. **Verification method:** Visit `<MY_RENDER_URL>/` and `<MY_RENDER_URL>/classification/config` in a browser or curl and verify JSON responses with no 500 errors or CORS failures from GitHub Pages.
6. **Blocks deployment:** **Yes** — all authenticated routes fail with 503/CORS errors without valid Supabase environment variables and `FRONTEND_ORIGINS`.

---

### 3. Set the GitHub Actions Repository Variable `RESQLINK_API_URL`
1. **Why it requires manual action:** GitHub repository Settings -> Variables require repository owner permissions on GitHub.
2. **Exact dashboard or file location:** **GitHub Repository > Settings > Secrets and variables > Actions > Variables**, used by [`.github/workflows/pages.yml`](./.github/workflows/pages.yml).
3. **Exact steps:**
   - Open your GitHub repository settings -> **Secrets and variables > Actions**.
   - Select the **Variables** tab and create/update variable `RESQLINK_API_URL` to `<MY_RENDER_URL>`.
   - Ensure GitHub Pages source is set to **GitHub Actions** under **Settings > Pages**.
4. **Expected result:** On push to `main`, `.github/workflows/pages.yml` passes the test gate and publishes `_site/api-config.js` pointing to `<MY_RENDER_URL>`.
5. **Verification method:** Inspect the deployed `api-config.js` on GitHub Pages or inspect network calls on `index.html` / `sos.html` DevTools Network tab.
6. **Blocks deployment:** **Yes** (for GitHub Pages CI deployment, because line 91 of `pages.yml` checks that `RESQLINK_API_URL` is non-empty).

---

### 4. Configure Supabase Auth URL Allowlist & Email / SMTP Delivery
1. **Why it requires manual action:** Auth domain allowlists and email sender credentials live inside your Supabase project security settings and third-party SMTP provider account.
2. **Exact dashboard or file location:** **Supabase Dashboard > Authentication > URL Configuration** and **Authentication > Notifications / SMTP Settings**.
3. **Exact steps:**
   - Set **Site URL** to your deployed GitHub Pages root URL.
   - Under **Redirect URLs**, add both local and production password reset URLs (for example `http://127.0.0.1:5500/password-reset.html` and `https://<your-github-pages-origin>/<repo>/password-reset.html`).
   - Configure custom SMTP under **Project Settings > Authentication > SMTP Settings** for reliable production signup confirmation and password-recovery delivery beyond Supabase's built-in rate limits.
4. **Expected result:** Password recovery links redirect users back to `password-reset.html#access_token=...&type=recovery` without rejected-redirect errors.
5. **Verification method:** Submit a test email on `password-reset.html`, click the emailed recovery link, and confirm password update succeeds.
6. **Blocks deployment:** **Partial** — core login/SOS works, but self-service password reset and reliable email confirmation require this setup.

---

### 5. Promote Initial Administrator Account (`ADMIN` Role)
1. **Why it requires manual action:** Privilege elevation cannot be performed automatically via public endpoints or unauthenticated migrations for security reasons.
2. **Exact dashboard or file location:** **Supabase Dashboard > SQL Editor** updating `public.profiles`.
3. **Exact steps:**
   - Register the intended responder/admin user normally through `register.html`.
   - Confirm their email if email confirmation is enabled.
   - In Supabase SQL Editor, run:
     ```sql
     update public.profiles
     set role = 'ADMIN'
     where id = '<target-user-uuid>';
     ```
4. **Expected result:** Signing in via `admin-login.html` with that account unlocks `dashboard.html` and `simulator.html`, while normal accounts stay restricted to `USER`.
5. **Verification method:** Sign in on `admin-login.html`; confirm `/me` returns `"role": "ADMIN"` and `dashboard.html` loads alerts without a 403 error.
6. **Blocks deployment:** **No** for standard user sign-in/SOS, **Yes** before responders can access the Command Center (`dashboard.html`) or Isolated Simulator (`simulator.html`).

---

### 6. Review Unowned Historical Emergency Alerts & Retention / Deletion Requests
1. **Why it requires manual action:** Determining ownership of legacy rows (`user_id is null`) or fulfilling GDPR/privacy account deletion requests (`deletion_requested_at`) requires human administrative review and organizational policy decisions.
2. **Exact dashboard or file location:** **Supabase Dashboard > SQL Editor** (`public.emergencies` and `public.profiles`) and **Supabase Authentication > Users**.
3. **Exact steps:**
   - Check unowned legacy alerts: `select id, created_at, severity, label from public.emergencies where user_id is null order by created_at;`
   - Periodically check accounts with `deletion_requested_at is not null` in `public.profiles`, export any legally required audit records, and remove the Auth user from **Authentication > Users** (which cascades profile/contact cleanup according to FK rules).
4. **Expected result:** Legacy unowned records stay hidden from regular users and deletion requests are fulfilled cleanly.
5. **Verification method:** Query `public.profiles where deletion_requested_at is not null` after processing; count should return 0 pending requests.
6. **Blocks deployment:** **No** — operational maintenance task.

---

### 7. Optional: Integrate an Authorized External SMS / WhatsApp Notification Adapter
1. **Why it requires manual action:** External messaging providers (such as Twilio or Meta WhatsApp Business API) require paid vendor accounts, sender verification, DLT/regulatory compliance, and API secrets.
2. **Exact dashboard or file location:** Vendor console + **Render Environment** + [`backend/contacts.py`](./backend/contacts.py).
3. **Exact steps:**
   - Until a provider is authorized and wired in, `POST /contacts/{id}/notify` honestly logs consent and returns `status: "PROVIDER_NOT_CONFIGURED"` with `tel:` and copy manual fallbacks.
   - If you obtain an authorized SMS/WhatsApp account later, add its credentials to Render Environment and implement the signed HTTP adapter inside `backend/contacts.py` (`record_notification_attempt`).
4. **Expected result:** Contacts receive automated SMS/WhatsApp alerts only after explicit vendor integration and user consent.
5. **Verification method:** Trigger a test notification in `contacts.html` for a test phone number and verify delivery receipt + audit row in `contact_notification_logs`.
6. **Blocks deployment:** **No** — manual `tel:` dialer and one-click clipboard copy work out of the box.

---

### 8. Real-Device Mobile GPS, Browser Permission & Node.js CI Check
1. **Why it requires manual action:** Real mobile GPS sensors, HTTPS permission prompts on iOS/Android, and GitHub Actions Ubuntu CI runners cannot be exercised on a local headless desktop shell (additionally, Node.js is not installed on the current local Windows shell).
2. **Exact dashboard or file location:** **GitHub Actions** tab (`.github/workflows/pages.yml`) and physical iOS/Android mobile browsers against the HTTPS GitHub Pages URL.
3. **Exact steps:**
   - Push to GitHub and inspect the `test` and `deploy` jobs in **Actions**.
   - On a mobile phone over HTTPS, test `sos.html` with (a) accurate GPS, (b) denied GPS fallback, and (c) dark-mode responsive layout across all 12 pages.
4. **Expected result:** CI runs `pytest` and `node --test frontend-tests/*.test.cjs` cleanly, and mobile GPS + Leaflet preview render without layout overflow.
5. **Verification method:** Green GitHub Actions checkmarks and visual inspection on mobile Chrome/Safari.
6. **Blocks deployment:** **No** (recommended pre-release verification).
