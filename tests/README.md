# Test Setup

Run the test suite from the project root:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest
```

Verbose mode:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest -v
```

Coverage:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest --cov=app
```

## Test Database Safety

By default, tests use an isolated in-memory SQLite database. They do not use the normal development PostgreSQL database.

To use PostgreSQL for tests, set `TEST_DATABASE_URL` to a disposable database whose database name contains `test`:

```powershell
$env:TEST_DATABASE_URL='postgresql://postgres@localhost:5432/purchasing_ai_test'
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m pytest
```

The test harness refuses to run against a non-SQLite database unless the database name contains `test`, and it explicitly refuses the `purchasing_ai` development database.

## Alembic Verification

The test suite includes a lightweight Alembic config/head check. To verify migrations against a disposable test database manually:

```powershell
$env:TEST_DATABASE_URL='postgresql://postgres@localhost:5432/purchasing_ai_test'
$env:DATABASE_URL=$env:TEST_DATABASE_URL
$env:DEBUG='false'
.\.venv\Scripts\python.exe -c "from alembic.config import main; main(['upgrade', 'head'])"
```

Do not run migration verification against the development database.

## Future Codex Rule

Every future Codex task must update tests relevant to the changed behavior. If no test is added, Codex must explain exactly why.
