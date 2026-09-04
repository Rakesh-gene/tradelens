# TradeLens Agent Guide

This file is the operating guide for contributors and coding agents working in
this repository. Preserve the established architecture and design language; do
not introduce a framework, dependency, storage layer, routing library, or
component system merely for convenience.

## Repository map

```
src/
  backend/                 Python HTTP API and PostgreSQL access
    auth/                  Authentication domain service, token helpers, models
    data_pipeline/         External market-data clients and ingestion jobs
    migrations/            Ordered, append-only PostgreSQL migrations
    repositories/          Repository implementations and migration runner
    server_http/           HTTP request/response boundary
  frontend/                Vite + React single-page application
    src/components/        Reusable presentational/form components
    src/pages/             Route-level page components
    src/styles.css         Shared design system and page styling
```

Keep domain logic out of HTTP handlers and React view components. The codebase
is deliberately small and explicit: add a focused file in the relevant layer
instead of creating broad abstractions.

## Working conventions

- Use `rg` for discovery and inspect the relevant files before changing them.
- Preserve existing user changes. Do not reset, discard, or reformat unrelated
  files.
- Use `apply_patch` for source edits.
- Run the narrowest relevant tests first, then the complete backend test suite
  and frontend build when a change crosses those boundaries.
- Do not commit generated files, logs, PID files, `node_modules`, virtual
  environments, or local `.env` files.
- Keep changes coherent and small. A new endpoint normally includes its
  service behavior, repository contract/implementation changes if needed, and
  tests in the same change.

## Backend architecture

### HTTP boundary

The backend uses Python's `ThreadingHTTPServer`; it is not Flask, FastAPI, or
Django. Routes belong in `src/backend/server_http/api.py`.

- Normalize paths using the existing `rstrip('/')` convention.
- Parse JSON with `_read_json()` and return JSON only through `_send_json()`.
- Return `400 Bad Request` for malformed payloads and business validation
  errors, `401 Unauthorized` for absent/invalid credentials, and `404 Not
  Found` for unknown routes.
- Keep handlers thin: extract request data, call a service, map the result to
  an HTTP payload, and return. Do not embed SQL or business rules in handlers.
- Maintain camelCase JSON fields for browser-facing payloads, while Python
  internals use snake_case.

### Services and repositories

Services in `auth/` own validation, authentication, password checks, and token
creation. Repositories own persistence only.

- Define repository behavior as a `Protocol` near the service that consumes
  it. This keeps unit tests able to use lightweight fakes or the existing
  in-memory repository.
- Keep PostgreSQL queries parameterized using psycopg placeholders (`%s` or
  named parameters); never interpolate user input into SQL strings.
- Return simple dictionaries from repository methods, as the current auth
  code does. Convert to dataclasses at a service boundary when a typed result
  makes the API clearer.
- `PostgresUserRepository` applies migrations on construction. Preserve this
  initialization behavior for database-backed repository additions.
- In-memory repositories must remain behaviorally compatible with their
  PostgreSQL counterparts so the HTTP tests remain meaningful.

### Authentication and JWTs

Authentication uses a signed HS256 access token.

- Login is `POST /api/login` with `email` and `password`.
- Protected requests use `Authorization: Bearer <token>`.
- `GET /api/auth/me` is the canonical session validation endpoint.
- Keep token signing and parsing in `auth/jwt.py`, not in handlers or React.
- JWT payloads currently include subject (`sub`), email, admin state, issue
  time, and expiration. Do not put passwords, password hashes, database DSNs,
  or other secrets in a token.
- Token signing is configured with `JWT_SECRET`. Local values live only in
  `src/backend/.env`; document a non-secret placeholder in `.env.example`.
- Passwords are currently stored using SHA-256 for compatibility with the
  existing schema. Do not change that format without a migration and a
  deliberate password-transition plan. New security work should favor an
  explicit upgrade path rather than silently breaking existing accounts.

