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

### Public access through Cloudflare Tunnel

The existing `tradelens` Cloudflare Tunnel serves
`https://tradelens.othla.in` from Vite on port 5004. Its connector token stays
outside this repository.

In the Cloudflare Zero Trust dashboard, configure the `tradelens` tunnel's
Public Hostname as `tradelens.othla.in` with service type `HTTP` and URL
`localhost:5004`. The tunnel's current remote rule is for `othla.in`, which
returns a 404 for the TradeLens subdomain.

Start the local services first, then run the tunnel from the repository root:

```powershell
.\start-tunnel.ps1
```

Use the following command to restart TradeLens before connecting the tunnel:

```powershell
.\start-tunnel.ps1 -RestartServices
```

Run this variant once after pulling the Vite hostname allow-list change, so the
running frontend reloads its configuration.

To validate the local application and Cloudflare tunnel registration without
opening a connector:

```powershell
.\start-tunnel.ps1 -ValidateOnly
```

The launcher verifies the frontend and API, obtains the connector token only at
runtime, and runs the TradeLens connector in the current PowerShell window.
Press `Ctrl+C` to stop it. It deliberately leaves the existing `cloudflared`
Windows service untouched because that service currently operates the separate
AlgoOptions tunnel.
