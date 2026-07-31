# Render Staging Deployment

This repository is prepared for a Render staging/demo deployment with:

- Render Web Service: FastAPI backend.
- Render Static Site: React/Vite frontend.
- Render Postgres: staging database.
- Alembic migrations run as the backend pre-deploy command.
- Secrets entered in the Render dashboard only.

## Deployment Readiness Audit

### Python Version

The repository now pins `.python-version` to `3.12.8`.

Python 3.12 is a stable deployment target with broad package support for FastAPI, SQLAlchemy, Alembic, Pydantic, Uvicorn, and `psycopg2-binary`. The local workstation currently has newer Python available, but staging should not depend on Python 3.14 while the wider ecosystem is still catching up.

### Backend Runtime Dependencies

`requirements.txt` is a development/local environment file and includes notebooks, test tools, data import tools, and GPU/PyTorch packages.

`requirements-deploy.txt` is the backend deployment file. It includes only the FastAPI runtime stack, SQLAlchemy/Alembic, PostgreSQL driver, Pydantic settings, Uvicorn, `httpx`, JWT validation, and Argon2 password verification.

Excluded from deployment:

- `pytest`, `pytest-cov`
- Jupyter/notebook packages
- CUDA/PyTorch packages
- pandas/numpy/matplotlib import-analysis tooling
- local-only development packages

### App Imports

`app.main` imports all backend routes and models. The deployed app should import with only runtime dependencies installed from `requirements-deploy.txt`.

OrderPro sync scripts and CSV import scripts are not part of the Render web service runtime.

### Configuration

Required environment variables for staging:

- `DATABASE_URL`
- `DEBUG=false`
- `DATABASE_AUTO_CREATE_TABLES=false`
- `AUTH_ENABLED`
- `FRONTEND_ORIGIN`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD_HASH`
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM=HS256`
- `ACCESS_TOKEN_EXPIRE_MINUTES=60`
- `ORDERPRO_API_BASE_URL`
- `ORDERPRO_SYNC_ENABLED=false`
- `LLM_PROVIDER=mock`
- `ENABLE_REAL_LLM=false`

Optional staging variables:

- `CORS_ORIGINS`
- `VITE_AUTH_ENABLED` for the frontend static site
- `ORDERPRO_API_TOKEN`
- `ORDERPRO_TIMEOUT_SECONDS`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

`ORDERPRO_SYNC_ENABLED` must remain `false` until a separate staging read-only OrderPro token is configured and sync is intentionally run.

`ENABLE_REAL_LLM` must remain `false` for the initial demo. The app should use `LLM_PROVIDER=mock`.

### CORS

Local development origins remain enabled:

- `http://localhost:5173`
- `http://127.0.0.1:5173`

Deployment origins are added through `FRONTEND_ORIGIN` or comma-separated `CORS_ORIGINS`.

The backend does not use wildcard CORS with credentials.

### Authentication

The staging backend uses single-admin authentication when `AUTH_ENABLED=true`.

Public endpoints:

- `GET /health`
- `POST /auth/login`

All business data and mutation endpoints require:

```text
Authorization: Bearer <access_token>
```

When `DEBUG=false`, `/docs`, `/redoc`, and `/openapi.json` are disabled so API documentation is not publicly exposed.

Temporary bypass:

- `AUTH_ENABLED=false` on the backend allows protected routes without a bearer token.
- `VITE_AUTH_ENABLED=false` on the frontend skips the login screen and sends requests without an `Authorization` header.
- These values must be changed together.
- Disabling authentication exposes the tool to anyone with the URL.
- To restore authentication, set both `AUTH_ENABLED=true` and `VITE_AUTH_ENABLED=true`, then redeploy both services.

When `DEBUG=false` and `AUTH_ENABLED=true`, the backend requires `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH`, and `JWT_SECRET_KEY` at startup. When `AUTH_ENABLED=false`, those authentication secrets are not required for startup, but the login/JWT implementation remains in the codebase for reactivation.

Generate a JWT secret locally:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Generate an admin password hash without placing the password in shell history:

```powershell
@'
from getpass import getpass
from pwdlib import PasswordHash
print(PasswordHash.recommended().hash(getpass("Admin password: ")))
'@ | .\.venv\Scripts\python.exe
```

Enter only the generated hash in `ADMIN_PASSWORD_HASH`. Do not enter or commit the plaintext password.

To rotate the admin password, generate a new hash and replace `ADMIN_PASSWORD_HASH` in Render. To invalidate existing sessions, rotate `JWT_SECRET_KEY` and redeploy/restart the backend.

### Frontend API URL

The frontend reads `import.meta.env.VITE_API_BASE_URL`.

Local fallback:

```text
http://127.0.0.1:8000
```

The Render Static Site must set `VITE_API_BASE_URL` to the backend Render HTTPS URL in the dashboard. Do not hard-code the Render URL in source.

### Database Migration Behavior

Render backend pre-deploy command:

```bash
python -m alembic upgrade head
```

The baseline Alembic migration creates the pre-Alembic core schema on a clean database before later migrations add product suppliers, purchase order workflow tables, OrderPro fields, seasonality tables, and review tables.

`Base.metadata.create_all()` remains gated behind `DATABASE_AUTO_CREATE_TABLES`; staging must keep this `false`.

Optional disposable database check:

