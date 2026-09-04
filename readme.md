# TradeLens

This repository contains a Vite-powered React frontend and a Python backend.

## Setup

### Backend

```powershell
cd src/backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe app.py
```

The backend runs at `http://localhost:9004`.

For local PostgreSQL, set `DATABASE_URL` in `src/backend/.env`. A ready-to-copy
example is provided in `src/backend/.env.example`. On first startup, migrations
create the application tables and the local administrator:

- Email: `admin@tradelens.local`
- Password: `ChangeMe123!` (change it before using outside local development)

### Frontend

```powershell
cd src/frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5004`. Requests beginning with `/api`
are proxied to the backend.

### Restarting locally

With PostgreSQL running, start or restart both services from the repository root:

```powershell
.\restart-services.ps1
```

The script starts the backend on port 9004 and Vite on port 5004, and writes
their output to `backend.log` and `frontend.log`.
