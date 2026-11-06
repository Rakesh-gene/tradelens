# Ontology-backed equity setup chat

The authenticated shell's **Chat** button opens an overlay. There is no `/chat`
route. This first slice supports only:

> What is the setup this equity has today?

Type a question such as “What is the setup in Reliance today?” The server
resolves the equity's name or symbol; no separate symbol field is required.
“This equity” uses the security/pattern page's context. Explicit equity names
in the question take precedence; ambiguous names ask for clarification.
The answer shows active daily primary BASE, BREAKOUT and
PULLBACK setups at the latest available evaluation, with the actual evidence
date, four separate scores, adjusted price levels, source links and lineage.
Earlier-session/missing evidence is labelled. Counts, past setups, arbitrary
historical questions and portfolio actions are intentionally not enabled.

## Start the local ontology service

Prerequisites: the existing TradeLens PostgreSQL database, Python backend
requirements, Docker Desktop, and network access for the initial image build.
No second database is created. Run the operator setup from `src/backend`:

```powershell
python -m operations.cli ontology configure
```

This applies append-only migration `042`, creates the three semantic read views,
and provisions `tradelens_ontology_reader` with access to those views only.
It sets a database statement timeout and read-only transactions. A generated
role password is stored in **git-ignored** `infra/ontology/.env`, without printing
it. Repeating setup reuses that password. Normal role access is scoped to the
views; underlying market/auth tables are not granted to this role. The database
administrator running configure must be able to create/alter that role.

From the repository root:

```powershell
docker compose -f infra/ontology/compose.yaml up -d --build
```

The pinned Ontop 5.5.0 image and checksum-pinned PostgreSQL JDBC driver load the
ontology, static RDF facts, R2RML mappings and lens metadata. The endpoint binds
only to `127.0.0.1:8088`; never publish it through the public tunnel or proxy.
The backend alone exposes authenticated, restricted chat operations. Local
processes can reach the raw endpoint, so it must remain a trusted local service.

Verify a real virtual-graph query from `src/backend`:

```powershell
python -m operations.cli ontology verify --symbol RELIANCE
```

Verification prints bounded market evidence, not credentials or internal equity
IRIs. `verify` does not call Gemini and does not modify market data.

## Enable Ollama and the answer endpoint

Set these values in **local** `src/backend/.env` (never in frontend variables):

```dotenv
CHAT_ENABLED=true
CHAT_PROVIDER=ollama
ONTOP_URL=http://127.0.0.1:8088/sparql
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4:31b-cloud
OLLAMA_TIMEOUT_SECONDS=45
```

Restart the backend through the repository's service restart procedure. The
widget shows an unavailable state until chat is enabled with valid settings.
After this initial code update is running, administrators can instead open
**Chat → Settings** to choose Ollama, enter the model ID, Ollama and ontology endpoints,
enable chat, and set a model timeout (5–120 seconds; default 45). Save configuration persists only these allowlisted settings to
the local backend `.env` and applies them immediately, without a restart.
The existing API key is never returned; leaving its field blank preserves it.
Both reading and updating settings enforce administrator authorization on the
server, independent of whether the Settings button is visible.
Run `ollama pull gemma4:31b-cloud` if the model is missing and sign in to Ollama
for cloud access. This model runs in Ollama Cloud, through the local daemon;
it is not local inference. Gemini remains an optional provider with its own
server-side key. No live provider test runs automatically.

In this deliberately narrow slice, the catalog selects one registered SPARQL
template. Ollama identifies the equity from free-form wording; there is no
prompt pattern or intent whitelist rejection. The current answer remains an
explicitly dated daily-setup snapshot; removing wording restrictions does not
add historical queries. The model receives ontology definitions and bounded
retrieved evidence, then returns a constrained summary code and supporting
source IDs. The server validates that response and renders dated factual text
and cards from the graph results. The model cannot invent prices, change a state,
choose SQL/SPARQL, or supply advice. This is constrained grounding, not an
unrestricted language agent. Future language capabilities extend the catalog,
query templates and validated answer schemas together.

Missing configuration or unavailable/invalid Ontop responses fail explicitly.
If Ontop retrieval and evidence validation succeed but Gemini times out or is
temporarily unreachable/unavailable, the response preserves those graph facts
as `ontologyEvidenceOnly`, with a null model, provider error code, partial flag
and an explicit warning that no LLM explanation was generated. It never replaces
Ontop with API-only data. Invalid model outputs/access settings still fail.
The normal product remains available if chat is disabled.

## Files and semantics

