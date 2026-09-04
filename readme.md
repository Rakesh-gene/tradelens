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

### Frontend

```powershell
cd src/frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5004`. Requests beginning with `/api`
are proxied to the backend.
