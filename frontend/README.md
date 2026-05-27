# Purchasing AI Frontend

This is the first small React/Vite frontend for the purchasing AI tool. It shows the product list and supplier mapping display fields exposed by the FastAPI backend.

## Setup

Install Node.js, then from `frontend/`:

```powershell
npm install
```

Copy the environment example if you need to override the backend URL:

```powershell
Copy-Item .env.example .env
```

Default backend URL:

```text
http://127.0.0.1:8000
```

## Run

Start the backend from the repository root:

```powershell
$env:DEBUG='false'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Start the frontend from `frontend/`:

```powershell
npm run dev
```

Open:

```text
http://localhost:5173
```

## Build

```powershell
npm run build
```

## Tests

```powershell
npm run test
```

Current frontend tests cover supplier display fallback rules:

- preferred supplier from `ProductSupplier`
- first mapping fallback
- legacy supplier fallback
- unmapped display

Future frontend tasks should add component-level tests for loading, error state, search/filtering, and expanded mapping rows.