### Data pipeline

External exchange behavior is isolated in `data_pipeline/`.

- Put NSE-specific HTTP headers, cookies, endpoint retry behavior, and future
  NSE calls in `NseApiClient` rather than a collector or route handler.
- Put import orchestration and CSV validation in `NseDataCollector`.
- Keep persistence behind an explicit repository method such as
  `upsert_equities`.
- Preserve the public scheduled-job method name `DownloadEquities()` and its
  PEP-8 `download_equities()` alias when extending this collector.
- Validate downloaded schemas before persisting rows. Do not store an HTML
  error response or malformed CSV as market data.

## Database and migrations

PostgreSQL is the application database. The local Docker instance is configured
via `DATABASE_URL` in `src/backend/.env`.

- Add schema changes as a new numbered `.sql` file in
  `src/backend/migrations/`; never modify an already-applied migration.
- Migration names must sort correctly, e.g. `006_create_watchlists.sql`.
- Migrations must be idempotent where practical (`CREATE TABLE IF NOT EXISTS`,
  `ADD COLUMN IF NOT EXISTS`) because local environments may be restarted.
- Seed data must be idempotent. Use `ON CONFLICT` and never overwrite a user's
  password or privileges during a normal migration.
- Use `TIMESTAMPTZ` for timestamps and database defaults such as `NOW()` when
  the database owns creation/update time.
- Use stable natural identifiers for upserts where the data source provides
  one (for NSE equities, this is `isin`).
- Never put a live DSN or secrets in migrations, source files, tests, docs, or
  commits. The local `.env` is intentionally git-ignored.

## Frontend architecture

The frontend is Vite + React with a deliberately minimal client-side router.
Do not add React Router unless a task explicitly calls for a routing-system
change.

- `App.jsx` owns pathname state, History API navigation, protected-route
  checks, and session restoration.
- Page-level views belong in `src/frontend/src/pages/`.
- Reusable form/UI behavior belongs in `src/frontend/src/components/`.
- Keep browser API calls (`fetch`, `sessionStorage`, History API) at a page or
  app boundary, not in generic presentational components.
- The access token is stored in `sessionStorage` under
  `tradelensAccessToken`. Sign-out must remove it and use
  `history.replaceState` before navigating to `/` so browser Back cannot reveal
  a previously protected screen.
- A protected page must validate its token through `/api/auth/me`; checking
  that a token merely exists is not sufficient.
- Use `fetch` against relative `/api/...` paths so Vite's development proxy
  remains effective.
- Use the automatic JSX runtime configured in `vite.config.js`. Existing files
  may import React explicitly for compatibility; preserve a file's established
  import style when editing it.

## Frontend design system

`src/frontend/src/topology.css` is the shared design-token source of truth;
`src/frontend/src/styles.css` consumes those tokens for component and page
rules. The system intentionally uses a small set of recurring visual tokens
rather than a third-party UI kit.

### Visual language

TradeLens is a dark, calm market-analysis product with warm amber accents.
Prefer restrained contrast and generous spacing over dashboards crowded with
controls.

| Token area | Established pattern | Use it for |
| --- | --- | --- |
| Canvas | near-black to brown/forest gradient with subtle radial glows | page backgrounds |
| Primary text | `#f6ecd6` / `#fff8ea` | headings and active input text |
| Muted text | `rgba(246, 236, 214, 0.58–0.8)` | descriptions, metadata, labels |
| Accent | `#ffdf84`, `#ffdc89`, `#f28d3f` | primary CTA, eyebrow text, focus state |
| Surfaces | `rgba(8–11, 10–14, 14–18, 0.42–0.78)` | cards and overlay panels |
| Borders | `rgba(255, 236, 199, 0.1–0.12)` | cards, inputs, pills |
| Radius | `1rem–1.25rem` controls/cards; `2rem` main panels; `999px` pills | all rounded UI |
| Shadows | `0 2rem 6rem rgba(0, 0, 0, 0.34)` | major elevated panels only |