| Artifact | Responsibility |
| --- | --- |
| `src/backend/ontology/tradelens.ttl` | RDFS/OWL vocabulary and lightweight subclass axioms |
| `src/backend/ontology/facts.ttl` | Queryable lifecycle-state individuals and canonical codes |
| `src/backend/ontology/shapes.ttl` | SHACL constraints for dated snapshots and score observations |
| `src/backend/ontology/catalog.json` | Versioned first capability and its permitted semantic vocabulary |
| `src/backend/repositories/semantic/tradelens.r2rml.ttl` | Virtual RDF mappings; database values remain in PostgreSQL |
| `src/backend/repositories/semantic/lenses.json` | True view keys/non-null constraints for query optimization |
| `src/backend/repositories/semantic/queries/equity_setup_today.rq` | Registered bounded semantic query |
| `src/backend/migrations/042_create_chat_semantic_views.sql` | Read-only projections retaining latest-evidence/active-state semantics |

The query asks for `PrimarySetupSnapshot`; only specific Base/Breakout/Pullback
subclasses are mapped. Ontop must use the ontology hierarchy to find them.
Scores are typed observations, separately from lifecycle states. Missing SQL
values produce no corresponding triple and remain JSON null in the answer.
Read views retain every eligible instance, without Setups' per-equity winner
collapse. They exclude evidence superseded by a newer feature/pattern date.

Snapshot IRIs identify the currently retained instance version/date. They do
not manufacture an immutable archive from mutable source rows. A missing
pattern evaluation cannot establish a verified zero. “Today” uses Asia/Kolkata;
the response separately records the requested date and actual evidence date.
Prior-session evidence is conservatively labelled even on nontrading days.

Source ontology/mapping/lens/query hashes are recorded in response provenance.
After modifying the embedded ontology, mappings, facts or lenses, rebuild the
Ontop image and restart the backend together. A deployment must use matching
artifacts; automatic remote manifest reconciliation is not implemented yet.

## API

Bearer authentication is mandatory for both endpoints:

- `GET /api/chat/capabilities`: enabled configuration and the supported question.
- `POST /api/chat/messages`: `{ "message": "What is the setup in Reliance today?" }`.
- Optional `contextSymbol` supplies validated page context for “this equity”.
- Administrator-only `GET` and `PATCH /api/admin/chat/configuration` read safe
  configuration metadata and save `enabled`, `model`, `ontologyUrl` and an
  optional write-only `apiKey`.

Other questions return `400 QUESTION_NOT_SUPPORTED`; client-supplied roles,
owner IDs, evidence, extra fields and arbitrary query fragments are rejected.
Errors use `{ "error": { "code", "message", "requestId" } }`. Provider errors
are sanitized. The response includes actual dates, stale/partial flags,
warnings, setup evidence, nulls and lineage. Credentials and internal ISINs are
not exposed by chat responses.

Limits: 4 concurrent requests globally, one per user, six per user per minute,
32KiB request body, 4,000-character question, 25 visible setups (26-row sentinel),
1MiB upstream responses, 10-second Ontop and configurable Gemini socket timeouts,
and an 8-second PostgreSQL statement timeout. Limits are process-local; they
reset after restart. The prototype does not persist conversations, quotas or
spend budgets. Reopening preserves the answer in browser memory until sign-out,
reload or a new equity question. Closing does not promise provider cancellation.
Socket timeouts are not a strict whole-turn CPU deadline inside Ontop.

Gemini errors distinguish actual timeouts (504 `UPSTREAM_TIMEOUT`) from blocked
network permissions, DNS/TLS failures, rejected credentials, missing models and
provider rate limits. The old generic “could not be reached within its time
limit” message did not prove a timeout occurred. A blocked server process needs
permitted outbound HTTPS; increasing its timeout cannot fix denied access.
For the current constrained citation/summary capability, compatible Gemini 3
Flash models use low reasoning and Gemini 2.5 Flash uses a zero thinking budget.
This setting does not change engine calculations, geometry or scores.

## Verify changes

Ordinary backend/frontend tests remain offline with fake provider/graph adapters.
For RDF parsing, real entailment and SHACL checks, install
`src/backend/requirements-ontology.txt` into the development environment, then
run from the repository root:

```powershell
python -m unittest discover -s src/backend -p 'test*.py'
```

To additionally exercise the actual local PostgreSQL/Ontop path:

```powershell
$env:TRADELENS_RUN_ONTOLOGY_TESTS = '1'
python -m unittest discover -s src/backend -p 'test_ontology.py' -v
Remove-Item Env:TRADELENS_RUN_ONTOLOGY_TESTS
```

This opt-in test is bounded and read-only; it compares actual RDF bindings to
the semantic views and the existing latest-evidence predicate. The checked-in
RDF fixture proves subclass reasoning and missing optional evidence offline;
SHACL tests include deliberately invalid scores/dates. Live NSE is never called.

Frontend: `npm test` and `npm run build` from `src/frontend`. Verify the modal
at desktop/tablet/390px/320px, keyboard focus, Escape/Close/reopen, missing
configuration, expired auth, failure/retry, and URL/history preservation.
