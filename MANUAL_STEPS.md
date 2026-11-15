# Manual Setup & Deployment Steps (`MANUAL_STEPS.md`)

Follow these steps in order to configure Supabase, Render, and GitHub Pages for your `akshhq/ResQlink` fork.

---

## a. Supabase Setup

1. **Create a Supabase project**
   - Go to [https://supabase.com/dashboard](https://supabase.com/dashboard) and click **New project**.
   - Choose a name (e.g., `resqlink`), a strong database password, and a region close to your users. Wait for provisioning to finish.

2. **Apply the unified database schema**
   - Open **SQL Editor** -> **New query** in your Supabase project.
   - **Fresh or existing database:** Copy and run the entire contents of [`supabase/schema.sql`](./supabase/schema.sql) (it is idempotent, adds `alert_id` + backfills any existing rows, and sets up all tables, RLS policies, and triggers).
   - **Full clean reset (optional):** If you want to wipe all existing ResQlink tables and start completely fresh, uncomment the `drop table if exists ... cascade;` lines at the top of [`supabase/schema.sql`](./supabase/schema.sql) before running it.

3. **Find your API credentials**
   - Open **Project Settings** -> **API** (or **API Keys**).
   - Copy:
     - **Project URL** -> `<SUPABASE_URL>`
     - **Publishable / anon key** -> `<SUPABASE_ANON_KEY>` (used as `SUPABASE_KEY`)
     - **Secret / service_role key** -> `<SUPABASE_SERVICE_ROLE_KEY>` (**keep backend-only; never put this in any frontend file**)

4. **Configure Auth URLs & Email Confirmation**
   - Open **Authentication** -> **URL Configuration**:
     - **Site URL:**
       ```text
       https://advaybhatia18.github.io/ResQlink/
       ```
     - **Redirect URLs** (add all of these):
       ```text
       https://advaybhatia18.github.io/ResQlink/password-reset.html
       https://advaybhatia18.github.io/ResQlink/login.html
       https://aksh.is-a.dev/ResQlink/password-reset.html
       https://aksh.is-a.dev/ResQlink/login.html
       http://127.0.0.1:5500/password-reset.html
       http://localhost:5500/password-reset.html
       ```
   - Open **Authentication** -> **Providers** -> **Email**:
     - Toggle **Confirm email** ON (recommended for production; users must click the confirmation email before signing in) or OFF (for faster testing without email verification).

5. **Promote your account to `ADMIN`**
   - First register your account normally through `register.html` (and confirm your email if enabled).
   - Find your user UUID in **Authentication** -> **Users**, or run in **SQL Editor**:
     ```sql
     update public.profiles
     set role = 'ADMIN'
     where id = (
         select id from auth.users where email = 'your-admin-email@example.com'
     );
     ```

---

## b. Render Backend Deployment

1. **Create the Web Service**
   - Go to [https://dashboard.render.com](https://dashboard.render.com) -> **New +** -> **Web Service** (or **Blueprint** using [`render.yaml`](./render.yaml)).
   - Connect your GitHub repository `akshhq/ResQlink` (branch `main`, Root Directory blank / `.`).
   - Confirm:
     - **Build Command:** `pip install -r backend/requirements.txt`
     - **Start Command:** `uvicorn app:app --app-dir backend --host 0.0.0.0 --port $PORT`
     - **Health Check Path:** `/healthz`

2. **Set the 5 required Environment Variables** under **Environment**:
   ```text
   SUPABASE_URL=<SUPABASE_URL>
   SUPABASE_KEY=<SUPABASE_ANON_KEY>
   SUPABASE_SERVICE_ROLE_KEY=<SUPABASE_SERVICE_ROLE_KEY>
   FRONTEND_ORIGINS=https://advaybhatia18.github.io,https://aksh.is-a.dev,http://127.0.0.1:5500,http://localhost:5500
   PASSWORD_RESET_REDIRECT_URL=https://advaybhatia18.github.io/ResQlink/password-reset.html
   ```
   > **Important:** `FRONTEND_ORIGINS` must contain scheme + host + port only (no `/ResQlink/` path and no trailing slash).

3. **Verify the deployed backend**
   - Render URL: `https://resqlink-ji0g.onrender.com`
   - Open `https://resqlink-ji0g.onrender.com/` and `https://resqlink-ji0g.onrender.com/classification/config` in a browser and confirm both return JSON with HTTP 200.

---

## c. GitHub Pages & Actions Setup

1. **Enable Actions on your fork**
   - Open `https://github.com/akshhq/ResQlink/actions` and enable workflows if prompted.

2. **Set GitHub Pages source**
   - Go to **Settings** -> **Pages**.
   - Under **Build and deployment** -> **Source**, select **GitHub Actions**.

3. **Optional: Override `RESQLINK_API_URL` repository variable**
   - `.github/workflows/pages.yml` and `api-config.js` already default to `https://resqlink-ji0g.onrender.com`.
   - If you ever change the Render URL, go to **Settings** -> **Secrets and variables** -> **Actions** -> **Variables** tab and set:
     - **Name:** `RESQLINK_API_URL`
     - **Value:** `https://resqlink-ji0g.onrender.com` (no trailing slash)

4. **Run the workflow**
   - Go to **Actions** -> **Test and deploy GitHub Pages** -> **Run workflow** (or push to `main`).
   - Wait for both `test` and `deploy` jobs to turn green. Your main site will be live at `https://advaybhatia18.github.io/ResQlink/` (and dev at `https://aksh.is-a.dev/ResQlink/`).

---

## d. Final End-to-End Verification Checklist

- [ ] Open `https://advaybhatia18.github.io/ResQlink/register.html` (or dev `https://aksh.is-a.dev/ResQlink/register.html`) and create a test member account.
- [ ] Confirm email (if email confirmation is enabled in Supabase).
- [ ] Sign in on `login.html` and verify redirect to `user-dashboard.html` with your name and `USER` role.
- [ ] Open `sos.html`, verify the safety notice is visible, and press the **SOS** button (allow GPS or choose **Submit without location**).
- [ ] Confirm the alert succeeds and displays a unique **Alert ID** (`RQ-YYYYMMDD-XXXXXX`), status `ACTIVE`, timestamp, and the safety notice.
- [ ] Open `history.html` and verify the same `RQ-YYYYMMDD-XXXXXX` Alert ID appears in your history and timeline modal.
- [ ] In **Supabase Dashboard -> Table Editor -> `emergencies`**, verify the row exists with `alert_id = 'RQ-...'`, `user_id`, and `idempotency_key`.
- [ ] Open `admin-login.html`, sign in with your promoted `ADMIN` account, and confirm `dashboard.html` loads the alert in the queue and can search by `RQ-...`.