### Components and interaction states

- Primary actions use the amber gradient, dark text, strong weight, and a
  restrained warm shadow (`.primary-button`).
- Secondary actions remain low-contrast dark surfaces with the standard warm
  border (`.secondary-button`).
- Inputs use the dark translucent surface and an amber focus ring; do not
  introduce bright blue browser-default focus styles.
- Cards use a warm translucent border, dark surface, and consistent corner
  radius. Avoid mixing sharp corners or opaque white cards into the app.
- Keep hover motion subtle (`translateY(-1px)` and short transitions). Do not
  add large transforms, bouncy animation, or flashing market-style effects.
- Retain semantic HTML, visible labels, keyboard-capable native controls, and
  descriptive `aria-label`s for form/page regions.

### Layout and responsiveness

- Base pages use `min-height: 100vh` with `clamp()`-based outer padding.
- Desktop login/signup layouts are two columns; the existing `980px` media
  query intentionally collapses them to one column.
- At the `640px` mobile breakpoint, use the mobile spacing/radius tokens from
  `topology.css`, stack dense rows (including password controls and form
  utility rows), keep navigation wrapped and left-aligned, and reduce display
  type without reducing hierarchy.
- Mobile controls must remain comfortably touchable: preserve the shared
  `--size-control-min-block` minimum height and avoid icon-only actions without
  an accessible name.
- Keep page content inside the viewport width at 320px and 390px. Do not use
  fixed card widths, horizontal overflow, or side-by-side form controls that
  force a narrow screen to scroll sideways.
- On mobile, normal content may scroll vertically, but auth forms should use
  compact panel padding and purposeful gaps; remove decorative or duplicate
  content before squeezing labels, inputs, or actions.
- A page that is intended to be a single-screen auth flow must fit the normal
  viewport without unnecessary vertical scroll. Before finishing such work,
  inspect `scrollHeight` against `window.innerHeight`.
- Scope compact spacing changes to the relevant modifier (for example,
  `.login-shell--signup`) instead of shrinking shared login styles and
  accidentally damaging another route.
- Overview pages may have more room, but should maintain the same heading,
  card, border, typography, and accent rules as auth pages.
- Add responsive rules for newly introduced multi-column grids. The overview
  grid, for example, should collapse at the same breakpoint as other layouts.

## Verification

Run commands from the indicated working directory.

```powershell
# Backend tests (repository root)
py -3.11 -m unittest discover -s src\backend -p "test*.py" -v

# Frontend production build
cd src\frontend
npm run build

# Restart local services (repository root; requires ownership of port listeners)
.\restart-services.ps1
```

For UI work, verify the relevant route after Vite has reloaded and confirm:

- no browser console errors;
- authentication requests return the expected status;
- protected routes redirect after token removal or expiry;
- sign-out does not allow Back to reveal protected content;
- the target auth page has no unintended vertical scroll at the normal desktop
  viewport and still works at 390px-wide and 320px-wide mobile breakpoints;
- no route has horizontal overflow at the tested mobile widths.

`restart-services.ps1` is responsible for replacing services on ports 5004 and
9004. If Windows denies stopping a listener owned by another account, report
the exact PID and require the user to run the script from an Administrator
PowerShell; do not silently claim the restart succeeded.

## Completion checklist

Before handing off a change, confirm the following as applicable:

- Architecture boundaries remain intact (handler -> service -> repository).
- New database schema is an append-only migration with safe repeat behavior.
- Secrets remain in local environment files and are absent from Git-tracked
  files and response logs.
- New API behavior has an automated backend test, including authorization
  failures where relevant.
- Frontend code builds successfully and the relevant route is visually checked.
- Visual additions use the established warm-dark tokens, radii, spacing, and
  responsive breakpoints.
- Local services are either verified healthy or any port/permission blocker is
  stated plainly.
