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

## Requirements

- Windows (the included emergency engine is `core/emergency64.dll`).
- Python 3.10 or later.
- A modern browser and, optionally, the VS Code Live Server extension.

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
trigger. This also enables Row Level Security; the backend uses its private
service-role key for database operations.

Generate an admin token for resolving dashboard alerts and set it as
`RESQLINK_ADMIN_TOKEN`. For example:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Paste that output into `.env`. The backend loads `.env` automatically from the
project root. Supabase Auth email confirmation can be configured under
**Authentication > Providers > Email** in the Supabase dashboard; when enabled,
users must confirm their email before signing in.

## Run the app

Start the API from the `backend` directory:

```powershell
Set-Location .\backend
python -m uvicorn app:app --reload
```

The API is available at <http://127.0.0.1:8000> and its interactive API
documentation is at <http://127.0.0.1:8000/docs>.

In a second terminal, start a static server from the project root, for example
with VS Code Live Server, and open `frontend/index.html`. Live Server's default
address (`http://127.0.0.1:5500`) is allowed by the API's CORS configuration.
The other frontend pages are `frontend/login.html`,
`frontend/register.html`, and `frontend/dashboard.html`. GPS access requires
browser permission.

The dashboard asks for the administrator token configured as
`RESQLINK_ADMIN_TOKEN`. User registration and sign-in use Supabase Auth; the
API validates Supabase access tokens and reads profile data from Postgres.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | API status |
| `POST` | `/emergency` | Create an emergency alert |
| `GET` | `/emergencies` | List emergency alerts |
| `PATCH` | `/emergency/{alert_id}/resolve` | Resolve an alert (admin token required) |
| `POST` | `/register` | Create a user account |
| `POST` | `/login` | Sign in |
| `GET` | `/me` | Get the signed-in user's account |

## Notes

- Tables and the profile trigger must be created by running the Supabase SQL
  setup before using the API.
- Keep `.env` and its secrets out of source control. Use distinct secrets for
  every deployment and do not use development settings for a public service.
- Existing accounts and alerts in `database/resqlink.db` are not migrated
  automatically; export/import them separately if they need to be retained.
- The frontend currently targets `http://127.0.0.1:8000`, and CORS is
  configured for the default local Live Server addresses.
