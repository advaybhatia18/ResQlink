# ResQlink

ResQlink is an emergency alert and location-sharing app. Its FastAPI backend
uses Supabase Auth for accounts and Supabase Postgres for emergency alerts and
user profiles. The native C engine in `core` calculates alert labels and
priorities. The frontend is made of static HTML pages.

## Features

- Submit an emergency alert with severity and browser-provided GPS coordinates.
- View alerts on the command-centre dashboard and resolve them with an admin
  token.
- Register and sign in to a user account.
- Store alerts and user profiles in Supabase Postgres.
- Authenticate accounts and API access tokens with Supabase Auth.

## Project layout

```text
.
├── index.html, login.html, register.html, dashboard.html
├── api-config.js            # Frontend API URL; safe to publish
├── backend/                 # FastAPI API and Supabase access
├── core/                    # C engine source and local Windows DLL
├── supabase/schema.sql      # Supabase tables and signup trigger
├── .github/workflows/       # GitHub Pages deployment
├── render.yaml              # Render API deployment
├── requirements.txt
└── .env.example
```

GitHub Pages hosts only the static HTML and JavaScript. The FastAPI backend
must run separately; this repository includes a Render deployment blueprint.

## Setup on Windows

Run these commands from the project root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Create a Supabase project, then open **Project Settings > API** and copy the
project URL and publishable key (`sb_publishable_...`) into `SUPABASE_URL` and
`SUPABASE_KEY`. Also set `SUPABASE_SERVICE_ROLE_KEY` to the project's private
secret/service-role key. The private key bypasses Row Level Security, so keep
it on the backend only; never place it in frontend files or commit `.env`.

In the Supabase SQL Editor, run [`supabase/schema.sql`](./supabase/schema.sql)
to create the profiles and emergencies tables and the profile-on-signup
trigger. This also enables Row Level Security and grants table access only to
the backend and authenticated users according to ownership policies. For an
existing project, first run
[`supabase/migrations/20261110_emergency_user_ownership.sql`](./supabase/migrations/20261110_emergency_user_ownership.sql).
It only copies a previously recorded `created_by` profile when that profile
still exists; other historical rows stay unowned and are never assigned
speculatively.

Review unowned historical alerts with:

```sql
select id, created_at, severity, label
from public.emergencies
where user_id is null
order by created_at;
```

These rows remain available to administrators only. Resolve ownership only
when verified from trusted records; otherwise retain or delete them according
to your organization's retention policy. No automatic time-based location
retention is configured. Deleting a profile cascades deletion of its owned
emergency records, including their precise coordinates.

The backend loads `.env` automatically from the project root. Supabase Auth
email confirmation can be configured under
**Authentication > Providers > Email** in the Supabase dashboard; when enabled,
users must confirm their email before signing in.

To grant responder access, first register the account normally, then promote
its profile using the Supabase SQL Editor and that account's Auth user UUID:

```sql
update public.profiles
set role = 'ADMIN'
where id = 'AUTH_USER_UUID';
```

Only the database profile role grants administrator access. Never accept role
changes from registration or browser-supplied request data.

## Run the app

Start the API from the `backend` directory:

```powershell
Set-Location .\backend
python -m uvicorn app:app --reload
```

The API is available at <http://127.0.0.1:8000> and its interactive API
documentation is at <http://127.0.0.1:8000/docs>.

In a second terminal, serve the repository root with VS Code Live Server and
open `index.html`. The other pages are `login.html`, `register.html`, and
`dashboard.html`. GPS access requires browser permission.

## Deploy

### GitHub Pages frontend

1. Push the repository to GitHub's `main` branch.
2. In the repository, open **Settings > Pages** and set the source to
   **GitHub Actions**.
3. Set `window.RESQLINK_API_URL` in `api-config.js` to the deployed backend
   base URL (for example, `https://resqlink-api.onrender.com`) and push the
   change. Do not add a trailing slash.
4. The workflow at `.github/workflows/pages.yml` deploys the root-level static
   pages. The site URL is shown under **Settings > Pages**.

### FastAPI backend on Render

1. Create a new Render Blueprint and select this repository. Render reads
   `render.yaml`; the blueprint compiles the C emergency engine for Linux.
2. Set `SUPABASE_URL`, `SUPABASE_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` in the
   Render dashboard when prompted. Keep the service-role key private, and
   remove any old `RESQLINK_ADMIN_TOKEN` setting; it is no longer used.
3. Set `FRONTEND_ORIGINS` to the exact origin of your Pages site, for example
   `https://advaybhatia18.github.io`. Origins have no path or trailing slash.
   The provided Render value includes the default repository's Pages origin
   plus localhost origins for development.
4. Copy the Render service URL into `api-config.js`, then push to `main`.

The configured Supabase project must have the tables and signup trigger from
[`supabase/schema.sql`](./supabase/schema.sql). For a custom Pages domain,
update `FRONTEND_ORIGINS` in Render to match its `https://` origin.

GitHub Pages cannot serve Python, run the C engine, or hold backend secrets.
Never put Supabase service-role keys in `api-config.js` or any other frontend
file. API authorization uses Supabase access tokens and database profile roles.

User registration and sign-in use Supabase Auth; the API validates Supabase
access tokens and reads profile roles from Postgres.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | API status |
| `POST` | `/emergency` | Create an emergency alert (valid Supabase user required) |
| `GET` | `/emergencies/me` | List the signed-in user's own emergency records |
| `GET` | `/emergencies` | List all emergency alerts (ADMIN required) |
| `PATCH` | `/emergency/{alert_id}/resolve` | Resolve an alert (ADMIN required) |
| `POST` | `/register` | Create a user account |
| `POST` | `/login` | Sign in |
| `GET` | `/me` | Get the signed-in user's account |

## Notes

- Tables and the profile trigger must be created by running the Supabase SQL
  setup before using the API.
- Ordinary users can retrieve their own records at `/emergencies/me`; only
  their own precise GPS coordinates are returned. The responder endpoint
  `/emergencies` requires the `ADMIN` profile role.
- Supabase `authenticated` users receive read-only table grants protected by
  owner/admin RLS policies. All writes go through the FastAPI backend; users
  cannot update `user_id`, and the service-role key remains backend-only.
- Keep `.env` and its secrets out of source control. Use distinct secrets for
  every deployment and do not use development settings for a public service.
- The default frontend API URL is for local development; point
  `api-config.js` to the deployed API before using the GitHub Pages site.
- Remove the obsolete `RESQLINK_ADMIN_TOKEN` variable from local or hosting
  environment settings. Administrator permissions now come from
  `public.profiles.role`.
- Run authorization tests with
  `python -m unittest discover -s backend -p "test_auth.py"`.
- Existing accounts and alerts in `database/resqlink.db` are not migrated
  automatically; export/import them separately if they need to be retained.