```powershell
$env:DISPOSABLE_DATABASE_URL = "<Render external URL for a disposable database>"
.\.venv\Scripts\python.exe scripts\check_clean_database_migrations.py --database-url "$env:DISPOSABLE_DATABASE_URL"
```

The check refuses the normal local development database and non-empty databases unless `--allow-non-empty` is passed.

### Sensitive Data Risks

The current local database is not safe to publish directly. Synced OrderPro order history may contain customer names, emails, phone numbers, order numbers, and commercial data.

Do not commit:

- `.env` files
- database dumps
- SQL exports
- OrderPro raw sample payloads
- `tmp/` reports
- API keys or database URLs with passwords

The demo should not be publicly shared while authentication is disabled. If `AUTH_ENABLED=false` and `VITE_AUTH_ENABLED=false`, anyone with the URL can access business data.

## Render Blueprint

`render.yaml` defines:

- `purchasing-ai-staging-db`: Render Postgres, free plan, PostgreSQL 17.
- `purchasing-ai-api`: Python web service.
- `purchasing-ai-frontend`: Vite static site.

Automatic deploys are disabled in the Blueprint with `autoDeployTrigger: 'off'` so the first staging data import can be controlled manually.

## Deployment Steps

### 1. Run Local Tests

Backend:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -v
```

Frontend:

```powershell
cd frontend
npm run test
npm run build
```

Secret safety:

```powershell
.\.venv\Scripts\python.exe scripts\check_deployment_secrets.py --root .
```

### 2. Commit and Push

Commit only source, docs, tests, and deployment config.

Do not commit `.env`, `tmp/`, database dumps, raw OrderPro payloads, or local sample reports.

### 3. Create the Render Blueprint

In Render, create a Blueprint from the GitHub repository using `render.yaml`.

The Blueprint defines the Postgres database, backend web service, and frontend static site.

### 4. Enter Backend Environment Values

Render supplies `DATABASE_URL` from `purchasing-ai-staging-db`.

Manually enter:

- `FRONTEND_ORIGIN`: the frontend Render URL, for example `https://purchasing-ai-frontend.onrender.com`.
- `ADMIN_EMAIL`: the single staging administrator email.
- `ADMIN_PASSWORD_HASH`: Argon2 hash generated locally with `pwdlib`.
- `JWT_SECRET_KEY`: high-entropy random secret generated locally.
- `ORDERPRO_API_TOKEN`: leave blank for the initial demo unless a staging read-only token is intentionally configured.
- `OPENAI_API_KEY`: leave blank for the initial demo.
- `OPENAI_MODEL`: leave blank unless real LLM is explicitly enabled in a later task.

Confirm:

- `DEBUG=false`
- `DATABASE_AUTO_CREATE_TABLES=false`
- `AUTH_ENABLED=false` only for the temporary unauthenticated staging window.
- `ORDERPRO_SYNC_ENABLED=false`
- `LLM_PROVIDER=mock`
- `ENABLE_REAL_LLM=false`

For the frontend static site, set:

- `VITE_API_BASE_URL`: the backend Render HTTPS URL.
- `VITE_AUTH_ENABLED=false` only while the backend also has `AUTH_ENABLED=false`.

To bring login back, set backend `AUTH_ENABLED=true`, set frontend `VITE_AUTH_ENABLED=true`, ensure the admin secrets are present, and redeploy both services.

### 5. Enter Frontend Environment Values

Set:

```text
VITE_API_BASE_URL=https://<backend-service>.onrender.com
```

Do not enter backend-only secrets in frontend environment variables.

### 6. Deploy Database, Backend, and Frontend

Deploy the database first.

Deploy the backend and confirm the pre-deploy Alembic migration command succeeds.

Deploy the frontend after `VITE_API_BASE_URL` points at the backend HTTPS URL.

### 7. Smoke Test

Backend:

```powershell
Invoke-RestMethod https://<backend-service>.onrender.com/health
```

Login when authentication is enabled:

```powershell
$login = Invoke-RestMethod `
  -Method Post `
  -Uri "https://<backend-service>.onrender.com/auth/login" `
  -ContentType "application/json" `
  -Body (@{ email = "<admin-email>"; password = "<admin-password>" } | ConvertTo-Json)

Invoke-RestMethod `
  -Uri "https://<backend-service>.onrender.com/auth/me" `
  -Headers @{ Authorization = "Bearer $($login.access_token)" }
```

Frontend:

- Open the frontend Render URL.
- Confirm the frontend loads.
- Confirm it can call the backend without CORS errors.

### 8. Import Staging Data Later

Do not upload local database dumps to Git.

If a staging database backup is needed, transfer it securely outside the repository and review it for customer personal data first.

Keep OrderPro sync disabled until a staging read-only token is configured.

### 9. Verify App Flows

After staging data exists, verify:

- Product list loads.
- Product forecast loads.
- Supplier forecast loads.
- Recommendation review works.
- Draft PO creation works.
- POs remain draft until manually submitted and approved.

### 10. Roll Back or Disable Demo

If the demo needs to be disabled:

- Turn off frontend/backend services in Render.
- Keep `ORDERPRO_SYNC_ENABLED=false`.
- Rotate any staging tokens that were entered.
- If sensitive data was imported, restrict or remove the staging database.

## Remaining Blockers Before Public Demo

- Staging data may include customer personal information.
- OrderPro sync should use a staging/read-only token only.
- OpenAI provider should remain disabled until a separate security review.
- Recommendations are advisory only.
- Purchase orders require human approval and must not be externally issued by the demo.
