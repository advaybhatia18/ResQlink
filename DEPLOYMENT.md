# Deployment Guide (`DEPLOYMENT.md`)

ResQlink uses a split static-frontend + API-backend deployment:
- **Frontend:** GitHub Pages (`.github/workflows/pages.yml`)
- **Backend API:** Render Web Service (`render.yaml`) — `https://resqlink-ji0g.onrender.com`
- **Database & Auth:** Supabase

## 1. Backend Deployment on Render

[`render.yaml`](./render.yaml) defines the Render Python service:
- **Python runtime:** `3.12.8`
- **Build & Start Commands (must match your Render Root Directory):**
  - If Render **Root Directory** is `backend`:
    - **Build command:** `pip install -r requirements.txt`
    - **Start command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
  - If Render **Root Directory** is blank / repository root (as in `render.yaml`):
    - **Build command:** `pip install -r backend/requirements.txt`
    - **Start command:** `uvicorn app:app --app-dir backend --host 0.0.0.0 --port $PORT`
- **Native C Engine:** On Linux, `backend/emergency_engine.py` automatically compiles `core/emergency.c` -> `core/libemergency.so` on first load if missing (with Python fallback if compilation is unavailable in the container).

### Required Render Environment Variables
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Supabase publishable/anon key
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase service-role secret (**backend only**)
- `FRONTEND_ORIGINS`: Comma-separated allowed origins (`https://advaybhatia18.github.io,https://aksh.is-a.dev,http://127.0.0.1:5500,http://localhost:5500`)
- `PASSWORD_RESET_REDIRECT_URL`: Exact deployed URL to `password-reset.html` (`https://advaybhatia18.github.io/ResQlink/password-reset.html`)

## 2. Frontend Deployment on GitHub Pages

1. In GitHub **Settings > Pages**, choose **GitHub Actions** as the source.
2. In **Settings > Secrets and variables > Actions > Variables**, optionally set (defaults to `https://resqlink-ji0g.onrender.com`):
   - `RESQLINK_API_URL` = `https://resqlink-ji0g.onrender.com`
3. Push to `main`. `.github/workflows/pages.yml` will:
   - Run `python -m pytest` and `node --test frontend-tests/*.test.cjs`
   - Copy all `*.html`, `*.css`, and `*.js` files into `_site/`
   - Write `_site/api-config.js` from `RESQLINK_API_URL`
   - Verify `RESQLINK_API_URL` is non-empty and publish `_site/` to GitHub Pages.

## 3. Supabase Production Checklist

- Run `supabase/schema.sql` in the Supabase SQL Editor (works on fresh databases and idempotently on existing ones; includes an optional commented-out reset block at the top).
- Allowlist both production and local `password-reset.html` URLs in **Authentication > URL Configuration**.
- Promote your responder account in `public.profiles` (`role = 'ADMIN'`).
- Configure custom SMTP if public user registration/password recovery volume exceeds Supabase's default rate limits.
